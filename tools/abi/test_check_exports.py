"""Small binary fixtures test missing symbols, extern filtering, archives and fat slices."""
import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from check_exports import inspect_bytes, ROOT
from platform_status import collect


def macho(names):
    strings = b'\0'
    symbols = b''
    for name, flags in names:
        symbols += struct.pack('<IBBHQ', len(strings), flags, 1, 0, 1)
        strings += ('_' + name).encode() + b'\0'
    header = struct.pack('<IIIIIIII', 0xfeedfacf, 0x100000c, 0, 1, 1, 24, 0, 0)
    command = struct.pack('<IIIIII', 2, 24, 56, len(names), 56+len(symbols), len(strings))
    return header + command + symbols + strings


def ar(member):
    # BSD extended member name, including alignment padding.
    name = b'fixture.o\0\0\0'
    member = name + member
    header = f'{"#1/12":<16}{0:<12}{0:<6}{0:<6}{"100644":<8}{len(member):<10}`\n'.encode()
    return b'!<arch>\n' + header + member + (b'\n' if len(member) % 2 else b'')


def main():
    one = macho([('exr_one', 0xf), ('exr_undefined', 1), ('exr_private', 0x1f), ('exr_local', 0xe)])
    two = macho([('exr_two', 0xf)])
    assert inspect_bytes(one)[0]['symbols'] == {'exr_one'}
    assert inspect_bytes(ar(one))[0]['symbols'] == {'exr_one'}
    # Each universal slice must pass separately: never union away a missing ABI.
    fat = struct.pack('>II', 0xcafebabe, 2)
    fat += struct.pack('>IIIII', 0x100000c, 0, 48, len(one), 0)
    fat += struct.pack('>IIIII', 0x1000007, 0, 48+len(one), len(two), 0)
    fat += one + two
    assert [p['symbols'] for p in inspect_bytes(fat)] == [{'exr_one'}, {'exr_two'}]
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        binary, contract = directory/'probe.dylib', directory/'contract.json'
        contract.write_text(json.dumps({'symbols': ['exr_one']}))
        command = [sys.executable, str(ROOT/'tools/abi/check_exports.py'), str(binary), '--contract', str(contract)]
        binary.write_bytes(one)
        assert subprocess.run(command, capture_output=True).returncode == 0
        binary.write_bytes(two)
        assert subprocess.run(command+['--allow-extra'], capture_output=True).returncode == 1
        binary.write_bytes(macho([('exr_one', 0xf), ('vendor', 0xf)]))
        assert subprocess.run(command, capture_output=True).returncode == 1
        assert subprocess.run(command+['--allow-extra'], capture_output=True).returncode == 0
        binary.write_bytes(fat)
        assert subprocess.run(command, capture_output=True).returncode == 1
        binary.write_bytes(b'not a library')
        assert subprocess.run(command, capture_output=True).returncode == 1
        binary.write_bytes(b'\x7fELF')
        assert subprocess.run(command, capture_output=True).returncode == 1
        manifest = {'artifacts': [{'platform': 'test', 'architecture': 'arm64', 'path': 'absent.so',
                                  'kind': 'library', 'sha256': 'recorded', 'status': 'CI pending'}]}
        row = collect(directory, manifest, {'exr_one'})[0]
        assert row['exists'] is False and row['observed_sha256'] is None and row['observed_abi'] is None
    print('PASS exports: extern/undefined/private, ar, per-slice fat, missing/extra, malformed, absent status')


if __name__ == '__main__':
    main()
