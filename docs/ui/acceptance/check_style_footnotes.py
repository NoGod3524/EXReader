#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Production HWND acceptance for reading styles, presets and popup footnotes.
Every change goes through the real settings EDIT/BUTTON/COMBOBOX controls or a
posted mouse/key message (examples/windows/shell_style_drive.inc). Screenshots
use ops/capture_window.py through check_selection.launch_capture.
Usage: check_style_footnotes.py EXE FONT OUTPUT
"""
import json, os, sys
from pathlib import Path
from check_selection import launch_capture, shot, ptr, read
from check_step5 import dump
ROOT = Path(__file__).resolve().parents[3]
FIX = ROOT / 'tests/fixtures/style-footnotes'
KEYS = ['font_size', 'line_height', 'paragraph_spacing', 'top', 'right', 'bottom', 'left', 'letter_spacing']
NAMES = ['字号', '行距', '段距', '上边距', '右边距', '下边距', '左边距', '字距']
LEVELS = [(12, 24, 32), (1.2, 2.0, 2.2), (0, 1.0, 1.5), (0, 80, 120), (0, 80, 120), (0, 80, 120), (0, 80, 120), (-0.02, 0.03, 0.06)]
DEFAULT = dict(font_size=18, line_height=1.75, paragraph_spacing=0.5, top=40, right=48, bottom=40, left=48, letter_spacing=0)
PAGE_NUMBER_H = 40


def setup(title, chapter=False):
    s = f'open|{title}\nwait_idle\nshell|on\nshell_dpi|96\nshell_client|1280|800\nwait_idle\nshell_click|light\nstyle_reset\nwait_idle\n'
    if chapter: s += 'shell_click|toc\nprobe_wait|230\ntoc_click|1\nwait_idle\n'
    return s


def style(folder, name): return read(folder / (name + '.style.json'))
def popup(folder, name): return read(folder / (name + '.popup.json'))
def same(a, b): return all(abs(a[k] - b[k]) < 1e-5 for k in KEYS)


def check_geometry(d):
    s = d['style']
    assert d['config'][0] == d['client'][0] - s['left'] - s['right'], d
    assert d['gaps'] == dict(left=s['left'], top=s['top'], right=s['right'], bottom=s['bottom'] + PAGE_NUMBER_H), d
    return d['gaps']


def main():
    exe, font, out = [Path(x).resolve() for x in sys.argv[1:]]; out.mkdir(parents=True, exist_ok=True)
    books = {b['id']: b for b in read(ROOT / 'tools/regress/corpus.json')['books']}
    hong = books['hongloumeng-24264']; result = {}
    profile = out / 'profile'
    os.environ['EXREADER_ANNOTATIONS_DIR'] = str(out / 'annotations')

    def launch(script, name, shots=(), p=profile):
        launch_capture(exe, font, script, p, out / name, shots); return out / name

    # 1+2: every field at three levels through the production EDIT; each change must rebuild the pager.
    s = f'import|{hong["path"]}\n' + setup('紅樓夢', True) + 'style_dump|base\n'
    for i, levels in enumerate(LEVELS):
        for j, v in enumerate(levels):
            s += f'style_field|{i}|{v}\nwait_idle\nstyle_dump|f{i}-{j}\n'
            if (i, j) in ((0, 2), (6, 2)): s += shot(f'f{i}-{j}')
        s += f'style_reset\nwait_idle\nstyle_dump|reset{i}\n'
    s += 'style_step|0|plus\nwait_idle\nstyle_dump|step-plus\nstyle_step|0|minus\nwait_idle\nstyle_dump|step-minus\n'
    s += 'style_field|0|99\nwait_idle\nstyle_dump|rejected\nquit\n'
    folder = launch(s, 'params', ('f0-2', 'f6-2'))
    base = style(folder, 'base'); assert same(base['style'], DEFAULT), base; check_geometry(base)
    previous = base['builds']; rows = []
    for i, levels in enumerate(LEVELS):
        for j, v in enumerate(levels):
            d = style(folder, f'f{i}-{j}')
            assert abs(d['style'][KEYS[i]] - v) < 1e-5 and d['valid'] and d['glyphs'] > 0, d
            assert d['builds'] > previous, (i, j, d['builds'], previous)  # immediate reflow, no restart
            assert d['frame_epoch'] == d['epoch'], d
            others = {k: d['style'][k] for k in KEYS if k != KEYS[i]}
            assert all(abs(others[k] - DEFAULT[k]) < 1e-5 for k in others), d
            gaps = check_geometry(d); previous = d['builds']
            rows.append(dict(field=NAMES[i], value=v, builds=d['builds'], glyphs=d['glyphs'],
                             config=d['config'], gaps=gaps, ink_gaps=d['ink_gaps']))
        r = style(folder, f'reset{i}'); assert same(r['style'], DEFAULT); previous = r['builds']
    assert style(folder, 'step-plus')['style']['font_size'] == 19 and style(folder, 'step-minus')['style']['font_size'] == 18
    assert same(style(folder, 'rejected')['style'], DEFAULT)
    result['reflow'] = f'{len(rows)}/{len(rows)} changes rebuilt immediately (8 fields x 3 levels), 0 crashes; buttons +/- 2/2; out-of-range 99px rejected'
    result['reflow_rows'] = rows
    # Independence: each edge changed alone leaves the other three measured gaps untouched.
    edges = {}
    for i, key in ((3, 'top'), (4, 'right'), (5, 'bottom'), (6, 'left')):
        changes = []
        for j, v in enumerate(LEVELS[i]):
            d = style(folder, f'f{i}-{j}'); gaps = d['gaps']; want = check_geometry(base)
            for edge in ('left', 'top', 'right', 'bottom'):
                if edge != key: assert gaps[edge] == want[edge], (key, v, gaps, want)
            changes.append(dict(value=v, gaps=gaps, ink_gaps=d['ink_gaps']))
        edges[key] = changes
    left = [style(folder, f'f6-{j}') for j in range(3)]
    result['left_only'] = dict(method='page-HWND client gaps of the composed page bitmap (view.dx/dy, bitmap size) and the ink box (non-background pixels of the rendered frame)',
                               base_right_gap=base['gaps']['right'], base_right_ink_gap=base['ink_gaps']['right'],
                               left=[d['style']['left'] for d in left], right_gap=[d['gaps']['right'] for d in left],
                               right_ink_gap=[d['ink_gaps']['right'] for d in left], left_gap=[d['gaps']['left'] for d in left],
                               left_ink_gap=[d['ink_gaps']['left'] for d in left])
    result['edges'] = edges

    # 3: two presets, switch, restart, switch again.
    a = dict(font_size=22, line_height=2.0, paragraph_spacing=1.0, top=20, right=60, bottom=80, left=100, letter_spacing=0.03)
    b = dict(font_size=14, line_height=1.4, paragraph_spacing=0.2, top=110, right=8, bottom=16, left=24, letter_spacing=-0.01)
    pp = out / 'preset-profile'
    s = f'import|{hong["path"]}\n' + setup('紅樓夢', True)
    for name, values in (('护眼大字', a), ('紧凑', b)):
        for i, k in enumerate(KEYS): s += f'style_field|{i}|{values[k]}\nwait_idle\n'
        s += f'style_save|{name}\n'
    s += 'style_reset\nwait_idle\nstyle_dump|reset\nstyle_pick|0\nwait_idle\nstyle_dump|pick-a\nstyle_pick|1\nwait_idle\nstyle_dump|pick-b\nstyle_pick|0\nwait_idle\nstyle_dump|pick-a2\nquit\n'
    folder = launch(s, 'presets', p=pp)
    assert same(style(folder, 'reset')['style'], DEFAULT)
    assert same(style(folder, 'pick-a')['style'], a) and same(style(folder, 'pick-b')['style'], b) and same(style(folder, 'pick-a2')['style'], a)
    assert style(folder, 'pick-b')['presets'] == ['护眼大字', '紧凑']
    for n in ('pick-a', 'pick-b'): check_geometry(style(folder, n))
    restart = launch(setup('紅樓夢', True).replace('style_reset\nwait_idle\n', '') + 'style_dump|restart\nstyle_pick|1\nwait_idle\nstyle_dump|restart-b\nquit\n', 'presets-restart', p=pp)
    assert same(style(restart, 'restart')['style'], a), style(restart, 'restart')  # last applied style persisted
    assert same(style(restart, 'restart-b')['style'], b)
    shelf = json.loads((pp / 'shelf.json').read_text(encoding='utf-8'))
    (out / 'shelf-settings.json').write_text(json.dumps(shelf['settings'], ensure_ascii=False, indent=2), encoding='utf-8')
    result['presets'] = '2/2 saved; switch A→B→A exact 8/8 fields each; restart restores current A and preset B 8/8; stored in shelf.json settings.style_presets'

    # 4+5: popup footnotes on three constructed books (+ none), 10 clicks each.
    clicks = {}
    for kind in ('chapter', 'end', 'vertical', 'none'):
        title = f'Style {kind}'; s = f'import|{FIX / f"style-{kind}.epub"}\n' + setup(title) + 'footnote_refs|refs\nquit\n'
        refs = read(launch(s, f'refs-{kind}', p=out / f'{kind}-profile') / 'refs.footnotes.json')
        n = len(refs['references'])
        if kind == 'none': assert n == 0 and not refs['footnotes']; clicks[kind] = dict(recognized=0, references=0); continue
        s = setup(title)
        for i, (part, start, end, note) in enumerate(refs['references']):
            s += f'annotgoto|{part}|{start}\nwait_idle\nstyle_dump|before-{i}\nfootnote_click|{i}\nfootnote_dump|open-{i}\n'
            if i == 0: s += shot(f'{kind}-popup') + 'footnote_scroll\nfootnote_dump|scrolled\n'
            s += 'footnote_key\n' if i % 2 == 0 else 'footnote_outside\n'
            s += f'footnote_dump|closed-{i}\nstyle_dump|after-{i}\n'
        s += 'quit\n'
        folder = launch(s, f'popup-{kind}', (f'{kind}-popup',), p=out / f'{kind}-profile'); ok = 0
        for i, (part, start, end, note) in enumerate(refs['references']):
            before, opened, closed, after = style(folder, f'before-{i}'), popup(folder, f'open-{i}'), popup(folder, f'closed-{i}'), style(folder, f'after-{i}')
            want = refs['footnotes'][note]
            w, h = opened['box'][2] - opened['box'][0], opened['box'][3] - opened['box'][1]
            assert opened['visible'] and opened['index'] == note and opened['text'] == want['text'], (kind, i, opened)
            assert opened['title'] == '脚注 ' + want['label'] and w <= 360 and h <= opened['client'][1] / 2, opened
            assert (before['part'], before['page'], before['range']) == (opened['part'], opened['page'], opened['range']) == (after['part'], after['page'], after['range'])
            assert not closed['visible'], closed
            ok += 1
        sc = popup(folder, 'scrolled')
        clicks[kind] = dict(recognized=len(refs['footnotes']), references=n, popups=f'{ok}/{n}', page_unchanged=f'{ok}/{n}',
                            closed=f'Esc {(n + 1) // 2} + outside {n // 2}', box=popup(folder, 'open-0')['box'],
                            mode=popup(folder, 'open-0')['mode'], scroll=sc['scroll'])
    assert clicks['vertical']['mode'] == 1
    result['footnotes'] = clicks

    # 6: two highlights + one note survive 18→24→18 through the style panel font field.
    s = setup('紅樓夢', True) + 'shell_measure|anchor-base\nquit\n'
    meta = read(launch(s, 'anchor-discover') / 'anchor-base.json')
    ranges = []
    for line in meta['lines']:
        glyphs = [g for g in meta['glyphs'][line[2]:line[2] + line[3]] if not g[7] & (4 | 2048)]
        # Use a text drag longer than the shelf gesture's 4-DIP tap threshold.
        if len(glyphs) < 12: continue
        ranges.append((glyphs[1][8], glyphs[10][8]))
        if len(ranges) == 3: break
    assert len(ranges) == 3
    s = setup('紅樓夢', True) + f'annotgoto|1|{meta["range"][0]}\nwait_idle\n'
    for i, (start, end) in enumerate(ranges):
        # Saving the previous annotation already clears its text selection.
        # An extra Esc here would return to the shelf under the shelf flow.
        s += 'annot_close\n'
        s += ptr('down', start) + ptr('move', end, 1) + ptr('up', end, 1)
        s += f'annot_command|{3 + i}\n' if i < 2 else 'annot_command|6\nannot_edit|样式改变后笔记仍在原位|2\n'
    s += 'annot_close\nannot_dump|a18\n' + shot('a18')
    s += 'style_field|0|24\nwait_idle\nannot_dump|a24\n' + shot('a24') + 'style_field|0|18\nwait_idle\nannot_dump|a18b\n' + shot('a18b') + 'quit\n'
    folder = launch(s, 'anchors', ('a18', 'a24', 'a18b'))
    stages = [read(folder / f'{n}.annotations.json') for n in ('a18', 'a24', 'a18b')]
    spans = [[(x['start'], x['end']) for x in st['items']] for st in stages]
    assert all(st['count'] == 3 and all(x['found'] and x['visible'] for x in st['items']) for st in stages), stages
    assert spans[0] == spans[1] == spans[2] and [st['font'] for st in stages] == [18, 24, 18]
    assert [x['bounds'] for x in stages[0]['items']] == [x['bounds'] for x in stages[2]['items']]
    assert sum(bool(x['text']) for x in stages[0]['items']) == 1
    result['anchors'] = dict(result='3/3 (2 highlights + 1 note) found+visible at 18→24→18; logical ranges identical; pixel bounds at 18 identical before/after',
                             ranges=spans[0], bounds18=[x['bounds'] for x in stages[0]['items']], bounds24=[x['bounds'] for x in stages[1]['items']])

    # 9 + C: settings panel, margin extremes and the book's own front contents page.
    s = setup('紅樓夢', True) + 'shell_click|settings\nwait_idle\nprobe_wait|400\n' + shot('settings-panel') + 'shell_click|settings\nwait_idle\n'
    for name, values in (('margins-0', [0, 0, 0, 0]), ('margins-120', [120, 120, 120, 120])):
        for i, v in zip((3, 4, 5, 6), values): s += f'style_field|{i}|{v}\nwait_idle\n'
        s += f'style_dump|{name}\n' + shot(name)
    s += 'style_reset\nwait_idle\nquit\n'
    folder = launch(s, 'screens', ('settings-panel', 'margins-0', 'margins-120'))
    for n in ('margins-0', 'margins-120'): check_geometry(style(folder, n))
    s = setup('紅樓夢') + 'shell_page|1\nwait_idle\nstyle_dump|front-default\n' + shot('front-default')
    for name, values in (('front-font32-m120', {0: 32, 3: 120, 4: 120, 5: 120, 6: 120}), ('front-font12-m0', {0: 12, 3: 0, 4: 0, 5: 0, 6: 0})):
        s += 'style_reset\nwait_idle\n' + ''.join(f'style_field|{i}|{v}\nwait_idle\n' for i, v in values.items())
        s += f'style_dump|{name}\nshell_measure|{name}-measure\n' + shot(name)
    s += 'style_reset\nwait_idle\nquit\n'
    folder = launch(s, 'front', ('front-default', 'front-font32-m120', 'front-font12-m0'))
    front = {}
    for n in ('front-font32-m120', 'front-font12-m0'):
        d = style(folder, n); check_geometry(d); m = read(folder / f'{n}-measure.json')
        w, h = m['page']
        inside = all(-0.5 <= g[3] and g[3] + g[5] <= w + 0.5 and g[4] <= h + 0.5 for g in m['glyphs'] if not g[7] & 4)
        assert inside, n
        front[n] = dict(part=d['part'], page=d['page'], glyphs=d['glyphs'], content=d['config'][:2], glyphs_inside=inside)
    result['front_contents'] = front
    dump(out / 'result.json', result)
    print(json.dumps({k: v for k, v in result.items() if k not in ('reflow_rows', 'edges')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
