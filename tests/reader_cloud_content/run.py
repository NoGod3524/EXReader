"""Actions-only ordinary import regression; no path replacement experiment."""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/cloud-pinned-evidence'
SEED = '11042994df180754a11e6d5f828df4277e839c3d'
FROZEN = '9854061be331fe603a1822d9b2b36ee357154927'
SDK = 'edddc463c06ed5731195cdb8f06b2df6dff7699e'
OWN = {'apps/reader/cloud-import/src/cloud_import.c',
       'tests/reader_cloud_pinned/run.py', 'tests/reader_cloud_pinned/strict.py',
       '.github/workflows/reader-cloud-pinned-source.yml',
       'docs/reader-cloud-pinned-source/PLAN.md',
       'apps/reader/cloud-import/include/reader_cloud_import.h',
       'apps/reader/cloud-import/CMakeLists.txt',
       'apps/reader/cloud-import/EXReaderCloudImportConfig.cmake.in',
       'extras/webdav/include/exr_webdav.h', 'extras/webdav/src/webdav.cpp',
       'extras/webdav/CMakeLists.txt', 'extras/webdav/EXReaderWebDAVObservedConfig.cmake.in',
       'tests/reader_cloud_content/run.py', 'tests/reader_cloud_content/strict.py',
       'tests/reader_cloud_content/CMakeLists.txt', 'tests/reader_cloud_content/observer.c',
       '.github/workflows/reader-cloud-content-binding.yml',
       'docs/reader-cloud-content-binding.md'}


def run(args, label):
    args = list(map(str, args))
    print('RUN', label, flush=True)
    p = subprocess.run(args, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       text=True, encoding='utf-8', errors='replace', timeout=3600)
    (OUT / 'logs').mkdir(parents=True, exist_ok=True)
    (OUT / 'logs' / (label + '.log')).write_text(p.stdout, encoding='utf-8')
    print(p.stdout[-6000:], flush=True)
    assert p.returncode == 0, (label, p.returncode)


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def build(source, name, prefix, extra=(), install=True):
    directory = ROOT / 'build/cpb' / name
    run(['cmake', '-S', source, '-B', directory, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
         '-DCMAKE_INSTALL_PREFIX=' + str(prefix), *extra], name + '-configure')
    run(['cmake', '--build', directory, '--parallel', '4'], name + '-build')
    if install:
        run(['cmake', '--install', directory], name + '-install')
    return directory


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
    source = git('rev-parse', 'HEAD')
    assert source == os.environ['GITHUB_SHA']
    OUT.mkdir(parents=True, exist_ok=True)
    version = os.environ['CLOUD_SDK_VERSION']
    assert version in ('3.40.0', '3.41.0')
    run(['git', 'merge-base', '--is-ancestor', SEED, source], 'seed')
    changed = set(git('diff', '--name-only', SEED, source).splitlines())
    assert changed <= OWN, changed - OWN
    run(['git', 'diff', '--exit-code', SEED, source, '--', 'src', 'include', 'cmake',
         'CMakeLists.txt', 'CMakePresets.json', 'bindings', 'tests/fixtures'], 'sdk-protected')
    for name in changed:
        assert git('ls-tree', source, '--', name).startswith('100644 blob '), name
    sdk_source = ROOT / 'build/cpsdk'
    sdk_source.mkdir(parents=True)
    ref = FROZEN if version == '3.40.0' else SDK
    data = subprocess.check_output(['git', 'archive', ref], cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        archive.extractall(sdk_source, filter='data')
    sdk = sdk_source / 'build/reading-library/stage'
    run(['cmake', '--preset', 'reading-library', '-S', sdk_source], 'sdk-configure')
    run(['cmake', '--build', sdk_source / 'build/reading-library', '--parallel', '4'], 'sdk-build')
    run(['cmake', '--install', sdk_source / 'build/reading-library'], 'sdk-install')
    prefix = OUT / 'installed'
    flags = ['-DEXR_SDK=' + str(sdk), '-DCMAKE_PREFIX_PATH=' + str(sdk),
             '-DEXR_SDK_VERSION=' + version]
    build(ROOT / 'extras/sideload', 'sideload', prefix, flags)
    build(ROOT / 'extras/webdav', 'webdav', prefix,
          ['-DEXR_WEBDAV_APPLE_URLSESSION=' + ('ON' if sys.platform == 'darwin' else 'OFF')])
    flags.append('-DCMAKE_PREFIX_PATH=' + ';'.join(map(str, [prefix, sdk])))
    build(ROOT / 'apps/reader/cloud-import', 'cloud', prefix, flags)
    observer_dir = build(ROOT / 'tests/reader_cloud_content', 'observer', prefix,
                         ['-DCMAKE_PREFIX_PATH=' + str(prefix)], False)
    consumer_source = ROOT / 'build/cp-consumer-source'
    shutil.copytree(ROOT / 'tests/reader_webdav_import/consumer', consumer_source)
    cmake = consumer_source / 'CMakeLists.txt'
    text = cmake.read_text(encoding='utf-8')
    old = 'find_package(EXReader 3.40.0 EXACT CONFIG REQUIRED COMPONENTS library)'
    assert text.count(old) == 1
    cmake.write_text(text.replace(old, old.replace('3.40.0', version)), encoding='utf-8')
    review = consumer_source / 'cloud_review_probe.c'
    text = review.read_text(encoding='utf-8')
    old_include = '#include "../../../..//apps/reader/cloud-import/src/cloud_import.c"'
    assert text.count(old_include) == 1
    review.write_text(text.replace(old_include, '#include "' +
        (ROOT / 'apps/reader/cloud-import/src/cloud_import.c').as_posix() + '"'), encoding='utf-8')
    directory = build(consumer_source, 'consumers', prefix, flags, False)
    suffix = '.exe' if os.name == 'nt' else ''
    programs = {}
    binary_dir = OUT / 'programs'
    binary_dir.mkdir()
    for name in ('cloud-probe', 'cloud-cpp-consumer', 'cloud-review-probe'):
        path = binary_dir / (name + suffix)
        shutil.copyfile(directory / path.name, path)
        programs[name] = {'member': 'programs/' + path.name, 'bytes': path.stat().st_size,
                          'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    report_dir = OUT / 'ordinary'
    # Project the unchanged ordinary fixture and its assertions, adding one
    # installed-package observer check against the same normal HTTPS server.
    checker = ROOT / 'build/content-check-cloud.py'
    check_source = (ROOT / 'tests/reader_webdav_import/check_cloud_import.py').read_text(encoding='utf-8')
    marker = "        # ---- 1. directory browsing -> selection -> download -> SDK import (nine formats) ----"
    assert check_source.count(marker) == 1
    injected = """        observer_staging = folder / 'observer-staging'
        observer_staging.mkdir()
        subprocess.run([os.environ['CONTENT_OBSERVER'], root, AUTH, str(observer_staging)], check=True, timeout=170)
        assert not list(observer_staging.glob('.exr-webdav-*'))
        assert not (observer_staging / 'cancel.epub').exists()
        record('observed_bytes_redirect_collision_retry_and_cancellation')
"""
    checker.write_text(check_source.replace(marker, injected + marker), encoding='utf-8')
    os.environ['CONTENT_OBSERVER'] = str(observer_dir / ('content-observer' + suffix))
    run([sys.executable, checker,
         '--probe', directory / ('cloud-probe' + suffix),
         '--cxx', directory / ('cloud-cpp-consumer' + suffix),
         '--review-probe', directory / ('cloud-review-probe' + suffix),
         '--fixtures', ROOT / 'tests/fixtures', '--module-prefix', prefix,
         '--output', report_dir], 'ordinary-full-regression')
    report = json.loads((report_dir / 'result.json').read_text(encoding='utf-8'))
    assert report['accepted'] is True and report['count'] == len(report['checks'])
    # Temporary fixture signing keys are not evidence and never leave the runner.
    for path in OUT.rglob('*.key'):
        path.unlink()
    files = {path.relative_to(OUT).as_posix(): {'bytes': path.stat().st_size,
              'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
             for path in sorted(OUT.rglob('*')) if path.is_file()}
    result = {'source_sha': source, 'run_id': os.environ['GITHUB_RUN_ID'],
              'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'platform': os.environ['RUNNER_OS'],
              'sdk_version': version, 'sdk_source': ref, 'ordinary_regression_accepted': True,
              'path_replacement_experiment_executed': False, 'd13_accepted': False,
              'scope': 'download content digest binding and ordinary cloud-import regressions',
              'cleanup_requires_private_stable_directory': True, 'programs': programs, 'files': files}
    (OUT / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
