# SPDX-License-Identifier: MIT
"""Run the real packaged host under a NETWORK-logon primary token (no credential-capable logon session).

Nothing here impersonates inside the host: the host process itself is created with the token, so every
thread it starts (including the credential worker) uses that primary token. The module also reports what
the host's threads actually hold, so "same token" is observed, not assumed. Windows only; secrets are
never handled here beyond the synthetic local account password, which is random and never printed.
"""
import ctypes as C
from ctypes import wintypes as W
import json
import os
import secrets
import subprocess
import threading
import time

K = C.WinDLL('kernel32', use_last_error=True)
A = C.WinDLL('advapi32', use_last_error=True)
U = C.WinDLL('user32', use_last_error=True)
S = C.WinDLL('secur32', use_last_error=True)

LOGON32_LOGON_NETWORK, LOGON32_PROVIDER_DEFAULT = 3, 0
TOKEN_ALL_ACCESS = 0xF01FF
PROCESS_QUERY_LIMITED, PROCESS_TERMINATE, SYNCHRONIZE = 0x1000, 0x1, 0x100000
THREAD_QUERY_LIMITED = 0x800
TH32CS_SNAPTHREAD = 0x4
LOGON_TYPES = {2: 'Interactive', 3: 'Network', 4: 'Batch', 5: 'Service', 7: 'Unlock', 8: 'NetworkCleartext',
               9: 'NewCredentials', 10: 'RemoteInteractive', 11: 'CachedInteractive'}

for fn, restype in ((K.OpenProcess, W.HANDLE), (K.OpenThread, W.HANDLE), (K.CreateToolhelp32Snapshot, W.HANDLE),
                    (K.GetCurrentProcess, W.HANDLE), (K.GetCurrentThread, W.HANDLE)):
    fn.restype = restype


class THREADENTRY32(C.Structure):
    _fields_ = [('dwSize', W.DWORD), ('cntUsage', W.DWORD), ('th32ThreadID', W.DWORD), ('th32OwnerProcessID', W.DWORD),
                ('tpBasePri', W.LONG), ('tpDeltaPri', W.LONG), ('dwFlags', W.DWORD)]


class LUID(C.Structure):
    _fields_ = [('Low', W.DWORD), ('High', W.LONG)]


class TOKEN_STATISTICS(C.Structure):
    _fields_ = [('TokenId', LUID), ('AuthenticationId', LUID), ('ExpirationTime', C.c_longlong), ('TokenType', W.DWORD),
                ('ImpersonationLevel', W.DWORD), ('DynamicCharged', W.DWORD), ('DynamicAvailable', W.DWORD),
                ('GroupCount', W.DWORD), ('PrivilegeCount', W.DWORD), ('ModifiedId', LUID)]


class LSA_STRING(C.Structure):
    _fields_ = [('Length', W.USHORT), ('MaximumLength', W.USHORT), ('Buffer', C.c_void_p)]


class LOGON_SESSION_DATA(C.Structure):
    _fields_ = [('Size', W.ULONG), ('LogonId', LUID), ('UserName', LSA_STRING), ('LogonDomain', LSA_STRING),
                ('AuthenticationPackage', LSA_STRING), ('LogonType', W.ULONG), ('Session', W.ULONG)]


class STARTUPINFOW(C.Structure):
    _fields_ = [('cb', W.DWORD), ('lpReserved', W.LPWSTR), ('lpDesktop', W.LPWSTR), ('lpTitle', W.LPWSTR),
                ('dwX', W.DWORD), ('dwY', W.DWORD), ('dwXSize', W.DWORD), ('dwYSize', W.DWORD),
                ('dwXCountChars', W.DWORD), ('dwYCountChars', W.DWORD), ('dwFillAttribute', W.DWORD), ('dwFlags', W.DWORD),
                ('wShowWindow', W.WORD), ('cbReserved2', W.WORD), ('lpReserved2', C.c_void_p),
                ('hStdInput', W.HANDLE), ('hStdOutput', W.HANDLE), ('hStdError', W.HANDLE)]


class PROCESS_INFORMATION(C.Structure):
    _fields_ = [('hProcess', W.HANDLE), ('hThread', W.HANDLE), ('dwProcessId', W.DWORD), ('dwThreadId', W.DWORD)]


def _name(value):
    return C.wstring_at(value.Buffer, value.Length // 2) if value.Buffer else ''


def _fail(what):
    return OSError('%s failed: %d' % (what, C.get_last_error()))


def _token_info(handle):
    """TokenType, impersonation level, logon id/type and session of one token handle (no secrets)."""
    stat = TOKEN_STATISTICS();size = W.DWORD()
    if not A.GetTokenInformation(handle, 10, C.byref(stat), C.sizeof(stat), C.byref(size)):
        raise _fail('GetTokenInformation(TokenStatistics)')
    session = W.DWORD()
    A.GetTokenInformation(handle, 12, C.byref(session), 4, C.byref(size))
    data = C.c_void_p();logon_type = None;user = None
    luid = LUID(stat.AuthenticationId.Low, stat.AuthenticationId.High)
    if S.LsaGetLogonSessionData(C.byref(luid), C.byref(data)) == 0 and data.value:
        row = C.cast(data, C.POINTER(LOGON_SESSION_DATA)).contents
        logon_type = LOGON_TYPES.get(row.LogonType, row.LogonType);user = _name(row.LogonDomain) + '\\' + _name(row.UserName)
        S.LsaFreeReturnBuffer(data)
    return {'token_type': {1: 'primary', 2: 'impersonation'}.get(stat.TokenType, stat.TokenType),
            'impersonation_level': stat.ImpersonationLevel if stat.TokenType == 2 else None,
            'logon_id': '%08x:%08x' % (stat.AuthenticationId.High & 0xffffffff, stat.AuthenticationId.Low),
            'logon_type': logon_type, 'logon_user': user, 'session_id': session.value}


def process_token_report(pid):
    process = K.OpenProcess(PROCESS_QUERY_LIMITED, False, pid)
    if not process:
        raise _fail('OpenProcess')
    token = W.HANDLE()
    try:
        if not A.OpenProcessToken(process, 0x8, C.byref(token)):
            raise _fail('OpenProcessToken')
        try:
            return _token_info(token)
        finally:
            K.CloseHandle(token)
    finally:
        K.CloseHandle(process)


def thread_ids(pid):
    snapshot = K.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
    found = set()
    entry = THREADENTRY32();entry.dwSize = C.sizeof(entry)
    ok = K.Thread32First(snapshot, C.byref(entry))
    while ok:
        if entry.th32OwnerProcessID == pid:
            found.add(entry.th32ThreadID)
        ok = K.Thread32Next(snapshot, C.byref(entry))
    K.CloseHandle(snapshot)
    return found


def thread_token_report(tid):
    """OpenThreadToken(OpenAsSelf=FALSE): ERROR_NO_TOKEN (1008) means the thread runs on the process primary token."""
    thread = K.OpenThread(THREAD_QUERY_LIMITED, False, tid)
    if not thread:
        return {'tid': tid, 'open_thread_error': C.get_last_error()}
    token = W.HANDLE()
    try:
        if A.OpenThreadToken(thread, 0x8, False, C.byref(token)):
            try:
                return dict(_token_info(token), tid=tid, thread_token='present')
            finally:
                K.CloseHandle(token)
        return {'tid': tid, 'thread_token': 'none', 'open_thread_token_error': C.get_last_error()}
    finally:
        K.CloseHandle(thread)


class ThreadSampler(threading.Thread):
    """Poll the host's threads while an action runs; keep each thread id that was not present at idle."""

    def __init__(self, pid):
        super().__init__(daemon=True)
        self.pid, self.baseline, self.new, self.stop_flag = pid, thread_ids(pid), {}, threading.Event()

    def run(self):
        while not self.stop_flag.is_set():
            for tid in thread_ids(self.pid) - self.baseline:
                if tid not in self.new:
                    self.new[tid] = thread_token_report(tid)
            time.sleep(0.002)

    def finish(self):
        self.stop_flag.set();self.join(5)
        return list(self.new.values())


def create_user():
    name = 'exrh02' + secrets.token_hex(4)
    password = 'Aa1!' + secrets.token_urlsafe(18)
    subprocess.run(['net', 'user', name, password, '/add', '/y'], check=True, capture_output=True)
    return name, password


def delete_user(name):
    subprocess.run(['net', 'user', name, '/delete'], capture_output=True)


def grant(path, name, rights):
    subprocess.run(['icacls', str(path), '/grant', '%s:(OI)(CI)%s' % (name, rights), '/T', '/C', '/Q'], check=True, capture_output=True)


def open_desktop_to_everyone():
    """Allow the synthetic account to attach to winsta0\\default of this throw-away runner."""
    sd = C.c_void_p()
    if not A.ConvertStringSecurityDescriptorToSecurityDescriptorW('D:(A;;GA;;;WD)', 1, C.byref(sd), None):
        raise _fail('ConvertStringSecurityDescriptorToSecurityDescriptorW')
    present, default, dacl = W.BOOL(), W.BOOL(), C.c_void_p()
    A.GetSecurityDescriptorDacl.argtypes = [C.c_void_p, C.POINTER(W.BOOL), C.POINTER(C.c_void_p), C.POINTER(W.BOOL)]
    A.GetSecurityDescriptorDacl(sd, C.byref(present), C.byref(dacl), C.byref(default))
    U.GetProcessWindowStation.restype = W.HANDLE
    U.OpenDesktopW.restype = W.HANDLE
    winsta = U.GetProcessWindowStation()
    desktop = U.OpenDesktopW('Default', 0, False, 0x00040000 | 0x00020000 | 0x00080000)  # READ_CONTROL|WRITE_DAC|... 
    results = {}
    A.SetSecurityInfo.argtypes = [W.HANDLE, W.DWORD, W.DWORD, C.c_void_p, C.c_void_p, C.c_void_p, C.c_void_p]
    results['winsta'] = A.SetSecurityInfo(winsta, 7, 4, None, None, dacl, None)
    results['desktop'] = A.SetSecurityInfo(desktop, 7, 4, None, None, dacl, None) if desktop else 'no desktop handle'
    return results


def network_primary_token(name, password):
    impersonation = W.HANDLE()
    if not A.LogonUserW(name, '.', password, LOGON32_LOGON_NETWORK, LOGON32_PROVIDER_DEFAULT, C.byref(impersonation)):
        raise _fail('LogonUserW(NETWORK)')
    primary = W.HANDLE()
    if not A.DuplicateTokenEx(impersonation, TOKEN_ALL_ACCESS, None, 2, 1, C.byref(primary)):
        raise _fail('DuplicateTokenEx')
    K.CloseHandle(impersonation)
    return primary


def enable_privilege(name):
    token = W.HANDLE()
    if not A.OpenProcessToken(K.GetCurrentProcess(), 0x28, C.byref(token)):
        return False
    luid = LUID()
    if not A.LookupPrivilegeValueW(None, name, C.byref(luid)):
        return False

    class TP(C.Structure):
        _fields_ = [('Count', W.DWORD), ('Luid', LUID), ('Attributes', W.DWORD)]
    tp = TP(1, luid, 2)
    A.AdjustTokenPrivileges(token, False, C.byref(tp), 0, None, None)
    ok = C.get_last_error() == 0
    K.CloseHandle(token)
    return ok


def current_session():
    session = W.DWORD()
    K.ProcessIdToSessionId(K.GetCurrentProcessId(), C.byref(session))
    return session.value


def spawn(exe_args, token, notes):
    """CreateProcessAsUserW first, CreateProcessWithTokenW second; every outcome goes to `notes`."""
    for privilege in ('SeAssignPrimaryTokenPrivilege', 'SeIncreaseQuotaPrivilege', 'SeImpersonatePrivilege', 'SeTcbPrivilege'):
        notes['privilege_' + privilege] = enable_privilege(privilege)
    session = W.DWORD(current_session())
    notes['token_session_set'] = bool(A.SetTokenInformation(token, 12, C.byref(session), 4)) or C.get_last_error()
    startup = STARTUPINFOW();startup.cb = C.sizeof(startup);startup.lpDesktop = 'winsta0\\default'
    info = PROCESS_INFORMATION()
    command = C.create_unicode_buffer(subprocess.list2cmdline(exe_args), 32768)
    if A.CreateProcessAsUserW(token, None, command, None, None, False, 0x00000400, None, None, C.byref(startup), C.byref(info)):
        notes['spawn'] = 'CreateProcessAsUserW'
    else:
        notes['CreateProcessAsUserW_error'] = C.get_last_error()
        command = C.create_unicode_buffer(subprocess.list2cmdline(exe_args), 32768)
        A.CreateProcessWithTokenW.argtypes = [W.HANDLE, W.DWORD, W.LPCWSTR, W.LPWSTR, W.DWORD, C.c_void_p, W.LPCWSTR,
                                              C.POINTER(STARTUPINFOW), C.POINTER(PROCESS_INFORMATION)]
        if not A.CreateProcessWithTokenW(token, 0, None, command, 0x00000400, None, None, C.byref(startup), C.byref(info)):
            notes['CreateProcessWithTokenW_error'] = C.get_last_error()
            raise OSError(json.dumps(notes))
        notes['spawn'] = 'CreateProcessWithTokenW'
    K.CloseHandle(info.hThread)
    return info.hProcess, info.dwProcessId


class HostProcess:
    """The slice of subprocess.Popen the retained UI driver uses."""
    TimeoutExpired = subprocess.TimeoutExpired

    def __init__(self, handle, pid):
        self.handle, self.pid, self.returncode = handle, pid, None

    def poll(self):
        if self.returncode is None:
            code = W.DWORD()
            K.GetExitCodeProcess(self.handle, C.byref(code))
            if code.value != 259:
                self.returncode = code.value
        return self.returncode

    def wait(self, timeout=None):
        end = None if timeout is None else time.monotonic() + timeout
        while self.poll() is None:
            if end is not None and time.monotonic() > end:
                raise subprocess.TimeoutExpired('host', timeout)
            time.sleep(0.02)
        return self.returncode

    def kill(self):
        if self.poll() is None:
            K.TerminateProcess(self.handle, 1)


class SubprocessShim:
    """Rebinding `subprocess` inside the retained driver module only; every launch uses the network token."""
    TimeoutExpired, STDOUT, PIPE, DEVNULL = subprocess.TimeoutExpired, subprocess.STDOUT, subprocess.PIPE, subprocess.DEVNULL

    def __init__(self, token, notes):
        self.token, self.notes, self.launches = token, notes, []

    def Popen(self, args, **unused):
        record = {}
        handle, pid = spawn([str(a) for a in args], self.token, record)
        record['pid'] = pid
        record['process_token'] = process_token_report(pid)
        self.launches.append(record)
        return HostProcess(handle, pid)

    def __getattr__(self, name):
        return getattr(subprocess, name)
