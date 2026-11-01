"""F09 Android screen reader: what TalkBack actually speaks on the product host.

Semantic-tree results say what an assistive client can query; they are not a
screen-reader result. This lane enables the emulator's own TalkBack, routes its
speech to tests/f09_audit/android_tts (a TTS engine that logs every utterance),
moves only with TalkBack's keyboard commands (Alt+Right next, Alt+Enter
activate) and reads the words TalkBack spoke. Human listening is a separate
record this lane does not claim. Actions only.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/f09'
PKG = 'org.exreader.host'
TALKBACK = 'com.google.android.marvin.talkback/com.google.android.marvin.talkback.TalkBackService'


def adb(*args, check=False):
    return subprocess.run(['adb', *args], check=check, capture_output=True, text=True, encoding='utf-8',
                          errors='replace').stdout


def spoken():
    return [line.split('SPEAK ', 1)[1].strip() for line in adb('logcat', '-d', '-s', 'F09TTS:I').splitlines()
            if 'SPEAK ' in line]


def chord(*keys):
    adb('shell', 'input', 'keycombination', *keys)
    time.sleep(0.9)


def seek(fragment, limit=40):
    for _ in range(limit):
        if any(fragment in s for s in spoken()[-3:]):
            return True
        chord('KEYCODE_ALT_LEFT', 'KEYCODE_DPAD_RIGHT')
    return any(fragment in s for s in spoken()[-3:])


def main(tts_apk):
    result = {'source_sha': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID'),
              'attempt': os.environ.get('GITHUB_RUN_ATTEMPT'), 'screen_reader': 'TalkBack (emulator)',
              'human_listening_verified': False}
    try:
        installed = adb('shell', 'pm', 'list', 'packages', 'com.google.android.marvin.talkback').strip()
        result['talkback_package'] = installed
        result['talkback_version'] = next((line.strip() for line in adb('shell', 'dumpsys', 'package',
            'com.google.android.marvin.talkback').splitlines() if 'versionName=' in line), None)
        if not installed:
            raise RuntimeError('TalkBack is not installed on this system image')
        adb('install', '-r', '-t', str(tts_apk), check=True)
        adb('shell', 'settings', 'put', 'secure', 'tts_default_synth', 'org.exreader.f09tts')
        adb('logcat', '-c')
        adb('shell', 'settings', 'put', 'secure', 'enabled_accessibility_services', TALKBACK)
        adb('shell', 'settings', 'put', 'secure', 'accessibility_enabled', '1')
        time.sleep(12)
        adb('shell', 'am', 'force-stop', PKG)
        adb('shell', 'monkey', '-p', PKG, '-c', 'android.intent.category.LAUNCHER', '1')
        time.sleep(8)
        found = {}
        found['speech_captured'] = bool(spoken())
        found['shelf_title'] = seek('shelf')
        found['book_row'] = seek('Sample')
        if found['book_row']:
            chord('KEYCODE_ALT_LEFT', 'KEYCODE_ENTER')
            time.sleep(8)
        found['reader'] = seek('Back to shelf') or seek('Select') or seek('page')
        result['found'] = found
        result['checks'] = [{'id': cid, 'status': 'pass' if found.get(key) else 'fail', 'expected': want}
                            for cid, key, want in (
                                ('T-01', 'speech_captured', 'TalkBack speaks through the capture engine'),
                                ('T-02', 'shelf_title', 'the shelf is announced'),
                                ('T-03', 'book_row', 'the imported book row is spoken with its title'),
                                ('T-04', 'reader', 'activating the row opens the reader, whose controls are spoken'))]
        result['accepted'] = all(c['status'] == 'pass' for c in result['checks'])
    except Exception as error:
        result['error'] = str(error)
        result['accepted'] = False
    finally:
        result['spoken'] = spoken()
        adb('shell', 'settings', 'put', 'secure', 'enabled_accessibility_services', '""')
        adb('shell', 'settings', 'put', 'secure', 'accessibility_enabled', '0')
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / 'android-talkback.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n',
                                                   encoding='utf-8')
        print(json.dumps({k: result.get(k) for k in ('accepted', 'checks', 'error', 'talkback_version')},
                         ensure_ascii=False), flush=True)


if __name__ == '__main__':
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'GitHub Actions only'
    main(Path(sys.argv[1]).resolve())
