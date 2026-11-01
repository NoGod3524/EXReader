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
SERVICE = 'com.google.android.marvin.talkback.TalkBackService'
moves = []


def adb(*args, check=False):
    return subprocess.run(['adb', *args], check=check, capture_output=True, text=True, encoding='utf-8',
                          errors='replace').stdout


def spoken():
    return [line.split('SPEAK ', 1)[1].strip() for line in adb('logcat', '-d', '-s', 'F09TTS:I').splitlines()
            if 'SPEAK ' in line]


def chord(*keys):
    adb('shell', 'input', 'keycombination', *keys)
    time.sleep(0.9)


def seek(fragment, since, limit=40, exclude=None):
    """Move with TalkBack's next-item command until a phrase spoken after
    index `since` contains `fragment` (and not `exclude`)."""
    def heard():
        return next((s for s in spoken()[since:] if fragment in s and not (exclude and exclude in s)), None)
    for _ in range(limit):
        phrase = heard()
        if phrase:
            return phrase
        before = len(spoken())
        chord('KEYCODE_ALT_LEFT', 'KEYCODE_DPAD_RIGHT')
        moves.append('key')
        if len(spoken()) == before:
            # TalkBack's own touch gesture: a quick swipe right is "next item".
            adb('shell', 'input', 'swipe', '250', '1300', '850', '1300', '120')
            time.sleep(0.9)
            moves.append('swipe')
    return heard()


def main(tts_apk, talkback_apk):
    result = {'source_sha': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID'),
              'attempt': os.environ.get('GITHUB_RUN_ATTEMPT'), 'screen_reader': 'TalkBack (emulator)',
              'human_listening_verified': False}
    try:
        # No API 34 x86_64 image ships TalkBack; the workflow builds Google's
        # open-source TalkBack (pinned commit) and it is installed here.
        if talkback_apk.is_file():
            result['talkback_install'] = adb('install', '-r', '-g', str(talkback_apk)).strip()[-200:]
        package = next((p for p in ('com.android.talkback', 'com.google.android.marvin.talkback')
                        if adb('shell', 'pm', 'list', 'packages', p).strip()), None)
        result['talkback_package'] = package
        if not package:
            raise RuntimeError('TalkBack is not installed')
        result['talkback_version'] = next((line.strip() for line in adb('shell', 'dumpsys', 'package',
            package).splitlines() if 'versionName=' in line), None)
        talkback = package + '/' + SERVICE
        result['talkback_component'] = talkback
        adb('install', '-r', '-t', str(tts_apk), check=True)
        adb('shell', 'settings', 'put', 'secure', 'tts_default_synth', 'org.exreader.f09tts')
        adb('logcat', '-c')
        adb('shell', 'settings', 'put', 'secure', 'enabled_accessibility_services', talkback)
        adb('shell', 'settings', 'put', 'secure', 'accessibility_enabled', '1')
        time.sleep(12)
        # First enable opens TalkBack's own tutorial; leave it with Back.
        for _ in range(3):
            if not any('Welcome to TalkBack' in s for s in spoken()[-4:]):
                break
            adb('shell', 'input', 'keyevent', 'KEYCODE_BACK')
            time.sleep(2)
        adb('shell', 'am', 'force-stop', PKG)
        adb('shell', 'monkey', '-p', PKG, '-c', 'android.intent.category.LAUNCHER', '1')
        time.sleep(8)
        found = {}
        found['speech_captured'] = bool(spoken())
        # The host reopens the last book; go back to the shelf with TalkBack.
        mark = len(spoken())
        if any(s.startswith('Opened ') for s in spoken()[-4:]) or seek('Back to shelf', mark, 12):
            seek('Back to shelf', mark, 12)
            chord('KEYCODE_ALT_LEFT', 'KEYCODE_ENTER')
            time.sleep(5)
        mark = len(spoken())
        result['shelf_mark'] = mark
        adb('shell', 'uiautomator', 'dump', '/sdcard/f09tb.xml')
        (OUT / 'android-talkback-shelf.xml').write_text(adb('exec-out', 'cat', '/sdcard/f09tb.xml'), encoding='utf-8')
        found['shelf_title'] = seek('EXReader shelf', mark)
        found['book_row'] = seek('Sample.epub', mark, exclude='Opened')
        if found['book_row']:
            mark = len(spoken())
            chord('KEYCODE_ALT_LEFT', 'KEYCODE_ENTER')
            time.sleep(8)
            found['reader'] = next((s for s in spoken()[mark:] if s.startswith('Opened Sample')), None) \
                or seek('Back to shelf', mark, 12)
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
        result['moves'] = moves
        adb('shell', 'settings', 'put', 'secure', 'enabled_accessibility_services', '""')
        adb('shell', 'settings', 'put', 'secure', 'accessibility_enabled', '0')
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / 'android-talkback.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n',
                                                   encoding='utf-8')
        print(json.dumps({k: result.get(k) for k in ('accepted', 'checks', 'error', 'talkback_version')},
                         ensure_ascii=False), flush=True)


if __name__ == '__main__':
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'GitHub Actions only'
    main(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
