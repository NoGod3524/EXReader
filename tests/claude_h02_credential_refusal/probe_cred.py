# SPDX-License-Identifier: MIT
"""Same-token API probe. NOT host evidence: it only shows what Credential Manager returns to a process with this token."""
import ctypes as C
from ctypes import wintypes as W
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import token_host as T


class CRED(C.Structure):
    _fields_ = [('Flags', W.DWORD), ('Type', W.DWORD), ('TargetName', W.LPWSTR), ('Comment', W.LPWSTR),
                ('LastWritten', W.FILETIME), ('CredentialBlobSize', W.DWORD), ('CredentialBlob', C.c_void_p),
                ('Persist', W.DWORD), ('AttributeCount', W.DWORD), ('Attributes', C.c_void_p),
                ('TargetAlias', W.LPWSTR), ('UserName', W.LPWSTR)]


def main():
    out = Path(sys.argv[1])
    target = 'EXReaderH02Probe/' + sys.argv[2]
    blob = (C.c_ubyte * 4)(1, 2, 3, 4)
    cred = CRED();cred.Type = 1;cred.TargetName = target;cred.CredentialBlobSize = 4
    cred.CredentialBlob = C.cast(blob, C.c_void_p);cred.Persist = 2;cred.UserName = 'probe'
    A = C.WinDLL('advapi32', use_last_error=True)
    result = {'pid': C.windll.kernel32.GetCurrentProcessId()}
    result['CredWriteW'] = 0 if A.CredWriteW(C.byref(cred), 0) else C.get_last_error()
    pointer = C.c_void_p()
    result['CredReadW'] = 0 if A.CredReadW(target, 1, 0, C.byref(pointer)) else C.get_last_error()
    result['CredDeleteW'] = 0 if A.CredDeleteW(target, 1, 0) else C.get_last_error()
    result['process_token'] = T.process_token_report(result['pid'])
    out.write_text(json.dumps(result), encoding='utf-8')


main()
