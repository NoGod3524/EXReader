#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Capture configured build inputs, or check them before a same-machine rebuild."""
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

from verify_artifacts import digest

ENVIRONMENT = ('PATH', 'CC', 'CXX', 'CFLAGS', 'CXXFLAGS', 'CPPFLAGS', 'LDFLAGS', 'CL', '_CL_',
               'LINK', '_LINK_', 'INCLUDE', 'LIB', 'LIBPATH', 'WindowsSdkDir', 'WindowsSDKVersion',
               'VCToolsInstallDir', 'SDKROOT', 'MACOSX_DEPLOYMENT_TARGET', 'SOURCE_DATE_EPOCH')
# Run reports and GitHub configuration are not build/package inputs. Excluding the
# manifest itself avoids a self-referential hash. All other tracked + unignored
# source files are hashed, including packaging scripts and installed documentation.
EXCLUDED = ('evidence/', 'docs/ui/evidence/', 'archive/', '.github/', 'tools/release/build_manifest.json')


def is_source_input(name):
    return (bool(name) and not name.startswith(EXCLUDED)
            and not ('/' not in name and (name == 'OUT.txt' or name.endswith('-OUT.txt'))))


def output(command, cwd=None):
    return subprocess.check_output(command, cwd=cwd, text=True, encoding='utf-8').strip()


def write_json(path, value):
    Path(path).write_bytes((json.dumps(value, indent=2, sort_keys=True) + '\n').encode('utf-8'))


def fingerprint(root, names):
    h = hashlib.sha256()
    files = 0
    for name in sorted(set(names)):
        path = root / name
        if not path.is_file():
            continue
        encoded = name.encode('utf-8')
        h.update(len(encoded).to_bytes(8, 'big') + encoded + bytes.fromhex(digest(path)))
        files += 1
    if not files:
        raise ValueError(f'no input files: {root}')
    return {'files': files, 'sha256': h.hexdigest()}


def tree(root):
    root = Path(root)
    names = []
    for directory, folders, files in os.walk(root):
        folders[:] = sorted(d for d in folders if d not in ('.git', '__pycache__'))
        names.extend((Path(directory) / f).relative_to(root).as_posix() for f in files)
    return fingerprint(root, names)


def source_inputs(source):
    names = output(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], source).split('\0')
    names = [n for n in names if is_source_input(n)]
    return fingerprint(source, names)


def cache_values(build):
    values = {}
    for line in (build / 'CMakeCache.txt').read_text(encoding='utf-8').splitlines():
        match = re.fullmatch(r'([^/#][^:]*):([^=]+)=(.*)', line)
        if match:
            name, kind, value = match.groups()
            values[name] = {'type': kind, 'value': value}
    return values


def tool(path):
    path = Path(path).resolve(strict=True)
    return {'path': str(path), 'sha256': digest(path)}


def capture(source, build, configure_args):
    cache = cache_values(build)
    value = lambda key, default='': cache.get(key, {}).get('value', default)
    if Path(value('CMAKE_HOME_DIRECTORY')).resolve() != source:
        raise ValueError('build directory belongs to a different source tree')
    if value('CMAKE_BUILD_TYPE') != 'Release' or value('EXR_REPRODUCIBLE') != 'ON':
        raise ValueError('use Release and -DEXR_REPRODUCIBLE=ON for the measured release build')
    compilers = {}
    for language in ('C', 'CXX'):
        compiler = value(f'CMAKE_{language}_COMPILER')
        if not compiler:
            continue
        paths = list((build / 'CMakeFiles').glob(f'*/CMake{language}Compiler.cmake'))
        if len(paths) != 1:
            raise ValueError('need exactly one configured compiler record; use a fresh build directory')
        data = paths[0].read_text(encoding='utf-8')
        fields = dict(re.findall(r'set\((CMAKE_[A-Z0-9_]+) "([^"\n]*)"\)', data))
        compilers[language] = dict(tool(compiler), id=fields[f'CMAKE_{language}_COMPILER_ID'],
                                  version=fields[f'CMAKE_{language}_COMPILER_VERSION'],
                                  configuration=fields)
    deps = {}
    declarations = (source / 'cmake/deps.cmake').read_text(encoding='utf-8')
    for name, url, pin in re.findall(r'FetchContent_Declare\((\w+) URL "([^"]+)" URL_HASH SHA256=([a-f0-9]{64})', declarations):
        override = value('FETCHCONTENT_SOURCE_DIR_' + name.upper())
        path = Path(override) if override else Path(value('FETCHCONTENT_BASE_DIR', str(build / '_deps'))) / (name + '-src')
        if path.is_dir():
            deps[name] = {'source_dir': str(path.resolve()), 'url': url, 'archive_sha256': pin,
                          'revision': url.split('/tar.gz/')[-1].removeprefix('refs/tags/'),
                          'local_override': bool(override), 'source_tree': tree(path)}
    if not {'expat', 'freetype', 'miniz'} <= deps.keys():
        raise ValueError('missing required dependency inputs')
    cmake = value('CMAKE_COMMAND') or shutil.which('cmake')
    toolchain = {name: tool(value(name)) for name in ('CMAKE_AR', 'CMAKE_RANLIB', 'CMAKE_LINKER', 'CMAKE_OBJCOPY', 'CMAKE_MAKE_PROGRAM')
                 if value(name) and Path(value(name)).is_file()}
    changed = output(['git', 'diff', '--name-only', 'HEAD'], source).splitlines()
    changed += output(['git', 'ls-files', '--others', '--exclude-standard'], source).splitlines()
    changed = sorted(set(n for n in changed if is_source_input(n)))
    epoch = os.environ.get('SOURCE_DATE_EPOCH') or output(['git', 'show', '-s', '--format=%ct', 'HEAD'], source)
    return {
        'schema': 1,
        'scope': 'same machine, same absolute source/build paths, unsigned Release DLL and installed SDK package',
        'source': {'directory': str(source), 'revision': output(['git', 'rev-parse', 'HEAD'], source),
                   'git_tree': output(['git', 'rev-parse', 'HEAD^{tree}'], source),
                   'tree': source_inputs(source),
                   'overrides': {n: digest(source / n) if (source / n).is_file() else None for n in changed},
                   'excluded': list(EXCLUDED) + ['root OUT.txt and *-OUT.txt progress logs']},
        'host': {'system': platform.system(), 'release': platform.release(), 'version': platform.version(),
                 'machine': platform.machine()},
        'compiler': compilers, 'cmake': dict(tool(cmake), version=output([cmake, '--version']).splitlines()[0]),
        'toolchain': toolchain, 'python': dict(tool(sys.executable), version=platform.python_version()),
        'dependencies': deps,
        'build': {'directory': str(build), 'generator': value('CMAKE_GENERATOR'), 'configuration': 'Release',
                  'configure_arguments': configure_args, 'cache': cache,
                  'generated_inputs': {n: tree(build / n) for n in ('generated', 'exr-stb') if (build / n).is_dir()}},
        'environment': {n: os.environ.get(n) for n in ENVIRONMENT},
        'package': {'format': 'tar.gz', 'source_date_epoch': int(epoch), 'gzip_filename': '',
                    'tar_uid': 0, 'tar_gid': 0, 'file_order': 'relative path sorted',
                    'signing': 'after unsigned reproducibility comparison'},
    }


def check(manifest):
    source = Path(manifest['source']['directory'])
    build = Path(manifest['build']['directory'])
    actual = capture(source, build, manifest['build']['configure_arguments'])
    for key in ('host', 'compiler', 'cmake', 'toolchain', 'python', 'dependencies', 'build', 'environment'):
        if actual[key] != manifest[key]:
            raise ValueError(f'build input changed: {key}')
    if actual['source']['tree'] != manifest['source']['tree']:
        raise ValueError('build input changed: source tree')
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--build-dir', type=Path)
    parser.add_argument('--configure-args', type=Path, help='JSON array of the actual CMake configure arguments')
    parser.add_argument('--output', type=Path, default=Path(__file__).with_name('build_manifest.json'))
    parser.add_argument('--check', type=Path, help='verify inputs of an existing manifest')
    args = parser.parse_args()
    try:
        if args.check:
            check(json.loads(args.check.read_text(encoding='utf-8')))
            print('PASS: all recorded build inputs match')
        else:
            if not args.build_dir or not args.configure_args:
                parser.error('capture requires --build-dir and --configure-args')
            configure_args = json.loads(args.configure_args.read_text(encoding='utf-8'))
            if not isinstance(configure_args, list) or not all(isinstance(a, str) for a in configure_args):
                raise ValueError('configure arguments must be an array of strings')
            write_json(args.output, capture(args.source.resolve(), args.build_dir.resolve(), configure_args))
            print('Wrote ' + str(args.output))
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
