#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Run the Android TTS probe in both real engine states on an Actions emulator.

Run one expects an installed engine: the probe must speak, report UTF-8 byte
ranges and render a real audio file. Run two removes every TTS engine from the
device first, so the missing-engine path is observed rather than simulated.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

PACKAGE = 'org.exreader.tts.probe'
RUNNER = PACKAGE + '.TtsProbe'
KNOWN_ENGINES = (
    'com.google.android.tts',
    'com.svox.pico',
    'com.github.olga_yakovleva.rhvoice.android',
    'com.reecedunn.espeak',
)


def require_actions():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('This probe runs only on GitHub Actions')


def adb(*arguments, timeout=300, check=True):
    completed = subprocess.run(['adb', *map(str, arguments)], stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, timeout=timeout)
    if check and completed.returncode != 0:
        raise SystemExit('adb %s failed: %s' % (' '.join(map(str, arguments)),
                                                completed.stdout.decode('utf-8', 'replace')))
    return completed.stdout


def product(*patterns, root='.'):
    for pattern in patterns:
        matches = sorted(Path(root).glob(pattern))
        if matches:
            return matches[0]
    raise SystemExit('missing build product: ' + ' | '.join(patterns))


def pull(remote, destination):
    data = adb('exec-out', 'run-as', PACKAGE, 'cat', remote)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    return data


def describe_cases(report, mode):
    """Prints every named case that is not a pass so the log carries the detail."""
    for case in report.get('cases') or []:
        if case.get('result') != 'pass':
            detail = (case.get('detail') or '').replace('\n', ' ')
            print('%s %s %s | %s' % (mode, case.get('result'), case.get('name'), detail[:400]),
                  flush=True)


def instrument(mode, output, source, run_id, attempt):
    output.mkdir(parents=True, exist_ok=True)
    raw = adb('shell', 'am', 'instrument', '-w', '-r',
              '-e', 'mode', mode,
              '-e', 'source_sha', source,
              '-e', 'run_id', run_id,
              '-e', 'attempt', attempt,
              PACKAGE + '.test/' + RUNNER, timeout=900)
    (output / 'instrumentation.txt').write_bytes(raw)
    if b'EXR_TTS_ANDROID_PROBE_RECORDED' not in raw or b'INSTRUMENTATION_CODE: -1' not in raw:
        raise SystemExit('probe %s failed: %s' % (mode, raw.decode('utf-8', 'replace')[-4000:]))
    report = json.loads(pull('files/device-report.json', output / 'device-report.json'))
    audio = output / 'tts-sample.wav'
    if pull_audio(audio):
        digest = hashlib.sha256(audio.read_bytes()).hexdigest()
        recorded = (report.get('audio') or {}).get('sha256')
        if recorded and recorded != digest:
            raise SystemExit('pulled audio digest differs from the on-device report')
        report['audio_pulled_bytes'] = audio.stat().st_size
        report['audio_pulled_sha256'] = digest
    return report


def pull_audio(destination):
    completed = subprocess.run(['adb', 'exec-out', 'run-as', PACKAGE, 'cat', 'files/audio/tts-sample.wav'],
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=300)
    if completed.returncode != 0 or not completed.stdout:
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(completed.stdout)
    return True


def enable_engines():
    for package in KNOWN_ENGINES:
        adb('shell', 'pm', 'install-existing', '--user', '0', package, check=False)
        adb('shell', 'pm', 'enable', '--user', '0', package, check=False)


def download_engine(output):
    """Last resort: install a real, publicly released Android TTS engine."""
    request = urllib.request.Request(
        'https://api.github.com/repos/RHVoice/RHVoice/releases/latest',
        headers={'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(request, timeout=60) as response:
        release = json.load(response)
    assets = [asset for asset in release.get('assets', [])
              if asset['name'].lower().endswith('.apk')]
    if not assets:
        return None
    asset = sorted(assets, key=lambda item: item['size'])[-1]
    target = output / 'engine' / asset['name']
    target.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(asset['browser_download_url'], timeout=180) as response:
        target.write_bytes(response.read())
    adb('install', '-r', str(target), timeout=600, check=False)
    return {'asset': asset['name'], 'bytes': target.stat().st_size,
            'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
            'release': release.get('tag_name')}


def disable_engines(report, extra=()):
    packages = list(dict.fromkeys(list(report.get('engine_packages') or []) + list(KNOWN_ENGINES) + list(extra)))
    for package in packages:
        adb('shell', 'pm', 'uninstall', '--user', '0', package, check=False)
        adb('shell', 'pm', 'disable-user', '--user', '0', package, check=False)
    adb('shell', 'am', 'force-stop', PACKAGE, check=False)
    time.sleep(3)
    return packages


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--workspace', default='.')
    arguments = parser.parse_args()
    require_actions()
    output = Path(arguments.output)
    output.mkdir(parents=True, exist_ok=True)
    logs = output / 'logs'
    logs.mkdir(parents=True, exist_ok=True)
    source = os.environ['GITHUB_SHA']
    run_id = os.environ['GITHUB_RUN_ID']
    attempt = os.environ['GITHUB_RUN_ATTEMPT']

    app_apk = product('tests/reader_tts_android/android/probe/build/outputs/apk/debug/*.apk')
    test_apk = product('tests/reader_tts_android/android/probe/build/outputs/apk/androidTest/debug/*.apk',
                       'tests/reader_tts_android/android/probe/build/outputs/apk/androidTest/*.apk',
                       'tests/reader_tts_android/android/probe/build/outputs/apk/androidTest/**/*.apk')
    adb('install', '-r', '-t', app_apk.resolve(), timeout=600)
    adb('install', '-r', '-t', test_apk.resolve(), timeout=600)
    (logs / 'install.txt').write_text(str(adb('shell', 'pm', 'list', 'packages', PACKAGE)), encoding='utf-8')

    engine_report = instrument('engine', output / 'engine', source, run_id, attempt)
    engine_install = None
    if not engine_report.get('engine_packages'):
        enable_engines()
        engine_report = instrument('engine', output / 'engine', source, run_id, attempt)
    if not engine_report.get('engine_packages'):
        engine_install = download_engine(output)
        if engine_install:
            engine_report = instrument('engine', output / 'engine', source, run_id, attempt)
    if not engine_report.get('engine_packages'):
        raise SystemExit('no real TTS engine could be made available on the image')
    if not engine_report.get('pass'):
        describe_cases(engine_report, 'engine')
        raise SystemExit('engine-present probe failed: ' + json.dumps(engine_report.get('failed_cases')))

    removed = disable_engines(engine_report, [])
    missing_report = instrument('none', output / 'none', source, run_id, attempt)
    if missing_report.get('engine_packages'):
        raise SystemExit('engines still registered after removal: %s' % missing_report['engine_packages'])
    describe_cases(engine_report, 'engine-skipped')
    if not missing_report.get('pass'):
        describe_cases(missing_report, 'none')
        raise SystemExit('missing-engine probe failed: ' + json.dumps(missing_report.get('failed_cases')))

    result = {
        'source_sha': source,
        'run_id': int(run_id),
        'attempt': int(attempt),
        'package': PACKAGE,
        'engine_install': engine_install,
        'removed_packages': removed,
        'engine': engine_report,
        'none': missing_report,
        'api': engine_report.get('api'),
        'abi': engine_report.get('abi'),
        'pass': bool(engine_report.get('pass')) and bool(missing_report.get('pass')),
    }
    (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'engine': engine_report.get('engine_packages'),
                      'cases': engine_report.get('case_count'),
                      'skipped_engine': engine_report.get('skipped_cases'),
                      'skipped_none': missing_report.get('skipped_cases'),
                      'audio': (engine_report.get('audio') or {}).get('bytes')}), flush=True)
    return 0 if result['pass'] else 1


if __name__ == '__main__':
    sys.exit(main())
