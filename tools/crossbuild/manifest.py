#!/usr/bin/env python3
"""Capture installed SDK provenance without executing the target library."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'abi'))
from check_exports import inspect_bytes


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(source, *args):
    result = subprocess.run(['git', '-C', str(source), *args], capture_output=True,
                            text=True, encoding='utf-8')
    return result.stdout.strip() if result.returncode == 0 else None


def source_files(source):
    paths = [source / 'CMakeLists.txt', source / 'tools/layers.json']
    for directory in ('src', 'include', 'cmake'):
        paths.extend(p for p in (source / directory).rglob('*') if p.is_file())
    return {p.relative_to(source).as_posix(): sha(p.read_bytes()) for p in sorted(paths)}


def snapshot(source):
    files = source_files(source)
    return {'commit': git(source, 'rev-parse', 'HEAD'),
            'tree': git(source, 'rev-parse', 'HEAD^{tree}'),
            'tracked_changes': git(source, 'status', '--porcelain', '--untracked-files=no',
                                   '--', 'CMakeLists.txt', 'cmake', 'src', 'include', 'tools/layers.json'),
            'sdk_input_sha256': sha(json.dumps(files, sort_keys=True).encode()), 'files': files}


def dependencies(settings, source):
    definitions = (source / 'cmake/deps.cmake').read_text(encoding='utf-8')
    result = {}
    for name in ('expat', 'freetype', 'miniz', 'zlib'):
        pin = re.search(r'FetchContent_Declare\(' + name + r' URL "([^"]+)" URL_HASH SHA256=([a-f0-9]+)', definitions)
        directory = settings[name + '_SOURCE_DIR']
        item = {'url': pin[1], 'archive_sha256': pin[2], 'source_directory': directory,
                'enabled': bool(directory)}
        if directory:
            root = Path(directory)
            if name == 'expat':
                header = root / 'expat/lib/expat.h'
                content = header.read_text(encoding='utf-8')
                version = '.'.join(re.search(r'#\s*define\s+XML_' + part + r'_VERSION\s+(\d+)', content)[1]
                                   for part in ('MAJOR', 'MINOR', 'MICRO'))
            elif name == 'freetype':
                header = root / 'include/freetype/freetype.h'
                content = header.read_text(encoding='utf-8')
                version = '.'.join(re.search(r'#\s*define\s+FREETYPE_' + part + r'\s+(\d+)', content)[1]
                                   for part in ('MAJOR', 'MINOR', 'PATCH'))
            elif name == 'miniz':
                header = root / 'CMakeLists.txt'
                content = header.read_text(encoding='utf-8')
                version = '.'.join(re.search(r'set\(MINIZ_' + part + r'_VERSION\s+(\d+)\s*\)', content, re.I)[1]
                                   for part in ('API', 'MINOR', 'PATCH'))
            else:
                header = root / 'zlib.h'
                content = header.read_text(encoding='utf-8')
                version = re.search(r'#\s*define\s+ZLIB_VERSION\s+"([^"]+)"', content)[1]
            item.update(version=version, version_evidence=str(header), version_file_sha256=sha(header.read_bytes()))
            # A source override need not be the declared tarball. Record its actual bytes.
            files = {p.relative_to(root).as_posix(): sha(p.read_bytes())
                     for p in sorted(root.rglob('*')) if p.is_file() and '.git' not in p.relative_to(root).parts}
            item['source_tree_sha256'] = sha(json.dumps(files, sort_keys=True).encode())
            item['source_file_count'] = len(files)
            if (root / '.git').exists():
                item['commit'] = git(root, 'rev-parse', 'HEAD')
        else:
            item['version'] = None
            item['reason'] = 'dependency disabled by configured feature options'
        result[name] = item
    return result


def capture(args):
    settings = json.loads(args.settings.read_text(encoding='utf-8'))
    original = json.loads(args.snapshot.read_text(encoding='utf-8'))
    current = snapshot(args.source)
    if current['files'] != original['files'] or current['commit'] != original['commit']:
        raise ValueError('SDK source changed after configuration; reconfigure and rebuild')
    binary = args.binary.read_bytes()
    slices = inspect_bytes(binary)
    expected = set((args.build / 'public-symbols.txt').read_text(encoding='utf-8').splitlines())
    for part in slices:
        if part['symbols'] != expected:
            raise ValueError(f"export surface mismatch: missing={sorted(expected - part['symbols'])}, "
                             f"extra={sorted(part['symbols'] - expected)}")
    platform = {'Windows': 'windows', 'Linux': 'linux', 'Darwin': 'macos',
                'Android': 'android', 'iOS': 'ios'}[settings['CMAKE_SYSTEM_NAME']]
    configuration = settings['configuration']
    properties_directory = Path(settings['target_properties_directory'])
    object_targets = {p.stem: p.read_text(encoding='utf-8')
                      for p in sorted(properties_directory.glob('*.txt'))}
    if not object_targets:
        raise ValueError('generated object target properties are missing')
    report = {'schema_version': 1, 'platform': platform, 'source': original,
              'compiler': {'id': settings['CMAKE_C_COMPILER_ID'], 'version': settings['CMAKE_C_COMPILER_VERSION'],
                           'path': settings['CMAKE_C_COMPILER']},
              'cmake': {'version': settings['CMAKE_VERSION'], 'generator': settings['CMAKE_GENERATOR']},
              'configuration': configuration,
              'compile_options': {'c_flags': settings['CMAKE_C_FLAGS'],
                                  'configuration_flags': settings.get('CMAKE_C_FLAGS_' + configuration.upper(), ''),
                                  'position_independent_code': settings['CMAKE_POSITION_INDEPENDENT_CODE'],
                                  'exr_options': {k: v for k, v in settings.items() if k.startswith('EXR_')},
                                  'object_targets': object_targets},
              'target': {k: v for k, v in settings.items() if k.startswith('CMAKE_') and k not in
                         ('CMAKE_C_COMPILER', 'CMAKE_C_COMPILER_ID', 'CMAKE_C_COMPILER_VERSION')},
              'dependencies': dependencies(settings, args.source),
              'artifact': {'file': args.binary.name, 'sha256': sha(binary), 'size_bytes': len(binary),
                           'exported_symbol_count': len(slices[0]['symbols']) if len(slices) == 1 else None,
                           'slices': [{**p, 'symbols': sorted(p['symbols']), 'exported_symbol_count': len(p['symbols'])}
                                      for p in slices]}}
    args.out.mkdir(parents=True, exist_ok=True)
    shutil.copytree(properties_directory, args.out / properties_directory.name, dirs_exist_ok=True)
    for path in (args.settings, args.snapshot, args.build / 'public-symbols.txt',
                 args.build / 'CMakeCache.txt', args.build / 'compile_commands.json'):
        if path.is_file():
            shutil.copy2(path, args.out / path.name)
    (args.out / f'build-manifest-{platform}.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(f"manifest {platform}: {report['artifact']['exported_symbol_count']} exports; SHA256 {sha(binary)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    configure = commands.add_parser('snapshot')
    configure.add_argument('--source', type=Path, required=True)
    configure.add_argument('--out', type=Path, required=True)
    collect = commands.add_parser('capture')
    for name in ('source', 'build', 'settings', 'snapshot', 'binary', 'out'):
        collect.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'snapshot':
        args.out.write_text(json.dumps(snapshot(args.source), indent=2) + '\n', encoding='utf-8')
    else:
        capture(args)


if __name__ == '__main__':
    main()
