#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Same-source diagnosis of the original 16 MiB single-document TXT import.

The accepted first-round observation recorded that this exact input never became
visible after its import. This script replays the original input (same frozen
generator parameters) through the real Win32 controls and records the facts
separately so the cause can be named instead of inferred from a filtered view:

  * the input itself: declared size, actual bytes, SHA-256, first line, generator;
  * the real import: dispatch, whether the import control returned to idle inside
    the original 300 s budget, elapsed time and the verbatim status text;
  * the public shelf query at the product level: real search-box queries with
    their own text and observed row counts;
  * the product catalog mapping and title (product schema only, never SDK SQL);
  * whether the imported original opens through the public SDK path.

It never changes the SDK, never relaxes the original waits and never turns a
failure into an expected rejection: a rejection is reported as a rejection.
"""
import argparse
import json
import os
import re
import shutil
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import perf_windows as perf  # noqa: E402

ORIGINAL = {
    'format': 'TXT',
    'declared_size': 16 << 20,
    'header': 'Perf Import %04d\n',
    'block': 'Perf Import %04d line %04d keeps the import worker busy while input continues.\n',
    'block_lines': 512,
    'title_expectation': 'file name stem (host fallback when the SDK title is empty or Untitled)',
    'import_wait_s': 300.0,
    'search_wait_s': 90.0,
    'open_wait_s': 120.0,
}
PROBE_TEMPLATES = ('Perf Import %04d', 'fixture %04d', 'Perf import', 'Untitled')
ROW_TITLE = re.compile(r'《(.*?)》')


def probe_needles(index):
    return tuple(template % index if '%04d' in template else template
                 for template in PROBE_TEMPLATES)


def row_title(row):
    match = ROW_TITLE.search(row or '')
    return match.group(1) if match else None


def original_fixture(directory, index):
    """Byte-identical replay of the first-round fixture generator."""
    path = directory / ('Perf Import %04d.txt' % index)
    header = ORIGINAL['header'] % index
    unit = (header + ''.join(ORIGINAL['block'] % (index, number)
                             for number in range(ORIGINAL['block_lines']))).encode()
    with path.open('wb') as handle:
        written = 0
        while written < ORIGINAL['declared_size']:
            handle.write(unit)
            written += len(unit)
    first_line = path.read_bytes().split(b'\n', 1)[0].decode('utf-8', 'replace')
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': perf.sha256(path),
            'generator': {'header': header, 'block_lines': ORIGINAL['block_lines'],
                          'unit_bytes': len(unit), 'declared_size': ORIGINAL['declared_size']},
            'first_line': first_line,
            'first_line_is_expected_title': first_line == 'Perf Import %04d' % index}


def settle_rows(host, timeout=8.0):
    """Read the list after the host's own 200 ms debounce and a stable snapshot."""
    started = time.monotonic()
    previous = None
    stable = 0
    while time.monotonic() - started < timeout:
        rows = host.rows()
        if rows == previous:
            stable += 1
            if stable >= 2 and time.monotonic() - started >= 0.5:
                return rows
        else:
            stable = 0
            previous = rows
        time.sleep(0.1)
    return host.rows()


def query(host, needle, wait_s):
    started = perf.now_ms()
    try:
        echo = host.set_text(host.control('search'), needle)
    except TimeoutError as error:
        return {'needle': needle, 'echo': None, 'rows': None, 'count': None,
                'first_rows': [], 'elapsed_ms': round(perf.now_ms() - started, 3),
                'timed_out': True, 'error': str(error)}
    rows = settle_rows(host, timeout=min(wait_s, 8.0))
    return {'needle': needle, 'echo': echo, 'rows': len(rows), 'count': len(rows),
            'first_rows': rows[:3], 'elapsed_ms': round(perf.now_ms() - started, 3),
            'timed_out': False}


def import_original(host, fixture, wait_s):
    echoed = host.set_text(host.control('path'), fixture['path'])
    path_accepted = echoed == fixture['path']
    started = perf.now_ms()
    host.click('import')
    samples = []
    completed = False
    while perf.now_ms() - started < wait_s * 1000:
        busy = not host.import_enabled()
        samples.append({'t_ms': round(perf.now_ms() - started, 3), 'busy': busy})
        if not busy:
            completed = True
            break
        time.sleep(0.02)
    elapsed = round(perf.now_ms() - started, 3)
    status = ''
    try:
        status = host.status()
    except TimeoutError:
        status = '<status read timed out>'
    return {'path_accepted': path_accepted, 'echo': echoed, 'completed': completed,
            'elapsed_ms': elapsed, 'status_after_import': status,
            'budget_s': wait_s, 'busy_samples': len(samples),
            'timed_out': not completed,
            'status_indicates_failure': ('失败' in status) or ('错误' in status)}


def catalog_facts(profile, fixture):
    database = Path(str(profile / 'library.sqlite') + '.product.sqlite')
    facts = {'catalog_path': str(database), 'exists': database.exists()}
    if not database.exists():
        return facts
    key = 'txt:' + fixture['sha256']
    with sqlite3.connect(str(database)) as connection:
        facts['total_books'] = connection.execute(
            'SELECT count(*) FROM reader_books').fetchone()[0]
        row = connection.execute(
            'SELECT book_key, format, source_sha256, source_bytes, title, deleted '
            'FROM reader_books WHERE book_key=?', (key,)).fetchone()
        if row:
            facts['row'] = {'book_key': row[0], 'format': row[1], 'source_sha256': row[2],
                            'source_bytes': row[3], 'title': row[4], 'deleted': row[5]}
        else:
            facts['row'] = None
        facts['sha_matches_input'] = bool(row and row[2] == fixture['sha256'])
        facts['bytes_match_input'] = bool(row and row[3] == fixture['bytes'])
        mapping = connection.execute(
            'SELECT sdk_book_id, location_kind FROM reader_local_books WHERE book_key=?',
            (key,)).fetchone()
        facts['local_mapping'] = ({'sdk_book_id': mapping[0], 'location_kind': mapping[1]}
                                  if mapping else None)
        facts['newest_rows'] = [
            {'book_key': item[0], 'title': item[1], 'source_bytes': item[2]}
            for item in connection.execute(
                'SELECT book_key, title, source_bytes FROM reader_books '
                'ORDER BY rowid DESC LIMIT 3')]
    return facts


def open_observed(host, title, wait_s):
    if not title:
        return {'attempted': False}
    found = query(host, title, 8.0)
    if not found['rows']:
        return {'attempted': True, 'search': found, 'selected': False, 'opened': False}
    started = perf.now_ms()
    try:
        host.lb_set(0)
        host.wait_enabled('open', 30)
        host.click('open')
        label = None

        def opened():
            nonlocal label
            try:
                if host.text_length(host.control('page_label'), 200) <= 6:
                    return None
            except TimeoutError:
                return None
            label = host.label(5000)
            return (label,) if perf.page_key(label) else None

        host.poll(opened, wait_s, interval=0.01)
        return {'attempted': True, 'search': found, 'selected': True, 'opened': True,
                'elapsed_ms': round(perf.now_ms() - started, 3), 'label': label,
                'status': host.status()}
    except (TimeoutError, perf.MeasurementFault) as error:
        return {'attempted': True, 'search': found, 'selected': True, 'opened': False,
                'elapsed_ms': round(perf.now_ms() - started, 3), 'error': str(error),
                'status': host.status()}


BISECT_MIB = (0.25, 0.5, 1, 2, 4, 8, 12, 16)


def sized_fixture(directory, mib):
    """Same line-oriented shape as the original, at a smaller declared size."""
    size = int(mib * (1 << 20))
    path = directory / ('Bisect %g MiB.txt' % mib)
    header = 'Bisect %g MiB\n' % mib
    unit = (header + ''.join('Bisect %g MiB line %04d keeps the import worker busy.\n'
                             % (mib, number) for number in range(512))).encode()
    written = 0
    lines = 1
    with path.open('wb') as handle:
        handle.write(unit)
        written = len(unit)
        lines += 512
        while written < size:
            handle.write(unit)
            written += len(unit)
            lines += 512
    return {'path': str(path), 'declared_mib': mib, 'bytes': path.stat().st_size,
            'sha256': perf.sha256(path), 'text_lines': lines}


def bisect_imports(host, directory, wait_s):
    results = []
    for mib in BISECT_MIB:
        fixture = sized_fixture(directory, mib)
        record = {'declared_mib': mib, 'bytes': fixture['bytes'], 'text_lines': fixture['text_lines'],
                  'sha256': fixture['sha256']}
        try:
            record.update(import_original(host, fixture, wait_s))
        except (TimeoutError, perf.MeasurementFault) as error:
            record.update({'completed': False, 'timed_out': True, 'error': str(error),
                           'status_after_import': None, 'status_indicates_failure': True})
        results.append(record)
        print(json.dumps({'bisect_mib': mib, 'bytes': record['bytes'],
                          'status': record.get('status_after_import'),
                          'rejected': record.get('status_indicates_failure')}, ensure_ascii=False),
              flush=True)
    return results


def classify(run):
    facts = run['facts']
    if not facts['import']['completed'] or facts['import']['status_indicates_failure']:
        return 'import_rejected'
    catalog = facts['catalog']
    if not catalog.get('row'):
        return 'imported_not_in_catalog'
    if not (catalog.get('sha_matches_input') and catalog.get('bytes_match_input')):
        return 'catalog_identity_mismatch'
    title = catalog['row']['title']
    probe = run['facts']['probes'].get(run['expected_title']) or {}
    if title == run['expected_title']:
        return 'consistent' if probe.get('count') else 'title_matches_but_filter_missed'
    return 'title_mismatch_after_success'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--seed', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--runs', type=int, default=3)
    args = parser.parse_args()
    if os.name != 'nt':
        raise SystemExit('This diagnosis runs on Windows only')
    package = args.package.resolve()
    exe, font = package / 'EXReader.exe', package / 'Reader.otf'
    for path in (exe, font, args.seed.resolve()):
        if not Path(path).exists():
            raise SystemExit('missing input: ' + str(path))
    output = args.output.resolve()
    if output.exists():
        raise SystemExit('choose a fresh diagnosis directory')
    output.mkdir(parents=True)
    (output / 'logs').mkdir()
    work = output.parent / (output.name + '-work')
    if work.exists():
        shutil.rmtree(work)
    (work / 'profiles').mkdir(parents=True)

    template = work / 'template'
    template.mkdir()
    seeded = subprocess_run([str(args.seed.resolve()), str(template / 'library.sqlite')])
    if seeded != 0:
        raise SystemExit('public-SDK seed program failed with %d' % seeded)

    runs = []
    for index in range(args.runs):
        profile = work / 'profiles' / ('txt-%02d' % index)
        perf.fresh_profile(template, profile)
        fixture = original_fixture(work, index)
        expected_title = 'Perf Import %04d' % index
        facts = {'fixture': fixture, 'expected_title': expected_title,
                 'expectation': {'import_succeeds': True, 'visible_after_import': True,
                                 'title': expected_title, 'source_bytes': fixture['bytes'],
                                 'source_sha256': fixture['sha256'],
                                 'visible_probe': 'real search box query for the expected title'}}
        host = perf.Host(exe, font, profile, output / 'logs' / ('txt-%02d.log' % index))
        try:
            facts['first_screen'] = perf.op_first_screen(host)
            facts['import'] = import_original(host, fixture, ORIGINAL['import_wait_s'])
            facts['probes'] = {}
            for needle in probe_needles(index):
                facts['probes'][needle] = query(host, needle, ORIGINAL['search_wait_s'])
            facts['shelf_after_clear'] = (query(host, '', ORIGINAL['search_wait_s']) or {}).get('first_rows')
            observed = None
            observed_row = None
            for needle, result in facts['probes'].items():
                if result['count'] == 1 and result['first_rows']:
                    observed_row = result['first_rows'][0]
                    observed = row_title(observed_row)
                    break
            facts['observed_row'] = observed_row
            facts['observed_title'] = observed
            facts['open'] = open_observed(host, observed, ORIGINAL['open_wait_s'])
            facts['peak'] = host.close()
        except Exception as error:
            facts['error'] = '%s: %s' % (type(error).__name__, error)
            try:
                facts['peak'] = host.close()
            except Exception:
                pass
        facts['catalog'] = catalog_facts(profile, fixture)
        run = {'run': index, 'facts': facts, 'expected_title': expected_title}
        run['verdict'] = classify(run)
        runs.append(run)
        print(json.dumps({'run': index, 'verdict': run['verdict'],
                          'import': facts['import'], 'catalog': facts['catalog'].get('row'),
                          'probes': {k: v['count'] for k, v in facts['probes'].items()},
                          'open': facts['open'].get('opened')}, ensure_ascii=False), flush=True)

    # One extra launch bisects the same line-oriented shape to name the boundary
    # the SDK enforces, so the hand-off carries a threshold and not just a status.
    bisect_profile = work / 'profiles' / 'bisect'
    perf.fresh_profile(template, bisect_profile)
    bisect = {'profile': str(bisect_profile)}
    host = perf.Host(exe, font, bisect_profile, output / 'logs' / 'bisect.log')
    try:
        bisect['first_screen'] = perf.op_first_screen(host)
        bisect['imports'] = bisect_imports(host, work, ORIGINAL['import_wait_s'])
        bisect['peak'] = host.close()
    except Exception as error:
        bisect['error'] = '%s: %s' % (type(error).__name__, error)
        try:
            bisect['peak'] = host.close()
        except Exception:
            pass
    for entry in bisect.get('imports', []):
        entry['catalog'] = catalog_facts(bisect_profile, entry)
    accepted = [entry for entry in bisect.get('imports', [])
                if not entry.get('status_indicates_failure')]
    rejected = [entry for entry in bisect.get('imports', [])
                if entry.get('status_indicates_failure')]
    bisect['largest_accepted_mib'] = max((entry['declared_mib'] for entry in accepted), default=None)
    bisect['smallest_rejected_mib'] = min((entry['declared_mib'] for entry in rejected), default=None)

    verdicts = [run['verdict'] for run in runs]
    overall = verdicts[0] if len(set(verdicts)) == 1 else 'mixed'
    observed_titles = [((run['facts'].get('catalog') or {}).get('row') or {}).get('title')
                       for run in runs]
    diagnosis = {
        'schema': 1,
        'input': {'kind': 'original 16 MiB single-document TXT', 'parameters': ORIGINAL,
                  'fixture_sha256': runs[0]['facts']['fixture']['sha256'] if runs else None,
                  'fixture_bytes': runs[0]['facts']['fixture']['bytes'] if runs else None},
        'expected_title': runs[0]['expected_title'] if runs else None,
        'verdict': overall,
        'verdicts': verdicts,
        'observed_titles': observed_titles,
        'runs': runs,
        'bisect': bisect,
        'notes': [
            'The filtered list is one observation, never the only one: the product catalog row and '
            'the public open path are recorded separately.',
            'A rejection is reported as a rejection; no wait budget was relaxed and no expected '
            'rejection was introduced.',
        ],
    }
    (output / 'diagnosis.json').write_text(json.dumps(diagnosis, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'verdict': overall, 'verdicts': verdicts,
                      'observed_titles': observed_titles,
                      'fixture': diagnosis['input']}, ensure_ascii=False))
    return 0


def subprocess_run(command):
    import subprocess
    return subprocess.run(command, capture_output=True).returncode


if __name__ == '__main__':
    sys.exit(main())
