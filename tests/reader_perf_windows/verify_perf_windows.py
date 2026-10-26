#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Strict gate over the Windows product performance observation.

The measurement reports observations and proposed budgets only; it never grants
a product performance acceptance. This gate rejects incomplete, cross-source or
forged evidence: it re-checks the source identity, the protected trees, the
package identity on disk, the corpus identity, the per-launch completeness and
the explicit "no frame time / no enforced budget" statements.
"""
import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ALLOWED = ('tests/reader_perf_windows/',
           '.github/workflows/reader-perf-windows.yml',
           'docs/READER-PERF-WINDOWS.md',
           'docs/validation/reader-perf-windows.json')
SDK_PATHS = ('src', 'include', 'cmake', 'CMakeLists.txt', 'tests/fixtures', 'bindings',
             '.github/workflows/native.yml', '.github/workflows/reliability.yml')
COHORTS = ('cold_shelf', 'warm_shelf', 'reading', 'import', 'import_epub')
TXT_REJECTIONS = ('import_rejected', 'rejected_but_sdk_orphan', 'imported_not_in_catalog',
                  'catalog_identity_mismatch')
REQUIRED_CHECKS = (
    'thirty_or_more_independent_process_starts',
    'at_least_ten_launches_per_named_cohort',
    'every_measured_launch_complete',
    'cold_and_warm_strategies_recorded',
    'window_appeared_each_launch',
    'first_screen_interactive_observed_each_shelf_launch',
    'shelf_pagination_observed',
    'search_result_observed',
    'eight_in_book_page_turns_per_reading_launch',
    'continue_reading_observed',
    'continue_reading_page_verified',
    'import_input_responsiveness_observed',
    'original_txt_input_identity_recorded',
    'original_txt_path_facts_separated',
    'original_txt_path_accounted_for',
    'working_set_peak_observed',
    'artifact_identity_recorded',
    'corpus_identity_recorded',
    'frame_time_not_measured',
    'numeric_budget_not_enforced',
)
PROPOSED_METRICS = ('first_screen_interactive_ms', 'shelf_next_page_ms', 'search_result_ms',
                    'book_page_turn_ms', 'resume_ms', 'input_during_import_p50_ms',
                    'peak_working_set_bytes')


def git(*arguments):
    return subprocess.run(['git', *arguments], capture_output=True, text=True, check=False)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--summary', type=Path, required=True)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--start', required=True)
    parser.add_argument('--launches', type=int, default=30)
    parser.add_argument('--per-cohort', type=int, default=10)
    args = parser.parse_args()

    problems = []

    def require(condition, message):
        if not condition:
            problems.append(message)

    head = os.environ.get('GITHUB_SHA', '')
    run_id = os.environ.get('GITHUB_RUN_ID', '')
    attempt = os.environ.get('GITHUB_RUN_ATTEMPT', '')

    # Source identity and protected trees.
    require(head and git('rev-parse', 'HEAD').stdout.strip() == head,
            'HEAD does not equal GITHUB_SHA')
    require(git('merge-base', '--is-ancestor', args.start, 'HEAD').returncode == 0,
            'fixed implementation start is not an ancestor of HEAD')
    protected = git('diff', '--name-only', '9854061be331fe603a1822d9b2b36ee357154927', 'HEAD', '--',
                    *SDK_PATHS)
    require(protected.returncode == 0 and not protected.stdout.strip(),
            'protected SDK tree differs from 9854061be331fe603a1822d9b2b36ee357154927: '
            + protected.stdout.strip())
    product = git('diff', '--name-only', 'f32bb8aa18ed3de286900f19ce4230fd93435dd0', 'HEAD', '--',
                  'apps/reader/store/001_catalog.sql')
    require(product.returncode == 0 and not product.stdout.strip(),
            'product catalog schema differs from f32bb8aa18ed3de286900f19ce4230fd93435dd0: '
            + product.stdout.strip())
    changed = git('diff', '--name-only', args.start, 'HEAD').stdout.splitlines()
    outside = [path for path in changed
               if path and not any(path == allowed or path.startswith(allowed)
                                   for allowed in ALLOWED)]
    require(not outside, 'changes outside this package whitelist: ' + ', '.join(outside))

    # Evidence documents.
    summary_path = args.summary.resolve()
    require(summary_path.is_file(), 'summary.json is missing: ' + str(summary_path))
    if not summary_path.is_file():
        print(json.dumps({'accepted': False, 'problems': problems}, ensure_ascii=False, indent=2))
        return 1
    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    evidence = summary_path.parent
    require(summary.get('schema') == 1, 'summary schema is not 1')
    require(summary.get('source_sha') == head, 'summary source_sha differs from GITHUB_SHA')
    require(summary.get('run_id') == run_id, 'summary run_id differs from GITHUB_RUN_ID')
    require(summary.get('attempt') == attempt, 'summary attempt differs from GITHUB_RUN_ATTEMPT')
    require(summary.get('complete') is True, 'measurement is not complete')
    require(summary.get('measured_process_starts', 0) >= args.launches,
            'fewer than %d measured process starts' % args.launches)
    require(summary.get('process_starts_total', 0) >= args.launches + 2,
            'preparation process starts are not accounted for')
    require(not summary.get('problems'), 'measurement recorded failing launches: %r'
            % (summary.get('problems'),))
    cohorts = summary.get('cohorts') or {}
    skipped = summary.get('skipped_cohorts') or {}
    txt_path = summary.get('txt_path') or {}
    expected = set(COHORTS)
    if txt_path.get('verdict') in TXT_REJECTIONS and skipped.get('import'):
        expected.discard('import')
    require(set(cohorts) == expected, 'named cohorts differ: %r (expected %r)'
            % (sorted(cohorts), sorted(expected)))
    require(all(count >= args.per_cohort for count in cohorts.values()),
            'a named cohort holds fewer than %d measured launches: %r' % (args.per_cohort, cohorts))

    # The original TXT input and its separated facts must be present in this run.
    fixture = (txt_path.get('fixture') or {})
    require(bool(fixture.get('sha256')) and isinstance(fixture.get('bytes'), int)
            and fixture['bytes'] > 0, 'original TXT fixture identity is not recorded')
    require(fixture.get('parameters') is not None,
            'original TXT generator parameters are not recorded')
    diagnosis = txt_path.get('diagnosis') or {}
    runs = diagnosis.get('runs') or []
    require(len(runs) >= 3, 'fewer than three TXT diagnostic runs')
    require(bool(diagnosis.get('verdict')), 'TXT diagnostic verdict is missing')
    for entry in runs:
        facts = entry.get('facts') or {}
        require(bool(facts.get('fixture')), 'diagnostic run lacks the input identity')
        require(bool(facts.get('import')), 'diagnostic run lacks the import observation')
        require('catalog' in facts, 'diagnostic run lacks the product catalog facts')
        require(bool(facts.get('probes')), 'diagnostic run lacks the shelf query facts')
    if skipped.get('import'):
        require(txt_path.get('verdict') in TXT_REJECTIONS,
                'the TXT cohort may only be skipped on a recorded rejection verdict')

    checks = summary.get('checks') or {}
    for name in REQUIRED_CHECKS:
        require(checks.get(name) is True, 'named check failed or missing: ' + name)
    require(summary.get('checks_passed') == summary.get('checks_total'),
            'not every general check passed')

    # No frame time, no enforced budget.
    require(summary.get('performance_accepted') is False,
            'performance acceptance must stay false in this package')
    require(summary.get('budget_enforced') is False, 'a numeric budget must not be enforced here')
    frame = summary.get('frame_time') or {}
    require(frame.get('measured') is False and bool(frame.get('reason')),
            'frame time must be reported as not measured with a reason')
    proposals = summary.get('proposed_budgets') or []
    require(bool(proposals), 'no budget proposal is recorded')
    for proposal in proposals:
        require(proposal.get('metric') in PROPOSED_METRICS,
                'unknown proposed metric: %r' % (proposal.get('metric'),))
        require(bool(proposal.get('basis')), 'proposal lacks a basis: %r' % (proposal,))
        numeric = proposal.get('proposal_ms', proposal.get('proposal_bytes'))
        require(isinstance(numeric, int) and numeric > 0,
                'proposal lacks a positive value: %r' % (proposal,))

    # Launch records and per-sample files.
    launches_path = evidence / 'per-launch.json'
    require(launches_path.is_file(), 'per-launch.json is missing')
    records = json.loads(launches_path.read_text(encoding='utf-8')) if launches_path.is_file() else []
    require(len(records) == summary.get('measured_process_starts'),
            'per-launch.json does not hold every measured launch')
    require(all(record.get('ok') is True for record in records), 'a launch record is incomplete')
    require(all(record.get('window_ms') is not None for record in records),
            'a launch never observed its window')
    require({record.get('cohort') for record in records} == expected,
            'launch cohorts differ from the expected cohorts')
    for record in records:
        if record.get('cohort') in ('cold_shelf', 'warm_shelf'):
            require(len((record.get('ops') or {}).get('page_turns') or []) == 0,
                    'shelf launch unexpectedly records book turns: ' + record.get('launch_id', '?'))
        if record.get('cohort') == 'reading':
            require(len((record.get('ops') or {}).get('page_turns') or []) >= 8,
                    'reading launch holds fewer than eight page turns: ' + record.get('launch_id', '?'))
        if record.get('cohort') in ('import', 'import_epub'):
            planted = (record.get('ops') or {}).get('import') or {}
            require(planted.get('visible') is True and planted.get('fixture_sha256'),
                    'import launch lacks a visible fixed fixture: ' + record.get('launch_id', '?'))
            require((planted.get('busy_input_samples') or 0) >= 1,
                    'import launch holds no busy-window input sample: ' + record.get('launch_id', '?'))

    for name in ('per-launch.csv', 'samples.csv', 'memory.csv', 'environment.json',
                 'preparation.json'):
        path = evidence / name
        require(path.is_file() and path.stat().st_size > 0, 'evidence file is missing or empty: ' + name)
    if (evidence / 'samples.csv').is_file():
        with (evidence / 'samples.csv').open(encoding='utf-8') as handle:
            rows = list(csv.DictReader(handle))
        operations = {row['op'] for row in rows}
        require('book_page_turn' in operations, 'samples.csv holds no book page-turn sample')
        require('input_during_import' in operations, 'samples.csv holds no import input sample')
        require(len(rows) >= 96 + 8, 'samples.csv holds too few raw samples: %d' % len(rows))
    if (evidence / 'memory.csv').is_file():
        with (evidence / 'memory.csv').open(encoding='utf-8') as handle:
            memory_rows = list(csv.DictReader(handle))
        require(len(memory_rows) >= len(records) * 10,
                'memory.csv holds too few working-set samples: %d' % len(memory_rows))

    # Environment identity.
    environment = summary.get('environment') or {}
    require(bool((environment.get('cpu') or {}).get('model')), 'CPU model is not recorded')
    require(bool((environment.get('os') or {}).get('version')), 'OS version is not recorded')
    display = environment.get('display') or {}
    require((display.get('screen_width_px') or 0) > 0 and (display.get('screen_height_px') or 0) > 0,
            'display geometry is not recorded')
    require((environment.get('memory_total_bytes') or 0) > 0, 'system memory is not recorded')
    measurement = environment.get('measurement') or {}
    require(measurement.get('frame_time_measured') is False,
            'environment must state that frame time is not measured')
    require(measurement.get('disk_cache_controlled') is False,
            'environment must state that the disk cache is not controlled')
    require('SendMessageTimeoutW' in (measurement.get('input_delivery') or ''),
            'input delivery path is not described')
    strategies = {(record.get('profile_strategy')) for record in records}
    require(strategies == {'fresh-sdk-library-copy', 'shared-profile'},
            'cold and warm strategies are not both recorded: %r' % (sorted(strategies),))

    # Package and corpus identity against the files on disk.
    package = args.package.resolve()
    exe = package / 'EXReader.exe'
    require(exe.is_file(), 'packaged EXReader.exe is missing')
    if exe.is_file():
        artifacts = environment.get('artifacts') or {}
        require(artifacts.get('exe_sha256') == sha256(exe), 'measured EXE digest differs from the package')
        require(artifacts.get('exe_bytes') == exe.stat().st_size,
                'measured EXE size differs from the package')
        require(artifacts.get('font_sha256') == sha256(package / 'Reader.otf'),
                'measured font digest differs from the package')
        files = artifacts.get('files') or {}
        require(files.get('EXReader.exe') == exe.stat().st_size,
                'package file table omits the measured EXE')
        require(artifacts.get('package_total_bytes') == sum(files.values()),
                'package total bytes do not match the recorded file table')
    preparation = summary.get('preparation') or {}
    corpus = preparation.get('corpus') or {}
    require(corpus.get('originals_in_catalog') == 2202,
            'product catalog does not hold 2202 originals')
    require(corpus.get('titles_and_bytes_exact') is True,
            'original titles or byte counts differ from the fixed inputs')
    require('"public_sdk_originals":2202' in ((preparation.get('seed') or {}).get('seed_stdout') or ''),
            'seed program did not report 2202 public-SDK originals')
    fixture_sha = (environment.get('corpus') or {}).get('reading_fixture_sha256')
    require(fixture_sha == sha256(package / 'Sample-positive.epub'),
            'reading fixture digest differs from the package')

    result = {'accepted': not problems, 'source_sha': head, 'run_id': run_id, 'attempt': attempt,
              'measured_process_starts': summary.get('measured_process_starts'),
              'cohorts': cohorts, 'checks_passed': summary.get('checks_passed'),
              'checks_total': summary.get('checks_total'),
              'performance_accepted': summary.get('performance_accepted'),
              'performance_reason': summary.get('performance_reason'),
              'problems': problems}
    (evidence / 'verification.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['accepted'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
