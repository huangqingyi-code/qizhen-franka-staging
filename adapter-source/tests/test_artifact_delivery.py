"""Artifact indexing and response budgets; no hardware is mounted."""

import io
import threading
import unittest
from unittest.mock import patch

from artifact_index import ArtifactIndexer
from core import canonical, envelope
from handler import export_artifact
from response_budget import MAX_RESPONSE_BYTES, artifact_page, bounded_response
import test_ribbon_upgrade as upgrade


class ArtifactDeliveryTests(unittest.TestCase):
    setUp = upgrade.RibbonUpgradeTests.setUp
    tearDown = upgrade.RibbonUpgradeTests.tearDown
    run_fixture = upgrade.RibbonUpgradeTests.run_fixture

    def test_status_does_not_scan_or_hash_while_indexer_hashes(self):
        session, run, _ = self.run_fixture()
        (run / "video.mp4").write_bytes(b"video" * 10000)
        indexer = ArtifactIndexer(self.b)
        indexer.scan()
        started, release = threading.Event(), threading.Event()
        from assets import sha256_file

        def slow_hash(path):
            self.assertFalse(self.b.lock._is_owned())
            started.set()
            if not release.wait(3):
                raise RuntimeError("test did not release hasher")
            return sha256_file(path)

        with patch("artifact_index.sha256_file", side_effect=slow_hash), patch.object(
                self.b.store, "collect", side_effect=AssertionError("status must not scan")):
            thread = threading.Thread(target=indexer.scan)
            thread.start()
            self.assertTrue(started.wait(2))
            try:
                result = self.b.invoke("franka.session.status", {"session_id": session["session_id"]})
                self.assertEqual(result["session_id"], session["session_id"])
            finally:
                release.set()
                thread.join(3)
        self.assertEqual(session["artifact_index"]["state"], "ready")
        with patch("artifact_index.sha256_file", side_effect=AssertionError("cached file rehashed")):
            indexer.scan()

    def test_live_video_is_generating_and_changed_hash_is_not_published(self):
        session, run, _ = self.run_fixture()
        session["state"] = "running"
        video = run / "video.mp4"
        video.write_bytes(b"first")
        indexer = ArtifactIndexer(self.b)
        with patch("artifact_index.sha256_file", side_effect=AssertionError("live file hashed")):
            indexer.scan()
            indexer.scan()
        self.assertEqual(session["artifact_index"]["state"], "generating")
        session["state"] = "succeeded"

        def mutate(path):
            path.write_bytes(b"changed during hash")
            return "0" * 64

        with patch("artifact_index.sha256_file", side_effect=mutate):
            indexer.scan()
        self.assertGreater(session["artifact_index"]["pending_count"], 0)
        video_record = next(a for a in session["artifacts"] if a["name"] == "video.mp4")
        self.assertEqual(video_record["state"], "generating")
        self.assertNotIn("artifact_id", video_record)

    def test_serialized_budget_includes_escaping_and_full_envelope(self):
        records = [{"name": "🙂" * 5000} for _ in range(100)]
        page, next_offset = artifact_page(records, 0, 100)
        self.assertLess(len(page), 100)
        self.assertEqual(next_offset, len(page))
        response = bounded_response(envelope("real", {"artifacts": page}))
        self.assertLessEqual(len(canonical(response).encode()), MAX_RESPONSE_BYTES)
        overflow = bounded_response(envelope("real", {"content": "🙂" * MAX_RESPONSE_BYTES}))
        self.assertFalse(overflow["ok"])
        self.assertEqual(overflow["error"]["code"], "RESPONSE_TOO_LARGE")

    def test_index_waits_for_late_renderer_without_affecting_session_state(self):
        session, run, _ = self.run_fixture()
        indexer = ArtifactIndexer(self.b)
        with patch("artifact_index.group_has_producers", return_value=True):
            indexer.scan()
            self.assertEqual(session["artifact_index"]["state"], "generating")
            (run / "late_video.mp4").write_bytes(b"late renderer output")
            indexer.scan()
            self.assertEqual(session["state"], "succeeded")
        indexer.scan()
        self.assertEqual(session["artifact_index"]["state"], "ready")
        self.assertIn("late_video.mp4", [a["name"] for a in session["artifacts"]])

    def test_private_export_is_binary_and_rejects_mutated_artifact(self):
        session, run, _ = self.run_fixture()
        path = run / "video.mp4"
        expected = bytes(range(256)) * 100
        path.write_bytes(expected)
        aid = self.b.store.register(path, session["session_id"])
        self.b.save()
        output = io.BytesIO()
        with patch("sys.stdout", new=type("Output", (), {"buffer": output})()):
            export_artifact(self.c, aid, 997, 5000)
        self.assertEqual(output.getvalue(), expected[997:5997])
        path.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "ARTIFACT_CHANGED"):
            export_artifact(self.c, aid, 0, 100)

    def test_legacy_handles_are_revalidated_outside_the_control_lock(self):
        path = self.b.store.root / "legacy.yaml"
        path.write_text("legacy: true")
        aid = self.b.store.register(path)
        self.b.store.data["artifacts"][aid].pop("_signature")
        indexer = ArtifactIndexer(self.b)
        indexer.scan()
        from assets import sha256_file

        def verify(path):
            self.assertFalse(self.b.lock._is_owned())
            return sha256_file(path)

        with patch("artifact_index.sha256_file", side_effect=verify):
            indexer.scan()
        self.assertEqual(self.b.store.artifact(aid), path)

    def test_large_receipts_are_not_reserialized_or_saved_on_status_polls(self):
        session, _run, _ = self.run_fixture()
        detail = {"receipt": {"status": "succeeded", "trace": "x" * 200000}}
        self.b.finish(session, 0, detail)
        from core import canonical as encode

        def bounded_encode(value):
            if value is detail:
                raise AssertionError("status serialized the full receipt")
            return encode(value)

        with patch("broker.canonical", side_effect=bounded_encode), patch.object(
                self.b, "save", side_effect=AssertionError("read-only poll rewrote state")):
            for _ in range(3):
                status = self.b.invoke("franka.session.status", {"session_id": session["session_id"]})
                self.assertTrue(status["result"]["details_truncated"])
