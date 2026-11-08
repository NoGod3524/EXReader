#!/usr/bin/env python3
"""Check real-book typography telemetry against the host's font shaper.

Run after check_typography.py captures, with the rebuilt check_typography_font
executable: python verify_typography.py EVIDENCE/resume out/font-test.exe
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from PIL import Image, ImageChops


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def pixels(path, meta):
    with Image.open(path) as image:
        x, y, _, _ = meta['client_box']
        l, t, r, b = meta['body']
        return image.convert('RGB').crop((x+l, y+t, x+r, y+b))


def verify(root, probe):
    title_rows = []
    indents = []
    for folder in ('after', 'dpi96'):
        v = read(root/folder/'chapter-27.json')
        first = v['lines'][0]
        glyphs = v['glyphs'][first[2]:first[2]+first[3]]
        title = ''.join(chr(g[2]) for g in glyphs)
        assert title.startswith('第二十七回') and title.endswith('殘紅'), title
        size = glyphs[0][6]
        text = root/(folder+'-shape.txt')
        text.write_text(title, encoding='utf-8')
        shaped = subprocess.run([str(probe), 'NotoSerifSC-VF.ttf', '0', str(size), str(text)],
                                capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
                                env={**os.environ, 'EXR_TEST_WINDOWS': os.environ['SystemRoot']},
                                timeout=30, check=True).stdout.decode('utf-8')
        (root/(folder+'-default-advances.txt')).write_text(shaped.replace('\r\n', '\n'), encoding='utf-8', newline='\n')
        defaults = [float(s.split(',')[2]) for s in shaped.splitlines() if s.startswith('glyph=')]
        assert len(defaults) == len(glyphs)
        rows = []
        for i, (g, default) in enumerate(zip(glyphs, defaults)):
            delta = abs(g[5]-default)/size
            assert delta <= .01, (folder, chr(g[2]), delta)
            origin = glyphs[i+1][3]-g[3] if i+1 < len(glyphs) else None
            if origin is not None:
                assert abs(origin-default)/size <= .01
            rows.append(dict(char=chr(g[2]), x=g[3], advance=g[5], default=default,
                             delta_em=delta, next_origin_delta=origin))
        title_rows.append(dict(folder=folder, size=size, title=title, glyphs=rows))
        a, b = v['lines'][1:3]
        indent = a[4]-b[4]
        assert abs(indent-2*v['font']) < .001
        indents.append(dict(folder=folder, dpi=v['dpi'], font=v['font'],
                            indent_physical_px=indent, indent_at_96_dpi=indent*96/v['dpi'],
                            body_line_height=a[7]))
    write(root/'title-advances.json', title_rows)
    write(root/'indents.json', indents)

    end = read(root/'after/chapter-26-end.json')
    start = read(root/'after/chapter-27-next.json')
    assert end['part'] == start['part'] and start['index'] == end['index']+1
    visible_end = ''.join(chr(g[2]) for g in end['glyphs'])
    assert '下回分解' in visible_end and '第二十七回' not in visible_end
    assert start['text'].startswith('第二十七回')
    assert end['lines'][-1][5]+end['lines'][-1][7] < end['page'][1]
    # Hidden source rules may remain in the text projection, never in glyphs.
    assert not any(g[2] in (0x2500, 0x2014, 0x5f) for g in start['glyphs'])
    write(root/'chapter-transition.json', dict(
        previous_page=[end['part']+1, end['index']+1],
        next_page=[start['part']+1, start['index']+1],
        previous_range=end['range'], next_range=start['range'],
        previous_page_blank_px=end['page'][1]-end['lines'][-1][5]-end['lines'][-1][7]))

    series = {}
    for folder, expected in [('latin-before', 42), ('latin-after', 45)]:
        files = sorted((root/folder).glob('sample-*.json'))
        assert len(files) == expected
        entries = []
        for path in files:
            meta = read(path)
            png = path.with_suffix('.png')
            body = pixels(png, meta)
            entries.append(dict(part=meta['part']+1, page=meta['index']+1,
                                range=meta['range'], body_sha256=hashlib.sha256(body.tobytes()).hexdigest(),
                                png_sha256=hashlib.sha256(png.read_bytes()).hexdigest()))
        assert len({(r['part'], r['page']) for r in entries}) == expected
        series[folder] = entries
    def ends(entries):
        return {part: max(r['range'][1] for r in entries if r['part'] == part)
                for part in {r['part'] for r in entries}}
    assert ends(series['latin-before']) == ends(series['latin-after'])
    rows = []
    for i, (a, b) in enumerate(zip(series['latin-before'], series['latin-after'])):
        assert a['body_sha256'] != b['body_sha256']
        before = pixels(root/'latin-before'/f'sample-{i+1:03}.png', read(root/'latin-before'/f'sample-{i+1:03}.json'))
        after = pixels(root/'latin-after'/f'sample-{i+1:03}.png', read(root/'latin-after'/f'sample-{i+1:03}.json'))
        delta = ImageChops.difference(before, after)
        red, green, blue = delta.split()
        nonzero = ImageChops.lighter(ImageChops.lighter(red, green), blue)
        changed = delta.width*delta.height-nonzero.histogram()[0]
        rows.append(dict(ordinal=i+1, before=a, after=b, different_body_pixels=changed))
    write(root/'latin-comparison.json', dict(before_pages=42, after_pages=45,
          changed_body_hashes=len(rows), additional_after_pages=3, rows=rows,
          additional_after=series['latin-after'][42:],
          explanation='Serif advances rewrap the same book: 42 baseline pages become 45. All 42 ordinal body hashes change. The strict 42-page target is not met.'))
    for folder in ('after', 'dpi96', 'cross-spine', 'latin-before', 'latin-after'):
        process = read(root/folder/'process.json')
        assert process['exit'] == 0 and process['foreground_observations'] == 0
    assert read(root/'selftest/report.json')['checks'] == 26
    assert read(root/'selftest/process.json')['exit'] == 0
    print('Real-book title advances, 2em indents, chapter transition, 87 Sample captures and self-test verified.')


if __name__ == '__main__':
    verify(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
