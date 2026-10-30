"""Operator-only configuration; never called by the Agent and never connects hardware."""

import argparse
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--backend", choices=["real"], required=True)
    p.add_argument("--workspace", type=Path, default=Path("/home/zhaoyunzyq/ribbon_ws"))
    p.add_argument("--state-dir", type=Path, default=Path.home() / ".local/share/qizhen-franka")
    p.add_argument("--ros-setup", type=Path, default=Path("/opt/ros/humble/setup.bash"))
    p.add_argument("--python-executable", type=Path, default=Path("/usr/bin/python3"))
    p.add_argument("--robot-ip", default="172.16.0.3")
    p.add_argument("--nokov-server", default="10.1.1.198")
    a = p.parse_args()
    import ipaddress

    ipaddress.ip_address(a.robot_ip)
    ipaddress.ip_address(a.nokov_server)
    for path in (a.workspace, a.state_dir, a.ros_setup, a.python_executable):
        if not path.is_absolute():
            raise SystemExit("all configuration paths must be absolute")
    config = {
        "backend": a.backend,
        "workspace": str(a.workspace),
        "state_dir": str(a.state_dir),
        "ros_setup": str(a.ros_setup),
        "python_executable": str(a.python_executable),
        "robot_ip": a.robot_ip,
        "nokov_server": a.nokov_server,
    }
    folder = Path.home() / ".config/qizhen-franka"
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = folder / "config.json"
    if path.exists() and json.loads(path.read_text()) != config:
        old = json.loads(path.read_text())
        if (Path(old["state_dir"]) / "broker.sock").exists():
            raise SystemExit(
                "Stop the owner-local broker with broker_control.py after sessions finish before changing config."
            )
    path.write_text(json.dumps(config, indent=2) + "\n")
    path.chmod(0o600)
    print(json.dumps({"config": str(path), "backend": a.backend, "hardware_accessed": False}))


if __name__ == "__main__":
    main()
