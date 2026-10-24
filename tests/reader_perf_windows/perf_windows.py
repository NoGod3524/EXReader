#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Cloud-only Windows product-host performance observation.

The packaged Windows native host (the product EXE built from the unchanged
examples/reader.c with the product catalog) is launched as an independent
process for every sample. Each drive step is delivered to the real Win32
controls of that running EXE and the resulting state is read back from the same
controls. Nothing is measured in-process; no production code is modified.

Reported values are external, end-to-end UI latencies: from the moment a native
input message is submitted to the moment the resulting UI state is observable
through the control surface. This path exposes no in-application frame or
present signal, so frame time is reported as not measured and no value in this
evidence may be read as a frame time.

Scope: the fixed 2202-original library built by the unchanged public-SDK seed
program, the frozen packaged font, and one fixed packaged multi-page book for
in-book paging and continue-reading. Cold/warm strategies are recorded in
environment.json; the operating-system disk cache and background load are not
controlled.
"""
import argparse
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

if os.name == 'nt':
    import winreg
else:  # pragma: no cover - the driver refuses to run outside Windows
    winreg = None

U = C.WinDLL('user32', use_last_error=True)
K = C.WinDLL('kernel32', use_last_error=True)
PS = C.WinDLL('psapi', use_last_error=True)
GDI = C.WinDLL('gdi32', use_last_error=True)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_VM_READ = 0x0010

WM_NULL, WM_SETTEXT, WM_GETTEXT, WM_CLOSE = 0x0000, 0x000C, 0x000D, 0x0010
WM_MOUSEWHEEL, BM_CLICK = 0x020A, 0x00F5
LB_GETCOUNT, LB_GETTEXT, LB_SETCURSEL = 0x018B, 0x0189, 0x0186
LB_GETTOPINDEX = 0x018E
SMTO_ABORTIFHUNG = 0x0002

IDS = {
    'path': 101, 'import': 102, 'open': 103, 'delete': 104, 'previous': 105,
    'next': 106, 'select': 107, 'copy': 108, 'add': 109, 'update': 110,
    'remove': 111, 'jump': 112, 'font_dec': 113, 'font_inc': 114,
    'zoom_dec': 115, 'zoom_inc': 116, 'cancel': 117, 'shelf_label': 118,
    'books': 119, 'notes_label': 120, 'notes': 121, 'comment': 122,
    'page': 123, 'page_label': 124, 'status': 125, 'search': 126,
    'refresh': 127,
}

LABEL_FIXED = re.compile(r'第 (\d+) / (\d+) 页')
LABEL_BOUNDED = re.compile(r'章 (\d+) · 本章第 (\d+) 页')
LABEL_REFLOW = re.compile(r'第 (\d+) 页 ·')
ROW_NUMBER = re.compile(r'Shelf (\d{4})')


class MEMORYSTATUSEX(C.Structure):
    _fields_ = [('dwLength', W.DWORD), ('dwMemoryLoad', W.DWORD),
                ('ullTotalPhys', C.c_ulonglong), ('ullAvailPhys', C.c_ulonglong),
                ('ullTotalPageFile', C.c_ulonglong), ('ullAvailPageFile', C.c_ulonglong),
                ('ullTotalVirtual', C.c_ulonglong), ('ullAvailVirtual', C.c_ulonglong),
                ('ullAvailExtendedVirtual', C.c_ulonglong)]


class SYSTEM_INFO(C.Structure):
    _fields_ = [('wProcessorArchitecture', W.WORD), ('wReserved', W.WORD),
                ('dwPageSize', W.DWORD), ('lpMinimumApplicationAddress', C.c_void_p),
                ('lpMaximumApplicationAddress', C.c_void_p), ('dwActiveProcessorMask', C.c_size_t),
                ('dwNumberOfProcessors', W.DWORD), ('dwProcessorType', W.DWORD),
                ('dwAllocationGranularity', W.DWORD), ('wProcessorLevel', W.WORD),
                ('wProcessorRevision', W.WORD)]


class PROCESS_MEMORY_COUNTERS_EX(C.Structure):
    _fields_ = [('cb', W.DWORD), ('PageFaultCount', W.DWORD),
                ('PeakWorkingSetSize', C.c_size_t), ('WorkingSetSize', C.c_size_t),
                ('QuotaPeakPagedPoolUsage', C.c_size_t), ('QuotaPagedPoolUsage', C.c_size_t),
                ('QuotaPeakNonPagedPoolUsage', C.c_size_t), ('QuotaNonPagedPoolUsage', C.c_size_t),
                ('PagefileUsage', C.c_size_t), ('PeakPagefileUsage', C.c_size_t),
                ('PrivateUsage', C.c_size_t)]


U.GetDlgItem.argtypes = [W.HWND, C.c_int]
U.GetDlgItem.restype = W.HWND
U.SendMessageTimeoutW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM, W.UINT, W.UINT,
                                  C.POINTER(C.c_size_t)]
U.SendMessageTimeoutW.restype = W.LPARAM
U.PostMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
U.PostMessageW.restype = W.BOOL
U.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
U.GetClassNameW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
U.GetClientRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
U.GetWindowRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
U.IsWindowEnabled.argtypes = [W.HWND]
U.IsWindowEnabled.restype = W.BOOL
U.GetDC.argtypes = [W.HWND]
U.GetDC.restype = W.HDC
U.ReleaseDC.argtypes = [W.HWND, W.HDC]
GDI.GetDeviceCaps.argtypes = [W.HDC, C.c_int]
GDI.GetDeviceCaps.restype = C.c_int
ENUM = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
U.EnumWindows.argtypes = [ENUM, W.LPARAM]
K.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
K.OpenProcess.restype = W.HANDLE
K.CloseHandle.argtypes = [W.HANDLE]
K.GlobalMemoryStatusEx.argtypes = [C.POINTER(MEMORYSTATUSEX)]
K.GetSystemInfo.argtypes = [C.POINTER(SYSTEM_INFO)]
PS.GetProcessMemoryInfo.argtypes = [W.HANDLE, C.c_void_p, W.DWORD]
PS.GetProcessMemoryInfo.restype = W.BOOL


class MeasurementFault(RuntimeError):
    """The observation surface itself failed, so the sample is incomplete."""


def now_ms():
    return time.perf_counter() * 1000.0


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def median(values):
    ordered = sorted(values)
    if not ordered:
        return None
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def p95(values):
    ordered = sorted(values)
    if not ordered:
        return None
    rank = max(1, -(-95 * len(ordered) // 100))  # nearest rank
    return float(ordered[rank - 1])


def summary_stats(values, unit='ms'):
    values = [value for value in values if isinstance(value, (int, float))]
    return {'unit': unit, 'n': len(values),
            'min': min(values) if values else None,
            'p50': median(values) if values else None,
            'p95': p95(values) if values else None,
            'max': max(values) if values else None}


def page_key(label):
    match = LABEL_FIXED.search(label or '')
    if match:
        return [0, int(match.group(1))]
    match = LABEL_BOUNDED.search(label or '')
    if match:
        return [int(match.group(1)), int(match.group(2))]
    match = LABEL_REFLOW.search(label or '')
    if match:
        return [1, int(match.group(1))]
    return None


def row_number(title):
    match = ROW_NUMBER.search(title or '')
    return int(match.group(1)) if match else None


class MemorySampler(threading.Thread):
    """Poll the host process working set from the observing process."""

    def __init__(self, pid):
        super().__init__(daemon=True)
        self.pid = pid
        self.started = now_ms()
        self.samples = []
        self.stop_event = threading.Event()

    def run(self):
        handle = K.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ, False, self.pid)
        if not handle:
            return
        try:
            while not self.stop_event.is_set():
                counters = PROCESS_MEMORY_COUNTERS_EX()
                counters.cb = C.sizeof(PROCESS_MEMORY_COUNTERS_EX)
                if PS.GetProcessMemoryInfo(handle, C.byref(counters), counters.cb):
                    self.samples.append([round(now_ms() - self.started, 2),
                                         int(counters.WorkingSetSize),
                                         int(counters.PeakWorkingSetSize),
                                         int(counters.PrivateUsage)])
                time.sleep(0.02)
        finally:
            K.CloseHandle(handle)

    def stop(self):
        self.stop_event.set()
        self.join(timeout=5)


class Host:
    """One independent product-host process driven through its real controls."""

    def __init__(self, exe, font, data, log_path):
        self.exe, self.font, self.data = Path(exe), Path(font), Path(data)
        self.data.mkdir(parents=True, exist_ok=True)
        self.log_path = Path(log_path)
        self.log = self.log_path.open('wb')
        self.started_utc = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        self.t0 = now_ms()
        self.process = subprocess.Popen([str(self.exe), '--font', str(self.font),
                                         '--data', str(self.data)],
                                        stdout=self.log, stderr=subprocess.STDOUT)
        self.sampler = MemorySampler(self.process.pid)
        self.sampler.start()
        self.window = None
        self._handles = {}

    # -- primitives ------------------------------------------------------
    def send(self, hwnd, message, wparam=0, lparam=0, timeout=2000):
        if not hwnd:
            raise MeasurementFault('control handle unavailable for message %d' % message)
        result = C.c_size_t()
        C.set_last_error(0)
        delivered = U.SendMessageTimeoutW(hwnd, message, wparam, lparam, SMTO_ABORTIFHUNG,
                                          timeout, C.byref(result))
        if not delivered:
            error = C.get_last_error()
            # A zero LRESULT from a serviced message (WM_NULL, LB_GETCOUNT on an
            # empty list, a zero top index) is not a failure; only ERROR_TIMEOUT
            # and real send errors are.
            if error not in (0, 1460):
                raise TimeoutError('UI message failed: message=%d winerror=%d' % (message, error))
            if error == 1460:
                raise TimeoutError('UI message not serviced: message=%d winerror=%d'
                                   % (message, error))
        return result.value

    def control(self, name):
        if name not in self._handles:
            handle = U.GetDlgItem(self.window, IDS[name])
            if not handle:
                raise MeasurementFault('product control missing: ' + name)
            self._handles[name] = handle
        return self._handles[name]

    def text(self, hwnd, capacity=2048, timeout=2000):
        buffer = C.create_unicode_buffer(capacity)
        self.send(hwnd, WM_GETTEXT, capacity, C.addressof(buffer), timeout)
        return buffer.value

    def set_text(self, hwnd, value, timeout=2000):
        buffer = C.create_unicode_buffer(value)
        self.send(hwnd, WM_SETTEXT, 0, C.addressof(buffer), timeout)
        return self.text(hwnd, max(64, len(value) + 8), timeout)

    def label(self, timeout=2000):
        return self.text(self.control('page_label'), 512, timeout)

    def status(self, timeout=2000):
        return self.text(self.control('status'), 1024, timeout)

    def lb_count(self, timeout=2000):
        return int(self.send(self.control('books'), LB_GETCOUNT, 0, 0, timeout))

    def lb_item(self, index, timeout=2000):
        buffer = C.create_unicode_buffer(1024)
        self.send(self.control('books'), LB_GETTEXT, index, C.addressof(buffer), timeout)
        return buffer.value

    def lb_top(self, timeout=2000):
        return int(self.send(self.control('books'), LB_GETTOPINDEX, 0, 0, timeout))

    def lb_set(self, index, timeout=2000):
        return self.send(self.control('books'), LB_SETCURSEL, index, 0, timeout)

    def rows(self, timeout=2000):
        return [self.lb_item(index, timeout) for index in range(self.lb_count(timeout))]

    def click(self, name, timeout=2000):
        return self.send(self.control(name), BM_CLICK, 0, 0, timeout)

    def wheel(self, notches, timeout=2000):
        for _ in range(notches):
            self.send(self.control('books'), WM_MOUSEWHEEL, ((-120) & 0xFFFF) << 16, 0, timeout)

    def wheel_up(self, notches, timeout=2000):
        for _ in range(notches):
            self.send(self.control('books'), WM_MOUSEWHEEL, (120 & 0xFFFF) << 16, 0, timeout)

    def import_enabled(self):
        return bool(U.IsWindowEnabled(self.control('import')))

    def roundtrip(self, timeout=2000):
        started = now_ms()
        self.send(self.window, WM_NULL, 0, 0, timeout)
        return now_ms() - started

    def memory(self):
        handle = K.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ, False,
                               self.process.pid)
        if not handle:
            return None
        try:
            counters = PROCESS_MEMORY_COUNTERS_EX()
            counters.cb = C.sizeof(PROCESS_MEMORY_COUNTERS_EX)
            if not PS.GetProcessMemoryInfo(handle, C.byref(counters), counters.cb):
                return None
            return {'working_set_bytes': int(counters.WorkingSetSize),
                    'peak_working_set_bytes': int(counters.PeakWorkingSetSize),
                    'private_bytes': int(counters.PrivateUsage)}
        finally:
            K.CloseHandle(handle)

    # -- lifecycle -------------------------------------------------------
    def find_window(self):
        found = []

        @ENUM
        def visit(window, unused):
            pid = W.DWORD()
            U.GetWindowThreadProcessId(window, C.byref(pid))
            if pid.value == self.process.pid:
                name = C.create_unicode_buffer(64)
                U.GetClassNameW(window, name, 64)
                if name.value == 'EXReaderHost':
                    found.append(window)
            return True

        U.EnumWindows(visit, 0)
        if found:
            self.window = found[0]
        return self.window

    def poll(self, probe, timeout, interval=0.004):
        """Repeat a probe returning None (not ready) or a one-tuple (result)."""
        deadline = time.perf_counter() + timeout
        last = None
        while time.perf_counter() < deadline:
            if self.process.poll() is not None:
                raise MeasurementFault('host exited early with code %s' % self.process.returncode)
            try:
                box = probe()
                if box is not None:
                    return box
            except TimeoutError as error:
                last = error
            time.sleep(interval)
        raise TimeoutError('expected UI transition did not complete (%s)'
                           % (last if last else 'no transition'))

    def close(self):
        peak = self.memory()
        if self.process.poll() is None:
            try:
                if self.window:
                    U.PostMessageW(self.window, WM_CLOSE, 0, 0)
                self.process.wait(timeout=30)
            except Exception:
                self.process.kill()
                self.process.wait(timeout=30)
        self.sampler.stop()
        self.log.close()
        return peak


# ---------------------------------------------------------------------------
# Environment identity
# ---------------------------------------------------------------------------

def display_identity():
    dpi = 0
    try:
        dpi = int(U.GetDpiForSystem())
    except Exception:
        dpi = 0
    if not dpi:
        try:
            dc = U.GetDC(0)
            dpi = GDI.GetDeviceCaps(dc, 88)
            U.ReleaseDC(0, dc)
        except Exception:
            dpi = 0
    return {'screen_width_px': U.GetSystemMetrics(0),
            'screen_height_px': U.GetSystemMetrics(1),
            'monitors': U.GetSystemMetrics(80), 'dpi': int(dpi or 0),
            'dpi_scale': round((dpi or 96) / 96.0, 3),
            'remote_session': bool(U.GetSystemMetrics(0x1000))}


def environment(package, exe, font, seed_exe, seed_source_sha):
    system = SYSTEM_INFO()
    K.GetSystemInfo(C.byref(system))
    memory = MEMORYSTATUSEX()
    memory.dwLength = C.sizeof(MEMORYSTATUSEX)
    K.GlobalMemoryStatusEx(C.byref(memory))
    cpu = platform.processor()
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
            cpu = winreg.QueryValueEx(key, 'ProcessorNameString')[0].strip()
    except Exception:
        pass
    package_files = {str(path.relative_to(package)).replace('\\', '/'): path.stat().st_size
                     for path in sorted(package.rglob('*')) if path.is_file()}
    return {
        'schema': 1,
        'source_sha': os.environ.get('GITHUB_SHA', ''),
        'run_id': os.environ.get('GITHUB_RUN_ID', ''),
        'attempt': os.environ.get('GITHUB_RUN_ATTEMPT', ''),
        'runner': {name: os.environ.get(name, '') for name in
                   ('RUNNER_OS', 'RUNNER_ARCH', 'RUNNER_NAME', 'ImageOS', 'ImageVersion',
                    'GITHUB_WORKFLOW', 'GITHUB_JOB')},
        'os': {'platform': platform.platform(), 'version': platform.version(),
               'windows_version': list(sys.getwindowsversion())},
        'cpu': {'model': cpu, 'logical_processors': os.cpu_count(),
                'system_processors': system.dwNumberOfProcessors,
                'page_size': system.dwPageSize,
                'allocation_granularity': system.dwAllocationGranularity},
        'memory_total_bytes': int(memory.ullTotalPhys),
        'display': display_identity(),
        'python': {'version': platform.python_version(),
                   'implementation': platform.python_implementation()},
        'artifacts': {
            'package_directory': str(package),
            'package_total_bytes': sum(package_files.values()),
            'files': package_files,
            'exe_bytes': exe.stat().st_size,
            'exe_sha256': sha256(exe),
            'font_bytes': font.stat().st_size,
            'font_sha256': sha256(font),
            'seed_exe_sha256': sha256(seed_exe),
            'seed_source_sha256': seed_source_sha,
        },
        'corpus': {
            'originals': 2202,
            'originals_source': 'tests/windows_host/seed_shelf.c public-SDK seed program (unmodified)',
            'reading_fixture': 'Sample-positive.epub packaged by tools/build_windows_host.py',
            'reading_fixture_sha256': sha256(package / 'Sample-positive.epub'),
            'reading_fixture_bytes': (package / 'Sample-positive.epub').stat().st_size,
        },
        'measurement': {
            'kind': 'external end-to-end native UI latency',
            'frame_time_measured': False,
            'frame_time_reason': 'No in-application frame or present signal is exposed to the '
                                 'observing process; only control-level state transitions are timed.',
            'clock': 'time.perf_counter() (Windows QueryPerformanceCounter)',
            'poll_interval_ms': '3 ms sleep plus one control round trip per probe',
            'input_delivery': 'SendMessageTimeoutW (SMTO_ABORTIFHUNG) to the real Win32 controls of '
                              'the running product process: BM_CLICK on the real buttons, WM_SETTEXT '
                              'into the real edit controls, WM_MOUSEWHEEL to the real list box, '
                              'WM_CLOSE to the real main window.',
            'input_path_note': 'Messages reach the real native controls and are serviced by the '
                               'product UI thread. This is not SendInput-level hardware injection '
                               'and no synthetic in-process call is used.',
            'disk_cache_controlled': False,
            'background_load_controlled': False,
        },
    }


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------

def op_window(host, deadline=240):
    host.poll(lambda: (host.window,) if host.find_window() else None, deadline, interval=0.003)
    return {'window_ms': round(now_ms() - host.t0, 3)}


def op_first_screen(host, deadline=240):
    marks = op_window(host, deadline)

    def rows_ready():
        try:
            return (True,) if host.lb_count(80) >= 50 else None
        except TimeoutError:
            return None

    host.poll(rows_ready, deadline, interval=0.004)
    marks['rows_ms'] = round(now_ms() - host.t0, 3)
    try:
        marks['roundtrip_ms'] = round(host.roundtrip(5000), 3)
        marks['first_screen_interactive_ms'] = round(now_ms() - host.t0, 3)
    except TimeoutError:
        # A timed-out round trip is preserved as an observation: the shelf has
        # rows but the UI thread did not service one synchronous message.
        marks['roundtrip_ms'] = None
        marks['roundtrip_timeout'] = True
        marks['first_screen_interactive_ms'] = None
    marks['first_row_count'] = host.lb_count()
    marks['first_rows'] = host.rows()[:5]
    return marks


def op_open(host, title, timeout=180):
    def locate():
        for index in range(host.lb_count()):
            if title in host.lb_item(index):
                return (index,)
        return None

    (row,) = host.poll(locate, 120, interval=0.02)
    started = now_ms()
    host.lb_set(row)
    host.click('open')

    def opened():
        try:
            label = host.label(150)
        except TimeoutError:
            return None
        return (label,) if page_key(label) else None

    (label,) = host.poll(opened, timeout, interval=0.003)
    return {'ms': round(now_ms() - started, 3), 'label': label, 'key': page_key(label),
            'row': row, 'book': title}


def op_resume(host, expected_key, timeout=180):
    def restored():
        try:
            label = host.label(150)
        except TimeoutError:
            return None
        return (label,) if page_key(label) else None

    (label,) = host.poll(restored, timeout, interval=0.003)
    key = page_key(label)
    return {'ms': round(now_ms() - host.t0, 3), 'label': label, 'key': key,
            'expected_key': expected_key,
            'verified': (key == expected_key) if expected_key else None}


def op_page_turn(host, previous_key, timeout=40):
    started = now_ms()
    host.click('next')

    def turned():
        try:
            key = page_key(host.label(500))
        except TimeoutError:
            return None
        return (key,) if key is not None and key != previous_key else None

    (key,) = host.poll(turned, timeout, interval=0.003)
    label = host.label()
    return {'ms': round(now_ms() - started, 3), 'from': previous_key, 'to': key,
            'label': label, 'status': 'ok'}


def op_shelf_next_page(host, timeout=180):
    started = now_ms()
    bursts = 0
    while now_ms() - started < timeout * 1000:
        bursts += 1
        host.wheel(8)
        burst_started = now_ms()
        while now_ms() - burst_started < 70:
            count = host.lb_count()
            if count >= 100:
                return {'ms': round(now_ms() - started, 3), 'bursts': bursts,
                        'rows_after': count, 'top_after': host.lb_top(), 'status': 'ok'}
            time.sleep(0.003)
    raise MeasurementFault('shelf did not deliver its next 50-row page')


def op_search(host, query, probe, verify, timeout=120):
    """Time WM_SETTEXT on the real search box to visible rows.

    probe() reads at most two list rows so polling does not flood the UI thread;
    verify() checks the final list once."""
    started = now_ms()
    echo = host.set_text(host.control('search'), query)

    def ready():
        try:
            return (True,) if probe(host) else None
        except TimeoutError:
            return None

    host.poll(ready, timeout, interval=0.008)
    elapsed = now_ms() - started
    rows = host.rows()
    if not verify(rows):
        raise MeasurementFault('search result rows differ from the expected filter: %r' % rows[:4])
    return {'ms': round(elapsed, 3), 'query': query, 'echo': echo,
            'rows': len(rows), 'first': rows[:3], 'status': 'ok'}


def numbered(rows):
    return [row_number(row) for row in rows]


def op_import(host, fixture, expected_title, timeout=300):
    echoed = host.set_text(host.control('path'), str(fixture))
    if echoed != str(fixture):
        # The host opens a file dialog when the path box is empty; never let a
        # rejected path turn into a modal dialog.
        raise MeasurementFault('import path edit rejected the fixture path: %r' % echoed)
    started = now_ms()
    host.click('import')
    # BM_CLICK returns after the catalog import job is submitted, so the import
    # button stays disabled until the worker has published the book.
    samples = []
    while now_ms() - started < timeout * 1000:
        busy = not host.import_enabled()
        roundtrip = None
        echo_ok = None
        probe_started = now_ms()
        try:
            roundtrip = round(host.roundtrip(3000), 3)
            if len(samples) % 4 == 0:
                echo_ok = host.set_text(host.control('path'), str(fixture) + ' ') == str(fixture) + ' '
        except TimeoutError:
            roundtrip = None
        samples.append({'t_ms': round(now_ms() - started, 3), 'busy': busy,
                        'roundtrip_ms': roundtrip, 'text_echo': echo_ok,
                        'sample_ms': round(now_ms() - probe_started, 3)})
        if not busy:
            break
        time.sleep(0.01)
    import_ms = round(now_ms() - started, 3)
    if not samples or samples[-1]['busy']:
        raise MeasurementFault('import did not complete within %d s' % timeout)

    found = op_search(host, expected_title,
                      lambda app: app.lb_count() == 1 and expected_title in app.lb_item(0),
                      lambda rows: len(rows) == 1 and expected_title in rows[0])
    busy_samples = [sample for sample in samples
                    if sample['busy'] and sample['roundtrip_ms'] is not None]
    return {'import_ms': import_ms, 'input_samples': samples,
            'busy_input_samples': len(busy_samples),
            'busy_input_p50_ms': median([s['roundtrip_ms'] for s in busy_samples]),
            'busy_input_max_ms': max([s['roundtrip_ms'] for s in busy_samples])
            if busy_samples else None,
            'input_timeouts': sum(1 for sample in samples if sample['roundtrip_ms'] is None),
            'post_import_search_ms': found['ms'], 'post_import_rows': found['rows'],
            'visible': True, 'fixture': str(fixture),
            'fixture_bytes': Path(fixture).stat().st_size,
            'fixture_sha256': sha256(fixture), 'title': expected_title}


def op_reset_top(host, limit=80):
    for _ in range(limit):
        if host.lb_top() == 0:
            return True
        host.wheel_up(4)
        time.sleep(0.03)
    return host.lb_top() == 0


# ---------------------------------------------------------------------------
# Profiles and cohorts
# ---------------------------------------------------------------------------

def fresh_profile(template, destination):
    shutil.copytree(template, destination)
    for name in ('host.ini', 'application.log'):
        path = destination / name
        if path.exists():
            path.unlink()
    for path in destination.glob('*product.sqlite*'):
        path.unlink()


def profile_bytes(directory):
    return {path.name: path.stat().st_size for path in sorted(directory.iterdir())
            if path.is_file()}


def run_launch(cohort, index, context):
    exe, font = context['exe'], context['font']
    work, out = context['work'], context['output']
    launch_id = '%s-%02d' % (cohort, index)
    record = {'launch_id': launch_id, 'cohort': cohort, 'index': index, 'ok': False,
              'faults': [], 'ops': {}, 'samples': [], 'window_ms': None,
              'started_utc': None, 'pid': None}
    if cohort in ('cold_shelf', 'import'):
        profile = work / 'profiles' / launch_id
        if profile.exists():
            shutil.rmtree(profile)
        fresh_profile(context['template'], profile)
        record['profile_strategy'] = 'fresh-sdk-library-copy'
    elif cohort == 'reading':
        profile = context['reading_profile']
        record['profile_strategy'] = 'shared-profile'
    else:
        profile = work / 'profiles' / 'warm_shelf-shared'
        if not profile.exists():
            shutil.copytree(context['template'], profile)
        record['profile_strategy'] = 'shared-profile'
    record['profile'] = str(profile)
    host = None
    try:
        host = Host(exe, font, profile, out / 'logs' / (launch_id + '.log'))
        record['pid'] = host.process.pid
        record['started_utc'] = host.started_utc
        if cohort == 'reading':
            record['ops']['first_screen'] = op_window(host)
            if index == 0:
                record['ops']['open'] = op_open(host, 'EXReader benchmark')
                key = record['ops']['open']['key']
            else:
                resume = op_resume(host, context.get('reading_key'))
                record['ops']['resume'] = resume
                key = resume['key']
            turns = []
            for _ in range(8):
                turn = op_page_turn(host, key)
                turns.append(turn)
                key = turn['to']
                record['samples'].append({'op': 'book_page_turn', 'ms': turn['ms'],
                                          'status': turn['status'], 'detail': turn['label']})
            record['ops']['page_turns'] = turns
            context['reading_key'] = key
        else:
            record['ops']['first_screen'] = op_first_screen(host)
            if cohort in ('cold_shelf', 'warm_shelf'):
                record['ops']['shelf_next_page'] = op_shelf_next_page(host)
                record['ops']['search'] = op_search(
                    host, 'Author %_!',
                    lambda app: app.lb_count() == 50 and 'Shelf 0017' in app.lb_item(1),
                    lambda rows: len(rows) == 50 and
                    all(number is not None and number % 17 == 0 for number in numbered(rows)))
                record['ops']['search_clear'] = op_search(
                    host, '',
                    lambda app: app.lb_count() == 50 and 'Shelf 0001' in app.lb_item(1),
                    lambda rows: len(rows) == 50 and numbered(rows) == list(range(50)))
                record['ops']['reset_top'] = op_reset_top(host)
            elif cohort == 'import':
                fixture = context['fixture'](index)
                planted = op_import(host, fixture, 'Perf Import %04d' % index)
                record['ops']['import'] = planted
                for sample in planted['input_samples']:
                    record['samples'].append({
                        'op': 'input_during_import',
                        'ms': sample['roundtrip_ms'] if sample['roundtrip_ms'] is not None else -1.0,
                        'status': 'ok' if sample['roundtrip_ms'] is not None else 'timeout',
                        'detail': 'busy=%s text_echo=%s' % (sample['busy'], sample['text_echo'])})
        record['window_ms'] = (record['ops'].get('first_screen') or {}).get('window_ms')
        record['memory_before_close'] = host.memory()
        record['peak'] = host.close()
        record['memory_samples'] = host.sampler.samples
        host = None
        record['profile_bytes'] = profile_bytes(profile)
        record['log_bytes'] = (out / 'logs' / (launch_id + '.log')).stat().st_size
        record['ok'] = True
    except Exception as error:
        record['faults'].append('%s: %s' % (type(error).__name__, error))
        if host is not None:
            try:
                record['peak'] = host.close()
                record['memory_samples'] = host.sampler.samples
            except Exception as error2:
                record['faults'].append('close: %s' % error2)
    finally:
        if cohort in ('cold_shelf', 'import') and profile.exists():
            shutil.rmtree(profile, ignore_errors=True)
    return record


# ---------------------------------------------------------------------------
# Preparation
# ---------------------------------------------------------------------------

def seed_corpus(template, seed_exe):
    template.mkdir(parents=True, exist_ok=True)
    library = template / 'library.sqlite'
    completed = subprocess.run([str(seed_exe), str(library)], capture_output=True, timeout=600)
    stdout = completed.stdout.decode('utf-8', 'replace').strip()
    if completed.returncode != 0:
        raise MeasurementFault('public-SDK seed program failed: '
                               + completed.stderr.decode('utf-8', 'replace'))
    report = json.loads(stdout.splitlines()[-1])
    if report.get('public_sdk_originals') != 2202 or report.get('created') != 2202:
        raise MeasurementFault('seed program did not create 2202 originals: ' + stdout)
    return {'seed_stdout': stdout, 'library_bytes': library.stat().st_size,
            'library_sha256': sha256(library)}


EXPECTED_BODY = 'Shelf original %04d. Read this book and return to the same shelf position.\n'


def verify_corpus(template):
    import sqlite3
    database = template / 'library.sqlite.product.sqlite'
    if not database.exists():
        raise MeasurementFault('product catalog was not created: ' + str(database))
    with sqlite3.connect(str(database)) as connection:
        rows = connection.execute(
            "SELECT title, source_bytes FROM reader_books WHERE format='txt' ORDER BY title"
        ).fetchall()
    if len(rows) != 2202:
        raise MeasurementFault('product catalog holds %d TXT originals' % len(rows))
    for number, (title, size) in enumerate(rows):
        if title != 'Shelf %04d' % number or size != len((EXPECTED_BODY % number).encode()):
            raise MeasurementFault('original %d differs: %r %d' % (number, title, size))
    return {'originals_in_catalog': len(rows), 'titles_and_bytes_exact': True,
            'catalog_sha256': sha256(database), 'catalog_bytes': database.stat().st_size}


def prepare(context):
    out, template = context['output'], context['template']
    template.mkdir(parents=True, exist_ok=True)
    prep = {'process_starts': 0}
    prep['seed'] = seed_corpus(template, context['seed'])

    # One unmeasured preparation launch builds the product catalog; the corpus
    # identity is then read back from that product catalog.
    prep['process_starts'] += 1
    host = Host(context['exe'], context['font'], template, out / 'logs' / 'prep-catalog.log')
    try:
        prep['first_screen'] = op_first_screen(host)
    finally:
        prep['peak'] = host.close()
    prep['corpus'] = verify_corpus(template)

    # A separate reading profile adds exactly one fixed multi-page packaged
    # book, so in-book paging and continue-reading do not alter the
    # 2202-original shelf corpus.
    reading = context['reading_profile']
    if reading.exists():
        shutil.rmtree(reading)
    shutil.copytree(template, reading)
    prep['process_starts'] += 1
    host = Host(context['exe'], context['font'], reading, out / 'logs' / 'prep-reading.log')
    try:
        op_first_screen(host)
        prep['reading_import'] = op_import(host, context['package'] / 'Sample-positive.epub',
                                           'EXReader benchmark')
    finally:
        prep['reading_peak'] = host.close()
    prep['reading_profile_bytes'] = profile_bytes(reading)
    return prep


def make_fixture(directory, index, size=16 << 20):
    path = directory / ('Perf Import %04d.txt' % index)
    if path.exists():
        return path
    header = 'Perf import fixture %04d. Read the shelf while an import runs.\n' % index
    block = 'line %04d keeps the import worker busy while input continues.\n'
    unit = (header + ''.join(block % number for number in range(512))).encode()
    with path.open('wb') as handle:
        written = 0
        while written < size:
            handle.write(unit)
            written += len(unit)
    return path


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------

def flatten(record):
    ops = record.get('ops') or {}
    first = ops.get('first_screen') or {}
    turns = [turn['ms'] for turn in (ops.get('page_turns') or [])]
    resume = ops.get('resume') or {}
    opened = ops.get('open') or {}
    planted = ops.get('import') or {}
    search = ops.get('search') or {}
    shelf = ops.get('shelf_next_page') or {}
    peak = record.get('peak') or {}
    return {
        'launch_id': record.get('launch_id'), 'cohort': record.get('cohort'),
        'index': record.get('index'), 'profile_strategy': record.get('profile_strategy'),
        'cold_warm': 'cold' if record.get('profile_strategy') == 'fresh-sdk-library-copy' else 'warm',
        'pid': record.get('pid'), 'ok': record.get('ok'),
        'faults': ' | '.join(record.get('faults') or []),
        'window_ms': record.get('window_ms') if record.get('window_ms') is not None
        else first.get('window_ms'),
        'rows_ms': first.get('rows_ms'),
        'first_screen_interactive_ms': first.get('first_screen_interactive_ms'),
        'first_screen_roundtrip_ms': first.get('roundtrip_ms'),
        'open_ms': opened.get('ms'),
        'resume_ms': resume.get('ms'),
        'resumed_page': json.dumps(resume.get('key')) if resume else '',
        'expected_page': json.dumps(resume.get('expected_key')) if resume else '',
        'resume_verified': resume.get('verified'),
        'page_turns': len(turns),
        'page_turn_p50_ms': median(turns),
        'page_turn_p95_ms': p95(turns),
        'shelf_next_page_ms': shelf.get('ms'),
        'shelf_rows_after_page': shelf.get('rows_after'),
        'search_ms': search.get('ms'),
        'search_rows': search.get('rows'),
        'import_ms': planted.get('import_ms'),
        'import_busy_input_samples': planted.get('busy_input_samples'),
        'import_busy_input_p50_ms': planted.get('busy_input_p50_ms'),
        'import_busy_input_max_ms': planted.get('busy_input_max_ms'),
        'import_input_timeouts': planted.get('input_timeouts'),
        'import_visible': planted.get('visible'),
        'peak_working_set_bytes': peak.get('peak_working_set_bytes'),
        'peak_private_bytes': peak.get('private_bytes'),
    }


FIELDS = ['launch_id', 'cohort', 'index', 'profile_strategy', 'cold_warm', 'pid', 'ok', 'faults',
          'window_ms', 'rows_ms', 'first_screen_interactive_ms', 'first_screen_roundtrip_ms',
          'open_ms', 'resume_ms', 'resumed_page', 'expected_page', 'resume_verified',
          'page_turns', 'page_turn_p50_ms', 'page_turn_p95_ms', 'shelf_next_page_ms',
          'shelf_rows_after_page', 'search_ms', 'search_rows', 'import_ms',
          'import_busy_input_samples', 'import_busy_input_p50_ms', 'import_busy_input_max_ms',
          'import_input_timeouts', 'import_visible', 'peak_working_set_bytes',
          'peak_private_bytes']


def write_csv(path, fields, rows):
    import csv
    with Path(path).open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def aggregate(records):
    cohorts = {}
    for record in records:
        cohorts.setdefault(record['cohort'], []).append(record)
    result = {}
    for cohort, group in sorted(cohorts.items()):
        ops = [record.get('ops') or {} for record in group]
        result[cohort] = {
            'launches': len(group),
            'complete_launches': sum(1 for record in group if record.get('ok')),
            'window_ms': summary_stats([(o.get('first_screen') or {}).get('window_ms') for o in ops]),
            'first_screen_interactive_ms': summary_stats(
                [(o.get('first_screen') or {}).get('first_screen_interactive_ms') for o in ops]),
            'rows_visible_ms': summary_stats(
                [(o.get('first_screen') or {}).get('rows_ms') for o in ops]),
            'open_ms': summary_stats([(o.get('open') or {}).get('ms') for o in ops]),
            'book_page_turn_ms': summary_stats(
                [turn['ms'] for o in ops for turn in (o.get('page_turns') or [])]),
            'shelf_next_page_ms': summary_stats([(o.get('shelf_next_page') or {}).get('ms') for o in ops]),
            'search_result_ms': summary_stats([(o.get('search') or {}).get('ms') for o in ops]),
            'search_clear_ms': summary_stats([(o.get('search_clear') or {}).get('ms') for o in ops]),
            'resume_ms': summary_stats([(o.get('resume') or {}).get('ms') for o in ops]),
            'import_ms': summary_stats([(o.get('import') or {}).get('import_ms') for o in ops]),
            'input_during_import_p50_ms': summary_stats(
                [(o.get('import') or {}).get('busy_input_p50_ms') for o in ops]),
            'input_during_import_max_ms': summary_stats(
                [(o.get('import') or {}).get('busy_input_max_ms') for o in ops]),
            'peak_working_set_bytes': summary_stats(
                [(record.get('peak') or {}).get('peak_working_set_bytes') for record in group],
                unit='bytes'),
            'input_timeout_samples': sum((o.get('import') or {}).get('input_timeouts', 0) for o in ops),
        }
    return result


def proposal(aggregates, cohort, metric, factor):
    stats = aggregates.get(cohort, {}).get(metric) or {}
    value = stats.get('p95')
    if value is None:
        return None
    return int(-(-value * factor // 1))


def build_summary(context, records, aggregates, environment_doc, prep):
    measured = len(records)
    per_cohort = {}
    for record in records:
        per_cohort[record['cohort']] = per_cohort.get(record['cohort'], 0) + 1
    complete = [record for record in records if record.get('ok')]
    resumes = [record['ops']['resume'] for record in records
               if (record.get('ops') or {}).get('resume')]
    turn_counts = [len(record['ops'].get('page_turns') or []) for record in records
                   if record['cohort'] == 'reading']
    input_samples = [(record['ops'].get('import') or {}).get('busy_input_samples') for record in records
                     if record['cohort'] == 'import']
    strategies = {'cold' if record['profile_strategy'] == 'fresh-sdk-library-copy' else 'warm'
                  for record in records}
    checks = {
        'thirty_or_more_independent_process_starts': measured >= 30,
        'at_least_ten_launches_per_named_cohort':
            len(per_cohort) >= 3 and all(count >= 10 for count in per_cohort.values()),
        'every_measured_launch_complete': len(complete) == measured,
        'cold_and_warm_strategies_recorded': {'cold', 'warm'} <= strategies,
        'window_appeared_each_launch':
            all(record.get('window_ms') is not None for record in records),
        'first_screen_interactive_observed_each_shelf_launch':
            all((record['ops'].get('first_screen') or {}).get('first_screen_interactive_ms') is not None
                for record in records if record['cohort'] != 'reading'),
        'shelf_pagination_observed': all(
            (record['ops'].get('shelf_next_page') or {}).get('rows_after', 0) >= 100
            for record in records if record['cohort'] in ('cold_shelf', 'warm_shelf')),
        'search_result_observed': all(
            (record['ops'].get('search') or {}).get('rows') == 50
            for record in records if record['cohort'] in ('cold_shelf', 'warm_shelf')),
        'eight_in_book_page_turns_per_reading_launch':
            bool(turn_counts) and all(count >= 8 for count in turn_counts),
        'continue_reading_observed': sum(1 for resume in resumes
                                         if resume.get('ms') is not None) >= 8,
        'continue_reading_page_verified': bool(resumes) and all(
            resume.get('verified') is True for resume in resumes),
        'import_input_responsiveness_observed':
            bool(input_samples) and all(count and count >= 1 for count in input_samples),
        'working_set_peak_observed': all(record.get('peak') for record in records),
        'artifact_identity_recorded': bool(environment_doc['artifacts']['exe_sha256']),
        'corpus_identity_recorded': bool((context.get('corpus') or {}).get('titles_and_bytes_exact')),
        'frame_time_not_measured': environment_doc['measurement']['frame_time_measured'] is False,
        'numeric_budget_not_enforced': True,
    }
    proposals = [
        {'metric': 'first_screen_interactive_ms', 'cohort': 'cold_shelf', 'statistic': 'p95',
         'proposal_ms': proposal(aggregates, 'cold_shelf', 'first_screen_interactive_ms', 1.5),
         'basis': 'cold cohort p95 plus 50% headroom; proposal only, requires product-owner ratification'},
        {'metric': 'first_screen_interactive_ms', 'cohort': 'warm_shelf', 'statistic': 'p95',
         'proposal_ms': proposal(aggregates, 'warm_shelf', 'first_screen_interactive_ms', 1.5),
         'basis': 'warm cohort p95 plus 50% headroom; proposal only'},
        {'metric': 'shelf_next_page_ms', 'cohort': 'warm_shelf', 'statistic': 'p95',
         'proposal_ms': proposal(aggregates, 'warm_shelf', 'shelf_next_page_ms', 2.0),
         'basis': 'wheel-to-next-batch p95 doubled; includes wheel traversal; proposal only'},
        {'metric': 'search_result_ms', 'cohort': 'warm_shelf', 'statistic': 'p95',
         'proposal_ms': proposal(aggregates, 'warm_shelf', 'search_result_ms', 2.0),
         'basis': 'query-to-visible-rows p95 doubled; includes the 200 ms host debounce; proposal only'},
        {'metric': 'book_page_turn_ms', 'cohort': 'reading', 'statistic': 'p95',
         'proposal_ms': proposal(aggregates, 'reading', 'book_page_turn_ms', 2.0),
         'basis': 'click-to-new-page-label p95 doubled; not a frame-time budget; proposal only'},
        {'metric': 'resume_ms', 'cohort': 'reading', 'statistic': 'p95',
         'proposal_ms': proposal(aggregates, 'reading', 'resume_ms', 1.5),
         'basis': 'launch-to-restored-page p95 plus 50% headroom; proposal only'},
        {'metric': 'input_during_import_p50_ms', 'cohort': 'import', 'statistic': 'p95',
         'proposal_ms': proposal(aggregates, 'import', 'input_during_import_p50_ms', 4.0),
         'basis': 'busy-window input round-trip p95 times four to cover a 100 ms line; proposal only'},
        {'metric': 'peak_working_set_bytes', 'cohort': 'cold_shelf', 'statistic': 'p95',
         'proposal_bytes': proposal(aggregates, 'cold_shelf', 'peak_working_set_bytes', 1.25),
         'basis': 'shelf-only cold peak plus 25%; the import cohort buffer is excluded; proposal only'},
    ]
    return {
        'schema': 1,
        'complete': len(complete) == measured and measured >= 30,
        'source_sha': environment_doc['source_sha'],
        'run_id': environment_doc['run_id'],
        'attempt': environment_doc['attempt'],
        'measured_process_starts': measured,
        'preparation_process_starts': prep.get('process_starts', 0),
        'process_starts_total': measured + prep.get('process_starts', 0),
        'cohorts': per_cohort,
        'checks': checks,
        'checks_passed': sum(1 for value in checks.values() if value is True),
        'checks_total': len(checks),
        'problems': [{'launch_id': record['launch_id'], 'faults': record['faults']}
                     for record in records if not record.get('ok')],
        'performance_accepted': False,
        'performance_reason': 'This package measures the baseline host and proposes budgets only. '
                              'No numeric product budget is enforced here and no observed latency is '
                              'a frame time.',
        'budget_enforced': False,
        'proposed_budgets': proposals,
        'frame_time': {'measured': False,
                       'reason': environment_doc['measurement']['frame_time_reason']},
        'limits': [
            'External end-to-end UI latency only; no in-application frame or present signal exists on '
            'this path.',
            'Operating-system disk cache and co-tenant load on the shared cloud runner are not '
            'controlled; the cold/warm labels describe the profile strategy only.',
            'Cold launches copy the seeded SDK library file, so the product catalog is rebuilt on '
            'every cold launch; warm launches reuse the populated profile.',
            'The import cohort imports a fixed 16 MiB generated TXT per launch, so its peak working '
            'set includes the host import buffer and is not comparable with the shelf cohorts.',
            'Book paging and continue-reading use one fixed packaged multi-page book in a separate '
            'profile; the 2202-original shelf corpus itself is unchanged.',
            'UI messages are delivered to the real native controls and serviced by the product UI '
            'thread; they are not SendInput-level hardware injection.',
        ],
        'environment': environment_doc,
        'preparation': prep,
        'aggregates': aggregates,
    }


# ---------------------------------------------------------------------------
# Self-check (no Win32 access)
# ---------------------------------------------------------------------------

def self_check():
    assert page_key('第 3 页 · EPUB · 字号 150%') == [1, 3]
    assert page_key('章 2 · 本章第 7 页 · EPUB · 字号 150%') == [2, 7]
    assert page_key('第 4 / 9 页 · PDF · 缩放 100%') == [0, 4]
    assert page_key('未打开书籍') is None
    assert row_number('《Shelf 0042》 — Reader · TXT') == 42
    assert row_number('《EXReader benchmark》 — 未知作者 · EPUB') is None
    assert median([1, 2, 3]) == 2.0
    assert median([1, 2, 3, 4]) == 2.5
    assert p95(list(range(1, 101))) == 95.0
    assert p95([7]) == 7.0
    assert summary_stats([]) == {'unit': 'ms', 'n': 0, 'min': None, 'p50': None,
                                 'p95': None, 'max': None}
    assert summary_stats([3, 1, 2])['p50'] == 2.0
    assert proposal({'x': {'m': {'p95': 10.0}}}, 'x', 'm', 1.5) == 15
    assert proposal({'x': {}}, 'x', 'm', 1.5) is None
    record = {'launch_id': 'cold-00', 'cohort': 'cold_shelf', 'index': 0,
              'profile_strategy': 'fresh-sdk-library-copy', 'ok': True, 'faults': [],
              'window_ms': 9.0,
              'ops': {'first_screen': {'window_ms': 10.0, 'rows_ms': 20.0,
                                       'first_screen_interactive_ms': 21.0, 'roundtrip_ms': 1.0,
                                       'first_row_count': 50, 'first_rows': []},
                      'shelf_next_page': {'ms': 30.0, 'rows_after': 100},
                      'search': {'ms': 40.0, 'rows': 50}},
              'peak': {'peak_working_set_bytes': 1000, 'private_bytes': 900}}
    row = flatten(record)
    assert row['first_screen_interactive_ms'] == 21.0 and row['search_ms'] == 40.0
    assert row['cold_warm'] == 'cold' and row['page_turns'] == 0
    assert row['peak_working_set_bytes'] == 1000
    aggregates = aggregate([record])
    assert aggregates['cold_shelf']['launches'] == 1
    assert aggregates['cold_shelf']['search_result_ms']['p50'] == 40.0
    assert aggregates['cold_shelf']['peak_working_set_bytes']['unit'] == 'bytes'
    assert len(FIELDS) == len(set(FIELDS))
    print(json.dumps({'self_check': 'passed', 'fields': len(FIELDS)}))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path)
    parser.add_argument('--seed', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--work', type=Path)
    parser.add_argument('--cohorts', default='cold_shelf,warm_shelf,reading,import')
    parser.add_argument('--launches-per-cohort', type=int, default=12)
    parser.add_argument('--self-check', action='store_true')
    args = parser.parse_args()
    if args.self_check:
        self_check()
        return 0
    if os.name != 'nt':
        raise SystemExit('This observation runs on Windows only')
    for name in ('package', 'seed', 'output'):
        if getattr(args, name) is None:
            parser.error('--%s is required' % name)
    package = args.package.resolve()
    exe = package / 'EXReader.exe'
    font = package / 'Reader.otf'
    seed = args.seed.resolve()
    for path in (exe, font, seed):
        if not Path(path).exists():
            raise SystemExit('missing input: ' + str(path))
    output = args.output.resolve()
    if output.exists():
        raise SystemExit('choose a fresh evidence directory')
    output.mkdir(parents=True)
    (output / 'logs').mkdir()
    work = (args.work or (output.parent / (output.name + '-work'))).resolve()
    if work.exists():
        shutil.rmtree(work)
    (work / 'fixtures').mkdir(parents=True)
    (work / 'profiles').mkdir()

    seed_source_sha = hashlib.sha256(
        subprocess.check_output(['git', 'show', 'HEAD:tests/windows_host/seed_shelf.c'])).hexdigest()
    environment_doc = environment(package, exe, font, seed, seed_source_sha)

    context = {'package': package, 'exe': exe, 'font': font, 'output': output, 'work': work,
               'seed': seed, 'template': work / 'template',
               'reading_profile': work / 'profiles' / 'reading-profile',
               'fixture': lambda index: make_fixture(work / 'fixtures', index)}
    records, prep, aggregates, summary = [], {}, {}, {}
    try:
        prep = prepare(context)
        context['corpus'] = prep['corpus']
        for cohort in [name for name in args.cohorts.split(',') if name]:
            for index in range(args.launches_per_cohort):
                record = run_launch(cohort, index, context)
                record.pop('_sampler', None)
                records.append(record)
                print(json.dumps(flatten(record), ensure_ascii=False), flush=True)
    finally:
        aggregates = aggregate(records)
        summary = build_summary(context, records, aggregates, environment_doc, prep)
        (output / 'environment.json').write_text(json.dumps(environment_doc, indent=2) + '\n',
                                                 encoding='utf-8')
        (output / 'preparation.json').write_text(json.dumps(prep, indent=2) + '\n', encoding='utf-8')
        (output / 'per-launch.json').write_text(json.dumps(records, indent=2) + '\n', encoding='utf-8')
        (output / 'per-launch.jsonl').write_text(
            ''.join(json.dumps(record, ensure_ascii=False) + '\n' for record in records),
            encoding='utf-8')
        write_csv(output / 'per-launch.csv', FIELDS, [flatten(record) for record in records])
        write_csv(output / 'samples.csv',
                  ['launch_id', 'cohort', 'op', 'index', 'ms', 'status', 'detail'],
                  [{'launch_id': record['launch_id'], 'cohort': record['cohort'],
                    'op': sample['op'], 'index': index, 'ms': sample['ms'],
                    'status': sample['status'], 'detail': sample['detail']}
                   for record in records
                   for index, sample in enumerate(record.get('samples') or [])])
        write_csv(output / 'memory.csv',
                  ['launch_id', 'cohort', 't_ms', 'working_set_bytes',
                   'peak_working_set_bytes', 'private_bytes'],
                  [{'launch_id': record['launch_id'], 'cohort': record['cohort'],
                    't_ms': sample[0], 'working_set_bytes': sample[1],
                    'peak_working_set_bytes': sample[2], 'private_bytes': sample[3]}
                   for record in records for sample in (record.get('memory_samples') or [])])
        (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'measured': len(records), 'complete': summary.get('complete'),
                          'checks': summary.get('checks_passed'),
                          'of': summary.get('checks_total'),
                          'problems': len(summary.get('problems') or [])}, ensure_ascii=False))
        memory_rows = sum(len(record.get('memory_samples') or []) for record in records)
        print('memory samples: %d' % memory_rows)
    incomplete = [record['launch_id'] for record in records if not record.get('ok')]
    if incomplete or len(records) < 30:
        print('incomplete samples: ' + ', '.join(incomplete), file=sys.stderr)
        return 3
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
