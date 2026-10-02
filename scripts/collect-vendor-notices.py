#!/usr/bin/env python3
"""Make a deterministic notice archive for all pinned vendored Rust inputs."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tomllib
import zipfile


# These are the exact license expressions among pinned vendor packages that
# ship no separate root notice file. A new expression requires an audit.
STANDARD_FOR_EXPRESSION = {
    "MIT": ("MIT",),
    "MIT OR Apache-2.0": ("MIT", "Apache-2.0"),
    "Apache-2.0 OR MIT": ("Apache-2.0", "MIT"),
    "MIT/Apache-2.0": ("MIT", "Apache-2.0"),
    "MIT / Apache-2.0": ("MIT", "Apache-2.0"),
    "Apache-2.0/MIT": ("Apache-2.0", "MIT"),
    "Apache-2.0": ("Apache-2.0",),
    "Apache-2.0 WITH LLVM-exception": ("Apache-2.0", "LLVM-exception"),
    "Apache-2.0 WITH LLVM-exception OR Apache-2.0 OR MIT":
        ("Apache-2.0", "LLVM-exception", "MIT"),
    "Zlib OR Apache-2.0 OR MIT": ("Zlib", "Apache-2.0", "MIT"),
    "MPL-2.0": ("MPL-2.0",),
    "MPL-2.0+": ("MPL-2.0",),
    "MIT OR Apache-2.0 OR LGPL-2.1-or-later":
        ("MIT", "Apache-2.0", "LGPL-2.1-or-later"),
    "BSD-3-Clause": ("BSD-3-Clause",),
    "Apache-2.0 OR GPL-2.0-only": ("Apache-2.0", "GPL-2.0-only"),
}

# SPDX license-list-data v3.29.0 at 31ba1a50e5397e00a304dbadc76531740e89ee48.
# The standard texts are pinned inputs, rather than content downloaded at
# release time or silently substituted for a package-specific notice.
STANDARD_SHA256 = {
    "Apache-2.0": "074e6e32c86a4c0ef8b3ed25b721ca23aca83df277cd88106ef7177c354615ff",
    "BSD-3-Clause": "5a93d5831e1297ab10fe643e1a631e83be392896da14ee2951285a79012df69d",
    "GPL-2.0-only": "aaf135472f81c5b4a0dca9367e5bb5e9750032b5bebe5442b36e4c0a47430df3",
    "LGPL-2.1-or-later": "5749785c8bdefafcb5d798270ed0a967036fe2ca63dcedade1627565dfef81d2",
    "LLVM-exception": "e34c58338bd89d43e709e226610d8f32b3e3c47f4ad9a99a8dc1d4ac7842488e",
    "MIT": "b05785f9f18e6716bab63424b11454513b9943a222595b70411009202fc592b5",
    "MPL-2.0": "66a3107d5ad6a058aab753eaac2047ccb2ed0e39465dd0fe5844da3e300d5172",
    "Zlib": "bfb1112d49db5b1daecdfef24bd7e2f3ea0bafb33aa67aa0ab51e2bf8407c03d",
}

# WebAssembly/wasi-libc 2fc32bc81b9f07f8d9525edea59bfbaf760c06d6.
EXTRA_SHA256 = {
    "WASI-LIBC-CLOUDLIBC-LICENSE.txt": "c8b789cf5a746611e6300a0cc7750dbf92b61912a709d04e639245f7290656d0",
    "WASI-LIBC-MUSL-COPYRIGHT.txt": "f9bc4423732350eb0b3f7ed7e91d530298476f8fec0c6c427a1c04ade22655af",
    "WASI-LIBC-MUSL-FTS-COPYING.txt": "55af87e4017668f54467a3380e7ebbac5e672d8c763bfe95e6fc882a6fdc4046",
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vendor", type=Path, required=True)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--extra-notices", type=Path, required=True)
    parser.add_argument("--standard-licenses", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit(f"refusing to replace an existing notice archive: {args.out}")
    lock_bytes = args.lock.read_bytes()
    lock = json.loads(lock_bytes)
    rust_revision = lock["rust"]["revision"]
    if not re.fullmatch(r"[0-9a-f]{40}", rust_revision):
        raise SystemExit("source lock has no exact Rust revision")
    checked_out = subprocess.check_output(
        ["git", "-C", str(args.vendor.parent), "rev-parse", "HEAD"], text=True
    ).strip()
    if checked_out != rust_revision:
        raise SystemExit("vendored Rust tree differs from the source lock")
    records = []
    files = {}
    expected_standard = {license_id + ".txt" for values in
                         STANDARD_FOR_EXPRESSION.values() for license_id in values}
    if set(STANDARD_SHA256) != {name.removesuffix(".txt") for name in expected_standard}:
        raise SystemExit("pinned SPDX standard license set needs an audit")
    actual_standard = {path.name for path in args.standard_licenses.iterdir()}
    if actual_standard != expected_standard:
        raise SystemExit("SPDX standard license input set differs from pinned audit")
    standard_records = {}
    for license_id in sorted(name.removesuffix(".txt") for name in expected_standard):
        source = args.standard_licenses / (license_id + ".txt")
        if not source.is_file() or source.is_symlink():
            raise SystemExit(f"invalid SPDX standard license input: {license_id}")
        data = source.read_bytes()
        if digest(data) != STANDARD_SHA256[license_id]:
            raise SystemExit(f"SPDX standard license input differs: {license_id}")
        path = f"licenses/standard/{source.name}"
        files[path] = data
        standard_records[license_id] = {"path": path, "bytes": len(data),
                                        "sha256": digest(data)}
    metadata_only = 0
    for package in sorted(args.vendor.iterdir()):
        manifest = package / "Cargo.toml"
        if not manifest.is_file():
            continue
        if package.is_symlink():
            raise SystemExit(f"symlink vendored package: {package}")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*", package.name):
            raise SystemExit(f"invalid vendored package path: {package.name}")
        meta = tomllib.loads(manifest.read_text())["package"]
        notices = []
        for item in sorted(package.iterdir()):
            if not item.name.upper().startswith(("LICENSE", "COPYRIGHT", "NOTICE")):
                continue
            if item.is_symlink():
                raise SystemExit(f"symlink notice: {item}")
            if not item.is_file():
                continue
            data = item.read_bytes()
            entry = f"licenses/vendor/{package.name}/{item.name}"
            files[entry] = data
            notices.append({"path": entry, "bytes": len(data), "sha256": digest(data)})
        license_file = meta.get("license-file")
        if license_file:
            logical = PurePosixPath(license_file)
            if logical.is_absolute() or "\\" in license_file or any(
                part in ("", ".", "..") for part in license_file.split("/")
            ):
                raise SystemExit(f"invalid declared license path: {package.name}")
            source = package.joinpath(*logical.parts)
            if not source.is_file() or source.is_symlink():
                raise SystemExit(f"declared license file is unavailable: {package.name}")
            if not source.resolve().is_relative_to(package.resolve()):
                raise SystemExit(f"declared license path escapes package: {package.name}")
            entry = f"licenses/vendor/{package.name}/{logical.as_posix()}"
            if entry not in files:
                data = source.read_bytes()
                files[entry] = data
                notices.append({"path": entry, "bytes": len(data), "sha256": digest(data)})
        if not notices and not meta.get("license"):
            raise SystemExit(f"missing license metadata and notice: {package.name}")
        notice_source = "vendored-file"
        if not notices:
            license_ids = STANDARD_FOR_EXPRESSION.get(meta["license"])
            if license_ids is None:
                raise SystemExit(f"unreviewed metadata-only license expression: {package.name}")
            notices = [standard_records[license_id] for license_id in license_ids]
            notice_source = "SPDX-standard-text-for-declared-expression"
            metadata_only += 1
        records.append({
            "directory": package.name,
            "name": meta["name"],
            "version": meta["version"],
            "licenseExpression": meta.get("license"),
            "noticeFiles": notices,
            "noticeSource": notice_source,
        })
    extras = []
    if {item.name for item in args.extra_notices.iterdir()} != set(EXTRA_SHA256):
        raise SystemExit("WASI libc source notice set differs from pinned audit")
    for item in sorted(args.extra_notices.iterdir()):
        if not item.is_file() or item.is_symlink() or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]*", item.name
        ):
            raise SystemExit(f"invalid extra source notice: {item}")
        data = item.read_bytes()
        if digest(data) != EXTRA_SHA256[item.name]:
            raise SystemExit(f"WASI libc source notice differs: {item.name}")
        entry = f"licenses/source-notices/{item.name}"
        files[entry] = data
        extras.append({"path": entry, "bytes": len(data), "sha256": digest(data)})
    if not extras:
        raise SystemExit("pinned source notices are missing")
    index = (json.dumps({
        "schemaVersion": 1,
        "scope": "all vendored Rust build inputs",
        "rustRevision": rust_revision,
        "sourceLockSHA256": digest(lock_bytes),
        "packageCount": len(records),
        "metadataOnlyPackageCount": metadata_only,
        "noticeFileCount": len(files),
        "standardLicenses": standard_records,
        "standardLicenseSource": "spdx/license-list-data v3.29.0, commit 31ba1a50e5397e00a304dbadc76531740e89ee48",
        "wasiLibcRevision": lock["wasiSDK"]["sourceSubmodules"]["src/wasi-libc"],
        "sourceNotices": extras,
        "packages": records,
    }, sort_keys=True, separators=(",", ":")) + "\n").encode()
    files["licenses/vendor-index.json"] = index
    with zipfile.ZipFile(args.out, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9, strict_timestamps=True) as archive:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, files[name], compress_type=zipfile.ZIP_DEFLATED,
                             compresslevel=9)
    print(len(records), "vendored packages;", len(files)-1, "notice files;", digest(args.out.read_bytes()))


if __name__ == "__main__":
    main()
