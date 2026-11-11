"""Collect reproducible CFI acceptance evidence after a full build/ctest/render.

python tests/collect_cfi_acceptance.py --build build/cfi
Uses the existing local 19-book manifest; no book bytes are copied to evidence.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION = [
    'include/exr/document.h', 'include/exr/layout.h', 'src/cfi.c',
    'src/cfi_syntax.c', 'src/cfi_offset.c', 'src/document_internal.h',
    'src/publication.c', 'tools/layers.json', 'CMakeLists.txt',
    'tests/test_cfi_compat.c', 'tests/cfi-vectors.tsv',
    'tests/collect_cfi_acceptance.py',
]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    args = parser.parse_args()
    build = args.build.resolve()
    evidence = ROOT / 'evidence/cfi-acceptance-20261108'
    evidence.mkdir(exist_ok=True)
    exe = build / 'exreader-cfi-compat-test.exe'
    dll = build / 'libexreader.dll'
    manifest = json.loads((ROOT / 'tools/regress/corpus.json').read_text(encoding='utf-8'))
    book = next(b for b in manifest['books'] if b['id'] == 'hongloumeng-24264')
    outputs = {}
    for group in ('parse', 'invalid', 'mapping', 'roundtrip', 'cross', 'contracts', 'real'):
        command = [str(exe), group]
        if group in ('parse', 'invalid'):
            command.append(str(ROOT / 'tests/cfi-vectors.tsv'))
        if group == 'real':
            command.append(book['path'])
        result = subprocess.run(command, cwd=ROOT, capture_output=True)
        if result.returncode:
            sys.stderr.buffer.write(result.stdout + result.stderr)
            raise RuntimeError(f'{group} failed: {result.returncode}')
        outputs[group] = result.stdout.decode('utf-8').replace('\r\n', '\n')
        (evidence / f'{group}.txt').write_text(outputs[group], encoding='utf-8', newline='\n')
    layer = subprocess.run([sys.executable, 'tools/check_layers.py', str(build)],
                           cwd=ROOT, capture_output=True, check=True)
    (evidence / 'layers.txt').write_text(layer.stdout.decode('utf-8').replace('\r\n', '\n'),
                                       encoding='utf-8', newline='\n')
    before = json.loads((build / 'realbooks-before.json').read_text(encoding='utf-8'))
    after = json.loads((build / 'realbooks-final.json').read_text(encoding='utf-8'))
    diff = json.loads((build / 'realbooks-final.diff.json').read_text(encoding='utf-8'))
    assert before['summary']['successful_books'] == after['summary']['successful_books'] == 19
    assert diff['comparable'] and not diff['needs_review'] and diff['hash_changed_pages'] == 0
    assert after['dll_sha256'] == sha(dll.read_bytes()), 'Render must use the final DLL'
    ctest = (build / 'ctest-final.log').read_text(encoding='utf-8')
    match = re.search(r'100% tests passed(?:, 0 tests failed)? out of (\d+)', ctest)
    assert match, 'Full ctest must pass'
    total = int(match[1])
    assert total >= 211
    for name in ('ctest-final.log', 'realbooks-before.json', 'realbooks-final.json',
                 'realbooks-final.diff.json', 'CMakeCache.txt'):
        (evidence / (name + '.gz')).write_bytes(gzip.compress((build / name).read_bytes(), mtime=0))
    valid = re.search(r'valid vectors: (\d+)/(\d+)', outputs['parse'])
    invalid = re.search(r'invalid vectors: (\d+)/(\d+)', outputs['invalid'])
    assert valid and invalid and valid[1] == valid[2] and invalid[1] == invalid[2]
    assert len(re.findall(r'^sample ', outputs['roundtrip'], re.M)) == 100
    assert len(re.findall(r'^sample ', outputs['cross'], re.M)) == 10
    assert len(re.findall(r'^sample ', outputs['real'], re.M)) == 20
    assert '100/100 = 100%' in outputs['roundtrip'] and '10/10 = 100%' in outputs['cross']
    assert '20/20 = 100%' in outputs['real']
    report = {
        'schema': 1,
        'baseline_revision': before['source_revision'],
        'baseline_dll_sha256': before['dll_sha256'],
        'candidate_dll_sha256': after['dll_sha256'],
        'test_executable_sha256': sha(exe.read_bytes()),
        'grammar_source': 'https://w3c.github.io/epub-specs/epub33/epubcfi/',
        'vector_origin': '13 W3C examples; additional original positive/negative cases',
        'definition': 'Exact equality of both (part, normalized UTF-8 byte offset) endpoints '
                      'and every field of anchors captured by anchor_from_range; any failure counts against denominator',
        'prng_seed': '0x41ce2026',
        'acceptance': {
            'parse': {'passed': int(valid[1]) + int(invalid[1]), 'valid': int(valid[1]),
                      'invalid': int(invalid[1]), 'failed': 0},
            'serialization': {'passed': int(valid[1]), 'failed': 0,
                              'equivalence': 'Exact scheme data, including assertion/parameter order; bare input gains epubcfi(...)'},
            'same_part_ranges': {'passed': 100, 'total': 100, 'percent': 100.0},
            'cross_part_ranges': {'passed': 10, 'total': 10, 'percent': 100.0},
            'real_positions': {'book': book['id'], 'book_sha256': book['sha256'],
                               'passed': 20, 'total': 20, 'percent': 100.0},
            'regression': {'passed_books': 19, 'total_books': 19,
                           'pages': after['summary']['total_pages'],
                           'glyphs': after['summary']['total_glyphs'],
                           'page_count_changes': sum(b['page_count_changed'] for b in diff['books']),
                           'hash_changed_pages': 0},
            'ctest': {'passed': total, 'total': total, 'baseline_total': total-6, 'new_groups': 6},
        },
        'layout': after['layout'],
        'font_sha256': after['font_sha256'],
        'content_fingerprint_before': before['content_fingerprint'],
        'content_fingerprint_after': after['content_fingerprint'],
        'implementation_git_lf_sha256': {p: sha((ROOT / p).read_bytes().replace(b'\r\n', b'\n')) for p in IMPLEMENTATION},
        'artifacts_sha256': {p.name: sha(p.read_bytes()) for p in sorted(evidence.iterdir()) if p.is_file()},
    }
    assert report['acceptance']['regression']['page_count_changes'] == 0
    (ROOT / 'tests/cfi-acceptance-20261108.json').write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(report['acceptance'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

