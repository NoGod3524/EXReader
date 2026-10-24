# SPDX-License-Identifier: MIT
"""Build the installed package for the iOS Simulator and run the probe inside a
real UIKit app, so AVSpeechSynthesizer is driven by an actual app main run loop.

The same installed binary runs on an iPhone simulator (the report that is
verified case by case) and on an iPad simulator (recorded as a second device
result plus one summary case). Both are registered in the merged report.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_report  # noqa: E402

BUNDLE_ID = 'org.exreader.tts.apple.probe'


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'this driver runs in GitHub Actions only'
    root = Path.cwd()
    out = root / 'build/tts-apple-ios'
    if out.exists():
        shutil.rmtree(out)
    logs = out / 'logs'
    logs.mkdir(parents=True)
    stage, module, probe = out / 'install', out / 'module', out / 'probe'

    def run(name, command, timeout=900, check=True):
        result = subprocess.run([str(x) for x in command], capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=timeout)
        (logs / (name + '.log')).write_text(result.stdout + result.stderr, encoding='utf-8')
        if check and result.returncode:
            print((result.stdout + result.stderr)[-12000:], flush=True)
        assert not check or result.returncode == 0, (name, result.returncode)
        return result

    def text(name, command, timeout=300):
        return run(name, command, timeout=timeout).stdout.strip()

    module_dir = root / 'extras/reader-tts-apple'
    simulator = ['-G', 'Ninja', '-DCMAKE_SYSTEM_NAME=iOS', '-DCMAKE_OSX_SYSROOT=iphonesimulator',
                 '-DCMAKE_OSX_ARCHITECTURES=arm64', '-DCMAKE_OSX_DEPLOYMENT_TARGET=15.0',
                 '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED=NO']

    run('module-configure', ['cmake', '-S', module_dir, '-B', module, *simulator,
                             '-DCMAKE_INSTALL_PREFIX=' + str(stage)])
    run('module-build', ['cmake', '--build', module])
    run('module-install', ['cmake', '--install', module])
    installed_header = stage / 'include/reader_tts.h'
    assert installed_header.is_file(), 'installed header missing for the simulator'
    assert installed_header.read_bytes() == (module_dir / 'include/reader_tts.h').read_bytes(), \
        'simulator install header differs from the source header'

    # Prefix search does not cross the sysroot boundary when targeting iOS, so the
    # installed package directory is passed explicitly (same lesson as the
    # retained reader-webdav-apple failure e39f5f3e).
    run('probe-configure', ['cmake', '-S', root / 'tests/reader_tts_apple', '-B', probe, *simulator,
                            '-DCMAKE_PREFIX_PATH=' + str(stage),
                            '-DEXReaderTTSApple_DIR=' + str(stage / 'lib/cmake/EXReaderTTSApple')])
    run('probe-build', ['cmake', '--build', probe])
    app = probe / 'ReaderTTSProbe.app'
    binary = app / 'ReaderTTSProbe'
    assert binary.is_file(), 'probe app binary missing'
    run('sign', ['codesign', '--force', '--sign', '-', app])
    arch = text('architecture', ['lipo', '-archs', binary])
    assert arch == 'arm64', 'unexpected simulator architecture: %s' % arch
    dependencies = text('dependencies', ['otool', '-L', binary])
    assert 'AVFoundation.framework' in dependencies, 'probe does not link AVFoundation'
    assert 'WebKit' not in dependencies and 'JavaScriptCore' not in dependencies, 'unexpected web dependency'

    runtimes = json.loads(text('runtimes', ['xcrun', 'simctl', 'list', 'runtimes', '--json']))['runtimes']
    runtime = max((entry for entry in runtimes
                   if entry.get('isAvailable') and entry['identifier'].startswith('com.apple.CoreSimulator.SimRuntime.iOS-')),
                  key=lambda entry: tuple(int(part) for part in entry['version'].split('.')))
    types = json.loads(text('device-types', ['xcrun', 'simctl', 'list', 'devicetypes', '--json']))['devicetypes']
    iphone = next((entry for entry in types if entry['name'].startswith('iPhone 16')), None)
    ipad = next((entry for entry in types if entry['name'] == 'iPad (A16)'), None) \
        or next((entry for entry in types if entry['name'].startswith('iPad')), None)
    assert iphone is not None and ipad is not None, 'no iPhone/iPad device type available'

    def run_device(label, device_type):
        udid = text('create-' + label, ['xcrun', 'simctl', 'create',
                                       'EXReader-TTS-%s-%s' % (label, os.environ['GITHUB_RUN_ID']),
                                       device_type['identifier'], runtime['identifier']])
        try:
            run('boot-' + label, ['xcrun', 'simctl', 'boot', udid])
            run('boot-status-' + label, ['xcrun', 'simctl', 'bootstatus', udid, '-b'], timeout=1200)
            run('install-' + label, ['xcrun', 'simctl', 'install', udid, app])
            container = Path(text('container-' + label, ['xcrun', 'simctl', 'get_app_container', udid, BUNDLE_ID, 'data']))
            documents = container / 'Documents'
            run('launch-' + label, ['xcrun', 'simctl', 'launch', udid, BUNDLE_ID])
            deadline = time.monotonic() + 600
            done = documents / 'done.json'
            while not done.is_file():
                assert time.monotonic() < deadline, 'the %s simulator probe exceeded its deadline' % label
                time.sleep(0.5)
            exit_code = json.loads(done.read_text(encoding='utf-8'))['exit']
            report_path = documents / 'result.json'
            assert report_path.is_file(), 'the %s simulator probe wrote no report' % label
            report_copy = out / ('speech-result-%s.json' % label)
            shutil.copy2(report_path, report_copy)
            wav_copy = out / ('speech-result-%s.json.wav' % label)
            if (documents / 'result.json.wav').is_file():
                shutil.copy2(documents / 'result.json.wav', wav_copy)
            report = check_report.load(report_copy)
            for case in report['checks']:
                if case['status'] != 'pass':
                    print('%s %s: %s' % (case['status'], case['name'], case['detail']), flush=True)
            assert exit_code == 0, 'the %s simulator probe reported a failing case (%d)' % (label, exit_code)
            return report, report_copy, wav_copy
        finally:
            subprocess.run(['xcrun', 'simctl', 'shutdown', udid], capture_output=True)
            subprocess.run(['xcrun', 'simctl', 'delete', udid], capture_output=True)

    phone_report, phone_path, phone_wav = run_device('iphone', iphone)
    pad_report, pad_path, pad_wav = run_device('ipad', ipad)

    merged = {
        'schema': 1,
        'platform': 'ios-simulator',
        'execution_platform': 'ios-simulator',
        'source_sha': os.environ['GITHUB_SHA'],
        'run_id': int(os.environ['GITHUB_RUN_ID']),
        'attempt': int(os.environ['GITHUB_RUN_ATTEMPT']),
        'consumer_sha256': check_report.sha256_file(binary),
        'speech_available': bool(phone_report.get('speech_available')),
        'speech_note': phone_report.get('speech_note', ''),
        'checks': list(phone_report['checks']),
        'counts': dict(phone_report['counts']),
        'os': phone_report.get('os'),
        'arch': arch,
        'runtime': {'name': runtime['name'], 'identifier': runtime['identifier']},
        'device_type': iphone['name'],
        'probe': {
            'consumer_sha256': check_report.sha256_file(binary),
            'dependencies': [line.strip() for line in dependencies.splitlines()[1:] if line.strip()],
            'state_at_create': phone_report.get('state_at_create'),
            'capabilities': phone_report.get('capabilities'),
            'voice_count': phone_report.get('voice_count'),
            'pcm': phone_report.get('pcm'),
        },
        'ipad': {
            'device_type': ipad['name'],
            'counts': pad_report['counts'],
            'speech_available': pad_report.get('speech_available'),
            'speech_note': pad_report.get('speech_note'),
            'voice_count': pad_report.get('voice_count'),
            'pcm': pad_report.get('pcm'),
            'checks': pad_report['checks'],
        },
    }
    # The iPad run is summarised as one named case: it must run and must not fail.
    if pad_report['counts']['fail'] == 0:
        merged['checks'].append({'name': 'probe.ipad-simulator-run', 'status': 'pass',
                                 'detail': '%s, pass %d pending %d' % (ipad['name'], pad_report['counts']['pass'],
                                                                       pad_report['counts']['pending'])})
    else:
        merged['checks'].append({'name': 'probe.ipad-simulator-run', 'status': 'fail',
                                 'detail': 'iPad counts %s' % (pad_report['counts'],)})
    counts = {'pass': 0, 'fail': 0, 'pending': 0}
    for check in merged['checks']:
        counts[check['status']] += 1
    merged['counts'] = counts

    check_report.verify_identity(merged, 'ios-simulator')
    check_report.verify_checks(merged, 'probe')
    check_report.verify_consumer(merged, binary)
    if merged['probe'].get('pcm') and phone_wav.is_file():
        digest = check_report.sha256_file(phone_wav)
        assert digest == merged['probe']['pcm']['sha256'], 'PCM digest mismatch in the iPhone simulator'
        merged['probe']['pcm']['recomputed_sha256'] = digest
        merged['probe']['pcm']['file_bytes'] = phone_wav.stat().st_size
        merged['probe']['pcm']['file'] = phone_wav.name
    (out / 'result.json').write_text(json.dumps(merged, indent=2), encoding='utf-8')
    print(json.dumps({'platform': 'ios-simulator', 'counts': merged['counts'],
                      'iphone': iphone['name'], 'ipad': ipad['name'],
                      'ipad_counts': pad_report['counts'],
                      'speech_available': merged['speech_available'],
                      'runtime': runtime['name']}), flush=True)


if __name__ == '__main__':
    main()
