#!/usr/bin/env python3
"""Compile verified generated C for its real Apple platform, never relabel objects."""
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compile_sources(source, output, sdk, target, jobs):
    provenance = json.loads((source / 'native-source-provenance.json').read_text())
    for item in provenance['files']:
        path = source / item['path']
        if path.name != item['path'] or path.stat().st_size != item['bytes'] or digest(path) != item['sha256']:
            raise ValueError('Native source inventory mismatch: ' + item['path'])
    sdk_path = subprocess.check_output(['xcrun', '--sdk', sdk, '--show-sdk-path'], text=True).strip()
    clang = subprocess.check_output(['xcrun', '--sdk', sdk, '--find', 'clang'], text=True).strip()
    compiler_version = subprocess.check_output([clang, '--version'], text=True)
    # Native compiler traps return through explicit C setjmp scopes; C++/ObjC
    # unwinding through generated guest frames is never part of this ABI.
    # Huge wasm2c functions exceed Apple's compact-unwind offset encoding.
    # Keep frame pointers, but omit unwind tables for these C objects only.
    flags = ['-target', target, '-isysroot', sdk_path, '-I', str(source)] + provenance['flags'] + [
        '-fno-unwind-tables', '-fno-asynchronous-unwind-tables']
    identity = hashlib.sha256(json.dumps([provenance, flags, compiler_version], sort_keys=True).encode()).hexdigest()
    output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()

    def one(path):
        obj = output / (path.stem + '.o')
        marker = obj.with_suffix('.json')
        if obj.exists() and marker.exists():
            record = json.loads(marker.read_text())
            if record.get('identity') == identity and record.get('sha256') == digest(obj):
                return obj
        command = [clang, *flags, '-c', str(path), '-o', str(obj)]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        obj.with_suffix('.log').write_text(result.stdout)
        if result.returncode:
            raise RuntimeError(path.name + ': ' + result.stdout[-8000:])
        marker.write_text(json.dumps({'identity': identity, 'sha256': digest(obj), 'command': command}, indent=2) + '\n')
        print('Compiled ' + path.name, flush=True)
        return obj

    paths = sorted(source.glob('*.c'))
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as executor:
        objects = list(executor.map(one, paths))
    archive = output / 'libCrabrixNativeCompiler.a'
    subprocess.run(['xcrun', '--sdk', sdk, 'libtool', '-static', '-o', str(archive), *map(str, objects)], check=True)
    record = {'schemaVersion': 1, 'candidate': True, 'productionReplacement': False,
              'compilerWASMSHA256': provenance['compilerWASMSHA256'], 'identity': identity,
              'sdk': sdk, 'sdkPath': sdk_path, 'target': target, 'clangVersion': compiler_version,
              'flags': flags, 'archiveSHA256': digest(archive), 'seconds': time.monotonic() - started,
              'objects': [{'path': path.name, 'sha256': digest(path)} for path in objects]}
    (output / 'native-compile-provenance.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({k: record[k] for k in ['target', 'archiveSHA256', 'seconds']}, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--sdk', choices=['iphoneos', 'macosx'], required=True)
    parser.add_argument('--target', required=True)
    parser.add_argument('--jobs', type=int, default=2, choices=range(1, 5))
    args = parser.parse_args()
    if (args.sdk == 'iphoneos') != args.target.startswith('arm64-apple-ios'):
        parser.error('Target must match the actual selected platform SDK')
    compile_sources(args.source.resolve(), args.output.resolve(), args.sdk, args.target, args.jobs)
