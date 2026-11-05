# SPDX-License-Identifier: MIT
"""Read-only ownership proof for S07.

The fixed implementation start is 0889f7d1. Every file outside this package's
own three paths plus HANDOFF-RESULT.md must be byte-identical to that start, so
the frozen public raw7 module, the frozen public-SDK capture driver, the G07
suite and the installed consumers are reused without one edited byte.

The frozen packages apply their ownership proof against their own branch base
(0737d03c for the raw7 companion package, b93b4a2f for the capture core). Those
blocks are history, not this branch: they reject this branch for containing this
package. S07 therefore re-proves the same property from its own start and
records the replaced block verbatim with its SHA-256, so no claim is inherited
from a branch that was never measured here.
"""
import hashlib
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
START = '0889f7d1e9a537c6c1b05456547e016b26e1cd85'
RAW7_BASE = '0737d03c1316295a210aa527833c05054d29c1d4'
CORE_BASE = 'b93b4a2f9ac24d7d0fc4d48c917dae11bec4baf7'
LEGACY_BASE = '210403d121d6484a8fff4ea7ffd911efa3163535'
SDK = 'edddc463c06ed5731195cdb8f06b2df6dff7699e'
FROZEN_SDK = '9854061be331fe603a1822d9b2b36ee357154927'

ALLOWED = (
    'tests/reader_final_s07/',
    '.github/workflows/reader-final-s07.yml',
    'docs/reader-final-s07/',
    'HANDOFF-RESULT.md',
)

# Trees this package consumes. None of them may differ from the start.
FROZEN = (
    'apps/reader',
    'extras',
    'src',
    'include',
    'cmake',
    'CMakeLists.txt',
    'CMakePresets.json',
    'bindings',
    'tools',
    'licenses',
    'examples',
    'tests/fixtures',
    'tests/reader_selector_bytes',
    'tests/reader_raw_store_companions',
    'tests/reader_commands',
    'tests/reader_revisions',
    'tests/reader_sync',
    'tests/reader_session',
    'tests/reader_sync_resilience',
    'tests/webdav',
    'tests/reader_reading_state',
    'tests/reader_reading_v2',
    'tests/reader_reading_commands',
    'tests/reader_annotation_view',
)

PRODUCER = (
    'tests/reader_raw_store_companions',
    'tests/reader_selector_bytes',
    'tests/reader_sync',
    'tests/reader_revisions',
    'tests/reader_sync_resilience',
)


def git(*arguments):
    return subprocess.check_output(['git', *arguments], cwd=str(ROOT), text=True)


def blob(path):
    return subprocess.check_output(['git', 'show', START + ':' + path], cwd=str(ROOT))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def guard():
    """Prove the start, the read-only boundary and the frozen producer identity."""
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
    head = git('rev-parse', 'HEAD').strip()
    assert head == os.environ['GITHUB_SHA'], (head, os.environ.get('GITHUB_SHA'))
    for commit in (START, RAW7_BASE, CORE_BASE, LEGACY_BASE, SDK, FROZEN_SDK):
        assert subprocess.run(['git', 'merge-base', '--is-ancestor', commit, head],
                              cwd=str(ROOT), capture_output=True).returncode == 0, commit
    changed = git('diff', '--name-only', START, head).splitlines()
    for path in changed:
        assert any(path.startswith(prefix) for prefix in ALLOWED), path
    diff = subprocess.run(['git', 'diff', '--exit-code', START, head, '--', *FROZEN],
                          cwd=str(ROOT), capture_output=True, text=True)
    assert diff.returncode == 0, diff.stdout + diff.stderr
    rows = git('ls-tree', '-r', START, '--', *PRODUCER).splitlines()
    return {
        'start': START,
        'head': head,
        'changed_paths': changed,
        'frozen_tree_paths': list(FROZEN),
        'frozen_tree_diff': 0,
        'producer_manifest_rows': len(rows),
        'producer_manifest_sha256': digest(('\n'.join(rows) + '\n').encode('utf-8')),
        'frozen_identities': {
            'raw7_run_py_sha256': digest(blob('tests/reader_raw_store_companions/run.py')),
            'raw7_tls_py_sha256': digest(blob('tests/reader_raw_store_companions/tls.py')),
            'raw7_consumers_cmake_sha256': digest(blob('tests/reader_raw_store_companions/CMakeLists.txt')),
            'core_run_py_sha256': digest(blob('tests/reader_selector_bytes/run.py')),
            'g07_checker_sha256': digest(blob('tests/reader_sync_resilience/check_resilience.py')),
            'g07_boundaries_sha256': digest(blob('tests/reader_sync_resilience/boundaries.py')),
            'revisions_consumer_sha256': digest(blob('tests/reader_revisions/consumer/main.cpp')),
            'sync_consumer_sha256': digest(blob('tests/reader_sync/consumer/main.cpp')),
            'commands_consumer_sha256': digest(blob('tests/reader_commands/consumer/main.cpp')),
            'revisions_header_sha256': digest(blob('apps/reader/revisions/include/reader_revisions.h')),
            'sync_header_sha256': digest(blob('apps/reader/sync/include/reader_sync.h')),
        },
        'sdk_source': SDK,
        'frozen_sdk_source': FROZEN_SDK,
        'raw7_base': RAW7_BASE,
        'core_base': CORE_BASE,
        'legacy_base': LEGACY_BASE,
    }
