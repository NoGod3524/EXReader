"""Exercise the sole Windows bookshelf through real HWND clicks and scrollbar messages.

Usage: python tools/quality/check_cleanup2_shelf.py EXE FONT OUTPUT
Raw books and profiles stay in OUTPUT; only copy reports/captures into docs.
"""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'docs/ui/acceptance'))
from check_selection import launch_capture, read, shot


def main():
    exe, font, out = (Path(x).resolve() for x in sys.argv[1:])
    out.mkdir(parents=True, exist_ok=True)
    profile = out / 'profile'
    os.environ['EXREADER_SHELF_PATH'] = str(profile / 'shelf.json')
    os.environ['EXREADER_ANNOTATIONS_DIR'] = str(out / 'annotations')
    setup = 'shell|on\nshell_dpi|96\nshell_client|1280|800\nwait_idle\nshell_click|light\n'

    def run(name, script, shots=()):
        folder = out / name
        launch_capture(exe, font, setup + script + 'quit\n', profile, folder, shots)
        return folder

    empty = run('empty', 'check|retired_controls\nsm_dump|empty\n' + shot('empty'), ('empty',))
    assert read(empty / 'empty.shelf.json')['visible'] == 1
    books = read(ROOT / 'tools/regress/corpus.json')['books']
    discovered = run('import', ''.join(f"import|{b['path']}\n" for b in books) + 'sm_dump|books\n')
    order = read(discovered / 'books.shelf.json')['order']
    assert len(order) == 19
    chosen = order[:5]
    first = chosen[0]['library_title']
    script = 'sm_click|grid\nsm_dump|grid\n' + shot('grid')
    script += 'sm_click|list\nsm_dump|list\n' + shot('list')
    script += 'sm_scroll|1\nsm_dump|scrolled\n' + shot('scrollbar')
    script += 'sm_scroll|0\nsm_click|grid\n'
    script += f'sm_context|{first}|edit\nsm_field|4|验收标签\nsm_save\n'
    script += 'sm_click|tag|验收标签\nsm_dump|tag\n' + shot('tag-filter')
    script += 'sm_click|all\n'
    for i, book in enumerate(chosen):
        script += f"sm_click|book|{book['library_title']}\nwait_idle\nshelf_dump|reading-{i}\ncheck|retired_controls\n"
        script += f'shelf_return\nwait_idle\nshelf_dump|returned-{i}\nsm_dump|returned-{i}\n'
    folder = run('acceptance', script, ('grid', 'list', 'scrollbar', 'tag-filter'))
    grid, listing, scrolled, tag = (read(folder / (n + '.shelf.json')) for n in ('grid', 'list', 'scrolled', 'tag'))
    assert grid['view'] == 'grid' and listing['view'] == 'list'
    assert scrolled['scroll'] > 0 and scrolled['scroll_max'] >= scrolled['scroll_page']
    assert tag['filter'] >= 0 and tag['filters']['验收标签'] == 1
    rows = []
    for i, book in enumerate(chosen):
        reading = read(folder / f'reading-{i}.state.json')
        returned = read(folder / f'returned-{i}.state.json')
        view = read(folder / f'returned-{i}.shelf.json')
        assert reading['book'] == book['id'] and reading['reading'] == 1 and reading['shelf'] == 0
        assert returned['reading'] == 0 and returned['shelf'] == 1 and view['visible'] == 1
        rows.append(dict(id=book['id'], title=book['library_title'], entered=True, returned=True))
    result = dict(roundtrips='5/5', rows=rows, books=19, scroll=scrolled['scroll'],
                  tag_filter_count=1, retired_controls='absent at shelf and all five books',
                  captures=['empty/empty.png', *['acceptance/' + n + '.png' for n in ('grid', 'list', 'scrollbar', 'tag-filter')]])
    (out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
