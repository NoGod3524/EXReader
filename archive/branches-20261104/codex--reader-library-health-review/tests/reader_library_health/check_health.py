#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only validation for the optional library-health package.

Runs the installed probe and C++ consumer, independently re-hashes every
original and both databases, checks each named verdict, and writes one
same-source result document. Nothing here runs locally.
"""
import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

ROWS = 2202
MAX_BOOK = 600 * 1024
REQUIRED_MAIN_CHECKS = (
    'main_open_pair',
    'main_rows_delivered',
    'main_status_ok',
    'main_done_flag',
    'main_keyset_order',
    'main_identity_and_verdicts',
    'main_step_count',
    'main_hashed_bytes_match_rows',
    'main_verdict_distribution',
    'main_repeat_step7',
)
REQUIRED_ADVERSARIAL_CHECKS = (
    'cancel_reports_cancelled',
    'cancel_keeps_delivered_rows_only',
    'cancel_resume_completes',
    'cancel_mid_read_not_delivered',
    'cancel_mid_read_resume_verified',
    'cancel_final_progress_not_delivered',
    'cancel_callback_reentry_is_rejected',
    'budget_splits_steps_without_loss',
    'limit_stops_at_max',
    'limit_continues_to_done',
    'reentry_is_rejected',
    'wrong_thread_rejected',
    'wrong_thread_owner_still_scans',
    'wrong_catalog_cursor_rejected',
    'wrong_catalog_fresh_cursor_works',
    'change_during_scan_reports_missing_source',
    'invalidate_mid_read_reports_failure',
    'rescan_after_change_verified',
    'argument_bounds_enforced',
    'verdict_names_defined',
    'status_names_defined',
)
REQUIRED_MEMORY_CHECKS = ('memory_import', 'memory_attach', 'memory_bounded_read',
                          'memory_peak_growth_bounded')
REQUIRED_CPP_CHECKS = ('cpp_create', 'cpp_rows_delivered', 'cpp_identity_and_order',
                       'cpp_verdicts', 'cpp_repeat_identical', 'cpp_reentry_refused',
                       'cpp_wrong_thread_refused', 'cpp_destroy')


class Report:
    def __init__(self):
        self.checks = []
        self.failed = 0

    def add(self, identifier, passed, detail):
        self.checks.append({'id': identifier, 'passed': bool(passed), 'detail': str(detail)})
        if not passed:
            self.failed += 1

    def require(self, identifier, passed, detail):
        self.add(identifier, passed, detail)
        return passed


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def identity(path):
    path = Path(path)
    if not path.is_file():
        return {'bytes': 0, 'sha256': None}
    return {'bytes': path.stat().st_size, 'sha256': sha256_file(path)}


def run(command, report, identifier):
    completed = subprocess.run(command, capture_output=True, text=True)
    detail = (completed.stdout.strip() + ' ' + completed.stderr.strip()).strip()
    report.add(identifier, completed.returncode == 0,
               'exit=%d %s' % (completed.returncode, detail[:400]))
    return completed.returncode == 0


def expected_verdict(action):
    return {
        'map': 'verified',
        'cloud': 'cloud_only',
        'missing': 'mapping_missing',
        'hash_bad': 'hash_mismatch',
        'size_short': 'size_mismatch',
        'size_long': 'size_mismatch',
        'limit': 'limit_skipped',
    }[action]


def catalog_bytes(row):
    if row['action'] == 'size_short':
        return row['bytes'] + 5
    if row['action'] == 'size_long':
        return row['bytes'] - 3
    return row['bytes']


def row_contract(row, plan_row, manifest_entry):
    problems = []
    action = plan_row['action']
    real_bytes = manifest_entry['bytes']
    real_sha = manifest_entry['sha256']
    if row['sort_title'] != plan_row['sort_title']:
        problems.append('sort_title')
    if row['format'] != plan_row['format']:
        problems.append('format')
    if row['verdict'] != expected_verdict(action):
        problems.append('verdict=%s' % row['verdict'])
    if action == 'map':
        if row['expected_sha256'] != real_sha:
            problems.append('expected_sha')
        if row['observed_sha256'] != real_sha:
            problems.append('observed_sha')
        if row['expected_bytes'] != real_bytes or row['retained_bytes'] != real_bytes:
            problems.append('bytes')
        if row['bytes_read'] != real_bytes or row['hashed'] is not True:
            problems.append('read')
        if row['sdk_book_id'] <= 0:
            problems.append('sdk_id')
    elif action == 'cloud':
        if row['sdk_book_id'] != 0 or row['hashed'] is not False:
            problems.append('cloud_identity')
        if row['retained_bytes'] != 0 or row['bytes_read'] != 0:
            problems.append('cloud_read')
    elif action == 'missing':
        if row['sdk_status'] != 1 or row['hashed'] is not False:
            problems.append('missing_status')
    elif action == 'hash_bad':
        if row['observed_sha256'] != real_sha:
            problems.append('observed_sha')
        if row['expected_sha256'] == real_sha:
            problems.append('expected_sha')
        if row['retained_bytes'] != real_bytes or row['bytes_read'] != real_bytes:
            problems.append('bytes')
        if row['hashed'] is not True:
            problems.append('hashed')
    elif action in ('size_short', 'size_long'):
        if row['retained_bytes'] != real_bytes:
            problems.append('retained')
        if row['expected_bytes'] != catalog_bytes(plan_row):
            problems.append('expected')
        if row['hashed'] is not False or row['bytes_read']:
            problems.append('read')
        if action == 'size_short' and row['retained_bytes'] >= row['expected_bytes']:
            problems.append('short_relation')
        if action == 'size_long' and row['retained_bytes'] <= row['expected_bytes']:
            problems.append('long_relation')
    elif action == 'limit':
        if row['retained_bytes'] != real_bytes or row['hashed'] is not False:
            problems.append('limit_flat')
        if row['bytes_read'] != 0:
            problems.append('limit_read')
    return problems


def load_checks(document, required, report, prefix):
    checks = document.get('checks', [])
    by_id = {check['id']: check for check in checks}
    report.require(prefix + '_checks_present', len(checks) >= len(required),
                   '%d checks' % len(checks))
    missing = [name for name in required if name not in by_id]
    report.require(prefix + '_checks_named', not missing, 'missing=' + ','.join(missing))
    failed = [check['id'] for check in checks if not check.get('passed')]
    report.require(prefix + '_checks_passed', not failed and not missing,
                   'failed=' + ','.join(failed))
    return by_id


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--probe', required=True)
    parser.add_argument('--cpp', required=True)
    parser.add_argument('--fixtures', required=True)
    parser.add_argument('--work', required=True)
    parser.add_argument('--installed', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()

    report = Report()
    source = os.environ.get('GITHUB_SHA', '')
    run_id = int(os.environ.get('GITHUB_RUN_ID', '0') or 0)
    attempt = int(os.environ.get('GITHUB_RUN_ATTEMPT', '0') or 0)
    workflow = '.github/workflows/reader-library-health.yml'
    report.require('actions_only', os.environ.get('GITHUB_ACTIONS') == 'true',
                   'GITHUB_ACTIONS=%r' % os.environ.get('GITHUB_ACTIONS'))
    report.require('source_identity', len(source) == 40 and run_id > 0 and attempt > 0,
                   'sha=%s run=%d attempt=%d' % (source, run_id, attempt))
    if platform.system() == 'Windows':
        granted = 'windows'
    elif platform.system() == 'Darwin':
        granted = 'macos'
    else:
        granted = 'linux'

    fixtures = Path(args.fixtures)
    work = Path(args.work)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    (work / 'main').mkdir(parents=True, exist_ok=True)
    (work / 'ev').mkdir(parents=True, exist_ok=True)
    (work / 'adv').mkdir(parents=True, exist_ok=True)
    (work / 'mem').mkdir(parents=True, exist_ok=True)
    evidence = work / 'ev'

    manifest = json.loads((fixtures / 'manifest.json').read_text(encoding='utf-8'))
    files = manifest['files']
    report.require('fixture_row_count', manifest.get('plan_rows') == ROWS,
                   'plan_rows=%r' % manifest.get('plan_rows'))

    plan = []
    for line in (fixtures / 'plan.tsv').read_text(encoding='utf-8').splitlines():
        if not line or line.startswith('#'):
            continue
        fields = line.split('\t')
        plan.append({'sort_title': fields[0], 'format': fields[1], 'sha256': fields[2],
                     'bytes': int(fields[3]), 'file': fields[4], 'action': fields[5]})
    report.require('plan_rows', len(plan) == ROWS, 'rows=%d' % len(plan))
    action_counts = {}
    for entry in plan:
        action_counts[entry['action']] = action_counts.get(entry['action'], 0) + 1
    report.require('plan_actions', action_counts.get('map') == 2185 and
                   action_counts.get('cloud') == 4 and action_counts.get('missing') == 4 and
                   action_counts.get('hash_bad') == 4 and action_counts.get('size_short') == 2 and
                   action_counts.get('size_long') == 2 and action_counts.get('limit') == 1,
                   json.dumps(action_counts, sort_keys=True))

    fixture_problems = []
    for name, entry in files.items():
        path = fixtures / name
        if not path.exists():
            fixture_problems.append(name + ':missing')
            continue
        if path.stat().st_size != entry['bytes'] or sha256_file(path) != entry['sha256']:
            fixture_problems.append(name + ':bytes')
    report.require('fixture_manifest', not fixture_problems,
                   'problems=' + ','.join(fixture_problems[:6]))

    probe = str(Path(args.probe).resolve())
    cpp = str(Path(args.cpp).resolve())
    database_dir = work / 'main'
    catalog = database_dir / 'catalog.db'
    library = database_dir / 'library.db'

    if run([probe, 'build', str(database_dir), str(fixtures), str(fixtures / 'plan.tsv')],
           report, 'build_exit'):
        report.require('build_outputs', catalog.exists() and library.exists(),
                       'catalog=%s library=%s' % (catalog.exists(), library.exists()))
    before = {}
    if catalog.exists() and library.exists():
        before = {'catalog': identity(catalog), 'library': identity(library)}
    main_json = evidence / 'main.json'
    run([probe, 'scan', str(database_dir), str(fixtures), str(fixtures / 'plan.tsv'),
         str(main_json), '32', '4096', str(MAX_BOOK)], report, 'scan_exit')
    after = {}
    if catalog.exists() and library.exists():
        after = {'catalog': identity(catalog), 'library': identity(library)}
    report.require('library_and_catalog_unchanged', before == after and bool(before),
                   'before=%s after=%s' % (json.dumps(before, sort_keys=True),
                                           json.dumps(after, sort_keys=True)))
    stray = sorted(name for name in os.listdir(database_dir)
                   if name not in ('catalog.db', 'library.db'))
    report.require('no_sidecar_files', not stray, 'stray=' + ','.join(stray))

    adversarial_json = evidence / 'adversarial.json'
    run([probe, 'adversarial', str(work / 'adv'), str(fixtures),
         str(fixtures / 'adversarial.tsv'), str(adversarial_json)], report, 'adversarial_exit')
    big = files['adversarial/big-scan.epub']
    memory_json = evidence / 'memory.json'
    run([probe, 'memory', str(work / 'mem'), str(fixtures / 'adversarial/big-scan.epub'),
         str(big['bytes']), big['sha256'], str(memory_json)], report, 'memory_exit')
    cpp_json = evidence / 'cpp.json'
    run([cpp, str(catalog), str(library), str(fixtures / 'plan.tsv'), '7', '4096',
         str(cpp_json)], report, 'cpp_exit')
    after_all = {}
    if catalog.exists() and library.exists():
        after_all = {'catalog': identity(catalog), 'library': identity(library)}
    report.require('library_and_catalog_unchanged_after_consumers',
                   after_all == after and bool(after),
                   'after=%s after_all=%s' % (json.dumps(after, sort_keys=True),
                                              json.dumps(after_all, sort_keys=True)))

    # Fixtures must still be byte-identical after every consumer ran.
    fixture_after = []
    for name, entry in files.items():
        path = fixtures / name
        if not path.exists() or sha256_file(path) != entry['sha256']:
            fixture_after.append(name)
    report.require('originals_unchanged_after_run', not fixture_after,
                   'changed=' + ','.join(fixture_after[:6]))

    rows = []
    main_document = {}
    if main_json.exists():
        document = json.loads(main_json.read_text(encoding='utf-8'))
        main_document = document
        report.require('main_source_identity', document.get('platform') == granted,
                       'platform=%r' % document.get('platform'))
        load_checks(document, REQUIRED_MAIN_CHECKS, report, 'main')
        rows = document.get('rows', [])
    report.require('main_row_count', len(rows) == ROWS, 'rows=%d' % len(rows))
    contract = []
    if len(rows) == len(plan):
        for index, (row, entry) in enumerate(zip(rows, plan)):
            problems = row_contract(row, entry, files[entry['file']])
            if problems:
                contract.append('%d:%s' % (index, ','.join(problems)))
    report.require('main_row_contract', not contract,
                   'problems=' + ';'.join(contract[:6]))
    verdicts = {}
    for row in rows:
        verdicts[row['verdict']] = verdicts.get(row['verdict'], 0) + 1
    expected_verdicts = {}
    for entry in plan:
        name = expected_verdict(entry['action'])
        expected_verdicts[name] = expected_verdicts.get(name, 0) + 1
    report.require('main_verdict_counts', verdicts == expected_verdicts,
                   'actual=%s expected=%s' % (json.dumps(verdicts, sort_keys=True),
                                              json.dumps(expected_verdicts, sort_keys=True)))
    hashed_bytes = sum(row['bytes_read'] for row in rows)
    expected_hashed = sum(files[entry['file']]['bytes'] for entry in plan
                          if entry['action'] in ('map', 'hash_bad'))
    report.require('main_hashed_bytes', hashed_bytes > 0 and hashed_bytes == expected_hashed,
                   'hashed=%d expected=%d' % (hashed_bytes, expected_hashed))
    report.require('main_stats_bytes',
                   int(main_document.get('stats', {}).get('bytes_hashed', -1)) == hashed_bytes,
                   'stats=%r rows=%d' % (main_document.get('stats', {}).get('bytes_hashed'),
                                         hashed_bytes))

    if adversarial_json.exists():
        load_checks(json.loads(adversarial_json.read_text(encoding='utf-8')),
                    REQUIRED_ADVERSARIAL_CHECKS, report, 'adversarial')
    if memory_json.exists():
        document = json.loads(memory_json.read_text(encoding='utf-8'))
        load_checks(document, REQUIRED_MEMORY_CHECKS, report, 'memory')
        report.require('memory_original_identity',
                       int(document.get('stats', {}).get('bytes', 0)) == big['bytes'],
                       'bytes=%r expected=%d' % (document.get('stats', {}).get('bytes'),
                                                 big['bytes']))
    cpp_rows = []
    if cpp_json.exists():
        document = json.loads(cpp_json.read_text(encoding='utf-8'))
        load_checks(document, REQUIRED_CPP_CHECKS, report, 'cpp')
        cpp_rows = document.get('rows', [])
    report.require('cpp_rows_match_c', cpp_rows == rows and bool(rows),
                   'cpp=%d c=%d' % (len(cpp_rows), len(rows)))

    canonical = json.dumps(rows, sort_keys=True, separators=(',', ':')).encode('utf-8')
    rows_digest = hashlib.sha256(canonical).hexdigest()

    installed = []
    for path in sorted(Path(args.installed).rglob('*')):
        if path.is_file():
            installed.append({'path': str(path.relative_to(args.installed)),
                              'bytes': path.stat().st_size, 'sha256': sha256_file(path)})

    sources = [
        'apps/reader/library-health/include/reader_library_health.h',
        'apps/reader/library-health/src/library_health.c',
        'apps/reader/library-health/CMakeLists.txt',
        'apps/reader/library-health/EXReaderLibraryHealthConfig.cmake.in',
        'tests/reader_library_health/make_fixtures.py',
        'tests/reader_library_health/check_health.py',
        'tests/reader_library_health/consumer/CMakeLists.txt',
        'tests/reader_library_health/consumer/library_health_probe.c',
        'tests/reader_library_health/consumer/library_health_cpp_consumer.cpp',
    ]
    repo_root = Path(__file__).resolve().parents[2]
    source_identity = {}
    for name in sources:
        path = repo_root / name
        if path.exists():
            source_identity[name] = identity(path)
    executable_identity = {'probe': identity(probe), 'cpp_consumer': identity(cpp)}

    # The final acceptance flag is the conjunction of every named check.
    report.require('all_named_checks', report.failed == 0,
                   '%d failures' % report.failed)
    accepted = report.failed == 0
    result = {
        'accepted': accepted,
        'source_sha': source,
        'run_id': run_id,
        'attempt': attempt,
        'workflow': workflow,
        'granted_platform': granted,
        'scope': ('optional library-health package: read-only catalog/original scan, '
                  'cancellation, budgets, limits, threads, reentry and bounded reads'),
        'complete_product': False,
        'host_wired': False,
        'performance_claimed': False,
        'repair_performed': False,
        'rows': {'count': len(rows), 'verdicts': verdicts, 'digest': rows_digest,
                 'bytes_hashed': hashed_bytes},
        'checks': report.checks,
        'identity': {'executables': executable_identity, 'sources': source_identity,
                     'installed': installed,
                     'plan_tsv': identity(fixtures / 'plan.tsv'),
                     'adversarial_tsv': identity(fixtures / 'adversarial.tsv'),
                     'manifest_json': identity(fixtures / 'manifest.json'),
                     'catalog_db': identity(catalog),
                     'library_db': identity(library)},
        'not_covered': [
            'host UI wiring, product actions and user-visible repair flows',
            'catalog rows inserted or deleted while a step is running (keyset snapshot only)',
            'SDK private tables, schema migration and sync transport',
            'performance or accessibility budgets for any host surface',
        ],
    }
    (output / 'result.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n',
                                        encoding='utf-8')
    print(json.dumps({'accepted': accepted, 'granted': granted, 'rows': len(rows),
                      'digest': rows_digest, 'failures': report.failed}, sort_keys=True))
    return 0 if accepted else 1


if __name__ == '__main__':
    sys.exit(main())
