#!/usr/bin/env python3
"""Compare a published library with the frozen symbol table in docs/ABI.md."""
import argparse
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/abi'))
from check_exports import inspect

ABI_DOC = ROOT / 'docs/ABI.md'
CONTRACT = ROOT / 'tools/abi/contract.json'


def load_baseline(abi_doc=ABI_DOC, contract=CONTRACT):
    rows = re.findall(r'^\|\s*`(exr_[A-Za-z0-9_]+)`\s*\|',
                      Path(abi_doc).read_text(encoding='utf-8'), re.MULTILINE)
    declared = json.loads(Path(contract).read_text(encoding='utf-8'))['symbols']
    if not rows or not declared:
        raise ValueError('ABI baseline must not be empty')
    if len(set(rows)) != len(rows) or len(set(declared)) != len(declared):
        raise ValueError('ABI baseline contains duplicate symbols')
    if set(rows) - set(declared):
        raise ValueError('contract.json is missing docs/ABI.md baseline symbols: '
                         f'{sorted(set(rows) - set(declared))}')
    return set(rows)


def check(binary, *, added_reason=None, abi_doc=ABI_DOC, contract=CONTRACT):
    expected = load_baseline(abi_doc, contract)
    if added_reason is not None and not added_reason.strip():
        raise ValueError('allowing added symbols requires a nonempty explanation')
    report = inspect(binary, expected)
    declared = set(json.loads(Path(contract).read_text(encoding='utf-8'))['symbols'])
    report.update(baseline_count=len(expected), baseline_document=str(abi_doc),
                  contract_additions=sorted(declared - expected), added_reason=added_reason)
    for part in report['slices']:
        part['added'] = part.pop('extra')
        part['missing_count'] = len(part['missing'])
        part['added_count'] = len(part['added'])
        part['passed'] = not part['missing'] and (not part['added'] or added_reason is not None)
    report['passed'] = all(part['passed'] for part in report['slices'])
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('binary', type=Path)
    parser.add_argument('--abi-doc', type=Path, default=ABI_DOC)
    parser.add_argument('--contract', type=Path, default=CONTRACT)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--allow-added', metavar='REASON', help='accept added symbols with an explicit explanation; missing symbols always fail')
    args = parser.parse_args()
    try:
        report = check(args.binary, added_reason=args.allow_added,
                       abi_doc=args.abi_doc, contract=args.contract)
        for part in report['slices']:
            print(f"{'PASS' if part['passed'] else 'FAIL'} ABI [{part['machine']}] "
                  f"baseline={report['baseline_count']} exports={part['symbol_count']} "
                  f"missing={part['missing_count']} added={part['added_count']}")
            if part['missing']:
                print('Missing: ' + ', '.join(part['missing']))
            if part['added']:
                print('Added: ' + ', '.join(part['added']))
        if args.allow_added:
            print('Added-symbol explanation: ' + args.allow_added)
        if report['contract_additions']:
            print('Machine-readable contract additions beyond docs baseline: '
                  + ', '.join(report['contract_additions']))
    except (OSError, ValueError, IndexError, KeyError, struct.error, UnicodeError) as error:
        report = {'path': str(args.binary), 'passed': False, 'error': str(error)}
        print('ERROR ABI: ' + str(error), file=sys.stderr)
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())
