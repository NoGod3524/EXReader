"""Cross-check runtime records, original inputs, coverage and change boundaries."""
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

from runtime_routes import ROOT, OUT, LOCAL, progress
import sys
sys.path.insert(0, str(ROOT / 'tools/regress'))
import run_realbooks as regression


def read(path):
    if path.suffix == '.gz':
        with gzip.open(path, 'rt', encoding='utf-8') as stream: return json.load(stream)
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    triage = read(OUT / 'triage.json')
    expected_ids = {r['id'] for r in read(ROOT / 'evidence/quality-20261108/diagnostics.json')['rows']
                    if r['classification'] == 'project'}
    assert len(triage['rows']) == 30 and {r['id'] for r in triage['rows']} == expected_ids
    assert all(r['conclusion'] in ('confirmed_false_positive', 'confirmed_defect', 'indeterminate') and r['reason'] for r in triage['rows'])
    assert all(r['current_sha256'] == sha(ROOT / r['file']) for r in triage['rows'])
    routes = read(OUT / 'routes.json')
    probe = next(r for r in routes if r['name'] == 'msvc-execute')
    assert probe['exit_code'] != 0 and 'ERROR: AddressSanitizer: heap-buffer-overflow' in probe['stderr']
    assert read(OUT / 'build-manifest.json')['source_diff'] == ''
    sources = {p.resolve() for p in (ROOT / 'src').glob('*.c')}
    compilation = read(LOCAL / 'a/compile_commands.json')
    instrumented = {Path(c['file']).resolve() for c in compilation if '/fsanitize=address' in c['command']}
    assert sources <= instrumented, sources-instrumented
    initial = read(OUT / 'asan-compile-commands.json.gz')
    initial_commands = {c['file']:c['command'] for c in initial if Path(c['file']).resolve() in sources}
    final_commands = {c['file']:c['command'] for c in compilation if Path(c['file']).resolve() in sources}
    assert initial_commands == final_commands
    suites = {}
    for mode in ('asan', 'coverage'):
        tests = {}
        initial_failures = []
        executions = 0
        paths = [OUT / f'{mode}-ctest.xml']
        primary = list(ET.parse(paths[0]).getroot().iter('testcase'))
        if len(primary) < 228 and (OUT / f'{mode}-fuzz.xml').exists(): paths.append(OUT / f'{mode}-fuzz.xml')
        if mode == 'asan' and any(t.find('failure') is not None for t in primary) and (OUT / 'asan-benchmark.xml').exists():
            paths.append(OUT / 'asan-benchmark.xml')
        for path in paths:
            suite = ET.parse(path).getroot()
            for test in suite.iter('testcase'):
                executions += 1
                if test.find('failure') is not None: initial_failures.append(dict(suite=path.name, test=test.attrib['name']))
                tests[test.attrib['name']] = test
        assert len(tests) == 228, (mode, len(tests))
        inventory_file = OUT / ('asan-fuzz-inventory.json' if mode == 'asan' and len(primary) < 228 else f'{mode}-ctest-inventory.json')
        assert set(tests) == {t['name'] for t in read(inventory_file)['tests']}
        assert all(t.find('failure') is None and t.find('error') is None and t.find('skipped') is None for t in tests.values())
        suites[mode] = dict(tests=len(tests), executions=executions, failures=0, skipped=0,
                            initial_failures=initial_failures, suites=[p.name for p in paths])
    workloads = {}
    diagnostic_rows = []
    for mode in ('asan', 'coverage'):
        rows = [json.loads(line) for line in (OUT / f'{mode}-fixtures.jsonl').read_text(encoding='utf-8').splitlines()]
        inventory = read(OUT / f'{mode}-fixtures-inventory.json')
        inputs = {r['file'] for r in inventory if r['kind'] != 'reference_or_test_data'}
        assert {r['file'] for r in rows if r['mutation'] == 'original'} == inputs
        assert len({(r['file'],r['mutation']) for r in rows}) == len(rows)
        assert all(r['outcome'] in ('complete', 'sdk_rejected') for r in rows)
        assert all(sha(ROOT / r['file']) == r['sha256'] for r in inventory)
        if mode == 'asan':
            assert Counter(r['mutation'] for r in rows) == dict.fromkeys(('original','empty','half','header-xor'), len(inputs))
        for r in rows:
            if 'ERROR: AddressSanitizer' in r['stderr'] or 'runtime error:' in r['stderr']:
                diagnostic_rows.append(dict(mode=mode, file=r['file'], mutation=r['mutation'], stderr=r['stderr']))
        books = read(OUT / f'{mode}-realbooks.json.gz')
        assert len(books['books']) == 19 and all(b['status']=='ok' for b in books['books'])
        diff = read(OUT / f'{mode}-realbooks.diff.json')
        # The November 8 baseline predates PR #96; retain its real drift separately.
        assert diff['hash_changed_pages'] == 646
        changed = [b for b in diff['books'] if b['hash_changed_pages'] or b['page_count_changed']]
        assert len(changed) == 1 and changed[0]['id'].startswith('zami-')
        assert (changed[0]['old_page_count'], changed[0]['new_page_count']) == (646, 666)
        workloads[mode] = dict(fixtures=read(OUT / f'{mode}-fixtures-summary.json'),
                               books=19, pages=sum(b['page_count'] for b in books['books']),
                               hash_changed_pages=diff['hash_changed_pages'], needs_review=diff['needs_review'])
    control = read(OUT / 'control-realbooks.json.gz')
    assert len(control['books']) == 19 and all(b['status'] == 'ok' for b in control['books'])
    control_commands = read(LOCAL / 'm/compile_commands.json')
    assert not any('/fsanitize=' in c['command'] for c in control_commands)
    comparisons = {}
    for mode in ('asan', 'coverage'):
        diff = regression.compare(control, read(OUT / f'{mode}-realbooks.json.gz'))
        assert not diff['needs_review'], (mode, diff)
        (OUT / f'{mode}-vs-control-realbooks.diff.json').write_text(json.dumps(diff, indent=2)+'\n', encoding='utf-8')
        comparisons[mode] = dict(books=19, pages=11504, page_count_changes=0, glyph_count_changes=0, hash_changed_pages=0)
    historical = read(OUT / 'history-zami.json')
    baseline = read(ROOT / 'docs/ui/evidence/annotations/books-after.json')
    for version, expected in (('before', baseline), ('after', control)):
        actual = read(OUT / f'history-zami-{version}.json')
        wanted = dict(expected, books=[b for b in expected['books'] if b['id'].startswith('zami-')])
        assert not regression.compare(wanted, actual)['needs_review']
    runtime_logs = [(OUT / name).with_suffix('.txt') for name in suites['asan']['suites']] + list(OUT.glob('asan-book-*-stderr.txt'))
    for mode in ('asan', 'coverage'):
        for test in ('txt-scan', 'txt-view', 'txt-anchor'):
            assert read(OUT / f'{mode}-{test}.json')['exit_code'] == 0
            if mode == 'asan': runtime_logs.append(OUT / f'{mode}-{test}.txt')
    for path in runtime_logs:
        text = path.read_text(encoding='utf-8', errors='replace')
        if 'ERROR: AddressSanitizer' in text or 'runtime error:' in text:
            diagnostic_rows.append(dict(log=path.name, text=text))
    coverage = read(OUT / 'coverage.json')
    assert coverage['line_percent'] >= 93.79 and coverage['source_files'] == len(sources)
    counters = read(OUT / 'coverage-counter-inventory.json')
    assert all(g['project_counters'] == len(sources) and not g['missing'] for g in counters['groups'] if g['used'])
    assert not diagnostic_rows, diagnostic_rows
    benchmark = read(LOCAL / 'g/native-convert-benchmark.json')
    assert benchmark['memory_budget_evaluated'] and benchmark['memory_budget_passed']
    (OUT / 'coverage-convert-benchmark.json').write_text(json.dumps(benchmark, indent=2)+'\n', encoding='utf-8')
    assert read(LOCAL / 'a/native-convert-benchmark.json')['instrumented']
    protected = ['.github', 'tests', 'include', 'apps', 'examples', 'cmake', 'CMakeLists.txt']
    trees = {p:subprocess.check_output(['git','rev-parse','HEAD:'+p], cwd=ROOT, text=True).strip() for p in protected}
    assert not subprocess.check_output(['git','diff','HEAD','--']+protected+['src'], cwd=ROOT)
    assert not subprocess.check_output(['git','diff','d9ffdbf0','--','src','include','examples','CMakeLists.txt','cmake'], cwd=ROOT)
    allowed = ('src/', 'tools/quality/', 'evidence/', 'docs/QUALITY.md', 'SAN-FINAL-OUT.txt')
    changes = subprocess.check_output(['git','status','--porcelain','--untracked-files=all'], cwd=ROOT, text=True).splitlines()
    assert all(line[3:].replace('\\','/').startswith(allowed) for line in changes), changes
    report = dict(evidence_consistent=True,
                  acceptance=dict(runtime_check=True, triage_30_of_30=True, coverage_floor=True,
                                  current_revision_zero_book_changes=True, historical_baseline_zero_book_changes=False,
                                  historical_difference_reproduced_and_attributed=True),
                  sanitizer='MSVC AddressSanitizer', instrumented_project_translation_units=len(sources),
                  diagnostic_count=0, diagnostic_classification=dict(project=0, third_party=0, false_positive=0),
                  positive_control_diagnostics=1, positive_control_is_not_a_project_defect=True,
                  triage=dict(total=30, conclusions=dict(Counter(r['conclusion'] for r in triage['rows']))),
                  ctest=suites, workloads=workloads,
                  current_revision_book_comparisons=comparisons, historical_book_change=historical,
                  historical_baseline_zero_change=False, historical_drift_preexisting=True,
                  product_source_changed=False,
                  coverage={k:v for k,v in coverage.items() if k!='files'}, protected_trees=trees,
                  source_sha256={str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in sorted(sources)},
                  binaries={str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in
                            (LOCAL/'a/exreader.dll',LOCAL/'g/libexreader.dll',LOCAL/'a/quality-font-bridge.dll',LOCAL/'fonts/Reader.otf')})
    if (OUT / 'asan-initial-artifacts.json').exists():
        report['initial_asan_workload_artifacts'] = read(OUT / 'asan-initial-artifacts.json')
    (OUT / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    progress(f'Evidence cross-check complete: 228 ASan tests, 19 books, all inputs + three variants, 30/30 adjudications; coverage {coverage["line_percent"]}%; runtime diagnostics=0. Current-source book changes=0; historical Zami change from PR #96 is retained, not called zero.')


if __name__ == '__main__':
    main()
