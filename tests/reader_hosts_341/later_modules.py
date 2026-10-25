"""Actions-only dual exact SDK installation for the four later reader packages."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/later-module-sdk'
BASE = '2dae171b75f04484813cd03487bbb9b5aab81c71'
SDKS = {'3.40.0': '9854061be331fe603a1822d9b2b36ee357154927',
        '3.41.0': 'edddc463c06ed5731195cdb8f06b2df6dff7699e'}
PACKAGES = {'cloud-import': 'CloudImport', 'thumbnails': 'Thumbnails',
            'book-information': 'BookInformation', 'local-downloads': 'LocalDownloads'}
ENV = dict(os.environ)


def run(args, label, rejected=False):
    done = subprocess.run(list(map(str, args)), cwd=ROOT, env=ENV, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', timeout=1800)
    (OUT / (label + '.log')).write_text(done.stdout, encoding='utf-8')
    print(label, done.returncode, done.stdout[-5000:], flush=True)
    assert (done.returncode != 0) if rejected else (done.returncode == 0), label
    return done.stdout


def configure(name, source, paths, extra=(), rejected=False):
    return run(['cmake', '-S', source, '-B', OUT / name, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
                '-DCMAKE_PREFIX_PATH=' + ';'.join(map(str, paths)), *extra], name + '-configure', rejected)


def build(name):
    run(['cmake', '--build', OUT / name, '--parallel', '4'], name + '-build')


def main():
    assert ENV.get('GITHUB_ACTIONS') == 'true'
    OUT.mkdir(parents=True, exist_ok=False)
    subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, 'HEAD'], cwd=ROOT, check=True)
    allowed = {'apps/reader/' + name + '/' + file for name, package in PACKAGES.items()
               for file in ('CMakeLists.txt', 'EXReader' + package + 'Config.cmake.in')}
    paths = subprocess.check_output(['git', 'diff', '--name-only', BASE, 'HEAD'], cwd=ROOT, text=True).splitlines()
    assert all(path in allowed or path.startswith('tests/reader_hosts_341/') or path in
               ('.github/workflows/reader-later-module-sdk.yml', 'docs/READER-HOSTS-341-FINAL.md') for path in paths), paths
    subprocess.run(['git', 'diff', '--exit-code', SDKS['3.41.0'], 'HEAD', '--',
                    'src', 'include', 'cmake', 'CMakeLists.txt', 'bindings', 'tests/fixtures'], cwd=ROOT, check=True)
    checks, versions = [], {}
    for version, source in SDKS.items():
        sdk_source = OUT / ('source-' + version)
        sdk_source.mkdir()
        raw = subprocess.check_output(['git', 'archive', source], cwd=ROOT)
        with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
            archive.extractall(sdk_source, filter='data')
        sdk = OUT / ('sdk-' + version)
        prefix = OUT / ('modules-' + version)
        name = 'sdk-build-' + version
        run(['cmake', '--preset', 'reading-library', '-S', sdk_source, '-B', OUT / name,
             '-DCMAKE_INSTALL_PREFIX=' + str(sdk)], name + '-configure')
        build(name)
        run(['cmake', '--install', OUT / name], name + '-install')
        modules = [('product', 'apps/reader/store/native'), ('sideload', 'extras/sideload'), ('webdav', 'extras/webdav')]
        modules += [(module, 'apps/reader/' + module) for module in PACKAGES]
        for module, directory in modules:
            name = module + '-' + version
            extra = ['-DEXR_SDK=' + str(sdk), '-DCMAKE_INSTALL_PREFIX=' + str(prefix)]
            # Actual default 3.40 is exercised without a version override.
            if version != '3.40.0':
                extra.append('-DEXR_SDK_VERSION=' + version)
            configure(name, directory, [prefix, sdk], extra)
            build(name)
            run(['cmake', '--install', OUT / name], name + '-install')
        configs = {}
        for module, package in PACKAGES.items():
            config = prefix / 'lib/cmake' / ('EXReader' + package) / ('EXReader' + package + 'Config.cmake')
            data = config.read_bytes()
            assert ('find_dependency(EXReader ' + version + ' EXACT CONFIG') in data.decode()
            configs[package] = hashlib.sha256(data).hexdigest()
        name = 'consumer-' + version
        configure(name, 'tests/reader_hosts_341/consumer', [prefix, sdk])
        build(name)
        run([OUT / name / ('later-sdk.exe' if os.name == 'nt' else 'later-sdk'), version], name + '-run')
        checks.append('actual-installed-defaults-and-SDK-' + version)
        versions[version] = dict(sdk_source=source, installed_config_sha256=configs)
    for module in PACKAGES:
        for invalid in ('3.42.0', '3x41x0'):
            text = configure(module + '-invalid-' + invalid, 'apps/reader/' + module, [],
                             ['-DEXR_SDK_VERSION=' + invalid], rejected=True)
            assert 'Unsupported exact reader SDK version' in text
            checks.append(module + '-reject-' + invalid)
        text = configure(module + '-wrong-sdk', 'apps/reader/' + module,
                         [OUT / 'modules-3.40.0', OUT / 'sdk-3.40.0'],
                         ['-DEXR_SDK_VERSION=3.41.0', '-DEXR_SDK=' + str(OUT / 'sdk-3.40.0')], rejected=True)
        assert '3.41.0' in text
        checks.append(module + '-reject-old-SDK-for-new-request')
    for version, wrong in (('3.40.0', '3.41.0'), ('3.41.0', '3.40.0')):
        text = configure('mixed-' + version, 'tests/reader_hosts_341/consumer',
                         [OUT / ('modules-' + version), OUT / ('sdk-' + wrong)], rejected=True)
        assert version in text
        checks.append('installed-' + version + '-reject-SDK-' + wrong)
    result = dict(accepted=True, source_sha=ENV['GITHUB_SHA'], run_id=ENV['GITHUB_RUN_ID'],
                  attempt=ENV['GITHUB_RUN_ATTEMPT'], platform=ENV['RUNNER_OS'], checks=checks, versions=versions,
                  complete_product=False, full_composition_accepted=False, host_ui_accepted=False)
    (OUT / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
