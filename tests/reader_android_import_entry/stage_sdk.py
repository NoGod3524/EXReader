#!/usr/bin/env python3
"""Cross-build and install the frozen SDK, the sideload module and the import-entry native component
for Android API 26 / x86_64, Release (consumed by the probe) and Debug (compile proof, separate prefix)."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NDK_VERSION = '27.0.12077973'
PLATFORM = 'android-26'


def run(cmd, log):
    cmd = [str(c) for c in cmd]
    print('+', ' '.join(cmd), flush=True)
    with open(log, 'ab') as out:
        out.write(('+ ' + ' '.join(cmd) + '\n').encode())
        process = subprocess.run(cmd, stdout=out, stderr=subprocess.STDOUT)
    if process.returncode:
        sys.stdout.write(Path(log).read_text(errors='replace')[-6000:])
        raise SystemExit('command failed: ' + ' '.join(cmd))


def toolchain():
    home = os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT')
    ndk = Path(home or '.') / 'ndk' / NDK_VERSION
    if not ndk.is_dir():
        raise SystemExit('Android NDK ' + NDK_VERSION + ' is not installed')
    return ndk / 'build/cmake/android.toolchain.cmake'


def common(config, prefix, search):
    return ['-G', 'Ninja', '-DCMAKE_TOOLCHAIN_FILE=' + str(toolchain()), '-DANDROID_ABI=x86_64',
            '-DANDROID_PLATFORM=' + PLATFORM, '-DANDROID_STL=c++_static', '-DCMAKE_BUILD_TYPE=' + config,
            '-DCMAKE_POSITION_INDEPENDENT_CODE=ON', '-DCMAKE_FIND_ROOT_PATH_MODE_PACKAGE=BOTH',
            '-DCMAKE_INSTALL_PREFIX=' + str(prefix), '-DCMAKE_PREFIX_PATH=' + ';'.join(str(p) for p in search)]


def build(source, build_dir, args, log, target=None):
    run(['cmake', '-S', source, '-B', build_dir, *args], log)
    run(['cmake', '--build', build_dir, '--parallel', '4', '--verbose'] + (['--target', target] if target else []), log)
    run(['cmake', '--install', build_dir], log)


def build_sdk(prefix, work, log):
    flags = ['-DEXR_BUILD_TOOLS=OFF', '-DEXR_BUILD_TESTS=OFF', '-DEXR_BUILD_JNI=OFF', '-DEXR_ENABLE_LIBRARY=ON',
             '-DEXR_ENABLE_AUDIO=ON', '-DEXR_ENABLE_PDF=ON', '-DEXR_ENABLE_PDF_EDIT=ON', '-DEXR_ENABLE_PDF_CRYPTO=OFF',
             '-DEXR_ENABLE_AAC=OFF', '-DEXR_ENABLE_TEXT_INDEX=OFF', '-DEXR_BUILD_TEXT_INDEX=OFF',
             '-DEXR_ENABLE_IMAGE_WEBP=OFF', '-DEXR_ENABLE_IMAGE_TIFF=OFF', '-DEXR_ENABLE_IMAGE_AVIF=OFF',
             '-DEXR_BUILD_SHARED_COMPAT=ON']
    # The SDK build is Release only; it is the frozen dependency, not the unit under test.
    args = ['-G', 'Ninja', '-DCMAKE_TOOLCHAIN_FILE=' + str(toolchain()), '-DANDROID_ABI=x86_64',
            '-DANDROID_PLATFORM=' + PLATFORM, '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_INSTALL_PREFIX=' + str(prefix), *flags]
    build(ROOT, work / 'sdk', args, log, target='install')


def elf(path):
    out = subprocess.check_output(['readelf', '-d', str(path)], text=True)
    soname = [l for l in out.splitlines() if '(SONAME)' in l]
    return soname[0].split('[')[1].rstrip(']') if soname else ''


def patch_engine(prefix, log):
    """Android installs an unversioned runtime; give it one stable SONAME and the aliases CMake exports name."""
    libs = sorted((prefix / 'lib').glob('libexreader.so.*.*'))
    engine = libs[-1] if libs else prefix / 'lib/libexreader.so'
    if not engine.is_file():
        raise SystemExit('installed SDK has no engine runtime')
    if elf(engine) != 'libexreader.so':
        run(['patchelf', '--set-soname', 'libexreader.so', engine], log)
    for name in ('libexreader.so', 'libexreader.so.1', 'libexreader.so.3.40.0'):
        target = prefix / 'lib' / name
        if not target.exists():
            shutil.copyfile(engine, target)
    apk = prefix / 'apk-libs/x86_64'
    apk.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(engine, apk / 'libexreader.so')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prefix', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    prefix, work = args.prefix.absolute(), args.work.absolute()
    work.mkdir(parents=True, exist_ok=True)
    log = work / 'stage.log'
    build_sdk(prefix, work, log)
    patch_engine(prefix, log)
    modules = {}
    for config, target in (('Release', prefix), ('Debug', work / 'debug-prefix')):
        search = [prefix] if config == 'Release' else [target, prefix]
        build(ROOT / 'extras/sideload', work / ('sideload-' + config),
              common(config, target, [prefix]) + ['-DEXR_SDK=' + str(prefix)], log)
        build(ROOT / 'extras/android-import-entry', work / ('entry-' + config),
              common(config, target, search) + ['-DEXR_SDK=' + str(prefix)], log)
        archive = target / 'lib/libexr_android_import_entry.a'
        modules[config] = {'archive_bytes': archive.stat().st_size,
                           'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}
    for required in ('include/exr_android_import_entry.h', 'include/exr_sideload.h',
                     'share/exreader-android-import-entry/sample/host_bridge.c',
                     'share/exreader-android-import-entry/sample/java/org/exreader/importentry/sample/NativeBridge.java',
                     'lib/cmake/EXReaderAndroidImportEntry/EXReaderAndroidImportEntryConfig.cmake'):
        if not (prefix / required).is_file():
            raise SystemExit('installed prefix lacks ' + required)
    (work / 'stage.json').write_text(json.dumps({'prefix': str(prefix), 'modules': modules}, indent=2))


if __name__ == '__main__':
    main()
