# SPDX-License-Identifier: MIT
"""Finite already-queried native UI observations; never a privacy verdict."""
import re
from contract import require

PREFIX = 'EXR_PRIVACY_UI_STATE '
CODES = ('empty', 'idle', 'preparing-original', 'receiving-shelf', 'preparing', 'running',
         'cancelling', 'closing', 'closed', 'finished', 'cancelled', 'failed', 'next-sync',
         'retry-preserves-history', 'other', 'unavailable')
PATTERN = re.compile(r'EXR_PRIVACY_UI_STATE seq=([1-9][0-9]{0,5}) elapsed_ms=([0-9]{1,7}) '
    r'phase=(remembered|session|missing-restart|unknown) snapshot=([01]) '
    r'label=(' + '|'.join(CODES) + r') value=(' + '|'.join(CODES) + r') '
    r'value_kind=(none|string|number|other) missing_label=([01]) missing_value=([01])')


def parse_ui_observations(path):
    records = []
    with path.open('r', encoding='utf-8', errors='replace') as file:
        for line in file:
            if not line.startswith(PREFIX): continue
            match = PATTERN.fullmatch(line.rstrip('\r\n'))
            require(match is not None, 'invalid finite UI observation record')
            sequence, elapsed = int(match[1]), int(match[2])
            require(sequence <= 100000 and elapsed <= 4800000 and len(records) < 5000,
                    'UI observation bounds exceeded')
            require(not records or (sequence > records[-1]['sequence'] and elapsed >= records[-1]['elapsed_ms']),
                    'UI observation order differs')
            records.append({'sequence': sequence, 'elapsed_ms': elapsed, 'phase': match[3],
                'snapshot_obtained': match[4] == '1', 'label_code': match[5], 'value_code': match[6],
                'value_kind': match[7], 'label_missing_credential': match[8] == '1',
                'value_missing_credential': match[9] == '1'})
    return {'valid': True, 'observed': bool(records), 'records': records,
            'scope': 'already queried accessibility snapshot codes; not secret absence or product callsite proof',
            'raw_ui_text_printed': False, 'privacy_acceptance': False}
