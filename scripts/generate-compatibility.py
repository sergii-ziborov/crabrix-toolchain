#!/usr/bin/env python3
"""Create a release compatibility report from actual Xcode result bundles."""

import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import re
import subprocess


GATES = {
    "release-manifest": "AppToolchainReleaseTests/testReleaseInputMatchesBundledCompilerAndSysroot()",
    "e0502": "BundledCompilerGateTests/testBundledRustcProducesE0502()",
    "repair-run": "BundledCompilerGateTests/testBundledRustcCompilesAndRunsRepairedProgram()",
    "root-features": "BundledCompilerGateTests/testRootFeaturesReachTheRootCrate()",
    "real-crate": "BundledCompilerGateTests/testResolvesDownloadsAndLinksARealCratesIOPackage()",
    "offline-pin": "BundledCompilerGateTests/testOfflinePinRehydratesSourcesAfterPurgeableCacheEviction()",
    "vendor-edit": "BundledCompilerGateTests/testVendoredCrateBuildsFromAProjectLocalPatch()",
    "academy-examples": "BundledCompilerGateTests/testEveryInstalledAcademyExampleBuildsAndRuns()",
    "heavy-route-planner": "BundledCompilerGateTests/testMultiFileRoutePlannerWithGraphCratesBuildsAndRuns()",
    "compiler-stop": "BundledCompilerGateTests/testStopInterruptsARunningCompile()",
    "output-bound": "BundledCompilerGateTests/testUserProgramOutputStopsAtWASIWriteBudget()",
    "multi-file-cli": "BundledCompilerGateTests/testMultiFileClapRegexCollectionsAppBuildsAndRuns()",
    "warning-cache": "CompilerPerformanceProbeTests/testColdEngineAndUnchangedWarningCheck()",
}


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def xcresult(path, name):
    output = subprocess.run(
        ["xcrun", "xcresulttool", "get", "test-results", name,
         "--path", str(path), "--format", "json"],
        capture_output=True, text=True, check=True,
    )
    return json.loads(output.stdout)


def leaves(node):
    if isinstance(node, dict):
        if node.get("nodeType") == "Test Case":
            yield node
        for child in node.get("children", []):
            yield from leaves(child)
    elif isinstance(node, list):
        for child in node:
            yield from leaves(child)


def build(dist, bundles, app_commit, runtime_revision, test_app, test_run,
          known_failure_bundles=()):
    if any(not re.fullmatch(r"[0-9a-f]{40}", value)
           for value in (app_commit, runtime_revision)):
        raise ValueError("app and runtime revisions must be exact commits")
    if not bundles or len({bundle.resolve() for bundle in bundles}) != len(bundles):
        raise ValueError("supply distinct Xcode result bundles")
    if test_app.name != "Crabrix.app" or test_app.parent.name != "Release-iphonesimulator":
        raise ValueError("test host must be a Release iOS Simulator app")
    run = plistlib.loads(test_run.read_bytes()).get("CrabrixTests")
    if not isinstance(run, dict) or run.get("TestHostPath") != \
            "__TESTROOT__/Release-iphonesimulator/Crabrix.app":
        raise ValueError("xctestrun does not target the Release app")
    manifest = json.loads((test_app / "toolchain.lock.json").read_bytes())
    compiler_sha = digest(dist / "rustc.wasm")
    sysroot_sha = digest(dist / "sysroot-wasip1.zip")
    toolchain_id = manifest.get("toolchainID")
    bundled = test_app / "Toolchain" / str(toolchain_id)
    if manifest.get("rustcSHA256") != compiler_sha or \
            manifest.get("sysrootArchiveSHA256") != sysroot_sha or \
            digest(bundled / "rustc.wasm") != compiler_sha or \
            digest(bundled / "sysroot-wasip1.zip") != sysroot_sha:
        raise ValueError("the Release test host did not bundle these exact artifact bytes")
    results = {}
    device = None
    for bundle in bundles:
        if not bundle.is_dir() or not bundle.name.endswith(".xcresult"):
            raise ValueError(f"missing Xcode result bundle: {bundle}")
        summary = xcresult(bundle, "summary")
        nodes = xcresult(bundle, "tests")
        cases = list(leaves(nodes.get("testNodes", [])))
        if not cases or summary.get("totalTestCount") != len(cases) or \
                summary.get("passedTests") != len(cases) or \
                summary.get("failedTests") != 0 or summary.get("skippedTests") != 0:
            raise ValueError(f"Xcode result is incomplete or failed: {bundle.name}")
        devices = nodes.get("devices")
        if not isinstance(devices, list) or len(devices) != 1 or \
                devices[0].get("platform") != "iOS Simulator":
            raise ValueError(f"expected one iOS Simulator device: {bundle.name}")
        selected = {key: devices[0].get(key) for key in
                    ("architecture", "modelName", "osBuildNumber", "osVersion", "platform")}
        if device is None:
            device = selected
        elif device != selected:
            raise ValueError("result bundles used different simulator configurations")
        for case in cases:
            test = case.get("nodeIdentifier")
            if case.get("result") != "Passed" or not isinstance(test, str) or test in results:
                raise ValueError(f"failed or duplicate test case: {test}")
            results[test] = (case, bundle.name)
    missing = set(GATES.values()) - set(results)
    if missing:
        raise ValueError(f"release gates were not executed: {sorted(missing)}")
    failed_probes = []
    for bundle in known_failure_bundles:
        summary = xcresult(bundle, "summary")
        nodes = xcresult(bundle, "tests")
        cases = list(leaves(nodes.get("testNodes", [])))
        failed = [case for case in cases if case.get("result") == "Failed"]
        if not failed or len(failed) != summary.get("failedTests") or \
                summary.get("totalTestCount") != len(cases) or \
                summary.get("skippedTests") != 0:
            raise ValueError(f"known failure evidence is incomplete: {bundle.name}")
        for case in failed:
            failed_probes.append({"test": case["nodeIdentifier"],
                                  "result": "Failed", "resultBundle": bundle.name})
    gates = []
    for gate_id, test in GATES.items():
        case, bundle_name = results[test]
        gates.append({
            "id": gate_id, "test": test, "executed": 1, "passed": 1,
            "failed": 0, "skipped": 0,
            "durationSeconds": case.get("durationInSeconds"),
            "resultBundle": bundle_name,
        })
    return {
        "schemaVersion": 1,
        "status": "passed",
        "compilerSHA256": compiler_sha,
        "sysrootArchiveSHA256": sysroot_sha,
        "appBuildInputCommit": app_commit,
        "runtimeRevision": runtime_revision,
        "environment": {
            "configuration": "Release",
            "platform": device["platform"],
            "osVersion": device["osVersion"],
            "osBuildNumber": device["osBuildNumber"],
            "deviceModel": device["modelName"],
            "architecture": device["architecture"],
        },
        "gates": gates,
        "failedProbes": failed_probes,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--app-commit", required=True)
    parser.add_argument("--runtime-revision", required=True)
    parser.add_argument("--xcresult", type=Path, action="append", required=True)
    parser.add_argument("--known-failure-xcresult", type=Path, action="append", default=[])
    parser.add_argument("--test-app", type=Path, required=True)
    parser.add_argument("--xctestrun", type=Path, required=True)
    args = parser.parse_args()
    output = args.dist / "compatibility-results.json"
    if output.exists():
        parser.error("compatibility report already exists")
    report = build(args.dist, args.xcresult, args.app_commit, args.runtime_revision,
                   args.test_app, args.xctestrun, args.known_failure_xcresult)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"Recorded {len(report['gates'])} passed app gates from Xcode result bundles")


if __name__ == "__main__":
    main()
