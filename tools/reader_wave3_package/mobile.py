#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only mobile deployment adapter over the unchanged platform builders."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
FEATURES = ('Search', 'Navigation', 'Reading', 'Preferences')
MODULES = ('reading-state', 'reading-commands', 'annotation-view', 'search', 'navigation', 'preferences')


def actions_only():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('Mobile builds and deployment run in GitHub Actions only')


def android_properties(sdk, product):
    """The four existing native features share one installed product prefix."""
    return ['-PexrSdk=' + str(sdk), '-PexrProduct=' + str(product),
            *['-Pexr' + feature + '=true' for feature in FEATURES],
            *['-Pexr' + feature + 'Prefix=' + str(product)
              for feature in ('Search', 'Navigation', 'Preferences')]]


def install_android_features(sdk, product, build):
    sys.path.insert(0, str(ROOT / 'tools'))
    from build_android_host import MIN_SDK, ndk_home
    version_header = (sdk / 'include/exr/base.h').read_text(encoding='utf-8')
    if '#define EXR_VERSION "3.41.0"' not in version_header:
        raise SystemExit('Delivery features require the unchanged installed SDK 3.41.0')
    common = ['-G', 'Ninja', '-DCMAKE_TOOLCHAIN_FILE=' + str(ndk_home() / 'build/cmake/android.toolchain.cmake'),
              '-DANDROID_ABI=x86_64', '-DANDROID_PLATFORM=android-' + str(MIN_SDK),
              '-DANDROID_STL=c++_static', '-DCMAKE_BUILD_TYPE=Release',
              '-DCMAKE_POSITION_INDEPENDENT_CODE=ON', '-DCMAKE_FIND_ROOT_PATH_MODE_PACKAGE=BOTH',
              '-DCMAKE_INSTALL_PREFIX=' + str(product), '-DCMAKE_PREFIX_PATH=' + str(product) + ';' + str(sdk),
              '-DEXR_SDK=' + str(sdk), '-DEXR_SDK_VERSION=3.41.0', '-DREADER_PRODUCT_PREFIX=' + str(product),
              '-DEXR_READER_SELECTOR_BYTES_CANDIDATE=OFF']
    for name in MODULES:
        destination = build / name
        subprocess.run(['cmake', '-S', str(ROOT / 'apps/reader' / name), '-B', str(destination), *common], check=True)
        subprocess.run(['cmake', '--build', str(destination), '--parallel', '4', '--target', 'install'], check=True)


def gradle_android(sdk, product, build, gradle, arguments):
    # The original builder invokes Gradle only after installing SDK and product.
    # Its --version call must remain a normal Gradle version query.
    if '-p' in arguments:
        install_android_features(sdk, product, build / 'features')
        arguments = [*arguments, *android_properties(sdk, product)]
        profile = {'schema': 1, 'kind': 'android-native-delivery-profile',
                   'features': {name.lower(): True for name in FEATURES},
                   'sdk_version': '3.41.0', 'sdk_prefix': str(sdk), 'product_prefix': str(product),
                   'installed_modules': list(MODULES), 'gradle_properties': android_properties(sdk, product),
                   'source_sha': os.environ.get('GITHUB_SHA', ''),
                   'run_id': os.environ.get('GITHUB_RUN_ID', ''),
                   'attempt': os.environ.get('GITHUB_RUN_ATTEMPT', ''),
                   'physical_device_execution': False}
        (build / 'mobile-profile.json').write_text(json.dumps(profile, indent=2) + '\n', encoding='utf-8')
    return subprocess.run([gradle, *arguments], check=False).returncode


def build_android(arguments):
    parser = argparse.ArgumentParser(description='Build the unchanged Android host with its explicit delivery profile')
    parser.add_argument('--stage', type=Path, default=ROOT / 'stage/android-x86_64')
    parser.add_argument('--sdk-build', type=Path, default=ROOT / 'build/android-sdk')
    parser.add_argument('--build-dir', type=Path, default=ROOT / 'build/android-host')
    parser.add_argument('--gradle', default=shutil.which('gradle') or 'gradle')
    args = parser.parse_args(arguments)
    if sys.platform != 'linux':
        parser.error('Android delivery builds require the Linux Actions runner')
    sdk, build = args.stage.resolve(), args.build_dir.resolve()
    product = ROOT / 'stage/android-product'
    if (build / 'build.json').exists() or (build / 'mobile-profile.json').exists():
        parser.error('Preserve earlier build evidence: choose a fresh output directory')
    gradle = shutil.which(args.gradle)
    if not gradle:
        parser.error('Gradle executable not found: ' + args.gradle)
    build.mkdir(parents=True, exist_ok=True)
    wrapper = build / 'delivery-gradle'
    wrapper.write_text('#!' + sys.executable + '\nimport subprocess, sys\n'
                       'raise SystemExit(subprocess.run(' + repr([
                           sys.executable, str(Path(__file__).resolve()), 'gradle-android',
                           str(sdk), str(product), str(build), gradle])
                       + ' + sys.argv[1:]).returncode)\n', encoding='utf-8')
    wrapper.chmod(0o755)
    return subprocess.run([sys.executable, str(ROOT / 'tools/build_android_host.py'),
                           '--stage', str(sdk), '--sdk-build', str(args.sdk_build.resolve()),
                           '--build-dir', str(build), '--gradle', str(wrapper)], check=False).returncode


def install_apple(app, udid, output):
    """Install and launch the exact unpacked simulator .app; record the real PID."""
    if sys.platform != 'darwin':
        raise SystemExit('Apple simulator deployment requires the macOS Actions runner')
    if output.exists():
        raise SystemExit('Choose a new deployment report to preserve earlier results')
    app = app.resolve()
    info = app / 'Info.plist'
    def value(key):
        return subprocess.check_output(['plutil', '-extract', key, 'raw', '-o', '-', str(info)], text=True).strip()
    bundle_id, executable = value('CFBundleIdentifier'), value('CFBundleExecutable')
    if bundle_id != 'org.exreader.host' or not (app / executable).is_file():
        raise SystemExit('Unpacked Apple delivery is not the expected EXReader native app')
    subprocess.run(['xcrun', 'simctl', 'bootstatus', udid, '-b'], check=True)
    subprocess.run(['xcrun', 'simctl', 'install', udid, str(app)], check=True)
    installed = Path(subprocess.check_output(['xcrun', 'simctl', 'get_app_container', udid, bundle_id, 'app'], text=True).strip())
    executable_sha = hashlib.sha256((app / executable).read_bytes()).hexdigest()
    installed_sha = hashlib.sha256((installed / executable).read_bytes()).hexdigest()
    if installed_sha != executable_sha:
        raise SystemExit('Installed Apple program differs from the unpacked delivery')
    process = subprocess.run(['xcrun', 'simctl', 'launch', '--terminate-running-process', udid, bundle_id],
                             text=True, capture_output=True, check=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({'app': str(app), 'bundle_id': bundle_id, 'executable': executable,
                                 'udid': udid, 'launch_exit': process.returncode,
                                 'executable_sha256': executable_sha, 'installed_executable_sha256': installed_sha,
                                 'stdout': process.stdout, 'stderr': process.stderr,
                                 'source_sha': os.environ.get('GITHUB_SHA', ''),
                                 'run_id': os.environ.get('GITHUB_RUN_ID', ''),
                                 'attempt': os.environ.get('GITHUB_RUN_ATTEMPT', ''),
                                 'physical_device_execution': False}, indent=2) + '\n', encoding='utf-8')
    return process.returncode


def main(arguments=None):
    actions_only()
    arguments = list(sys.argv[1:] if arguments is None else arguments)
    if arguments and arguments[0] == 'build-android':
        return build_android(arguments[1:])
    if arguments and arguments[0] == 'gradle-android':
        if len(arguments) < 6:
            raise SystemExit('gradle-android SDK PRODUCT BUILD GRADLE [Gradle arguments]')
        return gradle_android(Path(arguments[1]), Path(arguments[2]), Path(arguments[3]), arguments[4], arguments[5:])
    if arguments and arguments[0] == 'install-apple':
        parser = argparse.ArgumentParser()
        parser.add_argument('--app', type=Path, required=True)
        parser.add_argument('--udid', required=True)
        parser.add_argument('--output', type=Path, required=True)
        args = parser.parse_args(arguments[1:])
        return install_apple(args.app, args.udid, args.output)
    raise SystemExit('Expected build-android or install-apple')


if __name__ == '__main__':
    raise SystemExit(main())

