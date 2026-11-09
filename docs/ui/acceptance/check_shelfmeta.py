#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Shelf metadata / series / tags / statistics acceptance on the production HWND.
Screenshots: ops/capture_window.py (via check_selection.launch_capture).
Usage: check_shelfmeta.py EXE FONT OUTPUT
"""
import datetime, hashlib, json, os, sys, time
from pathlib import Path
from PIL import Image, ImageDraw
from check_selection import launch_capture, read
from check_step5 import dump
ROOT = Path(__file__).resolve().parents[3]

SERIES = {  # library title -> (series, index, tags)
    'The Fire Next Time': ('火的系列', 2, '经典,种族'),
    'The Fire This Time': ('火的系列', 3, '种族'),
    'Between the World and Me': ('火的系列', 1, '种族,回忆录'),
    'Born a Crime': ('成长三部曲', 3, '回忆录'),
    'Crying in H Mart': ('成长三部曲', 1, '回忆录'),
    'Black Boy': ('成长三部曲', 2, '经典,回忆录'),
}
EDITS = {  # library title -> (title, author, series, index, tags, cover size)
    'PACHINKO': ('柏青哥', '李珉锦', '', '', '小说,经典', (300, 450)),
    'The House on Mango Street': ('芒果街上的小屋', '桑德拉·希斯内罗丝', '', '', '小说', (320, 480)),
    'A Raisin in the Sun': ('阳光下的葡萄干', '洛林·汉斯伯里', '', '', '', (280, 420)),
}
IDS = ['the-fire-next-time', 'the-fire-this-time-a-new-generation-speaks-about-race', 'between-the-world-and-me',
       'born-a-crime', 'crying-in-h-mart', 'black-boy', 'pachinko', 'the-house-on-mango-street', 'a-raisin-in-the-sun']
SETUP = 'shell|on\nshell_dpi|96\nshell_client|1280|800\nwait_idle\nshell_click|light\n'


def shot(name):
    return f'shell_measure|{name}\nprobe_wait|900\n'


def cover(path, size, label, rgb):
    im = Image.new('RGB', size, rgb); d = ImageDraw.Draw(im)
    d.rectangle([12, 12, size[0] - 13, size[1] - 13], outline=(255, 255, 255), width=4)
    d.text((30, size[1] // 2), label, fill=(255, 255, 255)); im.save(path)


def edit(title, fields, cover_path=None):
    s = f'sm_context|{title}|edit\n'
    for i, v in enumerate(fields):
        s += f'sm_field|{i}|{v}\n'
    if cover_path: s += f'sm_cover|{cover_path}\n'
    return s


def noon(days_ago):
    d = datetime.datetime.now().replace(hour=12, minute=0, second=0, microsecond=0) - datetime.timedelta(days=days_ago)
    return int(d.timestamp() * 1000), d.strftime('%Y-%m-%d')


def main():
    exe, font, out = [Path(x).resolve() for x in sys.argv[1:]]
    out.mkdir(parents=True, exist_ok=True)
    profile = out / 'profile'; shelf = out / 'shelf.json'
    os.environ['EXREADER_SHELF_PATH'] = str(shelf); os.environ['EXREADER_ANNOTATIONS_DIR'] = str(out / 'annotations')
    books = {b['id']: b['path'] for b in read(ROOT / 'tools/regress/corpus.json')['books']}
    covers = {}
    for i, (t, e) in enumerate(EDITS.items()):
        covers[t] = out / f'cover-{i + 1}.png'
        cover(covers[t], e[5], f'COVER {i + 1}', [(176, 64, 48), (40, 120, 90), (60, 70, 160)][i])

    def launch(script, name, shots=()):
        folder = out / name; launch_capture(exe, font, script, profile, folder, shots); return folder

    # 1) import, edit 3 books (title/author/tags/cover), build 2 series x3 with tags
    s = ''.join(f'import|{books[i]}\n' for i in IDS) + SETUP + 'sm_show|0\nsm_dump|imported\n'
    for t, (title, author, series, index, tags, _) in EDITS.items():
        s += edit(t, [title, author, series, index, tags], covers[t])
        if t == 'PACHINKO': s += shot('edit-dialog')
        s += 'sm_save\n'
    for t, (series, index, tags) in SERIES.items():
        s += edit(t, ['', '', series, str(index), tags]) + 'sm_save\n'
    s += 'sm_click|grid\nsm_dump|edited\n' + shot('grid') + 'sm_click|list\n' + shot('list') + 'sm_click|grid\nquit\n'
    edited = read(launch(s, 'edit', ('edit-dialog', 'grid', 'list')) / 'edited.shelf.json')
    shelf_after_edit = shelf.read_bytes()

    # 2) restart: persistence, covers, series order, 4 tag filters
    tags = ['经典', '种族', '回忆录', '小说']
    s = SETUP + 'sm_show|0\nsm_dump|restarted\n' + shot('restarted-grid')
    for i, tag in enumerate(tags):
        s += f'sm_click|tag|{tag}\nsm_dump|filter-{i}\n' + shot(f'filter-{i}')
    s += 'sm_click|untagged\nsm_dump|filter-untagged\n' + shot('filter-untagged') + 'sm_click|all\n'
    # rollback: injected write failure keeps dialog open, memory and file unchanged
    s += 'sm_context|PACHINKO|edit\n' + shot('edit-dialog-tags') + 'sm_field|0|不应保存\nsm_fail_next\nsm_save|expect_fail\nsm_cancel\nsm_dump|after-failed-save\n'
    # remove covers
    for t in EDITS: s += f'sm_context|{t}|edit\nsm_nocover\nsm_save\n'
    s += 'sm_dump|covers-removed\nquit\n'
    rs = launch(s, 'restart', ('restarted-grid', 'filter-untagged', 'edit-dialog-tags') + tuple(f'filter-{i}' for i in range(4)))
    restarted = read(rs / 'restarted.shelf.json')

    # 3) restart after cover removal
    s = SETUP + 'sm_show|0\nsm_dump|removed-restarted\n' + shot('removed-restarted') + 'quit\n'
    removed = read(launch(s, 'restart2', ('removed-restarted',)) / 'removed-restarted.shelf.json')

    # 4) statistics: 3 books x 2 minutes on 3 consecutive days (virtual clock), then stats page
    base, first_day = noon(2)
    s = SETUP + f'sm_clock|freeze|{base}\nsm_foreground|1\n'
    read_books = ['Between the World and Me', 'Born a Crime', 'The House on Mango Street']
    for d, t in enumerate(read_books):
        if d: s += 'sm_clock|advance|86400000\n'
        s += f'sm_context|{t}|open\nwait_idle\n'
        if d == 0: s += shot('reading')
        for _ in range(12): s += 'next\nwait_idle\nsm_clock|advance|10000\n'
        s += f'sm_show|0\nsm_dump|read-{d}\n'
    s += 'sm_click|stats\nsm_dump|stats\n' + shot('stats') + 'sm_click|shelf\nsm_click|list\n' + shot('list-progress') + 'sm_click|grid\nquit\n'
    st = launch(s, 'stats', ('reading', 'stats', 'list-progress')); stats = read(st / 'stats.shelf.json')
    shelf_sample = shelf.read_bytes()

    # 5) idle rule: separate shelf file; 5 min still -> only 30 s credited; focus loss -> 0
    os.environ['EXREADER_SHELF_PATH'] = str(out / 'idle-shelf.json')
    t0, _ = noon(0)
    s = SETUP + f'sm_clock|freeze|{t0}\nsm_foreground|1\nsm_context|Black Boy|open\nwait_idle\nnext\nwait_idle\nsm_dump|idle-0\n'
    s += 'sm_clock|advance|300000\nsm_dump|idle-5min\nsm_clock|advance|300000\nsm_dump|idle-10min\n'
    s += 'next\nwait_idle\nsm_clock|advance|10000\nsm_dump|idle-resume\n'
    s += 'sm_foreground|0\nnext\nwait_idle\nsm_clock|advance|60000\nsm_dump|idle-unfocused\nquit\n'
    idle = launch(s, 'idle')
    os.environ['EXREADER_SHELF_PATH'] = str(shelf)

    # ---- checks ----
    def by(d, title):
        return next(o for o in d['order'] if o['library_title'] == title)
    persisted = 0
    for t, (title, author, _, _, tg, size) in EDITS.items():
        a, b = by(edited, t), by(restarted, t)
        fields = lambda o: (o['title'], o['author'], o['tags'])
        assert fields(a) == fields(b) == (title, author, [x for x in tg.split(',') if x]), (a, b)
        assert list(b['cover_decoded']) == list(size) and b['cover'], b
        persisted += 1
    cover_restored = sum(list(by(restarted, t)['cover_decoded']) == list(EDITS[t][5]) for t in EDITS)
    for t in EDITS:
        o = by(removed, t); assert o['cover'] is None and o['cover_decoded'] == [0, 0], o
    leftover = list((out / 'covers').glob('*'))
    # series: grouped, ordered by index, groups sorted by name
    groups = {}
    for o in restarted['order']:
        if o['series']: groups.setdefault(o['series'], []).append((o['series_index'], o['library_title']))
    seq = [o['series'] for o in restarted['order'] if o['series']]
    assert all(seq[i] == seq[i + 1] for i in range(len(seq) - 1) if i % 3 != 2), seq  # contiguous blocks of 3
    for name, members in groups.items():
        assert len(members) == 3 and [m[0] for m in members] == [1, 2, 3], (name, members)
    # tag filters vs expected counts from the assignment tables
    expected = {}
    for t, (_, _, tg) in SERIES.items():
        for x in tg.split(','): expected[x] = expected.get(x, 0) + 1
    for t, e in EDITS.items():
        for x in [x for x in e[4].split(',') if x]: expected[x] = expected.get(x, 0) + 1
    filter_counts = {}
    for i, tag in enumerate(tags):
        d = read(rs / f'filter-{i}.shelf.json'); assert d['filter'] >= 0
        filter_counts[tag] = d['filters'][tag]; assert d['filters'][tag] == expected[tag], (tag, d['filters'], expected)
    untagged = read(rs / 'filter-untagged.shelf.json')['filters']['(untagged)']
    assert untagged == 1, untagged  # A Raisin in the Sun has no tags
    failed = read(rs / 'after-failed-save.shelf.json')
    assert by(failed, 'PACHINKO')['title'] == '柏青哥' and failed['save_failures'] == 1
    # statistics
    read_ms = {t: by(stats, t)['read_ms'] for t in read_books}
    assert all(v == 120000 for v in read_ms.values()), read_ms
    assert stats['total_read_ms'] == 360000 and stats['streak'] == 3, stats
    assert [d[1] for d in stats['days']] == [120000] * 3 and stats['days'][0][0] == first_day, stats['days']
    opens = {t: by(stats, t)['opens'] for t in read_books}
    assert all(v == 1 for v in opens.values()), opens
    iv = {n: by(read(idle / f'idle-{n}.shelf.json'), 'Black Boy')['read_ms'] for n in ('0', '5min', '10min', 'resume', 'unfocused')}
    assert iv['5min'] - iv['0'] == 30000 and iv['10min'] == iv['5min'] and iv['resume'] - iv['10min'] == 10000 and iv['unfocused'] == iv['resume'], iv
    (out / 'shelf-sample.json').write_bytes(shelf_sample)
    result = dict(
        edits_persisted=f'{persisted}/3', covers_restored=f'{cover_restored}/3', covers_removed_to_default='3/3',
        cover_files_left_after_removal=len(leftover),
        series={k: [m[1] for m in v] for k, v in groups.items()},
        tag_filters=filter_counts, tag_expected={k: expected[k] for k in tags}, untagged=untagged,
        failed_save_rollback=dict(dialog_kept=True, title_unchanged=True, save_failures=failed['save_failures']),
        stats=dict(read_ms=read_ms, opens=opens, total_read_ms=stats['total_read_ms'], streak=stats['streak'], days=stats['days']),
        idle_ms=iv, shelf_sha256_after_edit=hashlib.sha256(shelf_after_edit).hexdigest())
    dump(out / 'result.json', result); print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
