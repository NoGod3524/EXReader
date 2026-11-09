"""Check the quality run's accounting, hash invariance and source boundary."""
import gzip
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

from analyze import ROOT, analyzer_command, split_command

sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'tools/regress'))
from run_realbooks import compare, file_hash

OUT = ROOT / 'evidence/quality-20261108'


def read(name):
    return json.loads((OUT / name).read_text(encoding='utf-8-sig'))


def main():
    # Exercise argument handling: paths with spaces/backslashes and removal of
    # only coverage/output flags, preserving the project's includes/defines.
    original = ['C:\\Program Files\\gcc.exe', '-Iinclude', '-DTHING=1', '-O1', '--coverage',
                '-fprofile-update=atomic', '-Werror', '-o', 'old.o', '-c', 'src/example.c']
    assert split_command(subprocess.list2cmdline(original)) == original
    command = analyzer_command({'arguments': original}, Path('new.o'))
    assert command[:3] == original[:3] and 'old.o' not in command
    assert '-fanalyzer' in command and '--coverage' not in command and command[-1] == 'new.o'

    diagnostics = read('diagnostics.json')
    with gzip.open(OUT / 'analyzer-results.json.gz', 'rt', encoding='utf-8') as stream:
        units = json.load(stream)
    expected = {p.resolve() for p in (ROOT / 'src').glob('*.c')}
    provenance = read('provenance.json')
    assert all(file_hash(ROOT / name) == digest for name, digest in provenance['project_c_sha256'].items())
    assert {Path(u['file']) for u in units if u['group'] == 'project'} == expected
    assert all(u['exit_code'] == 0 for u in units)
    assert sum(len(u['diagnostics']) for u in units) == len(diagnostics['rows']) == diagnostics['total']
    assert sum(diagnostics['by_classification'].values()) == diagnostics['total']
    for row in diagnostics['rows']:
        assert (OUT / row['evidence']).is_file()
        assert row['classification'] != 'suspected_false_positive' or row['suspected_false_positive_reason']

    coverage = read('coverage.json')
    assert {ROOT / r['file'] for r in coverage['files']} == expected
    assert coverage['lines'] == sum(r['lines'] for r in coverage['files'])
    assert coverage['covered_lines'] == sum(r['covered_lines'] for r in coverage['files']) > 0
    assert coverage['line_percent'] == round(100 * coverage['covered_lines'] / coverage['lines'], 2)
    for row in coverage['files']:
        assert len(row['function_details']) == row['functions']
        assert len(row['covered_line_numbers']) == row['covered_lines'] <= row['lines']

    baseline = json.loads((ROOT / 'docs/ui/evidence/annotations/books-after.json').read_text(encoding='utf-8'))
    with gzip.open(OUT / 'realbooks.json.gz', 'rt', encoding='utf-8') as stream:
        books = json.load(stream)
    assert len(books['books']) == 19 and not compare(baseline, books)['needs_review']
    assert books['dll_sha256'] == file_hash(OUT / 'local/coverage-build/libexreader.dll')
    assert all(len(b['pages']) == b['page_count'] for b in books['books'])

    fixtures = [json.loads(line) for line in (OUT / 'fixtures.jsonl').read_text(encoding='utf-8').splitlines()]
    expected_fixtures = {p.relative_to(ROOT).as_posix() for p in (ROOT / 'tests/fixtures').rglob('*') if p.is_file()}
    assert len(fixtures) == len(expected_fixtures) == read('fixtures-summary.json')['total_files']
    assert {r['file'] for r in fixtures} == expected_fixtures
    assert all(file_hash(ROOT / r['file']) == r['sha256'] for r in fixtures)
    assert not any(r['outcome'] in ('process_failure', 'timeout_60s') for r in fixtures)
    extras = read('fixtures-extra.json')
    assert len(extras) == 10 and {r['file'] for r in extras} <= expected_fixtures
    assert all(file_hash(ROOT / r['file']) == r['sha256'] for r in extras)

    suite = ET.parse(OUT / 'ctest.xml').getroot()
    cases = list(suite.iter('testcase'))
    inventory = read('ctest-inventory.json')['tests']
    assert len(cases) == len(inventory)
    assert {case.attrib['name'] for case in cases} == {test['name'] for test in inventory}
    assert not list(suite.iter('failure')) and not list(suite.iter('error')) and not list(suite.iter('skipped'))
    changed = subprocess.check_output(['git', 'diff', '--name-only', books['source_revision']], cwd=ROOT, text=True).splitlines()
    changed += subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard'], cwd=ROOT, text=True).splitlines()
    assert all(p.startswith(('tools/quality/', 'evidence/quality-20261108/')) or p == 'docs/QUALITY.md' for p in changed), changed
    print(f'PASS: {len(expected)} C sources; {len(cases)} tests; {len(expected_fixtures)} fixture inventory; '
          f'19 books/{sum(b["page_count"] for b in books["books"])} unchanged pages; '
          f'{coverage["line_percent"]}% line coverage; source boundary clean.')


if __name__ == '__main__':
    main()
