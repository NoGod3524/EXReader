# SPDX-License-Identifier: MIT
"""Actions-only Apple common-source admission and same-round authentication.
Original owner, native suites and old ZIP verifier remain unmodified.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
BASE = 'aefe6107f8f073847f0ed590f0ad9602fa720f3d'
OT = '8cab9b949b29c73ff54c6f9e5385edd351edf460'
ALLOWED = {'.github/workflows/reader-common-source-apple.yml', 'tests/apple_common_gate/gate.py'}
PINNED = {
    'src': 'e6bb1079cd50675a21ffe19cd99a6c08590eb3cf',
    'include': '775b4205dc86452d20e5744c73a3f1ae0a61d877',
    'examples/apple': 'f5e3cb94aad8bd4811c6d9ae207a5b181bfcdc0a',
    'tests/reader_team24_apple': 'f6bc0ba8887971020173b6c6c524d5d8819ee5b0',
    'tests/apple_host': 'f0ca3a249cd346b942821cf6ee8554ebcc8e2479',
    'apps/reader': '6f00a284ef13b9b7d8d91962812ea43023068349',
    'tools/check_apple_product.py': 'ed7f62597e01d4e045f679369805d27abc20b7bc',
    'src/opentype.c': OT,
}

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()

def identity():
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
    result = {k: os.environ[v] for k, v in [('source_sha', 'GITHUB_SHA'), ('run_id', 'GITHUB_RUN_ID'), ('attempt', 'GITHUB_RUN_ATTEMPT')]}
    assert git('rev-parse', 'HEAD') == result['source_sha']
    return result

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(value), flush=True)

def admission_errors(changes, blobs):
    return ['unregistered change: ' + p for p in sorted(set(changes) - ALLOWED)] + [
        'pinned source mismatch: ' + p for p, expected in PINNED.items() if blobs.get(p) != expected]

def admit():
    ident = identity()
    subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, ident['source_sha']], check=True)
    changes = git('diff', '--name-only', BASE, 'HEAD').splitlines()
    blobs = {p: git('rev-parse', 'HEAD:' + p) for p in PINNED}
    errors = admission_errors(changes, blobs)
    assert not admission_errors(ALLOWED, PINNED)
    assert admission_errors([*ALLOWED, 'examples/apple/HostModel.swift'], PINNED)
    assert admission_errors(ALLOWED, {**PINNED, 'src/opentype.c': '0' * 40})
    assert admission_errors(ALLOWED, {**PINNED, 'tests/apple_host': '0' * 40})
    assert admission_errors(ALLOWED, {**PINNED, 'examples/apple': '0' * 40})
    report = {**ident, 'common_base': BASE, 'accepted': not errors, 'product_accepted': False,
              'changes': changes, 'pinned_trees_and_blobs': blobs, 'negative_controls': 4,
              'separate_sync_run_not_repeated': '40633435674', 'errors': errors}
    # Preserve the obsolete caller rejection, rather than silently deleting it.
    out = ROOT / 'build/apple-source-admission'
    out.mkdir(parents=True, exist_ok=True)
    legacy = subprocess.run([sys.executable, 'tools/reader_composition/guard.py', '--source', ident['source_sha'],
                             '--report', str(out / 'legacy-composition.json')], capture_output=True, text=True)
    (out / 'legacy-source-guard.log').write_text(legacy.stdout + legacy.stderr)
    report['legacy_caller_returncode'] = legacy.returncode
    report['legacy_caller_expected_rejection'] = legacy.returncode != 0
    write(ROOT / 'build/apple-source-admission.json', report)
    assert not errors, errors

def stamp(target):
    ident = identity()
    out = ROOT / 'build/raw3-ios-sdk' / target
    files = {}
    for folder in ('sdk', 'raw-products'):
        for path in sorted((out / folder).rglob('*')):
            if path.is_file():
                files[path.relative_to(out).as_posix()] = {'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    assert files and any(p.endswith('.dylib') for p in files)
    write(out / 'common-sdk-identity.json', {**ident, 'target': target, 'common_base': BASE,
          'sdk_source_sha': ident['source_sha'], 'sdk_tree': git('rev-parse', 'HEAD:src'),
          'opentype_blob': git('rev-parse', 'HEAD:src/opentype.c'), 'files': files,
          'legacy_metadata_note': 'Historical baseline labels in original builder metadata are not the compiled source; actual SDK source is this run SHA.'})

def verify():
    ident = identity()
    old = subprocess.run([sys.executable, 'tests/reader_team24_apple/verify.py'])
    sys.path.insert(0, str(ROOT / 'tools'))
    from check_parallel_integration import fetch, download_artifact_zip
    report = {**ident, 'accepted': False, 'original_verifier_returncode': old.returncode, 'artifacts': [], 'failures': []}
    try:
        assert old.returncode == 0, 'original native ZIP verifier failed'
        artifacts = fetch(f"actions/runs/{ident['run_id']}/artifacts?per_page=100")['artifacts']
        suffix = '-' + ident['run_id'] + '-' + ident['attempt']
        sdks = [a for a in artifacts if a['name'].startswith('team24-apple-sdk-') and a['name'].endswith(suffix)]
        admissions = [a for a in artifacts if a['name'].startswith('same-source-apple-admission-') and a['name'].endswith(suffix)]
        assert len(sdks) == len(admissions) == 2
        for artifact in sdks + admissions:
            assert not artifact['expired'] and artifact['workflow_run']['head_sha'] == ident['source_sha']
            raw = download_artifact_zip(artifact['id'])
            sha = hashlib.sha256(raw).hexdigest()
            assert len(raw) == artifact['size_in_bytes'] and 'sha256:' + sha == artifact['digest']
            report['artifacts'].append({'id': artifact['id'], 'name': artifact['name'], 'bytes': len(raw), 'sha256': sha})
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                assert len(z.namelist()) == len(set(z.namelist()))
                if artifact in sdks:
                    data = json.loads(z.read('common-sdk-identity.json'))
                    target = data['target']
                    assert artifact['name'] == 'team24-apple-sdk-' + target + suffix
                    assert data['opentype_blob'] == OT and data['sdk_tree'] == PINNED['src']
                    assert data['sdk_source_sha'] == ident['source_sha']
                    for key, value in ident.items(): assert data[key] == value
                    assert data['files']
                    for path, expected in data['files'].items():
                        content = z.read(path)
                        assert len(content) == expected['bytes'] and hashlib.sha256(content).hexdigest() == expected['sha256'], path
                else:
                    matches = [n for n in z.namelist() if n.endswith('apple-source-admission.json')]
                    assert len(matches) == 1
                    data = json.loads(z.read(matches[0]))
                    for key, value in ident.items(): assert data[key] == value
                    assert data['accepted'] and data['negative_controls'] == 4 and data['pinned_trees_and_blobs'] == PINNED
        report['accepted'] = True
    except Exception as error:
        report['failures'].append(repr(error))
    write(ROOT / 'build/team24-apple-summary/common-authentication.json', report)
    assert report['accepted'], report['failures']

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('mode', choices=('admit', 'stamp', 'verify'))
    p.add_argument('--target', choices=('macos', 'iphonesimulator'))
    args = p.parse_args()
    if args.mode == 'admit': admit()
    elif args.mode == 'stamp': stamp(args.target)
    else: verify()
