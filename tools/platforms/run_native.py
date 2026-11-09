"""Compile and run the shared-library probe twice; reject a moved annotation."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--smoke', type=Path, help='existing prepare_smoke.py directory')
    parser.add_argument('--cc', default='gcc' if os.name == 'nt' else 'cc')
    args = parser.parse_args()
    library, out = args.library.resolve(strict=True), args.out.resolve()
    if any((out / name).exists() for name in ('create.log', 'reopen.log', 'result.json')):
        parser.error('output already contains a run; choose a fresh output directory')
    out.mkdir(parents=True, exist_ok=True)
    smoke = args.smoke.resolve() if args.smoke else out / 'smoke'
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    env['PATH'] = str(library.parent) + os.pathsep + env.get('PATH', '')
    commands = []

    def run(command, expected=0):
        command = [str(x) for x in command]
        commands.append(command)
        print('ARGV:', command, flush=True)
        result = subprocess.run(command, env=env)
        if expected == 0 and result.returncode != 0:
            raise RuntimeError(f'command exit={result.returncode}')
        if expected != 0 and result.returncode == 0:
            raise RuntimeError('negative control incorrectly passed')
        return result.returncode

    if not args.smoke:
        run([sys.executable, '-B', ROOT / 'tools/abi/prepare_smoke.py', smoke])
    directory = os.add_dll_directory(str(library.parent)) if os.name == 'nt' else None
    loaded = ctypes.CDLL(str(library))
    loaded.exr_version.restype = ctypes.c_char_p
    version = loaded.exr_version().decode()
    print('PASS explicit_load version=' + version, flush=True)
    probe = out / ('platform-probe.exe' if os.name == 'nt' else 'platform-probe')
    command = [args.cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-I' + str(ROOT / 'include'),
               ROOT / 'tools/platforms/probe.c', library, '-o', probe]
    if os.name != 'nt':
        command += ['-Wl,-rpath,' + str(library.parent)]
    run(command)
    base = [probe, smoke / 'smoke.epub', smoke / 'font.otf']
    run(base + [out, 'create'])
    run(base + [out, 'reopen'])
    log = (out / 'reopen.log').read_text()
    checks = {name: bool(re.search(r'^PASS ' + name + r'\b', log, re.M))
              for name in ('load', 'open', 'render', 'search', 'annotation')}
    if not all(checks.values()) or 'PASS platform checks=5/5' not in log:
        raise RuntimeError('incomplete runtime evidence')
    negative = out / 'negative'
    negative.mkdir()
    shutil.copyfile(out / 'highlight.json', negative / 'highlight.json')
    position = (out / 'position.txt').read_text().split()
    position[3] = str(int(position[3]) + 1)
    (negative / 'position.txt').write_text(' '.join(position) + '\n')
    rejected = run(base + [negative, 'reopen'], expected=1)
    result = {'checks': checks, 'passed': sum(checks.values()), 'version': version,
              'library': str(library), 'library_sha256': hashlib.sha256(library.read_bytes()).hexdigest(),
              'negative_moved_annotation_exit': rejected, 'commands': commands,
              'input_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (smoke / 'smoke.epub', smoke / 'font.otf')}}
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(log, end='')
    print('PASS negative control rejected moved annotation')
    if directory:
        directory.close()


if __name__ == '__main__':
    main()
