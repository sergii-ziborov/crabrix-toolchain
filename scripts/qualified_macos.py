"""Explicit qualification of a pinned Mac source build; preserves raw origins.

This is separate from the locked Linux builder. An experimental artifact is
eligible only after two identical clean-source builds and all app/macro gates.
The original candidate provenance remains embedded unchanged in the signed
release record, rather than being relabeled as a Linux build.
"""

import base64
import hashlib
import json
from pathlib import Path
import re

PROFILE_ID = "macos-wasi-rpc-fat-2026-10-25"
ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "release-profiles" / (PROFILE_ID + ".json")
PATH_SETTINGS = {
    "target.aarch64-apple-darwin.llvm-config": "/opt/homebrew/Cellar/llvm@22/22.1.8/bin/llvm-config",
    "target.wasm32-wasip1.wasi-root": "/Volumes/workspace/crabrix-compiler-performance/build/wasi-sdk-32.0-arm64-macos/share/wasi-sysroot",
    "target.wasm32-wasip1.linker": "/Volumes/workspace/crabrix-compiler-performance/build/wasi-sdk-32.0-arm64-macos/bin/clang",
}
COMMIT = re.compile(r"[0-9a-f]{40}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")
UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z")


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def profile():
    spec = json.loads(PROFILE.read_text())
    if spec.get("schemaVersion") != 1 or spec.get("id") != PROFILE_ID:
        raise ValueError("unknown Mac qualification profile")
    return spec


def validate_source(source, spec):
    if source.get("candidate") is not True or source.get("productionReplacement") is not False:
        raise ValueError("raw Mac source-build origin was altered")
    expected = {
        "toolchainRepositoryCommit": spec["recipeCommit"],
        "rustRevision": spec["rustRevision"], "rustVersion": spec["rustVersion"],
        "configSourceSHA256": spec["configSourceSHA256"],
        "patchDigests": spec["basePatchDigests"],
        "stage0ManifestSHA256": spec["stage0ManifestSHA256"],
        "sdk": spec["sdk"], "nativeLLVM": spec["nativeLLVM"],
        "experimentalProcMacroBridge": {
            "schemaVersion": 1, "patch": "0005-wasi-proc-macro-bridge.candidate.patch",
            "sha256": spec["bridgePatchSHA256"],
            "compilerOptInEnvironment": "CRABRIX_WASM_PROC_MACROS=1",
        },
    }
    if any(source.get(key) != value for key, value in expected.items()):
        raise ValueError("source build differs from the approved Mac recipe or patches")
    settings = source.get("settings")
    required = dict(spec["settings"], **{key: json.dumps(value) for key, value in PATH_SETTINGS.items()})
    if settings != required:
        raise ValueError("source compiler flags differ from the qualified profile")
    command = source.get("command")
    if not isinstance(command, list) or len(command) != 8 + 2 * len(settings) or \
            command[1:8] != ["x.py", "build", "compiler/rustc", "--stage", "2", "--jobs", "3"] or \
            not isinstance(command[0], str) or not command[0].endswith("/python3.13"):
        raise ValueError("source build invocation differs from the pinned bootstrap")
    arguments = command[8:]
    if any(arguments[index] != "--set" for index in range(0, len(arguments), 2)) or \
            sorted(arguments[1::2]) != sorted(f"{key}={value}" for key, value in settings.items()):
        raise ValueError("source build command and recorded settings disagree")
    if not UUID.fullmatch(source.get("cloudBuildID", "")) or \
            not SHA.fullmatch(source.get("compilerSHA256", "")) or \
            type(source.get("compilerBytes")) is not int or not 8 <= source["compilerBytes"] <= 256 * 1024**2 or \
            type(source.get("compilerBuildSeconds")) not in (int, float) or source["compilerBuildSeconds"] <= 0:
        raise ValueError("source build has no concrete compiler identity")
    sysroot = source.get("candidateSysroot", {})
    if source.get("candidateSysrootExportError") is not None or \
            sysroot.get("sourceStage") != "build/aarch64-apple-darwin/stage1/lib/rustlib/wasm32-wasip1/lib" or \
            type(sysroot.get("fileCount")) is not int or sysroot["fileCount"] != spec["sysrootFileCount"] or \
            any(not SHA.fullmatch(sysroot.get(key, "")) for key in ("archiveSHA256", "inventorySHA256")):
        raise ValueError("source-built macro sysroot is incomplete")
    return source


def check(directory, lock_path):
    spec = profile()
    if digest(lock_path) != spec["sourceLockSHA256"]:
        raise ValueError("Mac qualification source lock differs from approved input")
    provenance = json.loads((directory / "toolchain-provenance.json").read_text())
    if provenance.get("buildProfile") != PROFILE_ID or provenance.get("candidate") is not False or \
            provenance.get("productionReplacement") is not True or \
            provenance.get("qualificationWorkingTreeClean") is not True or \
            not COMMIT.fullmatch(provenance.get("qualificationSourceCommit", "")) or \
            provenance.get("qualificationProfileSHA256") != digest(PROFILE) or \
            provenance.get("builderSourceCommit") != spec["recipeCommit"] or \
            provenance.get("sourceLockSHA256") != spec["sourceLockSHA256"] or \
            provenance.get("rustRevision") != spec["rustRevision"] or \
            provenance.get("rustVersion") != spec["rustVersion"]:
        raise ValueError("Mac release was not explicitly qualified with the approved policy")
    raw = provenance.get("sourceBuilds")
    if not isinstance(raw, list) or len(raw) != 2:
        raise ValueError("two original source-build records are required")
    sources = []
    for record in raw:
        if not isinstance(record, dict) or set(record) != {"provenanceBase64", "provenanceSHA256"}:
            raise ValueError("invalid embedded source-build record")
        data = base64.b64decode(record["provenanceBase64"], validate=True)
        if len(data) > 128 * 1024 or hashlib.sha256(data).hexdigest() != record["provenanceSHA256"]:
            raise ValueError("original source-build provenance changed")
        sources.append(validate_source(json.loads(data), spec))
    if sources[0]["cloudBuildID"] == sources[1]["cloudBuildID"]:
        raise ValueError("two independent source builds are required")
    for source in sources:
        if source["compilerSHA256"] != digest(directory / "rustc.wasm") or \
                source["compilerBytes"] != (directory / "rustc.wasm").stat().st_size or \
                source["candidateSysroot"]["archiveSHA256"] != digest(directory / "sysroot-wasip1.zip") or \
                source["candidateSysroot"]["inventorySHA256"] != digest(directory / "sysroot-files.json"):
            raise ValueError("release does not match both independent raw source builds")
    inventory = json.loads((directory / "sysroot-files.json").read_text())["files"]
    if any(source["candidateSysroot"]["fileCount"] != len(inventory) for source in sources):
        raise ValueError("captured sysroot file count differs")
    for crate in ("std", "core", "alloc", "compiler_builtins", "proc_macro", "rustc_literal_escaper"):
        if not any(Path(item["path"]).name.startswith("lib" + crate + "-") and item["path"].endswith(".rlib") for item in inventory):
            raise ValueError("qualified sysroot lacks the macro API")
    names = {item["path"] for item in inventory}
    for name in ("libc.a", "crt1-command.o"):
        if "sysroot-wasip1/lib/rustlib/wasm32-wasip1/lib/self-contained/" + name not in names:
            raise ValueError("qualified sysroot lacks its WASI runtime")
    report = json.loads((directory / "reproducibility-results.json").read_text())
    identities = {source["cloudBuildID"] for source in sources}
    if report != {
        "schemaVersion": 2, "buildProfile": PROFILE_ID, "status": "identical",
        "sourceLockSHA256": spec["sourceLockSHA256"],
        "qualificationProfileSHA256": digest(PROFILE),
        "builderSourceCommit": spec["recipeCommit"], "outputTarget": "wasm32-wasip1",
        "independentCloudBuildIDs": sorted(identities),
        "compilerSHA256": digest(directory / "rustc.wasm"),
        "sysrootArchiveSHA256": digest(directory / "sysroot-wasip1.zip"),
        "sysrootInventorySHA256": digest(directory / "sysroot-files.json"),
        "compilerRawMatch": True, "sysrootRawMatch": True, "inventoryRawMatch": True,
    }:
        raise ValueError("Mac reproducibility report does not describe both raw builds")
    import check_compatibility
    check_compatibility.check(directory)
    compatibility = json.loads((directory / "compatibility-results.json").read_text())
    passed = {gate["id"] for gate in compatibility["gates"]}
    if not set(spec["requiredAdditionalGates"]).issubset(passed) or \
            compatibility.get("environment", {}).get("dispatch") != "software-direct":
        raise ValueError("Mac compiler has not passed real macro consumers and direct-mode gates")
    return report
