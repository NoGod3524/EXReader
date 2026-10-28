"""Actions-only negative protocol fixtures; never run in the source workspace."""
import io
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path

import contract as C


class ContractTests(unittest.TestCase):
    def bundle(self, names):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            for name in names:
                archive.writestr(name, b'x')
        stream.seek(0)
        return zipfile.ZipFile(stream)

    def test_archive_valid(self):
        with self.bundle(['a/b.txt', 'other.txt']) as archive:
            self.assertEqual(len(C.safe_members(archive)), 2)

    def test_archive_alias_and_traversal_rejected(self):
        for names in (['../x'], ['/x'], ['C:/x'], ['a\\b'], ['a/./b'], ['a//b'],
                      ['x', 'x'], ['a', 'a/b'], ['a/b', 'a'], ['A/b', 'a/c'],
                      ['caf\u00e9/a', 'cafe\u0301/b']):
            with self.subTest(names=names), self.bundle(names) as archive:
                with self.assertRaises(ValueError):
                    C.safe_members(archive)

    def test_symlink_archive_rejected(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            info = zipfile.ZipInfo('a'); info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, '../outside')
        stream.seek(0)
        with zipfile.ZipFile(stream) as archive, self.assertRaises(ValueError):
            C.safe_members(archive)

    def map_text(self):
        return '\n'.join('LOAD ' + p for p in ('/repo/' + C.SDK + '/lib/libsdk.a',
            '/repo/' + C.RAW + '/lib/libproduct.a', 'gtk-host/libexreader-linux-reading.a',
            'CMakeFiles/exreader-linux.dir/main.c.o', '/usr/lib/x86_64-linux-gnu/libc.so'))

    def test_final_map_has_exact_final_inputs(self):
        loads = C.project_loads(self.map_text(), '/repo')
        self.assertIn(C.HOST + '/gtk-host/libexreader-linux-reading.a', loads['project'])
        self.assertIn(C.HOST + '/CMakeFiles/exreader-linux.dir/main.c.o', loads['project'])

    def test_no_raw_host_or_missing_prefix_substitution(self):
        for text in ('', self.map_text().replace('/repo/' + C.SDK, '/outside/sdk'),
                     self.map_text().replace('/repo/' + C.RAW, '/repo/build/raw-host'),
                     self.map_text().replace('LOAD gtk-host/libexreader-linux-reading.a', 'discarded'),
                     self.map_text().replace('LOAD /repo/' + C.SDK + '/lib/libsdk.a', 'discarded'),
                     self.map_text().replace('LOAD /repo/' + C.RAW + '/lib/libproduct.a', 'discarded')):
            with self.subTest(text=text), self.assertRaises(ValueError):
                C.project_loads(text, '/repo')

    def test_inventory_rejects_omission_and_changed_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            names = set(C.REQUIRED)
            for prefix in C.PREFIXES:
                names.update(prefix + p for p in ('/include/public.h', '/lib/libmodule.a', '/lib/cmake/Example/ExampleConfig.cmake'))
            records = {}
            for name in names:
                path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'evidence')
                records[name] = dict(bytes=8, sha256=C.sha(b'evidence'))
            (root / 'inventory.json').write_text('{}')
            manifest = dict(files=records)
            self.assertTrue(C.verify_files(root, manifest))
            (root / C.MAP).write_bytes(b'drifted!')
            with self.assertRaises(ValueError):
                C.verify_files(root, manifest)
            (root / C.MAP).write_bytes(b'evidence')
            del records[C.MAP]
            with self.assertRaises(ValueError):
                C.verify_files(root, manifest)


if __name__ == '__main__':
    C.actions_only()
    unittest.main()
