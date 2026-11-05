# SPDX-License-Identifier: MIT
"""K03 package intake: authenticate the original A artifact and the fresh B package, then unpack both
into separate program directories whose paths contain spaces and non-ASCII characters.

Actions only. A is consumed byte-for-byte from artifact 12811449234; nothing is rebuilt for it.
usage: install.py --a-zip FILE --b-dir build/f06/linux --root DIR --evidence DIR
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
A_SOURCE = '8f8acf3234cba747165f001c0c96efe1b911e6ad'
A_ARTIFACT = dict(id=12811449234, name='f06-linux-40678657371-1', run=40678657371, attempt=1, bytes=18545727,
                  sha256='be3a91161939b3b61bce041feaa06679d03120af9f53abea02bab141d5665641')
B_BASELINE = '8232e91cd7b9296dfcdd3096b96317eb3fa1008a'
PROGRAMS = 'K03 程序 目录'
A_DIR, B_DIR = 'A 旧版 EXReader', 'B 新版 EXReader'


def sha(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def tree(path):
    return {p.relative_to(path).as_posix(): dict(sha256=sha(p), bytes=p.stat().st_size, mode=oct(p.stat().st_mode & 0o7777))
            for p in sorted(path.rglob('*')) if p.is_file() and not p.is_symlink()}


def unpack(label, delivery, into, evidence):
    """Uses the shipped unpack tool: manifest, archive digest, every file, SHA256SUMS."""
    archives = sorted(delivery.glob('EXReader-*.zip'))
    assert len(archives) == 1, (label, archives)
    report = evidence / f'unpack-{label}.json'
    subprocess.run([sys.executable, str(ROOT / 'tools/reader_wave3_package/unpack.py'), '--target', 'linux',
                    '--archive', str(archives[0]), '--manifest', str(delivery / 'manifest.json'),
                    '--into', str(into), '--report', str(report)], check=True)
    manifest = json.loads((delivery / 'manifest.json').read_text())
    entry = into / 'EXReader-Linux/bin/exreader-linux'
    launcher = into / 'EXReader-Linux/Start-EXReader.sh'
    assert entry.is_file() and os.access(entry, os.X_OK), f'{label}: no executable entry'
    assert launcher.is_file(), f'{label}: no Start-EXReader.sh user entry; not supplied by this test'
    ldd = subprocess.run(['ldd', str(entry)], text=True, capture_output=True, check=True).stdout
    workspace = os.environ.get('GITHUB_WORKSPACE', str(ROOT))
    assert 'not found' not in ldd and workspace not in ldd, f'{label}: unresolved or build-tree dependency'
    version = subprocess.run([str(entry), '--version'], text=True, capture_output=True, timeout=30)
    extra = {}
    for name in ('result.json', 'configuration.json', 'entry.json'):
        if (delivery / name).is_file():
            extra[name] = sha(delivery / name)
    return dict(label=label, install=str(into), archive=archives[0].name, archive_sha256=sha(archives[0]),
                archive_bytes=archives[0].stat().st_size, manifest_sha256=sha(delivery / 'manifest.json'),
                manifest_source_sha=manifest.get('source_sha'), manifest_sdk_version=manifest.get('sdk_version'),
                manifest_archive=manifest.get('archive'), entry_sha256=sha(entry), launcher_sha256=sha(launcher),
                launcher_text=launcher.read_text(), version_stdout=version.stdout.strip(), version_exit=version.returncode,
                ldd=ldd.splitlines(), delivery_files=extra, files=tree(into))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--a-zip', type=Path, required=True)
    parser.add_argument('--b-dir', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'GitHub Actions only'
    evidence = args.evidence.resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    raw = args.a_zip.read_bytes()
    outer = dict(path=str(args.a_zip), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    assert outer['bytes'] == A_ARTIFACT['bytes'] and outer['sha256'] == A_ARTIFACT['sha256'], ('A artifact differs', outer)
    a_delivery = args.root / 'A-artifact'
    a_delivery.mkdir(parents=True)
    with zipfile.ZipFile(args.a_zip) as bundle:
        names = bundle.namelist()
        assert all(not n.startswith('/') and '..' not in n.split('/') for n in names), names
        bundle.extractall(a_delivery)
    programs = args.root / PROGRAMS
    programs.mkdir(parents=True)
    a = unpack('A', a_delivery, programs / A_DIR, evidence)
    b = unpack('B', args.b_dir.resolve(), programs / B_DIR, evidence)
    assert a['manifest_source_sha'] == A_SOURCE, ('A manifest source', a['manifest_source_sha'])
    assert b['manifest_source_sha'] == os.environ['GITHUB_SHA'], ('B manifest source', b['manifest_source_sha'])
    report = dict(a_artifact=dict(A_ARTIFACT, outer=outer, members=names), a=a, b=b,
                  b_product_baseline=B_BASELINE, b_source=os.environ['GITHUB_SHA'],
                  same_entry_binary=a['entry_sha256'] == b['entry_sha256'], programs=str(programs))
    (evidence / 'install.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print('K03-INSTALL ' + json.dumps(dict(a_entry=a['entry_sha256'], b_entry=b['entry_sha256'],
                                           a_sdk=a['manifest_sdk_version'], b_sdk=b['manifest_sdk_version'],
                                           a_version=a['version_stdout'], b_version=b['version_stdout'])))


if __name__ == '__main__':
    main()
