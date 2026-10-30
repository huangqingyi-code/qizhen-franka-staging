"""Failure/unknown state contract; all robot reads and vendor actions are fixtures."""

import json
import subprocess
import unittest
from unittest.mock import patch

import test_adapter as original
from core import canonical
from jsonschema import Draft202012Validator
from stop_guard import requires_stop_check, session_blocks


class FailureStateTests(unittest.TestCase):
    def setUp(self):
        self.fixture = original.AdapterTests()
        self.fixture.setUp()
        self.b = self.fixture.b

    def tearDown(self):
        self.fixture.tearDown()

    def session(self):
        s = self.fixture.failed_session()
        s.update(state="unknown", backend="real")
        return s

    def status(self, s):
        return self.b.invoke("franka.session.status", {"session_id": s["session_id"]})

    def test_unknown_blocks_even_with_old_operator_assertion(self):
        for verified in (False, True):
            self.assertTrue(session_blocks({"state": "unknown", "control_lock_pending": False,
                                           "operator_verified_stopped": verified}))
        self.assertFalse(session_blocks({"state": "failed", "control_lock_pending": False}))

    def test_finish_motion_failure_stays_unknown_while_valid_state_fails_stop_check(self):
        moving = self.fixture.stationary()
        moving["dq"][0] = 0.010001
        for reading in (self.fixture.stationary(2), moving, {"robot_mode": 1}):
            s = self.session()
            with self.subTest(reading=reading), patch("stop_guard.read_snapshot", return_value=reading):
                self.b.finish(s, 1, {"hardware_motion_verified": False}, "MOTION_FAILED")
                self.assertEqual(s["state"], "unknown")
                self.assertTrue(s["control_lock_pending"])
                self.assertFalse(s["physical_stop_verified"])
                self.assertFalse(s["stop_verification"]["state_unavailable"])
                self.assertTrue(session_blocks(s))
                self.assertEqual(self.status(s)["state"], "unknown")

    def test_stationary_failure_is_failed_and_releases_without_replaying(self):
        s = self.session()
        with patch("stop_guard.read_snapshot", return_value=self.fixture.stationary()), \
             patch("stop_guard.time.sleep"), patch("broker.command") as command:
            self.b.finish(s, 1, {"hardware_motion_verified": False}, "MOTION_FAILED")
            self.assertEqual(s["state"], "failed")
            self.assertTrue(s["physical_stop_verified"])
            self.assertFalse(s["control_lock_pending"])
            self.assertFalse(session_blocks(s))
            command.assert_not_called()

    def test_unknown_status_converges_to_failed_same_session_and_preserves_error(self):
        s = self.session()
        with patch("stop_guard.read_snapshot", return_value=self.fixture.stationary(2)):
            self.assertEqual(self.status(s)["state"], "unknown")
        with patch("stop_guard.read_snapshot", return_value=self.fixture.stationary()), \
             patch("stop_guard.time.sleep"), patch("broker.command") as command:
            result = self.status(s)
            command.assert_not_called()
        self.assertEqual(result["state"], "failed")
        self.assertEqual(result["session_id"], s["session_id"])
        self.assertEqual(result["error"], "PROCESS_EXIT_1")
        self.assertEqual(len(self.b.store.data["sessions"]), 1)
        persisted = json.loads(self.b.store.path.read_text())["sessions"][s["session_id"]]
        self.assertEqual(persisted["state"], "failed")
        # Querying this old resolved session must not sample or relock a new robot operation.
        with patch("stop_guard.read_snapshot", side_effect=AssertionError("unexpected robot read")):
            self.assertEqual(self.status(s)["state"], "failed")

    def test_explicit_offline_plan_and_prepare_failure_never_read_robot(self):
        for mode in ("plan", "prepare"):
            s = self.session()
            s.update(operation_id="franka.pipeline.start", parameters={"mode": mode, "skip_leveling": True})
            with self.subTest(mode=mode), patch("broker.verify_stopped", side_effect=AssertionError("hardware read")):
                self.b.finish(s, 1, {"receipt": {"status": "failed"}}, "PLANNING_FAILED")
                result = self.status(s)
            self.assertEqual(result["state"], "failed")
            self.assertFalse(result["control_lock_pending"])
            self.assertFalse(result["physical_stop_verified"])
            self.assertFalse(result["stop_verification"]["required"])

    def test_prepare_without_skip_and_execute_are_not_assumed_offline(self):
        for parameters in ({"mode": "prepare"}, {"mode": "plan"},
                           {"mode": "execute", "skip_leveling": True}):
            s = self.session()
            s.update(operation_id="franka.pipeline.start", parameters=parameters)
            self.assertTrue(requires_stop_check(s))
            with patch("stop_guard.read_snapshot", return_value=self.fixture.stationary(2)):
                self.b.finish(s, 1, {}, "FAILED")
            self.assertEqual(s["state"], "unknown")
            self.assertTrue(s["control_lock_pending"])

    def test_prelaunch_failure_and_read_only_failure_do_not_require_stop(self):
        for op, data in (("franka.delta.move", {"started": False}), ("franka.state.read", {})):
            s = self.session()
            s["operation_id"] = op
            with patch("broker.verify_stopped", side_effect=AssertionError("hardware read")):
                self.b.finish(s, 1, data, "PRELAUNCH_OR_READ_FAILED")
            self.assertEqual(s["state"], "failed")
            self.assertFalse(s["stop_verification"]["required"])
            self.assertFalse(session_blocks(s))

    def test_restart_quarantines_interrupted_and_legacy_unverified_sessions(self):
        for state in ("running", "waiting_confirmation", "cancelling", "unknown", "failed"):
            s = self.session()
            s.update(state=state, control_lock_pending=False, operator_verified_stopped=True,
                     confirmation={"old": True})
            self.b.save()
            with patch("stop_guard.read_snapshot", side_effect=AssertionError("startup robot read")):
                self.b = original.Broker(self.fixture.c)
            result = self.b.store.data["sessions"][s["session_id"]]
            self.assertEqual(result["state"], "unknown")
            self.assertTrue(result["control_lock_pending"])
            self.assertIsNone(result["confirmation"])
            self.assertTrue(session_blocks(result))

    def test_restart_preserves_resolved_failed_and_explicit_offline_failure(self):
        s = self.session()
        s.update(state="failed", physical_stop_verified=True, control_lock_pending=False)
        self.b.save()
        self.b = original.Broker(self.fixture.c)
        self.assertEqual(self.b.store.data["sessions"][s["session_id"]]["state"], "failed")
        s = self.b.store.data["sessions"][s["session_id"]]
        s.update(state="running", operation_id="franka.pipeline.start",
                 parameters={"mode": "prepare", "skip_leveling": True})
        self.b.save()
        self.b = original.Broker(self.fixture.c)
        result = self.b.store.data["sessions"][s["session_id"]]
        self.assertEqual(result["state"], "failed")
        self.assertFalse(result["stop_verification"]["required"])

    def test_same_request_returns_existing_unknown_then_failed_and_never_launches(self):
        s = self.session()
        args = {"request_id": "same", "translation_m": [0.001, 0, 0]}
        self.b.store.data["requests"]["same"] = {
            "input": canonical({"operation": s["operation_id"], "parameters": args}),
            "session_id": s["session_id"]}
        self.b.save()
        for state, expected in ((self.fixture.stationary(2), "unknown"),
                                (self.fixture.stationary(), "failed")):
            with patch("stop_guard.read_snapshot", return_value=state), patch("stop_guard.time.sleep"), \
                 patch("broker.command") as command:
                result = self.b.invoke("franka.delta.move", args)
                command.assert_not_called()
                self.assertEqual(result["session_id"], s["session_id"])
                self.assertEqual(result["state"], expected)
        self.assertEqual(len(self.b.store.data["sessions"]), 1)

    def test_status_contract_validates_failed_unknown_and_no_motion_proof(self):
        schema = original.OPERATIONS["franka.session.status"]["output_schema"]["properties"]["data"]
        validator = Draft202012Validator(schema)
        s = self.session()
        with patch("stop_guard.read_snapshot", side_effect=OSError("offline")):
            validator.validate(self.status(s))
        with patch("stop_guard.read_snapshot", return_value=self.fixture.stationary()), patch("stop_guard.time.sleep"):
            validator.validate(self.status(s))
        s.update(operation_id="franka.pipeline.start", state="unknown",
                 parameters={"mode": "prepare", "skip_leveling": True})
        validator.validate(self.status(s))
        bad = dict(self.status(s), state="unknown", control_lock_pending=False)
        self.assertTrue(list(validator.iter_errors(bad)))
        bad = dict(self.status(s), state="failed", control_lock_pending=True)
        self.assertTrue(list(validator.iter_errors(bad)))


    def test_unknown_missing_operation_metadata_is_not_assumed_motion_free(self):
        self.assertTrue(requires_stop_check({"state": "unknown", "backend": "real"}))
        self.assertTrue(session_blocks({"state": "unknown"}))

    def test_unavailable_reader_releases_without_claiming_stop_or_replaying(self):
        for error in (OSError("offline"), subprocess.TimeoutExpired("reader", 2),
                      subprocess.CalledProcessError(1, "reader"), ValueError("bad json")):
            with self.subTest(error=error):
                s = self.session()
                with patch("stop_guard.read_snapshot", side_effect=error), \
                     patch("broker.command") as command:
                    result = self.status(s)
                self.assertEqual(result["state"], "failed")
                self.assertFalse(result["control_lock_pending"])
                self.assertFalse(result["physical_stop_verified"])
                self.assertFalse(result["stop_verification"]["verified"])
                self.assertTrue(result["stop_verification"]["state_unavailable"])
                self.assertIn("error", result["stop_verification"])
                self.assertEqual(result["error"], "PROCESS_EXIT_1")
                self.assertFalse(session_blocks(s))
                command.assert_not_called()
                schema = original.OPERATIONS["franka.session.status"]["output_schema"]["properties"]["data"]
                Draft202012Validator(schema).validate(result)

    def test_unavailable_second_read_releases_and_retains_first_sample(self):
        s = self.session()
        with patch("stop_guard.read_snapshot", side_effect=[self.fixture.stationary(), OSError("offline")]), \
             patch("stop_guard.time.sleep"):
            result = self.status(s)
        self.assertEqual(result["state"], "failed")
        self.assertEqual(len(result["stop_verification"]["samples"]), 1)
        self.assertFalse(result["physical_stop_verified"])
        self.assertTrue(result["stop_verification"]["state_unavailable"])

    def test_moving_sample_is_not_overridden_by_later_reader_unavailability(self):
        s = self.session()
        moving = self.fixture.stationary()
        moving["dq"][0] = 0.010001
        with patch("stop_guard.read_snapshot", side_effect=[moving, OSError("offline")]) as reader:
            result = self.status(s)
        reader.assert_called_once()
        self.assertEqual(result["state"], "unknown")
        self.assertTrue(result["control_lock_pending"])
        self.assertFalse(result["stop_verification"]["state_unavailable"])

    def test_unavailable_release_survives_restart_status_and_same_request(self):
        s = self.session()
        args = {"request_id": "same", "translation_m": [0.001, 0, 0]}
        self.b.store.data["requests"]["same"] = {
            "input": canonical({"operation": s["operation_id"], "parameters": args}),
            "session_id": s["session_id"]}
        with patch("stop_guard.read_snapshot", side_effect=OSError("offline")):
            released = self.status(s)
        self.b = original.Broker(self.fixture.c)
        with patch("stop_guard.read_snapshot", side_effect=AssertionError("resolved session reread")), \
             patch("broker.command") as command:
            for result in (self.status(s), self.b.invoke("franka.delta.move", args)):
                self.assertEqual(result["state"], "failed")
                self.assertEqual(result["session_id"], released["session_id"])
                self.assertEqual(result["stop_verification"], released["stop_verification"])
                self.assertFalse(result["control_lock_pending"])
                self.assertFalse(result["physical_stop_verified"])
            command.assert_not_called()

    def test_unavailable_release_allows_new_request_without_replaying_old_one(self):
        s = self.session()
        with patch("stop_guard.read_snapshot", side_effect=OSError("offline")):
            self.status(s)
        with patch("broker.command", return_value=(["fixture_vendor"], 10)) as command, \
             patch("broker.threading.Thread") as thread:
            result = self.b.invoke("franka.delta.move", {
                "request_id": "new_after_unavailable", "translation_m": [0.001, 0, 0]})
        command.assert_called_once()
        thread.return_value.start.assert_called_once()
        self.assertNotEqual(result["session_id"], s["session_id"])
        self.assertEqual(result["state"], "running")

    def test_failed_contract_requires_explicit_unavailable_reason_when_stop_unverified(self):
        s = self.session()
        with patch("stop_guard.read_snapshot", side_effect=OSError("offline")):
            result = self.status(s)
        schema = original.OPERATIONS["franka.session.status"]["output_schema"]["properties"]["data"]
        validator = Draft202012Validator(schema)
        validator.validate(result)
        for value in (False, None, "true"):
            bad = json.loads(json.dumps(result))
            if value is None:
                bad["stop_verification"].pop("state_unavailable")
            else:
                bad["stop_verification"]["state_unavailable"] = value
            self.assertTrue(list(validator.iter_errors(bad)))

    def test_cancelled_before_launch_declares_no_motion_without_claiming_robot_stop(self):
        s = self.session()
        s["state"] = "cancelled"
        with patch("broker.verify_stopped", side_effect=AssertionError("hardware read")):
            self.b.finish(s, 130, {"started": False})
        self.assertEqual(s["state"], "cancelled")
        self.assertFalse(s["physical_stop_verified"])
        self.assertFalse(s["control_lock_pending"])
        self.assertFalse(s["stop_verification"]["required"])
