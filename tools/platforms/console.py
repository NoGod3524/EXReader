"""Send one command to the task's QEMU serial port; fail on nonzero guest exit."""
import argparse
import re
import socket
import sys
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--port', type=int, default=44444)
parser.add_argument('--login', action='store_true')
parser.add_argument('--timeout', type=int, default=600)
parser.add_argument('command')
args = parser.parse_args()
with socket.create_connection(('127.0.0.1', args.port), timeout=10) as connection:
    connection.settimeout(1)
    if args.login:
        connection.sendall(b'\n')
        pending = ''
        deadline = time.monotonic() + 60
        while 'login:' not in pending and time.monotonic() < deadline:
            try:
                pending += connection.recv(65536).decode('utf-8', errors='replace')
            except TimeoutError:
                continue
        if 'login:' not in pending:
            raise TimeoutError('login prompt not observed')
        connection.sendall(b'root\n')
        pending = ''
        while ':~#' not in pending and time.monotonic() < deadline:
            try:
                pending += connection.recv(65536).decode('utf-8', errors='replace')
            except TimeoutError:
                continue
        if ':~#' not in pending:
            raise TimeoutError('root prompt not observed')
    # Split the marker in the echoed command, so it cannot be mistaken for output.
    connection.sendall((args.command + "; rc=$?; printf '\\n__PLAT%s=%s\\n' DONE \"$rc\"\n").encode())
    output = ''
    until = time.monotonic() + args.timeout
    while time.monotonic() < until:
        try:
            chunk = connection.recv(65536)
        except TimeoutError:
            continue
        if not chunk:
            raise RuntimeError('serial connection closed before completion')
        text = chunk.decode('utf-8', errors='replace')
        print(text, end='', flush=True)
        output += text
        match = re.search(r'__PLATDONE=(\d+)', output)
        if match:
            sys.exit(int(match[1]))
    raise TimeoutError('guest command timed out')
