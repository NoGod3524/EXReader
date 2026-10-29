#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Bounded loopback event collection and independent Actions-only native audit."""
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import math
import os
from pathlib import Path
import plistlib
import re
import resource
import secrets
import shutil
import signal
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from prepare import ROOT, OUT, BASE, BRANCH, PACKAGE, PATHS, HOSTS, FORMAL, FORMAL_SHA, BOOK_SHA, CLASS, CASES, ATS, generated, require

REPO = 'NoGod3524/EXReader'
RUNTIME = 'com.apple.CoreSimulator.SimRuntime.iOS-26-2'
DEVICE = 'com.apple.CoreSimulator.SimDeviceType.iPhone-SE-3rd-generation'
FIELDS = ('seq', 'tick', 'kind', 'owner', 'op', 'parent', 'a', 'b', 'c')
KINDS = set(range(0, 7)) | set(range(10, 28)) | {31, 40, 41, 42, 43}
CAP = 64 * 1024 ** 2
SELF_CHECKS = {k: True for k in ('append_order_no_overwrite', 'overflow_loss', 'try_lock_loss',
    'cutoff_writer_handshake', 'closed_equal_tick_refused', 'sealed_prefix_stable')}
COMMANDS = []
RESOURCE_ROOTS = []
WORK_ROOTS = []
EVIDENCE_BYTES = 1536 * 1024 ** 2
EVIDENCE_ENTRIES = 16000
DEADLINE = time.monotonic() + (720 if len(sys.argv) == 2 and sys.argv[1] == 'audit' else 55 * 60)


def check_time():
    require(time.monotonic() < DEADLINE, 'bounded job deadline exhausted')


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('wb') as stream:
        stream.write(encoded(value) + b'\n'); stream.flush(); os.fsync(stream.fileno())


def digest(path):
    sha = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 ** 2), b''):
            check_time(); sha.update(block)
    return sha.hexdigest()


def canonical(name):
    return unicodedata.normalize('NFC', name).casefold()


def names_checked(entries):
    seen, explicit = {}, set()
    for name, directory in entries:
        require(name and '\\' not in name and not any(ord(c) < 32 or ord(c) == 127 for c in name), 'unsafe member name')
        require(not name.endswith('//') and (directory or not name.endswith('/')), 'member trailing separator differs')
        parts = (name[:-1] if name.endswith('/') else name).split('/')
        require(all(p not in ('', '.', '..') and ':' not in p for p in parts), 'unsafe member path')
        key = canonical('/'.join(parts))
        require(key not in explicit, 'duplicate/case/Unicode member')
        explicit.add(key)
        for i in range(1, len(parts) + 1):
            spelling = '/'.join(parts[:i]); kind = 'dir' if i < len(parts) or directory else 'file'
            key = canonical(spelling)
            require(key not in seen or seen[key] == (spelling, kind), 'implicit directory/member alias')
            seen[key] = (spelling, kind)


def scan(folder, ceiling=2 * 1024 ** 3, partial=None):
    require(folder.is_dir() and not folder.is_symlink(), 'required plain directory missing')
    rows, entries, total = {}, [], 0
    pending = [folder]
    try:
        while pending:
            with os.scandir(pending.pop()) as children:
                for child in children:
                    check_time(); path = Path(child.path); info = child.stat(follow_symlinks=False)
                    mode = info.st_mode
                    require(stat.S_ISREG(mode) or stat.S_ISDIR(mode), 'link/special output refused')
                    name = path.relative_to(folder).as_posix()
                    entries.append((name, stat.S_ISDIR(mode)))
                    require(len(entries) <= 20000, '20000-entry ceiling exceeded')
                    if stat.S_ISDIR(mode): pending.append(path)
                    else:
                        total += info.st_size
                        require(total <= ceiling, 'cumulative output ceiling exceeded')
                        rows[name] = {'bytes': info.st_size, 'sha256': digest(path)}
        names_checked(entries)
    except Exception as error:
        if partial is not None:
            save(partial, {'complete': False, 'problem': str(error), 'bytes_seen': total,
                           'entries_seen': entries, 'files_hashed': rows})
        raise
    return rows


def readonly(folder):
    # Only authenticated, already type/alias/bound-checked extraction is frozen.
    for path in folder.rglob('*'): path.chmod(0o500 if path.is_dir() else 0o400)
    folder.chmod(0o500)


def writable_copy(reference, work, before):
    shutil.copytree(reference, work)
    for path in work.rglob('*'): path.chmod(0o700 if path.is_dir() else 0o600)
    work.chmod(0o700)
    require(scan(work) == before, 'working copy differs before parsing')
    for name in before:
        a, b = (reference / name).stat(), (work / name).stat()
        require((a.st_dev, a.st_ino) != (b.st_dev, b.st_ino) and b.st_nlink == 1, 'working copy shares writable inode')


def size_bound(folder, ceiling, count_limit):
    """Incremental metadata-only live guard, no rglob list or content parsing."""
    count = total = 0; pending = [folder]
    while pending:
        current = pending.pop()
        if not current.exists(): continue
        try: children = os.scandir(current)
        except FileNotFoundError: continue
        with children:
            for child in children:
                check_time(); count += 1
                require(count <= count_limit, 'live cumulative entry ceiling')
                try: info = child.stat(follow_symlinks=False)
                except FileNotFoundError: continue  # atomic parser rename; final scan remains strict
                require(stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode), 'live link/special output refused')
                if stat.S_ISDIR(info.st_mode): pending.append(Path(child.path))
                else:
                    total += info.st_size
                    require(total <= ceiling, 'live cumulative byte ceiling')
    return count, total


def unzip(path, target):
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        require(len(infos) <= 20000 and sum(i.file_size for i in infos) <= 2 * 1024 ** 3, 'ZIP size/count ceiling')
        names_checked([(i.filename, i.is_dir()) for i in infos])
        for item in infos:
            require(item.filename == item.orig_filename and stat.S_IFMT(item.external_attr >> 16) in
                    (0, stat.S_IFDIR if item.is_dir() else stat.S_IFREG), 'ZIP link/type/name refused')
        target.mkdir(mode=0o700)
        for item in infos:
            check_time()
            dest = target / item.filename
            if item.is_dir():
                dest.mkdir(parents=True, exist_ok=True); continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            size = 0
            with archive.open(item) as src, dest.open('xb') as out:
                for block in iter(lambda: src.read(1024 ** 2), b''):
                    check_time(); size += len(block)
                    require(size <= item.file_size, 'ZIP stream exceeds declared size'); out.write(block)
            require(size == item.file_size, 'ZIP stream size differs')


def command(argv, output, timeout=180, limit=CAP, allow_failure=False, env=None, watch=None):
    check_time(); output.parent.mkdir(parents=True, exist_ok=True)
    stderr = output.with_name(output.name + '.stderr')
    record = {'argv': list(map(str, argv)), 'output': str(output), 'started': time.monotonic()}
    COMMANDS.append(record)
    process = None; next_monitor = 0
    try:
        # Do not use preexec_fn after the HTTP receiver thread has started.
        # This fixed stdlib-only child sets its own limit after exec, then execs
        # the recorded fixed argv. No downloaded script or shell is evaluated.
        launcher = [sys.executable, '-c', 'import os,resource,sys; n=int(sys.argv[1]); '
            'resource.setrlimit(resource.RLIMIT_FSIZE,(n,n)); os.execvp(sys.argv[2],sys.argv[2:])',
            str(limit), *record['argv']]
        record['launcher_argv'] = launcher
        with output.open('wb') as stdout, stderr.open('wb') as err:
            process = subprocess.Popen(launcher, cwd=ROOT, env=env, stdout=stdout, stderr=err, start_new_session=True)
            while True:
                check_time()
                require(time.monotonic() - record['started'] < timeout, 'fixed command timeout')
                require(output.stat().st_size <= limit and stderr.stat().st_size <= limit, 'command output ceiling')
                if time.monotonic() >= next_monitor:
                    monitor_start = time.monotonic()
                    # 1.5GiB/16000 per evidence root leaves headroom for the
                    # 2GiB/20000 authenticated ZIP admission. Parser copies are
                    # separately bounded; total monitored working data <=6GiB.
                    total_bytes = total_entries = 0
                    roots = list(RESOURCE_ROOTS)
                    for root in roots:
                        count, size = size_bound(root, EVIDENCE_BYTES, EVIDENCE_ENTRIES)
                        total_bytes += size; total_entries += count
                    for root in WORK_ROOTS:
                        count, size = size_bound(root, 4 * 1024 ** 3, 40000)
                        total_bytes += size; total_entries += count; roots.append(root)
                    extras = [] if watch is None else ([watch] if isinstance(watch, Path) else list(watch))
                    for root in extras:
                        if any(root == p or p in root.parents for p in roots): continue
                        count, size = size_bound(root, 2 * 1024 ** 3, 20000)
                        total_bytes += size; total_entries += count; roots.append(root)
                    require(total_bytes <= 6 * 1024 ** 3 and total_entries <= 60000, 'live aggregate working ceiling')
                    record['monitor_seconds'] = record.get('monitor_seconds', 0) + time.monotonic() - monitor_start
                    next_monitor = time.monotonic() + 1
                code = process.poll()
                if code is not None:
                    record['exit_code'] = code
                    require(output.stat().st_size <= limit and stderr.stat().st_size <= limit, 'completed output ceiling')
                    require(code == 0 or allow_failure, 'command failed: ' + str(argv[:4]) + ' exit=' + str(code))
                    return code
                time.sleep(0.2)
    except Exception as error:
        record['problem'] = type(error).__name__ + ': ' + str(error); raise
    finally:
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL); process.wait()
        record['finished'] = time.monotonic()
        save(output.parent / 'commands.json', COMMANDS)


def text_command(argv, output, **kwargs):
    command(argv, output, **kwargs)
    return output.read_text().strip()


def api(endpoint, output):
    return json.loads(text_command(['gh', 'api', 'repos/' + REPO + '/' + endpoint], output))


def uint(value):
    return type(value) is int and 0 <= value < 2 ** 64


def frame(value, expected, previous=None):
    require(value['schema'] == 1 and value['nonce'] == expected['nonce'] and value['case'] == expected['case']
            and value['source_sha'] == expected['source_sha'] and value['sdk_version'] == '3.42.0', 'frame identity differs')
    require(type(value['pid']) is int and 0 < value['pid'] < 2 ** 31
            and re.fullmatch(r'[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}', value['simulator_udid']) is not None, 'app process/device domain missing')
    clock = value['clock']
    require(clock['name'] == 'mach_absolute_time' and type(clock['numer']) is type(clock['denom']) is int
            and 0 < clock['numer'] < 2 ** 32 and 0 < clock['denom'] < 2 ** 32, 'clock domain differs')
    require('identity_error' not in value and all(value[k] == expected[k] for k in
            ('executable_sha256', 'runtime_sha256', 'fixture_sha256')), 'app self-reported built identity differs')
    events = value['events']; require(isinstance(events, list) and 0 < len(events) <= 512, 'empty/unbounded event prefix')
    chain = bytes(32)
    for i, event in enumerate(events):
        require(set(event) == set(FIELDS) and event['seq'] == i and event['kind'] in KINDS
                and all(uint(event[k]) for k in FIELDS[:6]) and event['tick'] > 0
                and all(type(event[k]) is int and -(2 ** 63) <= event[k] < 2 ** 63 for k in FIELDS[6:]), 'invalid fixed record')
        require(event['op'] <= 128 and event['parent'] <= 128, 'operation ceiling')
        chain = hashlib.sha256(chain + struct.pack('>6Q3q', *(event[k] for k in FIELDS))).digest()
    require(events[0]['kind'] == 0 and len({e['owner'] for e in events if e['owner']}) <= 32, 'startup/owner admission differs')
    require(value['head_sha256'] == chain.hex(), 'event chain differs')
    stats = value['stats']
    require(all(uint(stats[k]) for k in ('lost', 'operations', 'cutoff', 'outside_calls', 'append_ticks_total', 'append_ticks_max'))
            and type(stats['sealed']) is bool and stats['operations'] <= 128, 'invalid recorder counters')
    require(stats['sealed'] == (stats['cutoff'] > 0), 'cutoff/admission differs')
    transport = value['transport']
    require(set(transport) == {'request', 'serialization_ticks', 'payload_bytes'}
            and all(uint(transport[k]) for k in transport) and 1 <= transport['request'] <= 600
            and transport['payload_bytes'] <= 600 * 256 * 1024, 'transport counters/bounds differ')
    immutable = ('schema', 'nonce', 'case', 'source_sha', 'sdk_version', 'pid', 'simulator_udid', 'clock',
                 'executable_sha256', 'runtime_sha256', 'fixture_sha256', 'self_checks')
    if previous is not None:
        require(all(previous[k] == value[k] for k in immutable), 'frame identity changed')
        require(len(events) >= len(previous['events']) and events[:len(previous['events'])] == previous['events'], 'gap/rewritten prefix')
        require(stats['lost'] >= previous['stats']['lost'], 'loss counter regressed')
        require(transport['request'] >= previous['transport']['request'] and
                all(transport[k] >= previous['transport'][k] for k in ('serialization_ticks', 'payload_bytes')), 'transport counter regressed')
        if transport['request'] == previous['transport']['request']:
            require(value == previous, 'conflicting duplicate transport request')
        if previous['stats']['sealed']:
            require(stats['sealed'] and stats['cutoff'] == previous['stats']['cutoff']
                    and events == previous['events'], 'sealed prefix changed')
    return value


def complete(value, ui):
    require(value['stats']['sealed'] and value['stats']['lost'] == 0 and value['stats']['cutoff'] > 0, 'missing seal or event loss')
    require(ui['schema'] == 1 and ui['trial'] == value['case'] and ui['nonce'] == value['nonce']
            and ui['source_sha'] == value['source_sha'] and ui['simulator_udid'] == value['simulator_udid']
            and ui['clock'] == value['clock'] and ui['lost'] == 0, 'UI/app identity/clock/loss differs')
    require(all(uint(ui[k]) for k in ('started', 'finished', 'native_tap_calls', 'native_tap_started',
            'native_tap_returned', 'original_wait_started', 'original_wait_returned', 'lost'))
            and type(ui['original_assertion_returned']) is bool and isinstance(ui['predicates'], list)
            and len(ui['predicates']) <= 512, 'UI unsigned tick/counter domains differ')
    require(ui['product_accepted'] is False and type(ui['formal_credit']) is int and ui['formal_credit'] == 0 and ui['started'] > 0
            and ui['finished'] >= ui['started'] and value['stats']['cutoff'] >= ui['finished'], 'observation cutoff/scope differs')
    require(ui['started'] <= value['events'][0]['tick'] <= ui['finished']
            and value['events'][0]['tick'] < value['stats']['cutoff'], 'startup not inside original observation domain')
    require(ui['native_tap_calls'] in (0, 1), 'native tap retried')
    if value['case'] == CASES[0]:
        require(ui['native_tap_calls'] == 0 and ui['predicates'] == []
                and value['self_checks'] == SELF_CHECKS, 'preflight controls incomplete')
        require(not any(e['kind'] == 11 or (e['kind'] == 20 and e['a'] == 11) for e in value['events']), 'preflight primed Verify/bootstrap')


def response_state(last, ui, case, nonce):
    ready = last is not None and last['stats']['lost'] == 0
    if ready and case == CASES[0]: ready = last['self_checks'] == SELF_CHECKS
    sealed = False
    if last is not None and ui is not None:
        try: complete(last, ui); sealed = True
        except (ValueError, KeyError, TypeError): pass
    return {'nonce': nonce, 'ready': ready, 'sealed': sealed, 'seal_requested': ui is not None,
            'count': len(last['events']) if last else 0, 'head_sha256': last['head_sha256'] if last else ''}


def check_ack(ack, last, ui, case, nonce):
    require(ack == response_state(last, ui, case, nonce)
            and all(type(ack[k]) is bool for k in ('ready', 'sealed', 'seal_requested')), 'durable ACK state differs')


class Receiver:
    def __init__(self, folder, source, program):
        self.folder, self.source, self.program = folder, source, program
        self.secret = secrets.token_hex(32); self.trials = {}; self.total = 0
        self.folder.mkdir(parents=True, exist_ok=True)
        save(folder / 'identity.json', {'source_sha': source, 'secret_commitment': hashlib.sha256(self.secret.encode()).hexdigest(),
                                      'program': program, 'formal_credit': 0})

    def register(self, case, nonce, selected):
        require(case in CASES and nonce not in self.trials, 'trial registration differs')
        self.trials[nonce] = {'case': case, 'nonce': nonce, 'source_sha': self.source, **self.program,
                              'selected_destination': selected, 'requests': 0, 'last': None, 'ui': None,
                              'seal_requested': False, 'problems': []}
        save(self.folder / nonce / 'registration.json', {k: v for k, v in self.trials[nonce].items() if k not in ('last', 'ui')})

    def accept(self, path, raw):
        require(len(raw) <= 256 * 1024 and self.total + len(raw) <= CAP, 'receiver byte ceiling')
        value = json.loads(raw); nonce = value.get('nonce')
        require(nonce in self.trials, 'unregistered nonce')
        trial = self.trials[nonce]; trial['requests'] += 1
        require(trial['requests'] <= 640, 'receiver request ceiling')
        # Reserve the bounded ACK as well; total emitted request/ACK bytes stay
        # below 64MiB (registration/refusal metadata has a separate 1MiB reserve).
        require(self.total + len(raw) + 4096 <= CAP - 1024 ** 2, 'receiver durable-output ceiling')
        self.total += len(raw) + 4096
        target = self.folder / nonce / f'{trial["requests"]:04d}-{path}.json'
        with target.open('wb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        if path == 'snapshot':
            trial['last'] = frame(value, trial, trial['last'])
        elif path == 'seal':
            require(trial['ui'] is None or trial['ui'] == value['ui'], 'rewritten UI seal request')
            trial['ui'] = value['ui']; trial['seal_requested'] = True
        elif path != 'status':
            raise ValueError('unknown fixed endpoint')
        answer = response_state(trial['last'], trial['ui'], trial['case'], nonce)
        save(target.with_name(target.stem + '-ack.json'), answer)
        return answer


def server(receiver):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            self.connection.settimeout(2)
            try:
                require(self.client_address[0] == '127.0.0.1' and self.path in ('/snapshot', '/seal', '/status')
                        and 'Transfer-Encoding' not in self.headers and self.headers.get('Content-Type') == 'application/json', 'HTTP admission differs')
                size = int(self.headers.get('Content-Length', '-1')); require(0 < size <= 256 * 1024, 'request size differs')
                raw = self.rfile.read(size); require(len(raw) == size, 'short request')
                expected = hmac.new(receiver.secret.encode(), raw, hashlib.sha256).hexdigest()
                require(hmac.compare_digest(self.headers.get('X-Phase-Mac', ''), expected), 'request authentication differs')
                answer = encoded(receiver.accept(self.path[1:], raw))
                auth = hmac.new(receiver.secret.encode(), answer, hashlib.sha256).hexdigest()
                self.send_response(200); self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(answer))); self.send_header('X-Phase-Mac', auth)
                self.end_headers(); self.wfile.write(answer)
            except Exception as error:
                save(receiver.folder / 'receiver-refusal.json', {'problem': type(error).__name__ + ': ' + str(error)})
                self.send_response(400); self.send_header('Content-Length', '0'); self.end_headers()
    http = HTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start()
    return http, thread


def protocol_controls(output):
    import copy
    event = dict(zip(FIELDS, [0, 10, 0, 0, 0, 0, 0, 0, 0]))
    chain = hashlib.sha256(bytes(32) + struct.pack('>6Q3q', *(event[k] for k in FIELDS))).hexdigest()
    expected = {'nonce': 'a' * 32, 'case': CASES[1], 'source_sha': 'b' * 40,
                'executable_sha256': 'c' * 64, 'runtime_sha256': 'd' * 64, 'fixture_sha256': BOOK_SHA}
    value = dict(expected, schema=1, pid=1, simulator_udid='00000000-0000-0000-0000-000000000001',
        sdk_version='3.42.0', clock={'name': 'mach_absolute_time', 'numer': 1, 'denom': 1},
        events=[event], head_sha256=chain, self_checks={}, transport={'request': 1, 'serialization_ticks': 0, 'payload_bytes': 0},
        stats={'sealed': True, 'cutoff': 30, 'lost': 0, 'operations': 0, 'outside_calls': 0,
               'append_ticks_total': 0, 'append_ticks_max': 0})
    ui = {'schema': 1, 'trial': CASES[1], 'nonce': expected['nonce'], 'source_sha': expected['source_sha'],
          'simulator_udid': value['simulator_udid'], 'clock': value['clock'], 'lost': 0, 'product_accepted': False,
          'formal_credit': 0, 'started': 1, 'finished': 20, 'native_tap_calls': 0,
          'native_tap_started': 0, 'native_tap_returned': 0, 'original_wait_started': 0,
          'original_wait_returned': 0, 'original_assertion_returned': False, 'predicates': []}
    frame(value, expected); frame(value, expected, value); complete(value, ui)
    outcomes = {'valid_complete': True, 'exact_duplicate': True}
    changes = {
        'wrong_nonce': lambda x, y: x.update(nonce='f' * 32),
        'gap': lambda x, y: x['events'][0].update(seq=1),
        'conflicting_duplicate': lambda x, y: x['events'][0].update(a=1),
        'overflow_loss': lambda x, y: x['stats'].update(lost=1),
        'missing_seal': lambda x, y: x['stats'].update(sealed=False, cutoff=0),
        'wrong_chain': lambda x, y: x.update(head_sha256='0' * 64),
        'cutoff_before_ui': lambda x, y: x['stats'].update(cutoff=19),
        'cutoff_equal_startup': lambda x, y: (x['stats'].update(cutoff=10), y.update(finished=10)),
        'boolean_ui_tick': lambda x, y: y.update(started=True),
        'boolean_transport_counter': lambda x, y: x['transport'].update(request=True),
        'transport_request_limit': lambda x, y: x['transport'].update(request=601),
        'clock_mismatch': lambda x, y: y.update(clock={'name': 'wall_clock', 'numer': 1, 'denom': 1})}
    for name, change in changes.items():
        candidate, receipt = copy.deepcopy(value), copy.deepcopy(ui); change(candidate, receipt)
        if name == 'conflicting_duplicate':
            candidate['head_sha256'] = hashlib.sha256(bytes(32) + struct.pack('>6Q3q',
                *(candidate['events'][0][k] for k in FIELDS))).hexdigest()
        try: frame(candidate, expected, value if name == 'conflicting_duplicate' else None); complete(candidate, receipt)
        except (ValueError, KeyError, TypeError): outcomes[name] = True
        else: outcomes[name] = False
    for field in ('ready', 'sealed', 'seal_requested', 'count', 'head_sha256'):
        ack = response_state(value, None, CASES[1], expected['nonce'])
        ack[field] = not ack[field] if type(ack[field]) is bool else 2 if field == 'count' else 'f' * 64
        try: check_ack(ack, value, None, CASES[1], expected['nonce'])
        except ValueError: outcomes['altered_ack_' + field] = True
        else: outcomes['altered_ack_' + field] = False
    for name, changes in [('counter_regression', {'request': 2, 'serialization_ticks': 9, 'payload_bytes': 9}),
                          ('request_regression', {'request': 1, 'serialization_ticks': 20, 'payload_bytes': 20})]:
        prior = copy.deepcopy(value); prior['transport'] = {'request': 2, 'serialization_ticks': 10, 'payload_bytes': 10}
        candidate = copy.deepcopy(value); candidate['transport'] = changes
        try: frame(candidate, expected, prior)
        except ValueError: outcomes[name] = True
        else: outcomes[name] = False
    final_ui = {'seal_request_accepted': True, 'seal_observed': True, 'capture_finalization_seconds': 1.0, 'capture_problems': []}
    final_receipt(final_ui)
    for name, field, bad in [('seal_flag_integer', 'seal_observed', 1), ('seal_flag_string', 'seal_request_accepted', 'true'),
            ('elapsed_negative', 'capture_finalization_seconds', -1), ('elapsed_boolean', 'capture_finalization_seconds', True),
            ('elapsed_infinite', 'capture_finalization_seconds', float('inf')), ('elapsed_nan', 'capture_finalization_seconds', float('nan')),
            ('elapsed_over_limit', 'capture_finalization_seconds', 10.01)]:
        candidate = dict(final_ui); candidate[field] = bad
        try: final_receipt(candidate)
        except ValueError: outcomes[name] = True
        else: outcomes[name] = False
    for name, filename, ordinal in [('ordinal_gap', '0003-snapshot.json', 2), ('ordinal_duplicate', '0001-status.json', 2),
                                    ('ordinal_limit', '0641-status.json', 641)]:
        try: request_ordinal(filename, ordinal)
        except ValueError: outcomes[name] = True
        else: outcomes[name] = False
    def model(path, busy=0):
        rows = []; changed = 0
        for kind in path:
            e = dict(zip(FIELDS, [len(rows), 10 + len(rows), kind, 11, 1, 0, 0, 0, 0]))
            if kind == 20: e['a'] = 100
            elif kind == 11: e.update(a=7, c=22)
            elif kind == 12: e['a'] = busy
            elif kind == 14: e.update(a=changed, b=1 - changed); changed += 1
            elif kind == 43: e['a'] = 7
            elif kind == 31: e.update(owner=22, a=1)
            rows.append(e)
        return rows
    paths = [[20, 11, 12, 14, 40, 15, 43, 16, 17, 18, 14], [20, 11, 12, 13],
             [20, 11, 12, 14, 40, 15, 41, 19, 14, 31], [20, 11, 12, 14, 40, 15, 43, 16, 41, 19, 14, 31]]
    for index, path in enumerate(paths):
        rows = model(path, 1 if index == 1 else 0)
        for length in range(1, len(rows) + 1): operations_of(rows[:length])
    outcomes['all_model_branch_prefixes'] = True
    valid = model(paths[0])
    for kind, a, b in [(20, 11, 0), (21, 0, 0), (22, 1, 1), (23, 0, 0), (24, 0, 0),
                       (25, 1, 1), (26, 0, 0), (31, 12, 0), (27, 0, 0)]:
        valid.append(dict(zip(FIELDS, [len(valid), 10 + len(valid), kind, 22, 2, 1 if kind == 20 else 0, a, b, 0])))
    for length in range(1, len(valid) + 1): operations_of(valid[:length])
    outcomes['model_bootstrap_parent_positive'] = True
    variants = {'dropped_model_phase': lambda rows: rows.pop(2),
        'duplicate_model_phase': lambda rows: rows.insert(5, copy.deepcopy(rows[5])),
        'reordered_model_phase': lambda rows: (rows.__setitem__(6, copy.deepcopy(rows[7])), rows.__setitem__(7, copy.deepcopy(valid[6]))),
        'wrong_catalog_identity': lambda rows: rows[6].update(a=8),
        'wrong_model_busy_value': lambda rows: rows[2].update(a=2),
        'wrong_parent': lambda rows: rows[11].update(parent=99),
        'wrong_owner': lambda rows: rows[14].update(owner=99),
        'wrong_publication_class': lambda rows: rows[-2].update(a=4),
        'wrong_metadata_result': lambda rows: rows[15].update(a=2)}
    for name, mutate in variants.items():
        rows = copy.deepcopy(valid); mutate(rows)
        try: operations_of(rows)
        except (ValueError, KeyError, IndexError): outcomes[name] = True
        else: outcomes[name] = False
    save(output, outcomes); require(all(outcomes.values()), 'transport negative control admitted')


def native_cases(raw):
    value = json.loads(raw); result = []
    def walk(node, ancestry):
        labels = ancestry + [str(node.get('name', '')), str(node.get('nodeIdentifier', ''))]
        if node.get('nodeType') == 'Test Case':
            require(any(CLASS in s for s in labels), 'wrong native class')
            names = re.findall(r'\btest[0-9A-Za-z_]+\b', node.get('name') or node.get('nodeIdentifier', ''))
            require(len(names) == 1 and names[0] in CASES, 'unexpected selected native method')
            result.append({'name': names[0], 'result': node['result'], 'duration': node.get('duration')})
        for child in node.get('children', []): walk(child, labels)
    require(isinstance(value.get('testNodes'), list), 'native tree missing')
    for node in value['testNodes']: walk(node, [])
    return result


def parse_bundle(reference, output, case):
    output.mkdir(parents=True, exist_ok=True)
    before = scan(reference, partial=output / 'reference-before-partial.json'); save(output / 'reference-before.json', before)
    readonly(reference)
    with tempfile.TemporaryDirectory(prefix='exr-phase-parser-') as temporary:
        work = Path(temporary) / 'working.xcresult'
        writable_copy(reference, work, before)
        operations = [(['xcrun', 'xcresulttool', 'get', 'test-results', 'tests', '--path', work, '--format', 'json'], 'native-tests'),
                      (['xcrun', 'xcresulttool', 'export', 'attachments', '--path', work, '--output-path', output / 'attachments'], 'attachments')]
        problems = []
        for argv, name in operations:
            prior = scan(work, partial=output / (name + '-before-partial.json')); save(output / (name + '-working-before.json'), prior)
            try:
                command(argv, output / (name + '.stdout'), watch=[Path(temporary), output / 'attachments'])
            except Exception as error: problems.append(name + ': ' + str(error))
            finally:
                try:
                    after = scan(work, partial=output / (name + '-after-partial.json')); save(output / (name + '-working-after.json'), after)
                    save(output / (name + '-working-diff.json'), {'added': {p: after[p] for p in after.keys() - prior.keys()},
                        'removed': {p: prior[p] for p in prior.keys() - after.keys()},
                        'changed': {p: {'before': prior[p], 'after': after[p]} for p in prior.keys() & after.keys() if prior[p] != after[p]}})
                except Exception as error: problems.append(name + ' post inventory: ' + str(error))
                save(output / 'parser-problems.json', problems)
        after_reference = scan(reference, partial=output / 'reference-after-partial.json'); save(output / 'reference-after.json', after_reference)
        require(after_reference == before, 'untouched original xcresult changed')
        # Preserve a native observation even if the later attachment parser or
        # completeness guard refuses. It never sets capture_complete by itself.
        try:
            observed = native_cases((output / 'native-tests.stdout').read_bytes())
            require(len(observed) == 1 and observed[0]['name'] == case and observed[0]['result'] in ('Passed', 'Failed'), 'partial native selection differs')
            save(output / 'partial-native-observation.json', observed[0])
        except Exception as error: problems.append('native observation: ' + str(error))
        require(not problems, 'fixed parser/inventory failure: ' + str(problems))
    cases = native_cases((output / 'native-tests.stdout').read_bytes())
    require(len(cases) == 1 and cases[0]['name'] == case and cases[0]['result'] in ('Passed', 'Failed'), 'missing/skipped native case')
    attachments = output / 'attachments'; scan(attachments, 512 * 1024 ** 2)
    manifest = json.loads((attachments / 'manifest.json').read_text()); receipt = None
    for group in manifest:
        require(case in (group.get('testIdentifier') or group.get('testName', '')), 'attachment owner differs')
        for item in group['attachments']:
            if not item['suggestedHumanReadableName'].startswith('verify-phase-ui-receipt-'): continue
            filename = item['exportedFileName']
            require(Path(filename).name == filename and receipt is None, 'duplicate/unsafe UI receipt')
            raw = (attachments / filename).read_bytes(); require(0 < len(raw) <= 256 * 1024, 'UI receipt bound')
            receipt = json.loads(raw)
    require(receipt is not None and receipt['trial'] == case, 'original UI timing receipt missing')
    return cases[0], receipt


def request_ordinal(filename, ordinal):
    require(re.fullmatch(r'[0-9]{4}-(snapshot|seal|status)\.json', filename) is not None
            and int(filename[:4]) == ordinal and ordinal <= 640, 'retained request order/count differs')


def final_receipt(ui):
    seconds = ui['capture_finalization_seconds']
    require(ui['seal_request_accepted'] is True and ui['seal_observed'] is True
            and type(seconds) in (int, float) and math.isfinite(seconds) and 0 <= seconds <= 10
            and ui['capture_problems'] == [], 'UI capture finalization incomplete')


def replay_transport(folder, expected, ui):
    require(re.fullmatch(r'[a-f0-9]{32}', expected['nonce']) and folder.name == expected['nonce'], 'trial path identity differs')
    last = None; seal_ui = None; accepted = []; ordinal = 0
    for path in sorted(folder.glob('[0-9][0-9][0-9][0-9]-*.json')):
        if path.stem.endswith('-ack'): continue
        ordinal += 1
        request_ordinal(path.name, ordinal)
        raw = path.read_bytes(); require(len(raw) <= 256 * 1024, 'retained request bound')
        value = json.loads(raw)
        endpoint = path.stem.split('-', 1)[1]
        require(value['nonce'] == expected['nonce'], 'retained nonce changed')
        if endpoint == 'snapshot': last = frame(value, expected, last)
        elif endpoint == 'seal':
            require(seal_ui is None or seal_ui == value['ui'], 'retained UI seal changed'); seal_ui = value['ui']
        elif endpoint != 'status': raise ValueError('unexpected retained endpoint')
        ack = json.loads(path.with_name(path.stem + '-ack.json').read_text())
        check_ack(ack, last, seal_ui, expected['case'], expected['nonce'])
        accepted.append(ack)
    require(last is not None and seal_ui is not None and any(a['sealed'] for a in accepted), 'final app seal/ACK missing')
    complete(last, seal_ui)
    final_receipt(ui)
    require({k: ui[k] for k in seal_ui if k != 'finished'} == {k: v for k, v in seal_ui.items() if k != 'finished'}, 'native UI receipt differs from seal request')
    require(ui['finished'] == seal_ui['finished'], 'UI observation cutoff changed')
    return last


def operations_of(inside):
    definitions = [e for e in inside if e['kind'] == 20]
    require(len({e['op'] for e in definitions}) == len(definitions)
            and all(e['op'] and e['owner'] and e['a'] in set(range(1, 12)) | {100, 101} for e in definitions), 'operation definitions differ')
    operations = {str(e['op']): {'kind': e['a'], 'owner': e['owner'], 'parent': e['parent'], 'events': []} for e in definitions}
    for event in inside:
        if event['op']:
            key = str(event['op']); require(key in operations, 'event references missing operation')
            report_error = event['kind'] == 31 and operations[key]['kind'] == 100 and any(
                e['kind'] == 11 and e['op'] == event['op'] and e['c'] == event['owner'] for e in inside)
            require(event['owner'] == operations[key]['owner'] or report_error, 'operation owner changed')
            operations[key]['events'].append(event)
        if event['kind'] == 10:
            require(event['a'] in (0, 1) and event['b'] > 0 and event['op'] == 0, 'panel gate domain differs')
    success = [20, 11, 12, 14, 40, 15, 43, 16, 17, 18, 14]
    for key, operation in operations.items():
        parent = operation['parent']; kind = operation['kind']
        if parent:
            require(str(parent) in operations and parent < int(key), 'missing/future operation parent')
            ancestor = operations[str(parent)]
            require((kind == 5 and ancestor['kind'] == 101) or
                    (kind == 11 and ancestor['kind'] == 100), 'invented operation causal parent')
            required_parent = [20, 42] if kind == 5 else success
            require([e['kind'] for e in ancestor['events']] == required_parent
                    and ancestor['events'][-1]['seq'] < operation['events'][0]['seq'], 'child before actual parent phase')
            if kind == 5: require(operation['owner'] == ancestor['owner'], 'selection owner differs')
            else: require(operation['owner'] == ancestor['events'][1]['c'], 'bootstrap organization differs')
        else: require(kind not in (5, 11), 'book selection/bootstrap parent missing')
        observed = operation['events']; kinds = [e['kind'] for e in observed]
        if kind <= 11:
            common = [20, 21, 22, 23, 24, 25, 26]
            worker = [e for e in observed if e['kind'] == 24]
            require(len(worker) <= 1 and all(e['a'] in (0, 1) for e in worker), 'metadata result domain differs')
            suffixes = [[31, 27]]
            success_suffixes = [[27], [31, 27]] if kind == 1 else [[5 if kind == 2 else 6 if kind == 3 else 31, 27]]
            if not worker: suffixes += success_suffixes
            elif worker[0]['a'] == 0: suffixes = success_suffixes
            require(any(kinds == (common + suffix)[:len(kinds)] for suffix in suffixes), 'run phase order/gap differs')
            operation['pending_at_cutoff'] = 27 not in kinds
            for before_kind, after_kind, delta in ((21, 22, 1), (25, 26, -1)):
                before = [e for e in observed if e['kind'] == before_kind]
                after = [e for e in observed if e['kind'] == after_kind]
                require(all(e['a'] >= (1 if before_kind == 25 else 0) and e['b'] == int(e['a'] != 0) for e in before), 'queue/busy before domain differs')
                if after:
                    require(len(before) == len(after) == 1 and after[0]['a'] == before[0]['a'] + delta
                            and after[0]['a'] >= 0 and after[0]['b'] == int(after[0]['a'] != 0), 'queue/busy transition differs')
            for event in observed:
                if event['kind'] == 31:
                    allowed = {1} if worker[0]['a'] == 1 else {1: {2}, 4: {3}, 5: {4, 5}, 6: {6},
                        7: {7}, 8: {8}, 9: {9}, 10: {10}, 11: {11, 12}}.get(kind, set())
                    require(event['a'] in allowed, 'publication class differs from source operation/result')
                elif event['kind'] == 5: require(kind == 2 and event['a'] in (0, 1, 2) and 0 <= event['b'] <= 200 and event['c'] in (0, 1), 'group result domain differs')
                elif event['kind'] == 6: require(kind == 3 and 0 <= event['a'] <= 200, 'member result domain differs')
        elif kind == 100:
            busy = [e for e in observed if e['kind'] == 12]
            require(len(busy) <= 1 and all(e['a'] in (0, 1) for e in busy), 'model busy guard domain differs')
            normal = [success, [20, 11, 12, 14, 40, 15, 41, 19, 14, 31],
                      [20, 11, 12, 14, 40, 15, 43, 16, 41, 19, 14, 31]]
            choices = [[20, 11, 12, 13]] if busy and busy[0]['a'] == 1 else normal
            require(any(kinds == path[:len(kinds)] for path in choices), 'model phase order/gap/branch differs')
            entry = [e for e in observed if e['kind'] == 11]
            require(all(e['a'] > 0 and e['c'] > 0 for e in entry), 'activation fixture scalar differs')
            changes = [e for e in observed if e['kind'] == 14]
            require([(e['a'], e['b']) for e in changes] == [(0, 1), (1, 0)][:len(changes)], 'model busy transition differs')
            for event in observed:
                if event['kind'] == 43: require(event['a'] == entry[0]['a'], 'catalog identity differs from activation')
                if event['kind'] == 31: require(event['a'] == 1 and event['owner'] == entry[0]['c'], 'model error publication differs')
            operation['pending_at_cutoff'] = not (kinds == [20, 11, 12, 13] or kinds[-1] == 31) and not any(
                child['parent'] == int(key) and any(e['kind'] == 27 for e in child['events']) for child in operations.values())
        else:
            require(kinds == [20, 42][:len(kinds)] and all(e['a'] in (0, 1, 2) for e in observed if e['kind'] == 42), 'selection link differs')
            operation['pending_at_cutoff'] = 42 not in kinds
    return operations


def classify(value, ui, native):
    events = value['events']; cutoff = value['stats']['cutoff']
    inside = [e for e in events if e['tick'] < cutoff]
    result = {'case': value['case'], 'native_result': native['result'], 'capture_complete': True,
        'original_assertion_returned': ui['original_assertion_returned'], 'strict_within_60_seconds': False,
        'late_positive_predicate': False, 'native_tap_calls': ui['native_tap_calls'],
        'event_count': len(events), 'cutoff': cutoff, 'cutoff_exclusive': True, 'out_of_window_records': [e for e in events if e['tick'] >= cutoff],
        'recorder_stats': value['stats'], 'transport_stats': value['transport'],
        'app_self_reported_identity_only': True, 'installed_app_identity_verified': False,
        'product_accepted': False, 'formal_credit': 0, 'root_cause_proved': False}
    if value['case'] == CASES[0]:
        result['phase_outcome'] = 'transport_preflight'; return result
    require(any(e['kind'] == 2 and e['a'] == 0 for e in inside) and any(e['kind'] == 3 and e['a'] == 0 for e in inside)
            and any(e['kind'] == 4 and e['a'] == 0 for e in inside), 'fresh startup proof missing')
    require(any(e['kind'] == 5 and e['a'] == 1 and e['b'] == 0 and e['c'] == 0 for e in inside), 'initial tag groups not proven empty')
    observations = ui['observations']
    if ui['native_tap_calls']:
        require(observations['book_id'] == 'organization.book.epub:' + BOOK_SHA
                and observations['group_id'].startswith('organization.group.'), 'fixture selection differs')
        require(ui['native_tap_started'] <= ui['native_tap_returned'] <= ui['original_wait_started'], 'native action timing differs')
    previous = ui['original_wait_started']
    for predicate in ui['predicates']:
        require(uint(predicate['begin']) and uint(predicate['end']) and previous <= predicate['begin'] <= predicate['end'] <= ui['original_wait_returned'] <= ui['finished']
                and type(predicate['result']) is bool and type(predicate['message_truncated']) is bool
                and isinstance(predicate['message'], str) and len(predicate['message'].encode()) <= 130,
                'predicate timing/order differs')
        previous = predicate['end']
        if predicate['result']:
            require(not predicate['message_truncated'] and '原件验证完成' in predicate['message'], 'positive predicate text missing')
            seconds = (predicate['end'] - ui['native_tap_returned']) * ui['clock']['numer'] / ui['clock']['denom'] / 1e9
            result['first_positive_seconds_after_tap'] = seconds
            result['strict_within_60_seconds'] = seconds <= 60
            result['late_positive_predicate'] = seconds > 60
            break
    require(ui['original_assertion_returned'] == any(p['result'] for p in ui['predicates']), 'original predicate outcome differs')
    result['operations'] = operations_of(inside)
    if ui['native_tap_returned']:
        # Derived labels only. They never substitute for the original predicate
        # or make a late callback evidence of progress within the old window.
        scale = ui['clock']['numer'] / ui['clock']['denom'] / 1e9
        result['derived_event_timing'] = [{'seq': e['seq'],
            'seconds_after_tap_return': (e['tick'] - ui['native_tap_returned']) * scale,
            'before_tap_start': e['tick'] < ui['native_tap_started'],
            'within_action_start_through_return_plus_60': e['tick'] >= ui['native_tap_started']
                and (e['tick'] - ui['native_tap_returned']) * scale <= 60} for e in inside]
    result['panel_gates'] = [e for e in inside if e['kind'] == 10]
    result['publications'] = [e for e in inside if e['kind'] == 31]
    result['phase_outcome'] = ('non_reproduction_under_instrumentation' if ui['original_assertion_returned'] else
        'verify_handler_entry_not_observed_before_cutoff' if ui['native_tap_calls'] == 1 and not any(e['kind'] == 11 or (e['kind'] == 20 and e['a'] == 100) for e in inside) else
        'prefix_did_not_reach_verify' if not ui['native_tap_calls'] else 'failure_with_recorded_phases')
    return result


def built_identity(evidence):
    app = OUT / 'DerivedData/Build/Products/Debug-iphonesimulator/EXReaderHost.app'
    info = plistlib.loads((app / 'Info.plist').read_bytes())
    require(info['EXRSourceSHA'] == os.environ['GITHUB_SHA'] and info['EXRSDKVersion'] == '3.42.0'
            and info['EXRPageThemeEnabled'] is True and info['NSAppTransportSecurity'] == ATS, 'built diagnostic app identity differs')
    result = {'executable_sha256': digest(app / 'EXReaderHost'),
              'runtime_sha256': digest(app / 'Frameworks/libexreader.3.42.0.dylib'), 'fixture_sha256': digest(app / 'Sample.epub')}
    require(result['fixture_sha256'] == BOOK_SHA, 'built fixture differs')
    products = OUT / 'DerivedData/Build/Products/Debug-iphonesimulator'
    runner_infos = {}
    for path in products.glob('*UITests*Runner.app/**/Info.plist'):
        require(len(runner_infos) < 32 and path.stat().st_size <= 1024 ** 2, 'runner Info bound')
        runner_infos[path.relative_to(products).as_posix()] = plistlib.loads(path.read_bytes())
    save(evidence / 'built-test-runner-info.json', runner_infos)
    command(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', app, evidence / 'EXReaderHost.zip'], evidence / 'retain-built.stdout')
    save(evidence / 'built-identity.json', dict(result, zip_sha256=digest(evidence / 'EXReaderHost.zip'), installed_identity_verified=False))
    return result


def run_native():
    evidence = OUT / 'evidence'; evidence.mkdir(parents=True, exist_ok=True)
    RESOURCE_ROOTS.append(evidence)
    report = {'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
              'cases': [], 'problems': [], 'capture_complete': False, 'formal_credit': 0, 'product_accepted': False}
    http = None; created = []; receiver = None
    try:
        require(os.environ['GITHUB_RUN_ATTEMPT'] == '1' and os.environ['GITHUB_REF_NAME'] == BRANCH, 'wrong attempt/branch')
        command(['xcodebuild', '-version'], evidence / 'xcode-version.stdout')
        command(['xcrun', 'simctl', 'list', 'runtimes', '-j'], evidence / 'runtimes.stdout')
        protocol_controls(evidence / 'protocol-controls.json')
        first = text_command(['xcrun', 'simctl', 'create', 'EXR-phase-' + os.environ['GITHUB_RUN_ID'] + '-preflight', DEVICE, RUNTIME], evidence / 'create-preflight.stdout')
        require(re.fullmatch(r'[0-9A-Fa-f-]{36}', first), 'created device identity missing'); created.append(first)
        common = ['-project', str(OUT / 'generated/project/EXReaderHost.xcodeproj'), '-scheme', 'EXReaderHost-iOS',
            '-derivedDataPath', str(OUT / 'DerivedData'), 'EXR_SDK_DIR=' + str(ROOT / 'build/apple-sdk342/iphonesimulator/sdk'),
            'EXR_PRODUCTS_DIR=' + str(ROOT / 'build/apple-sdk342/iphonesimulator/products'), 'CODE_SIGNING_ALLOWED=NO']
        command(['xcodebuild', 'build-for-testing', *common, '-destination', 'platform=iOS Simulator,id=' + first],
                evidence / 'build.log', timeout=1800, limit=256 * 1024 ** 2)
        program = built_identity(evidence)
        receiver = Receiver(evidence / 'transport', report['source_sha'], program)
        print('::add-mask::' + receiver.secret, flush=True)
        http, thread = server(receiver)
        endpoint = 'http://127.0.0.1:' + str(http.server_address[1])
        private = OUT / 'private-transport.json'
        with private.open('x', opener=lambda path, flags: os.open(path, flags, 0o600)) as stream:
            json.dump({'endpoint': endpoint, 'secret': receiver.secret}, stream)
        for index, case in enumerate(CASES):
            if index == 0: device = first
            else:
                device = text_command(['xcrun', 'simctl', 'create', 'EXR-phase-' + os.environ['GITHUB_RUN_ID'] + '-' + str(index), DEVICE, RUNTIME], evidence / ('create-' + case + '.stdout'))
                require(re.fullmatch(r'[0-9A-Fa-f-]{36}', device), 'created device differs'); created.append(device)
            nonce = secrets.token_hex(16); receiver.register(case, nonce, device)
            env = dict(os.environ, TEST_RUNNER_EXR_PHASE_ENDPOINT=endpoint, TEST_RUNNER_EXR_PHASE_SECRET=receiver.secret,
                       TEST_RUNNER_EXR_PHASE_NONCE=nonce, TEST_RUNNER_EXR_PHASE_CASE=case,
                       TEST_RUNNER_EXR_PHASE_SOURCE=report['source_sha'])
            bundle = evidence / (case + '.xcresult')
            code = command(['xcodebuild', 'test-without-building', *common, '-destination', 'platform=iOS Simulator,id=' + device,
                '-resultBundlePath', bundle, '-parallel-testing-enabled', 'NO', '-test-timeouts-enabled', 'YES',
                '-default-test-execution-time-allowance', '300', '-maximum-test-execution-time-allowance', '600',
                '-only-testing:EXReaderHostUITests-iOS/' + CLASS + '/' + case], evidence / (case + '.log'),
                timeout=780, limit=256 * 1024 ** 2, allow_failure=True, env=env)
            trial = {'case': case, 'nonce': nonce, 'selected_device': device, 'xcodebuild_exit': code, 'capture_complete': False}
            try:
                native, ui = parse_bundle(bundle, evidence / ('parsed-' + case), case)
                trial.update(native_result=native['result'], ui=ui)
                expected = dict(program, nonce=nonce, case=case, source_sha=report['source_sha'])
                value = replay_transport(evidence / 'transport' / nonce, expected, ui)
                require((code == 0) == (native['result'] == 'Passed'), 'native return/result mismatch')
                trial.update(classify(value, ui, native))
                if index == 0: require(native['result'] == 'Passed', 'transport preflight native failure')
            except Exception as error:
                trial['problem'] = type(error).__name__ + ': ' + str(error)
                partial = evidence / ('parsed-' + case) / 'partial-native-observation.json'
                if partial.exists(): trial['partial_native_observation'] = json.loads(partial.read_text())
            report['cases'].append(trial); save(evidence / 'producer-report.json', report)
            command(['xcrun', 'simctl', 'shutdown', device], evidence / ('shutdown-' + case + '.stdout'), allow_failure=True)
            command(['xcrun', 'simctl', 'delete', device], evidence / ('delete-' + case + '.stdout'))
            created.remove(device)
            if index == 0 and not (trial['capture_complete'] and trial.get('native_result') == 'Passed' and 'problem' not in trial):
                raise ValueError('preflight incomplete; three prefixes not run')
        report['capture_complete'] = len(report['cases']) == 4 and all(t['capture_complete'] for t in report['cases'])
    except Exception as error:
        report['problems'].append(type(error).__name__ + ': ' + str(error))
    finally:
        if http is not None: http.shutdown(); http.server_close()
        for device in created:
            try:
                command(['xcrun', 'simctl', 'shutdown', device], evidence / ('cleanup-shutdown-' + device + '.stdout'), allow_failure=True)
                command(['xcrun', 'simctl', 'delete', device], evidence / ('cleanup-delete-' + device + '.stdout'), allow_failure=True)
            except Exception as error: report['problems'].append('owned device cleanup: ' + str(error))
        save(evidence / 'producer-report.json', report)
        try: size_bound(evidence, EVIDENCE_BYTES, EVIDENCE_ENTRIES)
        except Exception as error:
            report['capture_complete'] = False
            report['problems'].append('final evidence ceiling: ' + str(error)); save(evidence / 'producer-report.json', report)
        print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0 if report['capture_complete'] and not report['problems'] and all(t['native_result'] == 'Passed' for t in report['cases']) else 1


def verify_generated(evidence, guard, output):
    retained = evidence / 'generated'
    current = scan(retained)
    require({p: v['sha256'] for p, v in current.items()} == guard['generated'], 'generated bytes differ')
    for path, content in generated(guard['producer_workspace']).items():
        require((retained / path).read_text() == content, 'generated reverse-reconstruction differs: ' + path)
    project = retained / 'project/EXReaderHost.xcodeproj'
    raw = text_command(['plutil', '-convert', 'xml1', '-o', '-', project / 'project.pbxproj'], output / 'project-plutil.stdout')
    objects = plistlib.loads(raw.encode())['objects']
    producer = Path(guard['producer_workspace']); project_dir = producer / 'build/ios-verify-phase-probe/generated/project'
    baseline_sources = sorted((ROOT / 'examples/apple').glob('*.swift')) + [ROOT / 'bindings/swift/EXReader.swift']
    host_sources = {'../host/' + p.name if p.name in HOSTS else
                    os.path.relpath(producer / p.relative_to(ROOT), project_dir) for p in baseline_sources}
    host_sources.add('../host/AppPhaseRecorder.swift')
    for target_name, expected in [('EXReaderHostUITests-iOS', {'../ui/VerifyPhaseTests.swift'}),
                                  ('EXReaderHost-iOS', host_sources)]:
        targets = [(key, obj) for key, obj in objects.items() if obj.get('isa') == 'PBXNativeTarget' and obj.get('name') == target_name]
        require(len(targets) == 1, 'native target ambiguous')
        target_id, target = targets[0]
        phases = [objects[k] for k in target['buildPhases'] if objects[k]['isa'] == 'PBXSourcesBuildPhase']
        require(len(phases) == 1, 'native source phase differs')
        refs = [objects[objects[k]['fileRef']] for k in phases[0]['files']]
        paths = [ref['path'] for ref in refs]
        require(set(paths) == expected and len(paths) == len(expected)
                and all(ref['sourceTree'] == '<group>' for ref in refs), 'exact target source set/binding differs')
        configs = objects[target['buildConfigurationList']]['buildConfigurations']
        require(all(objects[k]['buildSettings']['SWIFT_VERSION'] == '5.0' and
                    objects[k]['buildSettings']['IPHONEOS_DEPLOYMENT_TARGET'] == '15.0' for k in configs), 'deployment/Swift settings changed')
        if target_name.endswith('UITests-iOS'):
            scheme = ET.fromstring((project / 'xcshareddata/xcschemes/EXReaderHost-iOS.xcscheme').read_text())
            refs = scheme.findall('.//TestableReference')
            require(len(refs) == 1 and refs[0].get('skipped', 'NO') == 'NO'
                    and refs[0].find('BuildableReference').get('BlueprintIdentifier') == target_id, 'selected scheme differs')
    for path in ('project/Info-iOS.plist', 'project/Info-macOS.plist', 'project/PhaseTests-Info.plist'):
        require(plistlib.loads((retained / path).read_bytes())['NSAppTransportSecurity'] == ATS, 'ATS scope differs')
    for name in ('Info-iOS.plist', 'Info-macOS.plist'):
        before = plistlib.loads((retained / 'project' / ('Before-' + name)).read_bytes())
        after = plistlib.loads((retained / 'project' / name).read_bytes())
        require(before == {'EXRSourceSHA': guard['source_sha'], 'EXRSDKVersion': '3.42.0', 'EXRPageThemeEnabled': True}
                and after == dict(before, NSAppTransportSecurity=ATS), 'generated plist delta exceeds ATS')


def audit():
    output = ROOT / 'build/ios-verify-phase-audit'; output.mkdir(parents=True, exist_ok=False)
    RESOURCE_ROOTS.append(output)
    summary = {'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
               'capture_complete': False, 'product_accepted': False, 'formal_credit': 0, 'root_cause_proved': False,
               'installed_app_identity_verified': False, 'trials': [], 'problems': []}
    try:
        require(summary['attempt'] == '1' and os.environ['GITHUB_REF_NAME'] == BRANCH, 'wrong audit attempt/branch')
        delta = text_command(['git', 'diff', '--name-status', BASE, 'HEAD'], output / 'source-delta.stdout').splitlines()
        require(sorted(delta) == sorted('A\t' + p for p in PATHS), 'audit five-path admission differs')
        jobs = api(f'actions/runs/{summary["run_id"]}/attempts/1/jobs?per_page=100', output / 'jobs.stdout')['jobs']
        producers = [j for j in jobs if j['name'] == 'Isolated transport preflight and three Verify prefixes']
        require(len(producers) == 1 and producers[0]['head_sha'] == summary['source_sha']
                and producers[0]['conclusion'] in ('success', 'failure'), 'producer identity/status differs')
        artifacts = api(f'actions/runs/{summary["run_id"]}/artifacts?per_page=100', output / 'artifacts.stdout')['artifacts']
        matches = [a for a in artifacts if a['name'] == 'ios-verify-phase-probe-' + summary['run_id'] + '-1']
        require(len(matches) == 1, 'original probe artifact missing/ambiguous'); item = matches[0]
        require(not item['expired'] and item['workflow_run']['head_sha'] == summary['source_sha']
                and str(item['workflow_run']['id']) == summary['run_id'] and 0 < item['size_in_bytes'] <= 2 * 1024 ** 3, 'original artifact identity differs')
        with tempfile.TemporaryDirectory(prefix='exr-phase-audit-') as temporary:
            temporary = Path(temporary); original = temporary / 'original.zip'
            WORK_ROOTS.append(temporary)
            command(['gh', 'api', f'repos/{REPO}/actions/artifacts/{item["id"]}/zip'], output / 'download.stdout',
                    limit=2 * 1024 ** 3)
            shutil.move(output / 'download.stdout', original)
            checksum = digest(original)
            require(original.stat().st_size == item['size_in_bytes'] and item['digest'] == 'sha256:' + checksum, 'original ZIP digest/size differs')
            summary['original_artifact'] = {'id': item['id'], 'bytes': item['size_in_bytes'], 'sha256': checksum}
            evidence = temporary / 'original'; unzip(original, evidence)
            size_bound(temporary, 4 * 1024 ** 3, 40000)
            original_inventory = scan(evidence); save(output / 'original-inventory.json', original_inventory)
            readonly(evidence); original.chmod(0o400)
            guard = json.loads((evidence / 'source-guard.json').read_text())
            require(all(guard[k] == summary[k] for k in ('source_sha', 'run_id', 'attempt')) and guard['base'] == BASE
                    and guard['paths'] == sorted(PATHS) and guard['existing_blobs_unchanged'] and guard['reverse_reconstruction_equal']
                    and guard['selected_cases'] == CASES and guard['formal_ui_sha256'] == FORMAL_SHA
                    and guard['package_files'] == {p: digest(ROOT / p) for p in PATHS}, 'producer source guard differs')
            sdk = guard['sdk_package_identity']; product = sdk['product']
            require(all(sdk[k] == summary[k] for k in ('source_sha', 'run_id', 'attempt'))
                    and sdk['target'] == 'iphonesimulator' and sdk['page_theme_enabled'] is True
                    and sdk['sdk_content_candidate'] == '8357eafa28423a7ab93ba08b823af80f01ad1505'
                    and sdk['sdk_content_paths'] == ['src', 'include', 'cmake', 'CMakeLists.txt', 'bindings']
                    and product['source_sha'] == summary['source_sha'] and product['sdk_version'] == '3.42.0'
                    and product['wave3_enabled'] and product['organization_enabled'] and product['selector_bytes_candidate']
                    and product['system_sqlite_fallback'] is False, 'frozen SDK package identity differs')
            command(['git', 'diff', '--exit-code', sdk['sdk_content_candidate'], 'HEAD', '--', *sdk['sdk_content_paths']],
                    output / 'sdk-source-equality.stdout')
            verify_generated(evidence, guard, output)
            scan(evidence / 'transport', CAP)
            saved_program = json.loads((evidence / 'built-identity.json').read_text())
            require(digest(evidence / 'EXReaderHost.zip') == saved_program['zip_sha256'], 'built program ZIP differs')
            app_dir = temporary / 'built'; unzip(evidence / 'EXReaderHost.zip', app_dir)
            size_bound(temporary, 4 * 1024 ** 3, 40000)
            app = app_dir / 'EXReaderHost.app'; info = plistlib.loads((app / 'Info.plist').read_bytes())
            require(info['EXRSourceSHA'] == summary['source_sha'] and info['EXRSDKVersion'] == '3.42.0'
                    and info['EXRPageThemeEnabled'] is True and info['NSAppTransportSecurity'] == ATS, 'built app identity differs')
            program = {'executable_sha256': digest(app / 'EXReaderHost'), 'runtime_sha256': digest(app / 'Frameworks/libexreader.3.42.0.dylib'),
                       'fixture_sha256': digest(app / 'Sample.epub')}
            require(all(saved_program[k] == v for k, v in program.items()) and program['fixture_sha256'] == BOOK_SHA, 'built components differ')
            for name, expected in guard['fixtures'].items():
                require(Path(name).name == name and name not in ('.', '..') and re.fullmatch(r'[a-f0-9]{64}', expected), 'fixture inventory path/hash differs')
                require(digest(app / name) == expected, 'built fixture differs')
            control = json.loads((evidence / 'protocol-controls.json').read_text())
            protocol_controls(output / 'replayed-protocol-controls.json')
            require(control == json.loads((output / 'replayed-protocol-controls.json').read_text()), 'protocol controls differ')
            reports = json.loads((evidence / 'producer-report.json').read_text())
            require(all(reports[k] == summary[k] for k in ('source_sha', 'run_id', 'attempt')), 'producer report identity differs')
            require(len(reports['cases']) <= 4 and [r['case'] for r in reports['cases']] == CASES[:len(reports['cases'])], 'planned trial order/duplicate differs')
            for case in CASES:
                trial = {'case': case, 'capture_complete': False}
                try:
                    rows = [t for t in reports['cases'] if t['case'] == case]; require(len(rows) == 1, 'planned native case missing')
                    row = rows[0]
                    require(re.fullmatch(r'[a-f0-9]{32}', row['nonce']), 'trial nonce path differs')
                    native, ui = parse_bundle(evidence / (case + '.xcresult'), output / case, case)
                    trial.update(native_result=native['result'], ui=ui)
                    expected = dict(program, nonce=row['nonce'], case=case, source_sha=summary['source_sha'])
                    registration = json.loads((evidence / 'transport' / row['nonce'] / 'registration.json').read_text())
                    require(all(registration[k] == v for k, v in expected.items()) and registration['selected_destination'] == row['selected_device'], 'registration differs')
                    value = replay_transport(evidence / 'transport' / row['nonce'], expected, ui)
                    replayed = classify(value, ui, native); trial.update(replayed)
                    require(all(row[k] == v for k, v in replayed.items()), 'producer trial summary differs from independent replay')
                    require((row['xcodebuild_exit'] == 0) == (native['result'] == 'Passed'), 'original native status differs')
                except Exception as error:
                    trial['capture_complete'] = False
                    trial['problem'] = type(error).__name__ + ': ' + str(error)
                    summary['problems'].append(case + ': ' + trial['problem'])
                    partial = output / case / 'partial-native-observation.json'
                    if partial.exists(): trial['partial_native_observation'] = json.loads(partial.read_text())
                finally:
                    summary['trials'].append(trial); save(output / 'summary.json', summary)
            groups = [r['ui']['observations']['group_id'] for r in summary['trials'] if r['case'] != CASES[0] and r.get('ui', {}).get('native_tap_calls')]
            require(len(groups) == len(set(groups)), 'fresh group reused')
            for values in ([r['nonce'] for r in reports['cases']], [r['selected_device'] for r in reports['cases']],
                           [r['ui']['simulator_udid'] for r in summary['trials'] if 'ui' in r]):
                require(len(values) == len(set(values)), 'fresh trial nonce/device reused')
            require(scan(evidence) == original_inventory and digest(original) == checksum, 'authenticated reference/ZIP changed')
            summary['capture_complete'] = all(t['capture_complete'] for t in summary['trials']) and not summary['problems']
            summary['producer_conclusion'] = producers[0]['conclusion']
            summary['built_identity'] = program
            if summary['capture_complete']:
                require((producers[0]['conclusion'] == 'success') == all(t['native_result'] == 'Passed' for t in summary['trials']), 'native failures were masked')
    except Exception as error:
        summary['problems'].append(type(error).__name__ + ': ' + str(error))
    save(output / 'summary.json', summary); print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0 if summary['capture_complete'] and not summary['problems'] else 1


if __name__ == '__main__':
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and sys.platform == 'darwin', 'macOS Actions only')
    require(len(sys.argv) == 2 and sys.argv[1] in ('run', 'audit'), 'explicit mode required')
    raise SystemExit(run_native() if sys.argv[1] == 'run' else audit())
