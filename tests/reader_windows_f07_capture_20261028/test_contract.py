"""Actions-only synthetic negative tests, never native or F07 acceptance evidence."""
import hashlib
import io
import json
import stat
import sys
import unittest
import zipfile

from capture_contract import (BASE, F06, BUILD, BUILDS, PROGRAM, MAP, PACKAGED, RELOCATED,
    RECIPE, actions_only, diagnostic_argv, safe_members, validate_capture, verify_files,
    required_diagnostics)

actions_only()


def raw_json(value):
    return json.dumps(value, sort_keys=True).encode()


def info(raw):
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def bundle(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        for name, raw in files.items():
            archive.writestr(name, raw)
    stream.seek(0)
    return zipfile.ZipFile(stream)


def fixture():
    """Minimal declared shape only; its synthetic bytes are not native programs."""
    expected = dict(source_sha='a' * 40, run_id='101', attempt='1', sdk_version='3.42.0')
    root = 'D:/a/EXReader/EXReader'
    recipes = {RECIPE: info(b'unchanged old producer source fixture')}
    files = {
        'capture/source.json': raw_json(dict(expected, workspace=root, base_sha=BASE,
            recipes=recipes, passed=True)),
        PROGRAM: b'synthetic program, never executed',
        MAP: b'synthetic map; no symbol claims',
        BUILD + 'host/owner.obj': b'object fixture',
        BUILD + 'host/owner.lib': b'library fixture',
        BUILD + 'logs/sdk-build.log': b'original producer log fixture',
    }
    commands = []
    for label in BUILDS:
        for name in ('CMakeCache.txt', 'build.ninja', 'CMakeFiles/rules.ninja'):
            files[BUILD + label + '/' + name] = b'graph fixture'
        files['capture/ninja/' + label + '.commands.txt'] = b'command fixture'
        argv = ['cmake', '--build', root + '/' + BUILD + label]
        argv += ['--target', 'EXReaderWave3', '--parallel', '4'] if label == 'host' else ['--parallel', '4']
        commands.append(dict(original=argv, actual=diagnostic_argv(argv), completed=True, exit_code=0))
        if label == 'host':
            continue
        stage = 'sdk-stage' if label == 'sdk-build' else 'product-stage' if label == 'product-build' else 'raw-stage'
        installed = []
        for suffix in ('.h', '.lib', '.cmake'):
            name = BUILD + stage + '/' + label + suffix
            files[name] = b'installed fixture'
            installed.append(root + '/' + name)
        files[BUILD + label + '/install_manifest.txt'] = '\n'.join(installed).encode()
    files['capture/commands.json'] = raw_json(dict(expected, commands=commands))
    files['capture/ninja/host.commands.txt'] = (
        'cmake -E vs_link_exe --intdir=CMakeFiles/EXReaderWave3.dir -- link.exe '
        '/out:EXReaderWave3.exe /MAP:windows-host.map ' +
        ' '.join(root + '/' + BUILD + stage + '/module.lib'
            for stage in ('sdk-stage', 'product-stage', 'raw-stage'))).encode()
    required = required_diagnostics(files, root, {name: info(value) for name, value in files.items()})
    for output in required:
        files.setdefault('capture/' + output, b'synthetic diagnostic output')
    files['capture/diagnostics.json'] = raw_json(dict(expected,
        commands=[dict(value, output=output, exit_code=0) for output, value in required.items()]))
    files[PACKAGED] = files[RELOCATED] = files[PROGRAM]
    producer = dict(source_sha=expected['source_sha'], sdk_version='3.42.0',
        files={'EXReader.exe': info(files[PROGRAM])['sha256']})
    files[F06 + 'windows-payload/build.json'] = raw_json(producer)
    files[F06 + 'windows-payload/report.json'] = raw_json(dict(passed=True, checks=26))
    files[F06 + 'windows/configuration.json'] = raw_json(dict(expected,
        build_recipe_sha256=recipes[RECIPE]['sha256']))
    files[F06 + 'windows/entry.json'] = raw_json(dict(expected, passed=True,
        entry_sha256=info(files[PROGRAM])['sha256']))
    package_name = 'EXReader-windows-' + expected['source_sha'][:12] + '.zip'
    manifest = dict(source_sha=expected['source_sha'], sdk_version='3.42.0',
        target='windows', entry='EXReader/EXReader.exe',
        producer=dict(source_sha=expected['source_sha'], sdk_version='3.42.0',
            build_json_sha256=info(files[F06 + 'windows-payload/build.json'])['sha256']),
        provenance=dict(run_id='101', attempt='1'),
        files={'EXReader/EXReader.exe': info(files[PROGRAM]),
            'build.json': info(files[F06 + 'windows-payload/build.json'])},
        metadata_files=['manifest.json', 'SHA256SUMS'])
    checksums = ''.join(row['sha256'] + '  ' + name + '\n'
        for name, row in sorted(manifest['files'].items())).encode()
    delivered = {'EXReader/EXReader.exe': files[PROGRAM],
        'build.json': files[F06 + 'windows-payload/build.json'],
        'manifest.json': raw_json(manifest), 'SHA256SUMS': checksums}
    nested_stream = io.BytesIO()
    with zipfile.ZipFile(nested_stream, 'w') as nested:
        for name, raw in delivered.items():
            nested.writestr(name, raw)
            files[F06 + 'unpacked-windows/' + name] = raw
    files[F06 + 'windows/' + package_name] = nested_stream.getvalue()
    archive = dict(name=package_name, **info(nested_stream.getvalue()),
        checksums_sha256=hashlib.sha256(checksums).hexdigest())
    manifest['archive'] = archive
    files[F06 + 'windows/manifest.json'] = raw_json(manifest)
    files[F06 + 'windows/result.json'] = raw_json(dict(expected, passed=True, target='windows',
        program_sha256=info(files[PROGRAM])['sha256'], archive=archive,
        configuration_sha256=info(files[F06 + 'windows/configuration.json'])['sha256'],
        entry_report_sha256=info(files[F06 + 'windows/entry.json'])['sha256']))
    return expected, files


class CaptureContract(unittest.TestCase):
    def validate(self, files, expected):
        with bundle(files) as archive:
            return validate_capture(archive, {k: info(v) for k, v in files.items()}, expected)

    def test_only_diagnostic_native_arguments(self):
        configure = ['cmake', '-S', 'apps/reader/desktop', '-DEXR_SDK_VERSION=3.42.0']
        self.assertEqual(diagnostic_argv(configure), configure)
        old = ['cmake', '--build', 'host', '--parallel', '4', '--verbose']
        self.assertEqual(diagnostic_argv(old), old + ['--', '-d', 'keeprsp'])
        with self.assertRaises(ValueError):
            diagnostic_argv(old + ['--', '-j', '99'])

    def test_unchanged_producer_import_namespace(self):
        from run import load
        original = load('tests/reader_wave3_c09/build.py', 'capture_import_smoke')
        self.assertTrue(callable(original.compact_validate))
        self.assertTrue(sys.modules['contract'].__file__.replace('\\', '/').endswith(
            '/tests/reader_windows_compact/contract.py'))

    def test_zip_aliases_and_special_files_refused(self):
        for names in (['../x'], ['/x'], ['a\\b'], ['C:/x'], ['a//b'], ['a/./b'],
                ['A/x', 'a/y'], ['caf\u00e9/x', 'cafe\u0301/y'], ['a', 'a/x'], ['a/x', 'a']):
            with self.subTest(names=names), bundle({n: b'x' for n in names}) as archive:
                with self.assertRaises(ValueError):
                    safe_members(archive)
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            entry = zipfile.ZipInfo('symlink')
            entry.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(entry, 'outside')
        stream.seek(0)
        with zipfile.ZipFile(stream) as archive, self.assertRaises(ValueError):
            safe_members(archive)

    def test_raw_inventory_hash_and_membership(self):
        with bundle({'one': b'one'}) as archive:
            verify_files(archive, {'one': info(b'one')})
            with self.assertRaises(ValueError):
                verify_files(archive, {'one': info(b'two')})
            with self.assertRaises(ValueError):
                verify_files(archive, {})

    def test_capture_is_never_f07_admission(self):
        expected, files = fixture()
        report = self.validate(files, expected)
        self.assertTrue(report['capture_complete'])
        self.assertTrue(report['f06_identity_verified'])
        self.assertFalse(report['f07_accepted'])
        self.assertEqual(report['response_files'], [])

    def test_missing_real_inputs_fail_closed(self):
        expected, original = fixture()
        for name in (MAP, PROGRAM, BUILD + 'raw-stage/raw-annotation-import.lib',
                BUILD + 'sdk-build/install_manifest.txt',
                'capture/ninja/host.commands.txt', BUILD + 'host/owner.obj'):
            files = dict(original)
            del files[name]
            with self.subTest(name=name), self.assertRaises((ValueError, KeyError)):
                self.validate(files, expected)

    def test_other_attempt_and_changed_executable_refused(self):
        expected, files = fixture()
        with self.assertRaises(ValueError):
            self.validate(files, dict(expected, attempt='2'))
        files[PACKAGED] = b'decoy executable'
        with self.assertRaises(ValueError):
            self.validate(files, expected)

    def test_changed_commands_and_install_escape_refused(self):
        expected, original = fixture()
        files = dict(original)
        journal = json.loads(files['capture/commands.json'])
        journal['commands'][0]['actual'].append('-DNEW_PRODUCT_FLAG=ON')
        files['capture/commands.json'] = raw_json(journal)
        with self.assertRaises(ValueError):
            self.validate(files, expected)
        files = dict(original)
        files[BUILD + 'sdk-build/install_manifest.txt'] = b'D:/other/prefix/library.lib'
        with self.assertRaises(ValueError):
            self.validate(files, expected)

    def test_original_f06_floor_is_not_relaxed(self):
        expected, files = fixture()
        files[F06 + 'windows-payload/report.json'] = raw_json(dict(passed=True, checks=25))
        with self.assertRaises(ValueError):
            self.validate(files, expected)

    def test_actual_response_reference_must_be_retained(self):
        expected, files = fixture()
        link = files['capture/ninja/host.commands.txt'].decode()
        files['capture/ninja/host.commands.txt'] = (
            'cmake -E vs_link_exe --intdir=CMakeFiles/EXReaderWave3.dir -- '
            'link.exe @CMakeFiles/EXReaderWave3.rsp').encode()
        with self.assertRaises(ValueError):
            self.validate(files, expected)
        name = BUILD + 'host/CMakeFiles/EXReaderWave3.rsp'
        files[name] = link.split(' -- link.exe ', 1)[1].encode()
        report = self.validate(files, expected)
        self.assertEqual(report['final_response_files'], [name])

    def test_unpacked_nonprogram_file_is_authenticated(self):
        expected, files = fixture()
        files[F06 + 'unpacked-windows/build.json'] = b'changed metadata'
        with self.assertRaises(ValueError):
            self.validate(files, expected)

    def test_dropped_native_diagnostic_is_not_complete_capture(self):
        expected, files = fixture()
        diagnostics = json.loads(files['capture/diagnostics.json'])
        dropped = next(row for row in diagnostics['commands'] if row['output'].startswith('symbols/'))
        diagnostics['commands'].remove(dropped)
        del files['capture/' + dropped['output']]
        files['capture/diagnostics.json'] = raw_json(diagnostics)
        with self.assertRaises(ValueError):
            self.validate(files, expected)


if __name__ == '__main__':
    unittest.main()
