"""Native Win32 font acceptance; observations and fault injection are review-build only."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('wave3_font_driver', ROOT / 'tests/reader_wave3_c09/check_ui.py')
W = importlib.util.module_from_spec(spec)
spec.loader.exec_module(W)
P, U, send, N = W.P, W.U, W.send, W.N
assert os.environ.get('GITHUB_ACTIONS') == 'true' and os.name == 'nt'
out = ROOT / 'build/windows-font/evidence'
out.mkdir(parents=True, exist_ok=False)
exe = ROOT / 'build/windows-font/host/EXReaderWave3.exe'
font = ROOT / 'build/host-font-cache/Reader.otf'
profile = out / 'profile'
report = {'accepted': False, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
          'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'program_sha256': hashlib.sha256(exe.read_bytes()).hexdigest(),
          'checks': [], 'problems': []}
app = None

def loc():
    return tuple(send(app.window, 0x8000 + 32, i) for i in (1, 2, 3, 4))

def contains(before, after):
    assert before[3] and after[3] and before[0] == after[0] and after[1] <= before[1] < after[2], (before, after)

def events():
    p = profile / 'font-lease-review.log'
    return [line.split() for line in p.read_text(encoding='ascii').splitlines()] if p.exists() else []

def record(name):
    report['checks'].append({'name': name, 'location': loc(), 'events': events()})

try:
    app = P.App(exe, font, profile)
    app.wait_idle()
    W.import_and_open(app, ROOT / 'build/windows-font/fixtures/Picture book.epub')
    assert send(app.window, 0x8000 + 32, 8) == 1
    for _ in range(2):
        app.click('next'); app.wait_idle()
    initial = loc()
    assert initial[1] > 0 and initial[3], initial
    before_image = W.page_hash(app, out, 'before.bmp')
    d = W.open_feature(app, W.FONTS)
    W.post_click(d, W.B1); W.fill_system_dialog(app, ROOT / 'tests/fixtures/fonts/primary.ttf')
    W.wait_message(app, d, N.FONT_IMPORTED, 120)
    app.wait(lambda: len(W.rows(d)) == 2, timeout=30)
    W.select_row(d, 1); W.post_click(d, W.B2)
    W.wait_message(app, d, N.FONT_SWITCHED, 240); app.wait_idle()
    switched = loc(); contains(initial, switched)
    assert events() == [['open', '0', '1']], events()
    W.close_feature(app, d)
    selected_image = W.page_hash(app, out, 'selected.bmp')
    assert selected_image != before_image
    record('noninitial-valid-font-keeps-live-point-and-acquires-lease')

    d = W.open_feature(app, W.FONTS)
    W.select_row(d, 1); W.post_click(d, W.B2)
    W.wait_message(app, d, '已经在使用', 60)
    assert events()[-2:] == [['open', '0', '2'], ['release', '0', '1']], events()
    assert loc() == switched
    record('same-font-releases-temporary-lease')

    bad = out / 'bad.ttf'; bad.write_bytes(b'not a font ' * 64)
    W.post_click(d, W.B1); W.fill_system_dialog(app, bad)
    W.wait_message(app, d, N.FONT_IMPORT_FAILED, 60)
    assert len(W.rows(d)) == 2 and N.IN_USE in W.rows(d)[1] and loc() == switched
    assert events()[-1] == ['release', '0', '1']
    W.close_feature(app, d)
    assert selected_image == W.page_hash(app, out, 'bad-rollback.bmp')
    record('bad-font-preserves-selected-frame-and-lease')

    d = W.open_feature(app, W.FONTS)
    W.post_click(d, W.B1); W.fill_system_dialog(app, ROOT / 'tests/fixtures/fonts/fallback.ttf')
    W.wait_message(app, d, N.FONT_IMPORTED, 120)
    app.wait(lambda: len(W.rows(d)) == 3, timeout=30)
    fallback = next(i for i, row in enumerate(W.rows(d)) if 'fallback' in row)
    W.select_row(d, fallback)
    assert send(app.window, 0x8000 + 32, 5) == 1
    W.post_click(d, W.B2)
    W.wait_message(app, d, '字体切换失败', 240); app.wait_idle()
    assert loc() == switched and any('primary' in row and N.IN_USE in row for row in W.rows(d))
    assert events()[-2:] == [['open', '0', '2'], ['release', '0', '1']], events()
    W.close_feature(app, d)
    assert W.page_hash(app, out, 'layout-failure.bmp') == selected_image
    record('layout-failure-releases-candidate-and-preserves-frame-and-active-lease')

    d = W.open_feature(app, W.FONTS)
    fallback = next(i for i, row in enumerate(W.rows(d)) if 'fallback' in row)
    assert send(app.window, 0x8000 + 32, 6) == 1
    W.select_row(d, fallback); W.post_click(d, W.B2)
    W.wait_message(app, d, N.FONT_SWITCHED, 240); app.wait_idle()
    contains(switched, loc())
    assert send(app.window, 0x8000 + 32, 7) == 1
    assert events()[-2:] == [['open', '0', '2'], ['release', '0', '1']], events()
    W.close_feature(app, d)
    switched = loc()
    record('replacement-keeps-live-point-and-held-progress-and-releases-old-lease')

    d = W.open_feature(app, W.FONTS); W.post_click(d, W.B3)
    W.wait_message(app, d, N.FONT_SWITCHED, 240); app.wait_idle()
    contains(switched, loc())
    assert events()[-1] == ['release', '0', '0'], events()
    W.close_feature(app, d)
    record('builtin-restore-releases-lease-and-keeps-live-point')
    d = W.open_feature(app, W.FONTS); W.select_row(d, 1); W.post_click(d, W.B2)
    W.wait_message(app, d, N.FONT_SWITCHED, 240); app.wait_idle(); W.close_feature(app, d)
    assert events()[-1] == ['open', '0', '1']
    app.close(); assert app.process.returncode == 0
    assert events()[-2:] == [['release', '0', '0'], ['close', '0', '0']], events()
    report['checks'].append({'name': 'shutdown-releases-lease-and-closes-library', 'events': events()})

    profile = out / 'ordinary-profile'
    app = P.App(exe, font, profile)
    app.wait_idle()
    html = out / 'ordinary.html'
    html.write_text('<html><body>' + ''.join('<p>Position %04d ordinary document text remains here.</p>' % i
                                            for i in range(300)) + '</body></html>', encoding='utf-8')
    W.import_and_open(app, html)
    assert send(app.window, 0x8000 + 32, 8) == 0
    for _ in range(2):
        app.click('next'); app.wait_idle()
    ordinary = loc(); assert ordinary[1] > 0 and ordinary[3]
    d = W.open_feature(app, W.FONTS)
    W.post_click(d, W.B1); W.fill_system_dialog(app, ROOT / 'tests/fixtures/fonts/primary.ttf')
    W.wait_message(app, d, N.FONT_IMPORTED, 120)
    app.wait(lambda: len(W.rows(d)) == 2, timeout=30)
    W.select_row(d, 1); W.post_click(d, W.B2)
    W.wait_message(app, d, N.FONT_SWITCHED, 240); app.wait_idle()
    contains(ordinary, loc()); assert events() == [['open', '0', '1']]
    W.close_feature(app, d); record('ordinary-document-font-switch-keeps-noninitial-point')
    app.close(); assert app.process.returncode == 0
    assert events()[-2:] == [['release', '0', '0'], ['close', '0', '0']]
    report['accepted'] = True
except BaseException as error:
    traceback.print_exc()
    report['problems'].append(repr(error))
finally:
    if app and app.process.poll() is None:
        try: app.close()
        except BaseException: app.process.kill(); app.process.wait()
    (out / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
if not report['accepted']:
    sys.exit(1)
