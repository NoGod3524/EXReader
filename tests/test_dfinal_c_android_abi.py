# SPDX-License-Identifier: MIT
"""Keep the APK ELF inspector strict for both emulator and device ABIs."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from build_android_host import elf_check


class AndroidAbiChecks(unittest.TestCase):
    def test_machine_and_load_alignment(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'libhost.so'
            for abi, machine in [('x86_64', 62), ('arm64-v8a', 183)]:
                data = bytearray(120)
                data[:6] = b'\x7fELF\x02\x01'
                struct.pack_into('<H', data, 18, machine)
                struct.pack_into('<Q', data, 32, 64)
                struct.pack_into('<HH', data, 54, 56, 1)
                struct.pack_into('<I', data, 64, 1)
                struct.pack_into('<Q', data, 112, 16384)
                path.write_bytes(data)
                self.assertEqual(elf_check(path, abi), {'machine': machine, 'load_alignments': [16384]})
                wrong_abi = 'arm64-v8a' if abi == 'x86_64' else 'x86_64'
                with self.assertRaisesRegex(SystemExit, 'expected ' + wrong_abi):
                    elf_check(path, wrong_abi)
                struct.pack_into('<Q', data, 112, 4096)
                path.write_bytes(data)
                with self.assertRaisesRegex(SystemExit, 'below 16 KiB'):
                    elf_check(path, abi)


if __name__ == '__main__':
    unittest.main()
