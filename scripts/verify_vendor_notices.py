#!/usr/bin/env python3
"""Verify the deterministic vendored dependency notice archive and its index."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import zipfile


SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verify(archive_path, lock_path):
    lock_bytes = lock_path.read_bytes()
    lock = json.loads(lock_bytes)
    with zipfile.ZipFile(archive_path) as archive:
        entries = archive.infolist()
        if len(entries) > 10000 or sum(item.file_size for item in entries) > 128 * 1024 * 1024:
            raise ValueError("notice archive exceeds verification limits")
        names = [entry.filename for entry in entries]
        if len(names) != len(set(names)) or "licenses/vendor-index.json" not in names:
            raise ValueError("notice archive has duplicate paths or no index")
        for entry in entries:
            name = entry.filename
            if not name.startswith("licenses/") or PurePosixPath(name).is_absolute() or \
                    "\\" in name or "\0" in name or any(
                        part in ("", ".", "..") for part in name.split("/")) or \
                    entry.is_dir() or (entry.external_attr >> 16) != 0o100644 or \
                    entry.date_time != (1980, 1, 1, 0, 0, 0):
                raise ValueError(f"invalid notice entry: {name}")
        index = json.loads(archive.read("licenses/vendor-index.json"))
        packages = index.get("packages")
        if index.get("schemaVersion") != 1 or \
                index.get("rustRevision") != lock["rust"]["revision"] or \
                index.get("sourceLockSHA256") != digest(lock_bytes) or \
                index.get("wasiLibcRevision") != lock["wasiSDK"]["sourceSubmodules"]["src/wasi-libc"] or \
                index.get("standardLicenseSource") != \
                "spdx/license-list-data v3.29.0, commit 31ba1a50e5397e00a304dbadc76531740e89ee48" or \
                not isinstance(packages, list) or \
                index.get("packageCount") != len(packages) or len(packages) == 0:
            raise ValueError("notice index differs from locked source")
        referenced = set()

        def check_record(item):
            if not isinstance(item, dict) or not isinstance(item.get("path"), str) or \
                    not isinstance(item.get("bytes"), int) or isinstance(item["bytes"], bool) or \
                    item["bytes"] < 0 or not isinstance(item.get("sha256"), str) or \
                    not SHA256.fullmatch(item["sha256"]) or item["path"] not in names:
                raise ValueError("invalid notice index record")
            data = archive.read(item["path"])
            if len(data) != item["bytes"] or digest(data) != item["sha256"]:
                raise ValueError(f"notice digest differs: {item['path']}")
            referenced.add(item["path"])

        standard = index.get("standardLicenses")
        if not isinstance(standard, dict) or not standard:
            raise ValueError("standard license inventory missing")
        for item in standard.values():
            check_record(item)
        source_notices = index.get("sourceNotices")
        if not isinstance(source_notices, list) or not source_notices:
            raise ValueError("source notice inventory missing")
        for item in source_notices:
            check_record(item)
        metadata_only = 0
        directories = set()
        for package in packages:
            if not isinstance(package, dict) or not isinstance(package.get("directory"), str) or \
                    package["directory"] in directories or \
                    not isinstance(package.get("name"), str) or \
                    not isinstance(package.get("version"), str) or \
                    not isinstance(package.get("noticeFiles"), list) or \
                    not package["noticeFiles"]:
                raise ValueError("invalid vendored package notice record")
            directories.add(package["directory"])
            if package.get("noticeSource") == "SPDX-standard-text-for-declared-expression":
                metadata_only += 1
                if not package.get("licenseExpression") or any(
                        item not in standard.values() for item in package["noticeFiles"]):
                    raise ValueError("metadata-only package lacks its standard license")
            elif package.get("noticeSource") != "vendored-file":
                raise ValueError("unknown package notice source")
            for item in package["noticeFiles"]:
                check_record(item)
        if metadata_only != index.get("metadataOnlyPackageCount") or \
                len(names) - 1 != index.get("noticeFileCount") or \
                referenced != set(names) - {"licenses/vendor-index.json"}:
            raise ValueError("notice archive and index differ")
        return len(packages), metadata_only


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--lock", type=Path, required=True)
    args = parser.parse_args()
    packages, metadata_only = verify(args.archive, args.lock)
    print(f"Verified notices for {packages} vendored packages ({metadata_only} use pinned standard license texts)")


if __name__ == "__main__":
    main()
