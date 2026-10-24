"""Run the unchanged G02--G06 judges and the new installed-prefix chain in Actions."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

REPO = Path(__file__).resolve().parents[2]
PYTHON = sys.executable


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
    parser = argparse.ArgumentParser()
    parser.add_argument('--prefix', type=Path, required=True)
    parser.add_argument('--relocated', action='store_true')
    args = parser.parse_args()
    prefix = args.prefix.resolve()
    phase = 'relocated' if args.relocated else 'initial'
    output = REPO / 'build/composition/g1' / phase
    output.mkdir(parents=True, exist_ok=True)
    scratch = REPO / ('build/g1-' + phase)
    scratch.mkdir(parents=True, exist_ok=True)
    suffix = '.exe' if os.name == 'nt' else ''
    reports = []

    def run(label, command, timeout=1800):
        command = [str(x) for x in command]
        print('RUN ' + label, flush=True)
        done = subprocess.run(command, cwd=REPO, capture_output=True, text=True,
                              encoding='utf-8', errors='replace', timeout=timeout)
        (output / (label + '.log')).write_text('$ ' + ' '.join(command) + '\n' +
                done.stdout + '\n' + done.stderr, encoding='utf-8')
        print(done.stdout[-16000:], flush=True)
        if done.returncode:
            print(done.stderr[-10000:], flush=True)
            raise RuntimeError(label + ' exited ' + str(done.returncode))

    def build(label, source, install=None, packages=None):
        binary = scratch / label
        command = ['cmake', '-S', source, '-B', binary, '-G', 'Ninja',
                   '-DCMAKE_BUILD_TYPE=Release', '-DEXR_SDK=' + str(prefix),
                   '-DCMAKE_PREFIX_PATH=' + (packages or str(prefix)),
                   '-DEXR_MODULE_PREFIX=' + str(prefix)]
        if install:
            command.append('-DCMAKE_INSTALL_PREFIX=' + str(install))
        run(label + '-configure', command)
        run(label + '-build', ['cmake', '--build', binary, '--parallel', '4', '--verbose'])
        if install:
            run(label + '-install', ['cmake', '--install', binary])
        return binary

    def suite(label, action):
        try:
            action()
            reports.append({'name': label, 'pass': True})
        except Exception as error:
            reports.append({'name': label, 'pass': False, 'error': str(error)})
            print('FAIL ' + label + ': ' + str(error), flush=True)

    def chain():
        source = scratch / 'consumer-source'
        shutil.copytree(REPO / 'tests/reader_module_composition/consumer', source)
        for name in ('g1_chain.cpp', 'codec_scope.c'):
            shutil.copy2(Path(__file__).parent / 'consumer' / name, source / name)
        shutil.copy2(REPO / 'tests/reader_reading_state_codec/codec.c', source / 'codec.c')
        with (source / 'CMakeLists.txt').open('a', encoding='utf-8') as handle:
            handle.write('\n' + (Path(__file__).parent / 'consumer/extend.cmake').read_text())
        binary = build('chain', source)
        raw = output / 'chain.json'
        run('chain-consumer', [binary / ('g1-chain' + suffix), REPO / 'tests/fixtures',
                              output / 'chain-work', raw])
        report = json.loads(raw.read_text())
        assert report['failures'] == 0 and report['resolved_state'] == 'FOUND'
        checks = report['checks']
        assert len(checks) >= 20 and report['check_count'] == len(checks)
        assert len({item['name'] for item in checks}) == len(checks) and all(item['pass'] for item in checks)
        key = 'txt:' + hashlib.sha256((REPO / 'tests/fixtures/sample.txt').read_bytes()).hexdigest()
        assert report['book_key'] == key
        exported = [json.loads(line) for line in (output / 'chain-work/before.jsonl').read_text().splitlines()]
        assert len(exported) == 3, 'header, one annotation, footer required'
        # Raw wire bytes and all export semantics are independently judged by
        # the unchanged G05 suite below; this check binds the integrated chain.
        import importlib.util
        sys.path.insert(0, str(REPO / 'tests/reader_module_composition'))
        spec = importlib.util.spec_from_file_location('g1_maps', REPO / 'tests/reader_module_composition/check_composition.py')
        maps = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(maps)
        mapping = (binary / 'g1-chain.map').read_text(errors='replace')
        providers = maps.archive_providers(mapping)
        assert len(providers) == 1 and 'reader_catalog_sqlite' in providers[0]
        assert not maps.direct_providers(mapping)
        run('codec-only', [PYTHON, Path(__file__).parent / 'check_codec.py',
                           '--consumer', binary / ('g1-codec-only' + suffix),
                           '--map', binary / 'g1-codec.map', '--output', output / 'codec'])
        for name in ('g1-chain', 'g1-codec-only'):
            exe = binary / (name + suffix)
            shutil.copy2(exe, output / exe.name)
        shutil.copy2(binary / 'g1-chain.map', output / 'g1-chain.map')
        shutil.copy2(binary / 'g1-codec.map', output / 'g1-codec.map')

    suite('new-five-module-chain-and-sdk-free-product-link', chain)
    if not args.relocated:
        def thumbnails():
            binary = build('thumbnails', REPO / 'tests/reader_thumbnails/consumer')
            fixtures = scratch / 'thumbnail-fixtures'
            run('thumbnail-fixtures', [PYTHON, REPO / 'tests/reader_thumbnails/make_fixtures.py', fixtures])
            run('thumbnail-judge', [PYTHON, REPO / 'tests/reader_thumbnails/check_thumbnails.py',
                '--probe', binary / ('thumb-probe' + suffix), '--c-consumer', binary / ('thumb-c-consumer' + suffix),
                '--regress', binary / ('thumb-regress' + suffix), '--fault', binary / ('thumb-fault' + suffix),
                '--fixtures', fixtures, '--repo-fixtures', REPO / 'tests/fixtures',
                '--installed', prefix, '--output', output / 'thumbnails'], timeout=3600)

        def reading_commands():
            binary = build('reading-commands', REPO / 'tests/reader_reading_commands/consumer')
            fixtures = scratch / 'reading-fixtures'
            run('reading-fixtures', [PYTHON, REPO / 'tests/reader_reading_commands/make_fixtures.py', fixtures])
            run('reading-judge', [PYTHON, REPO / 'tests/reader_reading_commands/check_reading_commands.py',
                '--probe', binary / ('reading-commands-probe' + suffix),
                '--c-consumer', binary / ('reading-commands-c-consumer' + suffix), '--fixtures', fixtures,
                '--font', REPO / 'tests/fixtures/fonts/primary.ttf', '--link-map', binary / 'reading-commands-link.map',
                '--output', output / 'reading-commands'])

        def annotation_view():
            binary = build('annotation-view', REPO / 'tests/reader_annotation_view/consumer')
            run('view-judge', [PYTHON, REPO / 'tests/reader_annotation_view/check_annotation_view.py',
                '--probe', binary / ('annotation-view-probe' + suffix),
                '--c-consumer', binary / ('annotation-view-c-consumer' + suffix),
                '--link-map', binary / 'annotation-view-link.map', '--output', output / 'annotation-view'])

        def annotation_export():
            binary = build('annotation-export', REPO / 'tests/reader_annotation_export/consumer')
            fixtures = scratch / 'export-fixtures'
            run('export-fixtures', [PYTHON, REPO / 'tests/reader_annotation_export/make_fixtures.py', fixtures])
            run('export-judge', [PYTHON, REPO / 'tests/reader_annotation_export/check_export.py',
                '--probe', binary / ('annotation-export-probe' + suffix),
                '--c-consumer', binary / ('annotation-export-c-consumer' + suffix), '--fixtures', fixtures,
                '--output', output / 'annotation-export'])

        def local_downloads():
            binary = build('local-downloads', REPO / 'tests/reader_local_downloads/consumer')
            library = prefix / 'lib' / ('reader_local_downloads.lib' if os.name == 'nt' else 'libreader_local_downloads.a')
            common = ['--cpp', binary / ('ld-cpp-consumer' + suffix), '--fixtures', REPO / 'tests/fixtures',
                      '--library', library, '--path-extra', prefix / 'bin', '--path-extra', prefix / 'lib']
            run('local-judge', [PYTHON, REPO / 'tests/reader_local_downloads/check_local_downloads.py',
                '--probe', binary / ('ld-probe' + suffix), '--work', scratch / 'ld-work',
                '--output', output / 'local-downloads', *common])
            archive = scratch / 'old.tar'
            with archive.open('wb') as handle:
                subprocess.run(['git', 'archive', '7817caa968ce9350ed1c6b3712d31a13c2da8fd8',
                                'apps/reader/local-downloads'], cwd=REPO, stdout=handle, check=True)
            old = scratch / 'old-source'
            old.mkdir()
            with tarfile.open(archive) as bundle:
                bundle.extractall(old)
            old_prefix = scratch / 'old-prefix'
            build('old-module', old / 'apps/reader/local-downloads', install=old_prefix)
            old_binary = build('old-consumer', REPO / 'tests/reader_local_downloads/consumer',
                               packages=str(old_prefix) + ';' + str(prefix))
            run('local-regressions', [PYTHON, REPO / 'tests/reader_local_downloads/check_regressions.py',
                '--old-probe', old_binary / ('ld-probe' + suffix), '--new-probe', binary / ('ld-probe' + suffix),
                '--work', scratch / 'ld-regressions', '--output', output / 'local-regressions', *common])

        for name, action in [('G02-thumbnails-original-regression-allocation', thumbnails),
                             ('G03-reading-commands', reading_commands), ('G04-annotation-view', annotation_view),
                             ('G05-annotation-export', annotation_export), ('G06-local-downloads-and-old-build-control', local_downloads)]:
            suite(name, action)
    consumers = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.glob('g1-*') if p.is_file()}
    result = dict(accepted=all(item['pass'] for item in reports), source_sha=os.environ['GITHUB_SHA'],
                  run_id=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'],
                  platform=os.environ['RUNNER_OS'], phase=phase, checks=reports, consumers=consumers,
                  complete_product=False)
    (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)
    return 0 if result['accepted'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
