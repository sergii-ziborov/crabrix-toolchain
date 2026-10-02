#!/usr/bin/env python3
"""Privileged, deterministic Ed25519 toolchain descriptor signing step."""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


DOMAIN = b"Crabrix.ToolchainDescriptor.v1\n"
COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
ASSET_LIMITS = {
    "rustc.wasm": 256 * 1024 * 1024,
    "sysroot-wasip1.zip": 512 * 1024 * 1024,
    "sysroot-files.json": 16 * 1024 * 1024,
}
RELEASE_FILE_LIMITS = {
    "licenses.zip": 16 * 1024 * 1024,
    "vendor-notices.zip": 64 * 1024 * 1024,
    "toolchain.lock.json": 1024 * 1024,
    "sysroot-wasip1.sha256": 64,
    "toolchain-provenance.json": 1024 * 1024,
    "build-log-summary.txt": 1024 * 1024,
    "compatibility-results.json": 1024 * 1024,
    "reproducibility-results.json": 1024 * 1024,
}


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def sign(repository, directory, tag, toolchain_id, key_id, key_path, public_base64):
    for value, label in ((tag, "release tag"), (toolchain_id, "toolchain ID"), (key_id, "key ID")):
        if not COMPONENT.fullmatch(value):
            raise ValueError(f"invalid {label}")
    allowed_files = set(ASSET_LIMITS) | set(RELEASE_FILE_LIMITS) | {"SHA256SUMS"}
    actual_files = {item.name for item in directory.iterdir()}
    if actual_files not in (allowed_files, allowed_files - {"SHA256SUMS"}):
        raise ValueError(f"release file set is incomplete or unexpected: {sorted(actual_files ^ allowed_files)}")
    if "SHA256SUMS" in actual_files:
        expected = [f"{digest(directory / name)}  {name}" for name in
                    sorted(allowed_files - {"SHA256SUMS"})]
        if (directory / "SHA256SUMS").read_text().splitlines() != expected:
            raise ValueError("pre-signing SHA256SUMS differs from release files")
    if repository.resolve() in key_path.resolve().parents:
        raise ValueError("the private signing key must be outside the public repository")
    if key_path.stat().st_mode & 0o077:
        raise ValueError("the private signing key must be owner-only")
    lock = json.loads((repository / "toolchain.lock.json").read_text())
    provenance = json.loads((directory / "toolchain-provenance.json").read_text())
    lock_digest = digest(repository / "toolchain.lock.json")
    if provenance.get("candidate") is not False or provenance.get("builderWorkingTreeDirty") is not False or \
            provenance.get("sourceLockSHA256") != lock_digest or \
            provenance.get("rustRevision") != lock["rust"]["revision"] or \
            provenance.get("rustVersion") != lock["rust"]["actualVersion"]:
        raise ValueError("artifact provenance is not an eligible locked source build")
    source_commit = provenance.get("builderSourceCommit")
    if not isinstance(source_commit, str) or not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("missing exact builder source commit")
    import verify_artifacts
    verify_artifacts.verify_sysroot(directory)
    import check_compatibility
    check_compatibility.check(directory)
    import check_reproducibility
    check_reproducibility.check(directory, repository / "toolchain.lock.json")
    import verify_vendor_notices
    verify_vendor_notices.verify(directory / "vendor-notices.zip",
                                 repository / "toolchain.lock.json")
    assets = {}
    for name, maximum in ASSET_LIMITS.items():
        path = directory / name
        if not path.is_file() or path.is_symlink() or path.stat().st_size > maximum:
            raise ValueError(f"missing or oversized artifact: {name}")
        assets[name] = {"bytes": path.stat().st_size, "sha256": digest(path)}
    with (directory / "rustc.wasm").open("rb") as stream:
        if stream.read(8) != b"\0asm\1\0\0\0":
            raise ValueError("compiler has no Wasm header")
    release_files = {}
    for name, maximum in RELEASE_FILE_LIMITS.items():
        path = directory / name
        if not path.is_file() or path.is_symlink() or path.stat().st_size > maximum:
            raise ValueError(f"missing or oversized release evidence: {name}")
        release_files[name] = {"bytes": path.stat().st_size, "sha256": digest(path)}
    if release_files["toolchain.lock.json"]["sha256"] != lock_digest:
        raise ValueError("release source lock differs from the builder input")
    inventory = json.loads((directory / "sysroot-files.json").read_text())
    matches = [item for item in inventory["files"]
               if item.get("path") == "sysroot-wasip1/manifest.json"]
    if len(matches) != 1:
        raise ValueError("sysroot manifest inventory missing or ambiguous")
    manifest_sha = matches[0]["sha256"]
    payload = {
        "schemaVersion": 1,
        "releaseTag": tag,
        "toolchainID": toolchain_id,
        "target": "wasm32-wasip1",
        "rustVersion": provenance["rustVersion"],
        "rustcSHA256": assets["rustc.wasm"]["sha256"],
        "sysrootArchiveSHA256": assets["sysroot-wasip1.zip"]["sha256"],
        "sysrootManifestSHA256": manifest_sha,
        "sourceLockSHA256": lock_digest,
        "builderSourceCommit": source_commit,
        "assets": assets,
        "releaseFiles": release_files,
    }
    encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("private signing key is not Ed25519")
    public = base64.b64encode(key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
    if public != public_base64:
        raise ValueError("private key does not match app's built-in public key")
    signature = key.sign(DOMAIN + encoded)
    envelope = {
        "keyID": key_id,
        "payloadBase64": base64.b64encode(encoded).decode(),
        "signatureBase64": base64.b64encode(signature).decode(),
    }
    descriptor = directory / "toolchain.descriptor.json"
    if descriptor.exists():
        raise ValueError("descriptor already exists; release versions are immutable")
    descriptor.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n")
    sums = [f"{digest(path)}  {path.name}" for path in sorted(directory.iterdir())
            if path.is_file() and path.name != "SHA256SUMS"]
    (directory / "SHA256SUMS").write_text("\n".join(sums) + "\n")
    return {"descriptorSHA256": digest(descriptor), "payload": payload}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--toolchain-id", required=True)
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--private-key", type=Path, required=True)
    parser.add_argument("--expected-public-key-base64", required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.repository / "scripts"))
    result = sign(args.repository, args.dist, args.release_tag, args.toolchain_id,
                  args.key_id, args.private_key, args.expected_public_key_base64)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
