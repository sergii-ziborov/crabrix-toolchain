#!/usr/bin/env python3
"""Compare two raw toolchain packages, including Wasm sections and sysroot files."""

import argparse
import filecmp
import hashlib
import json
from pathlib import Path
import zipfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def digest_file(path):
    value = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def uleb(data, offset):
    result = 0
    for shift in range(0, 70, 7):
        if offset >= len(data):
            raise ValueError("truncated Wasm LEB128")
        byte = data[offset]
        offset += 1
        result |= (byte & 0x7f) << shift
        if byte < 0x80:
            return result, offset
    raise ValueError("invalid Wasm LEB128")


def sections(path):
    data = path.read_bytes()
    if data[:8] != b"\0asm\1\0\0\0":
        raise ValueError(f"invalid Wasm header: {path}")
    records = []
    offset = 8
    while offset < len(data):
        kind = data[offset]
        size, start = uleb(data, offset + 1)
        end = start + size
        if end > len(data):
            raise ValueError("truncated Wasm section")
        name = None
        if kind == 0:
            length, begin = uleb(data, start)
            if begin + length > end:
                raise ValueError("truncated Wasm custom section name")
            name = data[begin:begin + length].decode("utf-8", "replace")
        records.append({"kind": kind, "name": name, "bytes": size,
                        "sha256": digest(memoryview(data)[start:end])})
        offset = end
    return records


def zip_entries(path):
    with zipfile.ZipFile(path) as archive:
        return {entry.filename: {"bytes": entry.file_size,
                                 "sha256": digest(archive.read(entry))}
                for entry in archive.infolist()}


def compare(first, second):
    compiler_first = first / "rustc.wasm"
    compiler_second = second / "rustc.wasm"
    archive_first = first / "sysroot-wasip1.zip"
    archive_second = second / "sysroot-wasip1.zip"
    compiler_a = sections(compiler_first)
    compiler_b = sections(compiler_second)
    section_differences = []
    for index in range(max(len(compiler_a), len(compiler_b))):
        a = compiler_a[index] if index < len(compiler_a) else None
        b = compiler_b[index] if index < len(compiler_b) else None
        if a != b:
            section_differences.append({"index": index, "first": a, "second": b})
    zip_a = zip_entries(archive_first)
    zip_b = zip_entries(archive_second)
    sysroot_differences = [
        {"path": name, "first": zip_a.get(name), "second": zip_b.get(name)}
        for name in sorted(set(zip_a) | set(zip_b)) if zip_a.get(name) != zip_b.get(name)
    ]
    return {
        "first": {"compilerSHA256": digest_file(compiler_first),
                  "sysrootArchiveSHA256": digest_file(archive_first)},
        "second": {"compilerSHA256": digest_file(compiler_second),
                   "sysrootArchiveSHA256": digest_file(archive_second)},
        "compilerSectionDifferences": section_differences,
        "sysrootFileDifferences": sysroot_differences,
        "sysrootArchiveRawMatch": filecmp.cmp(archive_first, archive_second, shallow=False),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.write_text(json.dumps(compare(args.first, args.second), indent=2,
                                   sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
