# SPDX-License-Identifier: MIT
"""E1 environment provenance and E3 advisory identity; never grants acceptance."""
import ctypes
import os
from pathlib import Path
import platform
import subprocess


def environment(build=None):
    memory = None
    if os.name == 'nt':
        class Memory(ctypes.Structure):
            _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [(name, ctypes.c_ulonglong) for name in ('physical', 'available', 'page', 'available_page', 'virtual', 'available_virtual', 'extended')]
        value = Memory(); value.length = ctypes.sizeof(value)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)):
            memory = value.physical
    else:
        try:
            memory = os.sysconf('SC_PHYS_PAGES') * os.sysconf('SC_PAGE_SIZE')
        except (ValueError, OSError, AttributeError):
            try:
                memory = int(subprocess.check_output(['sysctl', '-n', 'hw.memsize'], text=True))
            except (OSError, ValueError, subprocess.SubprocessError):
                pass
    cpu = platform.processor()
    cpuinfo = Path('/proc/cpuinfo')
    if cpuinfo.is_file():
        cpu = next((line.split(':', 1)[1].strip() for line in cpuinfo.read_text().splitlines() if line.startswith('model name')), cpu)
    cache = {}
    path = Path(build or 'build/native') / 'CMakeCache.txt'
    if path.is_file():
        for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
            if '=' in line and ':' in line.split('=', 1)[0]:
                key, value = line.split('=', 1); cache[key.split(':', 1)[0]] = value
    compiler = cache.get('CMAKE_C_COMPILER') or os.environ.get('CC') or 'cc'
    try:
        version = subprocess.check_output([compiler, '--version'], text=True, stderr=subprocess.STDOUT).strip()
    except (OSError, subprocess.SubprocessError):
        version = 'unknown'
    return {'cpu': cpu or 'unknown', 'cores': os.cpu_count(), 'memory_bytes': memory,
            'os': platform.system(), 'os_version': platform.version(), 'kernel': platform.release(),
            'compiler': version, 'flags': {key: value for key, value in cache.items() if key.startswith('CMAKE_C_FLAGS')},
            'runner_label': os.environ.get('PERF_RUNNER_LABEL', 'unknown')}


def advisory(report, build=None):
    report['advisory'] = True
    report['accepted'] = False
    report['acceptance_scope'] = 'diagnostic measurements only; never performance acceptance'
    report['policy'] = {'issue': 32, 'expires_at': '2026-12-15T00:00:00-05:00', 'restore_requires': 'E1 and one strict re-verification'}
    report['measurement_environment'] = environment(build)
    return report
