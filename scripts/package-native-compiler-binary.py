#!/usr/bin/env python3
"""Package a real iOS static compiler and its original build records."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile


def sha(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def package(build, source, output):
    record_path = build / 'native-compile-provenance.json'
    record = json.loads(record_path.read_text())
    library = build / 'libCrabrixNativeCompiler.a'
    if record['target'] != 'arm64-apple-ios18.0' or record['sdk'] != 'iphoneos' or sha(library) != record['archiveSHA256']:
        raise ValueError('Not the recorded iOS compiler archive')
    for item in record['objects']:
        if Path(item['path']).name != item['path'] or sha(build / item['path']) != item['sha256']:
            raise ValueError('Compiled object differs from its build record')
    commands = subprocess.check_output(['xcrun', 'otool', '-l', str(library)], text=True)
    platforms = [line.strip().split()[-1] for line in commands.splitlines() if line.strip().startswith('platform ')]
    if not platforms or any(value not in ('2', 'IOS') for value in platforms):
        raise ValueError('A compiler object was not built for iOS')
    with zipfile.ZipFile(source) as archive:
        provenance_bytes = archive.read('native-source-provenance.json')
    provenance = json.loads(provenance_bytes)
    if provenance['compilerWASMSHA256'] != record['compilerWASMSHA256']:
        raise ValueError('Source archive and compiler binary have different origins')
    origin = {'schemaVersion': 1, 'candidate': True, 'productionReplacement': False,
              'compilerWASMSHA256': record['compilerWASMSHA256'],
              'sourceArchiveSHA256': sha(source),
              'sourceProvenanceSHA256': hashlib.sha256(provenance_bytes).hexdigest(),
              'staticLibrarySHA256': record['archiveSHA256']}
    if output.exists(): raise ValueError('Binary packages are immutable; use a fresh destination')
    entries = {'libCrabrixNativeCompiler.a': library,
               'native-compile-provenance.json': record_path.read_bytes(),
               'native-binary-provenance.json': (json.dumps(origin, indent=2, sort_keys=True) + '\n').encode()}
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 25, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            if isinstance(data, Path):
                with data.open('rb') as stream, archive.open(info, 'w', force_zip64=True) as target:
                    shutil.copyfileobj(stream, target, length=1024 * 1024)
            else: archive.writestr(info, data)
    return {'archiveSHA256': sha(output), 'archiveBytes': output.stat().st_size, **origin}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('build', 'source', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(package(args.build.resolve(), args.source.resolve(), args.output.resolve()), indent=2))
