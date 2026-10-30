"""Public snapshot boundary; packaged Broker, temporary state, no hardware access."""

from copy import deepcopy
import json
import unittest

from jsonschema import Draft202012Validator
import test_adapter as original
from core import canonical


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.fixture = original.AdapterTests()
        self.fixture.setUp()
        self.b = self.fixture.b
        self.schema = original.OPERATIONS["franka.session.status"]["output_schema"]["properties"]["data"]

    def tearDown(self):
        self.fixture.tearDown()

    def session(self):
        session = self.fixture.failed_session()
        session.update(physical_stop_verified=True, control_lock_pending=False,
                       backend="real", simulated=False, _result_is_large=False)
        return session

    def test_undeclared_internal_fields_stay_in_store_but_never_enter_snapshot(self):
        session = self.session()
        internal = {"internal_debug": {"opaque": "fixture"}, "future_internal_field": "fixture"}
        session.update(internal)
        self.b.save()
        before = self.b.store.path.read_bytes()
        result = self.b.snapshot(session)
        for name, value in internal.items():
            self.assertNotIn(name, result)
            self.assertEqual(session[name], value)
        self.assertEqual(self.b.store.path.read_bytes(), before)
        self.assertTrue(set(result) <= set(self.schema["properties"]))
        Draft202012Validator(self.schema).validate(result)

    def test_nested_evidence_confirmation_and_artifact_protocol_are_preserved(self):
        session = self.session()
        confirmation = {"confirmation_id": "confirm_fixture", "actions": ["MOVE"],
                        "prompt": "输入 MOVE", "hardware_confirmation_required": True,
                        "future_confirmation_metadata": {"fixture": True}}
        evidence = {"required": True, "verified": False, "samples": [{"q": [0.1] * 7, "dq": [0] * 7}],
                    "future_evidence_metadata": "kept"}
        detail = {"receipt": {"mode": "prepare", "error": {"code": "PLAN_FAILED", "details": {"log": "kept"}}},
                  "terminal_output": "完整日志", "future_nested_field": {"kept": True}}
        artifacts = [{"artifact_id": "art_" + str(i), "name": str(i), "extra_metadata": "kept"}
                     for i in range(60)]
        session.update(operation_id="franka.pipeline.start", state="waiting_confirmation",
                       confirmation=confirmation, stop_verification=evidence, result=detail,
                       artifacts=artifacts, artifact_index={"state": "generating", "pending_count": 60},
                       physical_stop_verified=False, control_lock_pending=True)
        expected = deepcopy(session)
        result = self.b.snapshot(session, "franka.pipeline.start")
        for name in ("confirmation", "stop_verification", "result", "artifact_index",
                     "physical_stop_verified", "control_lock_pending"):
            self.assertEqual(result[name], expected[name])
        self.assertEqual(result["artifacts"], artifacts[:50])
        self.assertEqual(result["artifact_count"], 60)
        self.assertEqual(result["artifacts_next_offset"], 50)
        self.assertEqual(result["artifact_delivery"], "1.0")
        self.assertEqual(result["completion_scope"], "adapter_session")
        self.assertEqual(session, expected)
        Draft202012Validator(self.schema).validate(result)

    def test_contract_rejects_new_top_level_field_but_allows_nested_extensions(self):
        session = self.session()
        session["result"] = {"arbitrary_native_receipt_extension": {"kept": True}}
        result = self.b.snapshot(session)
        validator = Draft202012Validator(self.schema)
        validator.validate(result)
        errors = list(validator.iter_errors({**result, "undeclared_internal_field": True}))
        self.assertTrue(any(error.validator == "additionalProperties" for error in errors))

    def test_new_snapshot_keeps_all_current_public_fields_of_a_saved_capture(self):
        # Representative compatibility fields used by confirmation, diagnostics,
        # frozen inputs and bounded monitor operations remain explicitly public.
        session = self.session()
        session.update(process_id=123, started_unix=1.0, prompt_epoch=2,
                       monitor_duration_completed=True, frozen_artifacts=["art_fixture"],
                       result_artifact_id="art_result", log_tail="diagnostic log",
                       started_at="2026-10-22T00:00:00Z", finished_at="2026-10-22T00:00:01Z",
                       exit_code=1)
        result = self.b.snapshot(session)
        for name in ("process_id", "started_unix", "prompt_epoch", "monitor_duration_completed",
                     "frozen_artifacts", "result_artifact_id", "log_tail", "started_at", "finished_at",
                     "exit_code", "session_id", "operation_id", "state", "backend", "simulated", "error"):
            self.assertEqual(result[name], session[name])
        Draft202012Validator(self.schema).validate(json.loads(canonical(result)))
