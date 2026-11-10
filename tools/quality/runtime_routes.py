"""Record native sanitizer route probes, including a deliberate ASan violation."""
import json
import os
from pathlib import Path
import shutil
import subprocess
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'evidence/runtime-20261109'
LOCAL = OUT / 'local'


def progress(message):
    with (ROOT / 'SAN-FINAL-OUT.txt').open('a', encoding='utf-8') as stream:
        stream.write(f'[{datetime.now(timezone.utc).isoformat()}] {message}\n')
    print(message, flush=True)


def msvc_env():
    cache = LOCAL / 'msvc-paths.json'
    if cache.exists():
        return os.environ.copy() | json.loads(cache.read_text(encoding='utf-8'))
    vswhere = Path(os.environ['ProgramFiles(x86)']) / 'Microsoft Visual Studio/Installer/vswhere.exe'
    paths = subprocess.check_output([str(vswhere), '-latest', '-products', '*',
                                    '-property', 'installationPath'], text=True).strip()
    setup = Path(paths) / 'VC/Auxiliary/Build/vcvars64.bat'
    result = subprocess.run(f'"{setup}" >nul && set', shell=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace'))
    env = os.environ.copy()
    for line in result.stdout.decode(errors='replace').splitlines():
        key, sep, value = line.partition('=')
        if sep and key:
            env[key.upper()] = value
    # Cache only tool search paths, never the caller's credentials/environment.
    LOCAL.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({key:env[key] for key in ('PATH', 'INCLUDE', 'LIB', 'LIBPATH')}, indent=2), encoding='utf-8')
    return env


def main():
    LOCAL.mkdir(parents=True, exist_ok=True)
    rows = []

    def run(name, args, env=None):
        try:
            result = subprocess.run(args, cwd=LOCAL, env=env, capture_output=True, timeout=60)
            def decode(data):
                return data.decode('utf-16-le' if b'\x00' in data else 'utf-8', errors='replace')
            row = dict(name=name, command=list(map(str, args)), exit_code=result.returncode,
                       stdout=decode(result.stdout), stderr=decode(result.stderr))
        except (OSError, subprocess.TimeoutExpired) as error:
            row = dict(name=name, command=list(map(str, args)), exit_code=None, error=str(error))
        rows.append(row)
        (OUT / 'routes.json').write_text(json.dumps(rows, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
        (OUT / f'route-{name}.txt').write_text(json.dumps(row, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
        progress(f'Route {name}: exit={row["exit_code"]}; evidence/runtime-20261109/route-{name}.txt')
        print(row, flush=True)
        return row

    # MSVC first: success must mean the instrumented executable detects the violation.
    env = msvc_env()
    cl = shutil.which('cl', path=env['PATH'])
    probe = LOCAL / 'msvc-address.exe'
    compiled = run('msvc-build', [cl, '/nologo', '/fsanitize=address', '/Zi', '/Od',
                                 str(ROOT / 'tools/quality/address_probe.c'), '/Fe'+str(probe)], env)
    if compiled['exit_code'] == 0:
        run('msvc-execute', [str(probe)], env)
    run('mingw-version', ['gcc', '--version'])
    run('mingw-undefined', ['gcc', '-fsanitize=undefined', '-fno-sanitize-recover=all', '-g', '-O1',
                            str(ROOT / 'tools/quality/overflow_probe.c'), '-o', 'gcc-undefined.exe'])
    run('mingw-address', ['gcc', '-fsanitize=address', '-g', '-O1',
                          str(ROOT / 'tools/quality/address_probe.c'), '-o', 'gcc-address.exe'])
    run('wsl', ['wsl', '-l', '-v'])
    run('docker', ['docker', '--version'])


if __name__ == '__main__':
    main()
