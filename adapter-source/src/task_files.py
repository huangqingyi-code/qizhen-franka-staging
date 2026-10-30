"""Read-only manual/task discovery and immutable imports into Adapter-owned storage."""

import hashlib
import json
import subprocess
from pathlib import Path
from uuid import uuid4

from assets import sha256_file
from layout import Workspace

MAX_TASK_BYTES = 2 * 1024 * 1024


def task_path(config, value, directory=False):
    root = Workspace(config).tasks.resolve()
    supplied = Path(value)
    path = (supplied if supplied.is_absolute() else root / supplied).resolve()
    if not path.is_relative_to(root):
        raise ValueError("TASK_PATH_OUTSIDE_TRAJECTORIES")
    if directory:
        if not path.is_dir():
            raise ValueError("TASK_DIRECTORY_MISSING")
    elif path.suffix.lower() not in {".yaml", ".yml"} or not path.is_file():
        raise ValueError("EXPECTED_TASK_YAML")
    elif path.stat().st_size > MAX_TASK_BYTES:
        raise ValueError("TASK_FILE_EXCEEDS_TWO_MIB")
    return path


def list_tasks(config, args):
    directory = task_path(config, args.get("subdirectory", ""), directory=True)
    paths = sorted((p for p in directory.iterdir() if p.suffix.lower() in {".yaml", ".yml"}), key=lambda p: p.name)
    offset, limit = args.get("offset", 0), args.get("limit", 100)
    tasks = []
    for candidate in paths[offset:offset + limit]:
        try:
            path = task_path(config, str(candidate))
            tasks.append({"task_path": str(path), "bytes": path.stat().st_size,
                          "sha256": sha256_file(path), "scientific_evidence": False})
        except ValueError as error:
            tasks.append({"task_path": str(candidate), "available": False, "error": str(error)})
    return {"tasks": tasks, "offset": offset, "total": len(paths),
            "next_offset": offset + limit if offset + limit < len(paths) else None,
            "scientific_evidence": False}


def parse_task_yaml(config, content):
    # YAML is already a dependency of the vendor ROS tools. Do not require it in
    # Connector's Python, import arbitrary task modules, or invoke robot tools.
    program = (
        "import json,sys,yaml; d=yaml.safe_load(sys.stdin.read()); "
        "assert isinstance(d,dict), 'TASK_YAML_MUST_BE_MAPPING'; "
        "print(json.dumps(d,allow_nan=False))"
    )
    completed = subprocess.run([config["python_executable"], "-c", program],
                               input=content.decode("utf-8"), capture_output=True,
                               text=True, timeout=10, check=False)
    if completed.returncode:
        raise ValueError("TASK_YAML_INVALID: " + completed.stderr[-1000:])
    if len(completed.stdout.encode()) > 4 * MAX_TASK_BYTES:
        raise ValueError("EXPANDED_TASK_YAML_TOO_LARGE")
    result = json.loads(completed.stdout)
    if not isinstance(result, dict):
        raise ValueError("TASK_YAML_MUST_BE_MAPPING")
    return result


def import_task(store, config, args):
    source = task_path(config, args["task_path"])
    with source.open("rb") as stream:
        content = stream.read(MAX_TASK_BYTES + 1)
    if len(content) > MAX_TASK_BYTES:
        raise ValueError("TASK_FILE_EXCEEDS_TWO_MIB")
    digest = hashlib.sha256(content).hexdigest()
    expected = args.get("expected_sha256", digest).removeprefix("sha256:")
    if digest != expected:
        raise ValueError("TASK_SOURCE_HASH_MISMATCH")
    task = parse_task_yaml(config, content)
    if task.get("start_state_source") == "live":
        raise ValueError("RIBBON_LIVE_START_FORBIDDEN")
    if "start_state_file" in task and "start_state" in task:
        raise ValueError("CONFLICTING_START_STATE")
    shared, snapshot = None, None
    if "start_state_file" in task:
        reference = task["start_state_file"]
        if not isinstance(reference, str):
            raise ValueError("INVALID_START_STATE_FILE")
        shared = Workspace(config).start_pose.resolve()
        # Match the gateway contract: relative task paths are rooted at trajectories.
        path = Path(reference)
        if not path.is_absolute():
            raise ValueError("IMPORTED_TASK_START_FILE_MUST_BE_ABSOLUTE")
        path = path.resolve()
        if path != shared:
            raise ValueError("IMPORTED_TASK_START_FILE_NOT_SHARED_POSE")
        snapshot = shared.read_bytes()
    tid = "task_" + uuid4().hex
    directory = store.root / tid
    directory.mkdir(mode=0o700)
    target = directory / "task.yaml"
    target.write_bytes(content)
    record = {"artifact_id": store.register(target), "scene_artifact_id": None,
              "source_path": str(source), "source_sha256": digest,
              "source_start_pose_artifact_id": None}
    if snapshot is not None:
        pose = directory / "imported_start_pose.yaml"
        pose.write_bytes(snapshot)
        record.update(source_start_pose_artifact_id=store.register(pose),
                      shared_start_path=str(shared),
                      shared_start_sha256=hashlib.sha256(snapshot).hexdigest())
    store.data["tasks"][tid] = record
    return {"task_id": tid, **record, "validated": "yaml_mapping_only",
            "hardware_validated": False, "scientific_evidence": False}


def read_manual(config, args):
    workspace = Workspace(config)
    path = workspace.manual
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError("MANUAL_MUST_BE_RELEASE_OWNED")
    content = path.read_bytes()
    if len(content) > 4 * MAX_TASK_BYTES:
        raise ValueError("MANUAL_TOO_LARGE")
    lines = content.decode("utf-8").splitlines(keepends=True)
    start = args.get("start_line", 1) - 1
    selected, byte_count = [], 0
    for line in lines[start:start + args.get("max_lines", 200)]:
        count = len(line.encode("utf-8"))
        if byte_count + count > 65536:
            if not selected:
                raise ValueError("MANUAL_LINE_EXCEEDS_PAGE_LIMIT")
            break
        selected.append(line)
        byte_count += count
    end = start + len(selected)
    return {"document": path.name, "version": next((l.strip() for l in lines[:10] if l.startswith("版本")), None),
            "sha256": hashlib.sha256(content).hexdigest(), "start_line": start + 1,
            "total_lines": len(lines), "lines_returned": len(selected), "content": "".join(selected),
            "next_line": end + 1 if end < len(lines) else None}
