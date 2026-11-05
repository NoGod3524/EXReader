#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Run the fixed 30-case EXReaderWebDAVCleanup matrix.

Every fixture lives in a fresh tempfile directory, every worker has a 30 s
limit, cross-process timing is a HELD/hook marker handshake, and only PIDs
this runner spawned are killed.

Besides results.json the runner writes raw per-case evidence (processes,
signals, filesystem snapshots, receipt bytes) under OUTPUT/evidence as each
case ends, so tests/webdav_managed_cleanup_evidence_20261031/verify.py can
recompute the invariants without trusting the passed flags.
"""
import argparse
import base64
import hashlib
import json
import os
import platform
import queue
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

LIMIT = 30
DATA = b"managed cleanup payload 20261031\n"
IN_PROCESS = [
    '01-normal-publish-cleanup', '02-abandon-owned', '03-abandon-sealed',
    '04-unauthorized-abandon-refused', '05-same-process-lock',
    '07-active-tx-blocks-close', '08-existing-target-not-replaced',
    '09-root-or-txdir-destination-refused', '10-payload-inode-replacement-refused',
    '11-payload-symlink-refused', '12-unknown-entry-preserved',
    '14-bounded-paging-idempotent', '15-lifetime-slot-limit', '16-wrong-uuid',
    '17-legacy-unreceipted-directory', '18-root-symlink',
    '19-receipt-checksum-corruption', '20-residual-receipt-next', '21-illegal-leaf',
]
# name: (phase, state, states after recovery, cleaned, pending)
KILL = {
    '22-kill-directory-created': ('directory_created', 1, [1], 0, 1),
    '23-kill-payload-created': ('payload_created', 1, [1], 0, 1),
    '24-kill-owned': ('owned', 2, [2], 0, 1),
    '25-kill-sealed': ('sealed', 3, [3], 0, 1),
    '26-kill-publish-intent': ('publish_intent', 4, [4], 0, 1),
    '27-kill-linked': ('linked', 4, [4], 0, 1),
    '28-kill-published': ('published', 5, [6], 1, 0),
    '29-kill-alias-unlinked': ('alias_unlinked', 5, [6], 1, 0),
    '30-kill-receipt-next-reserved': ('receipt_next_synced', 1, [], 0, 0),
}
# What a kill at each phase leaves on disk: (txdir, payload, book, book nlink, .receipt.next)
DISK = {
    'directory_created': (True, False, False, 0, False),
    'payload_created': (True, True, False, 0, False),
    'owned': (True, True, False, 0, False),
    'sealed': (True, True, False, 0, False),
    'publish_intent': (True, True, False, 0, False),
    'linked': (True, True, True, 2, False),
    'published': (True, True, True, 2, False),
    'alias_unlinked': (True, False, True, 1, False),
    'receipt_next_synced': (False, False, False, 0, True),
}
ALL = sorted(IN_PROCESS + ['06-cross-process-lock', '13-real-eacces-recovered'] + list(KILL))


class Failure(Exception):
    pass


def expect(condition, message):
    if not condition:
        raise Failure(message)


def process_record(ev, kind, argv):
    rec = dict(kind=kind, argv=[os.path.basename(argv[0])] + argv[1:], pid=None, returncode=None,
               timed_out=False, signal_sent=None, handshake=[], stdout=[])
    ev['processes'].append(rec)
    return rec


class Worker:
    """A spawned worker whose stdout lines arrive through a queue."""

    def __init__(self, argv, log, ev):
        self.argv = argv
        self.log = log
        self.rec = process_record(ev, 'worker', argv)
        self.lines = queue.Queue()
        self.proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True)
        self.rec['pid'] = self.proc.pid
        self.deadline = time.monotonic() + LIMIT
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        for line in self.proc.stdout:
            self.log.append(line.rstrip('\n'))
            self.rec['stdout'].append(line.rstrip('\n'))
            self.lines.put(line.rstrip('\n'))
        self.lines.put(None)

    def wait_for(self, prefix):
        while True:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                self.rec['timed_out'] = True
            expect(remaining > 0, f'timeout waiting for {prefix!r}')
            try:
                line = self.lines.get(timeout=remaining)
            except queue.Empty:
                self.rec['timed_out'] = True
                raise Failure(f'timeout waiting for {prefix!r}')
            expect(line is not None, f'worker exited before {prefix!r}')
            if line.startswith(prefix):
                self.rec['handshake'].append(line)
                return line

    def send(self, text):
        self.proc.stdin.write(text)
        self.proc.stdin.flush()

    def finish(self):
        """Waits for a normal exit within the worker deadline."""
        try:
            self.rec['returncode'] = self.proc.wait(timeout=max(0.1, self.deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            self.rec['timed_out'] = True
            self.kill()
            raise Failure('worker did not exit within its limit')
        self.reader.join(timeout=5)
        return self.rec['returncode']

    def kill(self):
        if self.proc.poll() is None:
            self.proc.kill()
            self.rec['signal_sent'] = int(signal.SIGKILL)
        self.rec['returncode'] = self.proc.wait(timeout=LIMIT)
        self.reader.join(timeout=5)
        return self.rec['returncode']


def run(argv, log, ev):
    rec = process_record(ev, 'run', argv)
    try:
        proc = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=LIMIT)
    except subprocess.TimeoutExpired as error:
        rec['timed_out'] = True
        out = error.stdout or ''
        rec['stdout'] = (out.decode(errors='replace') if isinstance(out, bytes) else out).splitlines()
        raise Failure(f'{rec["argv"][:2]} exceeded {LIMIT} s')
    log.extend(proc.stdout.splitlines())
    rec['returncode'] = proc.returncode
    rec['stdout'] = proc.stdout.splitlines()
    return proc.returncode, proc.stdout.splitlines()


def line_value(lines, prefix):
    found = [line[len(prefix):].strip() for line in lines if line.startswith(prefix)]
    expect(len(found) == 1, f'expected one {prefix!r} line, got {found}')
    return found[0]


def recover(consumer, base, uuid, log, ev):
    """Two recover passes in one new process, snapshotting after each pass."""
    ev['phases'].append('recover')
    worker = Worker([consumer, 'recover-step', str(base), uuid], log, ev)
    reports = []
    try:
        status = int(worker.wait_for('OPEN ').split()[1])
        if status == 0:
            for index in range(2):
                reports.append(json.loads(worker.wait_for('RECOVER ')[len('RECOVER '):]))
                snapshot(base, f'after_recovery_{index + 1}', ev)
                worker.send('\n')
        code = worker.finish()
    finally:
        if worker.rec['returncode'] is None:
            worker.kill()
    expect(code == 0, f'recover exited {code}')
    return status, reports


def entry_record(path):
    st = os.lstat(path)
    rec = dict(type='file' if stat.S_ISREG(st.st_mode) else 'dir' if stat.S_ISDIR(st.st_mode)
               else 'symlink' if stat.S_ISLNK(st.st_mode) else 'other',
               mode=stat.S_IMODE(st.st_mode), dev=st.st_dev, ino=st.st_ino, nlink=st.st_nlink, size=st.st_size)
    if rec['type'] == 'symlink':
        rec['link'] = os.readlink(path)
    if rec['type'] == 'file':
        try:
            raw = Path(path).read_bytes()
        except OSError as error:
            rec['read_errno'] = error.errno
        else:
            rec['sha256'] = hashlib.sha256(raw).hexdigest()
            if Path(path).name.startswith('.receipt'):
                rec['bytes_b64'] = base64.b64encode(raw).decode()
    return rec


def snapshot(base, label, ev):
    """Every entry of the synthetic fixture, without following symlinks."""
    entries, errors = {}, []

    def walk_error(error):
        errors.append(dict(path=str(error.filename), errno=error.errno))

    for directory, dirs, files in os.walk(base, onerror=walk_error):
        for name in sorted(dirs + files):
            path = Path(directory, name)
            try:
                entries[path.relative_to(base).as_posix()] = entry_record(path)
            except OSError as error:
                errors.append(dict(path=str(path), errno=error.errno))
    ev['snapshots'].append(dict(label=label, entries=entries, walk_errors=errors))


def file_record(path):
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return None
    return dict(dev=st.st_dev, ino=st.st_ino, nlink=st.st_nlink, size=st.st_size,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest() if stat.S_ISREG(st.st_mode) else None)


def tx_dirs(root):
    return sorted(p for p in root.iterdir() if p.name.startswith('tx-')) if root.is_dir() else []


def case_in_process(name, consumer, base, log, ev):
    ev['phases'].append('case')
    code, lines = run([consumer, 'case', str(base), name], log, ev)
    snapshot(base, 'final', ev)
    expect(code == 0 and f'PASS {name}' in lines, f'worker exited {code}')


def case_cross_process(consumer, base, log, ev):
    ev['phases'].append('prep')
    code, lines = run([consumer, 'prep', str(base)], log, ev)
    expect(code == 0, 'prep failed')
    uuid = line_value(lines, 'UUID ')
    ev['phases'].append('hold')
    holder = Worker([consumer, 'hold', str(base), uuid], log, ev)
    try:
        expect(holder.wait_for('HELD ') == 'HELD 0', 'holder did not open the root')
        ev['phases'].append('try-open-while-held')
        code, lines = run([consumer, 'try-open', str(base), uuid], log, ev)
        expect(code == 0 and line_value(lines, 'STATUS ') == '3', 'second process was not BUSY')
    finally:
        ev['phases'].append('kill-holder')
        returncode = holder.kill()
    expect(returncode == -9, f'holder ended with {returncode}, not SIGKILL')
    ev['phases'].append('try-open-after-kill')
    code, lines = run([consumer, 'try-open', str(base), uuid], log, ev)
    snapshot(base, 'final', ev)
    expect(code == 0 and line_value(lines, 'STATUS ') == '0', 'lock not released by process death')


def case_eacces(consumer, base, log, ev):
    expect(os.geteuid() != 0, 'real EACCES requires a non-root runner')
    name = '13-real-eacces-recovered'
    ev['phases'].append('case')
    code, lines = run([consumer, 'case', str(base), name], log, ev)
    snapshot(base, 'before_recovery', ev)
    expect(code == 0 and f'PASS {name}' in lines, f'phase one exited {code}')
    uuid = line_value(lines, 'UUID ')
    book = base / 'dest' / 'book.epub'
    before = file_record(book)
    expect(before and before['nlink'] == 2, 'alias missing after EACCES')
    status, reports = recover(consumer, base, uuid, log, ev)
    expect(status == 0 and len(reports) == 2, 'reopen failed')
    first, second = reports
    expect(first['status'] == 0 and first['cleaned'] == 1 and first['pending'] == 0 and first['states'] == [6],
           f'new process did not recover: {first}')
    expect(second['cleaned'] == 0 and second['pending'] == 0 and second['states'] == [6], f'not idempotent: {second}')
    after = file_record(book)
    expect(after and after['nlink'] == 1 and after['sha256'] == hashlib.sha256(DATA).hexdigest() and
           (after['dev'], after['ino']) == (before['dev'], before['ino']), 'published target changed')
    expect(not tx_dirs(base / 'root'), 'transaction directory left behind')


def case_kill(name, hookworker, consumer, base, log, ev):
    phase, state, states, cleaned, pending = KILL[name]
    ev['phases'].append('kill-flow')
    worker = Worker([hookworker, 'kill-flow', str(base), phase, str(state)], log, ev)
    try:
        uuid = worker.wait_for('UUID ').split()[1]
        held = worker.wait_for('HELD ')
        expect(held.split()[1:] == [phase, '0', str(state)], f'held at {held!r}')
    finally:
        ev['phases'].append('kill-worker')
        returncode = worker.kill()
    snapshot(base, 'before_recovery', ev)
    expect(returncode == -9, f'worker ended with {returncode}, not SIGKILL')
    root, book = base / 'root', base / 'dest' / 'book.epub'
    has_tx, has_payload, has_book, nlink, has_next = DISK[phase]
    dirs = tx_dirs(root)
    expect(bool(dirs) == has_tx and len(dirs) <= 1, f'transaction directories {dirs}')
    expect((bool(dirs) and (dirs[0] / 'payload').exists()) == has_payload, 'payload presence mismatch')
    before = file_record(book)
    expect((before is not None) == has_book, 'destination presence mismatch')
    if before:
        expect(before['nlink'] == nlink and before['sha256'] == hashlib.sha256(DATA).hexdigest(), f'destination {before}')
    expect((root / '.receipt.next').exists() == has_next, '.receipt.next presence mismatch')
    status, reports = recover(consumer, base, uuid, log, ev)
    expect(status == 0 and len(reports) == 2, f'reopen status {status}')
    for index, report in enumerate(reports):
        expect(report['status'] == 0 and report['refused'] == 0 and report['receipt_uncertain'] == 0 and
               report['pending'] == pending and report['states'] == states and
               report['cleaned'] == (cleaned if index == 0 else 0), f'recover pass {index}: {report}')
    expect(not (root / '.receipt.next').exists(), '.receipt.next survived reopen')
    after = file_record(book)
    if before:
        expect(after and (after['dev'], after['ino'], after['sha256']) == (before['dev'], before['ino'], before['sha256']),
               'published target changed or vanished')
        expect(after['nlink'] == (1 if cleaned else before['nlink']), f'nlink after recovery {after}')
    else:
        expect(after is None, 'destination appeared during recovery')
    expect(bool(tx_dirs(root)) == (has_tx and not cleaned), 'transaction directory state after recovery')
    if has_payload and not cleaned:
        expect((tx_dirs(root)[0] / 'payload').exists(), 'pending payload was removed')


def restore_private(path):
    for directory, _, _ in os.walk(path):
        try:
            os.chmod(directory, 0o700)
        except OSError:
            pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--consumer', required=True)
    parser.add_argument('--hookworker', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--core-sha', required=True)
    parser.add_argument('--tests-sha', required=True)
    parser.add_argument('--identity-file', action='append', default=[], metavar='LABEL=PATH',
                        help='file whose SHA-256 is recorded in the evidence identity')
    parser.add_argument('--compiler', default='')
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    consumer, hookworker = str(Path(args.consumer).resolve()), str(Path(args.hookworker).resolve())
    evidence = out / 'evidence'
    (evidence / 'cases').mkdir(parents=True, exist_ok=True)
    files = dict(consumer=args.consumer, hookworker=args.hookworker)
    files.update(item.split('=', 1) for item in args.identity_file)
    identity = dict(schema='exr-wc-evidence/1', core_sha=args.core_sha, tests_sha=args.tests_sha,
                    system=platform.system(), release=platform.release(), machine=platform.machine(),
                    python=platform.python_version(), uid=os.getuid(), euid=os.geteuid(),
                    compiler=args.compiler, worker_limit_seconds=LIMIT,
                    payload_sha256=hashlib.sha256(DATA).hexdigest(),
                    files={label: dict(path=path, sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())
                           for label, path in files.items()})
    (evidence / 'identity.json').write_text(json.dumps(identity, indent=2) + '\n')
    results = []
    for name in ALL:
        base = Path(tempfile.mkdtemp(prefix=f'wc-{name[:2]}-'))
        log, started = [], time.monotonic()
        ev = dict(name=name, phases=[], processes=[], snapshots=[], exception=None)
        try:
            if name == '06-cross-process-lock':
                case_cross_process(consumer, base, log, ev)
            elif name == '13-real-eacces-recovered':
                case_eacces(consumer, base, log, ev)
            elif name in KILL:
                case_kill(name, hookworker, consumer, base, log, ev)
            else:
                case_in_process(name, consumer, base, log, ev)
            passed, detail = True, ''
        except Exception as error:  # every case must leave a record
            passed, detail = False, f'{type(error).__name__}: {error}'
            ev['exception'] = detail
            try:
                snapshot(base, 'at_exception', ev)
            except Exception as snap_error:
                ev['snapshot_error'] = repr(snap_error)
        ev['seconds'] = round(time.monotonic() - started, 3)
        (evidence / 'cases' / f'{name}.json').write_text(json.dumps(ev, indent=1) + '\n')
        results.append(dict(name=name, passed=passed, detail=detail, seconds=round(time.monotonic() - started, 3), log=log))
        print(('PASS ' if passed else 'FAIL ') + name + (f' -- {detail}' if detail else ''), flush=True)
        if not passed:
            for line in log[-20:]:
                print(f'  | {line}', flush=True)
        restore_private(base)
        shutil.rmtree(base, ignore_errors=True)
    names = [r['name'] for r in results]
    summary = dict(core_sha=args.core_sha, tests_sha=args.tests_sha, system=platform.system(),
                   machine=platform.machine(), euid=os.geteuid(), total=len(results),
                   passed=sum(r['passed'] for r in results), names=names,
                   failed=[r['name'] for r in results if not r['passed']],
                   complete=sorted(names) == ALL and len(ALL) == 30)
    (out / 'results.json').write_text(json.dumps(dict(summary=summary, cases=results), indent=2) + '\n')
    (evidence / 'manifest.json').write_text(json.dumps(dict(
        schema='exr-wc-evidence/1', names=names, complete=summary['complete'],
        case_files={n: hashlib.sha256((evidence / 'cases' / f'{n}.json').read_bytes()).hexdigest() for n in names}),
        indent=2) + '\n')
    print('MANAGED-CLEANUP-RESULT ' + json.dumps(summary), flush=True)
    return 0 if summary['complete'] and summary['passed'] == 30 else 1


if __name__ == '__main__':
    sys.exit(main())
