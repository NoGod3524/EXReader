"""Actions-only source, archive, relocated entry and same-run F06 authentication."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/f06'
BASE = 'aefe6107f8f073847f0ed590f0ad9602fa720f3d'
TARGETS = ('windows', 'linux', 'macos', 'android', 'iphone', 'ipad')
sys.path.insert(0, str(ROOT / 'tools/reader_wave3_package'))
import delivery

def run(*args):
    return subprocess.check_output([str(a) for a in args], cwd=ROOT, text=True, stderr=subprocess.STDOUT)

def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n', encoding='utf-8')

def common():
    return dict(source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'])

def guard():
    assert run('git', 'rev-parse', 'HEAD').strip() == os.environ['GITHUB_SHA']
    run('git', 'merge-base', '--is-ancestor', BASE, 'HEAD')
    changed = run('git', 'diff', '--name-only', BASE, 'HEAD').splitlines()
    assert all(p.startswith('tests/reader_f06_packages/') or p == '.github/workflows/reader-f06-packages.yml' for p in changed), changed
    data = dict(common(), base_sha=BASE, changed_paths=changed,
                sdk_tree=run('git', 'rev-parse', 'HEAD:src').strip(), include_tree=run('git', 'rev-parse', 'HEAD:include').strip(),
                product_tree=run('git', 'rev-parse', 'HEAD:apps').strip(), examples_tree=run('git', 'rev-parse', 'HEAD:examples').strip(),
                passed=True)
    save(OUT / 'source.json', data)
    return data

def package(target, payload):
    payload = Path(payload)
    destination = OUT / target
    if target == 'linux':
        print(run(sys.executable, 'tools/reader_wave3_package/desktop.py', 'prepare', '--target', target, '--root', payload))
    args = [sys.executable, 'tools/reader_wave3_package/assemble.py', '--target', target, '--payload', payload,
            '--output', destination, '--source-sha', os.environ['GITHUB_SHA'], '--require-build-identity']
    for exclude in ('EXReader-Windows.zip', 'EXReader-Linux.tar.gz'):
        args += ['--exclude', exclude]
    print(run(*args))
    archive = next(destination.glob('EXReader-*.zip'))
    fresh = OUT / ('unpacked-' + target)
    print(run(sys.executable, 'tools/reader_wave3_package/unpack.py', '--target', target, '--archive', archive,
              '--manifest', destination / 'manifest.json', '--into', fresh, '--report', destination / 'unpack.json'))
    if target in ('windows', 'linux', 'macos'):
        print(run(sys.executable, 'tools/reader_wave3_package/desktop.py', 'verify', '--target', target, '--root', fresh,
                  '--source-sha', os.environ['GITHUB_SHA'], '--report', destination / 'entry.json'))
    configs = {}
    for cache in (ROOT / 'build').rglob('CMakeCache.txt'):
        # Preserve actual build configuration, not just intended options.
        content = cache.read_text(encoding='utf-8', errors='replace')
        configs[cache.relative_to(ROOT).as_posix()] = dict(sha256=hashlib.sha256(cache.read_bytes()).hexdigest(),
            entries=[l for l in content.splitlines() if l and not l.startswith(('#', '//'))])
    save(destination / 'configuration.json', dict(common(), target=target, cmake=configs,
        producer=json.loads((payload / 'build.json').read_text()), build_recipe_sha256=delivery.sha256_file(ROOT / 'tests/reader_f06_packages/build.py')))
    if target in ('windows', 'linux', 'macos'): finish(target)

def finish(target):
    destination = OUT / target
    entry = OUT / ('unpacked-' + target) / delivery.TARGETS[target]['entry']
    record = json.loads((destination / 'entry.json').read_text())
    if target in ('windows', 'linux', 'macos'): assert record.get('passed') is True
    elif target == 'android': assert record['installed_apk_sha256'] == delivery.sha256_file(entry) and record['launch_passed'] is True
    else: assert record['launch_exit'] == 0 and record['installed_executable_sha256'] == delivery.sha256_file(entry)
    save(destination / 'result.json', dict(common(), target=target, passed=True,
        program_sha256=delivery.sha256_file(entry), archive=json.loads((destination / 'manifest.json').read_text())['archive'],
        checked='actual archive extraction and relocated dependency entry' if target in ('windows','linux','macos') else 'actual emulator install, installed-byte identity and launch',
        full_behavioral_regression=False, physical_device=False, formal_release=False,
        missing_conditions=delivery.TARGETS[target]['limits'], configuration_sha256=delivery.sha256_file(destination / 'configuration.json'),
        entry_report_sha256=delivery.sha256_file(destination / 'entry.json')))

def install_android():
    target = 'android'
    apk = OUT / 'unpacked-android/artifacts/app-debug.apk'
    log = run('adb', 'install', '-r', apk)
    assert 'Success' in log, log
    installed = run('adb', 'shell', 'pm', 'path', 'org.exreader.host').strip()
    assert installed.startswith('package:') and '\n' not in installed, installed
    pulled = OUT / 'installed-android.apk'
    run('adb', 'pull', installed[len('package:'):], pulled)
    assert delivery.sha256_file(apk) == delivery.sha256_file(pulled)
    component = run('adb', 'shell', 'cmd', 'package', 'resolve-activity', '--brief', 'org.exreader.host').strip().splitlines()[-1]
    assert component.startswith('org.exreader.host/'), component
    launch = run('adb', 'shell', 'am', 'start', '-W', '-n', component)
    assert 'Status: ok' in launch, launch
    time.sleep(3)
    pid = run('adb', 'shell', 'pidof', 'org.exreader.host').strip()
    assert pid, 'app exited after launch'
    save(OUT / target / 'entry.json', dict(common(), launch_passed=True, install_log=log, launch_log=launch,
        pid=pid, component=component, installed_path=installed, installed_apk_sha256=delivery.sha256_file(pulled),
        api=run('adb', 'shell', 'getprop', 'ro.build.version.sdk').strip(), abi=run('adb', 'shell', 'getprop', 'ro.product.cpu.abi').strip()))
    finish(target)

def install_apple(target):
    inventory = json.loads(run('xcrun', 'simctl', 'list', 'devices', 'available', '--json'))
    family = 'iPhone' if target == 'iphone' else 'iPad'
    devices = [d for values in inventory['devices'].values() for d in values if d['name'].startswith(family)]
    assert devices, family + ' simulator unavailable'
    device = devices[0]
    if device['state'] != 'Booted': run('xcrun', 'simctl', 'boot', device['udid'])
    try:
        print(run(sys.executable, 'tools/reader_wave3_package/mobile.py', 'install-apple', '--app', OUT / ('unpacked-' + target) / 'EXReader.app',
                  '--udid', device['udid'], '--output', OUT / target / 'entry.json'))
        finish(target)
    finally:
        run('xcrun', 'simctl', 'shutdown', device['udid'])

def api(path):
    request = urllib.request.Request('https://api.github.com/repos/' + os.environ['GITHUB_REPOSITORY'] + '/' + path,
        headers={'Authorization':'Bearer ' + os.environ['GH_TOKEN'], 'Accept':'application/vnd.github+json'})
    return json.load(urllib.request.urlopen(request))

def summary():
    report = dict(common(), accepted=False, targets={}, failures=[])
    output = OUT / 'summary.json'
    try:
        workflow = api('actions/runs/' + os.environ['GITHUB_RUN_ID'])
        assert workflow['head_sha'] == os.environ['GITHUB_SHA']
        records = api('actions/runs/' + os.environ['GITHUB_RUN_ID'] + '/artifacts?per_page=100')['artifacts']
        for target in TARGETS:
            name = 'f06-' + target + '-' + os.environ['GITHUB_RUN_ID'] + '-' + os.environ['GITHUB_RUN_ATTEMPT']
            matches = [a for a in records if a['name'] == name and not a['expired']]
            assert len(matches) == 1, 'missing/duplicate artifact ' + name
            artifact = matches[0]
            assert artifact['workflow_run']['head_sha'] == os.environ['GITHUB_SHA']
            folder = ROOT / 'f06-input' / name
            result = json.loads((folder / 'result.json').read_text())
            for key, value in common().items(): assert result[key] == value, (target, key)
            assert result['passed'] is True and result['target'] == target
            manifest = json.loads((folder / 'manifest.json').read_text())
            assert manifest['source_sha'] == os.environ['GITHUB_SHA']
            assert manifest['provenance']['run_id'] == os.environ['GITHUB_RUN_ID']
            assert manifest['provenance']['attempt'] == os.environ['GITHUB_RUN_ATTEMPT']
            archive = folder / manifest['archive']['name']
            assert delivery.sha256_file(archive) == result['archive']['sha256'] == manifest['archive']['sha256']
            with zipfile.ZipFile(archive) as z:
                assert hashlib.sha256(z.read(delivery.TARGETS[target]['entry'])).hexdigest() == result['program_sha256']
            assert delivery.sha256_file(folder / 'configuration.json') == result['configuration_sha256']
            assert delivery.sha256_file(folder / 'entry.json') == result['entry_report_sha256']
            report['targets'][target] = dict(result=result, github_artifact_id=artifact['id'],
                github_artifact_digest=artifact.get('digest'), artifact_url='https://github.com/' + os.environ['GITHUB_REPOSITORY'] + '/actions/runs/' + os.environ['GITHUB_RUN_ID'] + '/artifacts/' + str(artifact['id']))
        report['accepted'] = True
    except Exception as error:
        report['failures'].append(str(error))
        raise
    finally:
        save(output, report)
        print(json.dumps(report, indent=2))

if __name__ == '__main__':
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'GitHub Actions only'
    operation = sys.argv[1]
    if operation == 'guard': guard()
    elif operation == 'package': package(sys.argv[2], sys.argv[3])
    elif operation == 'android': install_android()
    elif operation == 'apple': install_apple(sys.argv[2])
    elif operation == 'summary': summary()
    else: raise ValueError(operation)
