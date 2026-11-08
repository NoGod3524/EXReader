#!/usr/bin/env python3
"""Real Windows host selection acceptance; captures ONLY via ops/capture_window.py.

Usage: check_selection.py EXE FONT OUTPUT
Temporary book text and full telemetry stay under OUTPUT/work; result.json and
the selected UTF-8 slices are the reviewable evidence.
"""
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import zipfile

from check_step5 import run, dump, HIDDEN
from check_toc_panel import open_book

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'ops'))
from capture_window import capture


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def ptr(event, offset, trailing=0):
    return f'select_pointer|{event}|{offset}|{trailing}\n'


def copied(name):
    return f'select_key|C|0|1\nselect_dump|{name}\n'


def point(meta, offset):
    return next(g for g in meta['glyphs'] if g[8] <= offset < g[9] and not g[7] & (4 | 2048))


def check(folder, name, expected, start=None, end=None):
    selected = (folder / (name + '.utf8')).read_bytes()
    clipboard = (folder / (name + '.clipboard.utf8')).read_bytes()
    state = read(folder / (name + '.selection.json'))
    assert selected == clipboard == expected, (name, state, selected[:100], expected[:100])
    assert state['anchor_roundtrip'] == 1, (name, state)
    if start is not None:
        assert state['start'][1] == start and state['end'][1] == end, (name, state, start, end)
    return dict(bytes=len(selected), sha256=sha(selected), start=state['start'], end=state['end'],
                byte_equal=True, clipboard_equal=True, anchor_roundtrip=True,
                text=selected.decode('utf-8') if len(selected) < 400 else None)


def launch_capture(exe, font, script, profile, folder, shots):
    folder.mkdir(parents=True, exist_ok=True); profile.mkdir(parents=True, exist_ok=True)
    drive = folder / 'run.drive'; drive.write_text(script, encoding='utf-8')
    command = [str(exe), '--offscreen', '--drive', str(drive), '--evidence', str(folder),
               '--data', str(profile), '--library', str(profile / 'library.sqlite'), '--font', str(font), '--phase', '1']
    process = subprocess.Popen(command, env=dict(os.environ, EXREADER_HOST_ACCEPTANCE='1'), creationflags=HIDDEN)
    pending = set(shots); start = time.monotonic(); captures = {}
    while process.poll() is None:
        for name in list(pending):
            if (folder / (name + '.json')).exists():
                captures[name] = capture(process.pid, folder / (name + '.png')); pending.remove(name)
        if time.monotonic() - start > 180:
            process.kill(); raise RuntimeError('selection acceptance timed out')
        time.sleep(.02)
    assert process.returncode == 0 and not pending, (process.returncode, pending, (folder / 'drive.log').read_text(encoding='utf-8'))
    dump(folder / 'captures.json', captures)


def shot(name):
    return f'shell_measure|{name}\nprobe_wait|1200\n'


def fixture_book(path):
    paragraphs = [
        'Alpha bravo reader selection English. A café combines its accent; co-operate keeps its punctuation.',
        'Second paragraph contains portable text and deterministic boundaries.',
        'Third paragraph keeps every original logical character.',
        'Fourth paragraph demonstrates selection across wrapped lines.',
        'Fifth paragraph completes the original host acceptance sample.']
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('mimetype', 'application/epub+zip')
        archive.writestr('META-INF/container.xml', '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
        archive.writestr('book.opf', '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">selection-original</dc:identifier><dc:title>Selection Original</dc:title><dc:language>en</dc:language></metadata><manifest><item id="body" href="body.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="body"/></spine></package>')
        archive.writestr('body.xhtml', '<html xmlns="http://www.w3.org/1999/xhtml" lang="en"><head><title>Selection</title></head><body>' + ''.join('<p>' + p + '</p>' for p in paragraphs) + '</body></html>')
    return paragraphs


def main():
    exe, font, output = (Path(x).resolve() for x in sys.argv[1:])
    work = output / 'work'; work.mkdir(parents=True, exist_ok=True)
    corpus = {b['id']: Path(b['path']) for b in read(ROOT / 'tools/regress/corpus.json')['books']}
    hong = corpus['hongloumeng-24264']; vertical = corpus['kusamakura-japanese-vertical-writing']
    result = dict(exe_sha256=sha(exe.read_bytes()), capture_script='ops/capture_window.py',
                  sources={p.name: sha(p.read_bytes()) for p in (hong, vertical)})
    opening = open_book(hong, '紅樓夢') + 'shell_click|toc\nprobe_wait|230\ntoc_click|1\nwait_idle\nprobe_wait|230\n'
    discover = opening
    for page in range(1, 12):
        discover += f'shell_page|{page}\nwait_idle\nshell_measure|page{page}\n'
    discover += 'select_key|A|0|1\n' + copied('source') + 'quit\n'
    run(exe, font, discover, work / 'hong-discover-profile', work / 'hong-discover')
    pages = {p: read(work / f'hong-discover/page{p}.json') for p in range(1, 12)}
    source = (work / 'hong-discover/source.part.utf8').read_bytes()
    first, second = pages[10], pages[11]
    assert first['part'] == second['part'] and first['index'] == 9 and second['index'] == 10
    assert first['range'][1] == second['range'][0]
    phrase = '三劫后，我在北邙山等你，會齊了同往太虛幻境銷號。'.encode()
    a = source.index(phrase); b = a + len(phrase)
    script = opening + 'shell_page|10\nwait_idle\n' + shot('plain')
    script += ptr('down', a) + ptr('move', b - 3, 1) + ptr('up', b - 3, 1) + copied('sentence') + shot('sentence-light')
    script += 'shell_click|dark\n' + shot('sentence-dark') + 'shell_click|light\n'
    # Five CJK one-character drags. Every event is dispatched through page_procedure.
    cjk = []; pos = a
    for i, char in enumerate('三劫后我在'):
        pos = source.index(char.encode(), pos)
        name = f'cjk-{i}'; script += 'select_key|escape\n'
        script += ptr('down', pos) + ptr('move', pos, 1) + ptr('up', pos, 1) + copied(name)
        cjk.append((name, char.encode(), pos, pos+3)); pos += 3
    # Five actual double-clicks and five distinct paragraph triple-clicks.
    doubles = []
    for i, (_, expected, lo, hi) in enumerate(cjk):
        name = f'double-{i}'; script += ptr('double', lo) + ptr('up', lo) + copied(name)
        doubles.append((name, expected, lo, hi))
    triples = []; used = set()
    for page, meta in pages.items():
        if len(triples) == 5: break
        for glyph in meta['glyphs']:
            lo = glyph[8]
            if glyph[7] & (4 | 2048) or glyph[2] < 0x4e00: continue
            start = source.rfind(b'\n', 0, lo)+1; end = source.find(b'\n', lo)
            if end < 0: end = len(source)
            if start in used: continue
            used.add(start); name = f'triple-{len(triples)}'
            script += f'shell_page|{page}\nwait_idle\n' + ptr('double', lo) + ptr('up', lo) + ptr('down', lo) + ptr('up', lo) + copied(name)
            triples.append((name, source[start:end], start, end)); break
    assert len(triples) == 5
    # Drag from page 10 to page 11 through the production edge-turn timer.
    boundary = first['range'][1]
    left = first['glyphs'][-15][8]; right = second['glyphs'][14][8]
    script += 'select_key|escape\nshell_page|10\nwait_idle\n'
    script += ptr('down', left) + ptr('move', first['glyphs'][-1][8], 1) + 'select_edge\nwait_idle\n'
    script += ptr('move', right, 1) + ptr('up', right, 1) + copied('cross-page') + shot('cross-page11')
    script += 'prev\nwait_idle\n' + shot('cross-page10')
    # Keyboard character extension is independent of word snapping.
    script += 'select_key|escape\n' + ptr('down', a) + ptr('up', a)
    for i, key in enumerate(('right', 'right', 'left')):
        script += f'select_key|{key}|1|0\n' + copied(f'shift-{i}')
    for i, page in enumerate((2, 6, 10)):
        script += f'shell_page|{page}\nwait_idle\nselect_key|A|0|1\n' + copied(f'all-{i}')
    script += 'select_key|escape\n' + shot('escaped') + 'quit\n'
    target = work / 'hong'
    shots = ['plain', 'sentence-light', 'sentence-dark', 'cross-page10', 'cross-page11', 'escaped']
    launch_capture(exe, font, script, work / 'hong-profile', target, shots)
    result['1_sentence'] = check(target, 'sentence', phrase, a, b)
    result['2_cross_page'] = check(target, 'cross-page', source[left:right+3], left, right+3)
    result['2_cross_page']['boundary'] = boundary
    result['3_cjk'] = [check(target, *row) for row in cjk]
    result['4_double'] = [check(target, *row) for row in doubles]
    result['4_triple'] = [check(target, *row) for row in triples]
    result['7_shift'] = [check(target, f'shift-{i}', source[a:a+n], a, a+n) for i, n in enumerate((3, 6, 3))]
    result['7_all'] = [check(target, f'all-{i}', source, 0, len(source)) for i in range(3)]
    # English examples use original, distributable prose.
    english = work / 'english.epub'; fixture_book(english)
    en_open = open_book(english, 'Selection Original')
    run(exe, font, en_open + 'shell_measure|page\nselect_key|A|0|1\n' + copied('source') + 'quit\n', work / 'en-discover-profile', work / 'en-discover')
    en_source = (work / 'en-discover/source.part.utf8').read_bytes()
    script = en_open; english_rows = []
    for i, word in enumerate(('Alpha', 'bravo', 'reader', 'selection', 'English')):
        lo = en_source.index(word.encode()); name = f'english-{i}'
        script += 'select_key|escape\n' + ptr('down', lo+1) + ptr('move', lo+2, 1) + ptr('up', lo+2, 1) + copied(name)
        english_rows.append((name, word.encode(), lo, lo+len(word)))
    run(exe, font, script + 'quit\n', work / 'en-profile', work / 'english')
    result['3_english'] = [check(work / 'english', *row) for row in english_rows]
    # Grass Pillow: column-oriented selection across several physical columns.
    v_open = open_book(vertical, '草枕') + 'shell_page|5\nwait_idle\n'
    run(exe, font, v_open + 'shell_measure|page\nquit\n', work / 'v-discover-profile', work / 'v-discover')
    meta = read(work / 'v-discover/page.json'); assert meta['mode'] == 1
    lo, hi = meta['glyphs'][2][8], meta['glyphs'][55][8]
    script = v_open + shot('vertical-plain') + ptr('down', lo) + ptr('move', hi, 1) + ptr('up', hi, 1) + copied('vertical')
    script += shot('vertical-light') + 'shell_click|dark\n' + shot('vertical-dark') + 'quit\n'
    launch_capture(exe, font, script, work / 'v-profile', work / 'vertical', ['vertical-plain', 'vertical-light', 'vertical-dark'])
    selected = read(work / 'vertical/vertical.selection.json')
    v_source = (work / 'vertical/vertical.part.utf8').read_bytes()
    result['5_vertical'] = check(work / 'vertical', 'vertical', v_source[selected['start'][1]:selected['end'][1]])
    result['5_vertical']['writing_mode'] = meta['mode']
    # Verify the selection is a background: full ink pixels remain unchanged.
    from PIL import Image, ImageChops
    images = [Image.open(target / (name + '.png')).convert('RGB') for name in ('plain', 'sentence-light')]
    diff = ImageChops.difference(*images)
    result['background_pixels_changed'] = sum(p != (0, 0, 0) for p in diff.getdata())
    assert result['background_pixels_changed'] > 0
    ink = (27, 27, 31)
    result['opaque_ink_changed'] = sum(x == ink and y != ink for x, y in zip(images[0].getdata(), images[1].getdata()))
    assert result['opaque_ink_changed'] == 0
    v_images = [Image.open(work / 'vertical' / (name + '.png')).convert('RGB') for name in ('vertical-plain', 'vertical-light')]
    v_diff = ImageChops.difference(*v_images)
    result['5_vertical']['highlight_changed_pixels'] = sum(p != (0, 0, 0) for p in v_diff.getdata())
    box = v_diff.getbbox(); assert box and box[3]-box[1] > box[2]-box[0], box
    result['5_vertical']['highlight_box'] = box
    assert result['5_vertical']['highlight_changed_pixels'] > 0
    for folder, names in [(target, shots), (work / 'vertical', ['vertical-plain', 'vertical-light', 'vertical-dark'])]:
        for name in names:
            (output / (name + '.png')).write_bytes((folder / (name + '.png')).read_bytes())
    for name in ('sentence', 'cross-page'):
        for suffix in ('.utf8', '.clipboard.utf8', '.selection.json'):
            (output / (name + suffix)).write_bytes((target / (name + suffix)).read_bytes())
    (output / 'sentence.expected.utf8').write_bytes(phrase)
    (output / 'cross-page.expected.utf8').write_bytes(source[left:right+3])
    result['pass'] = True; dump(output / 'result.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
