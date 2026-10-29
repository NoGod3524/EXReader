# SPDX-License-Identifier: MIT
"""Continuation-only complete file capture and exact attribution candidate.

No product/privacy acceptance. Historical reference code and strict helpers are
unchanged; all execution and retained-byte profiling is Actions-only.
"""
import base64
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import time
from contract import ROOT, STAGES, require
from inspect_native import VARIANT_LABELS
from log_evidence import attribute_unified_log as reference_attribution

SOURCE = 'abd16571fda41b5bc936fcbcfb9a125554992c2e'
RUN = '40839064448'
REFERENCE_HASHES = {
    'continuation_lifecycle.py': 'b546ccf2b846bd3ff2413fcbeafe2d8617b42aa455f1b13e327d52d9a0143d82',
    'log_evidence.py': '0b45a8c25cc4d36f3993a8c72b1b2bc9b6258281c62fd4485cf9fc06e0179fbd',
    'contract.py': '3bbc7fca067c77b91ad5d4e3fa96a4e98e1d7ade6bfc5c90dd329b56f7eae3af',
    'inspect_native.py': 'a273d60d3d3c3a4642d643f7036796b6147ae831d62f26a725fe326b25ab9582',
    'archive_contract.py': '1101f1d4e4ccaa75d779a0d4392c5d9fac943dbba21fd90fddc9733451f201c4',
    'privacy_scan.py': 'd68195894df3d2b92cbea94a4c0876bc4291fea7a822635bb3e142c2528d9164',
}
FILES = ('host-unified.json', 'capture-stderr.txt')
CHUNK = 1024 * 1024
PROFILE_MARKER = '[privacy-capture-profile]'
OTHER_MARKERS = ('[privacy-diagnostic]', '[privacy-native-diagnostic]',
                 '[privacy-continuation-diagnostic]', '[privacy-continuation]')


def remaining(deadline):
    value = deadline - time.monotonic()
    require(value > 0, 'capture deadline exhausted')
    return value


def owned_identity(value):
    require(stat.S_ISREG(value.st_mode) and value.st_nlink == 1 and
            not (getattr(value, 'st_file_attributes', 0) & 0x400), 'capture file ownership differs')
    return (value.st_dev, value.st_ino, value.st_mode, value.st_nlink)


def stable_identity(value):
    return owned_identity(value) + (value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def private_directory(path, create=False):
    path = Path(path)
    if create: path.mkdir(mode=0o700, exist_ok=False)
    item = path.lstat()
    require(stat.S_ISDIR(item.st_mode) and not stat.S_ISLNK(item.st_mode), 'capture directory differs')
    require(item.st_uid == os.getuid() and stat.S_IMODE(item.st_mode) & 0o077 == 0,
            'capture directory not private')
    return (item.st_dev, item.st_ino, item.st_mode)


def stream_record(path, deadline, descriptor=None):
    """Full-byte stable regular-file hash, no size cutoff or FIFO blocking."""
    path = Path(path); before = stable_identity(path.lstat())
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    owned = descriptor is None
    fd = os.open(path, flags) if owned else descriptor
    try:
        require(stable_identity(os.fstat(fd)) == before, 'capture descriptor differs')
        os.lseek(fd, 0, os.SEEK_SET)
        digest, count, nonblank = hashlib.sha256(), 0, False
        while True:
            remaining(deadline); data = os.read(fd, CHUNK)
            if not data: break
            digest.update(data); count += len(data); nonblank = nonblank or bool(data.strip())
        require(stable_identity(os.fstat(fd)) == before == stable_identity(path.lstat()) and
                count == before[4], 'capture bytes changed')
        return {'bytes': count, 'sha256': digest.hexdigest()}, nonblank
    finally:
        if owned: os.close(fd)


class FileCapture:
    """Fresh private stdout/stderr sinks; failed streams are never discarded."""
    def __init__(self, folder):
        self.folder = Path(folder)
        self.directory_identity = private_directory(self.folder, create=True)
        self.descriptors, self.identities = {}, {}
        self.records, self.nonblank, self.returncode = None, False, None
        self.final_identities = {}
        self.terminated = False
        self.process = None
        try:
            for name in FILES:
                flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
                descriptor = os.open(self.folder / name, flags, 0o600)
                self.descriptors[name] = descriptor
                self.identities[name] = owned_identity(os.fstat(descriptor))
        except Exception:
            self.close(); raise

    def close(self):
        for descriptor in self.descriptors.values():
            try: os.close(descriptor)
            except OSError: pass
        self.descriptors.clear()

    def disposition(self, state):
        # A separate finite record cannot make partial streams a valid capture.
        require(state in ('failed-unsealed', 'complete-capture', 'failed-capture'), 'capture disposition differs')
        try:
            path = self.folder.parent / (self.folder.name + '-capture-disposition.json')
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            with os.fdopen(fd, 'w') as file:
                json.dump({'state': state, 'writers_terminated': self.terminated,
                           'valid_capture_manifest': False, 'native_acceptance': False}, file)
            return True
        except OSError:
            return False  # Caller refuses sealing; never print arbitrary operands.

    def command(self, lifecycle, argv, cap, check, cwd, env, max_capture):
        self.deadline = lifecycle.deadline
        process, proven, interrupted = None, False, False
        try:
            require(max_capture is None, 'file capture must retain complete streams')
            cutoff = min(lifecycle.deadline, time.monotonic() + lifecycle.remaining(cap))
            process = subprocess.Popen(list(map(str, argv)), stdout=self.descriptors[FILES[0]],
                stderr=self.descriptors[FILES[1]], cwd=cwd, env=env, start_new_session=True)
            self.process = process
            try: process.wait(timeout=max(0.001, cutoff - time.monotonic()))
            except subprocess.TimeoutExpired: interrupted = True
            try: os.killpg(process.pid, 0); lingering = True
            except ProcessLookupError: lingering = False
            except PermissionError: lingering = True
            if interrupted or lingering:
                lifecycle.failed = True
                try: os.killpg(process.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError): pass
                left = max(0, min(cutoff, lifecycle.deadline) - time.monotonic())
                if process.poll() is None and left:
                    try: process.wait(timeout=left)
                    except subprocess.TimeoutExpired: pass
                # Failure is unsealed even if a kill later succeeds; never use
                # an optimistic parent exit to certify descendant ownership.
                raise RuntimeError('file capture writer ownership incomplete')
            remaining(lifecycle.deadline)
            require(process.returncode is not None, 'file capture parent incomplete')
            self.terminated = True
            require(private_directory(self.folder) == self.directory_identity and
                    set(path.name for path in self.folder.iterdir()) == set(FILES), 'capture namespace differs')
            records = {}
            for name, descriptor in self.descriptors.items():
                require(owned_identity(os.fstat(descriptor)) == self.identities[name] ==
                        owned_identity((self.folder / name).lstat()), 'capture sink replaced')
                records[name], nonblank = stream_record(self.folder / name, lifecycle.deadline, descriptor)
                self.final_identities[name] = stable_identity(os.fstat(descriptor))
                if name == FILES[0]: self.nonblank = nonblank
            # Recheck the earlier stream and namespace after reading the later one.
            for name, descriptor in self.descriptors.items():
                require(stable_identity(os.fstat(descriptor)) == self.final_identities[name] ==
                        stable_identity((self.folder / name).lstat()),
                        'earlier capture stream changed')
            require(private_directory(self.folder) == self.directory_identity and
                    set(path.name for path in self.folder.iterdir()) == set(FILES), 'capture namespace changed')
            self.records, self.returncode, proven = records, process.returncode, True
            if not self.disposition('complete-capture' if self.returncode == 0 else 'failed-capture'):
                lifecycle.failed = True
                raise RuntimeError('capture disposition unavailable')
            require(not check or self.returncode == 0, 'bounded continuation command failed')
            return subprocess.CompletedProcess(argv, self.returncode, self.folder / FILES[0], self.folder / FILES[1])
        except BaseException:
            if not proven:
                lifecycle.failed = True
                if process is not None:
                    try: os.killpg(process.pid, signal.SIGKILL)
                    except (ProcessLookupError, PermissionError): pass
                self.disposition('failed-unsealed')
            raise
        finally:
            self.close()


def product_capture(evidence, stage):
    require(stage in STAGES, 'invalid log identity')
    parent = Path(evidence) / 'sensitive-synthetic-product-logs'
    try: parent.mkdir(mode=0o700, exist_ok=False)
    except FileExistsError: private_directory(parent)
    return FileCapture(parent / stage)


def publish_product_capture(capture, evidence, stage, platform, source, run, attempt):
    remaining(capture.deadline)
    require(stage in STAGES and platform in ('macos', 'iphone', 'ipad') and capture.terminated and
            capture.records is not None and type(capture.returncode) is int and
            capture.folder == Path(evidence) / 'sensitive-synthetic-product-logs' / stage,
            'file capture is not publishable')
    require(private_directory(capture.folder) == capture.directory_identity and
        set(path.name for path in capture.folder.iterdir()) == set(FILES) and
        all(stable_identity((capture.folder / name).lstat()) == capture.final_identities[name] for name in FILES),
        'capture changed before manifest')
    manifest = {'synthetic_run_only': True, 'may_contain_synthetic_credentials': True,
        'purpose': 'retained product-process log bytes; not a privacy acceptance verdict',
        'scope': 'EXReaderHost unified log including framework events; capture stderr separate',
        'source_sha': source, 'run_id': run, 'attempt': attempt, 'stage': stage, 'platform': platform,
        'capture_exit': capture.returncode, 'files': capture.records}
    path = Path(evidence) / (stage + '-product-log-manifest.json')
    with path.open('x') as file: file.write(json.dumps(manifest, indent=2) + '\n')
    remaining(capture.deadline)
    return capture.folder


def read_payload(path, deadline, expected=None):
    path = Path(path); before = stable_identity(path.lstat())
    chunks, digest, total = [], hashlib.sha256(), 0
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    with os.fdopen(fd, 'rb') as file:
        require(stable_identity(os.fstat(file.fileno())) == before, 'attribution descriptor differs')
        while True:
            remaining(deadline); data = file.read(CHUNK)
            if not data: break
            chunks.append(data); digest.update(data); total += len(data)
        require(stable_identity(os.fstat(file.fileno())) == before == stable_identity(path.lstat()) and total == before[4],
                'attribution payload changed')
    payload = b''.join(chunks)
    require(expected is None or expected == {'bytes': total, 'sha256': digest.hexdigest()}, 'attribution digest differs')
    remaining(deadline)
    return payload


class LiteralRoleSearch:
    """Literal longest-first search with complete contained and overlap roles."""
    def __init__(self, variants):
        mapping = {}
        for label, value in variants.items(): mapping.setdefault(value, set()).add(label.split(':', 1)[0])
        self.empty_roles = mapping.pop(b'', set())
        self.keys = sorted(mapping, key=lambda value: (-len(value), value))
        self.closures = {value: set().union(*(roles for other, roles in mapping.items() if other in value))
                         for value in self.keys}
        self.all_roles = self.empty_roles | set().union(*mapping.values())
        self.pattern = re.compile(b'(?:' + b'|'.join(re.escape(value) for value in self.keys) + b')') if self.keys else None
        self.search_calls = 0

    def roles(self, message):
        found = set(self.empty_roles)
        if self.pattern is None: return found
        position = 0
        while found != self.all_roles:
            self.search_calls += 1
            match = self.pattern.search(message, position)
            if match is None: break
            found.update(self.closures[match.group(0)])
            # Not match.end(): a later needle may cross this match's boundary.
            position = match.start() + 1
        return found


def attribution_with_state(payload, variants, deadline=None, observe_phases=False):
    """Same semantic return plus finite path/optional phase evidence."""
    require(type(observe_phases) is bool, 'attribution observation mode differs')
    started = time.monotonic_ns() if observe_phases else None
    state = {'candidate_path_used': False, 'fallback_used': False,
             'literal_event_count': 0, 'pattern_count': 0, 'search_call_count': 0,
             'phases': {name: None for name in ('decode_ns', 'prepare_ns', 'event_loop_ns', 'total_ns')}}
    def finish(value):
        if deadline is not None: remaining(deadline)
        if observe_phases: state['phases']['total_ns'] = time.monotonic_ns() - started
        return value, state
    require(all(label in VARIANT_LABELS for label in variants), 'unexpected attribution variant')
    if deadline is not None: remaining(deadline)
    if any(type(value) is not bytes for value in variants.values()):
        state['fallback_used'] = True
        return finish(reference_attribution(payload, variants))
    report = {'arbitrary_event_text_printed': False, 'byte_scan_is_authoritative': True,
              'owner_callsite_proven': False, 'parsed_json_array': False, 'matched_event_groups': []}
    began = time.monotonic_ns() if observe_phases else None
    try: events = json.loads(payload)
    except (ValueError, UnicodeDecodeError):
        if observe_phases: state['phases']['decode_ns'] = time.monotonic_ns() - began
        return finish(report)
    if observe_phases: state['phases']['decode_ns'] = time.monotonic_ns() - began
    if deadline is not None: remaining(deadline)
    if not isinstance(events, list): return finish(report)
    report['parsed_json_array'] = True
    report['event_count'] = len(events)
    began = time.monotonic_ns() if observe_phases else None
    try: search = LiteralRoleSearch(variants)
    except re.error:
        # re.error can carry the complete pattern; never format/print it.
        # Correct reference output is preserved, but this invocation cannot
        # qualify as the accelerated candidate in the retained experiment.
        if observe_phases: state['phases']['prepare_ns'] = time.monotonic_ns() - began
        state['fallback_used'] = True
        return finish(reference_attribution(payload, variants))
    if observe_phases: state['phases']['prepare_ns'] = time.monotonic_ns() - began
    state['pattern_count'] = len(search.keys)
    counts = {}
    began = time.monotonic_ns() if observe_phases else None
    for index, event in enumerate(events):
        if deadline is not None and index % 1024 == 0: remaining(deadline)
        if not isinstance(event, dict) or not isinstance(event.get('eventMessage'), str): continue
        message = event['eventMessage'].encode('utf-8')
        state['literal_event_count'] += 1
        roles = tuple(sorted(search.roles(message)))
        if not roles: continue
        sender = event.get('senderImagePath')
        category = 'unknown-or-other-image'
        if isinstance(sender, str):
            if any('/' + name + '.framework/' in sender for name in ('XCTest', 'XCTAutomationSupport')):
                category = 'test-framework-image'
            elif sender.startswith('/System/Library/'):
                if any('/' + name + '.framework/' in sender for name in ('AXRuntime', 'AXCoreUtilities', 'Accessibility')):
                    category = 'apple-accessibility-framework-image'
                elif any('/' + name + '.framework/' in sender for name in ('AppKit', 'UIKitCore', 'UIKit', 'ViewBridge')):
                    category = 'apple-ui-framework-image'
                else: category = 'apple-framework-image'
            elif sender.startswith('/usr/lib/'): category = 'system-library-image'
            elif Path(sender).name == 'EXReaderHost': category = 'application-image'
        key = (category, roles); counts[key] = counts.get(key, 0) + 1
    report['matched_event_groups'] = [{'sender_category': category, 'credential_roles': list(roles), 'event_count': count}
                                      for (category, roles), count in sorted(counts.items())]
    state['search_call_count'] = search.search_calls
    state['candidate_path_used'] = search.search_calls > 0
    if observe_phases: state['phases']['event_loop_ns'] = time.monotonic_ns() - began
    return finish(report)


def attribute_unified_log(payload, variants, deadline=None):
    return attribution_with_state(payload, variants, deadline=deadline)[0]

def profile_marker_valid(message):
    return type(message) is str and message.count(PROFILE_MARKER) == 1 and not any(marker in message for marker in OTHER_MARKERS)


def oracle_variants(oracle, source, run, attempt):
    from privacy_scan import needles
    require(type(oracle) is dict and set(oracle) == {'synthetic_only', 'source_sha', 'run_id', 'attempt', 'user', 'passwords'} and
        oracle['synthetic_only'] is True and
        (oracle['synthetic_only'], oracle['source_sha'], oracle['run_id'], oracle['attempt']) ==
        (True, source, run, attempt), 'oracle identity differs')
    user, passwords = oracle['user'], oracle['passwords']
    require(type(user) is str and re.fullmatch(r'privacy-user-[0-9a-f]{32}', user) and type(passwords) is dict and
        set(passwords) == {'remembered', 'session'} and passwords['remembered'] != passwords['session'] and
        all(type(value) is str and re.fullmatch(r'Privacy-[0-9a-f]{64}!%:\+', value) for value in passwords.values()),
        'invalid synthetic inputs')
    values = {'user': user.encode()}
    for role, password in passwords.items():
        pair = (user + ':' + password).encode()
        values[role] = password.encode(); values[role + '-pair'] = pair
        values[role + '-authorization'] = b'Basic ' + base64.b64encode(pair)
    return needles(values)


def write_private_json(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'w') as file: json.dump(value, file, sort_keys=True)


class ProfileDeadlineExpired(RuntimeError):
    pass


@contextmanager
def profile_deadline(deadline):
    """Actual main-thread timer covers parent walks/decoders/imports too."""
    require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), 'profile timer already owned')
    previous = signal.getsignal(signal.SIGALRM)
    def expired(unused_signal, unused_frame): raise ProfileDeadlineExpired()
    signal.signal(signal.SIGALRM, expired)
    try:
        signal.setitimer(signal.ITIMER_REAL, remaining(deadline))
        yield
    finally:
        # Block/drain only our owned timer signal before restoring the prior
        # handler, avoiding a stale alarm interrupting safe-summary writing.
        blocked = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGALRM})
        try:
            signal.setitimer(signal.ITIMER_REAL, 0)
            if signal.SIGALRM in signal.sigpending(): signal.sigwait({signal.SIGALRM})
            signal.signal(signal.SIGALRM, previous)
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, blocked)


def bounded_profile_session(out, deadline, summary, body):
    """Real publication path, also exercised by stalled-parent controls.

    The18-minute timer stops profiling work. Only fixed refusal-summary writing
    remains afterwards, in the job's separately reserved2-minute upload margin.
    No cleanup success or writer seal is inferred from an interrupted body.
    """
    out = Path(out)
    try:
        with profile_deadline(deadline):
            out.mkdir(mode=0o700, parents=True, exist_ok=False)
            value = body()
            remaining(deadline)
            return value
    except Exception as error:
        summary.update(profile_complete=False, profile_refused=True, performance_gate=False,
                       all_byte_and_role_parity=False, native_authorized=False)
        summary['refusal_code'] = 'deadline-exhausted' if type(error) is ProfileDeadlineExpired else 'retained-profile-refused'
        classes = {RuntimeError: 'runtime', OSError: 'os', ValueError: 'value', TypeError: 'type',
                   KeyError: 'key', FileNotFoundError: 'missing-file', PermissionError: 'permission'}
        summary['refusal_class'] = 'deadline' if type(error) is ProfileDeadlineExpired else classes.get(type(error), 'unclassified')
        return summary
    finally:
        try: write_private_json(out / 'summary.json', summary)
        except OSError:
            summary.update(profile_complete=False, profile_refused=True, performance_gate=False,
                           summary_write_refused=True, native_authorized=False)


def reference_modules(directory, deadline):
    """Verify historical source AND every nonstdlib transitive import first."""
    import contract, inspect_native, archive_contract, privacy_scan, log_evidence
    for name, expected in REFERENCE_HASHES.items():
        require(stream_record(Path(directory) / name, deadline)[0]['sha256'] == expected, 'historical reference differs')
    for module in (contract, inspect_native, archive_contract, privacy_scan, log_evidence):
        require(stream_record(Path(module.__file__), deadline)[0]['sha256'] == REFERENCE_HASHES[Path(module.__file__).name],
                'historical import differs')
    modules = []
    for name in ('continuation_lifecycle', 'log_evidence'):
        spec = importlib.util.spec_from_file_location('pinned_capture_' + name, Path(directory) / (name + '.py'))
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); modules.append(module)
    return modules


def profile_outcome(function, payload, variants):
    """Finite exception identity; never format an exception or its arguments."""
    try: return {'value': function(payload, variants), 'exception': None}
    except (RuntimeError, ValueError, UnicodeDecodeError, UnicodeEncodeError, TypeError) as error:
        require(type(error) in (RuntimeError, ValueError, UnicodeDecodeError, UnicodeEncodeError, TypeError),
                'profile exception subclass refused')
        return {'value': None, 'exception': type(error).__name__}


def profile_gate(rows):
    """Both AB/BA aggregates and each complete paired sample must improve."""
    require(type(rows) is list and len(rows) == 48, 'profile measurements incomplete')
    keys, totals, samples = set(), {}, {}
    for row in rows:
        require(type(row) is dict and set(row) == {'platform', 'stage', 'comparison', 'order', 'implementation', 'elapsed_ns', 'parity'} and
            row['platform'] in ('macos', 'iphone') and row['stage'] in STAGES[:3] and
            row['comparison'] in ('capture', 'attribution') and row['order'] in ('AB', 'BA') and
            row['implementation'] in ('reference', 'candidate') and row['parity'] is True and
            type(row['elapsed_ns']) is int and 0 < row['elapsed_ns'] <= 1080 * 1000000000,
            'profile measurement differs')
        key = tuple(row[name] for name in ('platform', 'stage', 'comparison', 'order', 'implementation'))
        require(key not in keys, 'duplicate profile measurement'); keys.add(key)
        total = (row['order'], row['implementation']); totals[total] = totals.get(total, 0) + row['elapsed_ns']
        sample = (row['platform'], row['stage'], row['implementation'])
        samples[sample] = samples.get(sample, 0) + row['elapsed_ns']
    aggregate = all(totals[order, 'candidate'] * 100 <= totals[order, 'reference'] * 80 for order in ('AB', 'BA'))
    regression = all(samples[platform, stage, 'candidate'] * 100 <= samples[platform, stage, 'reference'] * 110
                     for platform in ('macos', 'iphone') for stage in STAGES[:3])
    return {'all_byte_and_role_parity': True, 'both_order_aggregate_20_percent_improvement': aggregate,
            'no_sample_mean_regression_over_10_percent': regression, 'performance_gate': aggregate and regression,
            'native_authorized': False, 'full_f10_accepted': False}


def validate_candidate_state(state, phases_observed):
    require(type(phases_observed) is bool, 'candidate phase mode differs')
    require(type(state) is dict and set(state) == {'candidate_path_used', 'fallback_used', 'literal_event_count', 'pattern_count', 'search_call_count', 'phases'} and
        type(state['candidate_path_used']) is bool and type(state['fallback_used']) is bool and
        not (state['candidate_path_used'] and state['fallback_used']) and
        type(state['literal_event_count']) is int and 0 <= state['literal_event_count'] <= 1000000000 and
        type(state['pattern_count']) is int and 0 <= state['pattern_count'] <= len(VARIANT_LABELS) and
        type(state['search_call_count']) is int and 0 <= state['search_call_count'] <= 1000000000000 and
        state['candidate_path_used'] == (state['search_call_count'] > 0), 'candidate path state differs')
    phases = state['phases']
    require(type(phases) is dict and set(phases) == {'decode_ns', 'prepare_ns', 'event_loop_ns', 'total_ns'}, 'candidate phase shape differs')
    require(all(value is None or type(value) is int and 0 <= value <= 1080 * 1000000000 for value in phases.values()),
            'candidate phase number differs')
    if phases_observed:
        require(phases['total_ns'] is not None and sum(value or 0 for key, value in phases.items() if key != 'total_ns') <= phases['total_ns'],
                'candidate phase durations differ')
        require(not state['candidate_path_used'] or all(value is not None for value in phases.values()),
                'candidate entered phase missing')
    else: require(all(value is None for value in phases.values()), 'eligibility timing instrumented')
    return state['candidate_path_used'] and not state['fallback_used'] and state['literal_event_count'] > 0 and state['pattern_count'] > 0


def candidate_path_gate(records):
    require(type(records) is list and len(records) == 12, 'candidate path records incomplete')
    seen, qualified = set(), True
    for row in records:
        require(type(row) is dict and set(row) == {'platform', 'stage', 'order', 'state'} and row['platform'] in ('macos', 'iphone') and
            row['stage'] in STAGES[:3] and row['order'] in ('AB', 'BA'), 'candidate path record differs')
        key = (row['platform'], row['stage'], row['order'])
        require(key not in seen, 'duplicate candidate path record'); seen.add(key)
        valid = validate_candidate_state(row['state'], False)
        qualified = qualified and valid
    return qualified


def candidate_evidence_gate(paths, observations, samples):
    qualified = candidate_path_gate(paths)
    require(type(samples) is list and len(samples) == 6, 'candidate sample bindings incomplete')
    expected = {}
    for row in samples:
        require(type(row) is dict and set(row) == {'platform', 'stage', 'files'} and row['platform'] in ('macos', 'iphone') and
                row['stage'] in STAGES[:3], 'candidate sample binding shape differs')
        key = (row['platform'], row['stage'])
        require(key not in expected and type(row['files']) is dict and set(row['files']) == set(FILES), 'candidate sample stream shape differs')
        for item in row['files'].values():
            require(type(item) is dict and set(item) == {'bytes', 'sha256'} and type(item['bytes']) is int and item['bytes'] >= 0 and
                    type(item['sha256']) is str and re.fullmatch('[0-9a-f]{64}', item['sha256']), 'candidate sample stream metadata differs')
        expected[key] = row['files']
    require(set(expected) == {(platform, stage) for platform in ('macos', 'iphone') for stage in STAGES[:3]},
            'candidate sample bindings differ')
    require(type(observations) is list and len(observations) == 6, 'candidate subphase inventory differs')
    seen = set()
    for row in observations:
        require(type(row) is dict and set(row) == {'platform', 'stage', 'files', 'sample_elapsed_ns', 'state', 'semantic_parity'} and
            row['platform'] in ('macos', 'iphone') and row['stage'] in STAGES[:3] and row['semantic_parity'] is True and
            type(row['sample_elapsed_ns']) is int and 0 < row['sample_elapsed_ns'] <= 1080 * 1000000000, 'candidate subphase record differs')
        key = (row['platform'], row['stage'])
        require(key not in seen and row['files'] == expected[key], 'candidate subphase binding differs'); seen.add(key)
        valid = validate_candidate_state(row['state'], True)
        require(row['sample_elapsed_ns'] >= row['state']['phases']['total_ns'], 'candidate subphase timer differs')
        qualified = qualified and valid
        # The same frozen message/needle bytes must take the same literal path
        # in both paired calls and its independent observed call.
        fields = ('candidate_path_used', 'fallback_used', 'literal_event_count', 'pattern_count', 'search_call_count')
        value = tuple(row['state'][name] for name in fields)
        qualified = qualified and all(tuple(path['state'][name] for name in fields) == value
            for path in paths if (path['platform'], path['stage']) == key)
    return qualified


def profile_worker(mode, spec_path, output, reference, deadline):
    """Child-only work. Parent bounds this complete process group as well."""
    from continuation_lifecycle import ContinuationLifecycle
    from privacy_scan import scan_file
    spec = json.loads(read_payload(spec_path, deadline))
    remaining(deadline)
    if mode == 'emit':
        # A reference command creates its own session. This no-child emitter
        # has its own absolute deadline too; a refused profile never certifies
        # cleanup or a successful receipt after any owner timeout.
        signal.signal(signal.SIGALRM, lambda *unused: os._exit(125))
        signal.setitimer(signal.ITIMER_REAL, remaining(deadline))
        for name, destination in zip(FILES, (sys.stdout.buffer, sys.stderr.buffer)):
            before, unused = stream_record(spec['streams'][name], deadline)
            require(before == spec['manifest']['files'][name], 'emitter input differs')
            with Path(spec['streams'][name]).open('rb') as source:
                while True:
                    remaining(deadline); data = source.read(CHUNK)
                    if not data: break
                    destination.write(data)
            destination.flush()
        return
    if mode == 'extract':
        from archive_contract import safe_extract
        safe_extract(spec['archive'], output)
        return
    historical_lifecycle, historical_log = reference_modules(reference, deadline)
    variants = oracle_variants(json.loads(read_payload(spec['oracle'], deadline)), SOURCE, RUN, '1')
    require(spec['platform'] in ('macos', 'iphone') and spec['stage'] in STAGES[:3], 'profile sample differs')
    output = Path(output); private_directory(output)
    if mode in ('capture-reference', 'capture-candidate'):
        lifecycle_type = historical_lifecycle.ContinuationLifecycle if mode.endswith('reference') else ContinuationLifecycle
        lifecycle = lifecycle_type('macos', budget_seconds=min(4800, remaining(deadline)))
        command = [sys.executable, '-B', str(Path(__file__).resolve()), '--worker', 'emit', str(spec_path),
                   str(output), str(reference), str(deadline)]
        start = time.monotonic_ns()
        if mode.endswith('reference'):
            done = lifecycle.command(command, cap=60, check=False, max_capture=None)
            folder = historical_log.retain_product_log(output, spec['stage'], spec['platform'], SOURCE, RUN, '1',
                                                       done.stdout, done.stderr, done.returncode)
            require(done.returncode == 0 and bool(done.stdout.strip()), 'reference transport failed')
        else:
            capture = product_capture(output, spec['stage'])
            done = lifecycle.command(command, cap=60, check=False, max_capture=None, output_sink=capture)
            folder = publish_product_capture(capture, output, spec['stage'], spec['platform'], SOURCE, RUN, '1')
            require(done.returncode == 0 and capture.nonblank, 'candidate transport failed')
        # Identical full independent scan and manifest comparison costs count
        # in both timings. Original canary hits are equal, never required clean.
        for name in FILES:
            remaining(deadline)
            actual = scan_file(folder / name, variants)
            require(actual == spec['scans'][name], 'transport byte scan differs')
        manifest = json.loads(read_payload(output / (spec['stage'] + '-product-log-manifest.json'), deadline))
        require(manifest == spec['manifest'], 'transport manifest differs')
        for name in FILES:
            require(stream_record(folder / name, deadline)[0] == spec['manifest']['files'][name], 'transport final bytes differ')
        elapsed = time.monotonic_ns() - start
    else:
        require(mode in ('attribution-reference', 'attribution-candidate', 'phases-candidate'), 'profile worker mode differs')
        # The old command already materialized stdout; its read was charged
        # in capture-reference. Candidate must pay for its new file read here.
        payload = read_payload(spec['streams'][FILES[0]], deadline, spec['manifest']['files'][FILES[0]]) if mode.endswith('reference') else None
        start = time.monotonic_ns()
        if mode.endswith('candidate'):
            payload = read_payload(spec['streams'][FILES[0]], deadline, spec['manifest']['files'][FILES[0]])
        candidate_state = {}
        def candidate(value, supplied_variants):
            report, state = attribution_with_state(value, supplied_variants, deadline=deadline, observe_phases=mode=='phases-candidate')
            candidate_state.update(state)
            return report
        outcome = profile_outcome(historical_log.attribute_unified_log if mode.endswith('reference') else candidate, payload, variants)
        elapsed = time.monotonic_ns() - start
        require(outcome == {'value': spec['attribution'], 'exception': None}, 'retained attribution differs')
    remaining(deadline)
    measurement = {'elapsed_ns': elapsed, 'parity': True}
    if mode in ('attribution-candidate', 'phases-candidate'):
        validate_candidate_state(candidate_state, mode=='phases-candidate')
        measurement['candidate_state'] = candidate_state
    write_private_json(output / 'measurement.json', measurement)


def retained_profile(out, artifacts, source, run):
    """One fixed retained experiment. No SDK/native work or automatic retry."""
    from continuation_lifecycle import ContinuationLifecycle
    from privacy_scan import inventory
    from inspect_continuation_failure import sealed_lifecycle
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and sys.platform == 'darwin', 'Actions macOS only')
    require((source, run) == (SOURCE, RUN) and set(artifacts) == {'macos', 'iphone', 'ipad'}, 'profile pins differ')
    require(re.fullmatch('[0-9a-f]{40}', os.environ['GITHUB_SHA']), 'profile current source differs')
    lifecycle = ContinuationLifecycle('macos', budget_seconds=1080)
    deadline = lifecycle.deadline
    out = Path(out)
    work = out / 'private-work'
    summary = {'diagnostic_only': True, 'native_acceptance': False, 'full_f10_accepted': False,
        'profile_complete': False, 'profile_refused': False, 'old_source_sha': SOURCE, 'old_run_id': RUN, 'old_attempt': 1,
        'all_byte_and_role_parity': False, 'performance_gate': False, 'native_authorized': False,
        'current_source_sha': os.environ['GITHUB_SHA'], 'configured_runner_minutes': 30,
        'samples': [], 'measurements': [], 'ipad_sample_observed': False,
        'candidate_paths': [], 'phase_observations': [], 'all_candidate_paths_used': False,
        'profile_phase': 'setup', 'current_sample': None, 'summary_write_refused': False,
        'actual_apple_log_generation_profiled': False, 'cache_and_order_effects_excluded': False,
        'arbitrary_values_printed': False}
    command_number = [0]
    def command(argv, cap=None):
        command_number[0] += 1
        sink = FileCapture(work / ('owned-command-' + str(command_number[0])))
        done = lifecycle.command(argv, cap=min(remaining(deadline), cap or remaining(deadline)),
            check=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), max_capture=None, output_sink=sink)
        require(all(item['bytes'] <= 16 * 1024 * 1024 for item in sink.records.values()), 'profile command output oversized')
        return subprocess.CompletedProcess(argv, done.returncode,
            read_payload(done.stdout, deadline, sink.records[FILES[0]]),
            read_payload(done.stderr, deadline, sink.records[FILES[1]]))
    def worker(mode, spec_path, output, reference):
        command([sys.executable, '-B', str(Path(__file__).resolve()), '--worker', mode,
                 str(spec_path), str(output), str(reference), str(deadline)], remaining(deadline))
    def execute():
        private_directory(work, create=True)
        event = json.loads(read_payload(Path(os.environ['GITHUB_EVENT_PATH']), deadline))
        require(profile_marker_valid(event['head_commit']['message']), 'profile marker differs')
        # The unchanged guard executes in a bounded owned child, not outside
        # the parent deadline. Its change-list output is retained, never echoed.
        command([sys.executable, '-B', str(ROOT / 'tests/apple_password_privacy_20261028/contract.py')], 30)
        summary['profile_phase'] = 'historical-reference'
        reference = work / 'reference'; private_directory(reference, create=True)
        package = 'tests/apple_password_privacy_20261028/'
        for name, expected in REFERENCE_HASHES.items():
            data = command(['git', 'show', SOURCE + ':' + package + name], 30).stdout
            require(hashlib.sha256(data).hexdigest() == expected, 'historical source differs')
            (reference / name).write_bytes(data)
        reference_modules(reference, deadline)
        originals, folders, snapshots, result_rows = {}, {}, {}, {}
        for platform, (identifier, size, digest) in artifacts.items():
            summary['profile_phase'] = 'artifact-metadata'
            summary['current_sample'] = {'platform': platform, 'stage': None, 'comparison': None, 'order': None, 'implementation': None}
            endpoint = 'repos/' + os.environ['GITHUB_REPOSITORY'] + '/actions/artifacts/' + str(identifier)
            metadata = json.loads(command(['gh', 'api', endpoint], 30).stdout)
            require(metadata['id'] == identifier and metadata['name'] == 'password-continuation-native-' + platform + '-' + RUN + '-1' and
                str(metadata['workflow_run']['id']) == RUN and metadata['workflow_run']['head_sha'] == SOURCE and
                metadata['size_in_bytes'] == size and metadata['digest'] == 'sha256:' + digest and metadata['expired'] is False,
                'profile artifact metadata differs')
            summary['profile_phase'] = 'artifact-download'
            capture = FileCapture(work / ('download-' + platform))
            done = lifecycle.command(['gh', 'api', endpoint + '/zip'], cap=remaining(deadline), max_capture=None, output_sink=capture)
            require(capture.records[FILES[0]] == {'bytes': size, 'sha256': digest}, 'profile original archive differs')
            originals[platform] = done.stdout
            folder = work / platform
            spec_path = work / ('extract-' + platform + '.json')
            write_private_json(spec_path, {'archive': str(done.stdout)})
            summary['profile_phase'] = 'artifact-extract'
            worker('extract', spec_path, folder, reference)
            summary['profile_phase'] = 'original-member-replay'
            result = json.loads(read_payload(folder / 'result.json', deadline))
            require((result['source_sha'], result['run_id'], result['attempt'], result['platform']) ==
                (SOURCE, RUN, '1', platform) and result['accepted'] is False and result['full_f10_accepted'] is False,
                'profile original identity differs')
            snapshots[platform] = inventory(folder)
            files = {path.relative_to(folder).as_posix() for path in folder.rglob('*') if path.is_file()}
            require(files == set(result['files']) | {'result.json'}, 'profile original inventory differs')
            for name, item in result['files'].items():
                require(type(item) is dict and set(item) == {'bytes', 'sha256'} and
                    type(item['bytes']) is int and item['bytes'] >= 0 and type(item['sha256']) is str and
                    re.fullmatch('[0-9a-f]{64}', item['sha256']) and stream_record(folder / name, deadline)[0] == item,
                    'profile original member differs')
            summary['profile_phase'] = 'sealed-lifecycle'
            sealed_lifecycle(result, platform)
            require(list(result['checkpoints']) == (STAGES[:3] if platform != 'ipad' else []), 'profile stage inventory differs')
            if platform != 'ipad':
                require(json.loads(read_payload(folder / 'checkpoints.json', deadline)) == result['checkpoints'], 'profile checkpoints differ')
            folders[platform], result_rows[platform] = folder, result
        sample_inputs = []
        for platform in ('macos', 'iphone'):
            folder, result = folders[platform], result_rows[platform]
            oracle = folder / 'synthetic-oracle-input.json'
            oracle_variants(json.loads(read_payload(oracle, deadline)), SOURCE, RUN, '1')
            for stage in STAGES[:3]:
                summary['profile_phase'] = 'sample-binding'
                summary['current_sample'] = {'platform': platform, 'stage': stage, 'comparison': None, 'order': None, 'implementation': None}
                manifest = json.loads(read_payload(folder / (stage + '-product-log-manifest.json'), deadline))
                require((manifest['source_sha'], manifest['run_id'], manifest['attempt'], manifest['stage'], manifest['platform'],
                    manifest['capture_exit'], manifest['synthetic_run_only']) == (SOURCE, RUN, '1', stage, platform, 0, True),
                    'profile log manifest identity differs')
                scan = result['checkpoints'][stage]['scans']['product-log']
                stored_scans = json.loads(read_payload(folder / (stage + '-privacy-scan.json'), deadline))
                require(stored_scans == result['checkpoints'][stage]['scans'], 'profile original scans differ')
                scans = {item['path']: {key: item[key] for key in ('bytes', 'chunks', 'sha256', 'hits')} for item in scan['files']}
                require(set(scans) == set(FILES) and len(scan['files']) == 2 and manifest['files'] == {
                    name: {key: item[key] for key in ('bytes', 'sha256')} for name, item in scans.items()}, 'profile scan binding differs')
                attribution = json.loads(read_payload(folder / (stage + '-safe-log-attribution.json'), deadline))
                require(attribution == result['log_attribution'][stage], 'profile producer attribution differs')
                streams = {name: str(folder / 'sensitive-synthetic-product-logs' / stage / name) for name in FILES}
                for name, path in streams.items(): require(stream_record(path, deadline)[0] == manifest['files'][name], 'profile retained stream differs')
                spec = {'platform': platform, 'stage': stage, 'oracle': str(oracle), 'streams': streams,
                        'manifest': manifest, 'scans': scans, 'attribution': attribution}
                spec_path = work / (platform + '-' + stage + '.json'); write_private_json(spec_path, spec)
                sample_inputs.append((platform, stage, spec_path, manifest['files']))
                summary['samples'].append({'platform': platform, 'stage': stage, 'files': manifest['files']})
                for comparison in ('capture', 'attribution'):
                    for order, implementations in (('AB', ('reference', 'candidate')), ('BA', ('candidate', 'reference'))):
                        for implementation in implementations:
                            summary['profile_phase'] = comparison + '-' + implementation
                            summary['current_sample'] = {'platform': platform, 'stage': stage, 'comparison': comparison, 'order': order, 'implementation': implementation}
                            output = work / '-'.join((platform, stage, comparison, order, implementation))
                            private_directory(output, create=True)
                            worker(comparison + '-' + implementation, spec_path, output, reference)
                            measured = json.loads(read_payload(output / 'measurement.json', deadline))
                            if comparison == 'attribution' and implementation == 'candidate':
                                require(set(measured) == {'elapsed_ns', 'parity', 'candidate_state'}, 'candidate worker measurement differs')
                                state = measured.pop('candidate_state')
                                validate_candidate_state(state, False)
                                summary['candidate_paths'].append({'platform': platform, 'stage': stage, 'order': order, 'state': state})
                            require(set(measured) == {'elapsed_ns', 'parity'} and measured['parity'] is True and
                                type(measured['elapsed_ns']) is int and 0 < measured['elapsed_ns'] <= 1080 * 1000000000,
                                'profile worker measurement differs')
                            summary['measurements'].append(dict(measured, platform=platform, stage=stage,
                                comparison=comparison, order=order, implementation=implementation))
        # These six calls are separate diagnostics, NEVER extra eligibility
        # samples or replacements for a slower original paired measurement.
        for platform, stage, spec_path, files in sample_inputs:
            summary['profile_phase'] = 'candidate-subphases'
            summary['current_sample'] = {'platform': platform, 'stage': stage, 'comparison': 'subphases', 'order': None, 'implementation': 'candidate'}
            output = work / (platform + '-' + stage + '-subphases'); private_directory(output, create=True)
            worker('phases-candidate', spec_path, output, reference)
            measured = json.loads(read_payload(output / 'measurement.json', deadline))
            require(type(measured) is dict and set(measured) == {'elapsed_ns', 'parity', 'candidate_state'} and
                measured['parity'] is True and type(measured['elapsed_ns']) is int and 0 < measured['elapsed_ns'] <= 1080 * 1000000000,
                'candidate subphase measurement differs')
            validate_candidate_state(measured['candidate_state'], True)
            summary['phase_observations'].append({'platform': platform, 'stage': stage, 'files': files,
                'sample_elapsed_ns': measured['elapsed_ns'], 'state': measured['candidate_state'], 'semantic_parity': True})
        require(len(sample_inputs) == 6 and len(summary['phase_observations']) == 6, 'candidate subphase inventory differs')
        summary['profile_phase'] = 'final-original-replay'
        summary['current_sample'] = None
        for platform, folder in folders.items():
            require(inventory(folder) == snapshots[platform], 'profile changed original namespace')
            for name, item in result_rows[platform]['files'].items():
                require(stream_record(folder / name, deadline)[0] == item, 'profile changed original bytes')
            require(stream_record(originals[platform], deadline)[0] == {'bytes': artifacts[platform][1], 'sha256': artifacts[platform][2]},
                    'profile changed original ZIP')
        reference_modules(reference, deadline)
        summary['profile_phase'] = 'performance-gate'
        summary.update(profile_gate(summary['measurements']))
        summary['all_candidate_paths_used'] = candidate_evidence_gate(summary['candidate_paths'], summary['phase_observations'], summary['samples'])
        summary['performance_gate'] = summary['performance_gate'] and summary['all_candidate_paths_used']
        remaining(deadline)
        summary['profile_complete'] = True
        summary['profile_phase'] = 'complete'
        return summary
    return bounded_profile_session(out, deadline, summary, execute)


if __name__ == '__main__':
    try:
        require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
        if sys.argv[1:] == ['--check-mode']:
            event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
            message = event['head_commit']['message']
            require(PROFILE_MARKER not in message or profile_marker_valid(message), 'profile marker differs')
            raise SystemExit(0)
        require(len(sys.argv) == 7 and sys.argv[1] == '--worker', 'worker arguments differ')
        deadline = float(sys.argv[6])
        require(math.isfinite(deadline) and 0 < deadline - time.monotonic() <= 1080, 'worker deadline differs')
        profile_worker(sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4]), Path(sys.argv[5]), deadline)
    except Exception:
        raise SystemExit(1) from None
