# SPDX-License-Identifier: MIT
"""Actions-only: run the installed C, C++, regression, lock and fault consumers and judge the reports."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys

# category prefix -> minimum number of named checks that must be present and passing
REQUIRED_PREFIXES = {
    'version:': 1, 'sha256:': 2, 'exact:': 20, 'aspect:': 4, 'alpha:': 4, 'missing cover:': 5, 'library cover:': 4,
    'preview:': 13, 'origins:': 1, 'unchanged:': 2, 'limits:': 21, 'anomalous image:': 4, 'decoded bytes:': 2,
    'lru:': 6, 'mishit:': 9, 'corruption (': 24, 'recovery:': 6, 'cancel ': 10, 'reopen:': 7, 'owner:': 3,
    'bounded open:': 5, 'disk budget:': 4, 'owner lock:': 2, 'publish:': 3, 're-entry:': 2,
}
# individually required behaviours (exact names)
REQUIRED_EXACT = [
    'missing cover: host with no encoded cover gets the normal placeholder',
    'anomalous image: a PNG header declaring 30000x30000 over invalid data is refused before decoding (the SDK reports a damaged header)',
    'limits: a valid 9000x1 PNG above the 8192 SDK edge limit is refused with a limit status before decoding',
    'limits: a valid 4100x4100 PNG above 16,777,216 pixels is refused with a limit status before decoding',
    'limits: a 4294967295x4294967295 box is refused without allocation',
    'limits: a 9,000,000-pixel image above max_source_pixels=1,000,000 is refused before any decode allocation',
    'decoded bytes: a 3000x3000 cover reports 36,000,000 transient decoded bytes',
    'preview: PDF page 1 left half is red and right half is blue',
    'preview: PDF page 1 renders 100x50 and is labelled a first-page preview, not an author cover',
    'origins: an author cover and a first-page preview of the same book are separate entries with separate labels',
    'lru: the least recently used entry (6x6) was the one evicted',
    'reopen: LRU recency survives close and reopen (the touched entry stays, the stale one is evicted)',
    'unchanged: the stored original and the book rows are byte-identical after previews',
    'unchanged: every original fixture file is byte-identical after all operations',
    'owner: a call from another thread is refused and changes nothing',
    'bounded open: a reopen with max_entries=3 retains at most 3 while scanning, never 40',
    'bounded open: 1300 candidates are cleaned in one pass and the unrelated files are left untouched',
    'disk budget: an OK open leaves every own entry file inside max_entries=5 and max_total_bytes=4096',
    'disk budget: a directory above the scan ceiling is refused with RTH_LIMIT and no cache',
    'owner lock: a second cache handle on the same directory is refused',
    'owner lock: closing the first handle lets a new cache own the directory',
    'publish: an index that cannot be atomically replaced makes open fail with RTH_IO',
    'publish: a hard link planted at a temporary name is neither followed nor truncated',
    're-entry: stats, clear, find and close are all refused inside a control callback',
]
# The cross-process contract and the review findings, one process per phase.
REQUIRED_REGRESS = [
    'regress: LRU recency written by one process survives an independent reopen',
    'regress: reopening with a smaller entry bound evicts the stale entry, not the touched ones',
    'regress: a pre-seeded hard link at a temporary name is never followed or truncated',
    'regress: a fresh temporary file of another live cache instance is preserved by open',
    'regress: a stale temporary of the cache naming is removed by open',
    'regress: an index that cannot be atomically replaced is reported instead of silently accepted',
    'regress: re-entry from a control callback is refused by the cache statistics call',
    'regress: a directory with many more candidates than the scan budget leaves the uninspected files untouched',
    'regress: an unrepresentable directory path is refused with a status instead of an escaping exception',
    'regress: a second cache on one directory is refused while another process owns it',
    'regress: a killed owner\'s lock is released by the OS and the directory reopens',
]
# Allocation-failure ownership, one process per mode.
REQUIRED_FAULT = [
    'fault: an allocation failure inside open reports a status, clears the output and leaks nothing',
    'fault: an allocation failure after the thumbnail bytes exist reports a status with no output, loses no memory and the cache stores on retry',
    'fault: an allocation failure on the library cover path frees the borrowed blob and leaves the cache usable',
]
LINE = re.compile(r'^(PASS|FAIL) (.+?)(?: :: (.*))?$')


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tree(root):
    root = Path(root)
    return [{'path': p.relative_to(root).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha256(p)}
            for p in sorted(root.rglob('*')) if p.is_file()]


def run_consumer(program, extra, log_dir, label, timeout):
    result = subprocess.run([str(program)] + extra, capture_output=True, text=True, encoding='utf-8',
                            errors='replace', timeout=timeout)
    text = result.stdout + '\n' + result.stderr
    (log_dir / (label + '.log')).write_text(text, encoding='utf-8')
    print(text)
    names = []
    for line in result.stdout.splitlines():
        match = LINE.match(line.strip())
        if match:
            names.append({'name': match.group(2), 'pass': match.group(1) == 'PASS', 'detail': match.group(3) or '', 'mode': label})
    return result.returncode, names


def main():
    p = argparse.ArgumentParser()
    for name in ('probe', 'c-consumer', 'regress', 'fault', 'fixtures', 'repo-fixtures', 'installed', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args(); assert os.environ.get('GITHUB_ACTIONS') == 'true'
    out = a.output.resolve(); out.mkdir(parents=True)

    manifest = json.loads((a.fixtures / 'manifest.json').read_text(encoding='utf-8'))
    for name, entry in manifest.items():
        data = (a.fixtures / name).read_bytes()
        assert len(data) == entry['bytes'] and hashlib.sha256(data).hexdigest() == entry['sha256'], name

    c_work = out / 'c-work'
    c = subprocess.run([str(a.c_consumer.resolve()), str(c_work), str((a.fixtures / 'grad16x8.png').resolve())],
                       capture_output=True, text=True, encoding='utf-8', timeout=120)
    (out / 'c-consumer.log').write_text(c.stdout + '\n' + c.stderr, encoding='utf-8')
    print(c.stdout); print(c.stderr)
    assert c.returncode == 0 and c.stdout.strip() == 'c-consumer-ok', 'installed C consumer refused: exit %s' % c.returncode

    # Regression consumer: recency writer, independent reopen judge, cache/publish/scan
    # suite, and the cross-process owner lock (holder, blocked, released after a kill).
    regress = a.regress.resolve()
    fixture_png = (a.fixtures / 'grad16x8.png').resolve()
    regress_work = out / 'regress-work'
    regress_names = []
    for mode in ('lru-write', 'lru-verify', 'cache'):
        code, names = run_consumer(regress, ['--mode', mode, '--work', str(regress_work), '--fixture', str(fixture_png)],
                                   out, 'regress-' + mode, 900)
        assert all(n['pass'] for n in names), 'regression failures: %s' % [n['name'] for n in names if not n['pass']]
        assert code == 0, 'regression consumer mode %s exited %s' % (mode, code)
        regress_names += names
    holder = subprocess.Popen([str(regress), '--mode', 'lock-hold', '--work', str(regress_work), '--fixture', str(fixture_png)],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
    try:
        first = holder.stdout.readline()
        assert 'SETUP lock-hold' in first, 'lock holder did not start: %r' % first
        code, names = run_consumer(regress, ['--mode', 'lock-busy', '--work', str(regress_work), '--fixture', str(fixture_png)],
                                   out, 'regress-lock-busy', 300)
        assert all(n['pass'] for n in names), 'lock holder was not refused: %s' % [n['name'] for n in names if not n['pass']]
        assert code == 0, 'lock-busy exited %s' % code
        regress_names += names
    finally:
        holder.kill()
        holder.wait(timeout=120)
    code, names = run_consumer(regress, ['--mode', 'lock-release', '--work', str(regress_work), '--fixture', str(fixture_png)],
                               out, 'regress-lock-release', 300)
    assert all(n['pass'] for n in names), 'released lock was not usable: %s' % [n['name'] for n in names if not n['pass']]
    assert code == 0, 'lock-release exited %s' % code
    regress_names += names
    regress_check_names = [n['name'] for n in regress_names]
    assert len(regress_check_names) == len(set(regress_check_names)), 'duplicate regression check names'
    missing = [n for n in REQUIRED_REGRESS if n not in regress_check_names]
    assert not missing, 'regression checks absent: %s' % missing

    # Fault consumer: an injected allocation failure at every point of open, of a store
    # that already holds thumbnail pixels, and of the borrowed-blob cover path.
    fault = a.fault.resolve()
    fault_work = out / 'fault-work'
    fault_names = []
    for mode in ('open', 'store', 'library'):
        code, names = run_consumer(fault, ['--mode', mode, '--work', str(fault_work / mode), '--fixtures', str(a.fixtures.resolve()),
                                           '--repo-fixtures', str(a.repo_fixtures.resolve())], out, 'fault-' + mode, 1200)
        assert all(n['pass'] for n in names), 'fault failures: %s' % [n['name'] for n in names if not n['pass']]
        assert code == 0, 'fault consumer mode %s exited %s' % (mode, code)
        fault_names += names
    fault_check_names = [n['name'] for n in fault_names]
    missing = [n for n in REQUIRED_FAULT if n not in fault_check_names]
    assert not missing, 'fault checks absent: %s' % missing

    work = out / 'work'; work.mkdir()
    result = subprocess.run([str(a.probe.resolve()), '--fixtures', str(a.fixtures.resolve()), '--repo-fixtures', str(a.repo_fixtures.resolve()),
                             '--work', str(work), '--report', str(out / 'probe.json')],
                            capture_output=True, text=True, encoding='utf-8', timeout=2400)
    (out / 'probe.log').write_text(result.stdout + '\n' + result.stderr, encoding='utf-8')
    print(result.stdout); print(result.stderr)
    report_path = out / 'probe.json'
    assert report_path.exists(), 'C++ thumbnail probe wrote no report: exit %s' % result.returncode
    report = json.loads(report_path.read_text(encoding='utf-8'))
    checks = report['checks']
    failed = [c['name'] for c in checks if c['pass'] is not True]
    assert report['failures'] == len(failed) and not failed, 'failed checks: %s' % failed
    assert result.returncode == 0, 'C++ thumbnail probe exit %s' % result.returncode
    names = [c['name'] for c in checks]
    assert len(names) == len(set(names)), 'duplicate check names'
    problems = []
    for prefix, minimum in REQUIRED_PREFIXES.items():
        count = sum(1 for n in names if n.startswith(prefix))
        if count < minimum:
            problems.append('%s has %d of %d required checks' % (prefix, count, minimum))
    problems += ['required check absent: ' + n for n in REQUIRED_EXACT if n not in names]
    for n in names:
        m = re.match(r'cancel .*cancelling at each of (\d+) poll points', n)
        if m and int(m.group(1)) < 3:
            problems.append('too few poll points: ' + n)
    # The module hashed every fixture; Python re-derives them independently.
    for name, entry in manifest.items():
        if report['fixture_sha256'].get(name) != entry['sha256']:
            problems.append('probe SHA-256 of %s differs from hashlib' % name)
    assert report['expectations'] >= 10, 'expectation file shrank'
    assert len(report['measurements']) >= 4, 'measurements missing'
    assert not problems, 'coverage problems: %s' % problems
    expected_skipped = [] if report['threads']['before'] >= 0 else ['the module creates no thread (thread count is not measured on this platform)']
    assert report['skipped'] == expected_skipped, 'unexpected skips: %s' % report['skipped']

    shutil.rmtree(work)  # caches and library databases are scratch; kept only when a check failed
    shutil.rmtree(regress_work)
    shutil.rmtree(fault_work)
    runner = os.environ.get('RUNNER_OS', '').lower() or sys.platform
    summary = {
        'accepted': True, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
        'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'platform': sys.platform, 'platform_detail': platform.platform(),
        'runner_os': os.environ.get('RUNNER_OS'), 'runner_arch': os.environ.get('RUNNER_ARCH'), 'image': os.environ.get('ImageVersion'),
        'checks': len(checks), 'check_names': names, 'skipped': report['skipped'], 'threads': report['threads'],
        'regress_checks': len(regress_names), 'regress_check_names': regress_check_names, 'regress_results': regress_names,
        'fault_checks': len(fault_names), 'fault_check_names': fault_check_names, 'fault_results': fault_names,
        'measurements': report['measurements'], 'fixtures': manifest,
        'probe_sha256': sha256(a.probe), 'c_consumer_sha256': sha256(a.c_consumer), 'regress_sha256': sha256(a.regress),
        'fault_sha256': sha256(a.fault), 'installed_files': tree(a.installed),
        'granted_platform': runner, 'performance_claimed': False, 'host_ui_accepted': False, 'six_platform_accepted': False,
        'complete_product': False, 'schema_changed': False, 'sdk_changed': False,
    }
    (out / 'result.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8'); print(json.dumps(summary), flush=True)


if __name__ == '__main__': main()
