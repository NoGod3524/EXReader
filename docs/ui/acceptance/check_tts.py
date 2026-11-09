#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Real SAPI + production Windows host acceptance (no simulated speech).
Usage: python -X utf8 docs/ui/acceptance/check_tts.py EXE FONT OUTPUT
Only the no-voice case uses explicit fault injection. Window captures are taken
through the existing PrintWindow runner; the desktop is never activated.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

from PIL import Image, ImageChops
from check_selection import launch_capture, shot, read

ROOT = Path(__file__).resolve().parents[3]


def main():
    exe, font, out = [Path(x).resolve() for x in sys.argv[1:]]
    out.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='work-', dir=out))
    profile = work / 'profile'
    books = {b['id']: b for b in read(ROOT / 'tools/regress/corpus.json')['books']}
    english = books['a-raisin-in-the-sun']
    hong = books['hongloumeng-24264']
    setup = ('open|A Raisin in the Sun\nwait_idle\nshell|on\nshell_dpi|96\n'
             'shell_client|900|600\nshell_font|28\nwait_idle\nshell_click|light\n'
             'shell_click|toc\nprobe_wait|250\ntoc_click|6\nwait_idle\nprobe_wait|250\n')
    folder = work / 'controls'
    script = f'import|{english["path"]}\nimport|{hong["path"]}\n' + setup + 'tts_open\n'
    for i in range(4):
        script += f'tts_rate|{i}\ntts_dump|rate-{i}\n'
    script += 'tts_rate|1\n'
    for i in range(3):
        script += f'tts_voice|{i % 2}\nannotgoto|6|0\nwait_idle\ntts_start\nprobe_wait|1400\ntts_dump|start-{i}\n'
        # Pause takes effect at SAPI's next word boundary (including the long
        # "Introduction" heading), so sample native position after settling.
        script += f'tts_pause\nprobe_wait|2000\ntts_dump|pause-{i}\nprobe_wait|1000\ntts_dump|still-paused-{i}\n'
        script += f'tts_resume\nprobe_wait|1400\ntts_dump|resume-{i}\ntts_stop\nprobe_wait|200\ntts_dump|stop-{i}\n'
    script += 'tts_open\n' + shot('controls') + 'tts_close\nquit\n'
    launch_capture(exe, font, script, profile, folder, ('controls',))
    rates = [read(folder / f'rate-{i}.tts.json')['rate'] for i in range(4)]
    assert rates == [-2, 0, 2, 4], rates
    rounds = []
    for i in range(3):
        states = {name: read(folder / f'{name}-{i}.tts.json') for name in ('start', 'pause', 'still-paused', 'resume', 'stop')}
        assert [states[n]['state'] for n in ('start', 'pause', 'resume', 'stop')] == [1, 2, 1, 0], states
        assert states['start']['native_state'] == states['resume']['native_state'] == 2
        assert states['pause']['native_offset'] == states['still-paused']['native_offset']
        assert states['resume']['native_offset'] > states['still-paused']['native_offset']
        assert states['stop']['native_state'] == 1 and states['stop']['stream'] == 0
        rounds.append(states)

    folder = work / 'follow'
    script = setup + 'tts_voice|0\ntts_rate|1\ntts_close\n' + shot('follow-before')
    script += 'tts_start\ntts_dump|follow-start\nprobe_wait|30000\ntts_pause\nprobe_wait|250\nwait_idle\ntts_dump|follow-after\n'
    script += shot('follow-after') + 'tts_stop\n' + shot('highlight-cleared')
    script += 'tts_rate|3\ntts_start\nprobe_wait|45000\ntts_dump|continued-chunks\ntts_stop\ntts_rate|1\n'
    script += 'tts_start\nprobe_wait|1000\ntts_dump|minimize-before\ntts_minimize\nprobe_wait|3000\ntts_dump|minimized\n'
    script += 'tts_restore\nwait_idle\nprobe_wait|500\ntts_dump|restored\ntts_stop\n'
    script += 'tts_start\nprobe_wait|700\nshelf_return\nwait_idle\nprobe_wait|200\ntts_dump|left-book\nshelf_dump|speech-shelf\n'
    script += 'shelf_open|0\nwait_idle\ntts_start\nprobe_wait|700\nopen|紅樓夢\nwait_idle\ntts_dump|switched-book\nquit\n'
    launch_capture(exe, font, script, profile, folder, ('follow-before', 'follow-after', 'highlight-cleared'))
    follow = {name: read(folder / f'{name}.tts.json') for name in ('follow-start', 'follow-after', 'continued-chunks', 'minimize-before', 'minimized', 'restored', 'left-book', 'switched-book')}
    before, after = follow['follow-start'], follow['follow-after']
    elapsed = (after['uptime_ms'] - before['uptime_ms']) / 1000
    assert 30 <= elapsed < 35, elapsed
    assert after['jumps'] > 0 and after['page'] > before['page']
    assert after['frame'][0] == after['position'][0] and after['frame'][1] <= after['position'][1] < after['frame'][2]
    assert after['sentence']['visible'] and after['events'] > before['events']
    assert follow['continued-chunks']['state'] == 1 and follow['continued-chunks']['chunks'] >= 2
    assert follow['minimized']['state'] == 1 and follow['minimized']['minimized']
    assert follow['minimized']['events'] > follow['minimize-before']['events']
    assert follow['minimized']['position'] > follow['minimize-before']['position']
    assert follow['restored']['state'] == 1 and not follow['restored']['minimized']
    for key in ('left-book', 'switched-book'):
        assert follow[key]['state'] == 0 and follow[key]['native_state'] == 1 and follow[key]['sentence'] is None
    assert read(folder / 'speech-shelf.state.json')['shelf'] == 1
    # The paused frame and stopped frame are identical except for the temporary
    # sentence background. The pixel diff independently proves visible painting.
    highlighted = Image.open(folder / 'follow-after.png').convert('RGB')
    cleared = Image.open(folder / 'highlight-cleared.png').convert('RGB')
    changed = sum(ImageChops.difference(highlighted, cleared).convert('L').histogram()[1:])
    assert changed > 100, changed

    unavailable = work / 'no-voices'
    os.environ['EXREADER_TTS_NO_VOICES'] = '1'
    try:
        launch_capture(exe, font, setup + 'tts_no_voices\ntts_dump|unavailable\nquit\n', profile, unavailable, ())
    finally:
        os.environ.pop('EXREADER_TTS_NO_VOICES', None)
    missing = read(unavailable / 'unavailable.tts.json')
    assert missing['state'] == 0 and '没有可用的系统语音' in missing['message']
    for name in ('follow-before', 'follow-after', 'highlight-cleared'):
        shutil.copyfile(folder / f'{name}.png', out / f'{name}.png')
    shutil.copyfile(work / 'controls/controls.png', out / 'controls.png')
    for name in ('controls', 'follow', 'no-voices'):
        shutil.copyfile(work / name / 'drive.log', out / f'{name}.txt')
    result = dict(exe_sha256=hashlib.sha256(exe.read_bytes()).hexdigest(), voices=rounds[0]['start']['voices'],
                  set_rate=rates, controls={'start': 3, 'pause': 3, 'resume': 3, 'stop': 3}, rounds=rounds,
                  follow_seconds=elapsed, follow=follow, highlight_changed_pixels=changed, no_voices=missing)
    (out / 'host.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k not in ('rounds', 'follow')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
