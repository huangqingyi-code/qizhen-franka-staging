"""Read-only stop checks; unavailable state may release a lock without proving stop."""

import json
import math
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

TERMINAL = {"succeeded", "failed", "cancelled", "unknown"}
MOTION = {"franka.delta.move", "franka.home", "franka.ribbon.run",
          "franka.pipeline.start", "franka.offline.execute"}
# Values from this deployment's libfranka/include/franka/robot_state.h.
STOPPED_MODES = {1, 4, 5}  # Idle, Reflex, UserStopped; no automatic recovery.
VELOCITY_TOLERANCE = 1e-2  # rad/s, every joint and every sample
POSITION_TOLERANCE = 1e-4  # rad, maximum sampled range per joint
SAMPLES = 2
SAMPLE_INTERVAL = 0.25


def requires_stop_check(s):
    """Only broker-owned facts can prove that this session never commanded motion."""
    if s.get("backend") == "mock":
        return False
    operation = s.get("operation_id")
    if not isinstance(operation, str) or not operation.startswith("franka."):
        return True
    if operation not in MOTION:
        return False
    result = s.get("result") or {}
    if result.get("started") is False:
        return False
    parameters = s.get("parameters") or {}
    return not (
        s.get("operation_id") == "franka.pipeline.start"
        and parameters.get("mode") in {"plan", "prepare"}
        and parameters.get("skip_leveling") is True
    )


def session_blocks(s):
    # Broker normalizes legacy failed+pending records to unknown before serving.
    # Neither an old caller assertion nor a software restart releases unknown.
    if s["state"] == "unknown":
        return True
    if s["state"] == "failed":
        return False
    if s["state"] not in TERMINAL:
        return True
    return bool(s.get("control_lock_pending", False))


def read_snapshot(config):
    reader = Path(config["workspace"]) / "libfranka/build/examples/read_franka_state"
    result = subprocess.run(
        [str(reader), config["robot_ip"]], stdin=subprocess.DEVNULL,
        capture_output=True, text=True, timeout=2, check=True,
    )
    return json.loads(result.stdout)


def verify_stopped(config, s):
    """Use robot samples only; execution-process lifetime does not gate unlocking."""
    report = {"verified": False, "checked_at": datetime.now(timezone.utc).isoformat(),
              "samples": [], "state_unavailable": False,
              "velocity_tolerance_rad_s": VELOCITY_TOLERANCE,
              "position_tolerance_rad": POSITION_TOLERANCE}
    try:
        for index in range(SAMPLES):
            if index:
                time.sleep(SAMPLE_INTERVAL)
            try:
                state = read_snapshot(config)
            except (OSError, ValueError, IndexError, TypeError, subprocess.SubprocessError):
                # Reading/parsing failed: release the software lock by policy,
                # while keeping verified=False and the original reader error.
                # A returned but invalid/moving sample never takes this branch.
                report["state_unavailable"] = True
                raise
            if not isinstance(state, dict):
                raise ValueError("INVALID_ROBOT_STATE")
            mode = state.get("robot_mode")
            if isinstance(mode, bool) or not isinstance(mode, int) or mode not in STOPPED_MODES:
                raise ValueError("ROBOT_MODE_NOT_STOPPED")
            for name in ("q", "dq"):
                values = state.get(name)
                if not isinstance(values, list) or len(values) != 7 or any(
                    isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                    for v in values
                ):
                    raise ValueError("INVALID_ROBOT_STATE_" + name.upper())
            report["samples"].append({"robot_mode": mode, "q": state["q"], "dq": state["dq"]})
            if any(abs(v) > VELOCITY_TOLERANCE for v in state["dq"]):
                raise ValueError("ROBOT_STILL_MOVING")
        for joint in range(7):
            positions = [v["q"][joint] for v in report["samples"]]
            if max(positions) - min(positions) > POSITION_TOLERANCE:
                raise ValueError("ROBOT_POSITION_NOT_STABLE")
        report["verified"] = True
    except (OSError, ValueError, IndexError, TypeError, subprocess.SubprocessError) as ex:
        report["error"] = str(ex)[:1000]
    return report
