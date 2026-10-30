"Validated Franka API mapping. Caller inputs never become shell commands or paths."

import csv
import hashlib
import json
import math
import mimetypes
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from jsonschema import Draft202012Validator

from assets import file_signature, sha256_file
from layout import Workspace, adapter_manual
from stop_guard import MOTION, TERMINAL

PACKAGE = Path(__file__).resolve().parent
MANIFEST = json.loads((PACKAGE / "adapter.json").read_text())
OPERATIONS = {v["operation_id"]: v for v in MANIFEST["operations"]}
RIBBON_MARKER_SET = "ribbon_1021"
FCI = {
    "franka.state.read",
    "franka.delta.preview",
    "franka.delta.move",
    "franka.home",
    "franka.ribbon.run",
    "franka.pipeline.start",
    "franka.offline.execute",
}



def now():
    return datetime.now(UTC).isoformat()


def canonical(v):
    return json.dumps(v, sort_keys=True, separators=(",", ":"), allow_nan=False)


def envelope(backend, data=None, error=None):
    return {
        "schema_version": "1.0",
        "backend": backend,
        "simulated": backend == "mock",
        "ok": error is None,
        "sampled_at": now(),
        "data": data or {},
        "error": error,
    }


def validate(operation, args):
    if operation not in OPERATIONS:
        raise ValueError("UNKNOWN_OPERATION")
    canonical(args)  # Reject nonfinite values, including unknown nested values.
    Draft202012Validator(OPERATIONS[operation]["input_schema"]).validate(args)
    if operation.startswith("franka.delta."):
        if any(abs(v) > 0.03 for v in args["translation_m"]):
            raise ValueError("TRANSLATION_EXCEEDS_30_MM_PER_AXIS")
    if operation.startswith("franka.delta.") and args.get("align_ribbon_up"):
        if any(v != 0 for v in args["translation_m"]) or args.get("rotation_deg", 0) != 0:
            raise ValueError("ALIGN_RIBBON_UP_REQUIRES_ZERO_TRANSLATION_AND_ROTATION")
        if args.get("duration_seconds", 2) < 2:
            raise ValueError("ALIGN_RIBBON_UP_DURATION_BELOW_2_SECONDS")
    if operation == "franka.pipeline.start" and args.get("planning_domain", 81) == args.get(
        "simulation_domain", 82
    ):
        raise ValueError("ROS_DOMAINS_MUST_DIFFER")
    if operation == "franka.pipeline.start":
        if args.get("skip_leveling") and args["mode"] == "execute":
            raise ValueError("EXECUTE_CANNOT_SKIP_LEVELING")
    if operation == "franka.task.create":
        t = args["task"]
        for w in t["waypoints"]:
            if w["position"][0] < 0:
                raise ValueError("RIBBON_NEGATIVE_X_TARGET")
            fields = set(w) & {
                "rotation",
                "orientation_xyzw",
                "orientation_rpy_deg",
                "orientation_axes",
            }
            if len(fields) > 1 or (
                fields and w.get("keep_orientation", t.get("keep_orientation", False))
            ):
                raise ValueError("CONFLICTING_ORIENTATION")
            if (
                "orientation_xyzw" in w
                and abs(math.sqrt(sum(v * v for v in w["orientation_xyzw"])) - 1) > 0.01
            ):
                raise ValueError("QUATERNION_NOT_UNIT")
            if "orientation_axes" in w:
                a, b = (w["orientation_axes"][k] for k in ("x_axis", "z_axis"))
                na, nb = math.sqrt(sum(v * v for v in a)), math.sqrt(sum(v * v for v in b))
                if (
                    not na
                    or not nb
                    or abs(sum(x * y for x, y in zip(a, b, strict=True)) / (na * nb)) > 0.0001
                ):
                    raise ValueError("AXES_NOT_ORTHOGONAL")
        ids = set()
        for box in t.get("scene", {}).get("boxes", []):
            if box["id"] in ids or any(v <= 0 for v in box["size"]):
                raise ValueError("INVALID_SCENE_BOX")
            ids.add(box["id"])
            if (
                "orientation_xyzw" in box
                and abs(math.sqrt(sum(v * v for v in box["orientation_xyzw"])) - 1) > 0.01
            ):
                raise ValueError("SCENE_QUATERNION_NOT_UNIT")


def load_config(path):
    c = json.loads(path.read_text())
    required = {
        "backend",
        "state_dir",
        "workspace",
        "ros_setup",
        "python_executable",
        "robot_ip",
        "nokov_server",
    }
    if set(c) != required or c["backend"] not in {"real", "mock"}:
        raise ValueError("INVALID_LOCAL_CONFIG")
    for k in ("state_dir", "workspace", "ros_setup", "python_executable"):
        if not isinstance(c[k], str) or not Path(c[k]).is_absolute():
            raise ValueError("CONFIG_PATH_MUST_BE_ABSOLUTE: " + k)
    import ipaddress

    for k in ("robot_ip", "nokov_server"):
        ipaddress.ip_address(c[k])
    # There is no implicit fallback from real to mock.
    if c["backend"] == "mock" and not (PACKAGE / "mock_backend.py").is_file():
        raise ValueError("MOCK_BACKEND_NOT_IN_PRODUCTION_PACKAGE")
    return c


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)
        self.backend = None
        self.path = self.root / "state.json"
        self.data = (
            json.loads(self.path.read_text())
            if self.path.exists()
            else {"sessions": {}, "tasks": {}, "artifacts": {}, "requests": {}}
        )
        self._artifact_keys = {(v["path"], v["sha256"]): k
                               for k, v in self.data["artifacts"].items()}

    def save(self):
        p = self.path.with_suffix(".tmp")
        p.write_text(canonical(self.data))
        os.chmod(p, 0o600)
        with p.open("rb") as f:
            os.fsync(f.fileno())
        p.replace(self.path)
        directory = os.open(self.root, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    def owned(self, path):
        p = Path(path)
        resolved = p.resolve()
        if not resolved.is_relative_to(self.root) or any(
            v.is_symlink() for v in [p, *p.parents] if v != self.root.parent
        ):
            raise ValueError("ARTIFACT_OUTSIDE_OWNED_DIRECTORY")
        return resolved

    def register(self, path, session_id=None):
        p = self.owned(path)
        if not p.is_file():
            raise ValueError("ARTIFACT_MISSING")
        signature = file_signature(p)
        for k, v in self.data["artifacts"].items():
            if v["path"] == str(p) and v.get("_signature") == signature:
                return k
        digest = sha256_file(p)
        if signature != file_signature(p):
            raise ValueError("ARTIFACT_CHANGED_DURING_READ")
        return self.register_hashed(p, session_id, signature, digest)

    def register_hashed(self, p, session_id, signature, digest):
        existing = self._artifact_keys.get((str(p), digest))
        if existing:
            self.data["artifacts"][existing].update(_signature=signature, name=p.name,
                size_bytes=signature[1], mime_type=mimetypes.guess_type(p.name)[0] or "application/octet-stream")
            return existing
        aid = "art_" + uuid4().hex
        self.data["artifacts"][aid] = {
            "path": str(p),
            "sha256": digest,
            "session_id": session_id,
            "name": p.name,
            "size_bytes": p.stat().st_size,
            "backend": self.backend,
            "mime_type": mimetypes.guess_type(p.name)[0] or "application/octet-stream",
            "_signature": signature,
        }
        self._artifact_keys[(str(p), digest)] = aid
        return aid

    def artifact(self, aid):
        v = self.data["artifacts"][aid]
        p = self.owned(v["path"])
        signature = file_signature(p)
        if signature != v.get("_signature"):
            raise ValueError("ARTIFACT_CHANGED")
        return p

    def task(self, tid):
        record = self.data["tasks"][tid]
        if record.get("shared_start_sha256"):
            if sha256_file(Path(record["shared_start_path"])) != record["shared_start_sha256"]:
                raise ValueError("IMPORTED_START_POSE_CHANGED_REIMPORT_TASK")
        return self.artifact(self.data["tasks"][tid]["artifact_id"])

    def source_run(self, session_id):
        s = self.data["sessions"][session_id]
        if s["operation_id"] != "franka.pipeline.start" or s["state"] not in TERMINAL:
            raise ValueError("SOURCE_PIPELINE_MUST_BE_TERMINAL")
        aid = s.get("result", {}).get("run_result_artifact_id")
        if not aid:
            candidates = [v["artifact_id"] for v in s.get("artifacts", [])
                          if v.get("artifact_id") and v["name"] == "result.json"
                          and v.get("relative_path", "").count("/") <= 1]
            if len(candidates) != 1:
                raise ValueError("SOURCE_PIPELINE_RECEIPT_MISSING_OR_AMBIGUOUS")
            aid = candidates[0]
        receipt = self.artifact(aid)
        directory = self.owned(s["directory"])
        if not receipt.is_relative_to(directory):
            raise ValueError("SOURCE_PIPELINE_RECEIPT_OUTSIDE_SESSION")
        return receipt.parent

    def collect(self, s):
        ids = []
        for p in sorted(Path(s["directory"]).rglob("*")):
            if (
                p.is_file()
                and not p.is_symlink()
                and p.suffix.lower() in {".json", ".csv", ".yaml", ".yml", ".log", ".ribbon_guard", ".svg", ".mp4", ".png", ".html", ".txt", ".webm"}
            ):
                try:
                    ids.append(self.register(p, s["session_id"]))
                except FileNotFoundError:
                    continue  # A live producer may atomically replace a status file.
                except ValueError as error:
                    if str(error) != "ARTIFACT_CHANGED_DURING_READ":
                        raise
        s["artifacts"] = [
            {
                "artifact_id": k,
                **{a: b for a, b in self.data["artifacts"][k].items() if a not in {"path", "_signature"}},
                "relative_path": str(Path(self.data["artifacts"][k]["path"]).relative_to(s["directory"])),
            }
            for k in ids
        ]


def create_task(store, config, args):
    tid = "task_" + uuid4().hex
    d = store.root / tid
    d.mkdir(mode=0o700)
    t = dict(args["task"])
    scene = t.pop("scene", None)
    t.update(
        ribbon_task=True,
        frame_id="base",
        end_effector_link="fer_ribbon_tcp",
        position_reference="start",
        start_state_source="declared",
        require_start_state=True,
        x_floor={"link": "fer_ribbon_tcp", "minimum": "start"},
    )
    if "start_state" not in t:
        t["start_state_file"] = str(
            Workspace(config).start_pose
        )
    p = d / "task.yaml"
    p.write_text(
        json.dumps(t, ensure_ascii=False, allow_nan=False, indent=2)
    )  # JSON is a YAML subset.
    v = {"artifact_id": store.register(p), "scene_artifact_id": None}
    if scene:
        p = d / "scene.yaml"
        p.write_text(json.dumps(scene))
        v["scene_artifact_id"] = store.register(p)
    store.data["tasks"][tid] = v
    return {"task_id": tid, **v, "validated": "adapter_schema_only", "hardware_validated": False}


def shape_extract(store, aid):
    p = store.artifact(aid)
    frames = {}
    with p.open(newline="") as f:
        for r in csv.DictReader(f):
            if r["source"] != "markerset" or r["set_name"] != RIBBON_MARKER_SET:
                continue
            key = int(r["wall_unix_ns"]), int(r["frame"])
            frame = frames.setdefault(key, {"wall_iso": r["wall_iso"], "points": []})
            xyz = [float(r[k]) for k in ("x_mm", "y_mm", "z_mm")]
            if all(math.isfinite(v) and abs(v) < 1e6 for v in xyz):
                frame["points"].append({"name": r["marker_name"], "xyz_mm": xyz})
    valid = [k for k, v in frames.items() if len(v["points"]) >= 2]
    if not valid:
        raise ValueError("INSUFFICIENT_VISIBLE_POINTS")
    k = max(valid)
    v = frames[k]
    result = {
        "set_name": RIBBON_MARKER_SET,
        "frame": k[1],
        "wall_unix_ns": k[0],
        **v,
        "record_last_frame": max(frames)[1],
        "age_to_record_end_ms": (max(frames)[0] - k[0]) / 1e6,
        "n_visible": len(v["points"]),
        "coordinate_frame": "mocap_world",
        "unit": "mm",
        "base_extrinsic_known": False,
    }
    out = p.with_suffix(".shape.json")
    out.write_text(json.dumps(result, ensure_ascii=False))
    return {**result, "artifact_id": store.register(out)}


def plot_shape(store, aid):
    import html

    d = json.loads(store.artifact(aid).read_text())
    pts = d["points"]
    xyz = list(zip(*(p["xyz_mm"] for p in pts), strict=True))
    center = [(max(a) + min(a)) / 2 for a in xyz]
    span = max(max(a) - min(a) for a in xyz) or 1

    def project(v):
        x, y, z = [(a - b) / span * 450 for a, b in zip(v, center, strict=True)]
        return 450 + 0.8 * x - 0.6 * y, 340 + 0.3 * x + 0.4 * y - 0.85 * z

    lines = [
        (
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'width="900" height="700" viewBox="0 0 90'
            '0 700"><rect width="900" height="700" fi'
            'll="white"/>'
        ),
        ('<text x="30" y="35">Single-frame ribbon markers | Mocap world (mm)</text>'),
    ]
    for j, name in enumerate(("X", "Y", "Z")):
        v = center.copy()
        v[j] += span * 0.55
        x, y = project(v)
        lines.append(
            f'<path d="M450 340 L{x} {y}" stroke="gray"/><text x="{x}" y="{y}">{name} (mm)</text>'
        )
    for p in pts:
        x, y = project(p["xyz_mm"])
        lines.append(
            f'<circle cx="{x}" cy="{y}" r="4" fill="#1677cc"/>'
            f'<text x="{x + 6}" y="{y - 5}" font-size="12">'
            f"{html.escape(p['name'])}</text>"
        )
    lines += [
        f'<text x="30" y="670">frame={d["frame"]} | {html.escape(d["wall_iso"])} |'
        " equal XYZ scale; no inferred topology</text>",
        "</svg>",
    ]
    p = store.artifact(aid).with_suffix(".svg")
    p.write_text("\n".join(lines))
    return {
        "artifact_id": store.register(p),
        "format": "image/svg+xml",
        "projection": "3D oblique; equal axis scale",
        "points_connected": False,
    }


def command(config, store, operation, a, directory):
    workspace = Workspace(config)
    w = workspace.pipeline
    py = config["python_executable"]
    ip = config["robot_ip"]
    level = [py, str(w / "tools/ribbon_level.py"), "--params", str(w / "tools/ribbon_params.yaml")]
    if operation == "franka.state.read":
        return [str(workspace.examples / "read_franka_state"), ip], 30
    if operation.startswith("franka.nokov."):
        mode = operation.rsplit(".", 1)[1]
        v = [
            str(workspace.nokov),
            "--mode",
            mode,
            "--server",
            config["nokov_server"],
        ]
        if mode != "list":
            v += ["--plane", RIBBON_MARKER_SET, "--up-axis", "z"]
        if mode == "record":
            v += [
                "--duration",
                str(a.get("duration_seconds", 2)),
                "--outdir",
                str(directory),
                "--tag",
                "ribbon_shape",
            ]
        return v, a.get("duration_seconds", 2) + 30 if mode == "record" else (
            a.get("duration_seconds", 30) if mode == "monitor" else 30
        )
    if operation == "franka.ribbon.analyze":
        return level + ["analyze", str(store.artifact(a["artifact_id"])), "--json"], 30
    if operation.startswith("franka.ribbon."):
        sub = operation.rsplit(".", 1)[1]
        return level + ["session", sub] + (
            ["--record"] if sub == "measure" else []
        ), 7200 if sub == "run" else 60
    if operation == "franka.home":
        if (
            config["backend"] == "real"
            and "start_pose_artifact_id" in a
            and store.data["artifacts"][a["start_pose_artifact_id"]].get("backend") == "mock"
        ):
            raise ValueError("MOCK_POSE_CANNOT_DRIVE_REAL_HARDWARE")
        pose = (
            store.artifact(a["start_pose_artifact_id"])
            if "start_pose_artifact_id" in a
            else workspace.start_pose
        )
        if "start_pose_artifact_id" not in a:
            frozen_pose = directory / "franka_start_pose.yaml"
            frozen_pose.write_bytes(pose.read_bytes())
            store.register(frozen_pose, directory.name)
            pose = frozen_pose
        if pose.name not in {"franka_start_pose.yaml", "planned_start_pose.yaml"}:
            raise ValueError("EXPECTED_START_POSE_ARTIFACT")
        if pose.name == "planned_start_pose.yaml":
            owner = store.data["artifacts"][a["start_pose_artifact_id"]].get("session_id")
            if not owner or store.data["sessions"][owner]["operation_id"] != "franka.pipeline.start":
                raise ValueError("EXPECTED_PIPELINE_START_POSE_ARTIFACT")
        return [
            "ros2",
            "run",
            "franka_robot_driver",
            "home_pose",
            "--ip",
            ip,
            "--start-pose",
            str(pose),
            "--time-scale",
            str(float(a.get("time_scale", 3))),
            "--min-duration",
            str(float(a.get("min_duration_seconds", 2))),
            "--audit-dir",
            str(directory),
            "--ros-args",
            "-p",
            "automatic_error_recovery:=false",
        ], 1200
    if operation.startswith("franka.delta."):
        v = [
            str(workspace.examples / "cartesian_delta_move"),
            ip,
            *[str(float(x)) for x in a["translation_m"]],
            "--droll-deg",
            str(float(a.get("rotation_deg", 0))),
            "--roll-axis",
            a.get("rotation_axis", "x"),
            "--settle",
            str(float(a.get("settle_seconds", 0.3))),
            "--max-step-mm",
            "30",
        ]
        if a.get("align_ribbon_up"):
            v += ["--align-ribbon-up"]
        if "duration_seconds" in a:
            v += ["--duration", str(float(a["duration_seconds"]))]
        if operation.endswith(".preview"):
            v += ["--dry-run"]
        return v, 660
    if operation == "franka.task.validate":
        scene = store.data["tasks"][a["task_id"]]["scene_artifact_id"]
        program = (
            "import json,sys; from franka_motion_plan"
            "ner.task_config import load_task; d=load"
            "_task(sys.argv[1], sys.argv[2]) if len(s"
            "ys.argv)>2 else load_task(sys.argv[1]); "
            'assert d["ribbon_task"] is True; print(j'
            'son.dumps({"yaml_valid":True,"waypoints"'
            ':len(d["motions"])}))'
        )
        return [py, "-c", program, str(store.task(a["task_id"]))] + (
            [str(store.artifact(scene))] if scene else []
        ), 30
    if operation == "franka.pipeline.start":
        v = [
            py,
            str(w / "tools/run_pipeline.py"),
            "--mode",
            a["mode"],
            "--output-root",
            str(directory),
            "--planning-domain",
            str(a.get("planning_domain", 81)),
            "--simulation-domain",
            str(a.get("simulation_domain", 82)),
        ]
        # Every new invocation plans and simulates in its own output directory.
        v += ["--task", str(store.task(a["task_id"]))]
        scene = store.data["tasks"][a["task_id"]]["scene_artifact_id"]
        if scene:
            v += ["--scene", str(store.artifact(scene))]
        if a.get("skip_leveling"):
            v += ["--skip-leveling"]
        for kind, flag in [("simulation", "video"), ("ribbon", "ribbon-video")]:
            v += ["--" + ("" if a.get("videos", {}).get(kind, True) else "no-") + flag]
        v += ["--force-plot" if a.get("force_plot", True) else "--no-force-plot"]
        total = 7200
        for k, default in [("planning", 1800), ("simulation", 1200), ("execution", 900)]:
            seconds = a.get(k + "_timeout_seconds", default)
            total += seconds
            v += ["--" + k + "-timeout", str(seconds)]
        return v, total
    if operation == "franka.pipeline.render_videos":
        source = store.source_run(a["source_session_id"])
        return [py, str(PACKAGE / "render_videos.py"), "--workspace", str(workspace.root),
                "--source", str(source), "--output-dir", str(directory),
                "--kind", a.get("kind", "all")], 2400
    if operation.startswith("franka.offline."):
        if (
            config["backend"] == "real"
            and store.data["artifacts"][a["trajectory_artifact_id"]].get("backend") == "mock"
        ):
            raise ValueError("MOCK_TRAJECTORY_CANNOT_DRIVE_REAL_HARDWARE")
        p = store.artifact(a["trajectory_artifact_id"])
        if p.name != "trajectory.csv":
            raise ValueError("EXPECTED_THIS_RUN_TRAJECTORY")
        guard = Path(str(p) + ".ribbon_guard")
        matches = [k for k, v in store.data["artifacts"].items() if v["path"] == str(guard)]
        if not matches:
            raise ValueError("RIBBON_GUARD_MISSING")
        store.artifact(matches[-1])
        return [
            "ros2",
            "run",
            "franka_robot_driver",
            "execute_offline",
            "--ros-args",
            "-p",
            "joint_csv:=" + str(p),
            "-p",
            "require_ribbon_guard:=true",
            "-p",
            "time_scale:=" + str(float(a.get("time_scale", 1))),
            "-p",
            "automatic_error_recovery:=false",
            "-p",
            "start_tolerance:=0.01",
            "-p",
            "robot_ip:=" + ip,
            "-p",
            "dry_run:=" + ("true" if operation.endswith(".validate") else "false"),
        ], 660
    raise ValueError("NO_COMMAND_MAPPING")


def package_fingerprint(config):
    h = hashlib.sha256(canonical(config).encode())
    for p in sorted(PACKAGE.iterdir()):
        if p.is_file() and p.suffix in {".py", ".json"}:
            h.update(p.name.encode())
            h.update(p.read_bytes())
    for name in ("AGENT_OPERATIONS.md", "RIBBON.md"):
        manual = adapter_manual().parent / name
        h.update(("docs/" + name).encode())
        h.update(manual.read_bytes())
    return h.hexdigest()


def shell_launch(config, argv):
    # Only this fixed bootstrap uses bash. All variable arguments are positional,
    # quoted by the script, and validated operator configuration or generated argv.
    script = (
        'set -e; source "$1"; source "$2/ros/install/'
        'setup.bash"; cd "$2/pipeline"; export PYTHONPATH='
        '"$2/ros/src/franka_motion_planner${PYTHONPAT'
        'H:+:$PYTHONPATH}"; shift 2; exec "$@"'
    )
    return [
        "/bin/bash",
        "-c",
        script,
        "franka-bootstrap",
        config["ros_setup"],
        config["workspace"],
        *argv,
    ]
