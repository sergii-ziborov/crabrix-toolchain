#!/usr/bin/env python3
"""Prepare a new, unsigned release from two qualified Mac source builds.

Never edits candidate origins or signs an untested compiler. The subsequent
privileged signing step independently rechecks every condition.
"""

import argparse
import base64
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import qualified_macos as policy
import verify_artifacts
import verify_vendor_notices


def prepare(first, repeat, compatibility, notices, output):
    root, spec = policy.ROOT, policy.profile()
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip():
        raise ValueError("qualification recipe must be committed in a clean working tree")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    if output.exists():
        raise ValueError("release destination must be new; existing releases are immutable")
    if first.resolve() == repeat.resolve():
        raise ValueError("two independent build directories are required")
    sources = []
    for directory in (first, repeat):
        if directory.is_symlink():
            raise ValueError("source artifact directory is a symlink")
        record = directory / "provenance.json"
        data = record.read_bytes()
        source = policy.validate_source(json.loads(data), spec)
        verify_artifacts.verify_sysroot(directory)
        if policy.digest(directory / "rustc.wasm") != source["compilerSHA256"] or \
                (directory / "rustc.wasm").stat().st_size != source["compilerBytes"] or \
                policy.digest(directory / "sysroot-wasip1.zip") != source["candidateSysroot"]["archiveSHA256"] or \
                policy.digest(directory / "sysroot-files.json") != source["candidateSysroot"]["inventorySHA256"]:
            raise ValueError("source outputs differ from original build provenance")
        sources.append((source, {"provenanceBase64": base64.b64encode(data).decode(),
                                 "provenanceSHA256": hashlib.sha256(data).hexdigest()}))
    if sources[0][0]["cloudBuildID"] == sources[1][0]["cloudBuildID"]:
        raise ValueError("source records identify the same Cloud build")
    for name in ("rustc.wasm", "sysroot-wasip1.zip", "sysroot-files.json"):
        if policy.digest(first / name) != policy.digest(repeat / name):
            raise ValueError("independent raw source outputs are not identical")
    with (first / "rustc.wasm").open("rb") as stream:
        if stream.read(8) != b"\0asm\1\0\0\0": raise ValueError("compiler has no Wasm header")
    if policy.digest(root / "toolchain.lock.json") != spec["sourceLockSHA256"]:
        raise ValueError("qualification source lock differs from approved profile")
    verify_vendor_notices.verify(notices / "vendor-notices.zip", root / "toolchain.lock.json")
    output.mkdir(parents=True)
    for name in ("rustc.wasm", "sysroot-wasip1.zip", "sysroot-files.json", "sysroot-wasip1.sha256"):
        shutil.copyfile(first / name, output / name)
    for name in ("licenses.zip", "vendor-notices.zip"):
        shutil.copyfile(notices / name, output / name)
    shutil.copyfile(root / "toolchain.lock.json", output / "toolchain.lock.json")
    shutil.copyfile(compatibility, output / "compatibility-results.json")
    provenance = {
        "schemaVersion": 2, "candidate": False, "productionReplacement": True,
        "buildProfile": policy.PROFILE_ID,
        "qualificationSourceCommit": commit, "qualificationWorkingTreeClean": True,
        "qualificationProfileSHA256": policy.digest(policy.PROFILE),
        "builderSourceCommit": spec["recipeCommit"], "sourceLockSHA256": spec["sourceLockSHA256"],
        "rustRevision": spec["rustRevision"], "rustVersion": spec["rustVersion"],
        "sourceBuilds": [record for _, record in sources],
    }
    reproducibility = {
        "schemaVersion": 2, "buildProfile": policy.PROFILE_ID, "status": "identical",
        "sourceLockSHA256": spec["sourceLockSHA256"],
        "qualificationProfileSHA256": policy.digest(policy.PROFILE),
        "builderSourceCommit": spec["recipeCommit"], "outputTarget": "wasm32-wasip1",
        "independentCloudBuildIDs": sorted(source["cloudBuildID"] for source, _ in sources),
        "compilerSHA256": policy.digest(output / "rustc.wasm"),
        "sysrootArchiveSHA256": policy.digest(output / "sysroot-wasip1.zip"),
        "sysrootInventorySHA256": policy.digest(output / "sysroot-files.json"),
        "compilerRawMatch": True, "sysrootRawMatch": True, "inventoryRawMatch": True,
    }
    for name, data in (("toolchain-provenance.json", provenance),
                       ("reproducibility-results.json", reproducibility)):
        (output / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    (output / "build-log-summary.txt").write_text(
        "Qualified Mac source recipe: " + spec["recipeCommit"] + "\n"
        "Qualification policy commit: " + commit + "\n"
        "Original experimental source provenance is retained verbatim in toolchain-provenance.json.\n"
        "Both independent builds produced identical compiler, sysroot ZIP and inventory.\n"
        + "\n".join("Source Cloud build: " + source["cloudBuildID"] for source, _ in sources) + "\n"
        "Compiler SHA256: " + reproducibility["compilerSHA256"] + "\n"
        "Sysroot ZIP SHA256: " + reproducibility["sysrootArchiveSHA256"] + "\n"
        "The separate locked Linux release recipe was not used for this build.\n")
    policy.check(output, root / "toolchain.lock.json")
    verify_artifacts.verify_sysroot(output)
    return reproducibility


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("first", "repeat", "compatibility", "notices", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    try:
        result = prepare(args.first, args.repeat, args.compatibility, args.notices, args.output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SystemExit(f"Mac release qualification rejected: {error}") from error
    print(json.dumps(result, indent=2))


if __name__ == "__main__": main()
