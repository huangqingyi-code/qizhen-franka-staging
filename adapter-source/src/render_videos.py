"""Offline video rendering on a private copy; never launch motion or capture tools."""

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from assets import file_signature, sha256_file
from layout import Workspace


def run_child(argv, *, env, log, timeout):
    process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                               env=env, start_new_session=True)
    previous = {}

    def forward(signum, _frame):
        if process.poll() is None:
            os.killpg(process.pid, signum)
        raise KeyboardInterrupt

    for signum in (signal.SIGINT, signal.SIGTERM):
        previous[signum] = signal.signal(signum, forward)
    try:
        return process.wait(timeout=timeout)
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGINT)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def copy_run(source, target):
    source = source.resolve()
    target.mkdir(mode=0o700)
    allowed = {".json", ".yaml", ".yml", ".csv", ".ribbon_guard"}
    for path in source.rglob("*"):
        relative = path.relative_to(source)
        # Saved trajectories/markers are inputs; old simulations and rendered
        # outputs must never satisfy this session's generation checks.
        if relative.parts[0] in {"simulation", "videos"}:
            continue
        if path.is_symlink():
            raise ValueError("VIDEO_SOURCE_CONTAINS_SYMLINK")
        if path.is_file() and path.suffix.lower() in allowed:
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
    # Vendor renderers consume the saved receipt. Keep its input metadata, but
    # redirect paths to the private copy and remove prior video/result pointers.
    receipt = target / "result.json"
    document = json.loads(receipt.read_text())
    for key in ("simulation_source", "simulation_video", "simulation_video_warning",
                "ribbon_video_preview", "ribbon_video_warning"):
        document.pop(key, None)
    def relocate(value):
        if isinstance(value, dict):
            return {key: relocate(item) for key, item in value.items()}
        if isinstance(value, list):
            return [relocate(item) for item in value]
        if isinstance(value, str) and value.startswith(str(source) + "/"):
            return str(target.resolve()) + value[len(str(source)):]
        return value

    receipt.write_text(json.dumps(relocate(document), ensure_ascii=False))


def read_object(path):
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("INVALID_VIDEO_RECEIPT_OBJECT")
    return document


def video_metadata(path, native):
    # Only this attempt's fixed output can become a downloadable video.
    if path.is_symlink() or not path.is_file() or path.stat().st_size <= 0:
        raise ValueError("VIDEO_FILE_MISSING_OR_EMPTY")
    if "path" in native:
        if not isinstance(native["path"], str) or Path(native["path"]).resolve() != path.resolve():
            raise ValueError("VIDEO_RECEIPT_PATH_MISMATCH")
    before = file_signature(path)
    digest = sha256_file(path)
    after = file_signature(path)
    if after != before:
        raise ValueError("VIDEO_CHANGED_DURING_HASH")
    return {"path": str(path), "sha256": digest, "size_bytes": after[1],
            "scientific_evidence": False}


def render(workspace, source, directory, kind):
    layout = Workspace({"workspace": str(workspace)})
    receipt = source / "result.json"
    original_hash = sha256_file(receipt)
    target = directory / "render_input"
    copy_run(source, target)
    env = {**os.environ, "MPLBACKEND": "Agg", "PYTHONDONTWRITEBYTECODE": "1"}
    kinds = ["simulation", "ribbon"] if kind == "all" else [kind]
    reports = {}
    for item in kinds:
        try:
            with (directory / (item + "_render.log")).open("ab") as log:
                if item == "simulation":
                    # The vendor post-hoc helper still assumes its old install/
                    # layout. Invoke the native simulator with the current ROS
                    # environment instead, without patching the vendor workspace.
                    partition = "qizhen_video_" + uuid4().hex
                    simulation_env = {**env, "ROS_DOMAIN_ID": "83", "ROS_LOCALHOST_ONLY": "1",
                                      "IGN_PARTITION": partition, "GZ_PARTITION": partition}
                    simulation = target / "simulation"
                    simulation.mkdir(exist_ok=True)
                    code = run_child([sys.executable, str(layout.tools / "sim_replay.py"),
                                      str(target / "trajectory.csv"), "--output-dir", str(simulation),
                                      "--video", "--replay-timeout", "300"],
                                     env=simulation_env, log=log, timeout=600)
                    if code:
                        raise ValueError("NATIVE_GAZEBO_REPLAY_FAILED")
                    native = read_object(simulation / "summary.json").get("video")
                    if not isinstance(native, dict) or native.get("status") != "ok":
                        status = native.get("status") if isinstance(native, dict) else "invalid"
                        raise ValueError("NATIVE_GAZEBO_VIDEO_UNAVAILABLE: " + str(status))
                    reports[item] = {"status": "ready", "generation": "fresh_simulation_replay",
                        **video_metadata(simulation / "gazebo_review.mp4", native)}
                    continue
                # 2026-10-20: pipeline 默认只生成 HTML；补录工具显式要求两个 MP4。
                command = [sys.executable, str(layout.tools / "pipeline_videos.py"),
                           "--run-dir", str(target), "--kind", item]
                if item == "ribbon":
                    command.append("--ribbon-videos")
                command += ["--end-mode", "markers"]
                code = run_child(command, env=env, log=log, timeout=900)
                report = target / "videos/render_manifest.json"
                if code or not report.is_file():
                    raise ValueError("NATIVE_VIDEO_RENDER_FAILED")
                videos = read_object(report).get("videos")
                native = videos.get(item) if isinstance(videos, dict) else None
                if not isinstance(native, dict):
                    raise ValueError("INVALID_NATIVE_VIDEO_ENTRY")
                if native.get("status") not in ("ready", "partial"):
                    raise ValueError("NATIVE_RIBBON_VIDEO_UNAVAILABLE: " +
                                     str(native.get("error", native.get("status"))))
                reports[item] = {**native, "generation": "fresh_marker_render",
                                 **video_metadata(target / "videos/ribbon_fit.mp4", native)}
        except (ValueError, OSError, subprocess.SubprocessError) as error:
            reports[item] = {"status": "unavailable", "error": str(error)[:1024], "scientific_evidence": False}
    if sha256_file(receipt) != original_hash:
        raise ValueError("SOURCE_RECEIPT_CHANGED_DURING_RENDER")
    result = {"state": "completed", "videos": reports, "scientific_evidence": False,
              "generation_policy": "fresh_outputs_per_session",
              "source_receipt_sha256": original_hash, "source_receipt_unchanged": True,
              "posthoc_replay_is_original_validation": False, "hardware_calls": False}
    (directory / "render_result.json").write_text(json.dumps(result, ensure_ascii=False))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--kind", choices=["simulation", "ribbon", "all"], default="all")
    args = parser.parse_args()
    print(json.dumps(render(args.workspace, args.source, args.output_dir, args.kind)))


if __name__ == "__main__":
    main()
