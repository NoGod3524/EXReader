#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build an arm64 development host from this Actions job's installed SDK.

This is an APK build check, not device installation or a final-feature acceptance.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import zipfile

from build_android_host import (ANDROID, ROOT, build_product, inspect_apk,
                                patch_android_libraries, run, sha256)
from host_font import fetch
from sdk_version import installed_version, source_version


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    sdk = args.sdk.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    version = installed_version(sdk)
    if version != source_version():
        raise SystemExit('The installed SDK does not match the checked-out source version')
    product = output / 'product-stage'
    build_product(product, output / 'product-build', 'arm64-v8a')
    patch_android_libraries(sdk, 'arm64-v8a')
    assets = ANDROID / 'app/src/main/assets'
    assets.mkdir(parents=True, exist_ok=True)
    run(['python3', ROOT / 'tools/reader_catalog_assets.py',
         '--output', assets / 'reader-catalog-v1.json'])
    font = fetch(output / 'font')
    for name in ('Reader.otf', 'OFL.txt'):
        shutil.copyfile(font / name, assets / name)
    run(['gradle', '-p', ANDROID, '--no-daemon', '--stacktrace', ':app:assembleDebug',
         '-PexrAbi=arm64-v8a', '-PexrSdk=' + str(sdk),
         '-PexrSdkVersion=' + version, '-PexrProduct=' + str(product)])
    apk = output / 'host-debug-arm64-v8a.apk'
    shutil.copyfile(ANDROID / 'app/build/outputs/apk/debug/app-debug.apk', apk)
    native = inspect_apk(apk, 'arm64-v8a')
    with zipfile.ZipFile(apk) as archive:
        abis = sorted({name.split('/')[1] for name in archive.namelist() if name.startswith('lib/')})
    if abis != ['arm64-v8a']:
        raise SystemExit('Unexpected APK native ABI set: ' + repr(abis))
    manifest = {
        'source': os.environ['GITHUB_SHA'], 'run': os.environ['GITHUB_RUN_ID'],
        'target': 'android-arm64-v8a', 'tier': 'host-apk-build-only',
        'host_deployed': False, 'physical_device_verified': False,
        'sdk_version': version, 'variant': 'debug', 'abis': abis,
        'features': 'base host; optional sync/reading/wave3 integrations disabled',
        'apk': apk.name, 'apk_size': apk.stat().st_size, 'apk_sha256': sha256(apk),
        'native': native,
    }
    (output / 'host-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(manifest, indent=2), flush=True)


if __name__ == '__main__':
    main()
