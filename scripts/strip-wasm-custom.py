#!/usr/bin/env python3
"""Make a test-only size candidate by removing Wasm name and debug sections.

Every retained section is copied byte for byte. In particular, producers,
target_features, and executable sections stay intact. Compatibility and trap
diagnostics must be checked before this output is used by a release packager.
"""

import argparse
from pathlib import Path


MAGIC = b"\0asm\1\0\0\0"
CHUNK = 1024 * 1024


def read_uleb32(stream):
    raw = bytearray()
    value = 0
    for shift in range(0, 35, 7):
        byte = stream.read(1)
        if not byte:
            raise ValueError("truncated Wasm section length")
        part = byte[0]
        raw.extend(byte)
        if shift == 28 and part > 15:
            raise ValueError("Wasm section length exceeds u32")
        value |= (part & 127) << shift
        if not part & 128:
            return value, bytes(raw)
    raise ValueError("Wasm section length is overlong")


def strip(source: Path, destination: Path):
    source = Path(source)
    destination = Path(destination)
    if source.resolve() == destination.resolve():
        raise ValueError("input and output must be different files")
    if not source.is_file() or source.is_symlink():
        raise ValueError("input must be a regular Wasm file")
    if destination.exists():
        raise ValueError("output already exists")

    source_size = source.stat().st_size
    dropped = []
    created = False
    try:
        with source.open("rb") as incoming, destination.open("xb") as outgoing:
            created = True
            if incoming.read(8) != MAGIC:
                raise ValueError("invalid Wasm header")
            outgoing.write(MAGIC)
            while incoming.tell() < source_size:
                section_id = incoming.read(1)
                if not section_id:
                    raise ValueError("truncated Wasm section identifier")
                size, size_bytes = read_uleb32(incoming)
                payload_start = incoming.tell()
                payload_end = payload_start + size
                if payload_end > source_size:
                    raise ValueError("Wasm section exceeds input size")
                name = None
                if section_id == b"\0":
                    name_size, _ = read_uleb32(incoming)
                    if incoming.tell() + name_size > payload_end:
                        raise ValueError("Wasm custom section name exceeds payload")
                    name = incoming.read(name_size).decode("utf-8")
                if name == "name" or (name is not None and name.startswith(".debug_")):
                    dropped.append((name, 1 + len(size_bytes) + size))
                    incoming.seek(payload_end)
                    continue
                outgoing.write(section_id + size_bytes)
                incoming.seek(payload_start)
                remaining = size
                while remaining:
                    block = incoming.read(min(CHUNK, remaining))
                    if not block:
                        raise ValueError("truncated Wasm section payload")
                    outgoing.write(block)
                    remaining -= len(block)
        return dropped
    except Exception:
        if created:
            destination.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    dropped = strip(args.source, args.destination)
    removed = sum(size for _, size in dropped)
    print(f"removed {removed} bytes in {len(dropped)} name/debug sections; "
          f"output {args.destination.stat().st_size} bytes")


if __name__ == "__main__":
    main()
