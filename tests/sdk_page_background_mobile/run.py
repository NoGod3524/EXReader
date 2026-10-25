"""Actions-only: run the unchanged desktop probe against two installed mobile SDKs."""
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import uuid

FROZEN = '9854061be331fe603a1822d9b2b36ee357154927'
CANDIDATE = 'edddc463c06ed5731195cdb8f06b2df6dff7699e'
ROOT = Path.cwd()
BUILD = ROOT/'build/background-mobile'
EVIDENCE = BUILD/'evidence'


def execute(args, timeout=1200, log=None):
    result = subprocess.run([str(a) for a in args], capture_output=True, timeout=timeout)
    if log:
        (EVIDENCE/(log + '.stdout')).write_bytes(result.stdout)
        (EVIDENCE/(log + '.stderr')).write_bytes(result.stderr)
    if result.returncode:
        print(result.stdout.decode(errors='replace')[-12000:])
        print(result.stderr.decode(errors='replace')[-12000:], file=sys.stderr)
        raise RuntimeError('command failed (%d): %s' % (result.returncode, args[0]))
    return result.stdout


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cross(platform):
    if platform == 'android':
        return ['-DCMAKE_TOOLCHAIN_FILE=' + os.environ['ANDROID_HOME']
                + '/ndk/27.0.12077973/build/cmake/android.toolchain.cmake',
                '-DANDROID_ABI=x86_64', '-DANDROID_PLATFORM=android-26']
    return ['-DCMAKE_SYSTEM_NAME=iOS', '-DCMAKE_OSX_SYSROOT=iphonesimulator',
            '-DCMAKE_OSX_ARCHITECTURES=arm64', '-DCMAKE_OSX_DEPLOYMENT_TARGET=15.0',
            '-DCMAKE_MACOSX_BUNDLE=OFF', '-DCMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED=NO']


def build(platform):
    EVIDENCE.mkdir(parents=True)
    frozen = BUILD/'frozen-source';frozen.mkdir()
    archive = subprocess.Popen(['git', 'archive', FROZEN], stdout=subprocess.PIPE)
    try:
        subprocess.run(['tar', '-x', '-C', str(frozen)], stdin=archive.stdout, check=True)
    finally:
        archive.stdout.close()
    assert archive.wait() == 0
    assets = BUILD/'assets';(assets/'fixtures/fonts').mkdir(parents=True)
    names = ['complex-text.html', 'block-border-double.epub', 'table-border-alpha.epub',
             'table-border-dashed.epub', 'table-border-dotted.epub', 'table-border-rtl.epub',
             'table-border-vertical.epub', 'float-vertical-rl.epub', 'color-fonts.epub', 'fonts/primary.ttf']
    for name in names:
        shutil.copy2(ROOT/'tests/fixtures'/name, assets/'fixtures'/name)
    execute(['python3', 'tests/sdk_page_background/make_fixture.py', assets/'long.epub'], log='fixture')
    for kind, source in [('frozen', frozen), ('candidate', ROOT)]:
        sdk_build = BUILD/(kind + '-sdk');stage = BUILD/(kind + '-stage')
        consumer = BUILD/(kind + '-consumer')
        execute(['cmake', '--preset', 'reading-core', '-S', source, '-B', sdk_build,
                 '-DCMAKE_INSTALL_PREFIX=' + str(stage), *cross(platform)], log=kind + '-configure')
        execute(['cmake', '--build', sdk_build, '--parallel', '4'], log=kind + '-build')
        execute(['cmake', '--install', sdk_build], log=kind + '-install')
        package = stage/'lib/cmake/EXReader'
        assert (package/'EXReaderConfig.cmake').is_file(), 'installed package missing'
        execute(['cmake', '-S', 'tests/sdk_page_background', '-B', consumer, '-G', 'Ninja',
                 '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_PREFIX_PATH=' + str(stage),
                 '-DEXReader_DIR=' + str(package), '-DCMAKE_FIND_ROOT_PATH=' + str(stage),
                 '-DBACKGROUND_BASELINE=' + ('ON' if kind == 'frozen' else 'OFF'), *cross(platform)],
                log=kind + '-consumer-configure')
        execute(['cmake', '--build', consumer, '--parallel', '4'], log=kind + '-consumer-build')
        shutil.copy2(sdk_build/'CMakeCache.txt', EVIDENCE/(kind + '-sdk-cache.txt'))
        shutil.copy2(consumer/'CMakeCache.txt', EVIDENCE/(kind + '-consumer-cache.txt'))
        output = EVIDENCE/'programs'/kind;output.mkdir(parents=True)
        shutil.copy2(consumer/'page-background', output/'page-background')
        if platform != 'android':
            bundle = BUILD/(kind + '.app');bundle.mkdir()
            shutil.copy2(consumer/'page-background', bundle/'BackgroundProbe')
            info = dict(CFBundleIdentifier='org.exreader.background.' + kind,
                        CFBundleExecutable='BackgroundProbe', CFBundleName='BackgroundProbe',
                        CFBundlePackageType='APPL', CFBundleVersion='1', CFBundleShortVersionString='1.0',
                        CFBundleSupportedPlatforms=['iPhoneSimulator'], MinimumOSVersion='15.0',
                        LSRequiresIPhoneOS=True, UIDeviceFamily=[1, 2])
            with (bundle/'Info.plist').open('wb') as out:
                plistlib.dump(info, out)
            execute(['codesign', '--force', '--sign', '-', bundle], log=kind + '-codesign')
            # Authenticate the signed executable actually installed, not its pre-sign copy.
            shutil.copy2(bundle/'BackgroundProbe', output/'page-background')


def android():
    remote = '/data/local/tmp/exr-background-' + os.environ['GITHUB_RUN_ID']
    execute(['adb', 'shell', 'mkdir', '-p', remote])
    execute(['adb', 'push', BUILD/'assets/fixtures', remote + '/fixtures'], log='android-fixtures')
    execute(['adb', 'push', BUILD/'assets/long.epub', remote + '/long.epub'], log='android-epub')
    observations = dict(kind='emulator', api=int(execute(['adb', 'shell', 'getprop', 'ro.build.version.sdk']).strip()),
                        abi=execute(['adb', 'shell', 'getprop', 'ro.product.cpu.abi']).decode().strip(),
                        model=execute(['adb', 'shell', 'getprop', 'ro.product.model']).decode().strip(),
                        real_device=False)
    assert observations['api'] == 34 and observations['abi'] == 'x86_64'
    try:
        for kind in ('frozen', 'candidate'):
            program = EVIDENCE/'programs'/kind/'page-background'
            target = remote + '/' + kind
            execute(['adb', 'push', program, target], log=kind + '-push')
            execute(['adb', 'shell', 'chmod', '700', target])
            remote_hash = execute(['adb', 'shell', 'sha256sum', target]).decode().split()[0]
            assert remote_hash == digest(program)
            output = execute(['adb', 'shell', target, remote + '/fixtures', remote + '/' + kind + '-frames.bin',
                              remote + '/long.epub'], timeout=600, log=kind + '-run')
            (EVIDENCE/(kind + '.json')).write_bytes(output)
            execute(['adb', 'pull', remote + '/' + kind + '-frames.bin', EVIDENCE/(kind + '-frames.bin')],
                    log=kind + '-pixels-pull')
            observations[kind + '_installed_sha256'] = remote_hash
    finally:
        # Only the fresh per-run directory created above is removed, inside the emulator.
        execute(['adb', 'shell', 'rm', '-rf', remote])
    return observations


def ios(platform):
    def sim(*args, **kwargs):
        return execute(['xcrun', 'simctl', *args], **kwargs)
    runtimes = json.loads(sim('list', 'runtimes', 'available', '-j'))['runtimes']
    runtime = max((r for r in runtimes if r.get('platform') == 'iOS'),
                  key=lambda r: tuple(int(x) for x in r['version'].split('.')))
    family = 'iPad' if platform == 'ios-ipad' else 'iPhone'
    device = next(d for d in runtime['supportedDeviceTypes'] if d['productFamily'] == family)
    udid = sim('create', 'exr-background-' + uuid.uuid4().hex[:10], device['identifier'], runtime['identifier']).decode().strip()
    assert udid
    observations = dict(kind='simulator', runtime=runtime['identifier'], version=runtime['version'],
                        family=family, device_type=device['identifier'], abi='arm64', real_device=False)
    try:
        sim('boot', udid)
        sim('bootstatus', udid, '-b', timeout=600, log='ios-boot')
        for kind in ('frozen', 'candidate'):
            bundle_id = 'org.exreader.background.' + kind
            sim('install', udid, BUILD/(kind + '.app'), log=kind + '-install-app')
            data = Path(sim('get_app_container', udid, bundle_id, 'data').decode().strip())/'Documents'
            bundle = Path(sim('get_app_container', udid, bundle_id, 'app').decode().strip())
            shutil.copytree(BUILD/'assets', data, dirs_exist_ok=True)
            installed = digest(bundle/'BackgroundProbe')
            assert installed == digest(EVIDENCE/'programs'/kind/'page-background')
            output = sim('spawn', udid, bundle/'BackgroundProbe', data/'fixtures', data/(kind + '-frames.bin'),
                         data/'long.epub', timeout=600, log=kind + '-run')
            (EVIDENCE/(kind + '.json')).write_bytes(output)
            shutil.copy2(data/(kind + '-frames.bin'), EVIDENCE/(kind + '-frames.bin'))
            observations[kind + '_installed_sha256'] = installed
    finally:
        sim('shutdown', udid)
        sim('delete', udid)
    return observations


def run(platform):
    device = android() if platform == 'android' else ios(platform)
    old = json.loads((EVIDENCE/'frozen.json').read_bytes());new = json.loads((EVIDENCE/'candidate.json').read_bytes())
    assert old['accepted'] is new['accepted'] is True
    assert old['sdk'] == '3.40.0' and new['sdk'] == '3.41.0' and old['abi'] == new['abi'] == 1
    assert old['cases'] == new['cases'] == 12 and new['checks'] >= 535 and old['checks'] >= 164
    before = (EVIDENCE/'frozen-frames.bin').read_bytes();after = (EVIDENCE/'candidate-frames.bin').read_bytes()
    assert before and before == after
    result = dict(source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
                  attempt=os.environ['GITHUB_RUN_ATTEMPT'], platform=platform, accepted=True,
                  sdk_production_source=CANDIDATE, frozen_source=FROZEN, old=old, new=new, device=device,
                  old_api_pixels_identical=True, pixel_sha256=hashlib.sha256(after).hexdigest(),
                  frozen_consumer_sha256=digest(EVIDENCE/'programs/frozen/page-background'),
                  candidate_consumer_sha256=digest(EVIDENCE/'programs/candidate/page-background'),
                  native_suite_executed=False, host_ui_accepted=False, performance_accepted=False,
                  real_device_accepted=False, complete_product=False, six_platform_accepted=False)
    (EVIDENCE/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    operation, platform = sys.argv[1:]
    assert platform in ('android', 'ios-iphone', 'ios-ipad')
    {'build': build, 'run': run}[operation](platform)
