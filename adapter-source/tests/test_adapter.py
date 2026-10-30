"Contract validation and real-backend fake-vendor tests; no hardware access."

import importlib.util
import json
import sys
import tarfile
import tempfile
import time
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "build_adapter", ROOT / "scripts/build_adapter.py"
)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
PACKAGE_TMP = tempfile.TemporaryDirectory()
package_root = Path(PACKAGE_TMP.name)
archive = builder.build(ROOT, package_root, "amd64")

with tarfile.open(archive["package"]) as tar:
    tar.extractall(package_root, filter="data")
sys.path.insert(0, str(package_root / "franka-ribbon"))
from stop_guard import verify_stopped, session_blocks
from broker import Broker, prompt_actions  # noqa: E402 - import the built isolated package
from core import OPERATIONS, command, validate, shape_extract  # noqa: E402 - import the built isolated package


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.c = {
            "backend": "real",
            "state_dir": str(self.root / "state"),
            "workspace": str(self.root / "ws"),
            "ros_setup": str(self.root / "ros.bash"),
            "python_executable": sys.executable,
            "robot_ip": "172.16.0.3",
            "nokov_server": "10.1.1.198",
        }
        self.b = Broker(self.c)
        self.count = 0

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, op, **a):
        op = "franka." + op
        if OPERATIONS[op]["idempotency"] == "keyed" and "request_id" not in a:
            self.count += 1
            a["request_id"] = "req_" + str(self.count)
        return self.b.invoke(op, a)



    def test_invalid_parameters_and_no_shell_or_paths(self):
        cases = [
            ("state.read", {"command": "rm -rf /"}),
            ("delta.move", {"request_id": "x", "translation_m": [0.031, 0, 0]}),
            ("delta.preview", {"translation_m": [float("nan"), 0, 0]}),
            (
                "task.create",
                {"request_id": "x", "task": {"waypoints": [{"motion": "free", "position": [-0.001, 0, 0]}]}},
            ),
            (
                "task.create",
                {
                    "request_id": "x",
                    "task": {
                        "waypoints": [
                            {
                                "motion": "free",
                                "position": [0, 0, 0],
                                "keep_orientation": True,
                                "rotation": {"axis": "x", "angle_deg": 10, "frame": "base"},
                            }
                        ]
                    },
                },
            ),
            (
                "pipeline.start",
                {
                    "request_id": "x",
                    "task_id": "abc",
                    "mode": "prepare",
                    "planning_domain": 81,
                    "simulation_domain": 81,
                },
            ),
            ("artifact.read", {"artifact_id": "../../etc/passwd"}),
        ]
        for op, a in cases:
            with self.subTest(op=op):
                with self.assertRaises((ValueError, __import__("jsonschema").ValidationError)):
                    self.b.invoke("franka." + op, a)
        self.assertEqual(self.b.store.data["sessions"], {})




    def test_task_create_requires_motion_on_every_waypoint(self):
        from jsonschema import ValidationError

        valid = {"position": [0, 0, 0], "motion": "linear"}
        missing = {"position": [0, 0, 0]}
        for points, index in (([missing], 0), ([valid, missing], 1)):
            with self.subTest(index=index):
                with self.assertRaises(ValidationError) as raised:
                    self.call("task.create", task={"waypoints": points})
                self.assertEqual(raised.exception.validator, "required")
                self.assertIn("motion", raised.exception.message)
                self.assertEqual(list(raised.exception.absolute_path),
                                 ["task", "waypoints", index])
        self.assertEqual(self.b.store.data["tasks"], {})
        self.assertEqual(self.b.store.data["sessions"], {})
        self.assertEqual(self.b.store.data["requests"], {})
        self.assertFalse(any(self.b.store.root.glob("task_*")))

    def test_task_create_preserves_explicit_motion(self):
        for motion in ("linear", "free"):
            with self.subTest(motion=motion):
                task = self.call("task.create", task={"waypoints": [
                    {"position": [0, 0, 0], "motion": motion,
                     "keep_orientation": False,
                     "rotation": {"axis": "x", "angle_deg": 30, "frame": "base"}}
                ]})
                saved = json.loads(self.b.store.task(task["task_id"]).read_text())
                self.assertEqual(saved["waypoints"][0]["motion"], motion)
        self.assertEqual(self.b.store.data["sessions"], {})

    def test_production_package_excludes_mock(self):
        v = builder.build(ROOT, self.root / "out", "amd64")
        with tarfile.open(v["package"]) as tar:
            self.assertFalse(any("mock" in n for n in tar.getnames()))
            for name in ("AGENT_OPERATIONS.md", "RIBBON.md"):
                self.assertEqual(tar.extractfile("franka-ribbon/docs/" + name).read(),
                                 (ROOT / "docs" / name).read_bytes())
            m = json.load(tar.extractfile("franka-ribbon/adapter.json"))
            self.assertEqual(m["runtime_requirements"]["architecture"], "amd64")
            self.assertEqual(m["version"], json.loads((ROOT / "adapter.json").read_text())["version"])

    def test_release_version_and_no_overwrite(self):
        import hashlib
        import shutil
        manifest = json.loads((ROOT / "adapter.json").read_text())
        version = manifest["version"]
        output = self.root / "release"
        with self.assertRaises(ValueError):
            builder.build(ROOT, output, "amd64", version="999.0.0" if version != "999.0.0" else "998.0.0")
        self.assertFalse(output.exists())
        result = builder.build(ROOT, output, "amd64", version=version)
        archive = Path(result["package"])
        before = archive.read_bytes()
        checksum = archive.with_suffix(archive.suffix + ".sha256")
        self.assertEqual(checksum.read_text().strip(), "sha256:" + hashlib.sha256(before).hexdigest())
        with self.assertRaises(FileExistsError):
            builder.build(ROOT, output, "amd64", version=version)
        self.assertEqual(archive.read_bytes(), before)
        # A changed contract version produces a separate release with matching metadata.
        snapshot = self.root / "snapshot"
        snapshot.mkdir()
        shutil.copytree(ROOT / "src", snapshot / "src")
        shutil.copytree(ROOT / "docs", snapshot / "docs")
        parts = version.split(".")
        manifest["version"] = ".".join(parts[:2] + [str(int(parts[2]) + 1)])
        (snapshot / "adapter.json").write_text(json.dumps(manifest))
        new = builder.build(snapshot, output, "amd64", version=manifest["version"])
        self.assertNotEqual(new["package"], result["package"])
        with tarfile.open(new["package"]) as tar:
            self.assertEqual(json.load(tar.extractfile("franka-ribbon/adapter.json"))["version"], manifest["version"])
        manifest["version"] = "../../invalid"
        (snapshot / "adapter.json").write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            builder.build(snapshot, output, "amd64")

    def test_build_requires_release_manual(self):
        import shutil
        snapshot = self.root / "manual-source"
        snapshot.mkdir()
        shutil.copytree(ROOT / "src", snapshot / "src")
        shutil.copyfile(ROOT / "adapter.json", snapshot / "adapter.json")
        output = self.root / "manual-release"
        with self.assertRaisesRegex(ValueError, "docs/AGENT_OPERATIONS.md"):
            builder.build(snapshot, output, "amd64")
        (snapshot / "docs").mkdir()
        (snapshot / "docs/RIBBON.md").write_text("Legacy reference cannot replace the Agent manual")
        with self.assertRaisesRegex(ValueError, "docs/AGENT_OPERATIONS.md"):
            builder.build(snapshot, output, "amd64")
        (snapshot / "docs/AGENT_OPERATIONS.md").write_text("   ")
        with self.assertRaisesRegex(ValueError, "docs/AGENT_OPERATIONS.md"):
            builder.build(snapshot, output, "amd64")
        self.assertFalse(output.exists())

    def test_build_cli_reads_contract_version(self):
        import subprocess
        version = json.loads((ROOT / "adapter.json").read_text())["version"]
        output = self.root / "cli-release"
        args = [sys.executable, str(ROOT / "scripts/build_adapter.py"),
                "--architecture", "amd64", "--output", str(output)]
        result = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        release = json.loads(result.stdout)
        self.assertEqual(release["version"], version)
        self.assertEqual(Path(release["package"]).name, f"franka-ribbon-{version}-amd64.tar.gz")
        wrong = "999.0.0" if version != "999.0.0" else "998.0.0"
        result = subprocess.run(args + ["--version", wrong], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must match adapter.json", result.stderr)

    def connector_python_fixture(self, home):
        import shlex
        interpreter = home / ".local/lib/qizhen-edge/current/bin/python"
        interpreter.parent.mkdir(parents=True, exist_ok=True)
        # A temporary Connector layout delegates to the suite's actual environment.
        interpreter.write_text("#!/bin/sh\nexec " + shlex.quote(sys.executable) + ' "$@"\n')
        interpreter.chmod(0o755)
        return interpreter

    def test_scripts_require_connector_python_without_fallback_or_override(self):
        import os
        import subprocess
        home = self.root / "no-connector-home"
        home.mkdir()
        env = dict(os.environ, HOME=str(home), QIZHEN_FRANKA_TEST_PYTHON=sys.executable)
        for script in ("test.sh", "install.sh", "update.sh"):
            with self.subTest(script=script):
                result = subprocess.run(["/bin/bash", str(ROOT / "scripts" / script)],
                                        env=env, capture_output=True, text=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Connector Python is unavailable", result.stderr)
        # Even an invalid override cannot change the fixed Connector interpreter.
        interpreter = self.connector_python_fixture(home)
        result = subprocess.run(["/bin/bash", str(ROOT / "scripts/test.sh"), "-k", "test_all_contract_schemas"],
                                env={**env, "QIZHEN_FRANKA_TEST_PYTHON": "/nonexistent/python"},
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Test Python: " + sys.executable, result.stdout)
        self.assertIn("Ran 1 test", result.stderr)
        interpreter.chmod(0o644)
        result = subprocess.run(["/bin/bash", str(ROOT / "scripts/test.sh")],
                                env=env, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Connector Python is unavailable", result.stderr)

    def systemctl_fixture(self, log):
        fake = self.root / "fake-systemctl"
        fake.write_text("""#!/bin/bash
printf 'systemctl %s\n' "$*" >> "$TEST_CONNECTOR_LOG"
case "$2" in
  is-active) [[ -f "$TEST_SERVICE_STATE" ]] ;;
  stop)
    [[ ${TEST_FAIL_STOP:-0} != 1 ]] || exit 7
    rm -f "$TEST_SERVICE_STATE" ;;
  start)
    [[ ${TEST_FAIL_START:-0} != 1 ]] || exit 8
    touch "$TEST_SERVICE_STATE" ;;
  *) exit 2 ;;
esac
""")
        fake.chmod(0o755)
        state = self.root / "service-active"
        state.touch()
        return {"QIZHEN_SYSTEMCTL_BIN": str(fake), "TEST_SERVICE_STATE": str(state)}

    def test_update_script_uses_update_and_rejects_unsafe_inputs(self):
        import hashlib
        import os
        import subprocess
        home = self.root / "home"
        configdir = home / ".config/qizhen-franka"
        configdir.mkdir(parents=True)
        (configdir / "config.json").write_text(json.dumps(self.c))
        log = self.root / "connector.log"
        fake = self.root / "fake-connector"
        fake.write_text("#!/bin/bash\nprintf '%s\\n' \"$*\" >> \"$TEST_CONNECTOR_LOG\"\n")
        fake.chmod(0o755)
        package = self.root / "release.tar.gz"
        package.write_bytes(b"test-only package")
        digest = "sha256:" + hashlib.sha256(package.read_bytes()).hexdigest()
        env = dict(os.environ, HOME=str(home), QIZHEN_EDGE_BIN=str(fake),
                   TEST_CONNECTOR_LOG=str(log))
        self.connector_python_fixture(home)
        env.update(self.systemctl_fixture(log))
        def run(checksum):
            return subprocess.run(["bash", str(ROOT / "scripts/update.sh"), str(package), checksum],
                                  env=env, capture_output=True, text=True)
        bad = run("sha256:" + "0" * 64)
        self.assertNotEqual(bad.returncode, 0)
        self.assertFalse(log.exists())
        for state in ({"state": "unknown"}, {"state": "running"},
                      {"state": "failed", "control_lock_pending": True}):
            self.b.store.data["sessions"] = {"unfinished": state}
            self.b.save()
            completed = run(digest)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            report = json.loads(completed.stdout)
            self.assertEqual(report["broker"], "stopped")
            self.assertEqual(report["archived_sessions"], ["unfinished"])
            archive = json.loads(Path(report["archive"]).read_text())
            self.assertEqual(archive["state"]["sessions"], {"unfinished": state})
            self.assertEqual(json.loads(self.b.store.path.read_text())["sessions"], {})
            self.assertTrue(report["locks_released"])
            self.assertFalse(report["hardware_accessed"])
            self.assertFalse((self.b.store.root / "broker.pid").exists())
            self.assertEqual(log.read_text().splitlines(), [
                "systemctl --user is-active --quiet qizhen-linux-edge.service",
                "systemctl --user stop qizhen-linux-edge.service",
                f"adapter update {package} --sha256 {digest}",
                "adapter start adapter_franka_ribbon",
                "adapter health adapter_franka_ribbon", "capabilities sync",
                "systemctl --user start qizhen-linux-edge.service",
                "systemctl --user is-active --quiet qizhen-linux-edge.service"])
            log.unlink()
        # Identity failure must still stop the update before calling the Connector.
        (self.b.store.root / "broker.pid").write_text(str(os.getpid()))
        rejected = run(digest)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("PID does not identify", rejected.stderr)
        self.assertEqual(log.read_text().splitlines(), [
            "systemctl --user is-active --quiet qizhen-linux-edge.service",
            "systemctl --user stop qizhen-linux-edge.service",
            "systemctl --user start qizhen-linux-edge.service",
            "systemctl --user is-active --quiet qizhen-linux-edge.service"])
        self.assertTrue(Path(env["TEST_SERVICE_STATE"]).exists())
        self.assertEqual(json.loads((configdir / "config.json").read_text()), self.c)

    def test_update_service_failures_restore_previous_state_and_preserve_error(self):
        import hashlib
        import os
        import subprocess
        home = self.root / "update-home"
        configdir = home / ".config/qizhen-franka"
        configdir.mkdir(parents=True)
        (configdir / "config.json").write_text(json.dumps(self.c))
        log = self.root / "update.log"
        fake = self.root / "failing-connector"
        fake.write_text("""#!/bin/bash
printf '%s\n' "$*" >> "$TEST_CONNECTOR_LOG"
[[ "$*" != "${TEST_FAIL_COMMAND:-}" ]] || exit 9
""")
        fake.chmod(0o755)
        package = self.root / "release.tar.gz"
        package.write_bytes(b"test-only package")
        digest = "sha256:" + hashlib.sha256(package.read_bytes()).hexdigest()
        env = dict(os.environ, HOME=str(home), QIZHEN_EDGE_BIN=str(fake),
                   TEST_CONNECTOR_LOG=str(log))
        self.connector_python_fixture(home)
        env.update(self.systemctl_fixture(log))
        state = Path(env["TEST_SERVICE_STATE"])
        def run(**extra):
            return subprocess.run(["bash", str(ROOT / "scripts/update.sh"), str(package), digest],
                                  env={**env, **extra}, capture_output=True, text=True, timeout=10)
        for failed in (f"adapter update {package} --sha256 {digest}",
                       "adapter start adapter_franka_ribbon",
                       "adapter health adapter_franka_ribbon", "capabilities sync"):
            with self.subTest(failed=failed):
                state.touch()
                log.unlink(missing_ok=True)
                result = run(TEST_FAIL_COMMAND=failed)
                self.assertEqual(result.returncode, 9, result.stderr)
                lines = log.read_text().splitlines()
                self.assertEqual(lines[-2:], ["systemctl --user start qizhen-linux-edge.service",
                    "systemctl --user is-active --quiet qizhen-linux-edge.service"])
                self.assertTrue(state.exists())
                self.assertIn("no adapter rollback", result.stderr)
        # A failed stop must prevent broker state changes and all adapter commands.
        log.unlink()
        result = run(TEST_FAIL_STOP="1")
        self.assertEqual(result.returncode, 7)
        self.assertFalse(any(line.startswith("adapter ") for line in log.read_text().splitlines()))
        # Failure with the service initially stopped leaves it stopped.
        state.unlink(missing_ok=True)
        log.unlink()
        result = run(TEST_FAIL_COMMAND="capabilities sync")
        self.assertEqual(result.returncode, 9)
        self.assertFalse(state.exists())
        self.assertNotIn("systemctl --user start", log.read_text())
        # Report recovery failure without replacing the original update error.
        state.touch()
        log.unlink()
        result = run(TEST_FAIL_COMMAND="capabilities sync", TEST_FAIL_START="1")
        self.assertEqual(result.returncode, 9)
        self.assertIn("Connector recovery failed", result.stderr)
        # Failure to start at the end is itself an update failure.
        state.touch()
        log.unlink()
        result = run(TEST_FAIL_START="1")
        self.assertEqual(result.returncode, 8)
        self.assertIn("Connector recovery failed", result.stderr)

    def broker_control_fixture(self, ignore_term=False):
        import os
        home = self.root / "control-home"
        home.mkdir()
        handler = home / "installed/handler.py"
        handler.parent.mkdir()
        handler.write_text("""import argparse,fcntl,json,os,pathlib,signal,socket
p=argparse.ArgumentParser()
p.add_argument('--serve',action='store_true')
p.add_argument('--config')
a=p.parse_args()
c=json.loads(pathlib.Path(a.config).read_text())
r=pathlib.Path(c['state_dir']);r.mkdir(parents=True,exist_ok=True)
lock=(r/'broker.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
if c.get('test_ignore_term'): signal.signal(signal.SIGTERM,signal.SIG_IGN)
s=socket.socket(socket.AF_UNIX);s.bind(str(r/'broker.sock'));s.listen()
pidfile=r/'broker.pid.tmp';pidfile.write_text(str(os.getpid()));pidfile.replace(r/'broker.pid')
while True:
 client,_=s.accept();client.close()
""")
        config = home / "config.json"
        config.write_text(json.dumps({**self.c, "test_ignore_term": ignore_term}))
        index = home / ".local/share/qizhen-edge/adapters/adapter_franka_ribbon/state.json"
        index.parent.mkdir(parents=True)
        index.write_text(json.dumps({"current": "test-hash", "versions": [
            {"artifact_hash": "test-hash", "path": str(handler.parent)}]}))
        return config, dict(os.environ, HOME=str(home))

    def run_broker_control(self, config, env, *extra):
        import subprocess
        return subprocess.run([sys.executable, str(ROOT / "scripts/broker_control.py"),
                               "--config", str(config), *extra], env=env,
                              capture_output=True, text=True, timeout=20)

    def cleanup_test_broker(self):
        import os
        import signal
        pidfile = self.b.store.root / "broker.pid"
        if pidfile.exists():
            pid = int(pidfile.read_text())
            # Only the isolated fake handler owned by this fixture can be killed.
            cmd = Path(f"/proc/{pid}/cmdline")
            if cmd.exists() and str(self.root / "control-home/installed/handler.py").encode() in cmd.read_bytes().split(b"\0"):
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def test_broker_control_restart_preserves_unknown_locks_and_idempotency(self):
        from core import canonical
        config, env = self.broker_control_fixture()
        sessions = {"active": {"state": "running", "operation_id": "franka.delta.move"},
                    "failed": {"state": "failed", "control_lock_pending": True, "operation_id": "franka.delta.move"},
                    "legacy": {"state": "unknown", "operation_id": "franka.delta.move"},
                    "done": {"state": "succeeded", "operation_id": "franka.delta.move"}}
        parameters = {"request_id": "old-request", "translation_m": [0, 0, 0]}
        self.b.store.data["sessions"] = sessions
        self.b.store.data["requests"] = {"old-request": {
            "input": canonical({"operation": "franka.delta.move", "parameters": parameters}),
            "session_id": "active"}}
        self.b.save()
        before = json.loads((self.b.store.root / "state.json").read_text())
        try:
            checked = self.run_broker_control(config, env, "--stop")
            self.assertNotEqual(checked.returncode, 0)
            self.assertIn("Active or unresolved session", checked.stderr)
            self.assertEqual(json.loads((self.b.store.root / "state.json").read_text()), before)
            first = self.run_broker_control(config, env)
            self.assertEqual(first.returncode, 0, first.stderr)
            report = json.loads(first.stdout)
            self.assertEqual(set(report["archived_sessions"]), {"active", "failed", "legacy"})
            archive = json.loads(Path(report["archive"]).read_text())
            self.assertEqual(archive["state"], before)
            self.assertFalse(archive["physical_stop_verified"])
            self.assertEqual(Path(report["archive"]).stat().st_mode & 0o777, 0o600)
            after = json.loads((self.b.store.root / "state.json").read_text())
            self.assertEqual(set(after["sessions"]), set(sessions))
            self.assertEqual(after["sessions"]["done"], sessions["done"])
            for sid in ("active", "failed", "legacy"):
                self.assertEqual(after["sessions"][sid]["state"], "unknown")
                self.assertTrue(after["sessions"][sid]["control_lock_pending"])
            self.assertEqual(after["requests"], before["requests"])
            self.assertEqual(after["tasks"], before["tasks"])
            self.assertEqual(after["artifacts"], before["artifacts"])
            self.b = Broker(self.c)
            self.assertIsNotNone(self.b.blocked())
            with patch("broker.command") as launch, patch("stop_guard.read_snapshot", side_effect=OSError("offline")):
                retry = self.b.invoke("franka.delta.move", parameters)
                launch.assert_not_called()
            self.assertEqual(retry["state"], "failed")
            self.assertFalse(retry["control_lock_pending"])
            self.assertFalse(retry["physical_stop_verified"])
            self.assertTrue(retry["stop_verification"]["state_unavailable"])
            self.assertEqual(self.b.store.data["requests"]["old-request"]["session_id"], "active")
            self.assertEqual(set(self.b.store.data["sessions"]), set(sessions))
            second = self.run_broker_control(config, env)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertNotEqual(report["pid"], json.loads(second.stdout)["pid"])
            self.assertEqual(json.loads(second.stdout)["archived_sessions"], [])
            self.assertEqual(len(list((self.b.store.root / "broker-history").glob("*.json"))), 1)
            stopped = self.run_broker_control(config, env, "--stop")
            self.assertEqual(stopped.returncode, 0, stopped.stderr)
        finally:
            self.cleanup_test_broker()

    def test_broker_control_force_stop_archives_and_releases_without_restarting(self):
        config, env = self.broker_control_fixture()
        try:
            started = self.run_broker_control(config, env)
            self.assertEqual(started.returncode, 0, started.stderr)
            sessions = {"active": {"state": "running"},
                        "unknown": {"state": "unknown", "control_lock_pending": True},
                        "locked": {"state": "failed", "control_lock_pending": True}}
            self.b.store.data["sessions"] = sessions
            self.b.save()
            stopped = self.run_broker_control(config, env, "--force-stop")
            self.assertEqual(stopped.returncode, 0, stopped.stderr)
            report = json.loads(stopped.stdout)
            self.assertEqual(report["broker"], "stopped")
            self.assertEqual(json.loads(Path(report["archive"]).read_text())["reason"], "OPERATOR_FORCED_BROKER_STOP")
            self.assertEqual(set(report["archived_sessions"]), set(sessions))
            self.assertEqual(json.loads(Path(report["archive"]).read_text())["state"]["sessions"], sessions)
            self.assertEqual(json.loads(self.b.store.path.read_text())["sessions"], {})
            self.assertTrue(report["locks_released"])
            self.assertFalse(report["hardware_accessed"])
            self.assertFalse((self.b.store.root / "broker.pid").exists())
            self.assertFalse((self.b.store.root / "broker.sock").exists())
            # Stop-only mode works with no installed handler, too; it never resolves startup.
            index = Path(env["HOME"]) / ".local/share/qizhen-edge/adapters/adapter_franka_ribbon/state.json"
            index.unlink()
            repeated = self.run_broker_control(config, env, "--force-stop")
            self.assertEqual(repeated.returncode, 0, repeated.stderr)
            self.assertEqual(json.loads(repeated.stdout)["archived_sessions"], [])
            self.assertFalse(json.loads(repeated.stdout)["locks_released"])
            invalid = self.run_broker_control(config, env, "--stop", "--force-stop")
            self.assertEqual(invalid.returncode, 2)
        finally:
            self.cleanup_test_broker()

    def test_broker_control_escalates_unresponsive_broker(self):
        config, env = self.broker_control_fixture(ignore_term=True)
        try:
            first = self.run_broker_control(config, env)
            self.assertEqual(first.returncode, 0, first.stderr)
            second = self.run_broker_control(config, env)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertNotEqual(json.loads(first.stdout)["pid"], json.loads(second.stdout)["pid"])
        finally:
            self.cleanup_test_broker()

    def test_broker_control_refuses_unrelated_pid(self):
        import os
        config, env = self.broker_control_fixture()
        pidfile = self.b.store.root / "broker.pid"
        pidfile.write_text(str(os.getpid()))
        result = self.run_broker_control(config, env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PID does not identify", result.stderr)
        self.assertEqual(pidfile.read_text(), str(os.getpid()))

    def test_broker_control_reports_startup_failure(self):
        config, env = self.broker_control_fixture()
        (self.root / "control-home/installed/handler.py").write_text("raise SystemExit(1)\n")
        result = self.run_broker_control(config, env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Broker startup failed", result.stderr)
        self.assertTrue((self.b.store.root / "broker-start.log").exists())

    def test_install_starts_service_after_sync_and_reports_failures(self):
        import hashlib
        import os
        import subprocess
        home = self.root / "install-home"
        configdir = home / ".config/qizhen-franka"
        configdir.mkdir(parents=True)
        config = configdir / "config.json"
        config.write_text(json.dumps(self.c))
        log = self.root / "install.log"
        fake = self.root / "install-connector"
        fake.write_text("""#!/bin/bash
printf '%s\n' "$*" >> "$TEST_CONNECTOR_LOG"
[[ "$*" != "${TEST_FAIL_COMMAND:-}" ]] || exit 9
""")
        fake.chmod(0o755)
        package = self.root / "release.tar.gz"
        package.write_bytes(b"test-only package")
        digest = "sha256:" + hashlib.sha256(package.read_bytes()).hexdigest()
        env = dict(os.environ, HOME=str(home), QIZHEN_EDGE_BIN=str(fake),
                   TEST_CONNECTOR_LOG=str(log))
        self.connector_python_fixture(home)
        env.update(self.systemctl_fixture(log))
        state = Path(env["TEST_SERVICE_STATE"])
        def run(checksum=digest, **extra):
            return subprocess.run(["bash", str(ROOT / "scripts/install.sh"), str(package),
                                   checksum, str(config)], env={**env, **extra},
                                  capture_output=True, text=True, timeout=10)
        for active in (False, True):
            with self.subTest(active=active):
                log.unlink(missing_ok=True)
                if active:
                    state.touch()
                else:
                    state.unlink(missing_ok=True)
                result = run()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(log.read_text().splitlines(), [
                    "systemctl --user is-active --quiet qizhen-linux-edge.service",
                    "systemctl --user stop qizhen-linux-edge.service",
                    f"adapter install {package} --sha256 {digest}",
                    "adapter start adapter_franka_ribbon", "adapter health adapter_franka_ribbon",
                    "capabilities sync", "systemctl --user start qizhen-linux-edge.service",
                    "systemctl --user is-active --quiet qizhen-linux-edge.service"])
                self.assertTrue(state.exists())
        log.unlink()
        result = run("sha256:" + "0" * 64)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(log.exists())
        for command in (f"adapter install {package} --sha256 {digest}",
                        "adapter start adapter_franka_ribbon",
                        "adapter health adapter_franka_ribbon", "capabilities sync"):
            for active in (True, False):
                with self.subTest(failed=command, active=active):
                    log.unlink(missing_ok=True)
                    if active:
                        state.touch()
                    else:
                        state.unlink(missing_ok=True)
                    result = run(TEST_FAIL_COMMAND=command)
                    self.assertEqual(result.returncode, 9, result.stderr)
                    lines = log.read_text().splitlines()
                    self.assertEqual(lines[:2], [
                        "systemctl --user is-active --quiet qizhen-linux-edge.service",
                        "systemctl --user stop qizhen-linux-edge.service"])
                    self.assertEqual(state.exists(), active)
                    if active:
                        self.assertEqual(lines[-2:], [
                            "systemctl --user start qizhen-linux-edge.service",
                            "systemctl --user is-active --quiet qizhen-linux-edge.service"])
                    else:
                        self.assertNotIn("systemctl --user start", log.read_text())
        # Stop failure aborts before touching adapter installation.
        state.touch()
        log.unlink()
        result = run(TEST_FAIL_STOP="1")
        self.assertEqual(result.returncode, 7)
        self.assertFalse(any(line.startswith("adapter ") for line in log.read_text().splitlines()))
        self.assertTrue(state.exists())
        # Failed recovery does not hide the original installation error.
        log.unlink()
        result = run(TEST_FAIL_COMMAND="capabilities sync", TEST_FAIL_START="1")
        self.assertEqual(result.returncode, 9)
        self.assertIn("Connector recovery failed", result.stderr)
        log.unlink()
        result = run(TEST_FAIL_START="1")
        self.assertEqual(result.returncode, 8)
        self.assertEqual(log.read_text().splitlines()[-1],
                         "systemctl --user start qizhen-linux-edge.service")
        # A successful start command alone is insufficient: verify active state too.
        env["QIZHEN_SYSTEMCTL_BIN"] = str(self.root / "inactive-systemctl")
        Path(env["QIZHEN_SYSTEMCTL_BIN"]).write_text("""#!/bin/bash
printf 'systemctl %s\n' "$*" >> "$TEST_CONNECTOR_LOG"
[[ "$2" == start || "$2" == stop ]]
""")
        Path(env["QIZHEN_SYSTEMCTL_BIN"]).chmod(0o755)
        log.unlink()
        result = run()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(log.read_text().splitlines()[-1],
                         "systemctl --user is-active --quiet qizhen-linux-edge.service")

    def test_automatic_release_builds_before_install_or_update(self):
        import os
        import shutil
        import subprocess
        snapshot = self.root / "release-source"
        snapshot.mkdir()
        shutil.copytree(ROOT / "scripts", snapshot / "scripts")
        shutil.copytree(ROOT / "src", snapshot / "src")
        shutil.copytree(ROOT / "docs", snapshot / "docs")
        manifest = json.loads((ROOT / "adapter.json").read_text())
        contract = snapshot / "adapter.json"
        contract.write_text(json.dumps(manifest))
        # Stub only the nested test launcher to avoid recursively launching this suite.
        launcher = snapshot / "scripts/test.sh"
        launcher.write_text("#!/bin/bash\necho test >> \"$TEST_CONNECTOR_LOG\"\n")
        home = self.root / "home"
        configdir = home / ".config/qizhen-franka"
        configdir.mkdir(parents=True)
        (configdir / "config.json").write_text(json.dumps(self.c))
        log = self.root / "connector.log"
        fake = self.root / "connector"
        fake.write_text("#!/bin/bash\nprintf '%s\\n' \"$*\" >> \"$TEST_CONNECTOR_LOG\"\n")
        fake.chmod(0o755)
        env = dict(os.environ, HOME=str(home), QIZHEN_EDGE_BIN=str(fake),
                   TEST_CONNECTOR_LOG=str(log))
        self.connector_python_fixture(home)
        env.update(self.systemctl_fixture(log))
        def run(name):
            return subprocess.run(["bash", str(snapshot / "scripts" / name)],
                                  cwd=self.root, env=env, capture_output=True, text=True)
        installed = run("install.sh")
        self.assertEqual(installed.returncode, 0, installed.stderr)
        package = snapshot / "packages" / f"franka-ribbon-{manifest['version']}-amd64.tar.gz"
        self.assertTrue(package.exists())
        lines = log.read_text().splitlines()
        self.assertEqual(lines[0], "test")
        self.assertEqual(lines[1:3], [
            "systemctl --user is-active --quiet qizhen-linux-edge.service",
            "systemctl --user stop qizhen-linux-edge.service"])
        self.assertTrue(lines[3].startswith(f"adapter install {package} --sha256 "))
        self.assertEqual(lines[-3:], ["capabilities sync",
            "systemctl --user start qizhen-linux-edge.service",
            "systemctl --user is-active --quiet qizhen-linux-edge.service"])
        before = package.read_bytes()
        log.unlink()
        duplicate = run("update.sh")
        self.assertEqual(duplicate.returncode, 0, duplicate.stderr)
        self.assertEqual(log.read_text().splitlines()[0], "test")
        self.assertTrue(any(line.startswith(f"adapter update {package} --sha256 ")
                            for line in log.read_text().splitlines()))
        self.assertEqual(package.read_bytes(), before)
        # Source changes and damaged/incomplete releases fail before service calls.
        source = snapshot / "src/handler.py"
        original = source.read_bytes()
        checksum = Path(str(package) + ".sha256")
        original_checksum = checksum.read_bytes()
        manual = snapshot / "docs/AGENT_OPERATIONS.md"
        original_manual = manual.read_bytes()
        for invalid in ("source", "manual", "checksum", "missing-checksum", "missing-package", "contract"):
            with self.subTest(invalid=invalid):
                if invalid == "source":
                    source.write_bytes(original + b"\n# changed source\n")
                elif invalid == "manual":
                    manual.write_bytes(original_manual + b"\nchanged manual\n")
                elif invalid == "checksum":
                    checksum.write_text("sha256:" + "0" * 64)
                elif invalid == "missing-checksum":
                    checksum.unlink()
                elif invalid == "missing-package":
                    package.unlink()
                else:
                    changed = dict(manifest, description="changed contract")
                    contract.write_text(json.dumps(changed))
                log.unlink()
                rejected = run("update.sh")
                self.assertNotEqual(rejected.returncode, 0)
                self.assertEqual(log.read_text().splitlines(), ["test"])
                source.write_bytes(original)
                manual.write_bytes(original_manual)
                checksum.write_bytes(original_checksum)
                package.write_bytes(before)
                contract.write_text(json.dumps(manifest))
        parts = manifest["version"].split(".")
        manifest["version"] = ".".join(parts[:2] + [str(int(parts[2]) + 1)])
        contract.write_text(json.dumps(manifest))
        log.unlink()
        updated = run("update.sh")
        self.assertEqual(updated.returncode, 0, updated.stderr)
        lines = log.read_text().splitlines()
        self.assertEqual(lines[0], "test")
        self.assertEqual(lines[1:3], [
            "systemctl --user is-active --quiet qizhen-linux-edge.service",
            "systemctl --user stop qizhen-linux-edge.service"])
        self.assertTrue(lines[3].startswith("adapter update "))
        self.assertIn(f"franka-ribbon-{manifest['version']}-amd64.tar.gz", lines[3])
        self.assertEqual(lines[-3:], ["capabilities sync",
            "systemctl --user start qizhen-linux-edge.service",
            "systemctl --user is-active --quiet qizhen-linux-edge.service"])
        log.unlink()
        launcher.write_text("#!/bin/bash\nexit 1\n")
        failed = run("install.sh")
        self.assertNotEqual(failed.returncode, 0)
        self.assertFalse(log.exists())

    def test_flange_task_and_inline_calibration_marker(self):
        t = self.call("task.create", task={"waypoints": [{"motion": "free", "position": [0.003, 0, 0]}]})
        d = json.loads(self.b.store.task(t["task_id"]).read_text())
        self.assertEqual(d["end_effector_link"], "fer_ribbon_tcp")
        self.assertEqual(d["x_floor"], {"link": "fer_ribbon_tcp", "minimum": "start"})
        pose = {"joint_positions": [0] * 7}
        with self.assertRaises(__import__("jsonschema").ValidationError):
            validate("franka.task.create", {"request_id": "old", "task": {"waypoints": [{"motion": "free", "position": [0, 0, 0]}], "start_state": pose}})
        for mount in ("flange_8mm_v2", "flange_58mm_v2", "unknown"):
            with self.subTest(mount=mount), self.assertRaises(__import__("jsonschema").ValidationError):
                self.call("task.create", task={"waypoints": [{"motion": "linear", "position": [0, 0, 0]}],
                                              "start_state": {**pose, "ribbon_mount": mount}})
        pose["ribbon_mount"] = "flange_58mm_v3"
        task = {"waypoints": [{"motion": "linear", "position": [0, 0, 0]}], "start_state": pose}
        saved = self.call("task.create", task=task)
        self.assertEqual(json.loads(self.b.store.task(saved["task_id"]).read_text())["start_state"], pose)
        self.assertEqual(len(self.b.store.data["tasks"]), 2)
        self.assertEqual(self.b.store.data["sessions"], {})

    def test_markerset_command_and_shape_filter(self):
        for mode in ("monitor", "record"):
            with self.subTest(mode=mode):
                argv, _ = command(self.c, self.b.store, "franka.nokov." + mode, {}, self.root)
                self.assertEqual(argv[argv.index("--plane") + 1], "ribbon_1021")
        argv, _ = command(self.c, self.b.store, "franka.nokov.list", {}, self.root)
        self.assertNotIn("--plane", argv)
        p = self.b.store.root / "markers.csv"
        p.write_text("source,set_name,wall_unix_ns,frame,wall_iso,marker_name,x_mm,y_mm,z_mm\n"
                     "markerset,ribbon+y,200,2,now,old,9,9,9\n"
                     "markerset,ribbon,200,2,now,old1,9,9,9\n"
                     "markerset,ribbon,200,2,now,old2,9,9,9\n"
                     "markerset,x1,200,2,now,Marker2,9,9,9\n"
                     "markerset,x0,200,2,now,Marker3,9,9,9\n"
                     "rigidbody,ribbon_1021,200,2,now,body,9,9,9\n"
                     "markerset,ribbon_1021,100,1,now,Marker1,1,2,3\n"
                     "markerset,ribbon_1021,100,1,now,Marker2,4,5,6\n"
                     "markerset,ribbon_1021,200,2,now,Marker1,7,8,9\n"
                     "markerset,ribbon_1021,200,2,now,Marker2,nan,8,9\n")
        d = shape_extract(self.b.store, self.b.store.register(p))
        self.assertEqual(d["set_name"], "ribbon_1021")
        self.assertEqual(d["n_visible"], 2)
        self.assertEqual(d["frame"], 1)
        self.assertEqual(d["record_last_frame"], 2)
        self.assertEqual([v["xyz_mm"] for v in d["points"]], [[1, 2, 3], [4, 5, 6]])
        self.assertEqual(d["coordinate_frame"], "mocap_world")
        self.assertEqual(d["unit"], "mm")

    def test_shape_extraction_does_not_relabel_legacy_or_endpoint_assets(self):
        p = self.b.store.root / "legacy_markers.csv"
        for asset in ("ribbon", "ribbon+y", "x0", "x1"):
            with self.subTest(asset=asset):
                p.write_text("source,set_name,wall_unix_ns,frame,wall_iso,marker_name,x_mm,y_mm,z_mm\n"
                             f"markerset,{asset},100,1,now,Marker1,1,2,3\n"
                             f"markerset,{asset},100,1,now,Marker2,4,5,6\n")
                with self.assertRaisesRegex(ValueError, "INSUFFICIENT_VISIBLE_POINTS"):
                    shape_extract(self.b.store, self.b.store.register(p))
        self.assertFalse(p.with_suffix(".shape.json").exists())

    def test_alignment_constraints_and_preview_command(self):
        args = {"translation_m": [0, 0, 0], "align_ribbon_up": True, "duration_seconds": 2}
        validate("franka.delta.preview", args)
        argv, _ = command(self.c, self.b.store, "franka.delta.preview", args, self.root)
        self.assertIn("--align-ribbon-up", argv)
        self.assertIn("--dry-run", argv)
        for bad in [{**args, "translation_m": [0.001, 0, 0]}, {**args, "rotation_deg": 1}, {**args, "duration_seconds": 1}]:
            with self.assertRaises(ValueError): validate("franka.delta.preview", bad)

    def test_documented_prompt_actions_without_enter(self):
        self.assertEqual(prompt_actions("franka.ribbon.run", "暂停 RESUME / SKIP / QUIT"), ["RESUME", "SKIP", "QUIT"])
        self.assertEqual(prompt_actions("franka.ribbon.run", "暂停 RESUME/QUIT"), ["RESUME", "QUIT"])
        self.assertIsNone(prompt_actions("franka.ribbon.run", "自动调平，无逐条输入 MOVE"))
        self.assertEqual(prompt_actions("franka.pipeline.start", "最终执行：输入 MOVE"), ["MOVE"])
        for op in ["franka.home", "franka.delta.move"]:
            self.assertIsNone(prompt_actions(op, "不等待 Enter 或回车；连接后立即运动"))
        with self.assertRaises(__import__("jsonschema").ValidationError):
            validate("franka.session.respond", {"request_id": "x", "session_id": "s", "confirmation_id": "c", "action": "ENTER"})

    def test_native_leveling_pause_requires_complete_current_prompt(self):
        prompt = "处理完成输入 RESUME 重新测量；输入 QUIT 退出"
        skip = "；人工检查确认调平可接受后输入 SKIP，记为成功并更新规划初始位姿"
        for operation in ("franka.ribbon.run", "franka.pipeline.start"):
            for suffix, expected in (("", ["RESUME", "QUIT"]),
                                     (skip, ["RESUME", "SKIP", "QUIT"])):
                complete = prompt + suffix + "："
                with self.subTest(operation=operation, skip=bool(suffix)):
                    self.assertEqual(prompt_actions(operation, "任务已暂停\r\n" + complete), expected)
                    for length in range(1, len(complete)):
                        self.assertIsNone(prompt_actions(operation, complete[:length]))
                    self.assertIsNone(prompt_actions(operation, complete + "\r\n继续测量中"))
                    self.assertIsNone(prompt_actions(operation, "日志引用：" + complete))
        for operation in ("franka.home", "franka.delta.move", "franka.session.status"):
            self.assertIsNone(prompt_actions(operation, prompt + "："))

    def _exercise_native_leveling_pause_through_pty(self, allow_skip):
        self.vendor()
        prompt = "处理完成输入 RESUME 重新测量；输入 QUIT 退出"
        if allow_skip:
            prompt += "；人工检查确认调平可接受后输入 SKIP，记为成功并更新规划初始位姿"
        prompt += "："
        action = "SKIP" if allow_skip else "RESUME"
        program = "\n".join([
            "import argparse,json,time",
            "from pathlib import Path",
            "p=argparse.ArgumentParser();p.add_argument('--output-root');a,rest=p.parse_known_args()",
            "print('任务已暂停，历史和累计拉伸记录保留。',flush=True)",
            "prompt=" + repr(prompt),
            "print(prompt[:20],end='',flush=True);time.sleep(.1)",
            "print(prompt[20:],end='',flush=True)",
            "assert input() == " + repr(action),
            "print('最终执行：输入 MOVE',flush=True)",
            "assert input() == 'MOVE'",
            "d=Path(a.output_root);f=d/'result.json'",
            "f.write_text(json.dumps({'status':'succeeded','mode':'plan','outcome':'planned'}))",
            "print(json.dumps({'status':'succeeded','result':str(f),'error':None}),flush=True)",
        ]) + "\n"
        (Path(self.c["workspace"]) / "pipeline/tools/run_pipeline.py").write_text(program)
        task = self.call("task.create", task={"waypoints": [{"motion": "free", "position": [0, 0, 0]}]})
        session = self.wait(self.call("pipeline.start", task_id=task["task_id"], mode="plan"), "waiting_confirmation")
        expected = ["RESUME", "SKIP", "QUIT"] if allow_skip else ["RESUME", "QUIT"]
        self.assertEqual(session["confirmation"]["actions"], expected)
        first = session["confirmation"]["confirmation_id"]
        if not allow_skip:
            with self.assertRaisesRegex(ValueError, "STALE_OR_INVALID_CONFIRMATION"):
                self.call("session.respond", session_id=session["session_id"], confirmation_id=first, action="SKIP")
        self.call("session.respond", session_id=session["session_id"], confirmation_id=first, action=action)
        session = self.wait(session, "waiting_confirmation")
        second = session["confirmation"]["confirmation_id"]
        self.assertNotEqual(first, second)
        self.assertEqual(session["confirmation"]["actions"], ["MOVE"])
        with self.assertRaisesRegex(ValueError, "STALE_OR_INVALID_CONFIRMATION"):
            self.call("session.respond", session_id=session["session_id"], confirmation_id=first, action="MOVE")
        self.call("session.respond", session_id=session["session_id"], confirmation_id=second, action="MOVE")
        session = self.wait(session, "succeeded")
        self.assertEqual(session["result"]["receipt"]["outcome"], "planned")
        self.assertFalse(session["result"]["hardware_motion_verified"])

    def test_native_resume_quit_through_persistent_pty(self):
        self._exercise_native_leveling_pause_through_pty(False)

    def test_native_optional_skip_through_persistent_pty(self):
        self._exercise_native_leveling_pause_through_pty(True)

    def pipeline_receipt_fixture(self, outcome):
        directory = self.b.store.root / "session_fixture"
        directory.mkdir(exist_ok=True)
        r = directory / "result.json"
        r.write_text(json.dumps({"status": "succeeded", "mode": "execute", "outcome": outcome}))
        (directory / "terminal.log").write_text(json.dumps({"result": str(r)}))
        return {"directory": str(directory), "operation_id": "franka.pipeline.start", "parameters": {"mode": "execute"}}, directory

    def test_captured_pipeline_receipt_and_artifacts(self):
        s, d = self.pipeline_receipt_fixture("executed_and_captured")
        (d / "markers.csv").write_text("recorded markers\n")
        (d / "capture_result.json").write_text(json.dumps({"completed": True, "sample_count": 10, "files": ["markers.csv"]}))
        r = self.b.receipt(s, 0)
        self.assertTrue(r["capture_completed"])
        self.assertTrue(r["hardware_motion_verified"])
        self.assertEqual(r["capture_receipt"]["sample_count"], 10)

    def test_incomplete_or_escaping_capture_is_rejected(self):
        s, d = self.pipeline_receipt_fixture("executed_and_captured")
        for capture in [{"completed": False, "sample_count": 10, "files": ["markers.csv"]},
                        {"completed": True, "sample_count": 1, "files": ["markers.csv"]},
                        {"completed": True, "sample_count": 10, "files": []},
                        {"completed": True, "sample_count": 10, "files": ["../outside.csv"]}]:
            (d / "capture_result.json").write_text(json.dumps(capture))
            with self.assertRaises(ValueError): self.b.receipt(s, 0)
        (d / "capture_result.json").unlink()
        with self.assertRaisesRegex(ValueError, "CAPTURE_RECEIPT_INVALID"):
            self.b.receipt(s, 0)

    def test_without_capture_and_failed_pipeline_receipts(self):
        s, d = self.pipeline_receipt_fixture("executed_without_capture")
        self.assertFalse(self.b.receipt(s, 0)["capture_completed"])
        with self.assertRaises(ValueError): self.b.receipt(s, 1)
        (d / "result.json").write_text(json.dumps({"status": "failed", "outcome": "executed_without_capture"}))
        with self.assertRaises(ValueError): self.b.receipt(s, 0)

    def test_all_contract_schemas(self):
        validator = __import__("jsonschema").Draft202012Validator
        for operation in OPERATIONS.values():
            validator.check_schema(operation["input_schema"])
            validator.check_schema(operation["output_schema"])

    def test_pause_skip_through_persistent_pty(self):
        self.vendor()
        p = Path(self.c["workspace"]) / "pipeline/tools/run_pipeline.py"
        p.write_text("import argparse,json\nfrom pathlib import Path\np=argparse.ArgumentParser();p.add_argument('--output-root');a,rest=p.parse_known_args()\nprint('暂停：RESUME / SKIP / QUIT',flush=True)\nassert input() == 'SKIP'\nd=Path(a.output_root);f=d/'result.json';f.write_text(json.dumps({'status':'succeeded','mode':'plan','outcome':'planned'}))\nprint(json.dumps({'status':'succeeded','result':str(f),'error':None}),flush=True)\n")
        t = self.call("task.create", task={"waypoints": [{"motion": "free", "position": [0, 0, 0]}]})
        session = self.wait(self.call("pipeline.start", task_id=t["task_id"], mode="plan"), "waiting_confirmation")
        self.assertEqual(session["confirmation"]["actions"], ["RESUME", "SKIP", "QUIT"])
        self.call("session.respond", session_id=session["session_id"], confirmation_id=session["confirmation"]["confirmation_id"], action="SKIP")
        self.assertEqual(self.wait(session, "succeeded")["result"]["receipt"]["outcome"], "planned")

    def vendor(self):
        w = Path(self.c["workspace"])
        (w / "ros/install").mkdir(parents=True)
        (w / "ros/install/setup.bash").write_text(":\n")
        Path(self.c["ros_setup"]).write_text(":\n")
        p = w / "pipeline/tools/run_pipeline.py"
        p.parent.mkdir(parents=True)
        p.write_text("""import argparse,json,sys,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--output-root');p.add_argument('--mode');a,rest=p.parse_known_args()
print('输入 MO',end='',flush=True);time.sleep(.05);print('VE 确认本条运动',flush=True)
assert input()=='MOVE'
print('second step: 输入 MOVE 确认本条运动',flush=True)
assert input()=='MOVE'
d=Path(a.output_root);r={'status':'succeeded','outcome':{'plan':'planned','prepare':'offline_checks_passed','execute':'executed_without_capture'}[a.mode],'mode':a.mode}
f=d/'result.json';f.write_text(json.dumps(r));print(json.dumps({'status':'succeeded','result':str(f),'error':None}),flush=True)
""")
        self.c["backend"] = "real"
        self.b = Broker(self.c)

    def wait(self, s, state):
        end = time.monotonic() + 7
        while time.monotonic() < end:
            v = self.call("session.status", session_id=s["session_id"])
            if v["state"] == state:
                return v
            if v["state"] in {"failed", "unknown"}:
                self.fail(str(v))
            time.sleep(0.03)
        self.fail("timed out: " + str(v))

    def test_real_backend_persistent_pty_two_distinct_move_prompts(self):
        self.vendor()
        t = self.call("task.create", task={"waypoints": [{"motion": "free", "position": [0.003, 0, 0]}]})
        s = self.call("pipeline.start", task_id=t["task_id"], mode="plan")
        s = self.wait(s, "waiting_confirmation")
        first = s["confirmation"]["confirmation_id"]
        self.call(
            "session.respond", session_id=s["session_id"], confirmation_id=first, action="MOVE"
        )
        s = self.wait(s, "waiting_confirmation")
        second = s["confirmation"]["confirmation_id"]
        self.assertNotEqual(first, second)
        with self.assertRaises(ValueError):
            self.call(
                "session.respond", session_id=s["session_id"], confirmation_id=first, action="MOVE"
            )
        self.call(
            "session.respond", session_id=s["session_id"], confirmation_id=second, action="MOVE"
        )
        s = self.wait(s, "succeeded")
        self.assertEqual(s["result"]["receipt"]["outcome"], "planned")
        self.assertFalse(s["result"]["hardware_motion_verified"])

    def stationary(self, mode=1):
        return {"q": [0.0] * 7, "dq": [0.0] * 7, "robot_mode": mode}

    def test_stop_guard_requires_continuous_stationary_samples(self):
        with patch("stop_guard.read_snapshot", return_value=self.stationary()) as reader, patch("stop_guard.time.sleep"):
            report = verify_stopped(self.c, {})
            self.assertTrue(report["verified"])
            self.assertEqual(reader.call_count, 2)
        for mode in (4, 5):
            with patch("stop_guard.read_snapshot", return_value=self.stationary(mode)), patch("stop_guard.time.sleep"):
                self.assertTrue(verify_stopped(self.c, {})["verified"])
        drifting = self.stationary()
        drifting["q"][0] = 0.001
        with patch("stop_guard.read_snapshot", side_effect=[self.stationary(), drifting]), patch("stop_guard.time.sleep"):
            self.assertEqual(verify_stopped(self.c, {})["error"], "ROBOT_POSITION_NOT_STABLE")

    def test_stop_guard_velocity_001_and_position_tolerance_boundaries(self):
        # Exact new bounds pass, including negative velocity; either bound exceeded fails.
        for sign in (-1, 1):
            first = self.stationary()
            second = self.stationary()
            first["dq"] = [sign * 0.01] * 7
            second["dq"] = [sign * 0.01] * 7
            second["q"] = [sign * 0.0001] * 7
            with patch("stop_guard.read_snapshot", side_effect=[first, second]), patch("stop_guard.time.sleep"):
                report = verify_stopped(self.c, {})
                self.assertTrue(report["verified"], report)
                self.assertEqual(len(report["samples"]), 2)
                self.assertEqual(report["velocity_tolerance_rad_s"], 0.01)
                self.assertEqual(report["position_tolerance_rad"], 0.0001)
            for joint in range(7):
                too_fast = self.stationary()
                too_fast["dq"][joint] = sign * 0.010001
                with patch("stop_guard.read_snapshot", return_value=too_fast):
                    self.assertEqual(verify_stopped(self.c, {})["error"], "ROBOT_STILL_MOVING")
                drift = self.stationary()
                drift["q"][joint] = sign * 0.0001001
                with patch("stop_guard.read_snapshot", side_effect=[self.stationary(), drift]), patch("stop_guard.time.sleep"):
                    self.assertEqual(verify_stopped(self.c, {})["error"], "ROBOT_POSITION_NOT_STABLE")

    def test_stop_guard_rejects_moving_invalid_or_unavailable_state(self):
        import subprocess
        for mode in (0, 2, 3, 6, 99, True, "1", None):
            with self.subTest(mode=mode), patch("stop_guard.read_snapshot", return_value=self.stationary(mode)):
                self.assertFalse(verify_stopped(self.c, {})["verified"])
        for field, value in (("dq", [0.010001] * 7), ("dq", [float("nan")] * 7),
                             ("q", [True] * 7), ("q", [float("inf")] * 7), ("q", [])):
            state = self.stationary()
            state[field] = value
            with self.subTest(field=field, value=value), patch("stop_guard.read_snapshot", return_value=state):
                self.assertFalse(verify_stopped(self.c, {})["verified"])
        for error in (OSError("offline"), ValueError("bad json"), subprocess.TimeoutExpired("reader", 2)):
            with patch("stop_guard.read_snapshot", side_effect=error):
                self.assertFalse(verify_stopped(self.c, {})["verified"])

    def failed_session(self):
        directory = self.b.store.root / "failed-session"
        directory.mkdir(exist_ok=True)
        s = {"session_id": "failed-session", "operation_id": "franka.delta.move",
             "state": "failed", "directory": str(directory), "control_lock_pending": True,
             "physical_stop_verified": False, "error": "PROCESS_EXIT_1"}
        self.b.store.data["sessions"][s["session_id"]] = s
        self.b.save()
        return s

    def test_failed_lock_retries_and_unlocks_without_replaying_motion(self):
        s = self.failed_session()
        moving = self.stationary(2)
        with patch("stop_guard.read_snapshot", return_value=moving):
            snapshot = self.call("session.status", session_id=s["session_id"])
            self.assertTrue(snapshot["control_lock_pending"])
            with self.assertRaisesRegex(ValueError, "FCI_BUSY"):
                self.call("delta.preview", translation_m=[0, 0, 0])
        # A caller assertion alone does not bypass the state check.
        with patch("stop_guard.read_snapshot", return_value=moving):
            with self.assertRaisesRegex(ValueError, "STOP_NOT_VERIFIED"):
                self.call("session.reconcile", session_id=s["session_id"], operator_verified_stopped=True)
        with patch("stop_guard.read_snapshot", return_value=self.stationary()), patch("stop_guard.time.sleep"):
            snapshot = self.call("session.status", session_id=s["session_id"])
        self.assertEqual(snapshot["state"], "failed")
        self.assertEqual(snapshot["error"], "PROCESS_EXIT_1")
        self.assertFalse(snapshot["control_lock_pending"])
        self.assertTrue(snapshot["physical_stop_verified"])
        self.assertIsNone(self.b.blocked())
        self.assertEqual(len(self.b.store.data["sessions"]), 1)

    def test_failed_lock_and_legacy_unknown_survive_restart(self):
        s = self.failed_session()
        s["state"] = "unknown"
        s.pop("control_lock_pending")
        self.b.save()
        self.b = Broker(self.c)
        s = self.b.store.data["sessions"][s["session_id"]]
        self.assertEqual(s["state"], "unknown")
        self.assertTrue(session_blocks(s))
        self.assertEqual(s["error"], "PROCESS_EXIT_1")
        self.b = Broker(self.c)
        self.assertTrue(self.b.blocked())

    def test_failed_runtime_checks_stationary_before_unlock(self):
        self.vendor()
        program = Path(self.c["workspace"]) / "pipeline/tools/run_pipeline.py"
        program.write_text("raise SystemExit(1)\n")
        with patch("stop_guard.read_snapshot", return_value=self.stationary()):
            t = self.call("task.create", task={"waypoints": [{"motion": "free", "position": [0, 0, 0]}]})
            s = self.call("pipeline.start", task_id=t["task_id"], mode="plan")
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                result = self.call("session.status", session_id=s["session_id"])
                if result["state"] == "failed" and not result["control_lock_pending"]:
                    break
                time.sleep(0.02)
        self.assertEqual(result["state"], "failed")
        self.assertFalse(result["control_lock_pending"])
        self.assertTrue(result["physical_stop_verified"])

    def test_timeout_releases_lock_on_unavailable_state_without_claiming_stop(self):
        self.vendor()
        program = Path(self.c["workspace"]) / "pipeline/tools/run_pipeline.py"
        program.write_text("import time\ntime.sleep(30)\n")
        session = self.failed_session()
        session.update(state="running", argv=[sys.executable, str(program)], parameters={"mode": "plan"})
        with patch("stop_guard.read_snapshot", side_effect=OSError("offline")):
            self.b.run_real(session, 0.05)
        self.assertEqual(session["state"], "failed")
        self.assertEqual(session["error"], "SESSION_TIMEOUT")
        self.assertFalse(session_blocks(session))
        self.assertFalse(session["physical_stop_verified"])
        self.assertTrue(session["stop_verification"]["state_unavailable"])

    def test_stop_check_uses_robot_samples_with_live_process(self):
        from unittest.mock import Mock
        session = self.failed_session()
        process = Mock()
        process.poll.return_value = None
        self.b.live[session["session_id"]] = (None, process)
        with patch("stop_guard.read_snapshot", return_value=self.stationary(2)) as reader:
            self.b.refresh_failed_lock(session)
            reader.assert_called_once()
        self.assertTrue(session_blocks(session))
        with patch("stop_guard.read_snapshot", return_value=self.stationary()) as reader, patch("stop_guard.time.sleep"):
            self.b.refresh_failed_lock(session)
            self.assertEqual(reader.call_count, 2)
        self.assertFalse(session_blocks(session))
        self.assertTrue(session["physical_stop_verified"])
        process.poll.assert_not_called()
        self.assertIn(session["session_id"], self.b.live)

    def test_stop_check_uses_robot_samples_with_live_descendant(self):
        import os
        import signal
        import subprocess
        leader = subprocess.Popen([sys.executable, "-c",
            "import subprocess,sys; subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])"],
            start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            leader.wait(timeout=3)
            os.killpg(leader.pid, 0)  # Confirm a descendant still keeps the group alive.
            with patch("stop_guard.read_snapshot", return_value=self.stationary()) as reader, patch("stop_guard.time.sleep"):
                report = verify_stopped(self.c, {"process_id": leader.pid})
                self.assertTrue(report["verified"], report)
                self.assertEqual(reader.call_count, 2)
            moving = self.stationary()
            moving["dq"][0] = 0.010001
            with patch("stop_guard.read_snapshot", return_value=moving):
                report = verify_stopped(self.c, {"process_id": leader.pid})
                self.assertFalse(report["verified"])
                self.assertEqual(report["error"], "ROBOT_STILL_MOVING")
        finally:
            try:
                os.killpg(leader.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    def test_real_cancel_does_not_assert_physical_stop(self):
        self.vendor()
        t = self.call("task.create", task={"waypoints": [{"motion": "free", "position": [0, 0, 0]}]})
        s = self.call("pipeline.start", task_id=t["task_id"], mode="plan")
        s = self.wait(s, "waiting_confirmation")
        with patch("stop_guard.read_snapshot", return_value=self.stationary(2)):
            self.call("session.cancel", session_id=s["session_id"])
            end = time.monotonic() + 7
            while time.monotonic() < end:
                s = self.call("session.status", session_id=s["session_id"])
                if s["state"] == "unknown":
                    break
                time.sleep(0.03)
            self.assertEqual(s["state"], "unknown")
            self.assertTrue(s["control_lock_pending"])
            self.assertFalse(s["physical_stop_verified"])
            with self.assertRaisesRegex(ValueError, "FCI_BUSY"):
                self.call("state.read")


if __name__ == "__main__":
    unittest.main(verbosity=2)
