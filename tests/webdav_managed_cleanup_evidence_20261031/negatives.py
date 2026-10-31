#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Negative controls for verify.py.

Each mutation is applied to a fresh copy of a real evidence directory; the
original is never written.  The unmodified copy must be accepted and every
mutation must be rejected with an error that names the broken invariant.

usage: negatives.py EVIDENCE_DIR --report FILE
"""
import argparse
import base64
import hashlib
import json
import shutil
import struct
import sys
import tempfile
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify  # noqa: E402


def load(d, name):
    return json.loads((d / 'cases' / f'{name}.json').read_text())


def save(d, name, case):
    (d / 'cases' / f'{name}.json').write_text(json.dumps(case))


def edit(name):
    def wrap(fn):
        def apply(d):
            case = load(d, name)
            fn(case)
            save(d, name, case)
        return apply
    return wrap


def snapshot(case, label):
    return next(s for s in case['snapshots'] if s['label'] == label)['entries']


def set_receipt(entry, raw):
    entry['bytes_b64'] = base64.b64encode(raw).decode()
    entry['sha256'] = hashlib.sha256(raw).hexdigest()


def recrc(raw):
    image = bytearray(raw)
    image[60:64] = bytes(4)
    struct.pack_into('<I', image, 60, zlib.crc32(bytes(image)) & 0xffffffff)
    return bytes(image)


@edit('22-kill-directory-created')
def drop_field(case):
    del case['processes'][0]['returncode']


@edit('24-kill-owned')
def normal_exit(case):
    case['processes'][0]['returncode'] = 0
    case['processes'][0]['signal_sent'] = None


@edit('28-kill-published')
def target_hash(case):
    snapshot(case, 'after_recovery_1')['dest/book.epub']['sha256'] = '0' * 64


@edit('28-kill-published')
def target_inode(case):
    snapshot(case, 'after_recovery_2')['dest/book.epub']['ino'] += 1


@edit('29-kill-alias-unlinked')
def illegal_nlink(case):
    snapshot(case, 'after_recovery_1')['dest/book.epub']['nlink'] = 3


@edit('25-kill-sealed')
def wrong_uuid(case):
    lines = case['processes'][0]['stdout']
    i = next(k for k, l in enumerate(lines) if l.startswith('UUID '))
    uuid = lines[i].split()[1]
    lines[i] = 'UUID ' + ('1' if uuid[0] == '0' else '0') + uuid[1:]


@edit('30-kill-receipt-next-reserved')
def wrong_generation(case):
    entry = snapshot(case, 'before_recovery')['root/.receipt.next']
    raw = bytearray(base64.b64decode(entry['bytes_b64']))
    struct.pack_into('<Q', raw, 16, struct.unpack_from('<Q', raw, 16)[0] + 1)
    set_receipt(entry, recrc(bytes(raw)))  # valid CRC, generation current+2


@edit('01-normal-publish-cleanup')
def bad_crc(case):
    entry = snapshot(case, 'final')['root/.receipt']
    raw = bytearray(base64.b64decode(entry['bytes_b64']))
    raw[16] ^= 1
    set_receipt(entry, bytes(raw))


def missing_case(d):
    (d / 'cases' / '17-legacy-unreceipted-directory.json').unlink()


def duplicate_case(d):
    shutil.copyfile(d / 'cases' / '05-same-process-lock.json', d / 'cases' / '05-same-process-lock-copy.json')


@edit('28-kill-published')
def second_pass_cleans(case):
    p = case['processes'][1]
    idx = [k for k, l in enumerate(p['stdout']) if l.startswith('RECOVER ')]
    report = json.loads(p['stdout'][idx[1]][len('RECOVER '):])
    report['cleaned'] = 1
    p['stdout'][idx[1]] = 'RECOVER ' + json.dumps(report)


def complete_with_timeout(d):
    case = load(d, '05-same-process-lock')
    case['processes'][0]['timed_out'] = True
    save(d, '05-same-process-lock', case)
    manifest = json.loads((d / 'manifest.json').read_text())
    manifest['complete'] = True
    (d / 'manifest.json').write_text(json.dumps(manifest))


# mutation -> substring the rejection must contain
MUTATIONS = {
    'missing-required-field': (drop_field, 'missing required field'),
    'sigkill-replaced-by-normal-exit': (normal_exit, 'not SIGKILL'),
    'target-hash-changed': (target_hash, 'destination sha256 changed'),
    'target-inode-changed': (target_inode, 'destination ino changed'),
    'illegal-nlink': (illegal_nlink, 'nlink'),
    'wrong-uuid': (wrong_uuid, 'UUID'),
    'wrong-generation': (wrong_generation, 'generation'),
    'bad-crc': (bad_crc, 'CRC mismatch'),
    'missing-case': (missing_case, "missing ['17-legacy-unreceipted-directory']"),
    'duplicate-case': (duplicate_case, "duplicate ['05-same-process-lock']"),
    'second-recovery-cleans-again': (second_pass_cleans, 'second pass cleaned again'),
    'complete-with-worker-timeout': (complete_with_timeout, 'claims complete but workers timed out'),
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('evidence')
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    source = Path(args.evidence)
    results, ok = {}, True
    with tempfile.TemporaryDirectory() as tmp:
        control = Path(tmp) / 'control'
        shutil.copytree(source, control)
        errors, _ = verify.verify(control)
        results['unmodified-control'] = dict(expected='accept', accepted=not errors, errors=errors)
        ok &= not errors
        for name, (mutate, needle) in MUTATIONS.items():
            copy = Path(tmp) / name
            shutil.copytree(source, copy)
            try:
                mutate(copy)
                errors, _ = verify.verify(copy)
                matched = [e for e in errors if needle in e]
                passed = bool(errors) and bool(matched)
                results[name] = dict(expected='reject', needle=needle, rejected=bool(errors), matched=matched,
                                     errors=errors, passed=passed)
            except Exception as error:  # a mutation that cannot be applied is a failure
                passed = False
                results[name] = dict(expected='reject', passed=False, error=f'{type(error).__name__}: {error}')
            ok &= passed
            print(('PASS ' if passed else 'FAIL ') + name)
    Path(args.report).write_text(json.dumps(dict(evidence=str(source), passed=ok, results=results), indent=2) + '\n')
    print('WC-EVIDENCE-NEGATIVES ' + json.dumps(dict(passed=ok, mutations=len(MUTATIONS))))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
