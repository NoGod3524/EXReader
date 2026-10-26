#!/usr/bin/env python3
"""Lightweight path and fail-closed protocol checks; runs in Actions only."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
if os.environ.get('GITHUB_ACTIONS') != 'true':
    raise SystemExit('run only in GitHub Actions')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(data):
    return hashlib.sha256(data).hexdigest()


def check_paths():
    for workflow in ('reader-composition-perf-gtk.yml', 'reader-composition-perf-windows.yml'):
        text = (ROOT / '.github/workflows' / workflow).read_text()
        # Source paths used by Python commands and CMake configure, not generated build paths.
        paths = set(re.findall(r'\b(?:tests|tools)/[A-Za-z0-9_./-]+\.py', text))
        paths.update(re.findall(r'cmake -S (apps/reader/[A-Za-z0-9_/-]+|tests/reader_perf_gtk/composition)', text))
        assert paths, workflow
        for path in paths:
            assert (ROOT / path).exists(), (workflow, path)
        assert 'workflow_call:' in text and 'workflow_dispatch:' in text
    cmake = ROOT / 'tests/reader_perf_gtk/composition/CMakeLists.txt'
    assert (cmake.parent / '../seed_library.c').resolve().is_file()
    assert '3.41.0 EXACT' in cmake.read_text()
    print('PASS workflow references and CMake source path')


def check_summary():
    m = load('gtk_summary', 'tests/reader_perf_gtk/composition/summarize.py')
    plan = {'launches': 32, 'kinds': ['a', 'b', 'c', 'd'],
            'turns': {'shelf_search_open_turn': (6, 2), 'shelf_search_variants': (2, 1),
                      'resume_turn': (4, 1)},
            'import_key_slots': 8, 'imports_per_launch': 3, 'import_turns': 2}
    counts, per_kind = m.expected_counts(plan)
    assert per_kind == 8 and counts['startup_shelf_rows'] == 24
    assert counts['page_turn_forward'] == 112 and counts['import_input_response'] == 192
    assert m.nearest_rank([3, 1, 2], .95) == 3
    print('PASS GTK sample plan and percentile protocol')


def check_windows():
    m = load('windows_gate', 'tests/reader_perf_windows/verify_composition.py')
    with tempfile.TemporaryDirectory() as temp:
        args = ['verify', '--summary', str(Path(temp) / 'missing.json'), '--package', temp,
                '--start', os.environ['GITHUB_SHA']]
        with mock.patch.object(sys, 'argv', args), mock.patch.dict(os.environ, {'GITHUB_SHA': '0' * 40}), contextlib.redirect_stdout(io.StringIO()) as output:
            code = m.main()
        assert code != 0 and 'HEAD does not equal GITHUB_SHA' in output.getvalue()
        assert 'summary.json is missing' in output.getvalue()
    assert 'frame_time_not_measured' in m.REQUIRED_CHECKS and 'numeric_budget_not_enforced' in m.REQUIRED_CHECKS
    print('PASS Windows missing and cross-source evidence rejected')


def check_gtk():
    m = load('gtk_verify', 'tests/reader_perf_gtk/composition/verify.py')
    source, run, attempt = os.environ['GITHUB_SHA'], int(os.environ['GITHUB_RUN_ID']), int(os.environ['GITHUB_RUN_ATTEMPT'])
    repository = os.environ['GITHUB_REPOSITORY']
    launch = {'process_exit': 0, 'vm_hwm_kb': 1}
    metric_report = {key: {'expected': 1, 'ok': 1} for key in m.CORE_METRICS}
    metrics = {key: {'count': 1, 'samples_ms': [1], 'min_ms': 1, 'p50_ms': 1,
                     'p95_ms': 1, 'max_ms': 1} for key in m.CORE_METRICS}
    report = {'accepted': True, 'problems': [], 'complete_product': False, 'source_sha': source,
              'run_id': run, 'attempt': attempt, 'launches': 30, 'metrics': metric_report,
              'samples': 1, 'checks': []}
    summary = {'source_sha': source, 'run_id': run, 'attempt': attempt, 'launches': {'completed': 30},
               'metrics': metrics, 'guards': {'head': source, 'github_sha': source, 'components': {'src': 'tree'}},
               'environment': {'payload': {}, 'seed': {'corpus_sha256': 'x'}},
               'corpus': {'books': 2202, 'long_book_bytes': 1, 'total_original_bytes': 1},
               'rss': {'per_launch_kb': [1], 'p50_kb': 1, 'max_kb': 1},
               'paint': {'total': 1}, 'calibration': {}}
    samples = {'source_sha': source, 'samples': [{'outcome': 'ok'}], 'plan': [{}]}
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        def make_zip(changed=False):
            files = {name: b'{}' for name in m.REQUIRED_MEMBERS - {'bundle.json'}}
            for name, value in {'report.json': report, 'summary.json': summary, 'samples.json': samples,
                                'launches.json': {'launches': [launch] * 30}}.items():
                files[name] = json.dumps(value).encode()
            listed = {name: {'bytes': len(data), 'sha256': digest(data)} for name, data in files.items()}
            if changed:
                files['samples.json'] += b' '
            files['bundle.json'] = json.dumps({'files': listed}).encode()
            archive = root / 'source.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                for name, data in files.items():
                    z.writestr(name, data)
            return archive
        def run_case(caller, bad_attempt=False, corrupt=False):
            archive = make_zip(corrupt)
            zipdata = archive.read_bytes()
            def job(name):
                return {'name': name, 'head_sha': source, 'run_id': run,
                        'run_attempt': attempt, 'status': 'completed', 'conclusion': 'success', 'id': 1}
            prefix = 'caller / ' if caller else ''
            jobs = [job(prefix + m.PERF_JOB), job(prefix + m.VERIFY_JOB)]
            if caller:
                jobs.append(job('unrelated caller job'))
            path = '.github/workflows/caller.yml' if caller else m.WORKFLOW
            record = {'id': run, 'head_sha': source, 'run_attempt': attempt, 'path': path, 'event': 'workflow_dispatch'}
            artifact = {'name': f'reader-composition-perf-gtk-{run}-{attempt}', 'expired': False,
                        'size_in_bytes': len(zipdata), 'digest': 'sha256:' + digest(zipdata),
                        'workflow_run': {'id': run, 'head_sha': source}, 'id': 9, 'expires_at': 'later'}
            if bad_attempt:
                jobs[0]['run_attempt'] = attempt + 1
            def pages(path, key):
                return jobs if key == 'jobs' else [artifact]
            def download(_, destination):
                shutil.copyfile(archive, destination)
            env = {'GITHUB_WORKFLOW_REF': repository + '/' + path + '@refs/heads/test'}
            args = ['verify', '--output', str(root / 'out')]
            with mock.patch.object(m, 'api', return_value=record), mock.patch.object(m, 'pages', side_effect=pages), \
                 mock.patch.object(m, 'download', side_effect=download), mock.patch.object(sys, 'argv', args), \
                 mock.patch.dict(os.environ, env), contextlib.redirect_stdout(io.StringIO()):
                try:
                    m.main()
                    return True
                except SystemExit:
                    return False
        assert run_case(False) and run_case(True)
        assert not run_case(True, bad_attempt=True) and not run_case(False, corrupt=True)
    print('PASS GTK direct/caller identity and rejection of cross-attempt or modified evidence')


if __name__ == '__main__':
    check_paths()
    check_summary()
    check_windows()
    check_gtk()
