"""Run only inside an ephemeral container: real Connector/handler/broker, fake vendor."""

import base64
import hashlib
import importlib.util
import json
import os
import signal
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
if os.environ.get("QIZHEN_SMOKE_CONNECTOR_PATH"):
    sys.path.insert(0, os.environ["QIZHEN_SMOKE_CONNECTOR_PATH"])
from qizhen_linux_edge.adapters import AdapterManager
from qizhen_linux_edge.client import ConnectorService
from qizhen_linux_edge.state import EdgePaths


def main():
    # The test image's home is ephemeral and must not contain a real configuration.
    config_path = Path.home() / ".config/qizhen-franka/config.json"
    if config_path.exists():
        raise RuntimeError("Refusing to run smoke test against an existing configuration")
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        workspace = root / "fake-ribbon"
        tools = workspace / "pipeline/tools"
        tools.mkdir(parents=True)
        setup = workspace / "ros/install/setup.bash"
        setup.parent.mkdir(parents=True)
        setup.write_text(":\n")
        ros_setup = root / "ros.bash"
        ros_setup.write_text(":\n")
        (tools / "run_pipeline.py").write_text('''import argparse,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--output-root');p.add_argument('--mode');p.add_argument('--skip-leveling',action='store_true');a,_=p.parse_known_args()
assert a.skip_leveling and a.mode=='prepare'
run=Path(a.output_root)/'fixture_run';run.mkdir()
(run/'gazebo_review.mp4').write_bytes(bytes(range(256))*50)
r={'status':'succeeded','mode':'prepare','outcome':'offline_checks_passed','initial_state_source':'default_start_pose_fallback','capture':{'status':'disabled'},'force_capture':{'status':'disabled'}}
f=run/'result.json';f.write_text(json.dumps(r))
print(json.dumps({'status':'succeeded','result':str(f),'error':None}),flush=True)
''')
        config = {"backend": "real", "workspace": str(workspace), "state_dir": str(root / "adapter-state"),
                  "ros_setup": str(ros_setup), "python_executable": sys.executable,
                  "robot_ip": "192.0.2.1", "nokov_server": "192.0.2.2"}
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(config))
        config_path.chmod(0o600)
        try:
            spec = importlib.util.spec_from_file_location("smoke_builder", ROOT / "scripts/build_adapter.py")
            builder = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(builder)
            version = json.loads((ROOT / "adapter.json").read_text())["version"]
            release = ROOT / f"packages/franka-ribbon-{version}-amd64.tar.gz"
            archive = ({"package": str(release), "sha256": Path(str(release) + ".sha256").read_text().strip()}
                       if release.is_file() else builder.build(ROOT, root / "packages", "amd64"))
            manager = AdapterManager(EdgePaths(root / "connector-state"))
            record = manager.install(Path(archive["package"]), archive["sha256"])
            adapter_id = record["manifest"]["adapter_revision_id"]
            record = manager.set_running(adapter_id, True)
            frozen_hash = manager.adapter_hash(record)
            exported = manager._capability_adapter(record)
            assert [op["operation_id"] for op in exported["operations"]
                    if op["side_effect"] == "high_impact"] == ["franka.session.respond"]

            def invoke(operation, args):
                return manager.invoke(adapter_id, version, record["artifact_hash"], frozen_hash, operation, args)

            manual = invoke("franka.manual.read", {"start_line": 1, "max_lines": 30})["data"]
            assert manual["document"] == "AGENT_OPERATIONS.md"
            assert manual["sha256"] == hashlib.sha256((ROOT / "docs/AGENT_OPERATIONS.md").read_bytes()).hexdigest()
            assert "Adapter " + version in manual["content"]
            assert not (workspace / "pipeline/docs/AGENT_OPERATIONS.md").exists()
            task = invoke("franka.task.create", {"request_id": "create", "task": {"waypoints": [{"motion": "free", "position": [0, 0, 0]}], "return_to_start_joints": True}})
            started = invoke("franka.pipeline.start", {"request_id": "prepare", "task_id": task["data"]["task_id"], "mode": "prepare", "skip_leveling": True})
            sid = started["data"]["session_id"]
            deadline = time.monotonic() + 15
            while True:
                status = invoke("franka.session.status", {"session_id": sid})
                if status["data"]["state"] == "succeeded" and status["data"].get("artifact_index", {}).get("state") == "ready":
                    break
                if status["data"]["state"] == "failed" or time.monotonic() > deadline:
                    raise AssertionError(status)
                time.sleep(0.05)
            assert status["data"]["result"]["receipt"]["initial_state_source"] == "default_start_pose_fallback"
            assets = invoke("franka.session.artifacts", {"session_id": sid})["data"]["artifacts"]
            video = next(v for v in assets if v["name"] == "gazebo_review.mp4")
            offset, chunks = 0, []
            while True:
                page = invoke("franka.artifact.read", {"artifact_id": video["artifact_id"], "offset": offset, "max_bytes": 1024})["data"]
                chunks.append(base64.b64decode(page["content"]))
                if page["next_offset"] is None:
                    break
                offset = page["next_offset"]
            assert hashlib.sha256(b"".join(chunks)).hexdigest() == video["sha256"]
            with tempfile.TemporaryFile() as exported:
                count = manager.export_part({"adapter_revision_id": adapter_id, "adapter_version": version,
                    "artifact_hash": record["artifact_hash"], "adapter_hash": frozen_hash},
                    video["artifact_id"], 0, 8 * 1024 * 1024, exported)
                exported.seek(0)
                assert count == video["size_bytes"]
                assert hashlib.sha256(exported.read()).hexdigest() == video["sha256"]
            native = workspace / "libfranka/build/examples/cartesian_delta_move"
            native.parent.mkdir(parents=True, exist_ok=True)
            native.write_text("#!" + sys.executable + "\nprint('MOTION_DONE_NS 123',flush=True)\n")
            native.chmod(0o755)
            delta = invoke("franka.delta.move", {"request_id": "direct-delta", "translation_m": [0, 0, 0]})["data"]
            deadline = time.monotonic() + 15
            while delta["state"] != "succeeded":
                assert delta["state"] == "running" and delta["confirmation"] is None, delta
                assert time.monotonic() < deadline, delta
                time.sleep(0.05)
                delta = invoke("franka.session.status", {"session_id": delta["session_id"]})["data"]
            assert delta["confirmation"] is None
            # This fake vendor only accepts offline prepare. A plan invocation
            # fails; the missing fixture state reader exercises unavailable
            # release through the real Connector/handler/Broker and schema.
            unavailable = invoke("franka.pipeline.start", {
                "request_id": "reader-unavailable", "task_id": task["data"]["task_id"],
                "mode": "plan"})["data"]
            deadline = time.monotonic() + 15
            while unavailable["state"] == "running":
                assert time.monotonic() < deadline, unavailable
                time.sleep(0.05)
                unavailable = invoke("franka.session.status", {
                    "session_id": unavailable["session_id"]})["data"]
            assert unavailable["state"] == "failed", unavailable
            assert unavailable["control_lock_pending"] is False, unavailable
            assert unavailable["physical_stop_verified"] is False, unavailable
            assert unavailable["stop_verification"]["state_unavailable"] is True, unavailable
            assert unavailable["stop_verification"]["verified"] is False, unavailable
            retry = invoke("franka.pipeline.start", {
                "request_id": "reader-unavailable", "task_id": task["data"]["task_id"],
                "mode": "plan"})["data"]
            assert retry["session_id"] == unavailable["session_id"]
            fresh = invoke("franka.pipeline.start", {
                "request_id": "prepare-after-unavailable", "task_id": task["data"]["task_id"],
                "mode": "prepare", "skip_leveling": True})["data"]
            deadline = time.monotonic() + 15
            while fresh["state"] == "running":
                assert time.monotonic() < deadline, fresh
                time.sleep(0.05)
                fresh = invoke("franka.session.status", {"session_id": fresh["session_id"]})["data"]
            assert fresh["state"] == "succeeded", fresh
            service = ConnectorService.__new__(ConnectorService)
            service.adapters = manager
            service.paths = manager.paths
            service._credential = Mock(return_value=("fixture-only-token", "fixture-connector", 1))
            service.client = Mock()
            service.client.request.return_value = (200, {"status": "accepted"})
            assert service.sync_capabilities() == {"status": "accepted"}
            snapshot = service.client.request.call_args.args[2]
            import rfc8785
            expected = "sha256:" + hashlib.sha256(rfc8785.dumps({
                k: v for k, v in snapshot.items() if k != "snapshot_hash"
            })).hexdigest()
            assert snapshot["snapshot_hash"] == expected
            assert snapshot["adapters"][0]["adapter_version"] == version
            service.journal = Mock()
            service.journal.receive.return_value = None
            service._current_job = Mock(return_value={"state_version": 1})
            service._report = Mock()
            command = {"command_id": "bad-command", "command_type": "execute", "resource_job_id": "job",
                       "expected_state_version": 1, "issued_at": "2026-10-19T00:00:00Z",
                       "document": {"schema_version": "1.0", "run_resource_binding_id": "binding",
                                    "adapter_revision_id": adapter_id, "adapter_version": version,
                                    "adapter_hash": frozen_hash, "artifact_hash": record["artifact_hash"],
                                    "operation": "franka.task.validate", "parameters": {"task_id": "missing"},
                                    "input_resource_refs": [], "idempotency_key": "bad"}}
            failed = service.process_command(command)
            assert failed["execution_status"] == "failed"
            assert failed["delivery_status"] == "delivered"
            assert failed["inline_result"]["ok"] is False
            print(json.dumps({"ok": True, "real_connector_handler_broker": True, "hardware": "fixture_only",
                              "prepare": "offline_checks_passed", "binary_sha256_verified": True,
                              "private_binary_export_verified": True, "packaged_manual_verified": True,
                              "adapter_failure_reported_as_failure": True, "only_terminal_response_high_impact": True,
                              "native_delta_without_extra_input": True,
                              "capability_snapshot_jcs_hash_verified": True,
                              "capability_sync_with_fixture_api": True,
                              "reader_unavailable_release_verified": True,
                              "same_request_not_replayed": True,
                              "prepare_after_unavailable_release": True}))
        finally:
            pidfile = root / "adapter-state/broker.pid"
            if pidfile.is_file():
                try:
                    os.kill(int(pidfile.read_text()), signal.SIGTERM)
                except ProcessLookupError:
                    pass
            config_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
