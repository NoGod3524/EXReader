#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Use actual native consumers; verify missing/failed evidence never passes."""
import copy
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/reading_corpus'))
from run import registered, validate_report


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
    print(json.dumps({'protocol_checks': checks, 'accepted': True, 'real_document_credit': 0}))


if __name__ == '__main__':
    main()
