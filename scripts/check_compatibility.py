#!/usr/bin/env python3
"""Require the app's exact compiler, Cargo, Academy and sandbox release gates."""

import argparse
import hashlib
import json
from pathlib import Path
import re


SHA256 = re.compile(r"[0-9a-f]{64}\Z")
COMMIT = re.compile(r"[0-9a-f]{40}\Z")
REQUIRED = {
    "release-manifest",
    "e0502",
    "repair-run",
    "root-features",
    "real-crate",
    "offline-pin",
    "vendor-edit",
    "academy-examples",
    "heavy-route-planner",
    "compiler-stop",
    "output-bound",
}


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def check(directory):
    report = json.loads((directory / "compatibility-results.json").read_text())
    if report.get("schemaVersion") != 1 or report.get("status") != "passed":
        raise ValueError("compatibility report is not a passed release report")
    for field, filename in (("compilerSHA256", "rustc.wasm"),
                            ("sysrootArchiveSHA256", "sysroot-wasip1.zip")):
        if not isinstance(report.get(field), str) or not SHA256.fullmatch(report[field]) or \
                report[field] != digest(directory / filename):
            raise ValueError(f"compatibility {field} differs from packaged artifact")
    for field in ("runtimeRevision", "appBuildInputCommit"):
        if not isinstance(report.get(field), str) or not COMMIT.fullmatch(report[field]):
            raise ValueError(f"compatibility report lacks exact {field}")
    environment = report.get("environment")
    if not isinstance(environment, dict) or environment.get("configuration") != "Release" or \
            environment.get("platform") not in ("iOS Simulator", "iOS device"):
        raise ValueError("compatibility gate environment is incomplete")
    gates = report.get("gates")
    if not isinstance(gates, list):
        raise ValueError("compatibility report has no gates")
    seen = set()
    for gate in gates:
        if not isinstance(gate, dict) or not isinstance(gate.get("id"), str) or \
                gate["id"] in seen or not isinstance(gate.get("test"), str) or \
                not gate["test"].startswith(("BundledCompilerGateTests/", "AppToolchainReleaseTests/", "WasmSandboxPolicyTests/", "CompilerPerformanceProbeTests/")) or \
                isinstance(gate.get("executed"), bool) or not isinstance(gate.get("executed"), int) or \
                gate["executed"] < 1 or gate.get("passed") != gate["executed"] or \
                gate.get("failed") != 0 or gate.get("skipped") != 0:
            raise ValueError(f"compatibility gate is incomplete or failed: {gate}")
        seen.add(gate["id"])
    if not REQUIRED.issubset(seen):
        raise ValueError(f"missing required compatibility gates: {sorted(REQUIRED - seen)}")
    failed_probes = report.get("failedProbes", [])
    passed_tests = {gate["test"] for gate in gates}
    if not isinstance(failed_probes, list) or any(
        not isinstance(item, dict) or item.get("result") != "Failed" or
        not isinstance(item.get("test"), str) or item["test"] in passed_tests or
        not isinstance(item.get("resultBundle"), str)
        for item in failed_probes
    ):
        raise ValueError("failed probes are malformed or overlap release gates")
    return len(gates)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", type=Path, required=True)
    args = parser.parse_args()
    try:
        count = check(args.dist)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise SystemExit(f"toolchain compatibility rejected: {error}") from error
    print(f"Verified {count} exact app compatibility gates")


if __name__ == "__main__":
    main()
