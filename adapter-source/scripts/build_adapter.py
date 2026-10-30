#!/usr/bin/env python3
"Build immutable architecture-specific packages from the one contract source."

import argparse
import hashlib
import json
import re
import shutil
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build(root, output, architecture, version=None, reuse_existing=False):
    if architecture != "amd64":
        raise ValueError("This deployment supports amd64 only")
    manifest = json.loads((root / "adapter.json").read_text())
    manifest_version = manifest["version"]
    if not isinstance(manifest_version, str) or not re.fullmatch(
        r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", manifest_version
    ):
        raise ValueError("adapter.json version must be MAJOR.MINOR.PATCH")
    if version is not None and version != manifest_version:
        raise ValueError("--version must match adapter.json version; update the contract first")
    manuals = [root / "docs" / name for name in ("AGENT_OPERATIONS.md", "RIBBON.md")]
    for manual in manuals:
        if not manual.is_file() or manual.is_symlink() or not manual.read_text(encoding="utf-8").strip():
            raise ValueError("Release requires a nonempty docs/" + manual.name)
    dst = output / f"franka-ribbon-{manifest_version}-{architecture}.tar.gz"
    checksum = dst.with_suffix(dst.suffix + ".sha256")
    if reuse_existing and (dst.exists() or checksum.exists()):
        if not dst.is_file() or not checksum.is_file():
            raise ValueError("Existing release is incomplete; package and checksum are both required")
        digest = "sha256:" + hashlib.sha256(dst.read_bytes()).hexdigest()
        if checksum.read_text().strip() != digest:
            raise ValueError("Existing package checksum mismatch; release refused")
        expected_manifest = dict(manifest)
        expected_manifest["runtime_requirements"] = {
            **manifest["runtime_requirements"], "architecture": architecture
        }
        expected_sources = {
            "franka-ribbon/" + p.name: p.read_bytes()
            for p in (root / "src").glob("*.py")
        }
        for manual in manuals:
            expected_sources["franka-ribbon/docs/" + manual.name] = manual.read_bytes()
        try:
            with tarfile.open(dst) as tar:
                members = tar.getmembers()
                names = [m.name for m in members]
                expected_names = set(expected_sources) | {"franka-ribbon/adapter.json"}
                if (len(names) != len(set(names)) or set(names) != expected_names
                        or any(not m.isfile() for m in members)):
                    raise ValueError("Existing package file list differs from current source; use a new adapter.json version")
                if json.load(tar.extractfile("franka-ribbon/adapter.json")) != expected_manifest:
                    raise ValueError("Existing package contract differs from current source; use a new adapter.json version")
                for name, content in expected_sources.items():
                    if tar.extractfile(name).read() != content:
                        raise ValueError("Existing package source differs from current source; use a new adapter.json version")
        except (tarfile.TarError, EOFError, OSError, json.JSONDecodeError) as ex:
            raise ValueError("Existing package is invalid; release refused") from ex
        return {"package": str(dst), "sha256": digest,
                "architecture": architecture, "version": manifest_version, "reused": True}
    if dst.exists() or checksum.exists():
        raise FileExistsError("Release already exists; use a new adapter.json version: " + str(dst))
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        package = Path(tmp) / "franka-ribbon"
        package.mkdir()
        src = root / "src"
        for p in src.glob("*.py"):
            shutil.copyfile(p, package / p.name)
        (package / "docs").mkdir()
        for manual in manuals:
            shutil.copyfile(manual, package / "docs" / manual.name)
        manifest["runtime_requirements"]["architecture"] = architecture
        (package / "adapter.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
        )
        archive = Path(tmp) / "package.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            for p in sorted(package.rglob("*")):
                if p.is_file():
                    tar.add(p, arcname=package.name + "/" + p.relative_to(package).as_posix())
        digest = "sha256:" + hashlib.sha256(archive.read_bytes()).hexdigest()
        # Exclusive creation also refuses overwrites by concurrent builds.
        with dst.open("xb") as target:
            try:
                with archive.open("rb") as source:
                    shutil.copyfileobj(source, target)
                with checksum.open("x") as f:
                    f.write(digest + "\n")
            except BaseException:
                dst.unlink(missing_ok=True)
                raise
    return {
        "package": str(dst),
        "sha256": digest,
        "architecture": architecture,
        "version": manifest["version"],
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--version", help="Optional version assertion; defaults to adapter.json version")
    p.add_argument("--architecture", choices=["amd64"], required=True)
    p.add_argument("--output", type=Path, default=ROOT / "output/franka-ribbon")
    p.add_argument("--reuse-existing", action="store_true",
                   help="Reuse an existing release only when checksum, contract and source match")
    a = p.parse_args()
    try:
        result = build(ROOT, a.output, a.architecture, a.version, a.reuse_existing)
    except (ValueError, FileExistsError) as ex:
        p.error(str(ex))
    print(json.dumps(result))
