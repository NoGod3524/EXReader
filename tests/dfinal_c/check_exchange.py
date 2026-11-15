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


def malformed_phase(checks, probe, work, keys, pdf):
    # Start with old annotations already committed by raw_phase, rather than an
    # empty receiver, so rejection also proves that existing user data survives.
    receiver = work / 'recv-pdf.sqlite'
    before = checks.dump(receiver)
    data = (work / 'out/pdf.jsonl').read_bytes()
    lines = data.splitlines(keepends=True)
    cases = {
        'empty-file': b'',
        'missing-final-LF': data[:-1],
        'incomplete-footer': data.replace(b'"complete":true', b'"complete":false'),
        'duplicate-header-key': data.replace(b'"type":"header"', b'"type":"header","type":"header"', 1),
        'duplicate-annotation': b''.join(lines[:2] + [lines[1]] + lines[2:]),
        'invalid-UTF8': data.replace(b'actual PDF', b'actual \xffPDF', 1),
        'raw-NUL': data.replace(b'actual PDF', b'actual \x00PDF', 1),
        'escaped-NUL': data.replace(b'actual PDF', b'actual \\u0000PDF', 1),
        'unpaired-surrogate': data.replace(b'actual PDF', b'actual \\ud800PDF', 1),
        'Markdown-as-JSONL': (work / 'out/pdf.md').read_bytes(),
    }
    for name, payload in cases.items():
        path = work / 'negative' / (name + '.jsonl')
        path.write_bytes(payload)
        for mode in ('preview', 'commit'):
            rejected = checks.probe(probe, 'raw-import', 'raw', receiver, keys['pdf'], path,
                                    mode, 'required', checks.sha(path), 0, 0, pdf,
                                    label=name + '-' + mode)
            checks.expect(rejected.status == checks.AI_FORMAT and
                          rejected.stats['validated'] == 0 and rejected.stats['committed'] == 0 and
                          rejected.stats['fingerprint'] == '' and checks.dump(receiver) == before,
                          f'malformed {name}: {mode} rejects with no confirmed digest or old-data changes', rejected.text)
    title = work / 'unicode-title.jsonl'
    title.write_bytes(data.replace(b'actual PDF', '中文标题 📚'.encode('utf-8'), 1))
    preview = checks.probe(probe, 'raw-import', 'raw', receiver, keys['pdf'], title,
                           'preview', 'required', 0, 0, 0, pdf, label='unicode-title-preview')
    checks.expect(preview.status == checks.AI_OK and preview.stats['fingerprint'] == checks.sha(title) and
                  checks.dump(receiver) == before, 'valid CJK and supplementary Unicode title previews without writes', preview.text)


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
        malformed_phase(checks, args.probe.resolve(), checks.OUT / 'raw', keys, pdf)
        result.update(passed=True, exported_sha256=hashes)
    finally:
        result.update(checks=checks.CHECKS, failed=checks.FAILED, count=len(checks.CHECKS))
        (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        print(f"DFINAL-C annotation model: {len(checks.CHECKS)} checks, passed={result['passed']}")


if __name__ == '__main__':
    main()
