"""Actions-only long product-TXT font relayout and owner lifecycle acceptance."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('wave3_txt_font_driver', ROOT / 'tests/reader_wave3_c09/check_ui.py')
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
sys.path.insert(0, str(ROOT / 'tests/reader_perf_windows'))
from perf_windows import make_txt_fixture
P, send, N = W.P, W.send, W.N
assert os.environ.get('GITHUB_ACTIONS') == 'true' and os.name == 'nt'
out = ROOT / 'build/windows-font/evidence/txt'
out.mkdir(parents=True, exist_ok=False)
profile = out / 'profile'
exe = ROOT / 'build/windows-font/host/EXReaderWave3.exe'
font = ROOT / 'build/host-font-cache/Reader.otf'
report = {'accepted': False, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
          'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'program_sha256': hashlib.sha256(exe.read_bytes()).hexdigest(),
          'checks': [], 'problems': []}
app = None

def loc():
    return tuple(send(app.window, 0x8000 + 32, i) for i in (1, 2, 3, 4))

def point():
    return send(app.window, 0x8000 + 32, 9)

def events():
    path = profile / 'font-lease-review.log'
    return [line.split() for line in path.read_text(encoding='ascii').splitlines()] if path.exists() else []

def check_point(expected):
    current = loc()
    assert current[3] and current[1] <= expected < current[2], (expected, current)
    assert point() == expected, (point(), expected, current)

def record(name, **details):
    report['checks'].append({'name': name, 'passed': True, 'location': loc(), 'events': events(), **details})

def selected(dialog, name):
    return next(i for i, row in enumerate(W.rows(dialog)) if name in row)

def durable_point(key):
    dbpath = Path(str(app.db) + '.product.sqlite')
    with sqlite3.connect(dbpath, timeout=20) as db:
        rows = db.execute("SELECT revision_id, body_json FROM reader_revisions WHERE entity_kind='progress' AND entity_key=?", (key,)).fetchall()
    wires = [(rid, json.loads(body)) for rid, body in rows]
    parents = {p for _, wire in wires for p in wire['parents']}
    heads = [wire for rid, wire in wires if rid not in parents]
    assert len(heads) == 1, heads
    return heads[0]['payload']['location']['selector']['start']

try:
    fixture = make_txt_fixture(out, 0)
    with fixture.open('rb') as f:
        digest = hashlib.file_digest(f, 'sha256').hexdigest()
    assert fixture.stat().st_size == 16792975 and digest == '4f45393b25817f506a51b56cc5d61599556e4dd5b0bd59aa00f7eb43cbfc0a86'
    app = P.App(exe, font, profile); app.wait_idle()
    W.import_and_open(app, fixture)
    assert send(app.window, 0x8000 + 32, 10) == 1
    first = loc()
    app.click('next'); app.wait_idle(); second = loc()
    app.click('next'); app.wait_idle(); third = loc()
    assert 0 < third[1] and first[1] < second[1] < third[1], (first, second, third)
    assert second[2] == third[1], (second, third)
    target = third[1]
    base = W.page_hash(app, out, 'before.bmp')
    d = W.open_feature(app, W.FONTS)
    W.post_click(d, W.B1); W.fill_system_dialog(app, ROOT / 'tests/fixtures/fonts/primary.ttf')
    W.wait_message(app, d, N.FONT_IMPORTED, 120); app.wait(lambda: len(W.rows(d)) == 2, timeout=30)
    W.select_row(d, 1); W.post_click(d, W.B2)
    W.wait_message(app, d, N.FONT_SWITCHED, 240); app.wait_idle(); check_point(target)
    assert events() == [['open', '0', '1']]
    W.close_feature(app, d)
    selected_image = W.page_hash(app, out, 'selected.bmp'); assert selected_image != base
    assert durable_point('txt:' + digest) == target
    record('txt-boundary-noninitial-select-retains-exact-point', point=target, previous_end=second[2])

    d = W.open_feature(app, W.FONTS)
    bad = out / 'bad.ttf'; bad.write_bytes(b'not a valid font' * 64)
    before = loc(); prior_events = events()
    W.post_click(d, W.B1); W.fill_system_dialog(app, bad); W.wait_message(app, d, N.FONT_IMPORT_FAILED, 120)
    assert loc() == before and point() == target and events() == prior_events
    assert any('primary' in row and N.IN_USE in row for row in W.rows(d))
    W.close_feature(app, d); assert W.page_hash(app, out, 'bad.bmp') == selected_image
    record('txt-bad-font-keeps-frame-point-and-lease', point=target)

    d = W.open_feature(app, W.FONTS)
    W.post_click(d, W.B1); W.fill_system_dialog(app, ROOT / 'tests/fixtures/fonts/fallback.ttf')
    W.wait_message(app, d, N.FONT_IMPORTED, 120); app.wait(lambda: len(W.rows(d)) == 3, timeout=30)
    W.select_row(d, selected(d, 'fallback'))
    assert send(app.window, 0x8000 + 32, 11) == 1
    W.post_click(d, W.B2); W.wait_message(app, d, '字体切换失败', 240); app.wait_idle()
    assert loc() == before and point() == target and events()[-2:] == [['open', '0', '2'], ['release', '0', '1']]
    assert any('primary' in row and N.IN_USE in row for row in W.rows(d))
    W.close_feature(app, d); assert W.page_hash(app, out, 'outside-page.bmp') == selected_image
    record('txt-rejects-outside-page-and-releases-candidate', point=target)

    for name in ('fallback', 'primary', 'fallback', None, 'primary'):
        d = W.open_feature(app, W.FONTS)
        if name is None:
            W.post_click(d, W.B3)
        else:
            W.select_row(d, selected(d, name)); W.post_click(d, W.B2)
        W.wait_message(app, d, N.FONT_SWITCHED, 240); app.wait_idle(); check_point(target)
        W.close_feature(app, d)
        assert durable_point('txt:' + digest) == target
    assert events()[-1][2] == '1', events()
    record('txt-repeated-switches-keep-same-point-and-durable-position', point=target)

    before_nav = loc(); app.click('next'); app.wait_idle(); after_nav = loc()
    assert after_nav[1] > before_nav[1], (before_nav, after_nav)
    new_point = after_nav[1]
    d = W.open_feature(app, W.FONTS); W.post_click(d, W.B3)
    W.wait_message(app, d, N.FONT_SWITCHED, 240); app.wait_idle(); check_point(new_point)
    W.close_feature(app, d); assert durable_point('txt:' + digest) == new_point
    assert events()[-1] == ['release', '0', '0']
    record('txt-navigation-establishes-new-point', point=new_point)
    app.close(); assert app.process.returncode == 0
    assert events()[-1] == ['close', '0', '0']
    report['accepted'] = True
except BaseException as error:
    traceback.print_exc(); report['problems'].append(repr(error))
finally:
    if app and app.process.poll() is None:
        try: app.close()
        except BaseException: app.process.kill(); app.process.wait()
    (out / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
if not report['accepted']:
    sys.exit(1)
