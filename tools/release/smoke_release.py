#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Package, relocate, and execute the README's three native SDK quickstart commands."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def quickstart(readme, system, mingw=False):
    heading = {'Windows': f"Windows ({'MinGW' if mingw else 'MSVC'} x64)",
               'Linux': 'Linux', 'Darwin': 'macOS'}[system]
    section = re.search(r'^### ' + re.escape(heading) + r'[^\n]*\n(.*?)(?=^### |\Z)',
                        readme, re.MULTILINE | re.DOTALL)
    if not section:
        raise ValueError(f'Missing README quickstart section: {heading}')
    language = 'powershell' if system == 'Windows' else 'bash'
    block = re.search(r'^```' + language + r'\s*\n(.*?)^```',
                      section[1], re.MULTILINE | re.DOTALL)
    if not block:
        raise ValueError(f'Missing {language} block in {heading} quickstart')
    commands = [line for line in block[1].splitlines() if line.strip()]
    if len(commands) != 3:
        raise ValueError(f'{heading} quickstart must contain exactly three command lines')
    return commands


def msvc_environment(compiler, env):
    if shutil.which('cl', path=env.get('PATH')) and env.get('INCLUDE') and env.get('LIB'):
        return env
    candidates = []
    if compiler:
        for parent in Path(compiler).resolve().parents:
            candidates.append(parent / 'Auxiliary/Build/vcvars64.bat')
            candidates.append(parent / 'VC/Auxiliary/Build/vcvars64.bat')
    finder = shutil.which('vswhere')
    if not finder:
        finder = str(Path(env.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) /
                     'Microsoft Visual Studio/Installer/vswhere.exe')
    if Path(finder).is_file():
        install = subprocess.check_output(
            [finder, '-latest', '-products', '*', '-requires',
             'Microsoft.VisualStudio.Component.VC.Tools.x86.x64',
             '-property', 'installationPath'], text=True).strip()
        if install:
            candidates.append(Path(install) / 'VC/Auxiliary/Build/vcvars64.bat')
    vcvars = next((path for path in candidates if path.is_file()), None)
    if vcvars is None:
        raise RuntimeError('The Windows README requires MSVC x64; cannot locate vcvars64.bat')
    with tempfile.TemporaryDirectory(prefix='exreader-vcvars-') as directory:
        script = Path(directory) / 'environment.cmd'
        script.write_text(f'@echo off\ncall "{vcvars}" >nul\n'
                          'if errorlevel 1 exit /b %errorlevel%\nset\n', encoding='utf-8')
        output = subprocess.check_output(
            [env.get('COMSPEC', 'cmd.exe'), '/d', '/c', 'environment.cmd'],
            cwd=directory, env=env, text=True, errors='replace')
    result = dict(env)
    for line in output.splitlines():
        key, separator, value = line.partition('=')
        if separator and key:
            result[key.upper()] = value
    return result


def fields(output):
    found = dict(re.findall(r'^(Title|Pages|TOC entries|Format|Version): (.*)$',
                            output, re.MULTILINE))
    for key in ('Pages', 'TOC entries'):
        if key in found:
            found[key] = int(found[key])
    return found


def pgm_info(path):
    data = path.read_bytes()
    header = re.match(rb'P5\n(\d+) (\d+)\n255\n', data)
    if not header:
        raise ValueError('The sample did not produce a binary P5 PGM')
    width, height = map(int, header.groups())
    pixels = data[header.end():]
    if (width, height) != (720, 1040) or len(pixels) != width * height:
        raise ValueError(f'Unexpected PGM dimensions/payload: {width}x{height}, {len(pixels)} bytes')
    nonwhite = sum(pixel != 255 for pixel in pixels)
    if not nonwhite:
        raise ValueError('The rendered first page is entirely white')
    return {'width': width, 'height': height, 'bytes': len(data), 'nonwhite_pixels': nonwhite}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir', type=Path, required=True)
    parser.add_argument('--config', default='Release')
    parser.add_argument('--compiler', help='CMake C compiler path, used to find the MSVC environment')
    parser.add_argument('--output-dir', type=Path, help='evidence directory; default BUILD/release-smoke')
    args = parser.parse_args()
    build = args.build_dir.resolve()
    evidence = (args.output_dir or build / 'release-smoke').resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    report = {'passed': False, 'platform': platform.system(), 'commands': []}
    transcript = []

    def run(command, cwd, env, label):
        completed = subprocess.run(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, errors='replace')
        text = f'[{label}] {command!r}\n{completed.stdout}exit: {completed.returncode}\n'
        transcript.append(text)
        print(text, flush=True)
        if completed.returncode:
            raise RuntimeError(f'{label} failed with exit {completed.returncode}')
        return completed.stdout

    try:
        system = platform.system()
        if system not in ('Windows', 'Linux', 'Darwin'):
            raise RuntimeError(f'Unsupported native platform: {system}')
        env = dict(os.environ)
        mingw = system == 'Windows' and args.compiler and re.search(
            r'(?:^|-)gcc(?:\.exe)?$', Path(args.compiler).name, re.IGNORECASE)
        for variable in ('CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'LIBRARY_PATH',
                         'LD_LIBRARY_PATH', 'DYLD_LIBRARY_PATH', 'DYLD_FALLBACK_LIBRARY_PATH'):
            env.pop(variable, None)
        if system == 'Windows':
            if mingw:
                env['PATH'] = str(Path(args.compiler).resolve().parent) + os.pathsep + env.get('PATH', '')
            else:
                env = msvc_environment(args.compiler, env)
            shell = shutil.which('pwsh') or shutil.which('powershell')
            if shell is None:
                raise RuntimeError('PowerShell is required for the Windows README')
        else:
            shell = shutil.which('bash')
            if shell is None:
                raise RuntimeError('bash is required for the POSIX README')
        with tempfile.TemporaryDirectory(prefix='exreader SDK smoke ') as directory:
            work = Path(directory)
            output = work / 'packages'
            if system == 'Windows':
                package_command = [shell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                                   str(ROOT / 'tools/release/build_packages.ps1'),
                                   '-BuildDir', str(build), '-OutputDir', str(output),
                                   '-Configuration', args.config, '-Python', sys.executable]
            else:
                env['PYTHON'] = sys.executable
                package_command = ['sh', str(ROOT / 'tools/release/build_packages.sh'),
                                   str(build), str(output), args.config]
            run(package_command, ROOT, env, 'package wrapper')
            archives = list(output.glob('*.zip' if system == 'Windows' else '*.tar.gz'))
            if len(archives) != 1:
                raise ValueError(f'Expected one native package archive, found {archives}')
            shutil.copy2(archives[0], evidence / archives[0].name)
            report['archive_sha256'] = hashlib.sha256(archives[0].read_bytes()).hexdigest()
            extracted = work / 'independent extraction'
            shutil.unpack_archive(str(archives[0]), str(extracted))
            packages = list(extracted.iterdir())
            if len(packages) != 1 or not packages[0].is_dir():
                raise ValueError('The archive must contain one SDK root directory')
            sdk = packages[0]
            run([sys.executable, str(ROOT / 'tools/release/check_release.py'), str(sdk),
                 '--json', str(evidence / 'check-release.json')], work, env, 'extracted package check')
            commands = quickstart((sdk / 'README.md').read_text(encoding='utf-8'), system, mingw)
            report['commands'] = commands
            report['archive_name'] = archives[0].name
            markers = [f'EXR_README_COMMAND_{number}' for number in range(1, 4)]
            script = work / ('quickstart.ps1' if system == 'Windows' else 'quickstart.sh')
            lines = ["$ErrorActionPreference = 'Stop'" if system == 'Windows' else 'set -eu']
            for marker, command in zip(markers, commands):
                lines.append(f"Write-Output '{marker}'" if system == 'Windows' else
                             f"printf '%s\\n' '{marker}'")
                lines.append(command)
                if system == 'Windows':
                    lines.append("if (-not $?) { throw 'README command failed' }")
            script.write_text('\n'.join(lines) + '\n', encoding='utf-8')
            invocation = [shell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script)] \
                if system == 'Windows' else [shell, str(script)]
            actual = run(invocation, sdk, env, 'README three commands')
            for index, marker in enumerate(markers):
                if marker + '\n' not in actual:
                    raise ValueError(f'Missing README command execution marker: {marker}')
                section = actual.split(marker + '\n', 1)[1]
                if index < 2:
                    section = section.split(markers[index + 1] + '\n', 1)[0]
                report.setdefault('command_results', []).append(
                    {'command': commands[index], 'exit_code': 0, 'output': section})
                transcript.append(f'[README command {index + 1}] {commands[index]}\n{section}exit: 0\n')
            example_output = report['command_results'][2 if system == 'Windows' else 1]['output']
            sample = fields(example_output)
            if not sample.get('Title') or sample.get('Pages', 0) < 1 or sample.get('TOC entries', -1) < 0:
                raise ValueError(f'Incomplete example output: {sample}')
            if 'Output: page-1.pgm (720 x 1040, PGM)' not in example_output:
                raise ValueError('Example output does not confirm the expected PGM path and dimensions')
            report['pgm'] = pgm_info(sdk / 'page-1.pgm')
            shutil.copy2(sdk / 'page-1.pgm', evidence / 'page-1.pgm')
            cli = sdk / 'bin' / ('exr-info.exe' if system == 'Windows' else 'exr-info')
            version = (sdk / 'VERSION').read_text(encoding='utf-8').strip()
            version_output = run([str(cli), '--version'], work, env, 'relocated CLI version')
            if version_output.strip() != f'EXReader {version}':
                raise ValueError('Runtime version differs from packaged VERSION')
            info_output = run([str(cli), str(sdk / 'examples/minimal/sample.epub'),
                               str(sdk / 'examples/minimal/font.ttf')], work, env, 'relocated CLI info')
            info = fields(info_output)
            if info.get('Version') != version or info.get('Format') != 'EPUB' or any(
                    info.get(key) != sample[key] for key in ('Title', 'Pages', 'TOC entries')):
                raise ValueError(f'CLI/sample mismatch: CLI={info}, sample={sample}')
            report.update(passed=True, sample=sample, cli=info, version=version)
            print('PASS: relocated SDK, all three README commands, PGM pixels, CLI and version', flush=True)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        report['error'] = str(error)
        print(f'FAIL: {error}', file=sys.stderr, flush=True)
    finally:
        (evidence / 'smoke.log').write_text('\n'.join(transcript), encoding='utf-8')
        (evidence / 'smoke.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
