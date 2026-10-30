"""Explicit operator force-stop; fake broker/vendor only, no robot or live state access."""

import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import test_adapter as original
from core import canonical


spec = importlib.util.spec_from_file_location(
    "broker_control_force_stop_test", original.ROOT / "scripts/broker_control.py")
control = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control)


class ForceStopTests(unittest.TestCase):
    def setUp(self):
        self.fixture = original.AdapterTests()
        self.fixture.setUp()
        self.b = self.fixture.b

    def tearDown(self):
        self.fixture.cleanup_test_broker()
        self.fixture.tearDown()

    def test_force_stop_preserves_evidence_and_old_request_never_replays_after_restart(self):
        config, env = self.fixture.broker_control_fixture()
        s = self.fixture.failed_session()
        s.update(state="unknown", backend="real", confirmation={"old": "prompt"})
        args = {"request_id": "original_motion", "translation_m": [0.001, 0, 0]}
        self.b.store.data["requests"][args["request_id"]] = {
            "input": canonical({"operation": s["operation_id"], "parameters": args}),
            "session_id": s["session_id"]}
        done = {**s, "session_id": "session_done", "state": "succeeded",
                "control_lock_pending": False}
        self.b.store.data["sessions"][done["session_id"]] = done
        self.b.save()
        before = json.loads(self.b.store.path.read_text())
        stopped = self.fixture.run_broker_control(config, env, "--force-stop")
        self.assertEqual(stopped.returncode, 0, stopped.stderr)
        report = json.loads(stopped.stdout)
        archive = Path(report["archive"])
        self.assertEqual(archive.stat().st_mode & 0o777, 0o600)
        audit = json.loads(archive.read_text())
        self.assertEqual(audit["state"], before)
        self.assertTrue(audit["locks_released"])
        self.assertFalse(audit["physical_stop_verified"])
        after = json.loads(self.b.store.path.read_text())
        self.assertEqual(after["sessions"], {done["session_id"]: done})
        self.assertEqual(after["artifacts"], before["artifacts"])
        self.assertTrue(Path(s["directory"]).is_dir())
        self.b = original.Broker(self.fixture.c)
        self.fixture.b = self.b
        self.assertIsNone(self.b.blocked())
        with patch("broker.command") as command, patch("stop_guard.read_snapshot") as reader:
            archived = self.b.invoke("franka.delta.move", args)
            command.assert_not_called()
            reader.assert_not_called()
        self.assertTrue(archived["archived"])
        self.assertEqual(archived["session_id"], s["session_id"])
        self.assertEqual(archived["state"], "failed")
        self.assertFalse(archived["control_lock_pending"])
        self.assertFalse(archived["physical_stop_verified"])
        self.assertTrue(archived["stop_verification"]["required"])
        self.assertFalse(archived["stop_verification"]["verified"])
        self.assertIsNone(archived["confirmation"])
        # A new request can reach the vendor launcher, but this test never runs it.
        with patch("broker.command", return_value=(["fixture_vendor"], 10)) as command, \
             patch("broker.threading.Thread") as thread:
            fresh = self.b.invoke("franka.delta.move", {**args, "request_id": "new_motion"})
        command.assert_called_once()
        thread.return_value.start.assert_called_once()
        self.assertNotEqual(fresh["session_id"], s["session_id"])
        self.assertEqual(self.b.invoke("franka.delta.move", args), archived)
        with self.assertRaisesRegex(ValueError, "REQUEST_ID_REUSED_WITH_DIFFERENT_INPUT"):
            self.b.invoke("franka.delta.move", {**args, "translation_m": [0.002, 0, 0]})

    def test_backup_failure_does_not_remove_blocking_sessions(self):
        s = self.fixture.failed_session()
        s["state"] = "unknown"
        self.b.save()
        before = self.b.store.path.read_bytes()
        open_path = Path.open

        def reject_backup(path, *args, **kwargs):
            if path.parent.name == "broker-history":
                raise OSError("fixture disk unavailable")
            return open_path(path, *args, **kwargs)

        with patch.object(Path, "open", reject_backup):
            with self.assertRaisesRegex(OSError, "fixture disk unavailable"):
                control.archive_blocking_sessions(self.b.store.root, "stop", release=True)
        self.assertEqual(self.b.store.path.read_bytes(), before)

    def test_force_stop_refuses_unrelated_pid_without_releasing_state(self):
        config, env = self.fixture.broker_control_fixture()
        s = self.fixture.failed_session()
        s["state"] = "unknown"
        self.b.save()
        before = self.b.store.path.read_bytes()
        pidfile = self.b.store.root / "broker.pid"
        pidfile.write_text(str(os.getpid()))
        result = self.fixture.run_broker_control(config, env, "--force-stop")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PID does not identify", result.stderr)
        self.assertEqual(self.b.store.path.read_bytes(), before)
        self.assertEqual(pidfile.read_text(), str(os.getpid()))
