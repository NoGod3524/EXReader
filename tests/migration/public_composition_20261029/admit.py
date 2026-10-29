#!/usr/bin/env python3
"""Actions-only source admission for the public-product recovery composition."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

assert os.environ.get('GITHUB_ACTIONS') == 'true'
BASE = '10672a5325e721b6ae43be43e3f2e6865e1cf4d0'
RECOVERY = '0c0a24bf53b1efecb515ac5e6a8dfcf1a8f8e101'
GATE = '2fff53ff6734ec2b495c841e6669aef562e170d7'
SCOPES = ['extras/migration', 'tests/migration/recovery_preflight_20261029',
          'tests/migration/recovery_handoff_20261029',
          'tests/migration/recovery_integration_20261029',
          'tests/migration/new_target_recovery_20261029',
          'tests/migration/windows_recovery_native_20261029']

def git(*args):
    return subprocess.check_output(['git', *args])

assert git('rev-parse', 'HEAD').decode().strip() == os.environ['GITHUB_SHA']
pinned = git('ls-tree', '-r', '--name-only', RECOVERY, '--', *SCOPES).decode().splitlines()
assert pinned
hashes = {}
for path in pinned:
    data = Path(path).read_bytes()
    blob = git('rev-parse', 'HEAD:' + path).decode().strip()
    if path == 'tests/migration/recovery_handoff_20261029/run.py':
        previous = git('show', RECOVERY + ':' + path).decode('utf-8')
        expected = previous.replace('SPEC.loader.exec_module(P)', "SPEC.loader.exec_module(P)\nTOKEN_SPEC = importlib.util.spec_from_file_location('complete_private_token', Path(__file__).parents[1] / 'recovery_integration_20261029/run.py')\nT = importlib.util.module_from_spec(TOKEN_SPEC)\nTOKEN_SPEC.loader.exec_module(T)")
        expected = expected.replace("def go(self,root,phase):(root/(phase+'.go')).write_bytes(b'continue\\n')", "def go(self,root,phase):T.private_token(root/(phase+'.go'))")
        expected = expected.replace("(ctl / (phase + '.go')).write_bytes(b'continue\\n')", 'c.go(ctl,phase)')
        current = git('show', 'HEAD:' + path).decode('utf-8')
        assert current.replace('\r\n','\n') == expected.replace('\r\n','\n'), path
        import ast, collections
        def assertions(source):
            return collections.Counter(ast.dump(n, include_attributes=False) for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Assert))
        assert assertions(current) == assertions(previous), 'original handoff assertions changed'
    else:
        assert blob == git('rev-parse', RECOVERY + ':' + path).decode().strip(), path
    hashes[path] = dict(blob=blob, checkout_sha256=hashlib.sha256(data).hexdigest())
gate = ['examples/reader.c', 'apps/reader/desktop/windows_catalog.inc',
        'apps/reader/desktop/windows_migration_gate.h',
        'tests/windows_migration_startup/check.py']
for path in gate:
    assert git('rev-parse', 'HEAD:' + path) == git('rev-parse', GATE + ':' + path), path
frozen = ['src', 'include', 'cmake', 'CMakeLists.txt', 'bindings',
          'tests/migration/legacy_data.py', 'tests/migration/run_cases.py',
          'tests/migration/review_cases.py', 'tests/migration/e2e']
assert not git('diff', '--name-only', BASE, 'HEAD', '--', *frozen)
changed = set(git('diff', '--name-only', BASE, 'HEAD').decode().splitlines())
allowed = set(pinned) | {
    'tests/migration/public_composition_20261029/admit.py',
    '.github/workflows/migration-public-windows-stage-20261029.yml',
    '.github/workflows/migration-public-posix-stage-20261029.yml',
    'docs/MIGRATION-PUBLIC-COMPOSITION-STAGE-20261029.md'}
assert changed <= allowed, sorted(changed - allowed)
out = Path('build/evidence')
out.mkdir(parents=True, exist_ok=True)
receipt = dict(source=os.environ['GITHUB_SHA'], run=os.environ['GITHUB_RUN_ID'],
               attempt=os.environ['GITHUB_RUN_ATTEMPT'], base=BASE,
               recovery_source=RECOVERY, gate_source=GATE, changed=sorted(changed),
               pinned_sha256=hashes, sdk_and_original_tests_unchanged=True,
               windows_recovery_supported=False, full_p0_acceptance=False)
(out/'public-source-admission.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
print(json.dumps(dict(source=receipt['source'], exact_pinned_files=len(pinned),
                     windows_recovery_supported=False, full_p0_acceptance=False)))
