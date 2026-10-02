#!/usr/bin/env python3
"""Verify a published Crabrix toolchain descriptor and every bound release file."""

import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import sys

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


DOMAIN = b"Crabrix.ToolchainDescriptor.v1\n"
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
EXPECTED_ASSETS = {"rustc.wasm", "sysroot-wasip1.zip", "sysroot-files.json"}
EXPECTED_RELEASE_FILES = {
    "licenses.zip", "vendor-notices.zip", "toolchain.lock.json",
    "sysroot-wasip1.sha256", "toolchain-provenance.json",
    "build-log-summary.txt", "compatibility-results.json",
    "reproducibility-results.json",
}


def unique_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=pairs)


def digest(path):
    checksum = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def verify(directory, keyring):
    envelope = unique_json((directory / "toolchain.descriptor.json").read_bytes())
    if not isinstance(envelope, dict) or set(envelope) != {
        "keyID", "payloadBase64", "signatureBase64"
    }:
        raise ValueError("invalid toolchain descriptor envelope")
    keys = unique_json(keyring.read_bytes())
    if keys.get("schemaVersion") != 1 or not isinstance(keys.get("keys"), list):
        raise ValueError("invalid toolchain public keyring")
    matches = [item for item in keys["keys"]
               if isinstance(item, dict) and item.get("keyID") == envelope["keyID"]]
    if len(matches) != 1:
        raise ValueError("descriptor key ID is not uniquely trusted")
    public = base64.b64decode(matches[0]["publicKeyBase64"], validate=True)
    payload_bytes = base64.b64decode(envelope["payloadBase64"], validate=True)
    signature = base64.b64decode(envelope["signatureBase64"], validate=True)
    if len(public) != 32 or len(signature) != 64:
        raise ValueError("invalid Ed25519 key or signature size")
    Ed25519PublicKey.from_public_bytes(public).verify(signature, DOMAIN + payload_bytes)
    payload = unique_json(payload_bytes)
    if payload.get("schemaVersion") != 1 or payload.get("target") != "wasm32-wasip1":
        raise ValueError("unsupported signed toolchain payload")
    groups = (("assets", EXPECTED_ASSETS), ("releaseFiles", EXPECTED_RELEASE_FILES))
    recorded = {}
    for group_name, expected in groups:
        group = payload.get(group_name)
        if not isinstance(group, dict) or set(group) != expected:
            raise ValueError(f"incomplete signed {group_name}")
        for name, item in group.items():
            path = directory / name
            if not isinstance(item, dict) or set(item) != {"bytes", "sha256"} or \
                    not isinstance(item["bytes"], int) or isinstance(item["bytes"], bool) or \
                    item["bytes"] < 0 or not isinstance(item["sha256"], str) or \
                    not SHA256.fullmatch(item["sha256"]) or not path.is_file() or path.is_symlink() or \
                    path.stat().st_size != item["bytes"] or digest(path) != item["sha256"]:
                raise ValueError(f"signed release file differs: {name}")
            recorded[name] = item["sha256"]
    if payload["rustcSHA256"] != recorded["rustc.wasm"] or \
            payload["sysrootArchiveSHA256"] != recorded["sysroot-wasip1.zip"] or \
            payload["sourceLockSHA256"] != recorded["toolchain.lock.json"]:
        raise ValueError("signed release identity differs from its files")
    inventory = unique_json((directory / "sysroot-files.json").read_bytes())
    manifest_entries = [item for item in inventory.get("files", [])
                        if item.get("path") == "sysroot-wasip1/manifest.json"]
    if len(manifest_entries) != 1 or manifest_entries[0].get("sha256") != payload.get("sysrootManifestSHA256"):
        raise ValueError("signed sysroot manifest digest differs from the inventory")
    lock = unique_json((directory / "toolchain.lock.json").read_bytes())
    provenance = unique_json((directory / "toolchain-provenance.json").read_bytes())
    if provenance.get("candidate") is not False or \
            provenance.get("builderWorkingTreeDirty") is not False or \
            provenance.get("builderSourceCommit") != payload["builderSourceCommit"] or \
            provenance.get("sourceLockSHA256") != payload["sourceLockSHA256"] or \
            provenance.get("rustVersion") != payload.get("rustVersion") or \
            provenance.get("rustRevision") != lock["rust"]["revision"]:
        raise ValueError("signed release provenance is inconsistent")
    sums = (directory / "SHA256SUMS").read_text().splitlines()
    expected_names = sorted([*recorded, "toolchain.descriptor.json"])
    if {item.name for item in directory.iterdir()} != set(expected_names) | {"SHA256SUMS"}:
        raise ValueError("signed release directory has unexpected or missing files")
    expected_sums = [f"{digest(directory / name)}  {name}" for name in expected_names]
    if sums != expected_sums:
        raise ValueError("SHA256SUMS differs from the signed release files")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import verify_artifacts
    verify_artifacts.verify_sysroot(directory)
    import check_compatibility
    check_compatibility.check(directory)
    import check_reproducibility
    check_reproducibility.check(directory, directory / "toolchain.lock.json")
    import verify_vendor_notices
    verify_vendor_notices.verify(directory / "vendor-notices.zip",
                                 directory / "toolchain.lock.json")
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--keys", type=Path, required=True)
    args = parser.parse_args()
    try:
        payload = verify(args.dist, args.keys)
    except (OSError, ValueError, KeyError, TypeError, InvalidSignature) as error:
        raise SystemExit(f"signed toolchain release rejected: {error}") from error
    print(f"Verified signed release {payload['releaseTag']} ({payload['toolchainID']})")


if __name__ == "__main__":
    main()
