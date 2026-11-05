"""Actions-only producer: SDK 3.42 Android host whose Sync links the installed OPDS hash owner."""
import json, os, shutil, subprocess, sys
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/installed-sync'
VERSION = '3.42.0'

def run(argv, **kw):
    print('$ ' + ' '.join(map(str, argv)), flush=True)
    subprocess.run(list(map(str, argv)), cwd=ROOT, check=True, **kw)

def refresh_env():
    for line in Path(os.environ['GITHUB_ENV']).read_text().splitlines():
        key, sep, value = line.partition('=')
        if sep: os.environ[key] = value

def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    assert not OUT.exists(), 'fresh output required'
    OUT.mkdir(parents=True)
    hash_prefix = (OUT / 'hash-stage').resolve()
    ndk = Path(os.environ['ANDROID_HOME']) / 'ndk' / os.environ['C11_NDK']
    build = OUT / 'hash-build'
    run(['cmake', '-S', 'extras/opds', '-B', build, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
         '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON', '-DCMAKE_POSITION_INDEPENDENT_CODE=ON',
         '-DCMAKE_TOOLCHAIN_FILE=' + str(ndk / 'build/cmake/android.toolchain.cmake'),
         '-DANDROID_ABI=x86_64', '-DANDROID_PLATFORM=android-26', '-DANDROID_STL=c++_static',
         '-DEXREADER_OPDS_HASH_ONLY=ON', '-DCMAKE_INSTALL_PREFIX=' + str(hash_prefix)])
    run(['cmake', '--build', build, '--parallel', '4'])
    run(['cmake', '--install', build])
    os.environ['EXREADER_ORIGINAL_HASH_PREFIX'] = str(hash_prefix)
    with Path(os.environ['GITHUB_ENV']).open('a') as f: f.write('EXREADER_ORIGINAL_HASH_PREFIX=' + str(hash_prefix) + '\n')
    recipe = ROOT / '.github/workflows/android-composition-candidate.yml'
    steps = yaml.safe_load(recipe.read_text())['jobs']['android']['steps']
    names = ['Prepare existing C11 candidate test sources', 'Build and install the frozen 3.41 SDK for x86_64',
             'Install the raw0.2 product and reviewed wave3 packages into one prefix',
             'Author the deterministic fixtures and the bundled font',
             'Build the real wave3 host with search directory reading settings and sync']
    for index, name in enumerate(names):
        matches = [s for s in steps if s.get('name') == name]
        assert len(matches) == 1, name
        body = matches[0]['run']
        if index == 2:
            assert body.count('-DEXR_SDK_VERSION=3.41.0') == 1
            body = body.replace('-DEXR_SDK_VERSION=3.41.0', '-DEXR_SDK_VERSION=' + VERSION)
        if index == 4:
            assert body.count('-PexrSdk=') == 3 and '-PexrSdkVersion=' not in body
            body = body.replace('-PexrSdk=', '-PexrSdkVersion=' + VERSION + ' -PexrSdk=')
        script = OUT / ('step-%d.sh' % index)
        script.write_text(body)
        run(['bash', '-e', '-o', 'pipefail', script])
        refresh_env()
    assert '#define EXR_VERSION "' + VERSION + '"' in (ROOT / 'build/wave3/sdk-stage/include/exr/base.h').read_text()
    run([sys.executable, 'tests/reader_android_installed_sync_handoff/prepare.py'])
    ws = ROOT / 'build/wave3'; stage = ws / 'stage'
    run([sys.executable, 'tests/reader_reading_state/make_fixtures.py', ws / 'sync-reading-fixtures'])
    gradle = ['gradle', '-p', 'examples/android', '--no-daemon', '--stacktrace',
              '-I', str(ROOT / 'tests/reader_android_installed_sync_handoff/init.gradle'),
              '-PexrSdkVersion=' + VERSION, '-PexrSdk=' + str(ws / 'sdk-stage'), '-PexrProduct=' + str(stage),
              '-PexrSync=true', '-PexrSearch=true', '-PexrNavigation=true', '-PexrReading=true', '-PexrPreferences=true',
              '-PexrSelectorBytes=true', '-PexrWave3=true', '-PexrWave3Prefix=' + str(stage), '-PexrSearchPrefix=' + str(stage),
              '-PexrNavigationPrefix=' + str(stage), '-PexrPreferencesPrefix=' + str(stage), '-PexrDav=' + str(stage),
              '-PexrSideload=' + str(stage), '-PexrTestRunner=org.exreader.host.HostSync342Test', ':app:assembleDebugAndroidTest']
    with (ws / 'logs/sync-342-runner-gradle.log').open('w') as log:
        subprocess.run(gradle, cwd=ROOT, check=True, stdout=log, stderr=subprocess.STDOUT)
    shutil.copyfile(ROOT / 'examples/android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk',
                    ws / 'artifacts/sync-342-debug-androidTest.apk')
    (OUT / 'build.json').write_text(json.dumps(dict(source_sha=os.environ['GITHUB_SHA'], hash_prefix=str(hash_prefix),
        sdk_version=VERSION, recipe=recipe.relative_to(ROOT).as_posix(), run_id=os.environ['GITHUB_RUN_ID'],
        attempt=os.environ['GITHUB_RUN_ATTEMPT']), indent=2) + '\n')

if __name__ == '__main__': main()
