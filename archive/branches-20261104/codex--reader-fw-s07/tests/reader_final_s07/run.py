# SPDX-License-Identifier: MIT
"""Actions-only driver for S07.

Order of work, all in one job and one source SHA:

1. source guard (read-only proof, frozen producer identity);
2. the frozen public-SDK capture core, with only its ownership block replaced
   in memory by this package's guard (the frozen block is recorded verbatim);
3. the frozen raw7 stage recipe and the frozen raw7 installed-consumer
   project, byte-identical, consuming the installed 0.2.0/0.4.0 packages;
4. the frozen two-peer real-HTTPS raw7 companion test (tests/.../tls.py);
5. the frozen G07 suite: the unchanged 20-item account-session acceptance and
   the 21 G07 fault boundaries, both on this same source/run/attempt;
6. this package's three-peer temporary-HTTPS regression.

Nothing here is spliced from another run: every block records the same
source_sha, run_id and attempt, and the aggregate job re-checks all of them.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import types

PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parents[1]
sys.path.insert(0, str(PACKAGE))
import source_guard

OUT = ROOT / 'build/reader-final-s07'
BUILD = ROOT / 'build/s07-build'
CORE_OUT = ROOT / 'build/selector-bytes'
SUFFIX = '.exe' if os.name == 'nt' else ''
MODULES = ('commands', 'sync', 'session')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def run(argv, name, timeout=5400):
    command = [str(item) for item in argv]
    print('RUN', ' '.join(command), flush=True)
    process = subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True,
                             encoding='utf-8', errors='replace', timeout=timeout)
    logs = BUILD / 'driver-logs'
    logs.mkdir(parents=True, exist_ok=True)
    (logs / (name + '.log')).write_text(process.stdout + process.stderr, encoding='utf-8')
    print((process.stdout + process.stderr)[-20000:], flush=True)
    assert process.returncode == 0, (name, process.returncode)
    return process.stdout


def build(source, name, prefix, extra=(), install=True):
    target = BUILD / name
    run(['cmake', '-S', source, '-B', target, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
         '-DCMAKE_INSTALL_PREFIX=' + str(prefix), *extra], name + '-configure')
    run(['cmake', '--build', target, '--parallel', '4'], name + '-build')
    if install:
        run(['cmake', '--install', target], name + '-install')
    return target


def capture_core(guard):
    """Run the frozen capture core with only its ownership block replaced."""
    core = ROOT / 'tests/reader_selector_bytes/run.py'
    original = core.read_text(encoding='utf-8')
    first_marker = "    assert run(['git', 'rev-parse', 'HEAD']).strip() == os.environ['GITHUB_SHA']"
    kept = ("    run(['git', 'diff', '--exit-code', 'edddc463c06ed5731195cdb8f06b2df6dff7699e',"
            " 'HEAD', '--', 'src', 'include', 'cmake', 'CMakeLists.txt'])")
    start = original.index(first_marker)
    last = original.index("    pdf = ROOT / 'tests/fixtures/pdf-public-text.pdf'", start)
    block = original[start:last]
    assert kept in block and 'allowed = tuple' in block and "'examples'" in block
    replacement = (kept + '\n'
                   + "    run(['git', 'diff', '--exit-code', s07_start, 'HEAD', '--', 'src', 'include',"
                   + " 'cmake', 'CMakeLists.txt', 'apps/reader/store', 'examples', 'tests/fixtures',"
                   + " 'extras/opds', 'extras/webdav'])\n"
                   + '    s07_guard()\n')
    patched = original[:start] + replacement + original[last:]
    module = types.ModuleType('s07_capture_core')
    module.__file__ = str(core)
    module.__dict__['s07_start'] = source_guard.START
    module.__dict__['s07_guard'] = lambda: guard
    exec(compile(patched, str(core), 'exec'), module.__dict__)
    module.main()
    return {
        'capture_core_source_sha256': digest(original.encode('utf-8')),
        'capture_core_patched_sha256': digest(patched.encode('utf-8')),
        'replaced_block': block,
        'replaced_block_sha256': digest(block.encode('utf-8')),
        'replacement': replacement,
        'replacement_sha256': digest(replacement.encode('utf-8')),
        'reason': ('the frozen block pins examples/ and apps/reader/store to the capture package base '
                   'b93b4a2f, which the mainline moved after that package; this package instead proves '
                   'those trees are unchanged from the fixed implementation start to HEAD'),
    }


def stages(core_out):
    product = core_out / 'product-stage'
    sdk = ROOT / 'build/reading-library/stage'
    assert (product / 'lib/cmake/EXReaderProductCatalog').is_dir(), product
    assert (sdk / 'lib/cmake/EXReader').is_dir(), sdk
    dav = BUILD / 'dav-stage'
    build(ROOT / 'extras/webdav', 'dav', dav)
    built = {}
    for label, enabled in (('off', False), ('candidate', True)):
        stage = BUILD / (label + '-stage')
        shutil.copytree(core_out / (label + '-stage'), stage)
        prefixes = ';'.join(map(str, [stage, dav, product, sdk]))
        for module in MODULES:
            build(ROOT / 'apps/reader' / module, label + '-' + module, stage,
                  ['-DEXR_READER_SELECTOR_BYTES_CANDIDATE=' + ('ON' if enabled else 'OFF'),
                   '-DCMAKE_PREFIX_PATH=' + prefixes])
        built[label] = stage
    return built, dav, product, sdk


def consumers(built, dav, product, sdk):
    raw_prefix = ';'.join(map(str, [built['candidate'], dav, product, sdk]))
    off_prefix = ';'.join(map(str, [built['off'], dav, product, sdk]))
    raw = build(ROOT / 'tests/reader_raw_store_companions', 'raw7-consumers', built['candidate'],
                ['-DCMAKE_PREFIX_PATH=' + raw_prefix], False)
    off_sync = build(ROOT / 'tests/reader_sync/consumer', 'off-sync-consumer', built['off'],
                     ['-DCMAKE_PREFIX_PATH=' + off_prefix], False)
    off_command = build(ROOT / 'tests/reader_commands/consumer', 'off-command-consumer', built['off'],
                        ['-DCMAKE_PREFIX_PATH=' + off_prefix], False)
    off_session = build(ROOT / 'tests/reader_session/consumer', 'off-session-consumer', built['off'],
                        ['-DCMAKE_PREFIX_PATH=' + off_prefix], False)
    g07 = build(ROOT / 'tests/reader_sync_resilience/consumer', 'g07-consumer', built['off'],
                ['-DCMAKE_PREFIX_PATH=' + off_prefix], False)
    return raw, off_sync, off_command, off_session, g07


def main():
    evidence = source_guard.guard()
    OUT.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    capture = capture_core(evidence)
    core_result = json.loads((CORE_OUT / 'result.json').read_text(encoding='utf-8'))
    assert core_result['accepted']
    assert [core_result[key] for key in ('source_sha', 'run_id', 'attempt')] == [
        os.environ['GITHUB_SHA'], os.environ['GITHUB_RUN_ID'], os.environ['GITHUB_RUN_ATTEMPT']]
    built, dav, product, sdk = stages(CORE_OUT)
    raw, off_sync, off_command, off_session, g07 = consumers(built, dav, product, sdk)
    old_revision = CORE_OUT / 'off-revision-consumer' / ('revision-consumer' + SUFFIX)
    assert old_revision.is_file(), old_revision

    tls_output = BUILD / 'actual-tls'
    run([sys.executable, ROOT / 'tests/reader_raw_store_companions/tls.py',
         '--programs', raw, '--core', CORE_OUT, '--old-revision', old_revision,
         '--output', tls_output], 'raw7-two-peer-tls', 2400)
    tls_result = json.loads((tls_output / 'result.json').read_text(encoding='utf-8'))

    session_output = BUILD / 'g07-original-session'
    run([sys.executable, ROOT / 'tests/reader_session/check_session.py',
         '--consumer', off_session / ('session-consumer' + SUFFIX),
         '--revision-consumer', old_revision, '--output', session_output], 'g07-original-session', 3600)
    session_result = json.loads((session_output / 'result.json').read_text(encoding='utf-8'))

    boundary_output = BUILD / 'g07-boundaries'
    run([sys.executable, ROOT / 'tests/reader_sync_resilience/check_resilience.py',
         '--consumer', g07 / ('resilience-consumer' + SUFFIX),
         '--revision-consumer', old_revision,
         '--original-report', session_output / 'result.json',
         '--output', boundary_output], 'g07-boundaries', 3600)
    boundary_result = json.loads((boundary_output / 'result.json').read_text(encoding='utf-8'))

    peers_output = OUT / 'three-peers'
    run([sys.executable, PACKAGE / 'three_peers.py', '--programs', raw, '--core', CORE_OUT,
         '--old-revision', old_revision,
         '--old-sync', off_sync / ('sync-consumer' + SUFFIX),
         '--old-command', off_command / ('command-consumer' + SUFFIX),
         '--output', peers_output], 'three-peers', 2400)
    peers = json.loads((peers_output / 'result.json').read_text(encoding='utf-8'))

    assert tls_result['accepted'] and len(tls_result['checks']) == 9, tls_result.get('checks')
    assert len(tls_result['exact_wires']) == 11
    assert session_result['accepted'] and len(session_result['checks']) == 20
    assert boundary_result['accepted'] and len(boundary_result['checks']) == 21
    assert peers['accepted'] and peers['count'] == 8

    preconditions = OUT / 'preconditions'
    preconditions.mkdir()
    shutil.copyfile(CORE_OUT / 'result.json', preconditions / 'capture-core-result.json')
    shutil.copyfile(tls_output / 'result.json', preconditions / 'raw7-two-peer-tls-result.json')
    shutil.copyfile(session_output / 'result.json', preconditions / 'g07-original-session-result.json')
    shutil.copyfile(boundary_output / 'result.json', preconditions / 'g07-boundaries-result.json')

    result = {
        'accepted': True,
        'package': 'S07',
        'scope': ('three-peer temporary-HTTPS fault and idempotency regression on the frozen public '
                  'raw7 module, with the frozen two-peer raw7 test and the frozen G07 suite in the '
                  'same source/run/attempt'),
        'source_sha': os.environ['GITHUB_SHA'],
        'run_id': os.environ['GITHUB_RUN_ID'],
        'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
        'platform': sys.platform,
        'guard': evidence,
        'capture_core_ownership_replacement': capture,
        'preconditions': {
            'capture_core': {
                'accepted': core_result['accepted'],
                'protocol_checks': len(core_result['protocol_checks']),
                'graph_checks': len(core_result['graph_checks']),
                'result_sha256': digest((CORE_OUT / 'result.json').read_bytes()),
                'consumer_sha256': core_result['consumer_sha256'],
                'pdf_sha256': core_result['pdf_sha256'],
            },
            'raw7_two_peer_tls': {
                'accepted': tls_result['accepted'],
                'count': tls_result['count'],
                'checks': tls_result['checks'],
                'exact_wires': tls_result['exact_wires'],
                'result_sha256': digest((tls_output / 'result.json').read_bytes()),
            },
            'g07_original_session': {
                'accepted': session_result['accepted'],
                'count': session_result['count'],
                'checks': session_result['checks'],
                'result_sha256': digest((session_output / 'result.json').read_bytes()),
            },
            'g07_fault_boundaries': {
                'accepted': boundary_result['accepted'],
                'count': boundary_result['count'],
                'checks': [item['id'] for item in boundary_result['checks']],
                'uncovered': boundary_result['uncovered'],
                'result_sha256': digest((boundary_output / 'result.json').read_bytes()),
            },
        },
        'three_peers': peers,
        'gaps': peers['gaps'],
        'adopted': False,
        'actual_hosts': False,
        'physical_device': False,
        'complete_product': False,
        'grants': {
            'three_peer_raw_sync_faults': True,
            'raw7_module_unchanged': True,
            'real_host_ui': False,
            'six_platform_interop': False,
            'real_third_party_service': False,
        },
    }
    (OUT / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    summary = dict(result)
    summary['three_peers'] = {'count': peers['count'], 'checks': [item['name'] for item in peers['checks']],
                              'wires': peers['wires'], 'original': peers['original']}
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
