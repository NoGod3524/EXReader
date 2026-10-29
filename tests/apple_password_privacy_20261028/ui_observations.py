# SPDX-License-Identifier: MIT
"""Finite native UI state and bounded detail observations; never a privacy verdict."""
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
SAVE_PATTERN = re.compile(r'EXR_PRIVACY_UI_SAVE elapsed_ms=([0-9]{1,7}) '
    r'status=(saved|remember-update-incomplete|session-only|anonymous|anonymous-remove-incomplete|session-remove-incomplete|absent|ambiguous)')
DETAIL_PATTERN = re.compile(r'EXR_PRIVACY_UI_DETAIL elapsed_ms=([0-9]{1,7}) '
    r'phase=(remembered|session|missing-restart|unknown) missing_credential=([01])')


def parse_ui_observations(path):
    records, initial_save, failed_details = [], [], []
    last_elapsed = -1
    def ordered_time(value):
        nonlocal last_elapsed
        elapsed = int(value)
        require(last_elapsed <= elapsed <= 4800000, 'UI observation global time order differs')
        last_elapsed = elapsed
        return elapsed
    with path.open('r', encoding='utf-8', errors='replace') as file:
        for line in file:
            if line.startswith('EXR_PRIVACY_UI_SAVE '):
                match = SAVE_PATTERN.fullmatch(line.rstrip('\r\n'))
                require(match is not None, 'invalid finite UI save record')
                elapsed = ordered_time(match[1])
                require(not initial_save and not records and not failed_details,
                        'UI save observation bounds exceeded')
                initial_save.append({'elapsed_ms': elapsed, 'status': match[2]})
                continue
            if line.startswith('EXR_PRIVACY_UI_DETAIL '):
                match = DETAIL_PATTERN.fullmatch(line.rstrip('\r\n'))
                require(match is not None, 'invalid finite UI detail record')
                elapsed = ordered_time(match[1])
                require(len(failed_details) < 4 and
                        match[2] not in [row['phase'] for row in failed_details],
                        'UI detail observation bounds exceeded')
                require(not failed_details or elapsed >= failed_details[-1]['elapsed_ms'],
                        'UI detail observation order differs')
                require(records and records[-1]['phase'] == match[2] and
                        (records[-1]['label_code'] == 'failed' or
                         (records[-1]['label_code'] == 'empty' and records[-1]['value_code'] == 'failed')) and
                        elapsed >= records[-1]['elapsed_ms'],
                        'UI detail lacks preceding failed state')
                failed_details.append({'elapsed_ms': elapsed, 'phase': match[2],
                                       'missing_credential_text_exists': match[3] == '1'})
                continue
            if not line.startswith(PREFIX): continue
            match = PATTERN.fullmatch(line.rstrip('\r\n'))
            require(match is not None, 'invalid finite UI observation record')
            sequence, elapsed = int(match[1]), ordered_time(match[2])
            require(sequence <= 100000 and elapsed <= 4800000 and len(records) < 5000,
                    'UI observation bounds exceeded')
            require(not records or (sequence > records[-1]['sequence'] and elapsed >= records[-1]['elapsed_ms']),
                    'UI observation order differs')
            records.append({'sequence': sequence, 'elapsed_ms': elapsed, 'phase': match[3],
                'snapshot_obtained': match[4] == '1', 'label_code': match[5], 'value_code': match[6],
                'value_kind': match[7], 'label_missing_credential': match[8] == '1',
                'value_missing_credential': match[9] == '1'})
    return {'valid': True, 'observed': bool(records), 'records': records,
            'initial_save': initial_save, 'failed_details': failed_details,
            'scope': 'state snapshot codes plus finite accessibility text queries; absent is not cause proof',
            'raw_ui_text_printed': False, 'privacy_acceptance': False}
