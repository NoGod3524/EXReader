# SPDX-License-Identifier: MIT
"""Real GTK host driver: launch, X11 keys, windows and evidence capture.

Keys are delivered with xdotool to the mapped X11 window, so every audited
transition is produced by the same input path a keyboard user produces.  The
host's own observation file is used only to know when a scripted operation
has settled; no assertion is derived from an in-process test hook.
"""
import configparser
import os
from pathlib import Path
import re
import subprocess
import time


def command(*args, timeout=30, **kwargs):
    return subprocess.run([str(item) for item in args], capture_output=True, text=True,
                          timeout=timeout, check=False, **kwargs)


def wait_until(predicate, timeout, interval=0.1, description='condition'):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            last = predicate()
        except Exception:  # a transient read must not end the wait
            last = None
        if last:
            return last
        time.sleep(interval)
    raise TimeoutError('timed out waiting for %s (last=%r)' % (description, last))


class Host:
    def __init__(self, binary, font, folder, title='EXReader Linux'):
        self.binary = Path(binary)
        self.font = Path(font)
        self.folder = Path(folder)
        self.title = title
        self.profile = self.folder / 'profile'
        self.observe = self.folder / 'state.ini'
        self.log_path = self.folder / 'application.log'
        self.keys_path = self.folder / 'keys.log'
        self.process = None
        self.log = None
        self.window = None
        self.keys = 0
        self.focus_hook = None

    # -- lifecycle ---------------------------------------------------------
    def environment(self):
        env = dict(os.environ)
        # The audit needs the accessibility bridge that the credential checks
        # deliberately disable; inherit nothing that would turn it off.
        for name in ('NO_AT_BRIDGE', 'GTK_MODULES', 'GTK_A11Y', 'AT_SPI_BUS_ADDRESS'):
            env.pop(name, None)
        env['GTK_A11Y'] = 'atspi'
        return env

    def launch(self, timeout=120):
        self.observe.unlink(missing_ok=True)
        self.log = self.log_path.open('ab')
        self.process = subprocess.Popen([str(self.binary), str(self.font), str(self.profile),
                                         str(self.observe)], stdout=self.log,
                                        stderr=subprocess.STDOUT, env=self.environment())
        self.wait_state(lambda state: state.get('visible') == 1, timeout=timeout)
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.process.poll() is not None:
                raise RuntimeError('host exited before mapping a window; see application.log')
            found = command('xdotool', 'search', '--onlyvisible', '--pid', str(self.process.pid))
            for candidate in found.stdout.splitlines():
                if command('xdotool', 'getwindowname', candidate).stdout.strip() == self.title:
                    self.window = candidate
                    break
            if self.window:
                break
            time.sleep(0.1)
        if not self.window:
            raise TimeoutError('host window was not mapped; see application.log')
        self.activate(self.window)
        return self.window

    def close(self, timeout=40):
        if self.process and self.process.poll() is None:
            self.activate(self.window)
            self.key('alt+F4')
            try:
                self.process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=15)
        if self.log and not self.log.closed:
            self.log.close()
        return self.process.returncode if self.process else None

    # -- observation -------------------------------------------------------
    def section(self, entry, retries=20):
        parser = configparser.ConfigParser(interpolation=None)
        for _ in range(retries):
            try:
                read = parser.read(self.observe)
                if read and parser.has_section(entry):
                    return dict(parser[entry])
            except Exception:
                pass
            time.sleep(0.05)
        return {}

    def host_state(self):
        found = self.section('host')
        out = {}
        for key, value in found.items():
            try:
                out[key] = int(value)
            except ValueError:
                out[key] = value
        return out

    def number(self, entry, key, default=0):
        value = self.section(entry).get(key, '')
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def wait_state(self, predicate, timeout=60, description='host state'):
        def probe():
            state = self.host_state()
            return state if state and predicate(state) else None
        return wait_until(probe, timeout, description=description)

    def wait_visible(self, window_id, present=True, timeout=30):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            listed = bool(window_id in self.window_list())
            if listed == present:
                return listed
            time.sleep(0.1)
        raise TimeoutError('window %s visibility != %r after %ss' % (window_id, present, timeout))

    def window_list(self):
        result = command('xdotool', 'search', '--onlyvisible', '--all', '--pid', str(self.process.pid))
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]

    def window_named(self, title, present=True, timeout=30):
        pattern = '^' + re.escape(title) + '$'
        end = time.monotonic() + timeout
        last = ''
        while time.monotonic() < end:
            found = command('xdotool', 'search', '--onlyvisible', '--name', pattern)
            ids = [line.strip() for line in found.stdout.splitlines() if line.strip()]
            last = found.stdout + found.stderr
            if bool(ids) == present:
                return ids[-1] if ids else None
            time.sleep(0.1)
        raise TimeoutError('window %r presence != %r after %ss (%s)'
                           % (title, present, timeout, last.strip()))

    def log_text(self):
        try:
            return self.log_path.read_text(errors='replace')
        except FileNotFoundError:
            return ''

    def last_status(self):
        for line in reversed(self.log_text().splitlines()):
            if line.startswith('STATUS '):
                match = re.search(r'message=(.*)$', line)
                return match.group(1) if match else ''
        return ''

    # -- input -------------------------------------------------------------
    def activate(self, window_id):
        command('xdotool', 'windowactivate', '--sync', window_id)
        time.sleep(0.15)

    def record(self, key, focus=None):
        if focus is None and self.focus_hook is not None:
            try:
                focus = self.focus_hook()
            except Exception:
                focus = ''
        focus = focus or ''
        self.keys += 1
        with self.keys_path.open('a', encoding='utf-8') as out:
            out.write('%d\t%.3f\t%s\t%s\n' % (self.keys, time.monotonic(), key, focus))

    def key(self, *keys, settle=None, settle_timeout=60):
        for entry in keys:
            command('xdotool', 'key', '--clearmodifiers', entry)
            self.record(entry)
            time.sleep(0.15)
        if settle is not None:
            self.wait_state(settle, timeout=settle_timeout, description='host idle after %r' % (keys,))

    def paste(self, value):
        # xclip forks a holder process that inherits the stdio pipes; capturing
        # them would keep this call waiting until the timeout expires.
        result = subprocess.run(['xclip', '-selection', 'clipboard'], input=value.encode(),
                                check=False, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, timeout=20)
        if result.returncode != 0:
            raise RuntimeError('xclip failed with status %d' % result.returncode)
        self.key('ctrl+v')

    def type_text(self, value):
        command('xdotool', 'type', '--clearmodifiers', '--delay', '40', value)
        self.record('type:' + value[:40])

    # -- evidence ----------------------------------------------------------
    def screenshot(self, path, window=None):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        target = window or self.window or 'root'
        result = command('import', '-window', str(target), str(path), timeout=60)
        if result.returncode != 0 or not path.exists() or path.stat().st_size == 0:
            raise RuntimeError('screenshot %s failed: %r' % (path, result.stderr))

    def geometry(self, window=None):
        return command('xdotool', 'getwindowgeometry', '--shell', window or self.window).stdout

    def window_tree(self, path):
        text = command('xwininfo', '-root', '-tree').stdout
        Path(path).write_text(text, encoding='utf-8')
        return text
