#!/usr/bin/env python3
"""Actions-only pre-deployment identity gate; not a deployment verdict."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import zipfile

def need(ok, reason):
    if not ok:
        raise ValueError(reason)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def macho(data, expected_kind):
    need(len(data) >= 32, 'macho-truncated')
    magic, cpu, subtype, kind, count, size, flags, reserved = struct.unpack_from('<8I', data)
    need(magic == 0xfeedfacf and cpu == 0x100000c, 'macho-cpu')
    need(kind == expected_kind, 'macho-kind')
    need(32 + size <= len(data), 'macho-commands')
    pos, platforms = 32, []
    for _ in range(count):
        need(pos + 8 <= 32 + size, 'macho-command-header')
        cmd, length = struct.unpack_from('<II', data, pos)
        need(length >= 8 and pos + length <= 32 + size, 'macho-command-size')
        if cmd == 0x32:
            need(length >= 24, 'macho-build-version')
            platforms.append(struct.unpack_from('<I', data, pos + 8)[0])
        pos += length
    need(pos == 32 + size and platforms == [7], 'macho-platform')
    return {'cpu': cpu, 'platform': platforms[0], 'kind': kind}

def elf(data):
    need(len(data) >= 64 and data[:6] == b'\x7fELF\x02\x01', 'elf-header')
    kind, machine = struct.unpack_from('<HH', data, 16)
    need(kind == 3 and machine == 62, 'elf-machine')
    return {'class': 64, 'machine': machine, 'kind': kind}

def verify(root, manifest, target, source, sdk):
    need(os.environ.get('GITHUB_ACTIONS') == 'true', 'actions-only')
    need(not Path(root).is_symlink(), 'symlink')
    root = Path(root).resolve()
    need(manifest.get('target') == target, 'target')
    need(manifest.get('source_sha') == source, 'source')
    need(manifest.get('sdk_version') == sdk, 'sdk')
    def read(name):
        p = (root / name).resolve()
        need(p.is_relative_to(root) and p.is_file(), 'missing-file')
        return p.read_bytes()
    files = manifest.get('files', {})
    need(files, 'empty-inventory')
    paths = list(root.rglob('*'))
    need(not any(p.is_symlink() for p in paths), 'symlink')
    metadata = set(manifest.get('metadata_files', []))
    need(metadata <= {'manifest.json', 'SHA256SUMS'}, 'metadata')
    actual_files = {str(p.relative_to(root)) for p in paths if p.is_file()}
    need(actual_files == set(files) | metadata, 'actual-inventory')
    for name, record in files.items():
        raw = read(name)
        need(digest(raw) == record.get('sha256') and len(raw) == record.get('bytes'), 'outer-hash')
    need('build.json' in files, 'missing-producer')
    producer = json.loads(read('build.json'))
    need(producer.get('source_sha') == source, 'producer-source')
    need(producer.get('sdk_version') == sdk, 'producer-sdk')
    observations = {}
    if target in ('iphone', 'ipad'):
        need(producer.get('platform') == 'simulator', 'producer-platform')
        need(producer.get('target') == 'arm64-apple-ios15.0-simulator', 'producer-target')
        original = producer.get('files')
        need(isinstance(original, dict) and original, 'producer-inventory')
        actual = {n[len('EXReader.app/'):] for n in files if n.startswith('EXReader.app/')}
        need(actual == set(original), 'producer-inventory')
        for name, sha in original.items():
            need(digest(read('EXReader.app/' + name)) == sha, 'producer-hash')
        need('EXReader' in original, 'missing-entry')
        binaries = ['EXReader'] + [n for n in original if n.endswith('.dylib')]
        need(len(binaries) > 1, 'missing-sdk-runtime')
        for name in binaries:
            observations[name] = macho(read('EXReader.app/' + name), 2 if name == 'EXReader' else 6)
    else:
        need(target == 'android' and producer.get('abi') == 'x86_64', 'producer-abi')
        artifacts = producer.get('artifacts', {})
        name = 'app-debug.apk'
        need(name in artifacts, 'producer-artifact')
        raw = read('artifacts/' + name)
        need(digest(raw) == artifacts[name].get('sha256'), 'producer-hash')
        with zipfile.ZipFile(io.BytesIO(raw)) as apk:
            names = apk.namelist()
            need(len(names) == len(set(names)), 'duplicate-apk-entry')
            for lib in ('product', '', 'jni', 'host'):
                path = 'lib/x86_64/libexreader' + ('_' + lib if lib else '') + '.so'
                need(path in names, 'missing-sdk-runtime')
                observations[path] = elf(apk.read(path))
    return {'accepted': True, 'target': target, 'source_sha': source,
            'sdk_version': sdk, 'observations': observations,
            'scope': 'identity-only; no deployment acceptance'}

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', required=True)
    p.add_argument('--manifest', required=True)
    p.add_argument('--target', required=True, choices=['android','iphone','ipad'])
    p.add_argument('--source', required=True)
    p.add_argument('--sdk', required=True)
    p.add_argument('--output', required=True)
    a = p.parse_args()
    result = verify(a.root, json.loads(Path(a.manifest).read_text()), a.target, a.source, a.sdk)
    Path(a.output).write_text(json.dumps(result, indent=2) + '\n')
if __name__ == '__main__':
    main()
