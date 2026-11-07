#!/usr/bin/env python3
"""Sign or verify exact bytes of a source-built toolchain release.

The private Ed25519 key is supplied only to the protected publish step. Normal
builds and pull requests need a public keyring for verification, not that key.
"""

import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import sys
import unicodedata

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

ROOT = Path(__file__).resolve().parent.parent
DOMAIN = b"Crabrix.ToolchainDescriptor.v1\n"
MANDATORY = {
    "rustc.wasm", "sysroot-wasip1.zip", "sysroot-files.json", "SHA256SUMS",
    "toolchain-provenance.json", "compatibility-results.json", "build-log-summary.txt",
}
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
GIT_REV = re.compile(r"[0-9a-f]{40}\Z")
IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def inventory(directory):
    if not directory.is_dir():
        raise ValueError("release directory does not exist")
    files = []
    folded = set()
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"release symlink rejected: {path}")
        if not path.is_file():
            continue
        if path.stat().st_nlink != 1:
            raise ValueError(f"release hardlink rejected: {path}")
        name = path.relative_to(directory).as_posix()
        if name == "toolchain.descriptor.json":
            continue
        if unicodedata.normalize("NFC", name).casefold() == "toolchain.descriptor.json":
            raise ValueError(f"release path collides with descriptor: {name}")
        components = name.split("/")
        if any(part in ("", ".", "..") or part.endswith((" ", ".")) for part in components):
            raise ValueError(f"unsafe release path: {name}")
        collision = unicodedata.normalize("NFC", name).casefold()
        if collision in folded:
            raise ValueError(f"release path collision: {name}")
        folded.add(collision)
        files.append({"path": name, "bytes": path.stat().st_size, "sha256": digest(path)})
    names = {item["path"] for item in files}
    if not MANDATORY.issubset(names) or not any(name.startswith("licenses/") for name in names):
        raise ValueError("release lacks mandatory files or component notices")
    return files


def release_identity(directory):
    if (directory / "CANDIDATE-NOT-FOR-RELEASE.txt").exists():
        raise ValueError("candidate artifacts cannot be signed for release")
    lock = json.loads((ROOT / "toolchain.lock.json").read_text(encoding="utf-8"))
    provenance = json.loads((directory / "toolchain-provenance.json").read_text(encoding="utf-8"))
    if provenance.get("candidate") is not False or provenance.get("builderWorkingTreeDirty") is not False:
        raise ValueError("release provenance is candidate or dirty")
    if provenance.get("sourceLockSHA256") != digest(ROOT / "toolchain.lock.json"):
        raise ValueError("release provenance does not match this source lock")
    if provenance.get("rustRevision") != lock["rust"]["revision"]:
        raise ValueError("release Rust revision differs from this source lock")
    image_digest = lock["buildEnvironment"]["imageDigest"]
    if (not isinstance(image_digest, str) or not image_digest.startswith("sha256:")
            or not SHA256.fullmatch(image_digest[7:])
            or not lock["buildEnvironment"]["hostToolVersions"]):
        raise ValueError("release environment lock is incomplete")
    return provenance, lock


def require_compatibility(directory):
    compatibility = json.loads((directory / "compatibility-results.json").read_text(encoding="utf-8"))
    if compatibility.get("schemaVersion") != 1:
        raise ValueError("compatibility results use an unknown schema")
    for field, path in (("rustcSHA256", "rustc.wasm"),
                        ("sysrootSHA256", "sysroot-wasip1.zip")):
        if compatibility.get(field) != digest(directory / path):
            raise ValueError(f"compatibility results do not match {path}")
    for field in ("appRevision", "runtimeRevision"):
        if not isinstance(compatibility.get(field), str) or not GIT_REV.fullmatch(compatibility[field]):
            raise ValueError(f"compatibility results lack {field}")
    gates = compatibility.get("gates")
    if not isinstance(gates, list):
        raise ValueError("compatibility results lack gates")
    recorded = {}
    for gate in gates:
        if not isinstance(gate, dict) or not isinstance(gate.get("id"), str):
            raise ValueError("invalid compatibility gate")
        if gate["id"] in recorded:
            raise ValueError(f'duplicate compatibility gate: {gate["id"]}')
        recorded[gate["id"]] = gate
    if any(recorded.get(f"T{number:02d}", {}).get("status") != "passed" for number in range(1, 7)):
        raise ValueError("required toolchain gates have not passed")
    for number in range(1, 7):
        gate = recorded[f"T{number:02d}"]
        evidence = gate.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise ValueError(f'gate {gate["id"]} lacks evidence files')
        for name in evidence:
            if not isinstance(name, str) or not name.startswith("validation/") or any(
                part in ("", ".", "..") for part in name.split("/")
            ) or not (directory / name).is_file() or (directory / name).stat().st_size == 0:
                raise ValueError(f'gate {gate["id"]} has invalid evidence path')


def payload_bytes(directory, toolchain_id):
    if not IDENTITY.fullmatch(toolchain_id):
        raise ValueError("invalid toolchain ID")
    files = inventory(directory)
    provenance, lock = release_identity(directory)
    require_compatibility(directory)
    payload = {
        "schemaVersion": 1,
        "toolchainID": toolchain_id,
        "target": "wasm32-wasip1",
        "rustVersion": lock["rust"]["actualVersion"],
        "rustRevision": provenance["rustRevision"],
        "sourceLockSHA256": provenance["sourceLockSHA256"],
        "files": files,
    }
    return (json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def envelope(payload, key_id, private_key):
    if not IDENTITY.fullmatch(key_id):
        raise ValueError("invalid signing key ID")
    signature = private_key.sign(DOMAIN + payload)
    value = {
        "keyID": key_id,
        "payloadBase64": base64.b64encode(payload).decode("ascii"),
        "signatureBase64": base64.b64encode(signature).decode("ascii"),
    }
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sign(args):
    directory = args.dist.resolve()
    output = directory / "toolchain.descriptor.json"
    if output.exists():
        raise ValueError("release descriptor already exists; published releases are immutable")
    if args.private_key.resolve().is_relative_to(ROOT):
        raise ValueError("the private signing key must stay outside this repository")
    key = serialization.load_pem_private_key(args.private_key.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("the signing key must be Ed25519")
    payload = payload_bytes(directory, args.toolchain_id)
    with output.open("xb") as stream:
        stream.write(envelope(payload, args.key_id, key))
    print(f"Signed {args.toolchain_id} with {args.key_id}")


def verify(args):
    directory = args.dist.resolve()
    if (directory / "CANDIDATE-NOT-FOR-RELEASE.txt").exists():
        raise ValueError("candidate artifacts cannot be accepted as a release")
    raw = args.descriptor.read_bytes()
    if len(raw) > 1024 * 1024:
        raise ValueError("descriptor envelope exceeds 1 MiB")
    wrapper = json.loads(raw)
    keyring = json.loads(args.keyring.read_text(encoding="utf-8"))
    key_id = wrapper["keyID"]
    public_key = Ed25519PublicKey.from_public_bytes(
        base64.b64decode(keyring["keys"][key_id], validate=True)
    )
    payload = base64.b64decode(wrapper["payloadBase64"], validate=True)
    signature = base64.b64decode(wrapper["signatureBase64"], validate=True)
    public_key.verify(signature, DOMAIN + payload)
    value = json.loads(payload)
    if value.get("schemaVersion") != 1 or value.get("target") != "wasm32-wasip1":
        raise ValueError("unsupported toolchain descriptor")
    if not isinstance(value.get("toolchainID"), str) or not IDENTITY.fullmatch(value["toolchainID"]):
        raise ValueError("invalid toolchain ID")
    if not isinstance(value.get("rustRevision"), str) or not GIT_REV.fullmatch(value["rustRevision"]):
        raise ValueError("invalid rustRevision")
    if not isinstance(value.get("sourceLockSHA256"), str) or not SHA256.fullmatch(value["sourceLockSHA256"]):
        raise ValueError("invalid sourceLockSHA256")
    if value.get("files") != inventory(directory):
        raise ValueError("release bytes differ from the signed file inventory")
    provenance = json.loads((directory / "toolchain-provenance.json").read_text(encoding="utf-8"))
    if provenance.get("candidate") is not False or provenance.get("builderWorkingTreeDirty") is not False:
        raise ValueError("release provenance is candidate or dirty")
    if provenance.get("sourceLockSHA256") != value["sourceLockSHA256"] or provenance.get("rustRevision") != value["rustRevision"]:
        raise ValueError("release provenance differs from the signed identity")
    require_compatibility(directory)
    print(f'Verified {value["toolchainID"]} ({len(value["files"])} files)')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    signing = commands.add_parser("sign")
    signing.add_argument("--dist", type=Path, required=True)
    signing.add_argument("--toolchain-id", required=True)
    signing.add_argument("--key-id", required=True)
    signing.add_argument("--private-key", type=Path, required=True)
    checking = commands.add_parser("verify")
    checking.add_argument("--dist", type=Path, required=True)
    checking.add_argument("--descriptor", type=Path, required=True)
    checking.add_argument("--keyring", type=Path, required=True)
    args = parser.parse_args()
    try:
        sign(args) if args.command == "sign" else verify(args)
    except (OSError, ValueError, KeyError, TypeError, InvalidSignature, json.JSONDecodeError) as error:
        raise SystemExit(f"toolchain descriptor rejected: {error}") from error


if __name__ == "__main__":
    main()
