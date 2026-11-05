#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Offline verifier for exr-wc-evidence/1 (see SCHEMA.md).

Recomputes the managed-cleanup invariants from raw evidence only: process
exit codes and signals, fixture snapshots and receipt bytes.  The producer's
passed flags and results.json are never read.  The expectation tables below
are restated from the contract in exr_webdav_cleanup.h and the K01 document,
not imported from the producer.

usage: verify.py EVIDENCE_DIR [--report FILE]
Exit 0 only when every check holds.
"""
import argparse
import base64
import hashlib
import json
import re
import struct
import sys
import zlib
from pathlib import Path

SCHEMA = 'exr-wc-evidence/1'
DATA = b'managed cleanup payload 20261031\n'
DATA_SHA = hashlib.sha256(DATA).hexdigest()
SIGKILL = 9
EACCES = 13
OK, IO, BUSY = 0, 2, 3
RESERVED, OWNED, SEALED, INTENT, PUBLISHED, CLEANED = range(1, 7)
NAMES = sorted([
    '01-normal-publish-cleanup', '02-abandon-owned', '03-abandon-sealed', '04-unauthorized-abandon-refused',
    '05-same-process-lock', '06-cross-process-lock', '07-active-tx-blocks-close',
    '08-existing-target-not-replaced', '09-root-or-txdir-destination-refused',
    '10-payload-inode-replacement-refused', '11-payload-symlink-refused', '12-unknown-entry-preserved',
    '13-real-eacces-recovered', '14-bounded-paging-idempotent', '15-lifetime-slot-limit', '16-wrong-uuid',
    '17-legacy-unreceipted-directory', '18-root-symlink', '19-receipt-checksum-corruption',
    '20-residual-receipt-next', '21-illegal-leaf', '22-kill-directory-created', '23-kill-payload-created',
    '24-kill-owned', '25-kill-sealed', '26-kill-publish-intent', '27-kill-linked', '28-kill-published',
    '29-kill-alias-unlinked', '30-kill-receipt-next-reserved'])
# Kill cases: hook phase, slot state at the hook, receipt states after
# recovery, slots cleaned by the first pass, pending slots, and the residue a
# kill leaves: (txdir, payload, destination, destination nlink, .receipt.next).
KILL = {
    '22-kill-directory-created': ('directory_created', RESERVED, [RESERVED], 0, 1, (1, 0, 0, 0, 0)),
    '23-kill-payload-created': ('payload_created', RESERVED, [RESERVED], 0, 1, (1, 1, 0, 0, 0)),
    '24-kill-owned': ('owned', OWNED, [OWNED], 0, 1, (1, 1, 0, 0, 0)),
    '25-kill-sealed': ('sealed', SEALED, [SEALED], 0, 1, (1, 1, 0, 0, 0)),
    '26-kill-publish-intent': ('publish_intent', INTENT, [INTENT], 0, 1, (1, 1, 0, 0, 0)),
    '27-kill-linked': ('linked', INTENT, [INTENT], 0, 1, (1, 1, 1, 2, 0)),
    '28-kill-published': ('published', PUBLISHED, [CLEANED], 1, 0, (1, 1, 1, 2, 0)),
    '29-kill-alias-unlinked': ('alias_unlinked', PUBLISHED, [CLEANED], 1, 0, (1, 0, 1, 1, 0)),
    '30-kill-receipt-next-reserved': ('receipt_next_synced', RESERVED, [], 0, 0, (0, 0, 0, 0, 1)),
}
ENTRY_FIELDS = ('type', 'mode', 'dev', 'ino', 'nlink', 'size')
PROCESS_FIELDS = ('kind', 'argv', 'pid', 'returncode', 'timed_out', 'signal_sent', 'handshake', 'stdout')
CASE_FIELDS = ('name', 'phases', 'processes', 'snapshots', 'exception', 'seconds')
IDENTITY_FIELDS = ('schema', 'core_sha', 'tests_sha', 'system', 'machine', 'uid', 'euid', 'compiler',
                   'worker_limit_seconds', 'payload_sha256', 'files')
IDENTITY_FILES = ('consumer', 'hookworker', 'archive', 'installed_header')
HEX40, HEX64 = re.compile(r'[0-9a-f]{40}'), re.compile(r'[0-9a-f]{64}')


class Bad(Exception):
    pass


def need(cond, msg):
    if not cond:
        raise Bad(msg)


def fields(obj, names, where):
    need(isinstance(obj, dict), f'{where}: not an object')
    missing = [n for n in names if n not in obj]
    need(not missing, f'{where}: missing required field(s) {missing}')


def decode_receipt(raw, where):
    """Decodes the fixed little-endian v1 layout; CRC-32 detects damage only."""
    need(len(raw) == 64 + 64 * 64, f'{where}: receipt is {len(raw)} bytes')
    image = bytearray(raw)
    image[60:64] = b'\0\0\0\0'
    magic, version, count, generation, root_ino = struct.unpack_from('<8sIIQQ', raw, 0)
    uuid, crc = raw[32:48].hex(), struct.unpack_from('<I', raw, 60)[0]
    need(magic == b'EXRWCRCT' and version == 1, f'{where}: bad magic/version')
    need(crc == zlib.crc32(bytes(image)) & 0xffffffff, f'{where}: CRC mismatch')
    need(raw[48:60] == bytes(12), f'{where}: reserved header bytes not zero')
    need(count <= 64 and generation and root_ino, f'{where}: count/generation/root inode invalid')
    slots = []
    for i in range(64):
        s = raw[64 + 64 * i:128 + 64 * i]
        if i >= count:
            need(s == bytes(64), f'{where}: unused slot {i} not zero')
            continue
        state, reserved, nbytes, dir_ino, payload_ino = struct.unpack_from('<IIQQQ', s, 0)
        need(RESERVED <= state <= CLEANED and not reserved and s[48:] == bytes(16), f'{where}: slot {i} invalid')
        need((not (nbytes or dir_ino or payload_ino)) if state == RESERVED else (dir_ino and payload_ino),
             f'{where}: slot {i} inode fields inconsistent with state {state}')
        slots.append(dict(state=state, bytes=nbytes, dir_ino=dir_ino, payload_ino=payload_ino, id=s[32:48].hex()))
    return dict(count=count, generation=generation, root_ino=root_ino, uuid=uuid, slots=slots)


def check_entry(entry, where):
    fields(entry, ENTRY_FIELDS, where)
    if entry['type'] == 'file' and 'read_errno' not in entry:
        need(HEX64.fullmatch(str(entry.get('sha256', ''))), f'{where}: file without sha256')


def snap(case, label):
    found = [s for s in case['snapshots'] if s.get('label') == label]
    need(len(found) == 1, f'{case["name"]}: expected one {label!r} snapshot, found {len(found)}')
    entries = found[0].get('entries')
    need(isinstance(entries, dict), f'{case["name"]}/{label}: entries missing')
    for path, entry in entries.items():
        check_entry(entry, f'{case["name"]}/{label}/{path}')
    return entries


def receipt(entries, path, where):
    entry = entries.get(path)
    need(entry and entry['type'] == 'file' and 'bytes_b64' in entry, f'{where}: {path} bytes missing')
    raw = base64.b64decode(entry['bytes_b64'])
    need(hashlib.sha256(raw).hexdigest() == entry['sha256'], f'{where}: {path} bytes do not match sha256')
    return decode_receipt(raw, f'{where}/{path}')


def tx_dirs(entries, root='root'):
    return sorted(p for p in entries if re.fullmatch(re.escape(root) + r'/tx-[0-9a-f]{32}', p))


def check_root_consistent(entries, root, where, uuid=None, strict_payload=True):
    """Receipt decodes, belongs to this directory and matches the tx dirs."""
    m = receipt(entries, f'{root}/.receipt', where)
    need(m['root_ino'] == entries[root]['ino'], f'{where}: receipt root inode {m["root_ino"]} != {entries[root]["ino"]}')
    if uuid is not None:
        need(m['uuid'] == uuid, f'{where}: receipt UUID {m["uuid"]} != handshake {uuid}')
    need(entries[root]['type'] == 'dir' and entries[root]['mode'] & 0o077 == 0, f'{where}: root not private dir')
    lock = entries.get(f'{root}/.lock')
    need(lock and lock['type'] == 'file', f'{where}: .lock missing')
    for path in tx_dirs(entries, root):
        tid = path.rsplit('tx-', 1)[1]
        owners = [s for s in m['slots'] if s['id'] == tid]
        need(len(owners) == 1 and owners[0]['state'] != CLEANED, f'{where}: {path} not owned by a live slot')
        slot = owners[0]
        if slot['state'] != RESERVED:
            need(entries[path]['ino'] == slot['dir_ino'], f'{where}: {path} inode differs from receipt')
            payload = entries.get(f'{path}/payload')
            if strict_payload and payload is not None and payload['type'] == 'file':
                need(payload['ino'] == slot['payload_ino'], f'{where}: payload inode differs from receipt')
    return m


def parse_process(case, index, kind=None, argv1=None):
    procs = case['processes']
    need(index < len(procs), f'{case["name"]}: process {index} missing')
    p = procs[index]
    fields(p, PROCESS_FIELDS, f'{case["name"]}/process[{index}]')
    if kind:
        need(p['kind'] == kind, f'{case["name"]}/process[{index}]: kind {p["kind"]} != {kind}')
    if argv1:
        need(len(p['argv']) > 1 and p['argv'][1] == argv1, f'{case["name"]}/process[{index}]: argv {p["argv"][:2]}')
    return p


def exited_ok(p, where):
    need(not p['timed_out'], f'{where}: worker timed out')
    need(p['signal_sent'] is None and p['returncode'] == 0, f'{where}: exit {p["returncode"]} signal {p["signal_sent"]}')


def sigkilled(p, where):
    need(not p['timed_out'], f'{where}: worker timed out')
    need(p['signal_sent'] == SIGKILL, f'{where}: signal sent {p["signal_sent"]}, not SIGKILL')
    need(p['returncode'] == -SIGKILL, f'{where}: wait returned {p["returncode"]}, not -SIGKILL')


def one(lines, prefix, where):
    found = [l[len(prefix):] for l in lines if l.startswith(prefix)]
    need(len(found) == 1, f'{where}: expected one {prefix!r} line, got {len(found)}')
    return found[0]


def recovery(case, index, where):
    p = parse_process(case, index, 'worker', 'recover-step')
    exited_ok(p, where)
    need(one(p['stdout'], 'OPEN ', where) == '0', f'{where}: reopen status not OK')
    reports = [json.loads(l[len('RECOVER '):]) for l in p['stdout'] if l.startswith('RECOVER ')]
    need(len(reports) == 2, f'{where}: {len(reports)} recovery reports, expected 2')
    return reports


def same_file(a, b, where):
    need(a and b and a['type'] == b['type'] == 'file', f'{where}: destination missing or not a regular file')
    for k in ('dev', 'ino', 'sha256', 'size', 'mode'):
        need(a[k] == b[k], f'{where}: destination {k} changed {a[k]} -> {b[k]}')


def verify_kill(case):
    name = case['name']
    phase, state, states, cleaned, pending, residue = KILL[name]
    has_tx, has_payload, has_book, nlink, has_next = residue
    w = parse_process(case, 0, 'worker', 'kill-flow')
    sigkilled(w, f'{name}/kill-flow')
    uuid = one(w['stdout'], 'UUID ', name).strip()
    need(f'HELD {phase} 0 {state}' in w['stdout'], f'{name}: handshake HELD {phase} 0 {state} not seen')
    before = snap(case, 'before_recovery')
    need(len(tx_dirs(before)) == has_tx, f'{name}: {len(tx_dirs(before))} tx dirs before recovery')
    if has_tx:
        need((f'{tx_dirs(before)[0]}/payload' in before) == bool(has_payload), f'{name}: payload presence')
    book = before.get('dest/book.epub')
    need((book is not None) == bool(has_book), f'{name}: destination presence before recovery')
    if book:
        need(book['nlink'] == nlink and book['sha256'] == DATA_SHA, f'{name}: destination before {book}')
    need(('root/.receipt.next' in before) == bool(has_next), f'{name}: .receipt.next presence')
    m0 = check_root_consistent(before, 'root', f'{name}/before', uuid)
    if has_next:
        nxt = receipt(before, 'root/.receipt.next', f'{name}/before')
        need(nxt['uuid'] == m0['uuid'] and nxt['root_ino'] == m0['root_ino'], f'{name}: .receipt.next of another root')
        need(nxt['generation'] == m0['generation'] + 1, f'{name}: .receipt.next generation {nxt["generation"]} '
             f'is not current {m0["generation"]} + 1')
        need(m0['count'] == 0 and [s['state'] for s in nxt['slots']] == [state], f'{name}: residual successor slots')
    else:
        need([s['state'] for s in m0['slots']] == [state], f'{name}: receipt states before {m0["slots"]}')
    reports = recovery(case, 1, name)
    for i, r in enumerate(reports):
        need(r['status'] == OK and r['refused'] == 0 and r['receipt_uncertain'] == 0, f'{name}: pass {i + 1} {r}')
        need(r['pending'] == pending and r['states'] == states, f'{name}: pass {i + 1} pending/states {r}')
    need(reports[0]['cleaned'] == cleaned, f'{name}: first pass cleaned {reports[0]["cleaned"]} != {cleaned}')
    need(reports[1]['cleaned'] == 0, f'{name}: second pass cleaned again ({reports[1]["cleaned"]})')
    previous = before
    for label in ('after_recovery_1', 'after_recovery_2'):
        after = snap(case, label)
        m = check_root_consistent(after, 'root', f'{name}/{label}', uuid)
        need([s['state'] for s in m['slots']] == states, f'{name}/{label}: receipt states {m["slots"]}')
        need('root/.receipt.next' not in after, f'{name}/{label}: .receipt.next survived')
        target = after.get('dest/book.epub')
        if book:
            same_file(book, target, f'{name}/{label}')
            need(target['nlink'] == (1 if cleaned else book['nlink']), f'{name}/{label}: nlink {target["nlink"]}')
        else:
            need(target is None, f'{name}/{label}: destination appeared')
        need(len(tx_dirs(after)) == (has_tx and not cleaned), f'{name}/{label}: tx dirs {tx_dirs(after)}')
        if not cleaned:  # pending residue is kept exactly as it was
            for path, e in previous.items():
                if path.startswith('root/tx-'):
                    a = after.get(path)
                    need(a and (a['type'], a['ino'], a.get('sha256')) == (e['type'], e['ino'], e.get('sha256')),
                         f'{name}/{label}: pending {path} changed')
        previous = after


def verify_eacces(case, identity):
    name = case['name']
    need(identity['euid'] != 0, f'{name}: runner euid is root')
    p = parse_process(case, 0, 'run', 'case')
    exited_ok(p, f'{name}/phase-one')
    need(f'PASS {name}' in p['stdout'], f'{name}: phase one PASS marker missing')
    uuid = one(p['stdout'], 'UUID ', name).strip()
    canary = dict(kv.split('=') for kv in one(p['stdout'], 'EVID canary ', name).split())
    need(int(canary['euid']) != 0 and int(canary['euid']) == identity['euid'], f'{name}: canary euid {canary}')
    need(canary['mode'] == '500' and int(canary['rc']) != 0 and int(canary['errno']) == EACCES,
         f'{name}: canary did not prove a real EACCES {canary}')
    cl = {k: int(v, 8 if k == 'txdir_mode' else 10)
          for k, v in (kv.split('=') for kv in one(p['stdout'], 'EVID cleanup ', name).split())}
    need(cl['txdir_mode'] == 0o500 and cl['status'] == IO and cl['native_error'] == EACCES and
         cl['pending'] == 1 and cl['removed'] == 0 and cl['receipt_uncertain'] == 0,
         f'{name}: cleanup did not report a pending EACCES {cl}')
    before = snap(case, 'before_recovery')
    m0 = check_root_consistent(before, 'root', f'{name}/before', uuid)
    need([s['state'] for s in m0['slots']] == [PUBLISHED], f'{name}: before states {m0["slots"]}')
    book = before.get('dest/book.epub')
    need(book and book['nlink'] == 2 and book['sha256'] == DATA_SHA, f'{name}: destination before {book}')
    need(len(tx_dirs(before)) == 1, f'{name}: tx dir missing before recovery')
    reports = recovery(case, 1, name)
    need(reports[0]['status'] == OK and reports[0]['cleaned'] == 1 and reports[0]['pending'] == 0 and
         reports[0]['states'] == [CLEANED], f'{name}: new process did not recover {reports[0]}')
    need(reports[1]['cleaned'] == 0 and reports[1]['pending'] == 0 and reports[1]['states'] == [CLEANED],
         f'{name}: second pass cleaned again or not idempotent {reports[1]}')
    for label in ('after_recovery_1', 'after_recovery_2'):
        after = snap(case, label)
        check_root_consistent(after, 'root', f'{name}/{label}', uuid)
        same_file(book, after.get('dest/book.epub'), f'{name}/{label}')
        need(after['dest/book.epub']['nlink'] == 1, f'{name}/{label}: alias not removed')
        need(not tx_dirs(after), f'{name}/{label}: tx dir left behind')


def verify_cross(case):
    name = case['name']
    need(case['phases'] == ['prep', 'hold', 'try-open-while-held', 'kill-holder', 'try-open-after-kill'],
         f'{name}: phase order {case["phases"]}')
    prep = parse_process(case, 0, 'run', 'prep')
    exited_ok(prep, f'{name}/prep')
    uuid = one(prep['stdout'], 'UUID ', name).strip()
    hold = parse_process(case, 1, 'worker', 'hold')
    need(hold['handshake'] == ['HELD 0'], f'{name}: holder handshake {hold["handshake"]}')
    sigkilled(hold, f'{name}/hold')
    t1, t2 = parse_process(case, 2, 'run', 'try-open'), parse_process(case, 3, 'run', 'try-open')
    exited_ok(t1, f'{name}/try-open-1')
    exited_ok(t2, f'{name}/try-open-2')
    need(one(t1['stdout'], 'STATUS ', name) == str(BUSY), f'{name}: second process was not BUSY')
    need(one(t2['stdout'], 'STATUS ', name) == str(OK), f'{name}: lock not free after SIGKILL')
    check_root_consistent(snap(case, 'final'), 'root', f'{name}/final', uuid)


def verify_in_process(case):
    name = case['name']
    p = parse_process(case, 0, 'run', 'case')
    exited_ok(p, name)
    need(f'PASS {name}' in p['stdout'] and not any(l.startswith('FAIL') for l in p['stdout']), f'{name}: no PASS')
    final = snap(case, 'final')
    roots = sorted(path.rsplit('/', 1)[0] for path in final if path.endswith('/.receipt') and path.count('/') == 1)
    # Case 10 replaces the payload inode on purpose; its refusal is the point.
    strict = name != '10-payload-inode-replacement-refused'
    decoded = {r: check_root_consistent(final, r, f'{name}/final', strict_payload=strict) for r in roots}
    need(not any(path.endswith('/.receipt.next') for path in final), f'{name}: .receipt.next left behind')
    states = {r: [s['state'] for s in m['slots']] for r, m in decoded.items()}
    book = final.get('dest/book.epub')
    if name == '01-normal-publish-cleanup':
        need(states == {'root': [CLEANED]} and book and book['nlink'] == 1 and book['sha256'] == DATA_SHA,
             f'{name}: final {states} {book}')
    elif name == '08-existing-target-not-replaced':
        need(book and book['nlink'] == 1 and book['sha256'] == hashlib.sha256(b'old\n').hexdigest(),
             f'{name}: existing target changed {book}')
    elif name == '12-unknown-entry-preserved':
        need(states == {'root': [CLEANED]} and book and book['nlink'] == 1 and book['sha256'] == DATA_SHA,
             f'{name}: final {states} {book}')
    elif name == '14-bounded-paging-idempotent':
        need(states == {'root': [CLEANED] * 5}, f'{name}: final {states}')
        for i in range(5):
            b = final.get(f'dest/b{i}.epub')
            need(b and b['nlink'] == 1 and b['sha256'] == DATA_SHA, f'{name}: b{i}.epub {b}')
    elif name == '15-lifetime-slot-limit':
        need(states == {'root': [CLEANED] * 64}, f'{name}: final slot states {states}')
    elif name == '17-legacy-unreceipted-directory':
        legacy = final.get('legacy/payload-old')
        need(legacy and legacy['sha256'] == DATA_SHA and 'legacy/.receipt' not in final, f'{name}: legacy residue')
    elif name in ('10-payload-inode-replacement-refused', '11-payload-symlink-refused'):
        payload = [final.get(f'{d}/payload') for d in tx_dirs(final)]
        need(len(payload) == 1 and payload[0], f'{name}: refused payload not preserved')
        need(payload[0]['type'] == ('symlink' if name.startswith('11') else 'file'), f'{name}: payload {payload[0]}')
        need(states == {'root': [SEALED]} and 'dest/book.epub' not in final, f'{name}: final {states}')


def verify(evidence):
    """Returns (errors, per-case verdicts)."""
    errors, verdicts = [], {}
    try:
        identity = json.loads((evidence / 'identity.json').read_text())
        fields(identity, IDENTITY_FIELDS, 'identity')
        need(identity['schema'] == SCHEMA, f'identity: schema {identity["schema"]}')
        need(HEX40.fullmatch(identity['core_sha']) and HEX40.fullmatch(identity['tests_sha']), 'identity: SHAs')
        need(identity['payload_sha256'] == DATA_SHA, 'identity: payload hash')
        for label in IDENTITY_FILES:
            need(HEX64.fullmatch(str(identity['files'].get(label, {}).get('sha256', ''))), f'identity: {label} hash')
    except (Bad, OSError, ValueError) as error:
        return [f'identity: {error}'], verdicts
    cases, seen = {}, []
    for path in sorted((evidence / 'cases').glob('*.json')):
        try:
            case = json.loads(path.read_text())
            fields(case, CASE_FIELDS, path.name)
        except (Bad, ValueError) as error:
            errors.append(f'{path.name}: {error}')
            continue
        seen.append(case['name'])
        cases[case['name']] = case
    duplicates = sorted({n for n in seen if seen.count(n) > 1})
    missing, extra = sorted(set(NAMES) - set(seen)), sorted(set(seen) - set(NAMES))
    if duplicates or missing or extra or len(seen) != 30:
        errors.append(f'case set: {len(seen)} records, missing {missing}, duplicate {duplicates}, unknown {extra}')
    try:
        manifest = json.loads((evidence / 'manifest.json').read_text())
        if sorted(manifest.get('names', [])) != NAMES or len(manifest['names']) != 30:
            errors.append('manifest: names are not the fixed 30-case set')
        timed_out = [n for n, c in cases.items() if any(p.get('timed_out') for p in c['processes'])]
        if manifest.get('complete') and timed_out:
            errors.append(f'manifest claims complete but workers timed out in {timed_out}')
    except (OSError, ValueError) as error:
        errors.append(f'manifest: {error}')
    for name in NAMES:
        case = cases.get(name)
        if case is None:
            verdicts[name] = 'missing'
            continue
        try:
            for i, p in enumerate(case['processes']):
                fields(p, PROCESS_FIELDS, f'{name}/process[{i}]')
            need(case['exception'] is None, f'{name}: producer recorded exception {case["exception"]!r}')
            if name in KILL:
                verify_kill(case)
            elif name == '13-real-eacces-recovered':
                verify_eacces(case, identity)
            elif name == '06-cross-process-lock':
                verify_cross(case)
            else:
                verify_in_process(case)
            verdicts[name] = 'verified'
        except (Bad, KeyError, TypeError, ValueError, struct.error) as error:
            verdicts[name] = 'rejected'
            errors.append(f'{name}: {type(error).__name__ + ": " if not isinstance(error, Bad) else ""}{error}')
    return errors, verdicts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('evidence')
    parser.add_argument('--report')
    args = parser.parse_args()
    errors, verdicts = verify(Path(args.evidence))
    report = dict(schema=SCHEMA, evidence=args.evidence, accepted=not errors, errors=errors, cases=verdicts)
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2) + '\n')
    for error in errors:
        print('REJECT ' + error)
    print('WC-EVIDENCE-VERDICT ' + json.dumps(dict(accepted=not errors, verified=sum(v == 'verified' for v in verdicts.values()),
                                                   errors=len(errors))))
    return 0 if not errors else 1


if __name__ == '__main__':
    sys.exit(main())
