#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Collect a native CMake build into the small, relocatable shared-library SDK."""
import argparse
import hashlib
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from check_reading_licenses import COMPONENTS, enabled, read_cache, switch


def copy(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Dereference SONAME links: every checksum describes ordinary file bytes.
    shutil.copy2(source, destination)


def artifact(directories, names):
    for directory in directories:
        for name in names:
            path = directory / name
            if path.is_file():
                return path
    raise FileNotFoundError(f'Build the required target first; missing {names}')


def copy_licenses(build, package, cache):
    switches = {key: switch(value) for key, value in cache.items()}
    for component in COMPONENTS:
        name = component['id']
        # <project>_SOURCE_DIR may point inside the archive (Expat uses expat/).
        # License manifest paths are relative to the FetchContent archive root.
        deps = Path(cache.get('FETCHCONTENT_BASE_DIR') or build / '_deps')
        source_dir = Path(cache.get(f'FETCHCONTENT_SOURCE_DIR_{name.upper()}') or
                          deps / f'{name}-src')
        for item in component['files']:
            condition = component['when'] if item['when'] is None else item['when']
            # The same crypto dependency is also linked by LCP without PDF.
            if name == 'mbedtls':
                condition += '|EXR_ENABLE_LCP'
            if enabled(condition, switches):
                base = source_dir if item['origin'] == 'upstream' else ROOT
                copy(base / item['path'], package / item['installed'])


def collect(build, package, target, config):
    cache = read_cache(build / 'CMakeCache.txt')
    if switch(cache.get('EXR_SANITIZE')) == 'ON':
        raise ValueError('Distributable SDK packages require -DEXR_SANITIZE=OFF')
    required = ('EXR_BUILD_SHARED_COMPAT', 'EXR_ENABLE_PDF', 'EXR_ENABLE_PDF_EDIT',
                'EXR_ENABLE_AUDIO', 'EXR_ENABLE_LIBRARY', 'EXR_BUILD_TEXT_INDEX')
    disabled = [key for key in required if switch(cache.get(key)) != 'ON']
    if disabled:
        raise ValueError('The full public SDK requires: ' +
                         ' '.join(f'-D{key}=ON' for key in disabled))
    directories = [build / config, build / 'bin' / config, build / 'lib' / config,
                   build, build / 'bin', build / 'lib']
    for header in sorted((ROOT / 'include/exr').glob('*.h')):
        copy(header, package / 'include/exr' / header.name)
    copy(build / 'generated/include/exr/version.h', package / 'include/exr/version.h')
    copy(ROOT / 'include/exreader.h', package / 'include/exreader.h')
    if target == 'win-x64':
        library = artifact(directories, ['libexreader.dll', 'exreader.dll'])
        import_lib = artifact(directories, ['libexreader.dll.a', 'exreader.lib', 'libexreader.lib'])
        copy(library, package / 'lib' / library.name)
        copy(import_lib, package / 'lib' / import_lib.name)
        # Windows searches beside the executable; consumers can also add lib to PATH.
        copy(library, package / 'bin' / library.name)
        executable = 'exr-info.exe'
    else:
        filename = 'libexreader.so' if target == 'linux-x64' else 'libexreader.dylib'
        library = artifact(directories, [filename])
        pattern = 'libexreader.so*' if target == 'linux-x64' else 'libexreader*.dylib'
        for candidate in sorted(library.parent.glob(pattern)):
            copy(candidate, package / 'lib' / candidate.name)
        executable = 'exr-info'
    copy(artifact(directories, [executable]), package / 'bin' / executable)
    copy(ROOT / 'examples/minimal/main.c', package / 'examples/minimal/main.c')
    copy(ROOT / 'tests/fixtures/layout.epub', package / 'examples/minimal/sample.epub')
    copy(ROOT / 'tests/fixtures/fonts/primary.ttf', package / 'examples/minimal/font.ttf')
    copy(ROOT / 'tests/fixtures/fonts/README.md', package / 'examples/minimal/FONT-LICENSE.md')
    for name in ('LICENSE', 'THIRD_PARTY_NOTICES.md', 'VERSION'):
        copy(ROOT / name, package / name)
    copy(ROOT / 'tools/release/README.md', package / 'README.md')
    copy_licenses(build, package, cache)
    lines = []
    for path in sorted(package.rglob('*')):
        if path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            lines.append(f'{digest}  {path.relative_to(package).as_posix()}\n')
    (package / 'SHA256SUMS').write_text(''.join(lines), encoding='utf-8', newline='\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'dist')
    parser.add_argument('--config', default='Release')
    args = parser.parse_args()
    machine = platform.machine().lower()
    target = {('Windows', 'amd64'): 'win-x64', ('Windows', 'x86_64'): 'win-x64',
              ('Linux', 'x86_64'): 'linux-x64', ('Darwin', 'arm64'): 'macos-arm64'}.get(
                  (platform.system(), machine))
    if target is None:
        parser.error('Build natively on Windows x64, Linux x64, or macOS arm64')
    version = (ROOT / 'VERSION').read_text(encoding='utf-8').strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('VERSION must contain major.minor.patch')
    build, output = args.build_dir.resolve(), args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    name = f'exreader-{version}-{target}'
    destination = output / name
    suffix = '.zip' if target == 'win-x64' else '.tar.gz'
    archive = output / (name + suffix)
    with tempfile.TemporaryDirectory(prefix='.exreader-package-', dir=output) as temporary:
        package = Path(temporary) / name
        collect(build, package, target, args.config)
        subprocess.run([sys.executable, str(ROOT / 'tools/release/check_release.py'),
                        str(package)], check=True)
        temporary_archive = Path(temporary) / archive.name
        if target == 'win-x64':
            with zipfile.ZipFile(temporary_archive, 'w', zipfile.ZIP_DEFLATED) as stream:
                for path in sorted(package.rglob('*')):
                    if path.is_file():
                        stream.write(path, path.relative_to(package.parent).as_posix())
        else:
            with tarfile.open(temporary_archive, 'w:gz') as stream:
                stream.add(package, arcname=name)
        subprocess.run([sys.executable, str(ROOT / 'tools/release/check_release.py'),
                        str(temporary_archive)], check=True)
        # Only replace this exact, validated package child, never an arbitrary path.
        if destination.is_symlink() or destination.resolve().parent != output:
            raise ValueError(f'Unsafe package destination: {destination}')
        if destination.exists():
            shutil.rmtree(destination)
        package.rename(destination)
        temporary_archive.replace(archive)
    print(f'Package: {archive}')
    print(f'Archive bytes: {archive.stat().st_size}')
    print(f'Archive SHA256: {hashlib.sha256(archive.read_bytes()).hexdigest()}')
    print(f'Unpacked: {destination}')


if __name__ == '__main__':
    main()
