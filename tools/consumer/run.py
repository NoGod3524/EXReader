#!/usr/bin/env python3
"""Generate and test a standalone consumer using only a published SDK's bytes."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from check_abi import check, load_baseline

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', required=True, type=Path, help='installed release package')
    parser.add_argument('--work-dir', type=Path, help='new, nonexistent directory outside the repository')
    parser.add_argument('--font', type=Path, default=ROOT / 'tests/fixtures/fonts/primary.ttf')
    parser.add_argument('--generator', help='CMake generator (otherwise use platform default)')
    parser.add_argument('--config', default='Release')
    parser.add_argument('--compiler', help='optional C compiler matching the published package')
    parser.add_argument('--report-dir', type=Path, help='copy text/JSON evidence here')
    parser.add_argument('--journal', type=Path, help='append each completed step immediately')
    parser.add_argument('--allow-added', help='explicit explanation for additions to the frozen ABI')
    parser.add_argument('--generate-only', action='store_true')
    args = parser.parse_args()
    args.config = args.config or 'Release'
    source_sdk = args.sdk.resolve(strict=True)
    if args.work_dir:
        work = args.work_dir.resolve()
        if work == ROOT or ROOT in work.parents:
            parser.error('--work-dir must be outside the repository')
        work.mkdir(parents=True, exist_ok=False)
    else:
        work = Path(tempfile.mkdtemp(prefix='exreader-consumer-')).resolve()
    if work == ROOT or ROOT in work.parents:
        raise ValueError('temporary directory must be outside the repository')
    logs = work / 'logs'
    logs.mkdir()
    report = {'work_dir': str(work), 'source_sdk': str(source_sdk), 'commands': [], 'passed': False}

    def record(message):
        line = f'[{datetime.now(timezone.utc).isoformat()}] {message}'
        print(line, flush=True)
        if args.journal:
            with args.journal.open('a', encoding='utf-8') as stream:
                stream.write(line + '\n')

    def run(name, command, cwd=work, expect_failure=False):
        command = [str(arg) for arg in command]
        result = subprocess.run(command, cwd=cwd, text=True, encoding='utf-8', errors='replace',
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        entry = {'name': name, 'cwd': str(cwd), 'argv': command, 'exit_code': result.returncode}
        report['commands'].append(entry)
        (logs / f'{name}.txt').write_text(json.dumps(entry) + '\n' + result.stdout, encoding='utf-8')
        if (result.returncode == 0) == expect_failure:
            raise RuntimeError(f'{name}: unexpected exit {result.returncode}\n{result.stdout[-6000:]}')
        return result.stdout

    try:
        sdk = work / 'sdk'
        shutil.copytree(source_sdk / 'include', sdk / 'include')
        shutil.copytree(source_sdk / 'lib', sdk / 'lib')
        # Windows publishes runtime DLLs in bin; relocate their unchanged bytes
        # to lib so the consumer receives precisely include/ and lib/.
        for dll in (source_sdk / 'bin').glob('*.dll'):
            shutil.copy2(dll, sdk / 'lib' / dll.name)
        libraries = [p for p in (sdk / 'lib').iterdir() if p.is_file() and
                     re.fullmatch(r'(?:lib)?exreader(?:\.dll|\.so(?:\.[0-9.]+)?|(?:\.[0-9.]+)?\.dylib)', p.name)]
        if not libraries:
            raise ValueError('package has no aggregate shared library in lib/ or bin/')
        library = sorted(libraries, key=lambda p: len(p.name))[0]
        project = work / 'project'
        project.mkdir()
        for name in ('CMakeLists.txt', 'main.c'):
            shutil.copy2(HERE / name, project / name)
        baseline = sorted(load_baseline())
        (project / 'abi_symbols.h').write_text(
            'static const char *const abi_symbols[] = {\n' +
            ''.join(f'  "{symbol}",\n' for symbol in baseline) + '};\n', encoding='utf-8')
        run('fixtures', [sys.executable, '-B', ROOT / 'tools/abi/prepare_smoke.py',
                         work / 'assets', '--font', args.font.resolve()])
        manifest = {str(p.relative_to(sdk)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted(sdk.rglob('*')) if p.is_file()}
        (logs / 'package-sha256.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        record(f'A PASS: standalone project={project}; SDK contains only include/ and lib/; '
               f'{len(manifest)} installed files copied; no repository source paths in project.')
        if args.generate_only:
            report['passed'] = True
            return 0

        def build(mode, package=sdk, label=None):
            label = label or mode
            build_dir = work / f'build-{label}'
            command = ['cmake', '-S', project, '-B', build_dir, f'-DSDK_ROOT={package}',
                       f'-DMODE={mode}', f'-DCMAKE_BUILD_TYPE={args.config}',
                       '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON']
            if args.generator:
                command += ['-G', args.generator]
            if args.compiler:
                command += [f'-DCMAKE_C_COMPILER={args.compiler}']
            run(f'{label}-configure', command)
            output = run(f'{label}-build', ['cmake', '--build', build_dir, '--config', args.config,
                                          '--verbose'], expect_failure=mode == 'headers-only')
            # Inspect real build commands/cache rather than trusting templates.
            audit = output + (build_dir / 'CMakeCache.txt').read_text(encoding='utf-8')
            compile_commands = build_dir / 'compile_commands.json'
            if compile_commands.exists():
                audit += compile_commands.read_text(encoding='utf-8')
            normalized = audit.replace('\\\\', '/').replace('\\', '/').lower()
            for forbidden in (ROOT, source_sdk):
                if forbidden.as_posix().lower() in normalized:
                    raise RuntimeError(f'{label}: build references original tree {forbidden}')
            executable = build_dir / ('consumer.exe' if os.name == 'nt' else 'consumer')
            return executable, output

        def invoke(label, executable, runtime_library=None, expect_failure=False):
            output = work / f'{label}.png'
            command = [executable, work / 'assets/smoke.epub', work / 'assets/font.otf', output]
            if runtime_library:
                command.append(runtime_library)
            text = run(f'{label}-run', command, cwd=executable.parent, expect_failure=expect_failure)
            if expect_failure:
                if (report['commands'][-1]['exit_code'] != 4 or
                        'SDK_VERSION_MISMATCH:' not in text or output.exists()):
                    raise RuntimeError(f'{label}: mismatch was not explicitly rejected before rendering: {text}')
            elif not output.is_file() or output.read_bytes()[:8] != b'\x89PNG\r\n\x1a\n':
                raise RuntimeError(f'{label}: no valid PNG signature')
            return text.strip()

        report['modes'] = {}
        for mode in ('static', 'shared', 'runtime'):
            executable, _ = build(mode)
            text = invoke(mode, executable, library if mode == 'runtime' else None)
            report['modes'][mode] = text
            record(f'B {mode} PASS: {text}')
        hashes = {mode: hashlib.sha256((work / f'{mode}.png').read_bytes()).hexdigest()
                  for mode in report['modes']}
        if len(set(hashes.values())) != 1:
            raise RuntimeError('rendered PNGs differ between consumption modes')
        report['render_sha256'] = hashes
        abi = check(library, added_reason=args.allow_added)
        report['abi'] = abi
        (logs / 'abi.json').write_text(json.dumps(abi, indent=2) + '\n', encoding='utf-8')
        if not abi['passed']:
            raise RuntimeError('ABI contract failed: see logs/abi.json')
        for part in abi['slices']:
            record(f"C PASS: baseline={abi['baseline_count']} exports={part['symbol_count']} "
                   f"missing={part['missing_count']} added={part['added_count']}; "
                   f"additions={part['added']}; reason={args.allow_added}")

        headers = work / 'headers-only'
        shutil.copytree(sdk / 'include', headers / 'include')
        executable, error = build('headers-only', headers)
        if not re.search(r'(cannot find|unable to find|not found|cannot open|could not open|LNK1104).*exreader|exreader.*(not found|No such file)', error, re.I):
            raise RuntimeError('include-only build failed for an unrelated reason: ' + error)
        if not list(executable.parent.rglob('*.o')) and not list(executable.parent.rglob('*.obj')):
            raise RuntimeError('include-only probe did not reach the link stage')
        report['headers_only_error'] = error.strip()
        record('D headers-only PASS: compilation succeeded; linker rejected absent exreader library. ' +
               '\n'.join(line for line in error.splitlines() if re.search('exreader|error', line, re.I)))

        newer = work / 'newer-headers'
        shutil.copytree(sdk, newer)
        version_header = newer / 'include/exr/version.h'
        original = version_header.read_text(encoding='utf-8')
        match = re.search(r'#define EXR_SDK_VERSION "(\d+)\.(\d+)\.(\d+)"', original)
        if not match:
            raise ValueError('cannot identify published SDK header version')
        version = f'{match[1]}.{int(match[2]) + 1}.0'
        version_header.write_text(original.replace(match[0], f'#define EXR_SDK_VERSION "{version}"'), encoding='utf-8')
        report['version_errors'] = {}
        for mode in ('static', 'shared', 'runtime'):
            label = f'newer-{mode}'
            executable, _ = build(mode, newer, label)
            text = invoke(label, executable, library if mode == 'runtime' else None, expect_failure=True)
            report['version_errors'][mode] = text
            record(f'D header>library {mode} PASS: {text}')
        report['passed'] = True
        record(f'COMPLETE: three independent builds/runs, identical PNGs, zero missing ABI symbols, '
               f'include-only link failure and newer-header rejection in all modes. Consumer retained at {work}')
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        report['error'] = str(error)
        record('FAIL: ' + str(error))
        return 1
    finally:
        (logs / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        if args.report_dir:
            args.report_dir.mkdir(parents=True, exist_ok=True)
            shutil.copytree(logs, args.report_dir, dirs_exist_ok=True)


if __name__ == '__main__':
    sys.exit(main())
