# SPDX-License-Identifier: MIT
"""Current-source model evidence; never grants iPad UI or physical-device acceptance."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def raw_boundary_phase(checks, probe, pdf, work, keys):
    """Reject hostile file bytes before committing; compare every product table."""
    source = work / 'out/pdf.jsonl'
    original = source.read_bytes()
    database = work / 'recv-file-boundaries.sqlite'
    checks.expect(checks.probe(probe, 'make-store', 'raw', database, work / 'books/pdf.json').exit == 0,
                  'file-boundary receiver seeded')
    before = checks.dump(database)
    files = work / 'file-boundaries'
    files.mkdir()
    cases = {
        'empty': b'',
        'markdown-is-display-only': (work / 'out/pdf.md').read_bytes(),
        'utf8-bom': b'\xef\xbb\xbf' + original,
        'invalid-utf8': original.replace(b'"book_title":"actual PDF"', b'"book_title":"\xff"', 1),
        'raw-nul': original.replace(b'"book_title":"actual PDF"', b'"book_title":"\0"', 1),
        'escaped-nul': original.replace(b'"book_title":"actual PDF"', b'"book_title":"\\u0000"', 1),
        'unpaired-surrogate': original.replace(b'"book_title":"actual PDF"', b'"book_title":"\\ud800"', 1),
        'duplicate-header-key': original.replace(b'"type":"header",', b'"type":"header","type":"header",', 1),
        'integer-overflow': original.replace(b'"source_bytes":8845', b'"source_bytes":18446744073709551616', 1),
        'integer-leading-zero': original.replace(b'"source_bytes":8845', b'"source_bytes":08845', 1),
        'crlf-records': original.replace(b'\n', b'\r\n'),
        'missing-final-lf': original[:-1],
    }
    for name, data in cases.items():
        checks.expect(data != original, 'file-boundary fixture differs: ' + name)
        path = files / (name + '.jsonl')
        path.write_bytes(data)
        # Even a caller supplying the hostile file's own digest cannot bypass validation.
        for mode in ('preview', 'commit'):
            result = checks.probe(probe, 'raw-import', 'raw', database, keys['pdf'], path,
                                  mode, 'verified', checks.sha(path), 0, 0, '-',
                                  label='file-boundary-' + mode + '-' + name)
            checks.expect(result.status == checks.AI_FORMAT and result.stats['validated'] == 0
                          and result.stats['fingerprint'] == '' and result.stats['committed'] == 0
                          and checks.dump(database) == before,
                          mode + ' rejects ' + name + ' without fingerprint or writes', result.text)
    for budget, status in ((len(original) - 1, checks.AI_LIMIT), (len(original), checks.AI_OK)):
        result = checks.probe(probe, 'raw-import', 'raw', database, keys['pdf'], source,
                              'preview', 'required', 0, 0, 0, pdf, budget,
                              label='file-budget-' + str(budget))
        checks.expect(result.status == status and checks.dump(database) == before
                      and (status != checks.AI_OK or result.stats['fingerprint'] == checks.sha(source)),
                      'exact input budget boundary ' + str(budget) + ' preserves the receiver', result.text)
    for mode in ('preview', 'commit'):
        result = checks.probe(probe, 'raw-import', 'raw', database, keys['pdf'], source,
                              mode, 'required', checks.sha(source), 5, 0, pdf,
                              label='resume-beyond-' + mode)
        checks.expect(result.status == checks.AI_FORMAT and result.stats['validated'] == 0
                      and result.stats['fingerprint'] == '' and checks.dump(database) == before,
                      mode + ' rejects resume beyond head count without writes', result.text)
    result = checks.probe(probe, 'raw-import', 'raw', database, keys['pdf'], source,
                          'commit', 'required', checks.sha(source), 4, 0, pdf, label='resume-at-end')
    checks.expect(result.status == checks.AI_OK and result.stats['committed'] == 0
                  and result.stats['next_index'] == 4 and not result.items and checks.dump(database) == before,
                  'resume at exact end is a zero-write completion', result.text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location('c06_checks', ROOT / 'tests/reader_next_c06/run.py')
    checks = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checks)
    # Reuse the independent JSON/wire/database judges, not the historical runner's
    # source-freeze guards or its unrelated old-source/platform acceptance.
    result = {'scope': 'current-source shared raw3 annotation model', 'passed': False,
              'source': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'actions': os.environ.get('GITHUB_ACTIONS') == 'true',
              'host_ui_verified': False, 'physical_device_verified': False}
    try:
        checks.OUT = Path(tempfile.mkdtemp(prefix='exchange-', dir=args.output))
        result['artifacts'] = str(checks.OUT.resolve())
        checks.legacy_phase('off', args.probe.resolve(), checks.OUT / 'legacy-off')
        pdf = ROOT / 'tests/fixtures/pdf-public-text.pdf'
        checks.expect(checks.sha(pdf) == checks.PDF_SHA, 'fixed PDF fixture SHA-256')
        hashes, keys = checks.raw_phase(args.probe.resolve(), args.probe.resolve(), pdf, checks.OUT / 'raw')
        raw_boundary_phase(checks, args.probe.resolve(), pdf, checks.OUT / 'raw', keys)
        result.update(passed=True, exported_sha256=hashes)
    finally:
        result.update(checks=checks.CHECKS, failed=checks.FAILED, count=len(checks.CHECKS))
        (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        print(f"DFINAL-C annotation model: {len(checks.CHECKS)} checks, passed={result['passed']}")


if __name__ == '__main__':
    main()
