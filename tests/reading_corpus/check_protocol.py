#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Use actual native consumers; verify missing/failed evidence never passes."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/reading_corpus'))
from run import digest, registered, validate_evidence, validate_report


def evidence_fixture(root):
    identity = {'source_sha': 'a' * 40, 'run_id': '12', 'run_attempt': '3'}
    report = {'scope': 'representative-real-v1-only', 'historical_1710_accepted': False,
              'manifest_entries': 8, 'source_dirty': False, 'identities_unchanged': True,
              'full_probe_accepted': True, 'documents': [], **identity}
    summary = {'accepted': True, 'identities_unchanged': True, 'source_dirty': False,
               'page_limit': 0, 'checked_entries': 8, 'manifest_entries': 8, 'results': [], **identity}
    for index in range(8):
        document = {'id': str(index), 'sha256': str(index) * 64}
        for phase in ('full', 'location'):
            folder = root / phase / f'{index:05d}'; folder.mkdir(parents=True)
            if phase == 'full':
                observed = {'schema': 1, 'engine_version': 'test', 'status': 0, 'stage': 'text',
                            'parts': 1, 'completed_parts': 1, 'pages': 1, 'text_bytes': 1, 'complete': True}
                native = 'stdout.json'; (folder / native).write_text(json.dumps(observed))
                result = {'index': index, 'input': {'id': str(index), 'sha256': document['sha256'],
                          'expected': {'status': 0, 'complete': True}}, 'observed_sha256': document['sha256'],
                          'report': observed}
            else:
                observed = {'schema': 1, 'status': 0, 'complete': True, 'units': 1, 'checked': 1, 'empty': 0}
                native = 'stdout.jsonl'
                (folder / native).write_text(json.dumps({'unit': 0, 'status': 0, 'text_bytes': 1,
                                                        'selector_state': 1}) + '\n' + json.dumps(observed) + '\n')
                result = {'id': str(index), 'input_sha256': document['sha256'], 'observed': observed}
            (folder / 'stderr.log').write_text('')
            result.update(classification='passed', exit_code=0, **identity,
                          evidence={name: digest(folder / name) for name in (native, 'stderr.log')})
            (folder / 'result.json').write_text(json.dumps(result))
            relative = f'{phase}/{index:05d}/result.json'
            document.update({phase + '_classification': 'passed', phase + '_observed': observed,
                             phase + '_result': relative, phase + '_result_sha256': digest(folder / 'result.json')})
            if phase == 'full':
                summary['results'].append({'index': index, 'result': relative, 'classification': 'passed',
                                           'observed': observed, 'sha256': document['full_result_sha256']})
        report['documents'].append(document)
    (root / 'full/summary.json').write_text(json.dumps(summary))
    report['full_summary_sha256'] = digest(root / 'full/summary.json')
    return report


def change_result(root, report, phase, changes):
    path = root / report['documents'][0][phase + '_result']
    value = json.loads(path.read_text()); value.update(changes); path.write_text(json.dumps(value))
    report['documents'][0][phase + '_result_sha256'] = digest(path)
    if phase == 'full':
        path = root / 'full/summary.json'; value = json.loads(path.read_text())
        value['results'][0]['sha256'] = report['documents'][0]['full_result_sha256']
        path.write_text(json.dumps(value)); report['full_summary_sha256'] = digest(path)


def evidence_checks():
    checks = 0
    changes = [lambda r, p: (r / 'full/summary.json').unlink(),
               lambda r, p: p.update(full_summary_sha256='0' * 64)]
    for phase in ('full', 'location'):
        changes += [lambda r, p, h=phase: (r / h / '00000/result.json').unlink(),
                    lambda r, p, h=phase: (r / h / '00000/stderr.log').unlink(),
                    lambda r, p, h=phase: p['documents'][0].update({h + '_result': '../result.json'}),
                    lambda r, p, h=phase: p['documents'][0].update({h + '_result_sha256': '0' * 64}),
                    lambda r, p, h=phase: change_result(r, p, h, {'classification': 'unexpected_outcome'}),
                    lambda r, p, h=phase: change_result(r, p, h, {'exit_code': 1})]
        for key, value in (('source_sha', 'b' * 40), ('run_id', '13'), ('run_attempt', '2')):
            changes.append(lambda r, p, h=phase, k=key, v=value: change_result(r, p, h, {k: v}))
    for change in [None, *changes]:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); report = evidence_fixture(root)
            if change is None:
                assert validate_evidence(report, root); checks += 1
                continue
            change(root, report)
            try:
                validate_evidence(report, root)
            except (OSError, ValueError, KeyError, TypeError, IndexError):
                checks += 1
            else:
                raise AssertionError('Invalid retained evidence was accepted')
    return checks


def main():
    binary, font = (Path(x).resolve() for x in sys.argv[1:])
    checks = 0
    for name in ('sample.epub', 'pdf-public.pdf'):
        # These protocol fixtures are explicitly synthetic and count zero real inputs.
        proc = subprocess.run([str(binary), str(ROOT / 'tests/fixtures' / name), str(font)],
                              capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, proc.stderr
        last = json.loads(proc.stdout.splitlines()[-1])
        assert last['complete'] is True and last['checked'] > 0
        checks += 1
    proc = subprocess.run([str(binary), str(ROOT / 'tests/fixtures/nonexistent.pdf'), str(font)],
                          capture_output=True, text=True, timeout=30)
    assert proc.returncode != 0 and json.loads(proc.stdout.splitlines()[-1])['complete'] is False
    checks += 1
    for anchor in ('0' * 40, 'not-a-sha'):
        try:
            registered(ROOT / 'tools/reading_corpus/real-v1.json', anchor)
        except (ValueError, subprocess.CalledProcessError):
            checks += 1
        else:
            raise AssertionError('A false registration was accepted')
    skeleton = {'scope': 'representative-real-v1-only', 'historical_1710_accepted': False,
                'manifest_entries': 8, 'source_dirty': False, 'identities_unchanged': True,
                'full_probe_accepted': True,
                'documents': [{'full_classification': 'passed', 'location_classification': 'passed'} for _ in range(8)]}
    assert validate_report(skeleton)
    mutations = [('scope', 'historical-full'), ('historical_1710_accepted', True),
                 ('source_dirty', True), ('identities_unchanged', False),
                 ('full_probe_accepted', False), ('manifest_entries', 7), ('documents', [])]
    for key, value in mutations:
        bad = copy.deepcopy(skeleton)
        bad[key] = value
        assert not validate_report(bad)
        checks += 1
    for phase in ('full_classification', 'location_classification'):
        for state in ('timeout', 'unexpected_outcome', 'invalid_report', 'input_changed'):
            bad = copy.deepcopy(skeleton)
            bad['documents'][3][phase] = state
            assert not validate_report(bad)
            checks += 1
    checks += evidence_checks()
    print(json.dumps({'protocol_checks': checks, 'accepted': True, 'real_document_credit': 0}))


if __name__ == '__main__':
    main()
