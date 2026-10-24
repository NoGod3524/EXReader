# SPDX-License-Identifier: MIT
"""Build the installed package for the iOS Simulator and run the probe inside a
real UIKit app, so AVSpeechSynthesizer is driven by an actual app main run loop.
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
    assert (stage / 'include/reader_tts.h').is_file(), 'installed header missing for the simulator'
    assert (stage / 'include/reader_tts.h').read_bytes() == (module_dir / 'include/reader_tts.h').read_bytes()

    run('probe-configure', ['cmake', '-S', root / 'tests/reader_tts_apple', '-B', probe, *simulator,
                            '-DCMAKE_PREFIX_PATH=' + str(stage)])
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
    device_type = next(entry for entry in types if entry['name'].startswith('iPad'))
    udid = text('create', ['xcrun', 'simctl', 'create', 'EXReader-TTS-' + os.environ['GITHUB_RUN_ID'],
                           device_type['identifier'], runtime['identifier']])
    try:
        run('boot', ['xcrun', 'simctl', 'boot', udid])
        run('boot-status', ['xcrun', 'simctl', 'bootstatus', udid, '-b'], timeout=1200)
        run('install', ['xcrun', 'simctl', 'install', udid, app])
        container = Path(text('container', ['xcrun', 'simctl', 'get_app_container', udid, BUNDLE_ID, 'data']))
        documents = container / 'Documents'
        run('launch', ['xcrun', 'simctl', 'launch', udid, BUNDLE_ID])
        deadline = time.monotonic() + 600
        done = documents / 'done.json'
        while not done.is_file():
            assert time.monotonic() < deadline, 'the simulator probe exceeded its deadline'
            time.sleep(0.5)
        exit_code = json.loads(done.read_text(encoding='utf-8'))['exit']
        report_path = documents / 'result.json'
        assert report_path.is_file(), 'the simulator probe wrote no report'
        shutil.copy2(report_path, out / 'speech-result.json')
        wav = documents / 'result.json.wav'
        if wav.is_file():
            shutil.copy2(wav, out / 'speech-result.json.wav')
        probe_report = check_report.load(out / 'speech-result.json')
        assert exit_code == 0, 'the simulator probe reported a failing case (%d)' % exit_code

        merged = {
            'schema': 1,
            'platform': 'ios-simulator',
            'execution_platform': 'ios-simulator',
            'source_sha': os.environ['GITHUB_SHA'],
            'run_id': int(os.environ['GITHUB_RUN_ID']),
            'attempt': int(os.environ['GITHUB_RUN_ATTEMPT']),
            'consumer_sha256': check_report.sha256_file(binary),
            'speech_available': bool(probe_report.get('speech_available')),
            'speech_note': probe_report.get('speech_note', ''),
            'checks': probe_report['checks'],
            'counts': probe_report['counts'],
            'os': probe_report.get('os'),
            'arch': arch,
            'runtime': {'name': runtime['name'], 'identifier': runtime['identifier']},
            'device_type': device_type['name'],
            'probe': {
                'consumer_sha256': check_report.sha256_file(binary),
                'dependencies': [line.strip() for line in dependencies.splitlines()[1:] if line.strip()],
                'state_at_create': probe_report.get('state_at_create'),
                'capabilities': probe_report.get('capabilities'),
                'voice_count': probe_report.get('voice_count'),
                'pcm': probe_report.get('pcm'),
            },
        }
        check_report.verify_identity(merged, 'ios-simulator')
        check_report.verify_checks(merged, 'probe')
        check_report.verify_consumer(merged, binary)
        wav_path = out / 'speech-result.json.wav'
        if merged['probe'].get('pcm') and wav_path.is_file():
            digest = check_report.sha256_file(wav_path)
            assert digest == merged['probe']['pcm']['sha256'], 'PCM digest mismatch in the simulator'
            merged['probe']['pcm']['recomputed_sha256'] = digest
            merged['probe']['pcm']['file_bytes'] = wav_path.stat().st_size
            merged['probe']['pcm']['file'] = wav_path.name
        (out / 'result.json').write_text(json.dumps(merged, indent=2), encoding='utf-8')
        print(json.dumps({'platform': 'ios-simulator', 'counts': merged['counts'],
                          'speech_available': merged['speech_available'],
                          'runtime': merged['runtime']['name']}), flush=True)
    finally:
        subprocess.run(['xcrun', 'simctl', 'shutdown', udid], capture_output=True)
        subprocess.run(['xcrun', 'simctl', 'delete', udid], capture_output=True)


if __name__ == '__main__':
    main()
