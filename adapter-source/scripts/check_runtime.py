#!/usr/bin/env python3
"""Read-only deployment preflight; never start broker, ROS, device tools or sudo."""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from layout import Workspace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path.home() / ".config/qizhen-franka/config.json")
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    paths = Workspace(config).checks(config)
    checks = [{"path": str(path), "exists": path.is_file(), "readable": os.access(path, os.R_OK)} for path in paths]
    report = {"ok": all(item["exists"] and item["readable"] for item in checks),
              "hardware_accessed": False, "workspace_layout": "ribbon_ws_20261018", "checks": checks,
              "state_dir": config["state_dir"], "state_dir_exists": Path(config["state_dir"]).is_dir()}
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
