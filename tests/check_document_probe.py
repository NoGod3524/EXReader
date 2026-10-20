#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check complete traversal, caps and evidence rejection using real SDK calls."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).absolute().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from check_corpus import digest, valid_report
from run_benchmarks import make_epub


def main():
    binary, fixtures = (Path(p).absolute() for p in sys.argv[1:])
    font = fixtures/'fonts/primary.ttf'
    with tempfile.TemporaryDirectory(prefix='exreader-complete-') as directory:
        root = Path(directory)
        book = root/'整本.epub'
        make_epub(book, 3, 16384)

        def probe(path, limit=0):
            p = subprocess.run([str(binary), str(path), str(font), str(limit)],
                               capture_output=True, timeout=30)
            report = json.loads(p.stdout)
            assert valid_report(report)
            return p.returncode, report

        code, full = probe(book)
        assert code == 0 and full['complete'] and full['completed_parts'] == full['parts'] == 3
        assert full['pages'] > 3 and full['text_bytes'] >= 3*16384
        code, limited = probe(book, 1)
        assert code == 1 and limited['status'] == 0 and not limited['complete'] and limited['pages'] == 1
        code, exact = probe(book, full['pages'])
        assert code == 0 and exact == full
        pdf = root/'sample.PdF'
        shutil.copyfile(fixtures/'pdf-color/shading-axial.pdf', pdf)
        code, fixed = probe(pdf)
        assert code == 0 and fixed['complete'] and fixed['pages'] == 1
        for name in ('sample.txt', 'comic.cbz'):
            code, report = probe(fixtures/name)
            assert code == 0 and report['complete'] and report['pages'] > 0
        bad = root/'bad.epub'
        bad.write_bytes(b'not a publication')
        code, rejected = probe(bad)
        assert code == 1 and rejected['status'] and not rejected['complete']
        for limit in ('-1', '+1', ' 1', '1x', '18446744073709551616'):
            p = subprocess.run([str(binary), str(book), str(font), limit], capture_output=True, timeout=30)
            assert p.returncode == 2 and not p.stdout
        manifest = root/'manifest.json'
        records = [{'path': p.name, 'sha256': digest(p), 'expected': {'status': 0, 'complete': True}}
                   for p in (book, pdf)]

        def corpus(name, expected, *options):
            p = subprocess.run([sys.executable, str(ROOT/'tools/check_corpus.py'), str(binary), str(font),
                                str(manifest), str(root/name), *options], capture_output=True, timeout=60)
            assert p.returncode == (0 if expected else 1), name
            summary = json.loads((root/name/'summary.json').read_text(encoding='utf-8'))
            assert summary['accepted'] is expected
            assert all(digest(Path(r['result'])) == r['sha256'] for r in summary['results'])
            return summary

        manifest.write_text(json.dumps(records), encoding='utf-8')
        assert corpus('full', True)['counts'] == {'passed': 2}
        assert corpus('parallel', True, '--workers', '2')['counts'] == {'passed': 2}
        manifest.write_text(json.dumps({'files': records, 'complete': False, 'target': 500}), encoding='utf-8')
        assert corpus('collection-incomplete', False)['completed_documents'] == 2
        manifest.write_text(json.dumps({'files': records, 'complete': True, 'target': 500}), encoding='utf-8')
        corpus('collection-count-mismatch', False)
        manifest.write_text(json.dumps(records), encoding='utf-8')
        assert 'incomplete' in corpus('cap', False, '--max-pages', '1')['counts']
        corpus('subset', False, '--max-files', '1')
        records[0]['sha256'] = '0'*64
        manifest.write_text(json.dumps(records), encoding='utf-8')
        assert corpus('hash', False)['counts']['invalid_input'] == 1
        records[0]['sha256'] = digest(book)
        del records[0]['expected']
        manifest.write_text(json.dumps(records), encoding='utf-8')
        assert corpus('unknown', False)['counts']['untriaged'] == 1
        records[0] = {'path': bad.name, 'sha256': digest(bad),
                      'expected': {'status': 0, 'complete': True}}
        manifest.write_text(json.dumps(records), encoding='utf-8')
        assert corpus('unexpected', False)['counts']['unexpected_outcome'] == 1
        records[0]['expected'] = {'status': rejected['status'], 'complete': False}
        manifest.write_text(json.dumps(records), encoding='utf-8')
        assert corpus('reason-required', False)['counts']['invalid_expectation'] == 1
        records[0]['expectation_reason'] = 'Deliberately invalid test document'
        manifest.write_text(json.dumps(records), encoding='utf-8')
        assert corpus('known-rejection', True)['counts']['expected_rejection'] == 1
        records.append(records[1])
        manifest.write_text(json.dumps(records), encoding='utf-8')
        assert corpus('duplicate', False, '--workers', '2')['counts']['invalid_input'] == 1
    print('Complete-document probe and corpus evidence checks passed')


if __name__ == '__main__':
    main()
