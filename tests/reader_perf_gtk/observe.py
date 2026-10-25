#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Event-driven observation of the frozen GTK product host.

The host writes its observation file with g_file_set_contents, which renames a
temporary file onto the destination. The destination directory therefore is
watched with inotify and every delivery timestamp comes straight from the
watcher thread; nothing here polls the observation file for latency. Screenshots
and AT-SPI are not used at all.
"""
import ctypes
import os
import select
import struct
import subprocess
import threading
import time
from pathlib import Path

IN_CREATE = 0x00000100
IN_MOVED_TO = 0x00000080
IN_CLOSE_WRITE = 0x00000008
IN_MODIFY = 0x00000002
IN_ISDIR = 0x40000000
IN_NONBLOCK = os.O_NONBLOCK
IN_CLOEXEC = os.O_CLOEXEC
EVENT = struct.Struct('iIII')
WATCH_MASK = IN_CREATE | IN_MOVED_TO | IN_CLOSE_WRITE | IN_MODIFY
WINDOW_TITLE = 'EXReader Linux'
IMPORT_DIALOG = '^Import book$'

_libc = ctypes.CDLL('libc.so.6', use_errno=True)
_libc.inotify_init1.argtypes = [ctypes.c_int]
_libc.inotify_init1.restype = ctypes.c_int
_libc.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
_libc.inotify_add_watch.restype = ctypes.c_int
_libc.inotify_rm_watch.argtypes = [ctypes.c_int, ctypes.c_int]
_libc.inotify_rm_watch.restype = ctypes.c_int


class SampleError(RuntimeError):
    """A planned sample could not be observed; reported as a real failure."""


def command(*args, timeout=30):
    return subprocess.run([str(item) for item in args], stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=timeout, check=True).stdout.decode().strip()


def _number(text):
    try:
        return int(text)
    except ValueError:
        try:
            return float(text)
        except ValueError:
            return text


def parse_state(text):
    host, shelf = {}, {}
    section = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith('[') and line.endswith(']'):
            section = line[1:-1]
            continue
        if '=' not in line:
            continue
        key, value = line.split('=', 1)
        target = host if section == 'host' else shelf if section == 'shelf' else None
        if target is not None:
            target[key] = _number(value)
    return {'host': host, 'shelf': shelf}


def read_state(path):
    for _ in range(5):
        try:
            return parse_state(Path(path).read_text(encoding='utf-8'))
        except FileNotFoundError:
            return None
        except OSError:
            time.sleep(0.001)
    return None


class Watch:
    """inotify watch on one launch directory; timestamps come from the watcher."""

    def __init__(self, folder, name='state.ini'):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.name = name
        self.target = name.encode()
        self.condition = threading.Condition()
        self.events = []
        self.failure = None
        self.fd = _libc.inotify_init1(IN_NONBLOCK | IN_CLOEXEC)
        if self.fd < 0:
            raise SampleError('inotify_init1 failed: errno %d' % ctypes.get_errno())
        self.wd = _libc.inotify_add_watch(self.fd, str(self.folder).encode(), WATCH_MASK)
        if self.wd < 0:
            raise SampleError('inotify_add_watch failed for %s: errno %d' % (self.folder, ctypes.get_errno()))
        self.running = True
        self.thread = threading.Thread(target=self._loop, name='observation-watch', daemon=True)
        self.thread.start()

    def _loop(self):
        while self.running:
            try:
                ready, _, _ = select.select([self.fd], [], [], 0.25)
            except OSError as error:
                self.failure = 'inotify select: %s' % error
                return
            if not ready:
                continue
            try:
                data = os.read(self.fd, 65536)
            except BlockingIOError:
                continue
            except OSError as error:
                self.failure = 'inotify read: %s' % error
                return
            if not data:
                continue
            stamp = time.monotonic()
            matched = False
            position = 0
            while position + EVENT.size <= len(data):
                _wd, mask, _cookie, length = EVENT.unpack_from(data, position)
                position += EVENT.size
                raw = data[position:position + length]
                position += length
                if mask & IN_ISDIR:
                    continue
                if raw.rstrip(b'\x00') == self.target:
                    matched = True
            if not matched:
                continue
            state = read_state(self.folder / self.name)
            if state is None:
                continue
            with self.condition:
                self.events.append({'at': stamp, 'state': state})
                self.condition.notify_all()

    def mark(self):
        with self.condition:
            return len(self.events)

    def event(self, index):
        return self.events[index]

    def latest(self):
        with self.condition:
            return self.events[-1] if self.events else None

    def wait(self, predicate, timeout, since=0):
        """First event at/after since whose state satisfies predicate."""
        deadline = time.monotonic() + timeout
        index = since
        while True:
            with self.condition:
                while len(self.events) <= index:
                    if self.failure:
                        return None, self.failure
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return None, 'timeout'
                    self.condition.wait(min(remaining, 0.5))
            state = self.events[index]['state']
            if predicate(state):
                return index, self.events[index]
            index += 1

    def close(self):
        self.running = False
        with self.condition:
            self.condition.notify_all()
        if self.wd is not None and self.fd >= 0:
            _libc.inotify_rm_watch(self.fd, self.wd)
            self.wd = None
        if self.fd >= 0:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = -1


class Host:
    """The unchanged installed-SDK GTK product host under a real X server."""

    def __init__(self, binary, font, profile, folder, environment, tag=''):
        self.binary = Path(binary)
        self.font = Path(font)
        self.profile = Path(profile)
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.state_path = self.folder / 'state.ini'
        self.log_path = self.folder / 'application.log'
        self.environment = environment
        self.tag = tag
        self.process = None
        self.log = None
        self.pid = None
        self.window = None

    def launch(self):
        if self.state_path.exists():
            self.state_path.unlink()
        self.log = self.log_path.open('ab')
        started = time.monotonic()
        self.process = subprocess.Popen([
            str(self.binary), str(self.font), str(self.profile), str(self.state_path)],
            stdout=self.log, stderr=subprocess.STDOUT, env=self.environment)
        self.pid = self.process.pid
        return started

    def alive(self):
        return self.process is not None and self.process.poll() is None

    def require_alive(self, where):
        if not self.alive():
            raise SampleError('host %s exited (%s) while %s; see %s' % (
                self.pid, self.process.poll() if self.process else 'not started', where, self.log_path))

    def find_window(self, timeout=60.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.require_alive('mapping its window')
            found = subprocess.run(['xdotool', 'search', '--onlyvisible', '--pid', str(self.pid)],
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=20)
            if found.returncode == 0:
                for candidate in found.stdout.decode().split():
                    if command('xdotool', 'getwindowname', candidate, timeout=20) == WINDOW_TITLE:
                        self.window = candidate
                        return candidate
            time.sleep(0.005)
        raise SampleError('window was not mapped within %.1fs' % timeout)

    def activate(self):
        if not self.window:
            self.find_window()
        command('xdotool', 'windowactivate', '--sync', self.window, timeout=30)

    def geometry(self):
        text = command('xdotool', 'getwindowgeometry', '--shell', self.window, timeout=20)
        values = {}
        for line in text.splitlines():
            if '=' in line:
                key, value = line.split('=', 1)
                key, value = key.strip(), value.strip()
                try:
                    values[key] = int(value)
                except ValueError:
                    values[key] = value
        return values

    def resize(self, width, height):
        command('xdotool', 'windowsize', '--sync', self.window, str(width), str(height), timeout=30)

    def press(self, key):
        """One real X11 key event; returns the monotonic injection timestamp."""
        stamp = time.monotonic()
        subprocess.run(['xdotool', 'key', '--clearmodifiers', key], stdout=subprocess.DEVNULL,
                       stderr=subprocess.PIPE, timeout=30, check=True)
        return stamp

    def paste(self, text):
        # xclip forks an owner that outlives this call. Keep its stdio away from the
        # step's pipe so the capture cannot be held open after the sampler exits.
        subprocess.run(['xclip', '-selection', 'clipboard'], input=text.encode(), timeout=30, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return self.press('ctrl+v')

    def dialog_visible(self):
        found = subprocess.run(['xdotool', 'search', '--onlyvisible', '--name', IMPORT_DIALOG],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        return found.returncode == 0

    def open_import_dialog(self, path, timeout=20.0):
        stamp = self.press('F1')
        dialog = command('xdotool', 'search', '--sync', '--onlyvisible', '--name', IMPORT_DIALOG, timeout=timeout)
        dialog = dialog.splitlines()[-1]
        command('xdotool', 'windowactivate', '--sync', dialog, timeout=20)
        self.press('ctrl+l')
        self.paste(str(path))
        self.press('Return')
        time.sleep(0.3)
        if self.dialog_visible():
            self.press('Return')
        return stamp

    def status(self):
        values = {}
        try:
            text = Path('/proc/%d/status' % self.pid).read_text()
        except OSError:
            return values
        for line in text.splitlines():
            if ':' in line:
                key, value = line.split(':', 1)
                values[key.strip()] = value.strip()
        return values

    def rss_kb(self):
        status = self.status()
        rss = status.get('VmRSS', '') or ''
        return int(rss.split()[0]) if rss[:1].isdigit() else None

    def hwm_kb(self):
        status = self.status()
        hwm = status.get('VmHWM', '') or ''
        return int(hwm.split()[0]) if hwm[:1].isdigit() else None

    def threads(self):
        status = self.status()
        value = status.get('Threads', '')
        return int(value) if value.isdigit() else None

    def window_tree(self):
        return command('xwininfo', '-root', '-tree', timeout=30)

    def close(self, timeout=60):
        if self.process is None:
            return None
        if self.process.poll() is None:
            self.activate()
            try:
                self.press('alt+F4')
            except subprocess.SubprocessError:
                pass
            try:
                return self.process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=30)
                return 'timeout'
        return self.process.returncode

    def kill(self):
        if self.process is not None and self.process.poll() is None:
            self.process.kill()
            self.process.wait(timeout=30)

    def close_log(self):
        if self.log is not None and not self.log.closed:
            self.log.close()
