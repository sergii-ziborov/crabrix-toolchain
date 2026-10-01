#!/usr/bin/env python3
"""Fail closed on unresolved or floating build inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

SHA = re.compile(r"[0-9a-f]{40}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def require_sha(value, name, errors):
    if not isinstance(value, str) or not SHA.fullmatch(value):
        errors.append(f"{name}: expected exact 40-character Git commit")


def require_digest(value, name, errors):
    if not isinstance(value, str) or not DIGEST.fullmatch(value):
        errors.append(f"{name}: expected verified SHA-256 digest")


def validate(lock, source_only=False):
    errors = []
    if lock.get("schemaVersion") != 1:
        errors.append("schemaVersion: expected 1")
    for name in ("builder", "rust"):
        item = lock.get(name, {})
        if not item.get("url", "").startswith("https://github.com/"):
            errors.append(f"{name}.url: expected HTTPS Git source")
        require_sha(item.get("revision"), f"{name}.revision", errors)
    require_sha(lock.get("backend", {}).get("revision"), "backend.revision", errors)
    patches = lock.get("backend", {}).get("patches")
    records = lock.get("patchDigests")
    if not isinstance(patches, list) or not isinstance(records, list):
        errors.append("backend.patches/patchDigests: expected lists")
    elif [item.get("path") for item in records if isinstance(item, dict)] != patches or len(records) != len(patches):
        errors.append("patchDigests: paths must match backend.patches in order")
    else:
        for item in records:
            relative = item["path"]
            if not isinstance(relative, str):
                errors.append("patchDigests.path: expected relative path")
                continue
            path = Path(relative)
            if path.is_absolute() or path.parts[:1] != ("patches",) or ".." in path.parts:
                errors.append(f"patchDigests[{relative}]: invalid path")
                continue
            require_digest(item.get("sha256"), f"patchDigests[{relative}].sha256", errors)
            source = Path(__file__).resolve().parents[1] / path
            if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != item.get("sha256"):
                errors.append(f"patchDigests[{relative}]: file missing or SHA-256 mismatch")
    submodules = lock.get("submodules", {})
    if not submodules:
        errors.append("submodules: empty")
    for path, sha in submodules.items():
        require_sha(sha, f"submodules[{path}]", errors)
    sdk = lock.get("wasiSDK", {})
    if not sdk.get("url", "").startswith("https://"):
        errors.append("wasiSDK.url: expected HTTPS")
    require_digest(sdk.get("sha256"), "wasiSDK.sha256", errors)
    bootstrap = lock.get("bootstrap", {})
    require_digest(bootstrap.get("configSourceSHA256"), "bootstrap.configSourceSHA256", errors)
    if bootstrap.get("codegenBackends") != ["cranelift"]:
        errors.append("bootstrap.codegenBackends: expected Cranelift-only compiler")
    if bootstrap.get("craneliftGlobalAssembler") != "gnu-as":
        errors.append("bootstrap.craneliftGlobalAssembler: expected pinned GNU assembler")
    if lock.get("wild", {}).get("used"):
        require_sha(lock["wild"].get("revision"), "wild.revision", errors)
    if lock.get("outputTargets") != ["wasm32-wasip1"]:
        errors.append("outputTargets: only wasm32-wasip1 is supported by this recipe")
    compiler = bootstrap.get("compiler", {})
    if not isinstance(compiler, dict) or set(compiler) != {"rustc", "rust-std", "cargo"}:
        errors.append("bootstrap.compiler: expected rustc, rust-std and cargo")
        compiler = {}
    for name, item in compiler.items():
        require_digest(item.get("sha256"), f"bootstrap.compiler.{name}.sha256", errors)
        if not item.get("url", "").startswith("https://"):
            errors.append(f"bootstrap.compiler.{name}.url: expected HTTPS")
    rustfmt = bootstrap.get("rustfmt", {})
    if rustfmt.get("date") != bootstrap.get("compilerDate"):
        errors.append("bootstrap.rustfmt.date: expected matching pinned stage0 date")
    fmt_components = rustfmt.get("components", {})
    if not isinstance(fmt_components, dict) or set(fmt_components) != {"rustfmt", "rustc"}:
        errors.append("bootstrap.rustfmt.components: expected rustfmt and matching rustc")
        fmt_components = {}
    for name, item in fmt_components.items():
        require_digest(item.get("sha256"), f"bootstrap.rustfmt.{name}.sha256", errors)
        if not item.get("url", "").startswith("https://static.rust-lang.org/dist/"):
            errors.append(f"bootstrap.rustfmt.{name}.url: expected HTTPS Rust dist")
    llvm = bootstrap.get("llvm", {})
    if llvm.get("mode") == "ci-prebuilt":
        require_sha(llvm.get("sourceCommit"), "bootstrap.llvm.sourceCommit", errors)
        require_digest(llvm.get("sha256"), "bootstrap.llvm.sha256", errors)
        if llvm.get("availability") != "verified":
            errors.append("bootstrap.llvm: archive availability is not verified")
    elif llvm.get("mode") in ("source", "disabled"):
        if not submodules.get("src/llvm-project"):
            errors.append("bootstrap.llvm: LLVM source submodule is missing")
        require_sha(llvm.get("sourceCommit"), "bootstrap.llvm.sourceCommit", errors)
        if llvm.get("sourceCommit") != submodules.get("src/llvm-project"):
            errors.append("bootstrap.llvm.sourceCommit: must match pinned LLVM submodule")
        if llvm.get("mode") == "source" and llvm.get("targets") != ["X86", "WebAssembly"]:
            errors.append("bootstrap.llvm.targets: expected X86 and WebAssembly")
    else:
        errors.append("bootstrap.llvm.mode: expected ci-prebuilt, source, or disabled")
    if lock.get("packagingFormatVersion") != 1:
        errors.append("packagingFormatVersion: expected 1")
    if source_only:
        return errors
    environment = lock.get("buildEnvironment", {})
    require_digest(environment.get("imageDigest"), "buildEnvironment.imageDigest", errors)
    versions = environment.get("hostToolVersions")
    if not isinstance(versions, dict) or not versions or any(
        not isinstance(name, str) or not isinstance(version, str) or not version
        for name, version in versions.items()
    ):
        errors.append("buildEnvironment.hostToolVersions: expected nonempty tool/version map")
    return errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, default=Path(__file__).resolve().parents[1] / "toolchain.lock.json")
    parser.add_argument("--source-only", action="store_true")
    args = parser.parse_args()
    errors = validate(json.loads(args.lock.read_text()), source_only=args.source_only)
    if errors:
        for error in errors:
            print(f"lock error: {error}", file=sys.stderr)
        return 1
    print("Source inputs pinned" if args.source_only else "Release build inputs locked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
