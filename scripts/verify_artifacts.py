#!/usr/bin/env python3
"""Check that the packaged sysroot matches its app-readable and full inventories."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
import zipfile


SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def digest_stream(stream):
    checksum = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        checksum.update(block)
    return checksum.hexdigest()


def verify_sysroot(directory):
    archive_path = directory / "sysroot-wasip1.zip"
    expected_zip = (directory / "sysroot-wasip1.sha256").read_text()
    if not SHA256.fullmatch(expected_zip):
        raise ValueError("invalid sysroot ZIP checksum")
    with archive_path.open("rb") as source:
        if digest_stream(source) != expected_zip:
            raise ValueError("sysroot ZIP checksum mismatch")
    inventory = json.loads((directory / "sysroot-files.json").read_text())
    if inventory.get("schemaVersion") != 1 or not isinstance(inventory.get("files"), list):
        raise ValueError("invalid sysroot inventory schema")
    entries = {}
    for entry in inventory["files"]:
        name = entry.get("path")
        if not isinstance(name, str) or not name or PurePosixPath(name).is_absolute() \
                or ".." in PurePosixPath(name).parts or "\\" in name or name in entries:
            raise ValueError(f"invalid or duplicate sysroot path: {name}")
        if not isinstance(entry.get("bytes"), int) or entry["bytes"] < 0 \
                or not SHA256.fullmatch(entry.get("sha256", "")):
            raise ValueError(f"invalid sysroot inventory entry: {name}")
        entries[name] = entry
    manifest_name = "sysroot-wasip1/manifest.json"
    if manifest_name not in entries or any(
        not name.startswith("sysroot-wasip1/") for name in entries
    ):
        raise ValueError("app-readable sysroot manifest missing")
    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        if len(infos) != len(entries) or {item.filename for item in infos} != set(entries):
            raise ValueError("sysroot ZIP entries differ from inventory")
        for info in infos:
            if info.is_dir() or (info.external_attr >> 16) != 0o100644:
                raise ValueError(f"invalid sysroot ZIP entry type: {info.filename}")
            entry = entries[info.filename]
            if info.file_size != entry["bytes"]:
                raise ValueError(f"sysroot ZIP byte count mismatch: {info.filename}")
            with archive.open(info) as source:
                if digest_stream(source) != entry["sha256"]:
                    raise ValueError(f"sysroot ZIP digest mismatch: {info.filename}")
        manifest = json.loads(archive.read(manifest_name))
        logical_files = sorted(name.removeprefix("sysroot-wasip1/")
                               for name in set(entries) - {manifest_name})
        if manifest != {"files": logical_files}:
            raise ValueError("app-readable sysroot manifest differs from inventory")
    return len(entries)


if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) == 2 else Path(__file__).resolve().parents[1] / "dist"
    print(f"Verified {verify_sysroot(root)} sysroot ZIP entries")
