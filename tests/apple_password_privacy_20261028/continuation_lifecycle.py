# SPDX-License-Identifier: MIT
"""Continuation-only bounded writer ownership and fail-closed evidence sealing."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import stat
import socket
from http.server import ThreadingHTTPServer
import subprocess
import sys
import tempfile
import threading
import time
from contract import ROOT, require


class ContinuationLifecycle:
    def __init__(self, platform, budget_seconds=4800, drain_seconds=90):
        require(platform in ('macos', 'iphone', 'ipad'), 'invalid lifecycle platform')
        require(type(budget_seconds) in (int, float) and math.isfinite(budget_seconds) and
                0 < budget_seconds <= 4800 and type(drain_seconds) in (int, float) and
                math.isfinite(drain_seconds) and 0 < drain_seconds <= 90, 'invalid lifecycle budget')
        self.deadline = time.monotonic() + budget_seconds
        self.budget_seconds = budget_seconds
        self.drain_seconds = drain_seconds
        self.condition = threading.Condition()
        self.admission_closed_event = threading.Event()
        self.admission_open, self.active, self.admitted, self.rejected = True, 0, 0, 0
        self.serving_stopped, self.drained, self.failed = False, False, False
        self.certificate_delete = None
        self.cleanup = {'certificate': 'not-required',
            'simulator-shutdown': 'not-required' if platform == 'macos' else 'pending',
            'simulator-erase': 'not-required' if platform == 'macos' else 'pending'}

    def remaining(self, cap=None, deadline=None):
        value = min(self.deadline, deadline if deadline is not None else self.deadline) - time.monotonic()
        require(value > 0, 'continuation deadline exhausted')
        return min(value, cap) if cap is not None else value

    def admit(self):
        with self.condition:
            if not self.admission_open:
                self.rejected += 1
                return False
            self.active += 1; self.admitted += 1
            require(self.admitted <= 100000, 'too many lifecycle admissions')
            return True

    def release(self):
        with self.condition:
            if self.active <= 0:
                self.failed = True
                raise RuntimeError('lifecycle counter underflow')
            self.active -= 1
            self.condition.notify_all()

    def close_admission(self):
        with self.condition:
            self.admission_open = False
            self.admission_closed_event.set()
            self.condition.notify_all()

    def command(self, argv, cap=30, check=True, cwd=None, env=None, max_capture=16 * 1024 * 1024):
        """Own the invocation group; retain output without waiting on inherited pipes."""
        limit = self.remaining(cap)
        cutoff = min(self.deadline, time.monotonic() + limit)
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            process = subprocess.Popen(list(map(str, argv)), stdout=stdout, stderr=stderr,
                                       cwd=cwd, env=env, start_new_session=True)
            interrupted = False
            left = cutoff - time.monotonic()
            if left <= 0: interrupted = True
            else:
                try: process.wait(timeout=left)
                except subprocess.TimeoutExpired: interrupted = True
            # A successful parent must not leave detached group members holding
            # output or evidence writers. These are this invocation's session,
            # never unrelated runner processes. Failed termination is unsealed.
            try:
                os.killpg(process.pid, 0)
                lingering = True
            except ProcessLookupError:
                lingering = False
            except PermissionError:
                lingering = True
            if interrupted or lingering:
                self.failed = True
                interrupted = True
                try: os.killpg(process.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError): pass
                left = max(0, cutoff - time.monotonic())
                if process.poll() is None and left:
                    try: process.wait(timeout=min(1, left))
                    except subprocess.TimeoutExpired: pass
            stdout.seek(0); stderr.seek(0)
            output = stdout.read() if max_capture is None else stdout.read(max_capture + 1)
            errors = stderr.read() if max_capture is None else stderr.read(max_capture + 1)
            require(max_capture is None or (len(output) <= max_capture and len(errors) <= max_capture),
                    'bounded continuation command output oversized')
            if time.monotonic() >= self.deadline:
                interrupted = True; self.failed = True
            code = process.returncode if process.returncode is not None else -1
            if interrupted and code == 0: code = 1
            require(not check or (code == 0 and not interrupted), 'bounded continuation command failed')
            return subprocess.CompletedProcess(argv, code, output, errors)

    def cleanup_command(self, name, argv):
        require(name in self.cleanup, 'invalid cleanup role')
        try:
            if self.deadline <= time.monotonic():
                self.cleanup[name] = 'not-attempted-deadline'
                self.failed = True
                return False
            self.command(argv)
            self.cleanup[name] = 'completed'
            return True
        except Exception:
            self.cleanup[name] = 'failed-or-timed-out'
            self.failed = True
            return False

    def stop(self, server, serving):
        self.close_admission()
        cutoff = min(self.deadline, time.monotonic() + self.drain_seconds)
        done, stopped = threading.Event(), [False]
        def stop_loop():
            try:
                server.close_owned_sockets()
                server.shutdown()
                server.server_close()  # Request threads remain daemon; no hidden unbounded join.
                stopped[0] = True
            except Exception:
                pass
            finally:
                done.set()
        try:
            self.remaining(deadline=cutoff)
            threading.Thread(target=stop_loop, daemon=True).start()
            require(done.wait(self.remaining(deadline=cutoff)) and stopped[0], 'serving shutdown incomplete')
            serving.join(timeout=self.remaining(deadline=cutoff))
            require(not serving.is_alive(), 'serving thread still active')
            self.serving_stopped = True
            with self.condition:
                while self.active:
                    self.condition.wait(timeout=self.remaining(deadline=cutoff))
                self.drained = True
        except Exception:
            self.failed = True
            raise RuntimeError('continuation drain incomplete') from None

    def receipt(self):
        with self.condition:
            return {'admission_closed': not self.admission_open, 'active_handlers': self.active,
                'admitted_handlers': self.admitted, 'rejected_handlers': self.rejected,
                'serving_stopped': self.serving_stopped, 'drained': self.drained,
                'failed': self.failed, 'cleanup': dict(self.cleanup),
                'outer_limit_seconds': self.budget_seconds, 'drain_limit_seconds': self.drain_seconds}


class LifecycleHTTPServer(ThreadingHTTPServer):
    """Continuation-only server: TLS ownership plus whole request-thread fence."""
    daemon_threads = True
    block_on_close = False

    def __init__(self, address, handler, lifecycle, tls_context, failures):
        self.lifecycle, self.tls_context, self.failures = lifecycle, tls_context, failures
        self.owned_sockets, self.socket_lock = set(), threading.Lock()
        self.handshake_started = threading.Event()
        super().__init__(address, handler)

    def get_request(self):
        connection, address = super().get_request()
        with self.socket_lock: self.owned_sockets.add(connection)
        try:
            connection.settimeout(self.lifecycle.remaining(10))
            if self.tls_context is not None:
                wrapped = self.tls_context.wrap_socket(connection, server_side=True, do_handshake_on_connect=False)
                with self.socket_lock:
                    self.owned_sockets.discard(connection); self.owned_sockets.add(wrapped)
                connection = wrapped
                self.handshake_started.set()
                connection.do_handshake()
            connection.settimeout(self.lifecycle.remaining(30))
            return connection, address
        except Exception:
            with self.socket_lock: self.owned_sockets.discard(connection)
            connection.close()
            raise OSError('bounded TLS admission refused') from None

    def process_request_thread(self, request, client_address):
        admitted = self.lifecycle.admit()
        try:
            if admitted: super().process_request_thread(request, client_address)
            else: self.shutdown_request(request)
        finally:
            if admitted: self.lifecycle.release()

    def shutdown_request(self, request):
        try: super().shutdown_request(request)
        finally:
            with self.socket_lock: self.owned_sockets.discard(request)

    def handle_error(self, request, client_address):
        # Error handling remains inside the counted request thread; no traceback.
        self.failures.append('RuntimeError')

    def close_owned_sockets(self):
        with self.socket_lock: connections = list(self.owned_sockets)
        for connection in connections:
            try: connection.shutdown(socket.SHUT_RDWR)
            except OSError: pass
            try: connection.close()
            except OSError: pass


def verify_lifecycle(receipt, platform):
    require(platform in ('macos', 'iphone', 'ipad'), 'invalid lifecycle platform')
    require(type(receipt) is dict and set(receipt) == {'admission_closed', 'active_handlers',
        'admitted_handlers', 'rejected_handlers', 'serving_stopped', 'drained', 'failed', 'cleanup',
        'outer_limit_seconds', 'drain_limit_seconds'}, 'lifecycle receipt shape differs')
    require(receipt['admission_closed'] is True and receipt['active_handlers'] == 0 and
        type(receipt['active_handlers']) is int and receipt['serving_stopped'] is True and
        receipt['drained'] is True and receipt['failed'] is False and
        type(receipt['admitted_handlers']) is int and 0 <= receipt['admitted_handlers'] <= 100000 and
        type(receipt['rejected_handlers']) is int and 0 <= receipt['rejected_handlers'] <= 100000 and
        type(receipt['outer_limit_seconds']) is int and receipt['outer_limit_seconds'] == 4800 and
        type(receipt['drain_limit_seconds']) is int and receipt['drain_limit_seconds'] == 90,
        'lifecycle ownership incomplete')
    require(receipt['cleanup'] == {'certificate': 'completed',
        'simulator-shutdown': 'not-required' if platform == 'macos' else 'completed',
        'simulator-erase': 'not-required' if platform == 'macos' else 'completed'}, 'lifecycle cleanup incomplete')


def _identity(path):
    value = path.lstat()
    require(stat.S_ISREG(value.st_mode), 'nonregular evidence file')
    return (value.st_dev, value.st_ino, value.st_mode, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns, value.st_nlink)


def _inventory(directory, deadline=None):
    files, directories = {}, {}
    def walk(path):
        require(deadline is None or time.monotonic() < deadline, 'evidence seal deadline exhausted')
        value = path.lstat()
        require(stat.S_ISDIR(value.st_mode), 'nonregular evidence directory')
        directories[path.relative_to(directory).as_posix()] = (value.st_dev, value.st_ino, value.st_mode,
            value.st_mtime_ns, value.st_ctime_ns, value.st_nlink)
        for child in sorted(path.iterdir()):
            require(deadline is None or time.monotonic() < deadline, 'evidence seal deadline exhausted')
            mode = child.lstat().st_mode
            if stat.S_ISDIR(mode): walk(child)
            else: files[child.relative_to(directory).as_posix()] = _identity(child)
            require(len(files) + len(directories) <= 100000, 'evidence inventory oversized')
    walk(directory)
    return files, directories


def _record(path, identity, deadline=None):
    require(deadline is None or time.monotonic() < deadline, 'evidence seal deadline exhausted')
    require(_identity(path) == identity, 'evidence changed before read')
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    checksum, total = hashlib.sha256(), 0
    with os.fdopen(descriptor, 'rb') as file:
        opened = os.fstat(file.fileno())
        require((opened.st_dev, opened.st_ino, opened.st_mode, opened.st_size,
            opened.st_mtime_ns, opened.st_ctime_ns, opened.st_nlink) == identity, 'evidence open identity differs')
        for data in iter(lambda: file.read(1024 * 1024), b''):
            require(deadline is None or time.monotonic() < deadline, 'evidence seal deadline exhausted')
            checksum.update(data); total += len(data)
        closed = os.fstat(file.fileno())
        require((closed.st_dev, closed.st_ino, closed.st_mode, closed.st_size,
            closed.st_mtime_ns, closed.st_ctime_ns, closed.st_nlink) == identity, 'evidence changed during read')
    require(_identity(path) == identity and total == identity[3], 'evidence changed after read')
    return {'bytes': total, 'sha256': checksum.hexdigest()}


def seal_files(directory, between_passes=None, deadline=None):
    """All files, all bytes, two passes and namespace/identity revalidation."""
    directory = Path(directory)
    for name in ('result.json', '.result-pending'):
        try: (directory / name).lstat()
        except FileNotFoundError: pass
        else: raise RuntimeError('evidence publication already exists')
    before = _inventory(directory, deadline)
    first = {name: _record(directory / name, identity, deadline) for name, identity in before[0].items()}
    if between_passes is not None:
        require(os.environ.get('GITHUB_ACTIONS') == 'true', 'seal controls are Actions only')
        between_passes()
    require(_inventory(directory, deadline) == before, 'evidence namespace changed')
    second = {name: _record(directory / name, identity, deadline) for name, identity in before[0].items()}
    require(first == second and _inventory(directory, deadline) == before, 'evidence final bytes changed')
    return second


def atomic_result(directory, result, deadline=None):
    path = Path(directory) / 'result.json'
    try: path.lstat()
    except FileNotFoundError: pass
    else: raise RuntimeError('result already published')
    temporary = Path(directory) / '.result-pending'
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as file:
        for chunk in json.JSONEncoder(indent=2, sort_keys=True).iterencode(result):
            require(deadline is None or time.monotonic() < deadline, 'result publication deadline exhausted')
            file.write(chunk)
        file.write('\n')
        file.flush(); os.fsync(file.fileno())
    require(deadline is None or time.monotonic() < deadline, 'result publication deadline exhausted')
    os.replace(temporary, path)


def write_unsealed(directory, source, platform, lifecycle):
    """Exact production/control refusal branch; no callback-owned dictionary reads."""
    require(type(source) is str and re.fullmatch(r'[0-9a-f]{40}', source) is not None and
            platform in ('macos', 'iphone', 'ipad'), 'invalid unsealed identity')
    report = {'accepted': False, 'diagnostic_only': True, 'sequence_complete': False,
        'full_f10_accepted': False, 'evidence_sealed': False,
        'failure': 'continuation-drain-cleanup-or-seal-incomplete',
        'source_sha': source, 'platform': platform,
        'lifecycle': lifecycle.receipt(), 'arbitrary_error_details_printed': False}
    try:
        (Path(directory) / 'unsealed.json').write_text(json.dumps(report, indent=2) + '\n')
        (Path(directory) / 'result.json').unlink(missing_ok=True)
    except Exception:
        raise RuntimeError('unsealed refusal could not be retained') from None
    return report


def frozen_helper(role, paths):
    """Frozen inspectors execute only in this bounded, owned Actions subprocess."""
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and sys.platform == 'darwin', 'Actions macOS only')
    sys.path[:0] = [str(ROOT / 'tests/apple_host'), str(ROOT / 'tools')]
    if role == 'inspect' and len(paths) == 2:
        from check_apple_product import inspect
        return inspect(Path(paths[0]), Path(paths[1]), True)
    if role == 'cases' and len(paths) == 1:
        from collect_evidence import load_results
        return load_results(Path(paths[0]))
    raise RuntimeError('unknown bounded helper role')


if __name__ == '__main__':
    try:
        print(json.dumps(frozen_helper(sys.argv[1], sys.argv[2:])))
    except Exception:
        raise RuntimeError('bounded frozen helper refused; arbitrary operands withheld') from None
