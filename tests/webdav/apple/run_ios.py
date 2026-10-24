# SPDX-License-Identifier: MIT
"""Build installed-only native transport and run original suites inside iOS."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    root = Path.cwd(); out = root / 'build/webdav-ios'; logs = out / 'logs'
    logs.mkdir(parents=True)

    def run(name, command, timeout=600):
        result = subprocess.run([str(x) for x in command], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout)
        (logs / (name + '.log')).write_text(result.stdout + result.stderr, encoding='utf-8')
        if result.returncode:
            print((result.stdout + result.stderr)[-12000:], flush=True)
        assert result.returncode == 0, (name, result.returncode)
        return result.stdout.strip()

    stage, module, consumer = out / 'stage', out / 'module-build', out / 'consumer'
    sdk = run('sdk', ['xcrun', '--sdk', 'iphonesimulator', '--show-sdk-path'])
    common = ['-G', 'Ninja', '-DCMAKE_SYSTEM_NAME=iOS', '-DCMAKE_OSX_SYSROOT=iphonesimulator',
              '-DCMAKE_OSX_ARCHITECTURES=arm64', '-DCMAKE_OSX_DEPLOYMENT_TARGET=15.0', '-DCMAKE_BUILD_TYPE=Release',
              '-DCMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED=NO', '-DLIBXML2_INCLUDE_DIR=' + sdk + '/usr/include/libxml2',
              '-DLIBXML2_LIBRARY=' + sdk + '/usr/lib/libxml2.tbd']
    run('module-configure', ['cmake', '-S', 'extras/webdav', '-B', module, *common, '-DCMAKE_INSTALL_PREFIX=' + str(stage)])
    run('module-build', ['cmake', '--build', module, '--verbose'])
    run('module-install', ['cmake', '--install', module])
    run('consumer-configure', ['cmake', '-S', 'tests/webdav/apple', '-B', consumer, *common, '-DCMAKE_PREFIX_PATH=' + str(stage)])
    run('consumer-build', ['cmake', '--build', consumer, '--verbose'])
    app = consumer / 'WebDAVProbe.app'; binary = app / 'WebDAVProbe'
    run('sign', ['codesign', '--force', '--sign', '-', app])
    assert run('architecture', ['lipo', '-archs', binary]) == 'arm64'
    dependencies = run('dependencies', ['otool', '-L', binary])
    assert 'Foundation.framework' in dependencies and not any(x in dependencies.lower() for x in ('libcurl', 'libssl', 'libcrypto', 'webkit', 'webview'))
    runtimes = json.loads(run('runtimes', ['xcrun', 'simctl', 'list', 'runtimes', '--json']))['runtimes']
    runtime = max((r for r in runtimes if r.get('isAvailable') and r['identifier'].startswith('com.apple.CoreSimulator.SimRuntime.iOS-')),
                  key=lambda r: tuple(int(x) for x in r['version'].split('.')))
    types = json.loads(run('device-types', ['xcrun', 'simctl', 'list', 'devicetypes', '--json']))['devicetypes']
    device = next(t for t in types if t['name'].startswith('iPhone 16'))
    udid = run('create', ['xcrun', 'simctl', 'create', 'EXReader-WebDAV-' + os.environ['GITHUB_RUN_ID'], device['identifier'], runtime['identifier']])
    try:
        run('boot', ['xcrun', 'simctl', 'boot', udid])
        run('boot-status', ['xcrun', 'simctl', 'bootstatus', udid, '-b'], timeout=900)
        run('install', ['xcrun', 'simctl', 'install', udid, app])
        container = run('container', ['xcrun', 'simctl', 'get_app_container', udid, 'org.exreader.webdav.probe', 'data'])
        os.environ['EXR_DAV_IOS_UDID'] = udid; os.environ['EXR_DAV_IOS_CONTAINER'] = container
        launch = root / 'tests/webdav/apple/launch.py'; launch.chmod(0o755)
        run('source-suite', [sys.executable, 'tests/webdav/check_tls.py', '--consumer', launch, '--native-binary', binary,
                             '--module-prefix', stage, '--output', out / 'source'], timeout=1200)
        run('compat-suite', [sys.executable, 'tests/webdav/check_compat.py', '--consumer', launch, '--native-binary', binary,
                             '--output', out / 'compat'], timeout=600)
        run('write-suite', [sys.executable, 'tests/webdav/apple/check_transport.py', '--consumer', launch, '--native-binary', binary,
                            '--output', out / 'writes'], timeout=600)
        reports = {name: json.loads((out / name / 'result.json').read_text(encoding='utf-8')) for name in ('source', 'compat', 'writes')}
        for name, count in [('source', 77), ('compat', 12), ('writes', 10)]:
            value = reports[name]
            assert value['accepted'] is True and value['source_sha'] == os.environ['GITHUB_SHA']
            assert value['count'] == count and value['execution_platform'] == 'ios-simulator'
            assert value['consumer_sha256'] == hashlib.sha256(binary.read_bytes()).hexdigest()
        report = {'accepted': True, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
                  'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'execution_platform': 'ios-simulator', 'architecture': 'arm64',
                  'runtime': runtime, 'device_type': device, 'suite_counts': {k: v['count'] for k, v in reports.items()},
                  'consumer_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'host_ui_accepted': False,
                  'full_reader_session_accepted': False, 'physical_device_execution': False, 'complete_product': False}
        (out / 'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report), flush=True)
    finally:
        subprocess.run(['xcrun', 'simctl', 'shutdown', udid], capture_output=True)
        subprocess.run(['xcrun', 'simctl', 'delete', udid], capture_output=True)


if __name__ == '__main__': main()
