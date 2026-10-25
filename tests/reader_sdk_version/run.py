"""Actions-only dual SDK installation, original module consumers and mismatch rejection."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

assert os.environ.get('GITHUB_ACTIONS') == 'true'
ROOT = Path.cwd()
BUILD = ROOT/'build/sdk-version'
BUILD.mkdir(parents=True, exist_ok=True)
SDK_SOURCES = {'3.40.0': '9854061be331fe603a1822d9b2b36ee357154927',
               '3.41.0': 'b911815e26a10e7c45f50f56bf7c4e46cbca010b'}


def run(*args):
    subprocess.run([str(a) for a in args], check=True)


def build(name, source, prefix, sdk, version=None, extra=()):
    target = BUILD/name
    args = ['cmake', '-S', source, '-B', target, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
            '-DCMAKE_PREFIX_PATH=' + str(prefix) + ';' + str(sdk),
            '-DCMAKE_INSTALL_PREFIX=' + str(prefix), '-DEXR_SDK=' + str(sdk), *extra]
    if version:
        args += ['-DEXR_SDK_VERSION=' + version]
    run(*args);run('cmake', '--build', target, '--parallel', '4')
    return target


versions = {}
for version, source in SDK_SOURCES.items():
    tree = BUILD/('source-' + version);tree.mkdir()
    archive = subprocess.Popen(['git', 'archive', source], stdout=subprocess.PIPE)
    try:
        subprocess.run(['tar', '-x', '-C', str(tree)], stdin=archive.stdout, check=True)
    finally:
        archive.stdout.close()
    assert archive.wait() == 0
    sdk = BUILD/('sdk-' + version)
    run('cmake', '--preset', 'reading-library', '-S', tree, '-B', BUILD/('sdk-build-' + version),
        '-DCMAKE_INSTALL_PREFIX=' + str(sdk))
    run('cmake', '--build', BUILD/('sdk-build-' + version), '--parallel', '4')
    run('cmake', '--install', BUILD/('sdk-build-' + version))
    prefix = BUILD/('modules-' + version)
    target = build('product-' + version, 'apps/reader/store/native', prefix, sdk)
    run('cmake', '--install', target)
    for name, directory, extra in (
            ('revisions', 'apps/reader/revisions', ['-DREADER_PRODUCT_PREFIX=' + str(prefix)]),
            ('sideload', 'extras/sideload', []),
            ('reading-state', 'apps/reader/reading-state', []),
            ('search', 'apps/reader/search', []),
            ('navigation', 'apps/reader/navigation', []),
            ('batch', 'apps/reader/batch-import', [])):
        # First variant deliberately does not pass a version: the frozen default is exercised.
        target = build(name + '-' + version, directory, prefix, sdk,
                       version if version == '3.41.0' else None, extra)
        run('cmake', '--install', target)
    consumers = {}
    for name, directory in (('reading', 'reader_reading_state'), ('search', 'reader_search'),
                            ('navigation', 'reader_navigation'), ('batch', 'reader_batch_import')):
        consumers[name] = build('consumer-' + name + '-' + version, 'tests/' + directory + '/consumer',
                                prefix, sdk, version if version == '3.41.0' else None)
    output = BUILD/('results-' + version);output.mkdir()
    run('python3', 'tests/reader_reading_state/make_fixtures.py', output/'reading-fixtures')
    run('python3', 'tests/reader_reading_state/check_reading_state.py', '--probe', consumers['reading']/'reading-state-probe',
        '--c-consumer', consumers['reading']/'reading-state-c-consumer', '--fixtures', output/'reading-fixtures',
        '--font', 'tests/fixtures/fonts/primary.ttf', '--link-map', consumers['reading']/'reading-state-link.map', '--output', output/'reading')
    run('python3', 'tests/reader_search/make_search_fixtures.py', output/'search-fixtures')
    run('python3', 'tests/reader_search/check_search.py', '--probe', consumers['search']/'search-probe',
        '--c-consumer', consumers['search']/'search-c-consumer', '--fixtures', output/'search-fixtures',
        '--font', 'tests/fixtures/fonts/primary.ttf', '--installed', prefix, '--output', output/'search')
    run('python3', 'tests/reader_navigation/make_navigation_fixtures.py', output/'navigation-fixtures')
    run('python3', 'tests/reader_navigation/check_navigation.py', '--probe', consumers['navigation']/'navigation-probe',
        '--c-consumer', consumers['navigation']/'navigation-c-consumer', '--fixtures', output/'navigation-fixtures',
        '--installed', prefix, '--output', output/'navigation')
    run('python3', 'tests/reader_batch_import/make_fixtures.py', '--fixtures', 'tests/fixtures', '--out', output/'batch-fixtures')
    run('python3', 'tests/reader_batch_import/check_batch_import.py', '--probe', consumers['batch']/'batch-probe',
        '--cxx', consumers['batch']/'batch-cpp-consumer', '--fixtures', output/'batch-fixtures', '--staging', output/'staging',
        '--work', output/'batch-work', '--output', output/'batch')
    run('python3', 'tests/reader_batch_import/check_review.py', '--probe', consumers['batch']/'batch-review-probe',
        '--original-probe', consumers['batch']/'batch-probe', '--work', output/'batch-review-work', '--output', output/'batch-review')
    versions[version] = dict(sdk_source=source, reports={}, configs={})
    for name, relative, flag in (('reading', 'reading/summary.json', 'v1_highlight_roundtrip_accepted'),
                                 ('search', 'search/result.json', 'accepted'), ('navigation', 'navigation/result.json', 'accepted'),
                                 ('batch', 'batch/report.json', 'ok'), ('batch-review', 'batch-review/review.json', 'ok')):
        raw = (output/relative).read_bytes();value = json.loads(raw)
        assert value[flag] is True and value.get('source_sha', value.get('source')) == os.environ['GITHUB_SHA']
        versions[version]['reports'][name] = dict(path=str((output/relative).relative_to(BUILD)), sha256=hashlib.sha256(raw).hexdigest())
    for package in ('ReadingState', 'Search', 'Navigation', 'BatchImport'):
        path = prefix/'lib/cmake'/('EXReader' + package)/('EXReader' + package + 'Config.cmake')
        text = path.read_text()
        assert 'find_dependency(EXReader ' + version + ' EXACT CONFIG' in text
        versions[version]['configs'][package] = hashlib.sha256(path.read_bytes()).hexdigest()

# New installed package must refuse the actual old SDK prefix, rather than
# silently linking its imported targets to a different provider.
negative = subprocess.run(['cmake', '-S', 'tests/reader_search/consumer', '-B', str(BUILD/'mixed'), '-G', 'Ninja',
    '-DCMAKE_PREFIX_PATH=' + str(BUILD/'modules-3.41.0') + ';' + str(BUILD/'sdk-3.40.0')],
    capture_output=True, text=True)
(BUILD/'mixed-version.log').write_text(negative.stdout + negative.stderr)
assert negative.returncode != 0 and '3.41.0' in negative.stdout + negative.stderr
negative = subprocess.run(['cmake', '-S', 'apps/reader/search', '-B', str(BUILD/'invalid-version'), '-G', 'Ninja',
    '-DEXR_SDK_VERSION=3.42.0'], capture_output=True, text=True)
(BUILD/'invalid-version.log').write_text(negative.stdout + negative.stderr)
assert negative.returncode != 0 and 'Unsupported exact reader SDK version' in negative.stdout + negative.stderr
result = dict(source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'],
              accepted=True, versions=versions, actual_mixed_sdk_refused=True, unsupported_version_refused=True,
              default_sdk='3.40.0', complete_product=False, host_ui_accepted=False, performance_accepted=False)
(BUILD/'result.json').write_text(json.dumps(result, indent=2)+'\n');print(json.dumps(result), flush=True)
