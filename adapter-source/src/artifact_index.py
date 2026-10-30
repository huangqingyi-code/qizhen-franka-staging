"""Background artifact discovery. File I/O and hashing never hold the Broker lock."""

import threading
import mimetypes
import os
from pathlib import Path

from assets import file_signature, sha256_file
from core import TERMINAL

SUFFIXES = {".json", ".csv", ".yaml", ".yml", ".log", ".ribbon_guard", ".svg",
            ".mp4", ".png", ".html", ".txt", ".webm"}


def process_fields(pid):
    return (Path("/proc") / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()


def group_has_producers(producer):
    """Read-only artifact finalization check, unrelated to control-lock release."""
    if not producer:
        return False
    pid = producer["pid"]
    try:
        if int(process_fields(pid)[19]) != producer["start_tick"]:
            return False  # An unrelated process reused the old leader PID.
    except FileNotFoundError:
        pass  # Children can still render after their parent has exited.
    try:
        os.killpg(pid, 0)  # Existence probe only; sends no signal.
    except ProcessLookupError:
        return False
    for entry in Path("/proc").iterdir():
        if entry.name.isdigit():
            try:
                fields = process_fields(entry.name)
                if int(fields[2]) == pid and fields[0] != "Z":
                    return True
            except (FileNotFoundError, ProcessLookupError, PermissionError):
                continue
    return False


class ArtifactIndexer:
    def __init__(self, broker):
        self.broker = broker
        self.seen = {}
        self.legacy_seen = {}
        self.legacy_checked = {}
        self.closed_producers = set()
        self.quiet_producers = {}
        self.stop_event = threading.Event()

    def warm_legacy(self):
        b = self.broker
        with b.lock:
            legacy = [(aid, dict(record)) for aid, record in b.store.data["artifacts"].items()
                      if not record.get("_signature")]
        changed = False
        digests = {}
        for aid, record in legacy:
            try:
                path = b.store.owned(record["path"])
                sig = file_signature(path)
                previous = self.legacy_seen.get(aid)
                self.legacy_seen[aid] = sig
                if previous != sig or self.legacy_checked.get(aid) == sig:
                    continue
                cache_key = (str(path), tuple(sig))
                if cache_key not in digests:
                    digests[cache_key] = sha256_file(path)
                digest = digests[cache_key]
                if file_signature(path) != sig:
                    continue
                self.legacy_checked[aid] = sig
                if digest != record["sha256"]:
                    continue
                with b.lock:
                    current = b.store.data["artifacts"].get(aid)
                    if current and current["sha256"] == digest and current["path"] == str(path):
                        current["_signature"] = sig
                        changed = True
            except (OSError, ValueError):
                continue
        if changed:
            with b.lock:
                b.save()

    def scan(self):
        self.warm_legacy()
        b = self.broker
        with b.lock:
            sessions = [(s["session_id"], s["directory"], s["state"], s.get("artifact_producer"))
                        for s in b.store.data["sessions"].values()]
            known = {v["path"]: (k, dict(v)) for k, v in b.store.data["artifacts"].items()}
        for sid, directory, state, producer in sessions:
            ready, generating, pending, error = [], [], 0, None
            producing = True
            try:
                producer_key = (sid, producer.get("pid"), producer.get("start_tick")) if producer else None
                if producer_key in self.closed_producers:
                    producing = False
                else:
                    producing = group_has_producers(producer)
                    if producer_key:
                        if producing:
                            self.quiet_producers[producer_key] = 0
                        elif self.quiet_producers.get(producer_key, 0):
                            self.closed_producers.add(producer_key)
                        else:
                            self.quiet_producers[producer_key] = 1
                            producing = True  # Require two observations before finalizing renderers.
                # Directory walks, stat and streaming hashes all happen without b.lock.
                for p in sorted(Path(directory).rglob("*")):
                    if p.suffix.lower() not in SUFFIXES or p.is_symlink() or not p.is_file():
                        continue
                    p = b.store.owned(p)
                    sig = file_signature(p)
                    previous = self.seen.get((sid, str(p)))
                    self.seen[(sid, str(p))] = sig
                    old = known.get(str(p))
                    if old and old[1].get("_signature") == sig:
                        ready.append((p, sig, old[1]["sha256"]))
                    elif state not in TERMINAL or producing or previous != sig:
                        pending += 1
                        generating.append({"state": "generating", "name": p.name,
                            "mime_type": mimetypes.guess_type(p.name)[0] or "application/octet-stream",
                            "size_bytes": sig[1], "relative_path": str(p.relative_to(directory))})
                    else:
                        digest = sha256_file(p)
                        if file_signature(p) != sig:
                            pending += 1
                            generating.append({"state": "generating", "name": p.name,
                                "mime_type": mimetypes.guess_type(p.name)[0] or "application/octet-stream",
                                "size_bytes": sig[1], "relative_path": str(p.relative_to(directory))})
                        else:
                            ready.append((p, sig, digest))
            except (OSError, ValueError) as ex:
                error = str(ex)[:500]
            with b.lock:
                s = b.store.data["sessions"].get(sid)
                if not s or s["directory"] != directory:
                    continue
                records = []
                for p, sig, digest in ready:
                    try:
                        if file_signature(p) != sig:
                            pending += 1
                            continue
                        aid = b.store.register_hashed(p, sid, sig, digest)
                        records.append({"artifact_id": aid, "state": "ready",
                            **{k: v for k, v in b.store.data["artifacts"][aid].items()
                               if k not in {"path", "_signature"}},
                            "relative_path": str(p.relative_to(directory))})
                    except OSError:
                        pending += 1
                ready_count = len(records)
                records.extend(generating)
                index = {"state": "failed" if error else
                    "ready" if state in TERMINAL and s["state"] in TERMINAL and not pending and not producing else "generating",
                    "pending_count": pending, "ready_count": ready_count, "error": error}
                if s.get("artifacts") != records or s.get("artifact_index") != index:
                    s["artifacts"], s["artifact_index"] = records, index
                    b.save()

    def run(self):
        while not self.stop_event.is_set():
            try:
                self.scan()
            except Exception:
                # A transient filesystem failure must not terminate discovery.
                pass
            self.stop_event.wait(2)

    def start(self):
        self.thread = threading.Thread(target=self.run, name="artifact-index", daemon=True)
        self.thread.start()
