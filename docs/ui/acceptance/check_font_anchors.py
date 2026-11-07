#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exact visible-head checks at pages 100/800; called by check_step5.py."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys

from check_step5 import run, dump


def check(exe, font, out):
    out.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location('fixtures', root/'tests/windows_host/make_fixtures.py')
    fixtures = importlib.util.module_from_spec(spec); spec.loader.exec_module(fixtures)
    # Small paragraphs keep the EPUB chapter window bounded, with unique quotes.
    paragraphs = [' '.join(f'Record {i*40+j:06d}: Reading a portable book keeps its content point while letters change size and pages are measured again.'
                           for j in range(40)) for i in range(400)]
    book = out/'Anchor-long.epub'
    fixtures.epub(book, 'Anchor long', '</p><p>'.join(paragraphs))
    rows = []
    for location in (100, 800):
        dest = out/str(location)
        script = (f'import|{book}\nopen|Anchor long\nwait_idle\nshell|on\nshell_dpi|96\n'
                  f'shell_font|17\nshell_client|1280|800\nwait_idle\nshell_page|{location}\nwait_idle\nshell_measure|before\n')
        for i in range(6):
            script += f'shell_click|plus\nwait_idle\nshell_measure|step-{i}\n'
        script += 'next\nwait_idle\nshell_measure|next\nprev\nwait_idle\nshell_measure|prev\n'
        for i, size in enumerate((17, 18, 24, 32, 17)):
            script += f'shell_font|{size}\nwait_idle\nshell_measure|jump-{i}\nsnapshot|jump-{i}\n'
        script += 'shell_client|720|560\nwait_idle\nshell_measure|small\nshell_client|1280|800\nwait_idle\nshell_measure|roundtrip\nquit\n'
        run(exe, font, script, dest/'profile', dest, timeout_seconds=1200)
        with sqlite3.connect(dest/'profile/library.sqlite') as db:
            assert db.execute('select count(*) from epub_bounded_books').fetchone()[0] == 1
        def measure(name): return json.loads((dest/(name+'.json')).read_text())
        before = measure('before')
        assert before['index']+1 == location, (location, before['index'])
        head = before['lines'][0][0]
        previous = before
        expected = [(f'step-{i}', size) for i, size in enumerate((18,20,22,24,28,32))]
        expected += [(f'jump-{i}', size) for i, size in enumerate((17,18,24,32,17))]
        for name, size in expected:
            current = measure(name)
            assert current['font'] == size, (location, name, current['font'], size)
            start, end = current['lines'][0][:2]
            glyphs = current['glyphs'][:current['lines'][0][3]]
            # Verify the owned text and the actual visible glyph source, too.
            prefix = current['text'].encode()[start-current['range'][0]:end-current['range'][0]]
            original = before['text'].encode()[head-before['range'][0]:]
            assert start == head and min(g[0] for g in glyphs) == head and original.startswith(prefix), (location, name, head, start)
            rows.append(dict(location=location, transition=f'{previous["font"]:g}->{current["font"]:g}',
                             name=name, source_before=previous['lines'][0][0], source_after=start,
                             page_before=previous['index']+1, page_after=current['index']+1, passed=True))
            previous = current
        step = measure('step-5'); next_ = measure('next'); prev = measure('prev')
        assert next_['lines'][0][0] == step['range'][1], (location, 'forward gap/overlap')
        assert prev['lines'][0][0] == head, (location, 'back head')
        for name in ('small', 'roundtrip'):
            assert measure(name)['lines'][0][0] == head, (location, name)
    result = dict(pass_=True, transitions=rows, stepped_passes=sum(r['name'].startswith('step') for r in rows),
                  jump_passes=sum(r['name'].startswith('jump') for r in rows),
                  fixture_sha256=hashlib.sha256(book.read_bytes()).hexdigest())
    dump(out/'result.json', result)
    return result


if __name__ == '__main__':
    print(json.dumps(check(*(Path(p).resolve() for p in sys.argv[1:])), indent=2))
