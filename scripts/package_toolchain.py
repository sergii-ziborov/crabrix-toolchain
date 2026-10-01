#!/usr/bin/env python3
"""Package an already source-built compiler and WASI sysroot reproducibly."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
WORK = Path(os.environ.get("CRABRIX_TOOLCHAIN_WORK", ROOT / "work"))
RUST = WORK / "rust"
CANDIDATE = os.environ.get("CRABRIX_TOOLCHAIN_CANDIDATE") == "1"
STRIP_EXPERIMENT = os.environ.get("CRABRIX_TOOLCHAIN_STRIP_EXPERIMENT") == "1"
OUT = Path(os.environ.get("CRABRIX_TOOLCHAIN_OUT", ROOT / "dist"))
CRATES = {
    "std", "core", "alloc", "compiler_builtins", "panic_abort", "panic_unwind", "wasi",
    "cfg_if", "rustc_demangle", "std_detect", "hashbrown", "rustc_std_workspace_core",
    "rustc_std_workspace_alloc", "miniz_oxide", "adler2", "unwind", "libc", "test",
    "getopts", "unicode_width", "rustc_std_workspace_std",
}


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_sysroot_archive(files, destination):
    """Write the app-readable manifest and return a per-file byte inventory."""
    prefix = "sysroot-wasip1/"
    manifest = (json.dumps({"files": sorted(files)}, sort_keys=True,
                           separators=(",", ":")) + "\n").encode("utf-8")
    inventory = [
        {"path": prefix + name, "bytes": path.stat().st_size, "sha256": digest(path)}
        for name, path in sorted(files.items())
    ]
    inventory.append({"path": prefix + "manifest.json", "bytes": len(manifest),
                      "sha256": hashlib.sha256(manifest).hexdigest()})
    inventory.sort(key=lambda item: item["path"])
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9, strict_timestamps=True) as archive:
        for name in sorted([*files, "manifest.json"]):
            data = manifest if name == "manifest.json" else files[name].read_bytes()
            info = zipfile.ZipInfo(prefix + name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED,
                             compresslevel=9)
    return inventory


def main():
    if STRIP_EXPERIMENT and not CANDIDATE:
        raise SystemExit("debug-section stripping is candidate-only until app gates pass")
    if CANDIDATE and OUT.resolve() != (WORK / "candidate-artifacts").resolve():
        raise SystemExit("candidate artifacts must stay in the work directory")
    if not CANDIDATE and OUT.resolve() != (ROOT / "dist").resolve():
        raise SystemExit("release artifacts must use the dist directory")
    if not RUST.is_dir():
        raise SystemExit("run fetch-sources.sh and build-toolchain.sh first")
    # The pinned bootstrap config installs into ./dist. Select that exact output,
    # never a stage0 compiler or a stale dry-run/build artifact found by a glob.
    compiler = RUST / "dist/bin/rustc.wasm"
    if not compiler.is_file() or compiler.is_symlink():
        raise SystemExit(f"installed source-built rustc.wasm is missing: {compiler}")
    with compiler.open("rb") as stream:
        magic = stream.read(8)
    if magic != b"\0asm\1\0\0\0":
        raise SystemExit("rustc.wasm has invalid Wasm header")
    lib = RUST / "build/x86_64-unknown-linux-gnu/stage1/lib/rustlib/wasm32-wasip1/lib"
    if not lib.is_dir() or lib.is_symlink():
        raise SystemExit(f"source-built stage1 WASI library is missing: {lib}")
    if OUT.exists() and any(OUT.iterdir()):
        raise SystemExit("dist must be empty; existing release files are immutable")
    OUT.mkdir(exist_ok=True)
    if STRIP_EXPERIMENT:
        subprocess.run([
            sys.executable, str(ROOT / "scripts/strip-wasm-custom.py"),
            str(compiler), str(OUT / "rustc.wasm"),
        ], check=True)
    else:
        shutil.copyfile(compiler, OUT / "rustc.wasm")
    files = {}
    for path in sorted(lib.rglob("*")):
        if path.is_symlink():
            raise SystemExit(f"sysroot symlink rejected: {path}")
        if not path.is_file():
            continue
        name = path.name
        if path.parent == lib:
            if not name.startswith("lib") or not name.endswith((".rlib", ".rmeta")):
                continue
            crate = name[3:].split("-", 1)[0]
            if crate not in CRATES:
                continue
        elif path.parent == lib / "self-contained":
            if name not in {"crt1-command.o", "libc.a"}:
                continue
        else:
            continue
        rel = path.relative_to(lib).as_posix()
        files[f"lib/rustlib/wasm32-wasip1/lib/{rel}"] = path
    if not any(p.startswith("lib/rustlib/wasm32-wasip1/lib/libstd-") for p in files):
        raise SystemExit("std rlib is missing")
    if "lib/rustlib/wasm32-wasip1/lib/self-contained/crt1-command.o" not in files:
        raise SystemExit("self-contained WASI crt is missing")
    inventory = {"schemaVersion": 1,
                 "files": write_sysroot_archive(files, OUT / "sysroot-wasip1.zip")}
    (OUT / "sysroot-files.json").write_text(json.dumps(inventory, indent=2) + "\n")
    # BundledSysroot.prepare compares this file byte-for-byte with the digest.
    # Keep the app's existing 64-byte checksum convention: no trailing newline.
    (OUT / "sysroot-wasip1.sha256").write_text(digest(OUT / "sysroot-wasip1.zip"))
    lock = json.loads((ROOT / "toolchain.lock.json").read_text())
    builder_commit = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
    ).strip()
    builder_dirty = bool(subprocess.check_output(
        ["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=normal"],
        text=True,
    ).strip())
    provenance = {"schemaVersion": 1, "sourceLockSHA256": digest(ROOT / "toolchain.lock.json"),
                  "rustRevision": lock["rust"]["revision"],
                  "rustVersion": lock["rust"]["actualVersion"],
                  "builderUpstreamRevision": lock["builder"]["revision"],
                  "builderSourceCommit": builder_commit,
                  "builderWorkingTreeDirty": builder_dirty,
                  "outputTarget": "wasm32-wasip1", "stripApplied": STRIP_EXPERIMENT,
                  "candidate": CANDIDATE}
    if STRIP_EXPERIMENT:
        provenance["stripInputSHA256"] = digest(compiler)
        provenance["stripPolicy"] = "remove name and .debug_*; retain producers"
    (OUT / "toolchain-provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    if CANDIDATE:
        (OUT / "CANDIDATE-NOT-FOR-RELEASE.txt").write_text(
            "Trial output from incomplete release-environment lock. Do not publish or bundle in a release.\n"
        )
    sums = [f"{digest(p)}  {p.name}" for p in sorted(OUT.iterdir()) if p.is_file()]
    (OUT / "SHA256SUMS").write_text("\n".join(sums) + "\n")
    print(f"Packaged {len(files)} verified source-built WASI sysroot files")


if __name__ == "__main__":
    main()
