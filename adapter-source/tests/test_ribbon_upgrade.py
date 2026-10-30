"""2026-10-19 contract regressions; all vendor programs and workspaces are fixtures."""

import base64
import hashlib
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import test_adapter as baseline
from assets import read_artifact, sha256_file
from broker import Broker, ReceiptError, prompt_actions
from core import command, validate, shell_launch
from layout import Workspace
from render_videos import copy_run, render
from task_files import import_task


class RibbonUpgradeTests(unittest.TestCase):
    setUp = baseline.AdapterTests.setUp
    tearDown = baseline.AdapterTests.tearDown
    call = baseline.AdapterTests.call
    vendor = baseline.AdapterTests.vendor
    wait = baseline.AdapterTests.wait

    def run_fixture(self, mode="prepare", status="succeeded", outcome=None, checkpoint=True):
        sid = "session_source"
        directory = self.b.store.root / sid
        run = directory / "run"
        run.mkdir(parents=True, exist_ok=True)
        receipt = {"status": status, "mode": mode,
                   "outcome": outcome or {"prepare": "offline_checks_passed", "plan": "planned", "execute": "executed_without_capture"}[mode]}
        path = run / "result.json"
        path.write_text(json.dumps(receipt))
        (directory / "terminal.log").write_text(json.dumps({"result": str(path)}))
        if checkpoint:
            (run / "checkpoint.json").write_text(json.dumps({"level": "plan" if mode == "plan" else "prepare"}))
        session = {"session_id": sid, "directory": str(directory),
                   "operation_id": "franka.pipeline.start", "parameters": {"mode": mode},
                   "state": status, "control_lock_pending": False,
                   "result": {"run_result_artifact_id": self.b.store.register(path, sid)}}
        self.b.store.data["sessions"][sid] = session
        self.b.store.collect(session)
        return session, run, receipt

    def update_receipt(self, session, run, receipt):
        (run / "result.json").write_text(json.dumps(receipt))
        return self.b.receipt(session, 0)

    def capture_fixture(self, run, name, calibrated=False):
        prefix = "force" if name == "force_capture" else "capture"
        file = "ati_force_run.csv" if prefix == "force" else "ribbon_markers.csv"
        (run / file).write_text("fixture samples\n")
        capture = {"completed": True, "sample_count": 12, "files": [file],
                   "first_frame_unix": 10.0, "last_frame_unix": 12.0}
        (run / (prefix + "_result.json")).write_text(json.dumps(capture))
        if prefix == "force":
            units = ["N"] * 3 + ["N·m"] * 3 if calibrated else ["counts"] * 6
            (run / "force_status.json").write_text(json.dumps({"calibrated": calibrated, "units": units}))
        return capture

    def test_all_commands_use_split_workspace_layout(self):
        layout = Workspace(self.c)
        cases = [("franka.state.read", {}, layout.examples / "read_franka_state"),
                 ("franka.nokov.list", {}, layout.nokov),
                 ("franka.delta.preview", {"translation_m": [0, 0, 0]}, layout.examples / "cartesian_delta_move")]
        for operation, args, executable in cases:
            argv, _ = command(self.c, self.b.store, operation, args, self.root)
            self.assertEqual(argv[0], str(executable))
        script = shell_launch(self.c, ["true"])[2]
        self.assertIn('/ros/install/', script)
        self.assertIn('/ros/src/franka_motion_planner', script)
        self.assertIn('cd "$2/pipeline"', script)
        task = self.call("task.create", task={"waypoints": [{"motion": "free", "position": [0, 0, 0]}]})
        native = json.loads(self.b.store.task(task["task_id"]).read_text())
        self.assertEqual(native["start_state_file"], str(layout.start_pose))

    def test_return_joint_request_survives_task_creation(self):
        task = self.call("task.create", task={"waypoints": [{"motion": "free", "position": [0, 0, 0]}], "return_to_start_joints": True})
        self.assertTrue(json.loads(self.b.store.task(task["task_id"]).read_text())["return_to_start_joints"])
        with self.assertRaises(Exception):
            self.call("task.create", task={"waypoints": [{"position": [0, 0, 0], "motion": "joint"}]})

    def test_pipeline_offline_flags_and_execute_rejection(self):
        task = self.call("task.create", task={"waypoints": [{"motion": "free", "position": [0, 0, 0]}]})
        args = {"request_id": "prepare", "task_id": task["task_id"], "mode": "prepare", "skip_leveling": True,
                "videos": {"simulation": False, "ribbon": False}, "force_plot": False}
        validate("franka.pipeline.start", args)
        argv, _ = command(self.c, self.b.store, "franka.pipeline.start", args, self.root)
        for flag in ("--skip-leveling", "--no-video", "--no-ribbon-video", "--no-force-plot"):
            self.assertIn(flag, argv)
        with self.assertRaises(Exception):
            validate("franka.pipeline.start", dict(args, mode="execute"))

    def test_pipeline_requires_task_and_rejects_checkpoint_reuse_before_launch(self):
        task = self.call("task.create", task={"waypoints": [{"motion": "free", "position": [0, 0, 0]}]})
        with patch.object(self.b, "run_real") as worker:
            for mode in ("plan", "prepare", "execute"):
                for extra in ({"source_session_id": "session_old"},
                              {"task_id": task["task_id"], "source_session_id": "session_old"},
                              {"task_id": task["task_id"], "on_start_drift": "abort"}, {}):
                    with self.subTest(mode=mode, extra=extra), self.assertRaises(Exception):
                        self.call("pipeline.start", mode=mode, **extra)
            worker.assert_not_called()
        self.assertEqual(self.b.store.data["sessions"], {})

    def test_every_new_pipeline_session_generates_its_own_outputs(self):
        self.vendor()
        script = Workspace(self.c).tools / "run_pipeline.py"
        script.write_text("import argparse,json\nfrom pathlib import Path\np=argparse.ArgumentParser();p.add_argument('--output-root');p.add_argument('--task');p.add_argument('--mode');a,rest=p.parse_known_args()\nassert '--from-run' not in rest\nd=Path(a.output_root);(d/'simulation').mkdir();(d/'trajectory.csv').write_text(str(d));(d/'simulation/gazebo_review.mp4').write_bytes(str(d).encode())\nf=d/'result.json';f.write_text(json.dumps({'status':'succeeded','mode':a.mode,'outcome':'offline_checks_passed'}));print(json.dumps({'result':str(f)}),flush=True)\n")
        task = self.call("task.create", task={"waypoints": [{"motion": "free", "position": [0, 0, 0]}]})
        first = self.wait(self.call("pipeline.start", request_id="fresh_one", task_id=task["task_id"],
                                   mode="prepare", skip_leveling=True), "succeeded")
        first_dir = Path(self.b.store.data["sessions"][first["session_id"]]["directory"])
        snapshot = {str(p.relative_to(first_dir)): p.read_bytes() for p in first_dir.rglob("*") if p.is_file()}
        retry = self.call("pipeline.start", request_id="fresh_one", task_id=task["task_id"],
                          mode="prepare", skip_leveling=True)
        self.assertEqual(retry["session_id"], first["session_id"])
        second = self.wait(self.call("pipeline.start", request_id="fresh_two", task_id=task["task_id"],
                                    mode="prepare", skip_leveling=True), "succeeded")
        second_dir = Path(self.b.store.data["sessions"][second["session_id"]]["directory"])
        self.assertNotEqual(first_dir, second_dir)
        self.assertNotEqual((first_dir / "trajectory.csv").read_bytes(),
                            (second_dir / "trajectory.csv").read_bytes())
        self.assertNotEqual((first_dir / "simulation/gazebo_review.mp4").read_bytes(),
                            (second_dir / "simulation/gazebo_review.mp4").read_bytes())
        self.assertEqual(snapshot, {str(p.relative_to(first_dir)): p.read_bytes()
                                   for p in first_dir.rglob("*") if p.is_file()})
        self.assertEqual(len(self.b.store.data["sessions"]), 2)

    def test_home_accepts_only_provenanced_planned_start_pose(self):
        session, run, _ = self.run_fixture()
        path = run / "planned_start_pose.yaml"
        path.write_text("joint_positions: [0,0,0,0,0,0,0]\n")
        aid = self.b.store.register(path, session["session_id"])
        argv, _ = command(self.c, self.b.store, "franka.home", {"start_pose_artifact_id": aid}, self.root)
        self.assertIn(str(path), argv)
        self.b.store.data["artifacts"][aid]["session_id"] = None
        with self.assertRaisesRegex(ValueError, "EXPECTED_PIPELINE_START_POSE"):
            command(self.c, self.b.store, "franka.home", {"start_pose_artifact_id": aid}, self.root)

    def test_ati_only_and_both_disabled_receipts(self):
        session, run, receipt = self.run_fixture(mode="execute", outcome="executed_and_captured")
        self.capture_fixture(run, "force_capture")
        receipt.update(capture={"status": "disabled"}, force_capture={"completed": True})
        result = self.update_receipt(session, run, receipt)
        self.assertFalse(result["capture_completed"])
        self.assertTrue(result["force_capture_completed"])
        self.assertFalse(result["force_measurement"]["usable_force_values"])
        receipt.update(outcome="executed_without_capture", force_capture={"status": "disabled"})
        result = self.update_receipt(session, run, receipt)
        self.assertFalse(result["capture_completed"])
        self.assertFalse(result["force_capture_completed"])

    def test_two_capture_channels_and_real_force_units(self):
        session, run, receipt = self.run_fixture(mode="execute", outcome="executed_and_captured")
        self.capture_fixture(run, "capture")
        self.capture_fixture(run, "force_capture", calibrated=True)
        receipt.update(capture={"completed": True}, force_capture={"completed": True},
                       execution_started_at=10.2, execution_finished_at=11.8)
        result = self.update_receipt(session, run, receipt)
        self.assertTrue(result["capture_completed"])
        self.assertTrue(result["force_capture_completed"])
        self.assertTrue(result["force_measurement"]["usable_force_values"])
        capture = json.loads((run / "force_result.json").read_text())
        capture["last_frame_unix"] = 11.0
        (run / "force_result.json").write_text(json.dumps(capture))
        with self.assertRaisesRegex(ReceiptError, "COVERAGE_INCOMPLETE"):
            self.update_receipt(session, run, receipt)

    def test_native_failure_details_and_fallback_origin_survive(self):
        session, run, receipt = self.run_fixture(status="failed")
        receipt.update(error={"code": "START_STATE_DRIFT", "details": {"relevel_command": "fixed command"}},
                       initial_state_source="default_start_pose_fallback", failure_stage="start_check")
        with self.assertRaises(ReceiptError) as raised:
            self.update_receipt(session, run, receipt)
        evidence = raised.exception.data
        self.assertEqual(evidence["native_error"]["code"], "START_STATE_DRIFT")
        self.assertEqual(evidence["receipt"]["initial_state_source"], "default_start_pose_fallback")
        self.b.finish(session, 1, evidence, str(raised.exception))
        self.assertEqual(session["result"]["native_error"]["details"]["relevel_command"], "fixed command")
        self.assertTrue(self.b.store.artifact(session["result_artifact_id"]).is_file())

    def test_home_relevel_prompt_has_current_nonce_and_actions(self):
        for text in ("HOME / RELEVEL / QUIT", "HOME 用 home_pose 归位\nRELEVEL 放弃复用\nQUIT 退出"):
            self.assertEqual(prompt_actions("franka.pipeline.start", text), ["HOME", "RELEVEL", "QUIT"])
        self.assertIsNone(prompt_actions("franka.delta.move", "HOME / RELEVEL / QUIT"))
        self.vendor()
        script = Workspace(self.c).tools / "run_pipeline.py"
        script.write_text("import argparse,json\nfrom pathlib import Path\np=argparse.ArgumentParser();p.add_argument('--output-root');a,_=p.parse_known_args()\nprint('HOME / RELEVEL / QUIT',flush=True)\nassert input()=='HOME'\nprint('最终执行：输入 MOVE',flush=True)\nassert input()=='MOVE'\nf=Path(a.output_root)/'result.json';f.write_text(json.dumps({'status':'succeeded','mode':'execute','outcome':'executed_without_capture'}))\nprint(json.dumps({'result':str(f)}),flush=True)\n")
        task = self.call("task.create", task={"waypoints": [{"motion": "free", "position": [0, 0, 0]}]})
        session = self.wait(self.call("pipeline.start", task_id=task["task_id"], mode="execute"), "waiting_confirmation")
        nonce = session["confirmation"]["confirmation_id"]
        self.call("session.respond", session_id=session["session_id"], confirmation_id=nonce, action="HOME")
        session = self.wait(session, "waiting_confirmation")
        self.assertNotEqual(session["confirmation"]["confirmation_id"], nonce)
        with self.assertRaisesRegex(ValueError, "STALE_OR_INVALID"):
            self.call("session.respond", session_id=session["session_id"], confirmation_id=nonce, action="MOVE")
        self.call("session.respond", session_id=session["session_id"], confirmation_id=session["confirmation"]["confirmation_id"], action="MOVE")
        self.assertEqual(self.wait(session, "succeeded")["result"]["receipt"]["mode"], "execute")

    def test_standalone_move_starts_without_a_synthetic_prompt(self):
        import threading
        started = threading.Event()
        with patch.object(self.b, "run_real", side_effect=lambda *_: started.set()) as worker:
            session = self.call("delta.move", translation_m=[0.001, 0, 0])
            self.assertTrue(started.wait(1))
            worker.assert_called_once()
        self.assertEqual(session["state"], "running")
        self.assertIsNone(session["confirmation"])
        stored = self.b.store.data["sessions"][session["session_id"]]
        self.assertNotIn("prelaunch_confirmation", stored)
        with self.assertRaisesRegex(ValueError, "STALE_OR_INVALID"):
            self.call("session.respond", session_id=session["session_id"],
                      confirmation_id="confirm_invented", action="MOVE")

    def test_home_still_freezes_and_checks_input_before_direct_launch(self):
        import threading
        pose = Workspace(self.c).start_pose
        pose.parent.mkdir(parents=True)
        pose.write_text("joint_positions: [0,0,0,0,0,0,0]\n")
        original = pose.read_bytes()
        started = threading.Event()
        with patch.object(self.b, "run_real", side_effect=lambda *_: started.set()):
            session = self.call("home")
            self.assertTrue(started.wait(1))
        self.assertIsNone(session["confirmation"])
        stored = self.b.store.data["sessions"][session["session_id"]]
        target = Path(stored["argv"][stored["argv"].index("--start-pose") + 1])
        self.assertNotEqual(target, pose)
        self.assertEqual(target.read_bytes(), original)
        pose.write_text("new shared pose\n")
        self.assertEqual(target.read_bytes(), original)
        target.write_text("tampered frozen pose\n")
        with patch("broker.subprocess.Popen") as child:
            self.b.run_real(stored, 10)
        child.assert_not_called()
        self.assertEqual(stored["state"], "failed")
        self.assertIn("ARTIFACT_CHANGED", stored["error"])
        self.assertFalse(stored["result"]["started"])

    def test_standalone_csv_starts_without_a_synthetic_prompt(self):
        import threading
        directory = self.b.store.root / "csv_fixture"
        directory.mkdir()
        trajectory = directory / "trajectory.csv"
        trajectory.write_text("fixture trajectory\n")
        guard = Path(str(trajectory) + ".ribbon_guard")
        guard.write_text("fixture guard\n")
        artifact = self.b.store.register(trajectory)
        self.b.store.register(guard)
        started = threading.Event()
        with patch.object(self.b, "run_real", side_effect=lambda *_: started.set()) as worker:
            session = self.call("offline.execute", trajectory_artifact_id=artifact)
            self.assertTrue(started.wait(1))
            worker.assert_called_once()
        self.assertEqual(session["state"], "running")
        self.assertIsNone(session["confirmation"])
        frozen = self.b.store.data["sessions"][session["session_id"]]["frozen_artifacts"]
        self.assertEqual({self.b.store.data["artifacts"][aid]["path"] for aid in frozen},
                         {str(trajectory), str(guard)})

    def test_native_delta_program_runs_without_extra_input(self):
        executable = Workspace(self.c).examples / "cartesian_delta_move"
        executable.parent.mkdir(parents=True)
        executable.write_text("#!" + sys.executable + "\nprint('MOTION_DONE_NS 123',flush=True)\n")
        executable.chmod(0o755)
        self.vendor()
        session = self.wait(self.call("delta.move", translation_m=[0,0,0]), "succeeded")
        self.assertIsNone(session["confirmation"])
        self.assertNotIn("托管运动确认", session["log_tail"])
        self.assertTrue(session["result"]["hardware_motion_verified"])

    def test_artifact_mime_binary_chunks_and_unicode_round_trip(self):
        for name, original in [("gazebo_review.mp4", bytes(range(256)) * 400),
                               ("force.png", b"\x89PNG\x00\xff" * 10000),
                               ("ribbon_viewer.html", ("中文播放器🙂" * 10000).encode())]:
            path = self.b.store.root / name
            path.write_bytes(original)
            aid = self.b.store.register(path)
            offset, chunks = 0, []
            while True:
                result = self.call("artifact.read", artifact_id=aid, offset=offset, max_bytes=997)
                chunks.append(base64.b64decode(result["content"]) if result["encoding"] == "base64" else result["content"].encode())
                self.assertLess(len(json.dumps(result).encode()), 1024 * 1024)
                if result["next_offset"] is None:
                    break
                offset = result["next_offset"]
            self.assertEqual(b"".join(chunks), original)
            self.assertIn("mime_type", result)

    def test_artifact_collection_pagination_and_hash_cache(self):
        session, run, _ = self.run_fixture()
        for i in range(125):
            (run / (str(i) + ".txt")).write_text("report")
        for name in ("video.mp4", "force.png", "viewer.html"):
            (run / name).write_bytes(b"fixture")
        self.b.store.collect(session)
        snapshot = self.b.snapshot(session)
        self.assertEqual(len(snapshot["artifacts"]), 50)
        all_ids = []
        offset = 0
        while True:
            page = self.call("session.artifacts", session_id=session["session_id"], offset=offset, limit=30)
            all_ids.extend(v["artifact_id"] for v in page["artifacts"])
            if page["next_offset"] is None:
                break
            offset = page["next_offset"]
        self.assertEqual(len(all_ids), len(set(all_ids)))
        self.assertEqual(len(all_ids), len(session["artifacts"]))
        with patch("core.sha256_file", side_effect=AssertionError("unchanged files must not be rehashed")):
            self.b.store.collect(session)
        video = next(v for v in session["artifacts"] if v["name"] == "video.mp4")
        (run / "video.mp4").write_bytes(b"modified")
        with self.assertRaisesRegex(ValueError, "ARTIFACT_CHANGED"):
            self.b.store.artifact(video["artifact_id"])

    def test_large_receipt_is_available_without_oversized_status(self):
        session, run, _ = self.run_fixture()
        detail = {"receipt": {"status": "succeeded", "trace": "测试" * 200000}}
        self.b.finish(session, 0, detail)
        snapshot = self.b.snapshot(session)
        self.assertLess(len(json.dumps(snapshot).encode()), 1024 * 1024)
        self.assertTrue(snapshot["result"]["details_truncated"])
        saved = json.loads(self.b.store.artifact(session["result_artifact_id"]).read_text())
        self.assertEqual(saved, detail)

    def test_manual_is_fixed_paged_and_hashed(self):
        manual = Workspace(self.c).manual
        vendor = Workspace(self.c).pipeline / "docs/RIBBON.md"
        vendor.parent.mkdir(parents=True)
        vendor.write_text("UNPACKAGED_VENDOR_MANUAL_SENTINEL\n")
        page = self.call("manual.read", start_line=2, max_lines=1)
        self.assertEqual(manual.read_bytes(), (baseline.ROOT / "docs/AGENT_OPERATIONS.md").read_bytes())
        self.assertEqual(page["document"], "AGENT_OPERATIONS.md")
        self.assertTrue(page["version"].startswith("版本：2026-10-28"))
        self.assertEqual(page["content"], manual.read_text().splitlines(keepends=True)[1])
        self.assertNotEqual(page["sha256"], sha256_file(vendor))
        self.assertNotIn("UNPACKAGED_VENDOR_MANUAL_SENTINEL", manual.read_text())
        self.assertIn("franka.task.create", manual.read_text())
        self.assertIn("franka.task.import", manual.read_text())
        self.assertIn("franka.task.list", manual.read_text())
        self.assertIn("flange_58mm_v3", manual.read_text())
        self.assertIn("ribbon_1021", manual.read_text())
        self.assertEqual(page["next_line"], 3)
        self.assertEqual(page["sha256"], sha256_file(manual))
        with self.assertRaises(Exception):
            self.call("manual.read", path="/etc/passwd")

    def test_manual_default_reads_complete_packaged_document(self):
        manual = Workspace(self.c).manual
        page = self.call("manual.read")
        self.assertLessEqual(len(manual.read_text().splitlines()), 200)
        self.assertEqual(page["content"], manual.read_text())
        self.assertEqual(page["lines_returned"], page["total_lines"])
        self.assertIsNone(page["next_line"])
        self.assertEqual(page["sha256"], sha256_file(manual))

    def test_source_layout_resolves_agent_manual_from_adapter_root(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "source_layout_fixture", baseline.ROOT / "src/layout.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.adapter_manual(), baseline.ROOT / "docs/AGENT_OPERATIONS.md")

    def test_package_fingerprint_tracks_agent_manual_and_reference(self):
        import shutil
        import core

        snapshot = self.root / "package-copy"
        shutil.copytree(core.PACKAGE, snapshot)
        manual = snapshot / "docs/AGENT_OPERATIONS.md"
        with patch("core.PACKAGE", snapshot), patch("core.adapter_manual", return_value=manual):
            original = core.package_fingerprint(self.c)
            manual.write_bytes(manual.read_bytes() + b"\nUpdated Agent instructions\n")
            updated = core.package_fingerprint(self.c)
            self.assertNotEqual(original, updated)
            reference = snapshot / "docs/RIBBON.md"
            reference.write_bytes(reference.read_bytes() + b"\nUpdated reference\n")
            self.assertNotEqual(updated, core.package_fingerprint(self.c))

    def test_remote_task_listing_import_hash_and_original_bytes(self):
        layout = Workspace(self.c)
        layout.tasks.mkdir(parents=True)
        layout.start_pose.parent.mkdir(parents=True)
        layout.start_pose.write_text("joint_positions: [0,0,0,0,0,0,0]\nribbon_mount: flange_58mm_v3\n")
        data = {"waypoints": [{"position": [0, 0, 0]}], "start_state_file": str(layout.start_pose), "return_to_start_joints": True}
        original = json.dumps(data, ensure_ascii=False).encode() + b"\n"
        path = layout.tasks / "experiment.yaml"
        path.write_bytes(original)
        listing = self.call("task.list")
        digest = listing["tasks"][0]["sha256"]
        with patch("task_files.parse_task_yaml", side_effect=lambda config, value: json.loads(value)):
            imported = self.call("task.import", task_path=str(path), expected_sha256=digest)
        self.assertEqual(self.b.store.task(imported["task_id"]).read_bytes(), original)
        self.assertEqual(path.read_bytes(), original)
        self.assertFalse(imported["hardware_validated"])
        layout.start_pose.write_text("changed pose")
        with self.assertRaisesRegex(ValueError, "START_POSE_CHANGED"):
            self.b.store.task(imported["task_id"])
        with patch("task_files.parse_task_yaml", side_effect=AssertionError("must reject hash before parse")):
            with self.assertRaisesRegex(ValueError, "TASK_SOURCE_HASH_MISMATCH"):
                self.call("task.import", task_path=str(path), expected_sha256="0" * 64)

    def test_remote_task_rejects_escape_oversize_and_other_start_file(self):
        layout = Workspace(self.c)
        layout.tasks.mkdir(parents=True)
        outside = self.root / "outside.yaml"
        outside.write_text("{}")
        (layout.tasks / "escape.yaml").symlink_to(outside)
        for name in (str(outside), "../outside.yaml", "escape.yaml"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.call("task.import", task_path=name)
        big = layout.tasks / "big.yaml"
        big.write_bytes(b" " * (2 * 1024 * 1024 + 1))
        with self.assertRaisesRegex(ValueError, "TWO_MIB"):
            self.call("task.import", task_path="big.yaml")
        other = layout.tasks / "other.yaml"
        other.write_text("start_state_file: /etc/passwd\n")
        with patch("task_files.parse_task_yaml", return_value={"start_state_file": "/etc/passwd"}):
            with self.assertRaisesRegex(ValueError, "NOT_SHARED_POSE"):
                self.call("task.import", task_path="other.yaml")

    def test_real_yaml_import_preserves_comments_and_rejects_unsafe_tags(self):
        import importlib.util
        if importlib.util.find_spec("yaml") is None:
            self.skipTest("Real YAML parser is exercised in the platform Python container")
        layout = Workspace(self.c)
        layout.tasks.mkdir(parents=True)
        source = layout.tasks / "original.yaml"
        original = b"# preserve original comment\nribbon_task: true\nreturn_to_start_joints: true\nwaypoints:\n  - position: [0.003, 0, 0]\n"
        source.write_bytes(original)
        imported = self.call("task.import", task_path="original.yaml")
        self.assertEqual(self.b.store.task(imported["task_id"]).read_bytes(), original)
        self.assertEqual(source.read_bytes(), original)
        source.write_text("!!python/object/apply:os.system ['touch " + str(self.root / "must-not-exist") + "']\n")
        with self.assertRaisesRegex(ValueError, "TASK_YAML_INVALID"):
            self.call("task.import", task_path="original.yaml")
        self.assertFalse((self.root / "must-not-exist").exists())

    def test_monitor_deadline_is_bounded_and_graceful(self):
        self.vendor()
        executable = Workspace(self.c).nokov
        executable.parent.mkdir(parents=True)
        executable.write_text("#!" + sys.executable + "\nimport signal,time,sys\nsignal.signal(signal.SIGINT,lambda *_:sys.exit(0))\nwhile True:time.sleep(.01)\n")
        executable.chmod(0o755)
        _, deadline = command(self.c, self.b.store, "franka.nokov.monitor", {}, self.root)
        self.assertEqual(deadline, 30)
        session = self.call("nokov.monitor", duration_seconds=0.2)
        result = self.wait(session, "succeeded")
        self.assertTrue(result["result"]["duration_completed"])
        self.assertFalse(result["result"]["hardware_motion_verified"])

    def test_video_render_uses_private_copy_and_never_changes_source(self):
        session, source, receipt = self.run_fixture()
        (source / "trajectory.csv").write_text("fixture trajectory")
        (source / "ribbon_markers.csv").write_text("fixture markers")
        (source / "simulation").mkdir()
        (source / "simulation/gazebo_review.mp4").write_bytes(b"old simulation video")
        (source / "videos").mkdir()
        (source / "videos/ribbon_fit.mp4").write_bytes(b"old ribbon video")
        (source / "videos/render_manifest.json").write_text('{"videos":{"ribbon":{"status":"ready"}}}')
        receipt.update(simulation_video={"path": str(source / "simulation/gazebo_review.mp4")},
                       ribbon_video_preview={"path": str(source / "videos/ribbon_fit.mp4")},
                       capture={"files": [str(source / "ribbon_markers.csv")]})
        (source / "result.json").write_text(json.dumps(receipt))
        before = {str(p.relative_to(source)): p.read_bytes() for p in source.rglob("*") if p.is_file()}
        destination = self.b.store.root / "rendered"
        destination.mkdir()
        calls = []

        def fake_child(argv, **kwargs):
            calls.append(argv)
            if "sim_replay.py" in argv[1]:
                out = Path(argv[argv.index("--output-dir") + 1])
                (out / "gazebo_review.mp4").write_bytes(b"native camera fixture")
                (out / "summary.json").write_text(json.dumps({"video": {"status": "ok", "path": str(out / "gazebo_review.mp4")}}))
            else:
                private = Path(argv[argv.index("--run-dir") + 1])
                private_receipt = json.loads((private / "result.json").read_text())
                self.assertNotIn("ribbon_video_preview", private_receipt)
                self.assertNotIn("simulation_video", private_receipt)
                self.assertEqual(private_receipt["capture"]["files"], [str(private / "ribbon_markers.csv")])
                target = private / "videos"
                self.assertIn("--ribbon-videos", argv)
                self.assertFalse((target / "render_manifest.json").exists())
                self.assertFalse((target / "ribbon_fit.mp4").exists())
                target.mkdir(exist_ok=True)
                kind = argv[argv.index("--kind") + 1]
                (target / "render_manifest.json").write_text(json.dumps({"videos": {kind: {"status": "ready", "scientific_evidence": False}}}))
                (target / "ribbon_fit.mp4").write_bytes(b"video")
            return 0

        with patch("render_videos.run_child", side_effect=fake_child):
            result = render(Path(self.c["workspace"]), source, destination, "all")
        self.assertEqual(before, {str(p.relative_to(source)): p.read_bytes() for p in source.rglob("*") if p.is_file()})
        self.assertFalse(result["hardware_calls"])
        self.assertTrue(result["source_receipt_unchanged"])
        self.assertFalse(result["scientific_evidence"])
        self.assertTrue(all("run_pipeline.py" not in arg and "nokov_recorder" not in arg for call in calls for arg in call))
        self.assertEqual(calls[0][1], str(Workspace(self.c).tools / "sim_replay.py"))
        self.assertEqual(len(calls), 2)
        self.assertEqual((destination / "render_input/simulation/gazebo_review.mp4").read_bytes(), b"native camera fixture")
        self.assertEqual(result["generation_policy"], "fresh_outputs_per_session")
        self.assertEqual(result["videos"]["simulation"]["generation"], "fresh_simulation_replay")
        self.assertEqual(result["videos"]["ribbon"]["generation"], "fresh_marker_render")

    def test_failed_fresh_render_does_not_return_an_old_video(self):
        _session, source, _receipt = self.run_fixture()
        (source / "trajectory.csv").write_text("fixture trajectory")
        (source / "simulation").mkdir()
        (source / "simulation/gazebo_review.mp4").write_bytes(b"old video")
        destination = self.b.store.root / "fresh_failed"
        destination.mkdir()
        with patch("render_videos.run_child", return_value=1) as child:
            result = render(Path(self.c["workspace"]), source, destination, "simulation")
        child.assert_called_once()
        self.assertEqual(result["videos"]["simulation"]["status"], "unavailable")
        self.assertNotIn("path", result["videos"]["simulation"])
        self.assertFalse((destination / "render_input/simulation/gazebo_review.mp4").exists())

    def test_simulation_requires_nonempty_video_and_native_success_receipt(self):
        _session, source, _ = self.run_fixture()
        (source / "trajectory.csv").write_text("fixture trajectory")
        cases = [
            ("empty", b"", {"video": {"status": "ok"}}),
            ("failed_receipt", b"not empty", {"video": {"status": "missing"}}),
            ("missing_receipt", b"not empty", None),
            ("missing_video_entry", b"not empty", {}),
            ("invalid_video_entry", b"not empty", {"video": []}),
            ("invalid_summary", b"not empty", []),
            ("malformed_summary", b"not empty", "malformed"),
            ("wrong_path", b"not empty", {"video": {"status": "ok", "path": str(source / "old.mp4")}}),
        ]
        for label, content, summary in cases:
            with self.subTest(case=label):
                destination = self.b.store.root / label
                destination.mkdir()

                def child(argv, **kwargs):
                    output = Path(argv[argv.index("--output-dir") + 1])
                    (output / "gazebo_review.mp4").write_bytes(content)
                    if summary is not None:
                        (output / "summary.json").write_text("{" if summary == "malformed" else json.dumps(summary))
                    return 0

                with patch("render_videos.run_child", side_effect=child):
                    result = render(Path(self.c["workspace"]), source, destination, "simulation")
                self.assertEqual(result["videos"]["simulation"]["status"], "unavailable")
                self.assertNotIn("path", result["videos"]["simulation"])
                self.assertEqual(json.loads((destination / "render_result.json").read_text()), result)

    def test_invalid_ribbon_receipts_preserve_successful_simulation_and_final_receipt(self):
        _session, source, _ = self.run_fixture()
        (source / "trajectory.csv").write_text("fixture trajectory")
        cases = [{"videos": {}}, {}, [], {"videos": []},
                 {"videos": {"ribbon": None}}, {"videos": {"ribbon": []}},
                 {"videos": {"ribbon": {}}},
                 {"videos": {"ribbon": {"status": "unavailable", "error": "no marker data"}}},
                 {"videos": {"ribbon": {"status": "unexpected"}}}, "malformed"]
        for index, document in enumerate(cases):
            with self.subTest(document=document):
                destination = self.b.store.root / ("bad_manifest_" + str(index))
                destination.mkdir()

                def child(argv, **kwargs):
                    if "sim_replay.py" in argv[1]:
                        output = Path(argv[argv.index("--output-dir") + 1])
                        (output / "gazebo_review.mp4").write_bytes(b"native video fixture")
                        (output / "summary.json").write_text('{"video":{"status":"ok"}}')
                    else:
                        output = Path(argv[argv.index("--run-dir") + 1]) / "videos"
                        output.mkdir()
                        (output / "render_manifest.json").write_text("{" if document == "malformed" else json.dumps(document))
                        (output / "ribbon_fit.mp4").write_bytes(b"leftover incomplete file")
                    return 0

                with patch("render_videos.run_child", side_effect=child):
                    result = render(Path(self.c["workspace"]), source, destination, "all")
                self.assertEqual(result["videos"]["simulation"]["status"], "ready")
                self.assertEqual(result["videos"]["ribbon"]["status"], "unavailable")
                self.assertNotIn("path", result["videos"]["ribbon"])
                self.assertEqual(json.loads((destination / "render_result.json").read_text()), result)

    def test_simulation_failure_preserves_successful_partial_ribbon(self):
        _session, source, _ = self.run_fixture()
        (source / "trajectory.csv").write_text("fixture trajectory")
        destination = self.b.store.root / "partial_ribbon"
        destination.mkdir()

        def child(argv, **kwargs):
            if "sim_replay.py" in argv[1]:
                return 1
            output = Path(argv[argv.index("--run-dir") + 1]) / "videos"
            output.mkdir()
            movie = output / "ribbon_fit.mp4"
            movie.write_bytes(b"partial marker video")
            (output / "render_manifest.json").write_text(json.dumps({"videos": {"ribbon": {
                "status": "partial", "path": str(movie), "missing_frames": 2,
                "scientific_evidence": True}}}))
            return 0

        with patch("render_videos.run_child", side_effect=child):
            result = render(Path(self.c["workspace"]), source, destination, "all")
        self.assertEqual(result["videos"]["simulation"]["status"], "unavailable")
        ribbon = result["videos"]["ribbon"]
        self.assertEqual(ribbon["status"], "partial")
        self.assertEqual(ribbon["missing_frames"], 2)
        self.assertEqual(ribbon["sha256"], sha256_file(Path(ribbon["path"])))
        self.assertGreater(ribbon["size_bytes"], 0)
        self.assertFalse(ribbon["scientific_evidence"])
        self.assertEqual(json.loads((destination / "render_result.json").read_text()), result)

    def test_ready_ribbon_requires_current_nonempty_regular_output(self):
        _session, source, _ = self.run_fixture()
        for case in ("missing", "empty", "symlink", "wrong_path"):
            with self.subTest(case=case):
                destination = self.b.store.root / ("ribbon_" + case)
                destination.mkdir()

                def child(argv, **kwargs):
                    output = Path(argv[argv.index("--run-dir") + 1]) / "videos"
                    output.mkdir()
                    movie = output / "ribbon_fit.mp4"
                    if case == "symlink":
                        movie.symlink_to(source / "result.json")
                    elif case != "missing":
                        movie.write_bytes(b"" if case == "empty" else b"native fixture")
                    native = {"status": "ready", "path": str(source / "old.mp4") if case == "wrong_path" else str(movie)}
                    (output / "render_manifest.json").write_text(json.dumps({"videos": {"ribbon": native}}))
                    return 0

                with patch("render_videos.run_child", side_effect=child):
                    result = render(Path(self.c["workspace"]), source, destination, "ribbon")
                self.assertEqual(result["videos"]["ribbon"]["status"], "unavailable")
                self.assertNotIn("path", result["videos"]["ribbon"])
                self.assertTrue((destination / "render_result.json").is_file())

    def test_render_rejects_unresolved_source_and_symlinks(self):
        session, source, _ = self.run_fixture()
        session["control_lock_pending"] = True
        with self.assertRaisesRegex(ValueError, "VIDEO_SOURCE_NOT_RESOLVED"):
            self.call("pipeline.render_videos", source_session_id=session["session_id"])
        link = source / "linked.csv"
        link.symlink_to(self.root / "missing")
        with self.assertRaisesRegex(ValueError, "SYMLINK"):
            copy_run(source, self.root / "render-target")


if __name__ == "__main__":
    unittest.main(verbosity=2)
