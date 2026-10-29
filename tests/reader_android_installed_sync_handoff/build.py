"""Actions-only: build the real SDK 3.42 Android host (Sync with the installed
OPDS hash owner) from the unchanged composition recipe, plus the frozen
HostSync suite admitted for 3.42. Nothing here runs on a developer machine."""
import hashlib, json, os, shutil, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/c1-installed-sync'
WAVE = ROOT / 'build/wave3'
VERSION = '3.42.0'
RECIPE = ROOT / '.github/workflows/android-composition-candidate.yml'
JAVA = ROOT / 'tests/reader_host_session_android/java/org/exreader/host/HostSyncTest.java'
DRIVER = ROOT / 'tests/reader_host_session_android/run_ui.py'


def sh(args):
    print('$', ' '.join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), cwd=ROOT, check=True)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_env():
    for line in Path(os.environ['GITHUB_ENV']).read_text().splitlines():
        key, sep, value = line.partition('=')
        if sep:
            os.environ[key] = value


def hash_stage():
    """Same explicit canonical hash prefix the public-boundary lane gives Sync."""
    ndk = Path(os.environ['ANDROID_HOME']) / 'ndk' / os.environ['C11_NDK']
    stage, build = OUT / 'hash-stage', OUT / 'hash-build'
    assert not stage.exists() and not build.exists()
    sh(['cmake', '-S', ROOT / 'extras/opds', '-B', build, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
        '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON', '-DCMAKE_POSITION_INDEPENDENT_CODE=ON',
        '-DCMAKE_TOOLCHAIN_FILE=' + str(ndk / 'build/cmake/android.toolchain.cmake'),
        '-DANDROID_ABI=x86_64', '-DANDROID_PLATFORM=android-26', '-DANDROID_STL=c++_static',
        '-DEXREADER_OPDS_HASH_ONLY=ON', '-DCMAKE_INSTALL_PREFIX=' + stage.as_posix()])
    sh(['cmake', '--build', build, '--parallel', '4'])
    sh(['cmake', '--install', build])
    assert stage.resolve() == stage and (stage / 'lib/cmake/EXReaderOPDSHash').is_dir()
    with Path(os.environ['GITHUB_ENV']).open('a') as f:
        f.write('EXREADER_ORIGINAL_HASH_PREFIX=' + stage.as_posix() + '\n')
    load_env()


def recipe_steps():
    import yaml
    steps = yaml.safe_load(RECIPE.read_text())['jobs']['android']['steps']
    names = ['Prepare existing C11 candidate test sources', 'Build and install the frozen 3.41 SDK for x86_64',
             'Install the raw0.2 product and reviewed wave3 packages into one prefix',
             'Author the deterministic fixtures and the bundled font',
             'Build the real wave3 host with search directory reading settings and sync']
    bodies = []
    for index, name in enumerate(names):
        found = [s for s in steps if s.get('name') == name]
        assert len(found) == 1, name
        body = found[0]['run']
        if index == 2:
            assert body.count('-DEXR_SDK_VERSION=3.41.0') == 1
            body = body.replace('-DEXR_SDK_VERSION=3.41.0', '-DEXR_SDK_VERSION=' + VERSION)
        if index == 4:
            assert body.count('-PexrSdk=') == 3 and '-PexrSdkVersion=' not in body
            body = body.replace('-PexrSdk=', '-PexrSdkVersion=' + VERSION + ' -PexrSdk=')
        bodies.append(body)
    return names, bodies


def host_sync_342():
    """Frozen HostSyncTest/run_ui.py with only the SDK admission widened to 3.42.0."""
    java, driver = JAVA.read_text(encoding='utf-8'), DRIVER.read_text(encoding='utf-8')
    for old, new in [('public final class HostSyncTest extends Instrumentation',
                      'public final class HostSync342Test extends Instrumentation'),
                     ('need(expectedSdk.equals("3.40.0")||expectedSdk.equals("3.41.0"),"supported expected SDK version")',
                      'need(expectedSdk.equals("3.40.0")||expectedSdk.equals("3.41.0")||expectedSdk.equals("3.42.0"),"supported expected SDK version")')]:
        assert java.count(old) == 1, old
        java = java.replace(old, new)
    root_line = "sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'reader_session_android'))"
    assert driver.count(root_line) == 1
    driver = driver.replace(root_line, "sys.path.insert(0,'" + (ROOT / 'tests/reader_session_android').as_posix() + "')")
    for old, new in [("choices=('3.40.0','3.41.0')", "choices=('3.40.0','3.41.0','3.42.0')"),
                     ("package+'.test/'+package+'.HostSyncTest'", "package+'.test/'+package+'.HostSync342Test'")]:
        assert driver.count(old) == 1, old
        driver = driver.replace(old, new)
    folder = OUT / 'candidate/java/org/exreader/host'
    folder.mkdir(parents=True)
    (folder / 'HostSync342Test.java').write_text(java, encoding='utf-8')
    (OUT / 'candidate/run_ui_342.py').write_text(driver, encoding='utf-8')
    return dict(java_original_sha256=sha(JAVA), driver_original_sha256=sha(DRIVER),
        java_candidate_sha256=sha(folder / 'HostSync342Test.java'),
        driver_candidate_sha256=sha(OUT / 'candidate/run_ui_342.py'),
        changes=['class and runner names', 'absolute sys.path for relocated driver', 'SDK admission list adds 3.42.0 (exact identity assertion unchanged)'])


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == os.environ['GITHUB_SHA']
    OUT.mkdir(parents=True)
    hash_stage()
    names, bodies = recipe_steps()
    for index, body in enumerate(bodies):
        script = OUT / ('recipe-step-%d.sh' % index)
        script.write_text(body)
        sh(['bash', '-e', '-o', 'pipefail', script])
        load_env()
    assert '#define EXR_VERSION "' + VERSION + '"' in (WAVE / 'sdk-stage/include/exr/base.h').read_text()
    apk = WAVE / 'artifacts/app-debug.apk'
    apk_sha = sha(apk)
    provenance = host_sync_342()
    stage = WAVE / 'stage'
    common = ['-PexrSdkVersion=' + VERSION, '-PexrSdk=' + str(WAVE / 'sdk-stage'), '-PexrProduct=' + str(stage),
              '-PexrSync=true', '-PexrSearch=true', '-PexrNavigation=true', '-PexrReading=true',
              '-PexrPreferences=true', '-PexrSelectorBytes=true', '-PexrWave3=true', '-PexrWave3Prefix=' + str(stage),
              '-PexrSearchPrefix=' + str(stage), '-PexrNavigationPrefix=' + str(stage),
              '-PexrPreferencesPrefix=' + str(stage), '-PexrDav=' + str(stage), '-PexrSideload=' + str(stage),
              '-PexrTestRunner=org.exreader.host.HostSync342Test']
    sh(['python3', 'tests/reader_reading_state/make_fixtures.py', WAVE / 'sync-reading-fixtures'])
    sh(['gradle', '-p', 'examples/android', '--no-daemon', '--stacktrace', '-I',
        ROOT / 'tests/reader_android_installed_sync_handoff/init.gradle', *common, ':app:assembleDebugAndroidTest'])
    runner = WAVE / 'artifacts/host-sync-342-androidTest.apk'
    shutil.copyfile(ROOT / 'examples/android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk', runner)
    rebuilt = ROOT / 'examples/android/app/build/outputs/apk/debug/app-debug.apk'
    (OUT / 'build.json').write_text(json.dumps(dict(source_sha=os.environ['GITHUB_SHA'],
        run_id=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'], sdk_version=VERSION,
        recipe=RECIPE.relative_to(ROOT).as_posix(), recipe_sha256=sha(RECIPE), recipe_steps=names,
        hash_prefix=os.environ['EXREADER_ORIGINAL_HASH_PREFIX'], host_apk_sha256=apk_sha,
        host_apk_after_runner_build_sha256=sha(rebuilt), runner_apk_sha256=sha(runner), candidate=provenance),
        indent=2) + '\n')


if __name__ == '__main__':
    main()
