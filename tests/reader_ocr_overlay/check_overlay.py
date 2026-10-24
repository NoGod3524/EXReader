#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Judge the installed OCR overlay consumer inside GitHub Actions.

Runs the probe against one generated page set and one model directory, then
checks the named verdicts, the fixture/model identity, the source and the
consumer binaries. Writes report.json first, then summary.json binding
source/run/attempt to that report digest. Nothing here runs locally.
"""
import argparse
import hashlib
import json
import os
import platform
import pathlib
import subprocess
import sys
import time

REQUIRED = {
    'fixture_document_created', 'engine_open_eng', 'recognize_page_ok',
    'recognize_page_source_labels', 'recognize_page_items_wellformed',
    'recognize_page_locate_rows', 'recognize_page_pixel_quad_consistent',
    'recognize_page_confidence_filter', 'render_fixture_page',
    'recognize_bitmap_ok', 'recognize_bitmap_matches_page',
    'snapshot_outlives_bitmap', 'snapshot_outlives_document',
    'rotation_90_page', 'rotation_180_page', 'rotation_270_page',
    'rotation_quads_invariant', 'content_rotation_90_upright',
    'scale_1_5_page', 'scale_1_5_quads_agree', 'blank_page_empty',
    'bars_page_no_letters', 'cancel_before_render',
    'cancel_during_recognition', 'timeout_deadline', 'stale_still_current',
    'still_current_commits', 'missing_model_directory', 'missing_model_file',
    'empty_model_file', 'argument_null_engine', 'argument_options',
    'argument_scale_rotation_confidence', 'argument_hard_caps',
    'argument_bitmap_mismatch', 'argument_page_range', 'argument_language',
    'limit_pixels_before_render', 'limit_snapshot_budget',
    'render_failure_propagates', 'busy_reentrant', 'to_fixed_text_lines',
    'to_fixed_text_words', 'to_fixed_text_rejects_level',
    'to_fixed_text_cancelled', 'to_fixed_text_independent',
    'thread_foreign_call_rejected', 'thread_foreign_close_rejected',
    'document_untouched', 'engine_close_null', 'engine_close_owner',
}
ALLOWED_SKIPS = {'windows_host_scope', 'mobile_host_scope', 'model_chi_sim'}
STATUSES = {'PASS', 'FAIL', 'SKIP', 'PENDING'}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest_dir(root, names=None):
    out = {}
    root = pathlib.Path(root)
    for path in sorted(root.iterdir()):
        if not path.is_file():
            continue
        if names is not None and path.name not in names:
            continue
        out[path.name] = {'bytes': path.stat().st_size, 'sha256': sha256(path)}
    return out


def parse_results(path):
    rows, problems = [], []
    text = path.read_text(encoding='utf-8', errors='replace')
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        columns = line.split('\t')
        if len(columns) != 3:
            problems.append(f'results line {number} does not have three columns')
            continue
        name, status, detail = columns
        if status not in STATUSES:
            problems.append(f'{name}: unknown status {status}')
        rows.append({'name': name, 'status': status, 'detail': detail})
    names = [row['name'] for row in rows]
    duplicates = {name for name in names if names.count(name) > 1}
    if duplicates:
        problems.append('duplicate verdicts: ' + ', '.join(sorted(duplicates)))
    missing = sorted(REQUIRED - set(names))
    if missing:
        problems.append('required verdicts missing: ' + ', '.join(missing))
    if len(rows) < 50:
        problems.append(f'only {len(rows)} named verdicts were reported')
    return rows, problems


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--probe', required=True)
    parser.add_argument('--fixtures', required=True)
    parser.add_argument('--models', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--binary', action='append', default=[])
    args = parser.parse_args()

    output = pathlib.Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    fixtures = pathlib.Path(args.fixtures)
    models = pathlib.Path(args.models)
    problems = []

    identity = {key: os.environ.get(key, '') for key in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT')}
    if not identity['GITHUB_SHA']:
        problems.append('GITHUB_SHA is unset; this checker runs only in Actions')

    manifest_path = fixtures / 'manifest.json'
    manifest = {}
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        if manifest.get('schema') != 1:
            problems.append('fixture manifest schema is not 1')
        lines = manifest.get('lines') or []
        if len(lines) != 4:
            problems.append(f'fixture manifest has {len(lines)} lines instead of 4')
        for name, image in (manifest.get('images') or {}).items():
            if image.get('width') != 900 or image.get('height') != 1200:
                problems.append(f'fixture image {name} is not 900x1200')
    else:
        problems.append('fixture manifest.json is missing')

    fixtures_before = digest_dir(fixtures)
    models_before = digest_dir(models)
    for name, record in (manifest.get('images') or {}).items():
        actual = fixtures_before.get(record['path'])
        if not actual or actual['sha256'] != record['sha256']:
            problems.append(f'fixture {record["path"]} does not match the manifest digest')

    model_identity = {}
    identity_path = models / 'identity.json'
    if identity_path.is_file():
        model_identity = json.loads(identity_path.read_text(encoding='utf-8'))
        for name, digest in (model_identity.get('files') or {}).items():
            actual = models_before.get(name)
            if not actual or actual['sha256'] != digest:
                problems.append(f'model {name} does not match the registered digest')
        if not (model_identity.get('license') or ''):
            problems.append('model identity does not register a licence')
    else:
        problems.append('model identity.json is missing')

    results_path = output / 'results.tsv'
    if results_path.exists():
        results_path.unlink()
    started = time.time()
    probe_exit, probe_stdout, probe_stderr = None, '', ''
    try:
        run = subprocess.run([args.probe, str(fixtures), str(models), str(results_path), str(output)],
                             capture_output=True, text=True, timeout=3600)
        probe_exit, probe_stdout, probe_stderr = run.returncode, run.stdout, run.stderr
    except (OSError, subprocess.SubprocessError) as failure:
        problems.append(f'probe did not run: {failure}')
    duration_ms = int((time.time() - started) * 1000)

    rows, result_problems = parse_results(results_path) if results_path.is_file() else ([], ['results.tsv was not written'])
    problems.extend(result_problems)
    counts = {status: sum(1 for row in rows if row['status'] == status) for status in sorted(STATUSES)}
    bad = [row['name'] for row in rows if row['status'] in ('FAIL', 'PENDING')]
    if bad:
        problems.append('failing or unreached verdicts: ' + ', '.join(sorted(bad)))
    wrong_skip = sorted({row['name'] for row in rows if row['status'] == 'SKIP'} - ALLOWED_SKIPS)
    if wrong_skip:
        problems.append('undeclared skips: ' + ', '.join(wrong_skip))
    if probe_exit not in (0, 1):
        problems.append(f'probe exited with {probe_exit}')

    fixtures_after = digest_dir(fixtures)
    models_after = digest_dir(models)
    if fixtures_before != fixtures_after:
        problems.append('the probe changed the fixture bytes')
    if models_before != models_after:
        problems.append('the probe changed the model bytes')
    if sorted(os.listdir(output)) != sorted(['results.tsv']):
        problems.append('the probe wrote files besides results.tsv')

    binaries = {}
    for item in args.binary:
        name, _, path = item.partition('=')
        candidate = pathlib.Path(path)
        if candidate.is_file():
            binaries[name] = {'path': path, 'bytes': candidate.stat().st_size, 'sha256': sha256(candidate)}
        else:
            problems.append(f'binary {name} is missing: {path}')
    probe_record = binaries.get('probe') or {'sha256': sha256(pathlib.Path(args.probe))}

    accepted = not problems
    report = {
        'id': 'J15',
        'title': 'reader_ocr_overlay temporary OCR text snapshot',
        'platform': {'system': platform.system(), 'machine': platform.machine(),
                     'python': platform.python_version(), 'runner_os': os.environ.get('RUNNER_OS', '')},
        'verdicts': rows,
        'counts': counts,
        'probe': {'exit_code': probe_exit, 'duration_ms': duration_ms,
                  'stdout_sha256': hashlib.sha256(probe_stdout.encode()).hexdigest(),
                  'stdout_tail': probe_stdout[-4000:], 'stderr_tail': probe_stderr[-4000:]},
        'fixtures': fixtures_before,
        'manifest': manifest,
        'models': models_before,
        'model_identity': model_identity,
        'binaries': binaries,
        'problems': problems,
        'accepted': accepted,
    }
    report_path = output / 'report.json'
    report_bytes = (json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    report_path.write_bytes(report_bytes)
    report_sha = hashlib.sha256(report_bytes).hexdigest()

    summary = {
        'id': 'J15',
        'component': 'reader_ocr_overlay',
        'source': identity['GITHUB_SHA'],
        'identity': identity,
        'platform': report['platform'],
        'accepted': accepted,
        'checks_total': len(rows),
        'checks_failed': counts.get('FAIL', 0),
        'checks_pending': counts.get('PENDING', 0),
        'checks_skipped': counts.get('SKIP', 0),
        'checks_passed': counts.get('PASS', 0),
        'verdict_names': [row['name'] for row in rows],
        'verdict_statuses': {row['name']: row['status'] for row in rows},
        'fixtures': fixtures_before,
        'models': models_before,
        'model_identity': model_identity,
        'binaries': binaries,
        'probe': {'exit_code': probe_exit, 'duration_ms': duration_ms},
        'results_sha256': sha256(results_path) if results_path.is_file() else '',
        'report_sha256': report_sha,
        'report_path': 'report.json',
        'problems': problems,
        'scope': {
            'implemented': 'installed C ABI component, C and C++ installed consumers, real Tesseract recognition on a rendered fixed page, rotation/scale coordinate mapping, cancellation/deadline/staleness, model-missing paths, snapshot lifetime, document immutability',
            'not_covered': ['Windows host', 'Android host', 'Apple host', 'real user scans', 'Chinese/other traineddata recognition', 'hard CPU/RSS isolation', 'host UI wiring'],
        },
    }
    summary_path = output / 'summary.json'
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'accepted': accepted, 'checks_total': len(rows), 'counts': counts, 'problems': problems},
                     ensure_ascii=False))
    return 0 if accepted else 1


if __name__ == '__main__':
    sys.exit(main())
