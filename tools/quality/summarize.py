"""Summarize retained GCC diagnostics; triage is evidence, never a suppression."""
from collections import Counter
import argparse
import gzip
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from analyze import ROOT, progress, write_json

OUT = ROOT / 'evidence/quality-20261108'

# These reviews apply only to the recorded source revision and reported paths.
REVIEWS = {
    ('construct.c', 198): (
        'The trace skips the resource initialization loop and takes count<=1 in unique(), '
        'then enters the i=1; i<resource_count loop. This contradicts the same count. '
        'For count>1, sorted allocation is checked and every element is assigned at line 178.'),
    ('chapter_window.c', 534): (
        'The trace takes allocate() budget failure (line 74), which sets p->failed=EXR_LIMIT '
        'via fail()/exr_fail(), then assumes status=p->failed is zero at line 533. '
        'src/common.c exr_fail returns its supplied nonzero code.'),
    ('toc_page.c', 179): (
        'The trace labels realloc as successful and moving the buffer at line 178, '
        'then takes next==NULL and claims the newly allocated next leaks. A successful '
        'nonzero allocation cannot also be NULL; the zero-size case does not leak a new allocation.'),
}


def measurements():
    records = [json.loads(line) for line in (OUT / 'fixtures.jsonl').read_text(encoding='utf-8').splitlines()]
    merged = {r['file']: r for r in records}
    extras = json.loads((OUT / 'fixtures-extra.json').read_text(encoding='utf-8'))
    for extra in extras:
        merged[extra['file']] = merged[extra['file']] | extra
    records = list(merged.values())
    with gzip.open(OUT / 'realbooks.json.gz', 'rt', encoding='utf-8') as stream:
        books = json.load(stream)
    suite = ET.parse(OUT / 'ctest.xml').getroot()
    runtime_lines = []
    for name in ('ctest.txt', 'realbooks-console.txt', 'fixtures.jsonl', 'fixtures-extra-console.txt'):
        for number, line in enumerate((OUT / name).read_text(encoding='utf-8').splitlines(), 1):
            if 'runtime error:' in line:
                runtime_lines.append(dict(log=name, line=number, text=line))
    summary = dict(
        route='C', runtime_sanitizer_executed=False, runtime_sanitizer_diagnostic_count=None,
        ordinary_test_output_runtime_error_lines=runtime_lines,
        ctest=dict(tests=len(list(suite.iter('testcase'))), failures=len(list(suite.iter('failure'))),
                   errors=len(list(suite.iter('error'))), skipped=len(list(suite.iter('skipped')))),
        realbooks=dict(books=len(books['books']), pages=sum(b['page_count'] for b in books['books']),
                       glyphs=sum(b['glyph_count'] for b in books['books']),
                       content_fingerprint=books['content_fingerprint'],
                       elapsed_seconds=books['elapsed_seconds']),
        fixtures=dict(total_files=len(records), executed_inputs=sum(r['kind'] != 'reference_or_test_data' for r in records),
                      kinds=dict(Counter(r['kind'] for r in records)),
                      outcomes=dict(Counter(r['outcome'] for r in records)),
                      rendered_pages=sum(r.get('probe', {}).get('pages', 0) for r in records)),
        coverage=json.loads((OUT / 'coverage.json').read_text(encoding='utf-8')))
    summary['coverage'].pop('files')
    write_json(OUT / 'measurements.json', summary)
    progress(OUT, f'Measurement accounting finalized: {summary["ctest"]}; {summary["fixtures"]}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--complete', action='store_true')
    args = parser.parse_args()
    with gzip.open(OUT / 'analyzer-results.json.gz', 'rt', encoding='utf-8') as stream:
        units = json.load(stream)
    rows = []
    for unit in units:
        for index, diagnostic in enumerate(unit['diagnostics']):
            physical = diagnostic['locations'][0]['physicalLocation']
            path = Path(physical['artifactLocation']['uri'])
            line = physical['region']['startLine']
            reason = REVIEWS.get((path.name, line)) if unit['group'] == 'project' else None
            group = 'suspected_false_positive' if reason else 'project' if unit['group'] == 'project' else 'third_party'
            stack = []
            for flow in diagnostic.get('codeFlows', []):
                for thread in flow['threadFlows']:
                    for event in thread['locations']:
                        for location in event['location'].get('logicalLocations', []):
                            name = location.get('fullyQualifiedName')
                            if name and name not in stack:
                                stack.append(name)
            rows.append(dict(id=f'{unit["id"]:03}:{index}', classification=group,
                             origin=unit['group'], category=diagnostic['ruleId'],
                             file=path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path),
                             line=line, message=diagnostic['message']['text'],
                             suspected_false_positive_reason=reason,
                             trigger=f'GCC -fanalyzer translation unit: {unit["file"]}',
                             runtime_test_case=None, static_path_functions=stack,
                             evidence=f'analyzer-{unit["id"]:03}.json.gz', sarif_result_index=index))
    summary = dict(kind='static analysis, not runtime checking',
                   counting='emitted SARIF warning records, including distinct paths at the same location',
                   translation_units=dict(Counter(u['group'] for u in units)),
                   total=len(rows), by_classification=dict(Counter(r['classification'] for r in rows)),
                   by_warning=dict(Counter(r['category'] for r in rows)),
                   by_origin=dict(Counter(r['origin'] for r in rows)),
                   unique_locations=len({(r['file'], r['line']) for r in rows}),
                   rows=rows)
    write_json(OUT / 'diagnostics.json', summary)
    build_warnings = []
    reasons = {
        'cbz.c': 'Frame count is capped at 4096; # plus its decimal index and NUL fit within the extra 24 bytes.',
        'flac.c': 'Every successful coded_number return writes n; its error helper bad returns zero, which the caller checks.',
    }
    for text in (OUT / 'build-final.txt').read_text(encoding='utf-8').splitlines():
        match = re.match(r'(.+):(\d+):(\d+): warning: (.+) \[(-W[^\]]+)\]$', text)
        if match:
            path = Path(match[1])
            reason = reasons.get(path.name)
            build_warnings.append(dict(file=path.relative_to(ROOT).as_posix(), line=int(match[2]),
                                       column=int(match[3]), message=match[4], category=match[5],
                                       classification='suspected_false_positive' if reason else 'project',
                                       reason=reason, evidence='build-final.txt'))
    write_json(OUT / 'build-warnings.json', build_warnings)
    progress(OUT, f'Static diagnostic triage completed: {len(rows)} emitted warnings; '
             f'{summary["by_classification"]}. All original paths retained.')
    if args.complete:
        measurements()


if __name__ == '__main__':
    main()
