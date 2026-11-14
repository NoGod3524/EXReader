"""Build-only current-source APK; does not run the historical frozen-source acceptance."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import build_android_host as builder
from host_font import fetch


def main():
    stage = ROOT / 'stage/android-x86_64'
    output = ROOT / 'build/android-host'
    output.mkdir(parents=True, exist_ok=True)
    builder.build_sdk(stage, ROOT / 'build/android-sdk')
    builder.build_product(ROOT / 'stage/android-product', output / 'product')
    builder.patch_android_libraries(stage)
    assets = builder.ANDROID / 'app/src/main/assets'
    assets.mkdir(parents=True, exist_ok=True)
    builder.run([sys.executable, ROOT / 'tools/reader_catalog_assets.py',
                 '--output', assets / 'reader-catalog-v1.json'])
    font = fetch(ROOT / 'build/host-font-cache')
    for name in ('Reader.otf', 'OFL.txt'):
        shutil.copyfile(font / name, assets / name)
    version = builder.header_version(stage / 'include/exr/base.h', 'EXR_VERSION')
    builder.run(['gradle', '-p', builder.ANDROID, '--no-daemon', '--stacktrace',
                 ':app:assembleDebug', ':uitest:assembleDebug', ':uitest:assembleDebugAndroidTest',
                 '-PexrSdk=' + str(stage), '-PexrSdkVersion=' + version])
    artifacts = builder.collect_artifacts(output)
    builder.inspect_apk(Path(artifacts['app-debug.apk']['path']))
    report = dict(source_sha=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                  scope='build-only', abi='x86_64', device_tests_run=False,
                  artifacts=artifacts)
    (output / 'build.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
