#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Real-process classification checks, including optional independent PDF checks."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).absolute().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from check_corpus import digest
from check_pdf_reference import valid_reference
from triage_corpus import category, limit_kind


def check(binary, fixtures, output):
    font = fixtures/'fonts/primary.ttf'
    bad = output/'invalid.epub'
    bad.write_bytes(b'not a publication')
    manifest = output/'manifest.json'
    manifest.write_text(json.dumps([{'path': bad.name, 'sha256': digest(bad),
        'expected': {'status': 0, 'complete': True}}]), encoding='utf-8')

    def run(script, args, name, expected):
        with (output/(name+'.stdout')).open('wb') as stdout, (output/(name+'.stderr')).open('wb') as stderr:
            p = subprocess.run([sys.executable, str(ROOT/script), *map(str, args)],
                               stdout=stdout, stderr=stderr, timeout=60)
        assert p.returncode == expected, name

    baseline = output/'baseline'
    run('tools/check_corpus.py', [binary, font, manifest, baseline], 'baseline', 1)
    summary = baseline/'summary.json'
    args = [summary, binary, font, output/'classification', '--root', output]
    run('tools/triage_corpus.py', args, 'triage', 0)
    report = json.loads((output/'classification/classification.json').read_text())
    assert not report['accepted'] and not report['baseline_accepted'] and report['baseline_unchanged']
    assert report['counts'] == {'requires_review': 1} and report['replayed'] == 1
    assert category(5, {'complete': True, 'repaired': False}) == 'reference_completed_primary_rejected'
    assert category(5, {'complete': True, 'repaired': True}) == 'reference_repaired_input'
    assert category(5, {'complete': False, 'password_required': True}) == 'reference_requires_password'
    assert category(6, None) == 'resource_limit' and category(11, None) == 'unsupported_feature'
    assert limit_kind('Unbreakable content exceeds page height') == 'unbreakable_page_height'
    assert limit_kind('Table layout limit exceeded') == 'table_layout_budget'
    assert limit_kind('unknown limit') == 'other_budget'
    assert limit_kind('Decoded image cache exceeds 64 MiB') == 'decoded_image_cache'

    # A retained result hash alone must not authorize changed diagnostic logs.
    attachment = baseline/'00000/stderr.log'
    saved = attachment.read_bytes()
    attachment.write_bytes(saved+b'changed')
    args[3] = output/'attachment-changed'
    run('tools/triage_corpus.py', args, 'attachment-changed', 1)
    assert not (args[3]/'classification.json').exists()

    good = output/'valid.txt'
    good.write_text('A complete document.', encoding='utf-8')
    manifest.write_text(json.dumps([{'path': good.name, 'sha256': digest(good),
        'expected': {'status': 0, 'complete': True}}]), encoding='utf-8')
    run('tools/check_corpus.py', [binary, font, manifest, output/'good-baseline'], 'good-baseline', 0)
    args[0], args[3] = output/'good-baseline/summary.json', output/'good-classification'
    run('tools/triage_corpus.py', args, 'good-triage', 0)
    good_report = json.loads((args[3]/'classification.json').read_text())
    assert good_report['baseline_accepted'] and not good_report['accepted'] and not good_report['replayed']
    assert good_report['counts'] == {'baseline_completed': 1} and good_report['source_tools_unchanged']
    # A completion record with an inconsistent process exit cannot count as completed.
    operational = output/'operational'
    operational.mkdir()
    original = json.loads((output/'good-baseline/00000/result.json').read_text())
    for name in original['evidence']:
        shutil.copyfile(output/'good-baseline/00000'/name, operational/name)
    original['classification'], original['exit_code'] = 'process_failure', 1
    result_path = operational/'result.json'
    result_path.write_text(json.dumps(original), encoding='utf-8')
    synthetic = json.loads((output/'good-baseline/summary.json').read_text())
    synthetic['accepted'] = False
    synthetic['results'] = [{'result': str(result_path), 'sha256': digest(result_path)}]
    synthetic_path = operational/'summary.json'
    synthetic_path.write_text(json.dumps(synthetic), encoding='utf-8')
    args[0], args[3] = synthetic_path, output/'operational-triage'
    run('tools/triage_corpus.py', args, 'operational-triage', 0)
    diagnostic = json.loads((args[3]/'classification.json').read_text())
    assert diagnostic['counts'] == {'baseline_failure_not_reproduced': 1} and diagnostic['replayed'] == 1
    assert diagnostic['results'][0]['baseline_classification'] == 'process_failure' and not diagnostic['accepted']
    attachment.write_bytes(saved)
    bad.write_bytes(b'changed input')
    args[0], args[3] = summary, output/'input-changed'
    run('tools/triage_corpus.py', args, 'input-changed', 1)
    assert not (args[3]/'classification.json').exists()

    reference_checked = False
    if importlib.util.find_spec('pymupdf'):
        import pymupdf
        with pymupdf.open() as document:
            document.new_page().insert_text((40, 40), 'Independent reference check')
            good = document.tobytes()
            protected = document.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256,
                                         owner_pw='local-check-owner', user_pw='local-check-user')
        cases = [('valid', good, True, False, False),
                 ('repair', good[:good.rindex(b'startxref')], True, True, False),
                 ('rejected', b'not a document', False, False, False),
                 ('password', protected, False, False, True)]
        for name, content, complete, repaired, password in cases:
            path = output/(name+'.pdf')
            path.write_bytes(content)
            run('tools/check_pdf_reference.py', [path], name, 0 if complete else 1)
            result = json.loads((output/(name+'.stdout')).read_text(encoding='utf-8'))
            assert valid_reference(result), name
            assert (result['complete'], result['repaired'], result['password_required']) == (complete, repaired, password), name
            if complete:
                result['pages'] += 1
                assert not valid_reference(result)
        reference_checked = True
    (output/'checks.json').write_text(json.dumps({'passed': True, 'reference_checked': reference_checked,
        'scope': 'classification integrity and isolated reference behavior; no corpus acceptance'}, indent=2)+'\n')
    print('Corpus classification checks passed; independent PDF reference '+('checked' if reference_checked else 'unavailable'))


if __name__ == '__main__':
    binary, fixtures = (Path(p).absolute() for p in sys.argv[1:3])
    if len(sys.argv) == 4:
        output = Path(sys.argv[3]).absolute()
        output.mkdir()  # Preserve any previous evidence.
        check(binary, fixtures, output)
    else:
        with tempfile.TemporaryDirectory(prefix='exr-triage-') as directory:
            check(binary, fixtures, Path(directory))
