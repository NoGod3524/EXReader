#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Package the current Android arm64 debug host in Actions; no device acceptance."""
import argparse
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

from build_android_host import (ANDROID, ROOT, android_home, build_product, build_sdk,
                               header_version, inspect_apk, ndk_home, ndk_revision,
                               patch_android_libraries, run, sha256)
from host_font import fetch as host_font


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', required=True, type=Path)
    parser.add_argument('--sdk-build', required=True, type=Path)
    parser.add_argument('--product-stage', required=True, type=Path)
    parser.add_argument('--build-dir', required=True, type=Path)
    parser.add_argument('--gradle', default='gradle')
    args = parser.parse_args()
    if platform.system() != 'Linux' or os.environ.get('GITHUB_ACTIONS') != 'true':
        parser.error('This build-only package requires a Linux GitHub Actions runner')
    source = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    if source != os.environ.get('GITHUB_SHA'):
        parser.error('Checked-out source must match GITHUB_SHA')
    stage, product, build = args.stage.resolve(), args.product_stage.resolve(), args.build_dir.resolve()
    if (build / 'build.json').exists():
        parser.error('Choose a new output directory to preserve earlier evidence')
    build.mkdir(parents=True, exist_ok=True)
    abi = 'arm64-v8a'
    build_sdk(stage, args.sdk_build.resolve(), abi)
    build_product(product, build / 'product', abi)
    patch_android_libraries(stage, abi)
    assets = ANDROID / 'app/src/main/assets'
    assets.mkdir(parents=True, exist_ok=True)
    run([sys.executable, ROOT / 'tools/reader_catalog_assets.py', '--output', assets / 'reader-catalog-v1.json'])
    font = host_font(ROOT / 'build/host-font-cache')
    for name in ('Reader.otf', 'OFL.txt'):
        shutil.copyfile(font / name, assets / name)
    # Install the actual enabled SDK's notices and the user instructions inside the APK.
    shutil.copytree(stage / 'share/exreader/licenses', assets / 'licenses', dirs_exist_ok=True)
    for origin in (ROOT / 'LICENSE', ROOT / 'THIRD_PARTY_NOTICES.md',
                   ROOT / 'docs/READER-INSTALL-UPGRADE-IMPORT-SYNC.md'):
        shutil.copyfile(origin, assets / origin.name)
    sdk_home = android_home()
    (ANDROID / 'local.properties').write_text('sdk.dir=' + str(sdk_home) + '\n', encoding='utf-8')
    version = header_version(stage / 'include/exr/base.h', 'EXR_VERSION')
    run([args.gradle, '-p', ANDROID, '--no-daemon', '--stacktrace', ':app:assembleDebug',
         '-PexrAbi=' + abi, '-PexrSdk=' + str(stage), '-PexrProduct=' + str(product),
         '-PexrSdkVersion=' + version])
    artifacts = build / 'artifacts'
    artifacts.mkdir(exist_ok=True)
    apk = artifacts / 'app-debug.apk'
    shutil.copyfile(ANDROID / 'app/build/outputs/apk/debug/app-debug.apk', apk)
    native = inspect_apk(apk, abi)
    with zipfile.ZipFile(apk) as archive, tempfile.TemporaryDirectory(prefix='arm64-apk-') as temporary:
        for name, entry in native.items():
            data = archive.read(name)
            library = Path(temporary) / Path(name).name
            library.write_bytes(data)
            notes = subprocess.check_output(['readelf', '-n', library], text=True)
            build_ids = re.findall(r'Build ID: ([0-9a-f]+)', notes)
            if len(set(build_ids)) != 1:
                raise SystemExit('Missing or ambiguous ELF build ID: ' + name)
            entry.update(sha256=sha256(library), build_id=build_ids[0])
    tools = sdk_home / 'build-tools/35.0.0'
    signature = subprocess.check_output([tools / 'apksigner', 'verify', '--verbose', '--print-certs', apk], text=True)
    (artifacts / 'signature.txt').write_text(signature, encoding='utf-8')
    badging = subprocess.check_output([tools / 'aapt', 'dump', 'badging', apk], text=True)
    (artifacts / 'badging.txt').write_text(badging, encoding='utf-8')
    for origin in (ROOT / 'LICENSE', ROOT / 'THIRD_PARTY_NOTICES.md',
                   ROOT / 'docs/READER-INSTALL-UPGRADE-IMPORT-SYNC.md'):
        shutil.copyfile(origin, artifacts / origin.name)
    identity = {
        'source': source, 'run': os.environ['GITHUB_RUN_ID'],
        'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'target': 'android-arm64-v8a',
        'tier': 'debug-apk-build-only', 'sdk_version': version,
        'android_platform': 'android-26', 'ndk': ndk_revision(ndk_home()),
        'host_deployed': False, 'physical_device_verified': False,
        'features': 'base reference host; optional sync/reading/wave3 integration disabled',
        'apk': {'path': 'artifacts/app-debug.apk', 'bytes': apk.stat().st_size, 'sha256': sha256(apk)},
        'native': native,
        'files': {str(p.relative_to(artifacts)): sha256(p) for p in sorted(artifacts.rglob('*')) if p.is_file()},
    }
    (build / 'build.json').write_text(json.dumps(identity, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: identity[key] for key in ('source', 'tier', 'apk', 'host_deployed', 'physical_device_verified')}, indent=2))


if __name__ == '__main__':
    main()
