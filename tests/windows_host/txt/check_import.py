"""Actions-only native picker coverage for the incomplete TXT host integration."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import traceback

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tests/reader_windows_compact'))
import check_ui as ui
sys.path.insert(0, str(ROOT / 'tests/reader_perf_windows'))
from perf_windows import make_txt_fixture


def main():
    assert os.name == 'nt' and os.environ.get('GITHUB_ACTIONS') == 'true'
    exe, font, out = map(lambda x: Path(x).resolve(), sys.argv[1:4])
    out.mkdir(parents=True, exist_ok=False)
    fixture = make_txt_fixture(out, 0)
    expected = '4f45393b25817f506a51b56cc5d61599556e4dd5b0bd59aa00f7eb43cbfc0a86'
    def digest(path):
        with path.open('rb') as f:
            return hashlib.file_digest(f, 'sha256').hexdigest()
    assert fixture.stat().st_size == 16792975 and digest(fixture) == expected
    report = dict(source_sha=os.environ['GITHUB_SHA'], host_sha256=digest(exe), checks=[],
                  scope='native picker import and duplicate only; reading is not implemented', accepted=False)
    app = None
    try:
        profile = out / 'profile'
        app = ui.P.App(exe, font, profile)
        app.wait_idle()
        ui.picker(app, fixture)
        assert '阅读与书架显示尚未完成' in app.status(), app.status()
        report['checks'].append('native picker import reports unavailable reader')
        original = Path(str(app.db) + '.originals') / (expected + '.txt')
        assert original.stat().st_size == 16792975 and digest(original) == expected
        with sqlite3.connect(str(app.db) + '.product.sqlite') as db:
            rows = db.execute('SELECT book_key,state FROM reader_originals').fetchall()
        assert rows == [('txt:' + expected, 'ready')], rows
        report['checks'].append('product original bytes and ready catalog row')
        app.close(); app = None
        app = ui.P.App(exe, font, profile, existing=True)
        app.wait_idle()
        ui.picker(app, fixture)
        assert 'TXT 原书已存在' in app.status(), app.status()
        with sqlite3.connect(str(app.db) + '.product.sqlite') as db:
            assert db.execute('SELECT count(*) FROM reader_originals').fetchone()[0] == 1
        assert digest(original) == expected and digest(fixture) == expected
        report['checks'].append('duplicate after restart preserves original')
        report['accepted'] = True
    except Exception:
        report['error'] = traceback.format_exc()
    finally:
        if app: app.close()
        (out / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False), flush=True)
    assert report['accepted']


if __name__ == '__main__':
    main()
