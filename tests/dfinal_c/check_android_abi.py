# SPDX-License-Identifier: MIT
"""Check native APK ABI selection without claiming Android runtime coverage."""
from pathlib import Path
import struct
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
import build_android_host as host


def elf(machine):
    data = bytearray(120)
    data[:6] = b'\x7fELF\x02\x01'
    struct.pack_into('<H', data, 18, machine)
    struct.pack_into('<Q', data, 32, 64)
    struct.pack_into('<HH', data, 54, 56, 1)
    struct.pack_into('<I', data, 64, 1)
    struct.pack_into('<Q', data, 112, 16384)
    return data


def main():
    checks = 0
    # These are synthetic ABI fixtures; real readelf/SONAME checks run on the Actions APK.
    host.elf_dynamic = lambda path: {'soname': '', 'needed': []}
    with tempfile.TemporaryDirectory(prefix='android-abi-') as temporary:
        apk = Path(temporary) / 'host.apk'
        for abi, machine in (('x86_64', 62), ('arm64-v8a', 183)):
            for scenario in ('valid', 'wrong-machine', 'extra-abi', 'missing-library'):
                names = ('libexreader_product.so', 'libexreader.so', 'libexreader_jni.so', 'libexreader_host.so')
                with zipfile.ZipFile(apk, 'w') as archive:
                    for name in names[:-1] if scenario == 'missing-library' else names:
                        archive.writestr('lib/' + abi + '/' + name, elf(machine if scenario != 'wrong-machine' else 999))
                    if scenario == 'extra-abi':
                        archive.writestr('lib/other/libexreader.so', elf(machine))
                try:
                    result = host.inspect_apk(apk, abi)
                except SystemExit:
                    assert scenario != 'valid', (abi, scenario)
                else:
                    assert scenario == 'valid', (abi, scenario)
                    assert all(entry['machine'] == machine for entry in result.values())
                print(abi + ': ' + scenario + (' accepted' if scenario == 'valid' else ' rejected'))
                checks += 1
    print(str(checks) + ' Android APK ABI checks passed (synthetic files; no device execution)')


if __name__ == '__main__':
    main()
