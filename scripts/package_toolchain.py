#!/usr/bin/env python3
"""Package an already source-built compiler and WASI sysroot reproducibly."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
WORK = Path(__import__("os").environ.get("CRABRIX_TOOLCHAIN_WORK", ROOT / "work"))
RUST = WORK / "rust"
OUT = ROOT / "dist"
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


def unique(paths, description):
    candidates = sorted(set(paths))
    if len(candidates) != 1:
        raise SystemExit(f"expected one {description}, found {len(candidates)}: {candidates[:4]}")
    return candidates[0]


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
    if not RUST.is_dir():
        raise SystemExit("run fetch-sources.sh and build-toolchain.sh first")
    compiler = unique((p for p in RUST.glob("build/**/rustc.wasm")
                       if "stage2" in p.parts or "dist" in p.parts), "source-built rustc.wasm")
    with compiler.open("rb") as stream:
        magic = stream.read(8)
    if magic != b"\0asm\1\0\0\0":
        raise SystemExit("rustc.wasm has invalid Wasm header")
    lib = unique((p for p in RUST.glob("build/**/stage1/lib/rustlib/wasm32-wasip1/lib")
                  if p.is_dir()), "stage1 wasm32-wasip1 library")
    if OUT.exists() and any(OUT.iterdir()):
        raise SystemExit("dist must be empty; existing release files are immutable")
    OUT.mkdir(exist_ok=True)
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
    (OUT / "sysroot-wasip1.sha256").write_text(digest(OUT / "sysroot-wasip1.zip") + "\n")
    lock = json.loads((ROOT / "toolchain.lock.json").read_text())
    provenance = {"schemaVersion": 1, "sourceLockSHA256": digest(ROOT / "toolchain.lock.json"),
                  "rustRevision": lock["rust"]["revision"],
                  "rustVersion": lock["rust"]["actualVersion"],
                  "builderRevision": lock["builder"]["revision"],
                  "outputTarget": "wasm32-wasip1", "stripApplied": False}
    (OUT / "toolchain-provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    sums = [f"{digest(p)}  {p.name}" for p in sorted(OUT.iterdir()) if p.is_file()]
    (OUT / "SHA256SUMS").write_text("\n".join(sums) + "\n")
    print(f"Packaged {len(files)} verified source-built WASI sysroot files")


if __name__ == "__main__":
    main()
