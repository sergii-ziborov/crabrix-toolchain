#!/usr/bin/env python3
"""Require a signed account of two independent clean toolchain builds."""

import argparse
import hashlib
import json
from pathlib import Path
import re


SHA = re.compile(r"[0-9a-f]{64}\Z")
COMMIT = re.compile(r"[0-9a-f]{40}\Z")


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def check(directory, lock_path):
    report = json.loads((directory / "reproducibility-results.json").read_text())
    lock = json.loads(lock_path.read_text())
    provenance = json.loads((directory / "toolchain-provenance.json").read_text())
    if report.get("schemaVersion") != 1 or report.get("sourceLockSHA256") != digest(lock_path) or \
            report.get("builderImageDigest") != lock["buildEnvironment"]["imageDigest"] or \
            report.get("outputTarget") != "wasm32-wasip1" or \
            not isinstance(report.get("builderSourceCommit"), str) or \
            not COMMIT.fullmatch(report["builderSourceCommit"]) or \
            report["builderSourceCommit"] != provenance.get("builderSourceCommit"):
        raise ValueError("reproducibility inputs differ from the locked build")
    builds = report.get("builds")
    if not isinstance(builds, list) or len(builds) != 2 or \
            {item.get("id") for item in builds if isinstance(item, dict)} != {"release-1", "release-2"}:
        raise ValueError("two distinct clean builds are required")
    for item in builds:
        if item.get("status") != "success" or \
                item.get("freshCompiledOutputAtStart") is not True or \
                item.get("installedOutputEmptyBeforeInstall") is not True or \
                item.get("builderSourceCommit") != report.get("builderSourceCommit") or \
                any(not isinstance(item.get(field), str) or not SHA.fullmatch(item[field])
                    for field in ("compilerSHA256", "sysrootArchiveSHA256")):
            raise ValueError("a clean build did not produce both artifacts")
    first, second = sorted(builds, key=lambda item: item["id"])
    if first["compilerSHA256"] != digest(directory / "rustc.wasm") or \
            first["sysrootArchiveSHA256"] != digest(directory / "sysroot-wasip1.zip"):
        raise ValueError("release assets are not the first recorded source build")
    compiler_match = first["compilerSHA256"] == second["compilerSHA256"]
    sysroot_match = first["sysrootArchiveSHA256"] == second["sysrootArchiveSHA256"]
    if report.get("compilerRawMatch") is not compiler_match or \
            report.get("sysrootRawMatch") is not sysroot_match or \
            report.get("status") != ("identical" if compiler_match and sysroot_match
                                     else "differences-recorded"):
        raise ValueError("raw output comparison is inconsistent")
    differences = report.get("differences")
    if not isinstance(differences, list) or \
            ((compiler_match and sysroot_match) and differences) or \
            ((not compiler_match or not sysroot_match) and not differences):
        raise ValueError("output differences are not recorded")
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--lock", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = check(args.dist, args.lock)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise SystemExit(f"reproducibility report rejected: {error}") from error
    print(f"Verified two clean builds: {result['status']}")


if __name__ == "__main__":
    main()
