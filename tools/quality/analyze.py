"""Run GCC's analyzer with real CMake flags; retain every diagnostic and path."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import ctypes
from datetime import datetime, timezone
import gzip
import json
import os
from pathlib import Path
import shlex
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def progress(out, message):
    with (out / 'QUAL-OUT.txt').open('a', encoding='utf-8') as stream:
        stream.write(f'[{datetime.now(timezone.utc).isoformat()}] {message}\n')
    print(message, flush=True)


def split_command(command):
    if os.name != 'nt':
        return shlex.split(command)
    shell = ctypes.windll.shell32
    shell.CommandLineToArgvW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
    shell.CommandLineToArgvW.restype = ctypes.POINTER(ctypes.c_wchar_p)
    count = ctypes.c_int()
    pointer = shell.CommandLineToArgvW(command, ctypes.byref(count))
    if not pointer:
        raise ctypes.WinError()
    try:
        return [pointer[i] for i in range(count.value)]
    finally:
        ctypes.windll.kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        ctypes.windll.kernel32.LocalFree(pointer)


def analyzer_command(entry, output):
    original = entry.get('arguments') or split_command(entry['command'])
    command = []
    skip = False
    for arg in original:
        if skip:
            skip = False
            continue
        if arg in ('-o', '-MF', '-MT', '-MQ'):
            skip = True
        elif arg not in ('-MD', '-MMD', '--coverage', '-Werror') and not arg.startswith(('-O', '-fprofile-')):
            command.append(arg)
    return command + ['-O0', '-fanalyzer', '-Wno-error', '-fdiagnostics-format=sarif-stderr',
                      '-fdiagnostics-show-option', '-o', str(output)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--collect', action='store_true', help='collect retained successful SARIF invocations')
    args = parser.parse_args()
    out = args.output.resolve()
    local = out / 'local/analyzer'
    local.mkdir(parents=True, exist_ok=True)
    entries = json.loads((args.build / 'compile_commands.json').read_text(encoding='utf-8'))
    chosen = {}
    for entry in entries:
        source = Path(entry['file']).resolve()
        if source.suffix != '.c':
            continue
        group = None
        if source.parent == ROOT / 'src':
            group = 'project'
        elif any(part.startswith('freetype') for part in source.parts):
            group = 'freetype'
        elif 'expat' in source.parts:
            group = 'expat'
        elif 'miniz' in source.parts:
            group = 'miniz'
        if group and source not in chosen:
            chosen[source] = dict(entry, group=group)
    expected = set((ROOT / 'src').glob('*.c'))
    missing = sorted(str(p) for p in expected - chosen.keys())
    if missing:
        raise RuntimeError(f'Missing compile commands: {missing}')
    jobs = []
    for number, (source, entry) in enumerate(chosen.items()):
        jobs.append(dict(entry, id=number, command=analyzer_command(entry, local / f'{number:03}.o')))
    if args.collect:
        jobs = [job for job in json.loads((out / 'analyzer-commands.json').read_text(encoding='utf-8'))
                if Path(job['file']).suffix == '.c']
        assert {Path(j['file']) for j in jobs if j['group'] == 'project'} == expected
    else:
        write_json(out / 'analyzer-commands.json', jobs)

    def run(job):
        started = time.monotonic()
        path = out / f'analyzer-{job["id"]:03}.json.gz'
        if args.collect:
            with gzip.open(path, 'rt', encoding='utf-8') as stream:
                saved = json.load(stream)
            assert saved['source'] == job['file'] and Path(job['command'][-1]).is_file()
        else:
            result = subprocess.run(job['command'], cwd=job['directory'], capture_output=True,
                                    encoding='utf-8', errors='replace')
            saved = dict(source=job['file'], exit_code=result.returncode,
                         stdout=result.stdout, stderr=result.stderr)
            with gzip.open(path, 'wt', encoding='utf-8') as stream:
                json.dump(saved, stream, ensure_ascii=False)
        sarif = json.loads(saved['stderr'])
        success = all(i['executionSuccessful'] for r in sarif['runs'] for i in r['invocations'])
        diagnostics = [diagnostic for run in sarif['runs'] for diagnostic in run.get('results', [])]
        return dict(id=job['id'], file=job['file'], group=job['group'],
                    exit_code=saved.get('exit_code', 0 if success else 1),
                    exit_code_source='process' if 'exit_code' in saved else 'SARIF executionSuccessful and emitted object',
                    timing_kind='collection' if args.collect else 'compiler',
                    seconds=round(time.monotonic() - started, 3),
                    diagnostics=diagnostics)

    results = []
    with ThreadPoolExecutor(args.workers) as pool:
        futures = [pool.submit(run, job) for job in jobs]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            progress(out, f'Analyzer {len(results)}/{len(jobs)}: {result["group"]}/'
                     f'{Path(result["file"]).name}; exit={result["exit_code"]}; '
                     f'diagnostics={len(result["diagnostics"])}; {result["seconds"]}s')
    results.sort(key=lambda row: row['id'])
    with gzip.open(out / 'analyzer-results.json.gz', 'wt', encoding='utf-8') as stream:
        json.dump(results, stream, ensure_ascii=False)
    progress(out, f'Analyzer complete: {len(expected)} project source files, '
             f'{len(jobs) - len(expected)} third-party translation units; '
             f'{sum(r["exit_code"] != 0 for r in results)} failed invocations.')
    return int(any(r['exit_code'] for r in results))


if __name__ == '__main__':
    raise SystemExit(main())
