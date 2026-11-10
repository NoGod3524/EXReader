"""Regression for dependency versions, quoted definitions and stale provenance."""
import argparse
import json
import tempfile
from pathlib import Path

from manifest import capture, dependencies, sha, snapshot
from test_check_exports import macho


def main():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        source, build, output = root / 'source', root / 'build', root / 'out'
        (source / 'cmake').mkdir(parents=True)
        (source / 'tools').mkdir()
        (source / 'src').mkdir()
        (source / 'CMakeLists.txt').write_text('project(provenance C)\n')
        (source / 'tools/layers.json').write_text('{}\n')
        (source / 'src/probe.c').write_text('int probe(void) { return 1; }\n')
        build.mkdir()
        settings = {
            'CMAKE_SYSTEM_NAME': 'Darwin', 'configuration': 'Release',
            'CMAKE_C_COMPILER_ID': 'AppleClang', 'CMAKE_C_COMPILER_VERSION': '17.0',
            'CMAKE_C_COMPILER': '/usr/bin/clang', 'CMAKE_VERSION': '4.4.5',
            'CMAKE_GENERATOR': 'Ninja', 'CMAKE_C_FLAGS': '',
            'CMAKE_C_FLAGS_RELEASE': '-O3 -DNDEBUG', 'CMAKE_POSITION_INDEPENDENT_CODE': 'ON',
        }
        fixtures = {
            'expat': ('expat/lib/expat.h', '#  define XML_MAJOR_VERSION 2\n#  define XML_MINOR_VERSION 9\n#  define XML_MICRO_VERSION 0\n', '2.9.0'),
            'freetype': ('include/freetype/freetype.h', '#define FREETYPE_MAJOR 2\n#define FREETYPE_MINOR 15\n#define FREETYPE_PATCH 0\n', '2.15.0'),
            'miniz': ('CMakeLists.txt', 'project(miniz C)\nset(MINIZ_API_VERSION 3)\nset(MINIZ_MINOR_VERSION 1)\nset(MINIZ_PATCH_VERSION 2)\n', '3.1.2'),
            'zlib': ('zlib.h', '#define ZLIB_VERSION "1.3.1"\n', '1.3.1'),
        }
        declarations = []
        for name, (header, content, _) in fixtures.items():
            directory = root / 'deps' / name
            path = directory / header
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            settings[name + '_SOURCE_DIR'] = str(directory)
            declarations.append(f'FetchContent_Declare({name} URL "https://example.invalid/{name}" URL_HASH SHA256={"a" * 64})')
        (source / 'cmake/deps.cmake').write_text('\n'.join(declarations))
        observed = dependencies(settings, source)
        assert {k: v['version'] for k, v in observed.items()} == {k: v[2] for k, v in fixtures.items()}
        disabled = {**settings, 'zlib_SOURCE_DIR': ''}
        assert dependencies(disabled, source)['zlib']['enabled'] is False

        properties = build / 'targets-Release'
        properties.mkdir()
        quoted = 'EXR_STATIC;MBEDTLS_CONFIG_FILE="exr_crypto_config.h"'
        (properties / 'base.COMPILE_DEFINITIONS.txt').write_text(quoted)
        settings['target_properties_directory'] = str(properties)
        settings_path, snapshot_path = build / 'settings-Release.json', build / 'source.json'
        settings_path.write_text(json.dumps(settings))
        snapshot_path.write_text(json.dumps(snapshot(source)))
        binary = root / 'libexreader.dylib'
        binary.write_bytes(macho([('exr_probe', 0xf)]))
        (build / 'public-symbols.txt').write_text('exr_probe\n')
        args = argparse.Namespace(source=source, build=build, out=output,
                                  settings=settings_path, snapshot=snapshot_path, binary=binary)
        capture(args)
        report = json.loads((output / 'build-manifest-macos.json').read_text())
        assert report['compile_options']['object_targets']['base.COMPILE_DEFINITIONS'] == quoted
        assert report['artifact']['sha256'] == sha(binary.read_bytes())
        assert report['artifact']['size_bytes'] == binary.stat().st_size
        assert report['artifact']['exported_symbol_count'] == 1
        assert report['artifact']['slices'][0]['symbols'] == ['exr_probe']
        assert (output / 'targets-Release/base.COMPILE_DEFINITIONS.txt').read_text() == quoted

        binary.write_bytes(macho([('exr_probe', 0xf), ('vendor_leak', 0xf)]))
        try:
            capture(args)
        except ValueError as error:
            assert 'vendor_leak' in str(error)
        else:
            raise AssertionError('unexpected exported symbol accepted')
        binary.write_bytes(macho([('exr_probe', 0xf)]))

        (source / 'src/probe.c').write_text('int probe(void) { return 2; }\n')
        try:
            capture(args)
        except ValueError as error:
            assert 'source changed after configuration' in str(error)
        else:
            raise AssertionError('mutated source accepted under stale snapshot')
    print('PASS manifest: actual versions, disabled dependency, quoted definitions, artifact identity, stale source rejection')


if __name__ == '__main__':
    main()
