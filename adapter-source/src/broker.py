"Owner-local Unix socket broker; persistent PTYs outlive individual tool calls."

import errno
import fcntl
import json
import os
import pty
import re
import select
import signal
import socketserver
import subprocess
import threading
import time
from pathlib import Path
from uuid import uuid4

from assets import read_artifact
from response_budget import artifact_page, bounded_response
from layout import Workspace
from stop_guard import requires_stop_check, session_blocks, verify_stopped
from task_files import import_task, list_tasks, read_manual

from core import (
    FCI,
    MOTION,
    OPERATIONS,
    MANIFEST,
    PACKAGE,
    TERMINAL,
    Store,
    canonical,
    command,
    create_task,
    envelope,
    now,
    package_fingerprint,
    plot_shape,
    shape_extract,
    shell_launch,
    validate,
)

SESSION_REVISION_MAX = OPERATIONS["franka.session.status"]["output_schema"]["properties"]["data"]["properties"]["session_revision"]["maximum"]


def prompt_actions(operation, text):
    "Recognize only documented prompts; home and delta never wait for input."
    if operation not in {"franka.ribbon.run", "franka.pipeline.start"}:
        return None
    # The native leveling pause uses prose rather than slash-separated choices.
    # Require its complete current prompt, so history and partial PTY reads do
    # not expose actions before input is actually requested.
    current_line = text.replace("\r", "").rstrip().rsplit("\n", 1)[-1]
    leveling_pause = re.fullmatch(
        r"处理完成输入\s+RESUME\s+重新测量；输入\s+QUIT\s+退出"
        r"(?P<skip>；人工检查确认调平可接受后输入\s+SKIP，记为成功并更新规划初始位姿)?"
        r"[：:]",
        current_line,
    )
    if leveling_pause:
        return ["RESUME", "SKIP", "QUIT"] if leveling_pause.group("skip") else ["RESUME", "QUIT"]
    if operation == "franka.pipeline.start" and (
        re.search(r"HOME\s*[/／]\s*RELEVEL\s*[/／]\s*QUIT", text)
        or (re.search(r"(?:^|\n)\s*HOME\s+", text)
            and re.search(r"(?:^|\n)\s*RELEVEL\s+", text)
            and re.search(r"(?:^|\n)\s*QUIT\b", text))
    ):
        return ["HOME", "RELEVEL", "QUIT"]
    pause = re.search(r"RESUME\s*[/／]\s*(?:(SKIP)\s*[/／]\s*)?QUIT", text)
    if pause:
        return ["RESUME", "SKIP", "QUIT"] if pause.group(1) else ["RESUME", "QUIT"]
    if operation == "franka.pipeline.start" and re.search(
        r"(输入\s*MOVE|(?:enter|type|input)\s+[\"\']?MOVE|最终.*MOVE)", text, re.I
    ):
        return ["MOVE"]
    return None


class ReceiptError(ValueError):
    def __init__(self, message, data):
        super().__init__(message)
        self.data = data


def failed_lock_resolved(s):
    """Preserve a completed stop check, including explicit reader-unavailable release."""
    return (s.get("state") == "failed" and not s.get("control_lock_pending")
            and (s.get("physical_stop_verified") is True
                 or (s.get("stop_verification") or {}).get("state_unavailable") is True))


class Broker:
    def __init__(self, config):
        self.config = config
        self.store = Store(config["state_dir"])
        self.store.backend = config["backend"]
        self.lock = threading.RLock()
        self.events_changed = threading.Condition(self.lock)
        self.live = {}
        self.fingerprint = package_fingerprint(config)
        for s in self.store.data["sessions"].values():
            if s["state"] not in TERMINAL or s["state"] == "unknown":
                self.mark_failure(s, s.get("error") or "BROKER_RESTART_EXECUTION_OUTCOME_UNVERIFIED")
            elif s["state"] == "failed":
                if not requires_stop_check(s):
                    self.mark_failure(s, s.get("error") or "SESSION_FAILED")
                elif not failed_lock_resolved(s):
                    self.mark_failure(s, s.get("error") or "LEGACY_STOP_UNVERIFIED")
                else:
                    s["control_lock_pending"] = False
        self.save()

    def mark_failure(self, s, error):
        required = requires_stop_check(s)
        s.update(state="unknown" if required else "failed", error=error,
                 confirmation=None, physical_stop_verified=False,
                 control_lock_pending=required)
        s["stop_verification"] = {"required": required, "checked_at": now(),
                                  "reason": "stop_unverified" if required else "no_motion_started"}
        if required:
            s["stop_verification"]["verified"] = False

    def refresh_failed_lock(self, s):
        if s["state"] not in {"failed", "unknown"}:
            return
        if not requires_stop_check(s):
            if (s["state"] != "failed" or s.get("control_lock_pending")
                    or (s.get("stop_verification") or {}).get("required") is not False):
                self.mark_failure(s, s.get("error") or "SESSION_FAILED")
                self.save()
            return
        if failed_lock_resolved(s):
            return
        # Persist quarantine before a reader can fail, time out or the broker can exit.
        self.mark_failure(s, s.get("error") or "STOP_UNVERIFIED")
        self.save()
        report = verify_stopped(self.config, s)
        report["required"] = True
        s["stop_verification"] = report
        s["physical_stop_verified"] = report["verified"]
        released = report["verified"] or report.get("state_unavailable") is True
        s["control_lock_pending"] = not released
        s["state"] = "failed" if released else "unknown"
        self.save()

    def refresh_failed_locks(self):
        for s in self.store.data["sessions"].values():
            self.refresh_failed_lock(s)

    def snapshot(self, s, operation=None):
        # The public top-level boundary is declared once in the operation contract.
        fields = OPERATIONS["franka.session.status"]["output_schema"]["properties"]["data"]["properties"]
        result = {key: s[key] for key in fields if key in s}
        artifacts = result.get("artifacts", [])
        page, next_offset = artifact_page(artifacts, 0, 50, budget=256 * 1024)
        result["session_revision"] = len(self.store.data.get("session_events", {}).get(s.get("session_id", ""), {}).get("events", []))
        result.update(artifacts=page, artifact_count=len(artifacts),
                      artifacts_next_offset=next_offset,
                      completion_scope="adapter_session")
        if operation in MANIFEST.get("artifact_delivery", {}).get("start_operations", []):
            result["artifact_delivery"] = "1.0"
        detail = result.get("result", {})
        if "_result_is_large" not in s:
            s["_result_is_large"] = len(canonical(detail).encode()) > 131072
        if s["_result_is_large"]:
            receipt = detail.get("receipt", {})
            if "_result_summary" not in s:
                s["_result_summary"] = {k: detail[k] for k in (
                    "exit_code", "hardware_motion_verified", "run_result_artifact_id",
                    "capture_completed", "force_capture_completed") if k in detail}
                s["_result_summary"].update(details_truncated=True,
                    result_artifact_id=s.get("result_artifact_id"),
                    receipt_summary={k: receipt[k] for k in ("status", "mode", "outcome", "initial_state_source") if k in receipt})
            result["result"] = s["_result_summary"]
        return result

    def save(self):
        # State and durable events are written by the same atomic Store.save.
        events = self.store.data.setdefault("session_events", {})
        for sid, session in self.store.data["sessions"].items():
            if not isinstance(session.get("session_id"), str):
                continue  # Preserve legacy quarantine records without inventing a session identity.
            snapshot = self.snapshot(session)
            signature = canonical({k: snapshot.get(k) for k in (
                "state", "confirmation", "error", "result", "finished_at",
                "physical_stop_verified", "control_lock_pending")})
            journal = events.setdefault(sid, {"signature": None, "events": []})
            if journal["signature"] != signature:
                revision = len(journal["events"]) + 1
                output = json.loads(canonical(bounded_response(envelope(self.config["backend"], snapshot))))
                output["data"]["session_revision"] = revision
                journal["events"].append({"revision": revision, "output": output})
                journal["signature"] = signature
        self.store.save()
        # All production callers already hold the Broker lock; construction does not.
        with self.events_changed:
            self.events_changed.notify_all()

    def session_events(self, request):
        if set(request) != {"session_id", "after", "max_wait_seconds"}:
            raise ValueError("INVALID_SESSION_EVENTS_REQUEST")
        sid, after, seconds = request["session_id"], request["after"], request["max_wait_seconds"]
        if type(after) is not int or not 0 <= after <= SESSION_REVISION_MAX or type(seconds) is not int or not 0 <= seconds <= 15:
            raise ValueError("INVALID_SESSION_EVENTS_CURSOR")
        with self.events_changed:
            if sid not in self.store.data["sessions"]:
                raise ValueError("UNKNOWN_SESSION")
            def page():
                records = self.store.data.get("session_events", {}).get(sid, {}).get("events", [])
                selected = []
                for event in records:
                    if event["revision"] > after:
                        if selected and len(canonical({"events": selected + [event]}).encode()) > 480 * 1024:
                            break
                        selected.append(event)
                        if len(selected) == 100:
                            break
                return selected
            if not page() and seconds:
                self.events_changed.wait_for(lambda: bool(page()), timeout=seconds)
            return {"events": page()}

    def verify_unresolved(self, stop):
        while not stop.wait(5):
            with self.lock:
                for session in self.store.data["sessions"].values():
                    if session["state"] == "unknown" and session.get("control_lock_pending"):
                        self.refresh_failed_lock(session)

    def blocked(self):
        return next((s for s in self.store.data["sessions"].values()
                     if s["operation_id"] in FCI and session_blocks(s)), None)

    def prompt(self, s, actions, text):
        s["state"] = "waiting_confirmation"
        s["confirmation"] = {
            "confirmation_id": "confirm_" + uuid4().hex,
            "actions": actions,
            "prompt": text[-16000:],
            "hardware_confirmation_required": self.config["backend"] == "real",
        }
        self.save()

    def finish(self, s, code, data, error=None):
        s["exit_code"] = code
        s["result"] = data
        s["confirmation"] = None
        if s["state"] != "cancelled":
            if error is None and s["state"] in {"failed", "unknown"}:
                error = s.get("error") or "EXECUTION_OUTCOME_UNVERIFIED"
            if error is not None:
                self.mark_failure(s, error)
            else:
                s.update(state="succeeded", control_lock_pending=False)
        if s["state"] == "cancelled" and not requires_stop_check(s):
            s.update(control_lock_pending=False, physical_stop_verified=False,
                     stop_verification={"required": False, "checked_at": now(),
                                        "reason": "no_motion_started"})
        s["error"] = error
        s["finished_at"] = now()
        result_path = Path(s["directory"]) / "adapter_result.json"
        serialized = canonical(data)
        result_path.write_text(serialized)
        s["_result_is_large"] = len(serialized.encode()) > 131072
        s.pop("_result_summary", None)
        s["result_artifact_id"] = self.store.register(result_path, s["session_id"])
        if s["_result_is_large"]:
            # The full receipt is immutable in adapter_result.json, not duplicated
            # into state.json and reread by every binary-export subprocess.
            s["result"] = self.snapshot(s)["result"]
        s["artifact_index"] = {"state": "generating", "pending_count": None}
        self.save()
        if error is not None:
            self.refresh_failed_lock(s)

    def invoke(self, op, a):
        with self.lock:
            validate(op, a)
            if op in FCI or op == "franka.ribbon.measure" or op == "franka.session.reconcile":
                self.refresh_failed_locks()
            key = a.get("request_id")
            frozen = canonical({"operation": op, "parameters": a})
            if key in self.store.data["requests"]:
                prior = self.store.data["requests"][key]
                if prior["input"] != frozen:
                    raise ValueError("REQUEST_ID_REUSED_WITH_DIFFERENT_INPUT")
                if prior.get("session_id"):
                    return self.snapshot(self.store.data["sessions"][prior["session_id"]], op)
                return prior["result"]
            if op == "franka.doctor":
                paths = Workspace(self.config).checks(self.config)
                result = {
                    "backend": self.config["backend"],
                    "hardware_accessed": False,
                    "checks": [{"path": str(p), "exists": p.is_file()} for p in paths],
                    "ready": self.config["backend"] == "mock"
                    or all(Path(p).is_file() for p in paths),
                    "operations": len(OPERATIONS),
                    "workspace_layout": "ribbon_ws_20261018",
                }
            elif op == "franka.task.create":
                result = create_task(self.store, self.config, a)
            elif op == "franka.task.list":
                result = list_tasks(self.config, a)
            elif op == "franka.task.import":
                result = import_task(self.store, self.config, a)
            elif op == "franka.manual.read":
                result = read_manual(self.config, a)
            elif op == "franka.artifact.read":
                result = read_artifact(self.store, a)
            elif op == "franka.shape.extract":
                result = shape_extract(self.store, a["artifact_id"])
            elif op == "franka.shape.plot":
                result = plot_shape(self.store, a["artifact_id"])
            elif op.startswith("franka.session."):
                s = self.store.data["sessions"][a["session_id"]]
                if op == "franka.session.status":
                    self.refresh_failed_lock(s)
                    result = self.snapshot(s, op)
                elif op == "franka.session.artifacts":
                    offset, limit = a.get("offset", 0), a.get("limit", 50)
                    records = s.get("artifacts", [])
                    page, next_offset = artifact_page(records, offset, limit)
                    result = {"session_id": s["session_id"], "artifacts": page,
                              "artifact_index": s.get("artifact_index", {"state": "generating"}),
                              "offset": offset, "total": len(records),
                              "next_offset": next_offset}
                elif op == "franka.session.respond":
                    pending = s.get("confirmation")
                    if (
                        s["state"] != "waiting_confirmation"
                        or not pending
                        or pending["confirmation_id"] != a["confirmation_id"]
                        or a["action"] not in pending["actions"]
                    ):
                        raise ValueError("STALE_OR_INVALID_CONFIRMATION")
                    action = a["action"]
                    s["confirmation"] = None
                    s["state"] = "running"
                    s["prompt_epoch"] = s.get("prompt_epoch", 0) + 1
                    if self.config["backend"] == "mock":
                        from mock_backend import respond

                        respond(self, s, action)
                    else:
                        fd, proc = self.live[s["session_id"]]
                        if proc.poll() is not None:
                            raise ValueError("PROCESS_ALREADY_EXITED")
                        os.write(fd, (action + "\n").encode())
                    result = self.snapshot(s, op)
                elif op == "franka.session.cancel":
                    if s["state"] not in TERMINAL:
                        s.update(
                            state="cancelling", confirmation=None, physical_stop_verified=False
                        )
                        if self.config["backend"] == "mock":
                            s.update(state="cancelled", error=None, finished_at=now())
                        else:
                            live = self.live.get(s["session_id"])
                            proc = live[1] if live else None
                            if proc is not None and proc.poll() is None:
                                os.killpg(proc.pid, signal.SIGINT)
                    result = self.snapshot(s, op)
                else:
                    if s["state"] not in {"failed", "unknown"}:
                        raise ValueError("RECONCILE_ONLY_FAILED_OR_UNKNOWN_SESSION")
                    if session_blocks(s):
                        raise ValueError("STOP_NOT_VERIFIED: " + str(s.get("stop_verification", {})))
                    result = self.snapshot(s, op)
            else:
                if op == "franka.pipeline.render_videos":
                    source = self.store.data["sessions"][a["source_session_id"]]
                    if session_blocks(source):
                        raise ValueError("VIDEO_SOURCE_NOT_RESOLVED")
                    if self.blocked() or any(s["operation_id"] == op and session_blocks(s)
                                             for s in self.store.data["sessions"].values()):
                        raise ValueError("VIDEO_RENDER_BUSY")
                elif op in FCI and any(s["operation_id"] == "franka.pipeline.render_videos" and session_blocks(s)
                                       for s in self.store.data["sessions"].values()):
                    raise ValueError("VIDEO_RENDER_BUSY")
                if op in FCI and self.blocked():
                    raise ValueError("FCI_BUSY_OR_STOP_UNVERIFIED: " + self.blocked()["session_id"])
                # Shared calibration history needs a separate lock even measure does not use FCI.
                if op in {
                    "franka.ribbon.measure",
                    "franka.ribbon.run",
                    "franka.pipeline.start",
                } and any(
                    s["operation_id"]
                    in {"franka.ribbon.measure", "franka.ribbon.run", "franka.pipeline.start"}
                    and session_blocks(s)
                    for s in self.store.data["sessions"].values()
                ):
                    raise ValueError("RIBBON_SESSION_BUSY")
                sid = "session_" + uuid4().hex
                directory = self.store.root / sid
                directory.mkdir(mode=0o700)
                # Validate all handle mappings before launching even in Mock mode.
                argv, timeout = command(self.config, self.store, op, a, directory)
                s = {
                    "session_id": sid,
                    "operation_id": op,
                    "state": "running",
                    "backend": self.config["backend"],
                    "simulated": self.config["backend"] == "mock",
                    "started_at": now(),
                    "started_unix": time.time(),
                    "directory": str(directory),
                    "argv": argv,
                    "parameters": a,
                    "confirmation": None,
                    "log_tail": "",
                    "artifacts": [],
                    "result": {},
                    "exit_code": None,
                    "physical_stop_verified": False,
                    "control_lock_pending": False,
                    "error": None,
                }
                self.store.data["sessions"][sid] = s
                if key:
                    self.store.data["requests"][key] = {"input": frozen, "session_id": sid}
                self.save()  # Durable identity before any process can start.
                if self.config["backend"] == "mock":
                    from mock_backend import start

                    start(self, s)
                else:
                    # Freeze input identities, but do not invent an input prompt.
                    # Native terminal output alone may request confirmation.
                    if op in {"franka.home", "franka.delta.move", "franka.offline.execute"}:
                        paths = set(argv)
                        if op == "franka.offline.execute":
                            trajectory = self.store.artifact(a["trajectory_artifact_id"])
                            paths.update({str(trajectory), str(trajectory) + ".ribbon_guard"})
                        s["frozen_artifacts"] = [aid for aid, record in self.store.data["artifacts"].items()
                                                 if record["path"] in paths]
                    threading.Thread(target=self.run_real, args=(s, timeout), daemon=True).start()
                result = self.snapshot(s, op)
            if key and key not in self.store.data["requests"]:
                self.store.data["requests"][key] = {"input": frozen, "result": result}
            if op not in {"franka.session.status", "franka.session.artifacts", "franka.artifact.read",
                          "franka.manual.read", "franka.task.list", "franka.doctor"}:
                self.save()
            if isinstance(result, dict) and "session_id" in result and "state" in result:
                result["session_revision"] = len(self.store.data.get("session_events", {}).get(
                    result["session_id"], {}).get("events", []))
            return result

    def receipt(self, s, code):
        "Only interpret this invocation's outputs; never equate exit 0 with movement."
        op = s["operation_id"]
        directory = Path(s["directory"])
        log = (directory / "terminal.log").read_text(errors="replace")
        data = {
            "exit_code": code,
            "terminal_output": log[-16000:],
            "hardware_motion_verified": False,
        }
        parsed = []
        for line in log.splitlines():
            try:
                v = json.loads(line)
                if isinstance(v, dict):
                    parsed.append(v)
            except ValueError:
                pass
        # Some programs pretty-print JSON.
        if not parsed:
            try:
                v = json.loads(log.strip())
                if isinstance(v, dict):
                    parsed.append(v)
            except ValueError:
                pass
        if parsed:
            data["native_reports"] = parsed
        if op == "franka.pipeline.start":
            refs = [v.get("result") for v in parsed if isinstance(v.get("result"), str)]
            if not refs:
                raise ValueError("PIPELINE_RECEIPT_MISSING")
            p = self.store.owned(refs[-1])
            if not p.is_relative_to(directory.resolve()):
                raise ValueError("PIPELINE_RECEIPT_OUTSIDE_SESSION")
            r = json.loads(p.read_text())
            data["receipt"] = r
            data["run_result_artifact_id"] = self.store.register(p, s.get("session_id"))
            data["native_error"] = r.get("error")
            if r.get("mode") != s["parameters"]["mode"]:
                raise ReceiptError("PIPELINE_MODE_MISMATCH", data)
            allowed = {
                "plan": {"planned"},
                "prepare": {"offline_checks_passed"},
                "execute": {"executed_without_capture", "executed_and_captured"},
            }
            if (
                code != 0
                or r.get("status") != "succeeded"
                or r.get("outcome") not in allowed[s["parameters"]["mode"]]
            ):
                native = r.get("error")
                message = native.get("code") if isinstance(native, dict) else native
                raise ReceiptError("PIPELINE_NOT_SUCCESSFUL: " + str(message or r.get("outcome")), data)
            capture_requested = r.get("outcome") == "executed_and_captured"
            data.update(capture_completed=False, force_capture_completed=False)
            for channel, filename, field in [("capture", "capture_result.json", "capture_completed"),
                                             ("force_capture", "force_result.json", "force_capture_completed")]:
                if not capture_requested:
                    continue
                info = r.get(channel)
                disabled = isinstance(info, dict) and info.get("status") == "disabled"
                enabled = not disabled and (isinstance(info, dict) or
                    (channel == "capture" and capture_requested and "force_capture" not in r))
                if not enabled:
                    continue
                capture_path = self.store.owned(p.parent / filename)
                try:
                    capture = json.loads(capture_path.read_text())
                except (OSError, ValueError) as error:
                    raise ReceiptError(channel.upper() + "_RECEIPT_INVALID: " + str(error), data) from error
                samples = capture.get("sample_count")
                if capture.get("completed") is not True or isinstance(samples, bool) or not isinstance(samples, int) or samples < 2:
                    raise ReceiptError(channel.upper() + "_INCOMPLETE", data)
                files = capture.get("files")
                if not isinstance(files, list) or not files:
                    raise ReceiptError(channel.upper() + "_FILES_MISSING", data)
                for name in files:
                    if not isinstance(name, str) or Path(name).is_absolute():
                        raise ReceiptError(channel.upper() + "_FILE_INVALID", data)
                    try:
                        captured_file = self.store.owned(p.parent / name)
                    except ValueError as error:
                        raise ReceiptError(channel.upper() + "_FILE_INVALID", data) from error
                    if not captured_file.is_relative_to(p.parent) or not captured_file.is_file() or captured_file.stat().st_size == 0:
                        raise ReceiptError(channel.upper() + "_FILE_INVALID", data)
                start, end = r.get("execution_started_at"), r.get("execution_finished_at")
                if isinstance(start, (float, int)) and isinstance(end, (float, int)):
                    first, last = capture.get("first_frame_unix"), capture.get("last_frame_unix")
                    if not isinstance(first, (float, int)) or not isinstance(last, (float, int)) or first > start or last < end:
                        raise ReceiptError(channel.upper() + "_COVERAGE_INCOMPLETE", data)
                data[field] = True
                data["capture_receipt" if channel == "capture" else "force_capture_receipt"] = capture
                if channel == "force_capture":
                    status_path = self.store.owned(p.parent / "force_status.json")
                    status = json.loads(status_path.read_text()) if status_path.is_file() else {}
                    combined = {**info, **status, **capture}
                    data["force_measurement"] = {k: combined[k] for k in ("calibrated", "units", "nonzero_status_count") if k in combined}
                    data["force_measurement"]["usable_force_values"] = (
                        combined.get("calibrated") is True and isinstance(combined.get("units"), list)
                        and len(combined["units"]) == 6 and combined["units"][:3] == ["N"] * 3
                        and all(u in {"N·m", "N*m", "N-m"} for u in combined["units"][3:])
                        and combined.get("nonzero_status_count", 0) == 0)
            if capture_requested and not (data["capture_completed"] or data["force_capture_completed"]):
                raise ReceiptError("PIPELINE_CAPTURE_OUTCOME_INCONSISTENT", data)
            data["hardware_motion_verified"] = s["parameters"]["mode"] == "execute"
        elif op == "franka.pipeline.render_videos":
            report = directory / "render_result.json"
            if not report.is_file():
                raise ValueError("VIDEO_RENDER_REPORT_MISSING")
            data["render_report"] = json.loads(report.read_text())
            data["scientific_evidence"] = False
        elif op in {"franka.home", "franka.offline.execute", "franka.offline.validate"}:
            # Native offline audit path is fixed by vendor; accept ONLY an exact
            # freshly created receipt path printed by this invocation, never latest-directory scans.
            if op.startswith("franka.offline."):
                candidates = re.findall(
                    r"(/[A-Za-z0-9_./-]+(?:result\.json|offline_[A-Za-z0-9_/-]+))", log
                )
                audit = Workspace(self.config).audit.resolve()
                for value in candidates:
                    p = Path(value)
                    if p.is_dir():
                        p = p / "result.json"
                    if (
                        not p.resolve().is_relative_to(audit)
                        or p.is_symlink()
                        or not p.is_file()
                        or p.stat().st_mtime < s["started_unix"] - 0.001
                    ):
                        continue
                    # Read only exact receipt, do not expose its external paths.
                    target = directory / "native_result.json"
                    target.write_bytes(p.read_bytes())
            receipts = [
                p
                for p in directory.rglob("*.json")
                if p.name in {"result.json", "native_result.json"}
            ]
            if not receipts:
                raise ValueError("NATIVE_RECEIPT_MISSING")
            r = json.loads(receipts[-1].read_text())
            data["receipt"] = r
            if not r.get("success"):
                raise ValueError("NATIVE_REPORTED_FAILURE")
            if op == "franka.offline.execute" and (
                r.get("dry_run") is not False
                or r.get("mock") is not False
                or r.get("ribbon_guard") is not True
            ):
                raise ValueError("OFFLINE_REAL_EXECUTION_NOT_VERIFIED")
            data["hardware_motion_verified"] = (
                bool(r.get("moved")) if op == "franka.home" else op == "franka.offline.execute"
            )
        elif op == "franka.delta.move":
            if "MOTION_DONE_NS" not in log:
                raise ValueError("MOTION_COMPLETION_MARKER_MISSING")
            data["hardware_motion_verified"] = True
        elif op == "franka.state.read":
            if not parsed:
                raise ValueError("STATE_JSON_MISSING")
            r = parsed[-1]
            for k, n in [("q", 7), ("dq", 7), ("O_T_EE", 16)]:
                v = r.get(k)
                if (
                    not isinstance(v, list)
                    or len(v) != n
                    or any(
                        isinstance(x, bool)
                        or not isinstance(x, (int, float))
                        or not __import__("math").isfinite(x)
                        for x in v
                    )
                ):
                    raise ValueError("INVALID_ROBOT_STATE")
            if "robot_mode" not in r:
                raise ValueError("ROBOT_MODE_MISSING")
            data["robot_state"] = r
        if op == "franka.nokov.monitor" and s.get("monitor_duration_completed") and code in {0, 130, -signal.SIGINT}:
            data["duration_completed"] = True
            return data
        if code and not (op == "franka.ribbon.analyze" and code == 1):
            raise ValueError("PROCESS_EXIT_" + str(code))
        if op == "franka.ribbon.analyze":
            data["criteria_done"] = code == 0
        return data

    def run_real(self, s, timeout):
        fd = None
        proc = None
        try:
            with self.lock:
                if s["state"] == "cancelling":
                    s["state"] = "cancelled"
                    self.finish(s, 130, {"started": False})
                    return
                # Recheck managed inputs immediately before starting the child.
                # Removing the synthetic MOVE must not remove hash validation.
                for aid in s.get("frozen_artifacts", []):
                    self.store.artifact(aid)
                master, slave = pty.openpty()
                fd = master
            with self.lock:
                if s["state"] == "cancelling":
                    os.close(slave)
                    s["state"] = "cancelled"
                    self.finish(s, 130, {"started": False})
                    return
                launcher = [
                    __import__("sys").executable,
                    "-I",
                    str(PACKAGE / "vendor_launch.py"),
                    str(os.getpid()),
                    *shell_launch(self.config, s["argv"]),
                ]
                proc = subprocess.Popen(
                    launcher,
                    stdin=slave,
                    stdout=slave,
                    stderr=slave,
                    start_new_session=True,
                    close_fds=True,
                    env={
                        "PATH": "/usr/local/bin:/usr/bin:/bin",
                        "HOME": str(Path.home()),
                        "LANG": "C.UTF-8",
                        "PYTHONDONTWRITEBYTECODE": "1",
                        "ROS_LOG_DIR": str(self.store.root / "ros-logs"),
                        "MPLCONFIGDIR": str(self.store.root / "matplotlib"),
                        "XDG_CACHE_HOME": str(self.store.root / "cache"),
                    },
                )
                os.close(slave)
                s["process_id"] = proc.pid
                # Only the artifact indexer uses this identity to wait for renderers.
                # Existing stop/unlock rules deliberately remain unchanged.
                from artifact_index import process_fields
                try:
                    s["artifact_producer"] = {"pid": proc.pid, "start_tick": int(process_fields(proc.pid)[19])}
                except FileNotFoundError:
                    pass
                self.live[s["session_id"]] = (master, proc)
                self.save()
            deadline = time.monotonic() + timeout
            pending = ""
            last_signature = None
            epoch = 0
            logpath = Path(s["directory"]) / "terminal.log"
            with logpath.open("wb") as log:
                while True:
                    if time.monotonic() > deadline:
                        if s["operation_id"] == "franka.nokov.monitor":
                            s["monitor_duration_completed"] = True
                            if proc.poll() is None:
                                os.killpg(proc.pid, signal.SIGINT)
                            break
                        with self.lock:
                            self.mark_failure(s, "SESSION_TIMEOUT")
                            self.save()
                        if proc.poll() is None:
                            os.killpg(proc.pid, signal.SIGINT)
                        # A fresh stop check applies the stop/unavailable release policy.
                        break
                    ready, _, _ = select.select([master], [], [], 0.1)
                    if ready:
                        try:
                            b = os.read(master, 8192)
                        except OSError as ex:
                            if ex.errno == errno.EIO:
                                b = b""
                            else:
                                raise
                        if b:
                            log.write(b)
                            log.flush()
                            pending = (pending + b.decode("utf-8", errors="replace"))[-32000:]
                            with self.lock:
                                if s.get("prompt_epoch", 0) != epoch:
                                    epoch = s.get("prompt_epoch", 0)
                                    pending = b.decode("utf-8", errors="replace")
                                    last_signature = None
                                s["log_tail"] = pending[-16000:]
                                # Search the recent prompt, not historical tokens or echoed input.
                                actions = None
                                tail = pending[-4000:]
                                actions = prompt_actions(s["operation_id"], tail)
                                signature = (actions, tail) if actions else None
                                if (
                                    actions
                                    and signature != last_signature
                                    and s["state"] == "running"
                                ):
                                    last_signature = signature
                                    self.prompt(s, actions, tail)
                                self.save()
                        if not b and proc.poll() is not None:
                            break
                    if proc.poll() is not None and not ready:
                        break
                    with self.lock:
                        # After a response, remove the old prompt before a fresh MOVE.
                        if s["state"] == "running" and last_signature is not None:
                            pending = ""
                            last_signature = None
            code = proc.wait(timeout=5)
            with self.lock:
                if s["state"] in {"failed", "unknown", "cancelling"}:
                    self.finish(s, code,
                                {"exit_code": code, "hardware_motion_verified": False},
                                s.get("error") or "CANCELLED_STOP_CHECK_REQUIRED")
                else:
                    try:
                        data = self.receipt(s, code)
                        self.finish(s, code, data)
                    except ReceiptError as ex:
                        self.finish(s, code, ex.data, str(ex))
                    except (ValueError, KeyError, OSError) as ex:
                        self.finish(
                            s, code, {"exit_code": code, "hardware_motion_verified": False}, str(ex)
                        )
        except Exception as ex:
            with self.lock:
                # A failure after Popen may have occurred after partial movement.
                self.finish(s, proc.poll() if proc else None,
                            {"started": proc is not None}, "PROCESS_ERROR: " + str(ex))
        finally:
            if fd is not None:
                os.close(fd)
            with self.lock:
                # Do not forget a still-running controller after timeout/error.
                if proc is None or proc.poll() is not None:
                    self.live.pop(s["session_id"], None)
                elif (s["state"] in {"failed", "unknown"} and requires_stop_check(s)
                      and s.get("physical_stop_verified") is not True):
                    self.mark_failure(s, s.get("error") or "STOP_UNVERIFIED")
                    self.save()
                self.refresh_failed_lock(s)


def serve(config):
    root = Path(config["state_dir"])
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = (root / "broker.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    sock = root / "broker.sock"
    sock.unlink(missing_ok=True)
    broker = Broker(config)
    from artifact_index import ArtifactIndexer

    indexer = ArtifactIndexer(broker)
    indexer.start()
    stop_verifier = threading.Event()
    verifier = threading.Thread(target=broker.verify_unresolved, args=(stop_verifier,), daemon=True)
    verifier.start()

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            self.connection.settimeout(20)
            try:
                b = self.rfile.readline(1024 * 1024 + 1)
                if len(b) > 1024 * 1024:
                    raise ValueError("MESSAGE_TOO_LARGE")
                req = json.loads(b)
                if req["config_hash"] != broker.fingerprint:
                    raise ValueError("CONFIG_CHANGED_RESTART_BROKER_AFTER_SESSIONS_END")
                if req.get("kind") == "session_events":
                    result = broker.session_events(req["parameters"])
                else:
                    result = envelope(
                        config["backend"], broker.invoke(req["operation_id"], req["parameters"])
                    )
            except Exception as ex:
                result = envelope(
                    config["backend"],
                    error={"code": "ADAPTER_REQUEST_FAILED", "message": str(ex)[:2000]},
                )
            self.wfile.write((canonical(bounded_response(result)) + "\n").encode())

    with socketserver.ThreadingUnixStreamServer(str(sock), Handler) as server:
        os.chmod(sock, 0o600)
        pidfile = root / "broker.pid.tmp"
        pidfile.write_text(str(os.getpid()))
        pidfile.replace(root / "broker.pid")
        try:
            server.serve_forever()
        finally:
            indexer.stop_event.set()
            stop_verifier.set()
