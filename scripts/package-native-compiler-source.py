#!/usr/bin/env python3
"""Package two matching compiler translations as an immutable app build input.

The archive contains source, never loadable iOS code. It is fetched only on the
build Mac; the app itself neither downloads nor translates its compiler.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(source):
    record = json.loads((source / 'native-source-provenance.json').read_text())
    files = record['files']
    names = set()
    for item in files:
        name = item['path']
        if Path(name).name != name or name in names or not (source / name).is_file() or (source / name).is_symlink():
            raise ValueError('Invalid native source file: ' + name)
        names.add(name)
        if (source / name).stat().st_size != item['bytes'] or digest(source / name) != item['sha256']:
            raise ValueError('Native source inventory differs: ' + name)
    if {item.name for item in source.iterdir()} != names | {'native-source-provenance.json'}:
        raise ValueError('Native source directory has undeclared entries')
    if not record.get('checkpointCount') or record['compilerWASMSHA256'] != record['sourceBuildProvenance']['compilerSHA256']:
        raise ValueError('Native compiler is not bound to its WASM source')
    return record


def package(first, repeat, output):
    a, b = verify(first), verify(repeat)
    if a['sourceBuildProvenance']['cloudBuildID'] == b['sourceBuildProvenance']['cloudBuildID']:
        raise ValueError('Independent compiler origins are required')
    fields = ('compilerWASMSHA256', 'wabtArchiveSHA256', 'generatorSHA256', 'flags', 'checkpointCount', 'limits', 'files')
    optional = ('checkpointInstrumenterSHA256', 'checkpointPolicy', 'checkpointCounts')
    if any(a[key] != b[key] for key in fields) or any(a.get(key) != b.get(key) for key in optional):
        raise ValueError('Independent compiler translations differ')
    if output.exists(): raise ValueError('Native source packages are immutable; use a fresh output')
    root = Path(__file__).resolve().parents[1]
    proof = {'schemaVersion': 1, 'candidate': True, 'productionReplacement': False,
             'compilerWASMSHA256': a['compilerWASMSHA256'],
             'nativeSourceMatch': True,
             'independentCloudBuildIDs': sorted([a['sourceBuildProvenance']['cloudBuildID'], b['sourceBuildProvenance']['cloudBuildID']]),
             'nativeProvenanceSHA256': [digest(source / 'native-source-provenance.json') for source in (first, repeat)]}
    readme = ("Crabrix bundled compiler source build input.\n"
        "Generated from the independently reproducible WASM compiler with WABT 1.0.42.\n"
        "Crabrix modifies the generated compiler by adding work, cancellation and stack checkpoints.\n"
        "Copied WABT runtime C files are wrapped in TARGET_OS_SIMULATOR guards.\n"
        "All original runtime copyright notices remain in their source files.\n"
        "WABT runtime license: WABT-LICENSE.txt (Apache-2.0).\n"
        "Rust and its compiler dependencies retain their separately published source-built toolchain notices.\n"
        "This source archive alone is not a production or performance qualification.\n"
        "Build only with the actual destination Apple SDK; never relabel host objects as iOS.\n")
    entries = {item['path']: first / item['path'] for item in a['files']}
    entries['native-source-provenance.json'] = (first / 'native-source-provenance.json').read_bytes()
    entries['native-source-repeat-provenance.json'] = (repeat / 'native-source-provenance.json').read_bytes()
    entries['native-source-reproducibility.json'] = (json.dumps(proof, indent=2, sort_keys=True) + '\n').encode()
    entries['WABT-LICENSE.txt'] = (root / 'native-compiler/WABT-LICENSE.txt').read_bytes()
    entries['BUILD-README.txt'] = readme.encode()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 25, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            if isinstance(data, Path):
                with archive.open(info, 'w', force_zip64=True) as destination, data.open('rb') as source:
                    shutil.copyfileobj(source, destination, length=1024 * 1024)
            else:
                archive.writestr(info, data)
    return {'compilerWASMSHA256': a['compilerWASMSHA256'], 'archiveSHA256': digest(output),
            'archiveBytes': output.stat().st_size, 'files': len(entries)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('first', 'repeat', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(package(args.first.resolve(), args.repeat.resolve(), args.output.resolve()), indent=2))
