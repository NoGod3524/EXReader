# SPDX-License-Identifier: MIT
"""Run the console WebDAV acceptance without starting the GUI host.

Usage: python -X utf8 examples/windows/check_shell_sync.py CHECK_SYNC_EXE OUTPUT
"""
import json
from pathlib import Path
import struct
import subprocess
import sys

SCENARIOS = {
    'merge': 'MERGE commutative=1',
    'first-upload': 'FIRST-UPLOAD',
    'incremental': 'INCREMENTAL',
    'conflict': 'CONFLICT-2',
    'tombstone': 'DELETE tombstone',
    'lww': 'LWW progress',
    '401': 'ERROR-401',
    '404': 'ERROR-404',
    'timeout': 'ERROR-TIMEOUT',
    '403': 'ERROR-403',
    'retry': 'RETRY two HTTP 500',
    'corrupt-remote': 'CORRUPT-REMOTE',
    'offline-queue': 'OFFLINE server down',
    'reconnect': 'RECONNECT 3/3',
    'credentials': 'CREDENTIALS',
}


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    exe, out = Path(sys.argv[1]).resolve(strict=True), Path(sys.argv[2])
    # Refuse GUI executables even if passed by mistake. PE subsystem 3 = console.
    data = exe.read_bytes()
    pe = struct.unpack_from('<I', data, 0x3c)[0]
    if exe.name.lower() != 'check_sync.exe' or data[pe:pe+4] != b'PE\0\0' or struct.unpack_from('<H', data, pe+24+68)[0] != 3:
        raise SystemExit('Expected the console check_sync.exe (PE subsystem 3)')
    out.mkdir(parents=True, exist_ok=True)
    result = subprocess.run([str(exe)], capture_output=True, timeout=90,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    text = result.stdout.decode('utf-8', errors='replace')
    (out / 'sync-console.log').write_bytes(result.stdout + result.stderr)
    checks = {name: marker in text for name, marker in SCENARIOS.items()}
    accepted = result.returncode == 0 and all(checks.values()) and 'windows_created=0' in text
    (out / 'sync-console.json').write_text(json.dumps(dict(
        command=[str(exe)], exit_code=result.returncode, accepted=accepted, scenarios=checks), indent=2) + '\n', encoding='utf-8')
    print(text, end='')
    print(f'{sum(checks.values())}/15 scenarios; exit_code={result.returncode}')
    return int(not accepted)


if __name__ == '__main__':
    raise SystemExit(main())
