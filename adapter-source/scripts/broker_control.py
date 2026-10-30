"""Preserve unresolved locks on restart; --force-stop explicitly archives and releases them."""

import argparse
import fcntl
import json
import os
import signal
import socket
import subprocess
import sys
import time
import tempfile
from datetime import datetime, timezone
from uuid import uuid4
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from stop_guard import session_blocks


def process_alive(pid):
    try:
        state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
        return state not in {"Z", "X"}
    except (FileNotFoundError, ProcessLookupError):
        return False


def broker_args(pid, config):
    if not process_alive(pid):
        return None
    proc = Path(f"/proc/{pid}")
    try:
        args = [v.decode() for v in (proc / "cmdline").read_bytes().split(b"\0") if v]
        owner = proc.stat().st_uid
    except (FileNotFoundError, ProcessLookupError):
        return None
    if not args and not process_alive(pid):
        return None
    try:
        matches = ("--serve" in args
                   and Path(args[args.index("--config") + 1]).resolve() == config
                   and any(v.endswith("/handler.py") for v in args))
    except (ValueError, IndexError):
        matches = False
    if not matches or owner != os.getuid():
        raise SystemExit("PID does not identify the configured Adapter broker; not stopped.")
    return args


def launch_args(a, config, previous):
    if a.handler:
        handler = a.handler.resolve()
        python = a.python or sys.executable
    elif previous:
        # Restart the exact installed entrypoint, never the unpackaged source tree.
        return [a.python or previous[0], *previous[1:]]
    else:
        index = Path.home() / ".local/share/qizhen-edge/adapters/adapter_franka_ribbon/state.json"
        data = json.loads(index.read_text())
        version = next(v for v in data["versions"] if v["artifact_hash"] == data["current"])
        handler = Path(version["path"]) / "handler.py"
        preferred = Path.home() / ".local/lib/qizhen-edge/current/bin/python"
        python = a.python or (str(preferred) if preferred.is_file() else sys.executable)
    if not handler.is_file():
        raise SystemExit(f"Installed handler not found: {handler}")
    return [str(python), "-I", str(handler), "--serve", "--config", str(config)]


def stop_broker(pid, config):
    if pid is None or broker_args(pid, config) is None:
        return
    for sig, timeout in ((signal.SIGTERM, 3), (signal.SIGKILL, 2)):
        # Recheck identity before every signal, including escalation.
        if broker_args(pid, config) is None:
            return
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not process_alive(pid):
                return
            time.sleep(0.1)
    raise SystemExit("Broker did not exit; socket retained.")


def archive_blocking_sessions(root, operation="restart", release=False):
    """Back up unresolved sessions; only an explicit force-stop releases software locks."""
    path = root / "state.json"
    if not path.exists():
        return {"archived_sessions": [], "archive": None, "locks_released": False}
    original = path.read_text()
    data = json.loads(original)
    blocked = {sid: session for sid, session in data["sessions"].items()
               if session_blocks(session) or (session.get("state") == "failed"
                   and session.get("control_lock_pending"))}
    if not blocked:
        return {"archived_sessions": [], "archive": None, "locks_released": False}
    history = root / "broker-history"
    history.mkdir(mode=0o700, exist_ok=True)
    archive = history / ("forced-reset-" + uuid4().hex + ".json")
    record = {"reason": "OPERATOR_FORCED_BROKER_" + operation.upper(), "physical_stop_verified": False,
              "archived_at": datetime.now(timezone.utc).isoformat(), "locks_released": release,
              "archived_sessions": list(blocked), "state": data}
    # Make a durable full snapshot before changing active state.
    with archive.open("x") as output:
        os.chmod(archive, 0o600)
        json.dump(record, output, ensure_ascii=False)
        output.flush()
        os.fsync(output.fileno())
    sync_directory(history)
    if release:
        data["sessions"] = {sid: session for sid, session in data["sessions"].items()
                            if sid not in blocked}
        for request in data.get("requests", {}).values():
            sid = request.get("session_id")
            if sid in blocked:
                # Keep the idempotency key: the old request returns an archived
                # outcome, never a fresh motion. Archival is not stop evidence.
                result = {k: v for k, v in blocked[sid].items()
                          if k not in {"directory", "argv", "parameters"}}
                result.update(state="failed", confirmation=None, control_lock_pending=False,
                              physical_stop_verified=False, archived=True,
                              stop_verification={"required": True, "verified": False,
                                                 "reason": "operator_forced_release_without_stop_verification"},
                              error="FORCED_BROKER_" + operation.upper() + "_SESSION_ARCHIVED")
                request.pop("session_id")
                request["result"] = result
    else:
        for session in blocked.values():
            session.update(state="unknown", confirmation=None, control_lock_pending=True,
                           physical_stop_verified=False,
                           error=session.get("error") or "BROKER_" + operation.upper() + "_OUTCOME_UNVERIFIED")
    fd, temporary = tempfile.mkstemp(prefix="state-reset-", suffix=".tmp", dir=root)
    try:
        with os.fdopen(fd, "w") as output:
            json.dump(data, output, ensure_ascii=False)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        sync_directory(root)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return {"archived_sessions": list(blocked), "archive": str(archive),
            "preserved_sessions": [] if release else list(blocked), "locks_released": release}


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, default=Path.home() / ".config/qizhen-franka/config.json")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--stop", action="store_true", help="stop only; refuse active or unresolved sessions")
    mode.add_argument("--force-stop", action="store_true", help="stop broker and archive blocking sessions to release software locks; does not stop the robot")
    p.add_argument("--handler", type=Path, help="explicit installed handler.py when automatic discovery is unavailable")
    p.add_argument("--python", help="interpreter for the installed handler")
    a = p.parse_args()
    config_path = a.config.resolve()
    config = json.loads(config_path.read_text())
    root = Path(config["state_dir"])
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Serialize operator commands without interfering with the broker's own lock.
    with (root / "broker-control.lock").open("a") as control:
        fcntl.flock(control, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if a.stop:
            path = root / "state.json"
            data = json.loads(path.read_text()) if path.exists() else {"sessions": {}}
            if any(session_blocks(s) or (s.get("state") == "failed" and s.get("control_lock_pending"))
                   for s in data["sessions"].values()):
                raise SystemExit("Active or unresolved session: use session.cancel/status/reconcile for stop verification first; broker not stopped.")
        pidfile = root / "broker.pid"
        pid = int(pidfile.read_text()) if pidfile.exists() else None
        previous = broker_args(pid, config_path) if pid is not None else None
        # Resolve startup before stopping, so missing installation leaves a live broker intact.
        command = None if (a.stop or a.force_stop) else launch_args(a, config_path, previous)
        stop_broker(pid, config_path)
        with (root / "broker.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            (root / "broker.sock").unlink(missing_ok=True)
            pidfile.unlink(missing_ok=True)
            reset = {} if a.stop else archive_blocking_sessions(
                root, "stop" if a.force_stop else "restart", release=a.force_stop)
        if a.stop or a.force_stop:
            print(json.dumps({"broker": "stopped", "hardware_accessed": False,
                              "session_history_preserved": True, **reset}))
            return
        with (root / "broker-start.log").open("ab") as log:
            proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                    start_new_session=True, close_fds=True)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise SystemExit("Broker startup failed; inspect broker-start.log.")
            try:
                with socket.socket(socket.AF_UNIX) as client:
                    client.settimeout(0.2)
                    client.connect(str(root / "broker.sock"))
                if pidfile.exists() and int(pidfile.read_text()) == proc.pid:
                    print(json.dumps({"broker": "restarted", "pid": proc.pid,
                                      "session_history_preserved": True, "hardware_accessed": False,
                                      **reset}))
                    return
            except (FileNotFoundError, ConnectionRefusedError, socket.timeout):
                pass
            time.sleep(0.1)
        raise SystemExit("Broker startup timed out; inspect broker-start.log (process may still be running).")


if __name__ == "__main__":
    main()
