"""Run one command, retain its output and exit status, append the task journal."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        parser.error('command required')
    args.log.parent.mkdir(parents=True, exist_ok=True)
    start = datetime.now(timezone.utc).isoformat()
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1')
    with args.log.open('w', encoding='utf-8') as log:
        log.write(f'UTC: {start}\nCWD: {Path.cwd()}\nARGV: {json.dumps(command)}\n')
        log.flush()
        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       text=True, encoding='utf-8', errors='replace', env=env)
            for line in process.stdout:
                log.write(line)
                log.flush()
                print(line, end='', flush=True)
            code = process.wait()
        except OSError as exc:
            log.write(f'{exc}\n')
            code = 127
        end = datetime.now(timezone.utc).isoformat()
        log.write(f'EXIT_CODE: {code}\nEND_UTC: {end}\n')
    with (ROOT / 'PLATFORMS2-OUT.txt').open('a', encoding='utf-8') as journal:
        journal.write(f'[{end}] exit={code}; log={args.log.as_posix()}; argv={json.dumps(command)}\n')
    return code


if __name__ == '__main__':
    sys.exit(main())
