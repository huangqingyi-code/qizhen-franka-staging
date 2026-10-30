"Linux Edge Adapter entrypoint. Self-test never creates a broker or touches hardware."

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

# Connector uses python -I: only add this immutable installed package directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import MANIFEST, canonical, envelope, load_config, package_fingerprint, validate
from response_budget import bounded_response


def export_artifact(config, artifact_id, offset, count):
    """Private Connector binary channel, separate from Tool JSON responses."""
    from core import Store
    from assets import file_signature

    if not artifact_id.startswith("art_") or not 0 <= offset or not 1 <= count <= 8 * 1024 * 1024:
        raise ValueError("INVALID_ARTIFACT_EXPORT")
    store = Store(config["state_dir"])
    p = store.artifact(artifact_id)
    record = store.data["artifacts"][artifact_id]
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        stat = os.fstat(stream.fileno())
        signature = [stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]
        if signature != record["_signature"] or offset > stat.st_size:
            raise ValueError("ARTIFACT_CHANGED")
        stream.seek(offset)
        remaining = min(count, stat.st_size - offset)
        while remaining:
            block = stream.read(min(remaining, 1024 * 1024))
            if not block:
                raise ValueError("ARTIFACT_CHANGED")
            sys.stdout.buffer.write(block)
            remaining -= len(block)
        if file_signature(p) != signature:
            raise ValueError("ARTIFACT_CHANGED")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--session-events", action="store_true")
    p.add_argument("--invoke")
    p.add_argument("--serve", action="store_true")
    p.add_argument("--export-artifact")
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--count", type=int, default=8 * 1024 * 1024)
    p.add_argument("--config", type=Path, default=Path.home() / ".config/qizhen-franka/config.json")
    a = p.parse_args()
    if a.self_test:
        from jsonschema import Draft202012Validator

        from layout import adapter_manual

        if not adapter_manual().read_text(encoding="utf-8").strip():
            raise ValueError("EMPTY_RELEASE_MANUAL")
        for op in MANIFEST["operations"]:
            Draft202012Validator.check_schema(op["input_schema"])
            Draft202012Validator.check_schema(op["output_schema"])
        print(
            canonical(
                {"ok": True, "operations": len(MANIFEST["operations"]), "hardware_accessed": False}
            )
        )
        return
    config = load_config(a.config)
    if a.session_events:
        parameters = json.loads(sys.stdin.read(8193))
        request = {"kind": "session_events", "parameters": parameters,
                   "config_hash": package_fingerprint(config)}
        with socket.socket(socket.AF_UNIX) as connection:
            connection.settimeout(20)
            # Event readers never start a Broker or any device task.
            connection.connect(str(Path(config["state_dir"]) / "broker.sock"))
            connection.sendall((canonical(request) + "\n").encode())
            with connection.makefile("rb") as stream:
                result = json.loads(stream.readline(1024 * 1024 + 1))
        if set(result) != {"events"}:
            raise ValueError("SESSION_EVENTS_UNAVAILABLE")
        print(canonical(result))
        return
    if a.export_artifact:
        export_artifact(config, a.export_artifact, a.offset, a.count)
        return
    if a.serve:
        from broker import serve

        serve(config)
        return
    backend = config["backend"]
    try:
        parameters = json.loads(sys.stdin.read(1024 * 1024 + 1))
        validate(a.invoke, parameters)
        request = {
            "operation_id": a.invoke,
            "parameters": parameters,
            "config_hash": package_fingerprint(config),
        }
        root = Path(config["state_dir"])
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        sock = root / "broker.sock"

        def connect():
            c = socket.socket(socket.AF_UNIX)
            c.settimeout(15)
            try:
                c.connect(str(sock))
            except Exception:
                c.close()
                raise
            return c

        try:
            c = connect()
        except (FileNotFoundError, ConnectionRefusedError):
            with (root / "broker-start.log").open("ab") as log:
                subprocess.Popen(
                    [
                        sys.executable,
                        "-I",
                        str(Path(__file__).resolve()),
                        "--serve",
                        "--config",
                        str(a.config),
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=log,
                    start_new_session=True,
                    close_fds=True,
                )
            c = None
            for _ in range(50):
                try:
                    c = connect()
                    break
                except (FileNotFoundError, ConnectionRefusedError):
                    time.sleep(0.1)
            if c is None:
                raise ValueError(
                    "BROKER_START_FAILED; inspect owner-local broker-start.log"
                ) from None
        with c:
            c.sendall((canonical(request) + "\n").encode())
            with c.makefile("rb") as f:
                b = f.readline(1024 * 1024 + 1)
        result = json.loads(b)
    except Exception as ex:
        result = envelope(
            backend, error={"code": "ADAPTER_REQUEST_FAILED", "message": str(ex)[:2000]}
        )
    print(canonical(bounded_response(result)))


if __name__ == "__main__":
    main()
