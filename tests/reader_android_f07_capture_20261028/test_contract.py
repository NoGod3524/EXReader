"""New collector-only cases, never substitutes for original host assertions."""
import struct
import unittest

from contract import ROOT, actions_only, elf_allocated


def fixture(payload=b'0123456789abcdef', debug=b'debug', machine=62):
    """Synthetic parser fixture is constructed only by the Actions test process."""
    names = b'\0.shstrtab\0.dynamic\0.debug_info\0'
    result = bytearray(640)
    result[:16] = b'\x7fELF\x02\x01\x01' + b'\0' * 9
    struct.pack_into('<HHIQQQIHHHHHH', result, 16, 3, machine, 1, 0,
                     64, 384, 0, 64, 56, 1, 64, 4, 1)
    struct.pack_into('<IIQQQQQQ', result, 64, 1, 6, 0, 0, 0, 320, 320, 4096)
    result[128:128 + len(names)] = names
    result[192:192 + len(payload)] = payload
    result[256:256 + len(debug)] = debug
    sections = [(0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
                (1, 3, 0, 0, 128, len(names), 0, 0, 1, 0),
                (11, 6, 3, 192, 192, len(payload), 0, 0, 8, 16),
                (20, 1, 0, 0, 256, len(debug), 0, 0, 1, 0)]
    for index, section in enumerate(sections):
        struct.pack_into('<IIQQQQIIQQ', result, 384 + index * 64, *section)
    return bytes(result)


class CaptureContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        actions_only()

    def test_debug_removal_is_not_whole_file_identity(self):
        first, second = fixture(), fixture(debug=b'')
        self.assertNotEqual(first, second)
        self.assertEqual(elf_allocated(first), elf_allocated(second))

    def test_allocated_byte_mutation_rejected_by_binding(self):
        self.assertNotEqual(elf_allocated(fixture())['allocated_sha256'],
                            elf_allocated(fixture(payload=b'X123456789abcdef'))['allocated_sha256'])

    def test_layout_mutation_changes_binding(self):
        changed = bytearray(fixture())
        struct.pack_into('<Q', changed, 64 + 40, 4096)
        self.assertNotEqual(elf_allocated(fixture())['allocated_sha256'],
                            elf_allocated(changed)['allocated_sha256'])

    def test_non_x86_64_is_not_silently_accepted(self):
        with self.assertRaises(ValueError):
            elf_allocated(fixture(machine=183))

    def test_truncation_refused(self):
        with self.assertRaises(ValueError):
            elf_allocated(fixture()[:-1])

    def test_missing_dynamic_section_refused(self):
        changed = bytearray(fixture())
        struct.pack_into('<Q', changed, 384 + 2 * 64 + 8, 0)
        with self.assertRaises(ValueError):
            elf_allocated(changed)

    def test_original_producer_and_runtime_settings_unchanged(self):
        import yaml
        old = yaml.safe_load((ROOT / '.github/workflows/android-sdk342-package.yml').read_text())
        new = yaml.safe_load((ROOT / '.github/workflows/android-f07-capture-20261028.yml').read_text())
        for field in ('permissions', 'defaults', 'env'):
            self.assertEqual(old[field], new[field])
        for field in ('runs-on', 'timeout-minutes'):
            self.assertEqual(old['jobs']['android'][field], new['jobs']['android'][field])
        first, second = old['jobs']['android']['steps'], new['jobs']['android']['steps']
        for action in ('actions/checkout@v4', 'actions/setup-java@v4', 'actions/setup-python@v5',
                       'gradle/actions/setup-gradle@v4', 'reactivecircus/android-emulator-runner@v2'):
            left = [s for s in first if s.get('uses') == action]
            right = [s for s in second if s.get('uses') == action]
            self.assertEqual(len(left), 1)
            self.assertEqual(len(right), 1)
            self.assertEqual(left[0].get('with'), right[0].get('with'))
        build = 'python3 tests/android_sdk342_package/run.py build'
        self.assertEqual(sum(s.get('run') == build for s in first), 1)
        self.assertEqual(sum(s.get('run') == build for s in second), 1)


if __name__ == '__main__':
    actions_only()
    unittest.main()
