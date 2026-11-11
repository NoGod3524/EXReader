#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Small acceptance/rejection regression for the release gate; no compiler needed."""
import hashlib
from pathlib import Path
import shutil
import struct
import tarfile
import tempfile
import zipfile

from check_release import API_HEADERS, ROOT, check_package, source_version
from test_check_exports import macho


def pe(count):
    names = [f'exr_fixture_{i}'.encode() + b'\0' for i in range(count)]
    data = bytearray(512 + 40 + count * 4 + sum(map(len, names)))
    data[:2] = b'MZ'
    struct.pack_into('<I', data, 60, 64)
    data[64:68] = b'PE\0\0'
    struct.pack_into('<HHIIIHH', data, 68, 0x8664, 1, 0, 0, 0, 240, 0)
    struct.pack_into('<H', data, 88, 0x20b)
    struct.pack_into('<II', data, 200, 0x1000, len(data)-512)
    struct.pack_into('<IIII', data, 336, len(data)-512, 0x1000, len(data)-512, 512)
    struct.pack_into('<I', data, 536, count)
    struct.pack_into('<I', data, 544, 0x1000+40)
    offset = 552 + count * 4
    for index, name in enumerate(names):
        struct.pack_into('<I', data, 552+index*4, 0x1000+offset-512)
        data[offset:offset+len(name)] = name
        offset += len(name)
    return bytes(data)


def seal(package):
    lines = [f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(package).as_posix()}'
             for path in sorted(package.rglob('*')) if path.is_file() and path.name != 'SHA256SUMS']
    (package / 'SHA256SUMS').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main():
    version = source_version(ROOT)
    with tempfile.TemporaryDirectory(prefix='exreader release test ') as temporary:
        root = Path(temporary)
        source = root / 'source'
        (source / 'cmake').mkdir(parents=True)
        (source / 'include/exr').mkdir(parents=True)
        (source / 'VERSION').write_text(version + '\n', encoding='utf-8')
        shutil.copy2(ROOT / 'cmake/versions.cmake', source / 'cmake/versions.cmake')
        shutil.copy2(ROOT / 'include/exr/version.h', source / 'include/exr/version.h')
        package = root / f'exreader-{version}-win-x64'
        for directory in ('include/exr', 'bin', 'lib', 'examples/minimal'):
            (package / directory).mkdir(parents=True)
        for name in API_HEADERS | {'version.h'}:
            shutil.copy2(ROOT / 'include/exr' / name, package / 'include/exr' / name)
        for name in ('LICENSE', 'README.md', 'VERSION'):
            (package / name).write_text(version + '\n', encoding='utf-8')
        (package / 'examples/minimal/main.c').write_text('int main(void) { return 0; }\n', encoding='utf-8')
        for name in ('sample.epub', 'font.ttf', 'FONT-LICENSE.md'):
            (package / 'examples/minimal' / name).write_bytes(b'regression fixture\n')
        binary = pe(389)
        (package / 'lib/exreader.dll').write_bytes(binary)
        (package / 'lib/exreader.lib').write_bytes(b'!<arch>\n')
        (package / 'bin/exreader.dll').write_bytes(binary)
        (package / 'bin/exr-info.exe').write_bytes(binary)
        seal(package)
        assert check_package(package, source)['passed']
        header = package / 'include/exr/version.h'
        header.write_bytes(header.read_bytes().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))
        seal(package)
        assert check_package(package, source)['passed']
        archive_path = root / (package.name + '.zip')
        with zipfile.ZipFile(archive_path, 'w') as archive:
            for path in package.rglob('*'):
                if path.is_file():
                    archive.write(path, path.relative_to(root).as_posix())
        assert check_package(archive_path, source)['passed']

        def rejected(relative, changed, expected, reseal=True):
            path = package / relative
            original = path.read_bytes()
            if changed is None:
                path.unlink()
            else:
                path.write_bytes(changed)
            if reseal:
                seal(package)
            report = check_package(package, source)
            assert not report['passed'], relative
            assert any(not row['passed'] and row['check'] == expected for row in report['checks']), report
            path.write_bytes(original)
            seal(package)

        rejected('LICENSE', b'tampered\n', 'SHA256SUMS coverage and content', reseal=False)
        rejected('include/exr/core.h', None, 'public headers')
        rejected('examples/minimal/font.ttf', None, 'required SDK files')
        rejected('VERSION', b'0.0.0\n', 'version identity')
        rejected('examples/minimal/main.c', b'/* line */\n' * 81, 'minimal example line limit')
        rejected('lib/exreader.dll', pe(388), 'public export count')
        wrong_cpu = binary[:68] + struct.pack('<H', 0xaa64) + binary[70:]
        rejected('bin/exr-info.exe', wrong_cpu, 'library and CLI architecture')
        seal(package)
        with zipfile.ZipFile(root / (package.name + '.zip'), 'w') as archive:
            archive.writestr(package.name + '/../escape', 'unsafe')
        assert not check_package(root / (package.name + '.zip'), source)['passed']
        assert check_package(package, source)['passed']
        for relative in ('lib/exreader.dll', 'lib/exreader.lib', 'bin/exreader.dll', 'bin/exr-info.exe'):
            (package / relative).unlink()
        package = package.rename(root / f'exreader-{version}-macos-arm64')
        binary = macho([(f'exr_fixture_{i}', 0xf) for i in range(389)])
        (package / 'lib/libexreader.dylib').write_bytes(binary)
        (package / 'bin/exr-info').write_bytes(binary)
        seal(package)
        def executable(member):
            if member.name.endswith('/bin/exr-info'):
                member.mode = 0o755
            return member
        archive_path = root / (package.name + '.tar.gz')
        with tarfile.open(archive_path, 'w:gz') as archive:
            archive.add(package, arcname=package.name, filter=executable)
        assert check_package(archive_path, source)['passed']
    print('PASS release gate: directory/ZIP/tar.gz, LF/CRLF header; rejects tampering, missing header, version mismatch, 81 lines, 388 exports, wrong CPU, traversal')


if __name__ == '__main__':
    main()
