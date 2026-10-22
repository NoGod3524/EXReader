#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Rejection regression for tools/reading_platform_evidence.py on a real platform build.

Replays the accepted verify invocation recorded in a platform-evidence.json report as a
positive control, then mutates one input at a time (program set, profile, platform,
dependency tool, execution records, artifact identity) and requires a rejecting report
that names the expected problem. The program set is also checked against the executables
Ninja itself lists for the consumer build, independently of the gate's own Ninja parser.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).absolute().parents[1]
TOOL = ROOT/'tools'/'reading_platform_evidence.py'


def option_pairs(argv, name):
    return [argv[i+1] for i, item in enumerate(argv) if item == name]


def without(argv, name, value=None):
    result, i = [], 0
    while i < len(argv):
        if argv[i] == name and (value is None or argv[i+1] == value):
            i += 2
            continue
        result.append(argv[i])
        i += 1
    return result


def replace(argv, name, value):
    return [value if i and argv[i-1] == name else item for i, item in enumerate(argv)]


def shim(folder, name, exit_code, text):
    """A dependency tool stand-in placed first on PATH."""
    folder.mkdir(parents=True, exist_ok=True)
    if os.name == 'nt':
        lines = ['@echo off'] + [f'echo {line}' for line in text] + [f'exit /b {exit_code}']
        (folder/f'{name}.cmd').write_text('\r\n'.join(lines)+'\r\n', encoding='ascii')
    else:
        path = folder/name
        path.write_text('#!/bin/sh\n' + ''.join(f"echo '{line}'\n" for line in text) + f'exit {exit_code}\n', encoding='ascii')
        path.chmod(0o755)
    return {**os.environ, 'PATH': str(folder) + os.pathsep + os.environ['PATH']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path, help='accepted platform-evidence.json from the same job')
    parser.add_argument('output', type=Path, help='regression result JSON')
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding='utf-8'))
    base = report['invocation']
    if base[0] != 'verify' or not report['accepted']:
        raise SystemExit('The replayed report must be an accepted verify report')
    profile, consumer, platform_name = base[1], Path(base[4]), report['platform_requested']
    programs = option_pairs(base, '--program')
    other_profile = {'reading-core': 'reading-library', 'reading-library': 'reading-core'}[profile]
    other_platform = {'Windows': 'macOS', 'macOS': 'Windows'}[platform_name]
    tool = 'dumpbin' if platform_name == 'Windows' else 'otool'
    work = Path(tempfile.mkdtemp(prefix='platform-evidence-regression-'))
    results = []

    def check(name, argv, codes, env=None, accepted=False):
        output = work/f'{len(results):02d}-{name}.json'
        argv = argv[:5] + [str(output)] + argv[6:]
        process = subprocess.run([sys.executable, str(TOOL), *argv], capture_output=True, text=True, env=env)
        try:
            observed = json.loads(output.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            observed = {'accepted': None, 'problems': []}
        found = {code: any(p.startswith(code+':') for p in observed['problems']) for code in codes}
        passed = observed['accepted'] is accepted and process.returncode == (0 if accepted else 1) and all(found.values())
        if accepted:
            passed = passed and not observed['problems']
        results.append({'case': name, 'expected_accepted': accepted, 'expected_codes': codes, 'exit_code': process.returncode,
                        'observed_accepted': observed['accepted'], 'codes_found': found,
                        'problems': observed['problems'], 'passed': passed})
        print(('PASS ' if passed else 'FAIL ') + name + ('' if passed else f' {observed["problems"]} {process.stderr[-2000:]}'))

    # Independent view of the consumer build: executables Ninja reports, not the gate's parser.
    targets = subprocess.run(['ninja', '-C', str(consumer), '-t', 'targets', 'all'], capture_output=True, text=True)
    ninja_programs = sorted(line.split(':', 1)[0].replace('\\', '/') for line in targets.stdout.splitlines()
                            if 'EXECUTABLE_LINKER' in line.split(':', 1)[-1])
    supplied = sorted(Path(p).resolve().relative_to(consumer.resolve()).as_posix() for p in programs)
    results.append({'case': 'program-set-equals-ninja-executables', 'ninja': ninja_programs, 'supplied': supplied,
                    'passed': targets.returncode == 0 and bool(ninja_programs) and ninja_programs == supplied})
    print(('PASS ' if results[-1]['passed'] else 'FAIL ') + f'program set {supplied} vs ninja {ninja_programs}')

    check('control', base, [], accepted=True)
    for program in programs:
        check(f'missing {Path(program).name}', without(base, '--program', program), ['missing-program'])
    check('empty-program-set', without(base, '--program'), ['empty-program-set', 'missing-program'])
    check('duplicate-program', base + ['--program', programs[0]], ['duplicate-program'])
    check('duplicate-program-other-spelling', base + ['--program', str(Path(programs[0]).absolute())], ['duplicate-program'])
    extra = work/'extra'/Path(programs[0]).name
    extra.parent.mkdir()
    shutil.copy2(programs[0], extra)
    check('unknown-program', base + ['--program', str(extra)], ['unknown-program'])
    check('wrong-profile', base[:1] + [other_profile] + base[2:], ['preset-mismatch'])
    check('unknown-profile', base[:1] + ['reading-unknown'] + base[2:], ['unknown-profile', 'unknown-program'])
    check('wrong-platform', replace(base, '--platform', other_platform), ['platform-mismatch'])
    check('unsupported-platform', replace(base, '--platform', 'Linux'), ['unsupported-platform', 'platform-mismatch'])
    check('dependency-tool-fails', base, ['dependency-tool-failed'],
          env=shim(work/'fail', tool, 3, ['simulated dependency tool failure']))
    check('dependency-output-empty', base, ['dependency-output-missing'], env=shim(work/'empty', tool, 0, []))
    check('dependency-output-unrecognised', base, ['dependency-output-missing'],
          env=shim(work/'garbage', tool, 0, ['no dependency section here']))
    for option in ('--ctest-junit', '--ctest-tests', '--smoke-summary', '--snapshot'):
        check(f'record-missing {option}', without(base, option), ['not-executed'])
    benchmark = next(p for p in programs if Path(p).name.startswith('reading-benchmark'))
    check('benchmark-not-executed', without(base, '--run'), ['not-executed'])
    if profile == 'reading-library':
        probe_record = next(path for path in option_pairs(base, '--run')
                            if Path(json.loads(Path(path).read_text(encoding='utf-8'))['program']).stem
                            == 'reading-library-chapter-probe')
        check('stored-chapter-probe-not-executed', without(base, '--run', probe_record), ['not-executed'])
        record = json.loads(Path(probe_record).read_text(encoding='utf-8'))
        record['sha256_after'] = '0' * 64
        wrong_hash = work/'probe-wrong-hash.json'
        wrong_hash.write_text(json.dumps(record), encoding='utf-8')
        check('stored-chapter-probe-hash-mismatch',
              without(base, '--run', probe_record) + ['--run', str(wrong_hash)], ['not-executed'])
    # Artifact identity: a copied consumer tree where one required path is not a native executable.
    fake = work/'consumer'
    for program in programs:
        target = fake/Path(program).resolve().relative_to(consumer.resolve())
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(program, target)
    shutil.copy2(consumer/'build.ninja', fake/'build.ninja')
    junk = fake/Path(benchmark).resolve().relative_to(consumer.resolve())
    junk.write_bytes(b'not a native executable\n')
    moved = [str(fake/Path(p).resolve().relative_to(consumer.resolve())) for p in programs]
    fake_argv = without(base[:4] + [str(fake)] + base[5:], '--program') + [x for p in moved for x in ('--program', p)]
    check('not-native-program', fake_argv, ['not-native-program'])
    (fake/'build.ninja').write_text('', encoding='utf-8')
    junk.write_bytes(Path(benchmark).read_bytes())
    check('not-build-output', fake_argv, ['not-build-output'])
    shutil.rmtree(work, ignore_errors=True)
    summary = {'schema': 1, 'profile': profile, 'platform': platform_name, 'report': args.report.as_posix(),
               'cases': len(results), 'passed': sum(r['passed'] for r in results),
               'accepted': all(r['passed'] for r in results), 'results': results}
    args.output.write_text(json.dumps(summary, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    print(json.dumps({key: summary[key] for key in ('profile', 'platform', 'cases', 'passed', 'accepted')}))
    return 0 if summary['accepted'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
