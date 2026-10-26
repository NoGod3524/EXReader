"""Actions-only: bounded group browsing over an isolated seeded catalog.

Originals come from the unchanged public-SDK seed. Projected group rows below
are test fixtures, so this test proves the host browser, not sync or editing.
"""
import ctypes as C
from ctypes import wintypes as W
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time
import traceback

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests/windows_host'))
from check_shelf_ui import Product
spec=importlib.util.spec_from_file_location('organizer_ui',ROOT/'tests/reader_windows_import_organize/check_ui.py')
ui=importlib.util.module_from_spec(spec);spec.loader.exec_module(ui)
out=ROOT/'build/group-page-ui';out.mkdir(parents=True,exist_ok=False)
profile=out/'profile';profile.mkdir()
exe=ROOT/'build/c09/package/EXReader/EXReader.exe'
seed=ROOT/'build/cloud-readback/group-page-seed.exe'
checks=[];problems=[];app=None;phase='seed'
report={'accepted':False,'source_sha':os.environ['GITHUB_SHA'],'run_id':os.environ['GITHUB_RUN_ID'],
        'attempt':os.environ['GITHUB_RUN_ATTEMPT'],'checks':checks,'problems':problems,
        'scope':'real Windows host group browser; fixture-only projected memberships, not sync'}
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def stable_numbers():
    box=app.control('books');before=ui.U.GetPropW(box,'EXReaderShelfSnapshot') or 0
    if before<2 or before%2:return None
    titles=app.titles();after=ui.U.GetPropW(box,'EXReaderShelfSnapshot') or 0
    if before!=after or after%2:return None
    matches=[re.search(r'Shelf (\d{4})',title) for title in titles]
    if any(match is None for match in matches):return None
    return [int(match[1]) for match in matches]
def starts_with(expected):
    values=stable_numbers()
    # A tall native window can prefetch the next 50-row page before the test
    # observes the first one; require a complete ordered prefix and cache bound.
    return values is not None and 50<=len(values)<=150 and values==expected[:len(values)]
def organizer():
    app.wait_idle();ui.U.SetForegroundWindow(app.window);ui.A.tap(ord('O'),(ui.A.VK_CONTROL,ui.A.VK_SHIFT))
    def find():
        found=[]
        @ui.ENUM
        def visit(w,_):
            pid=W.DWORD();ui.U.GetWindowThreadProcessId(w,C.byref(pid))
            if pid.value==app.process.pid and ui.U.IsWindowVisible(w) and ui.U.GetDlgItem(w,ui.ROWS):found.append(w)
            return True
        ui.U.EnumWindows(visit,0);assert len(found)<=1;return found[0] if found else None
    d=app.wait(find,timeout=30)
    app.wait(lambda:not ui.U.IsWindowEnabled(ui.U.GetDlgItem(d,ui.CANCEL)),timeout=120)
    return d
def names(d):
    box=ui.U.GetDlgItem(d,ui.GROUPS);rows=[]
    for i in range(ui.send(box,0x18B)):
        n=ui.send(box,0x18A,i);value=C.create_unicode_buffer(n+1)
        ui.send(box,0x189,i,C.addressof(value));rows.append(value.value)
    return rows
def open_group(action,name):
    d=organizer();ui.send(ui.U.GetDlgItem(d,ui.ACTION),0x14E,action)
    ui.send(d,0x111,(1<<16)|ui.ACTION,ui.U.GetDlgItem(d,ui.ACTION))
    app.wait(lambda:name in names(d),timeout=60)
    ui.send(ui.U.GetDlgItem(d,ui.GROUPS),0x186,names(d).index(name))
    ui.send(ui.U.GetDlgItem(d,260),ui.ACCOUNT.BM_CLICK);app.wait(lambda:not ui.U.IsWindow(d),timeout=30)
def show_all():
    d=organizer();ui.send(ui.U.GetDlgItem(d,261),ui.ACCOUNT.BM_CLICK)
    app.wait(lambda:not ui.U.IsWindow(d),timeout=30)
    app.wait(lambda:starts_with(list(range(2202))),timeout=90)
def refresh():
    app.wait_idle();ui.send(ui.U.GetDlgItem(app.window,ui.ACCOUNT.ACCOUNT),ui.ACCOUNT.BM_CLICK)
    def find():
        found=[]
        @ui.ENUM
        def visit(w,_):
            pid=W.DWORD();ui.U.GetWindowThreadProcessId(w,C.byref(pid))
            if pid.value==app.process.pid and ui.U.IsWindowVisible(w) and ui.U.GetDlgItem(w,ui.ACCOUNT.FORGET):found.append(w)
            return True
        ui.U.EnumWindows(visit,0);return found[0] if len(found)==1 else None
    d=app.wait(find,timeout=30)
    app.wait(lambda:ui.U.IsWindowEnabled(ui.U.GetDlgItem(d,ui.ACCOUNT.FORGET)),timeout=60)
    ui.send(ui.U.GetDlgItem(d,ui.ACCOUNT.CLOSE),ui.ACCOUNT.BM_CLICK)
    app.wait(lambda:not ui.U.IsWindow(d),timeout=30)
def walk(expected,direction):
    positions={value:i for i,value in enumerate(expected)};seen=set()
    box=app.control('books')
    for _ in range(500):
        values=stable_numbers()
        if values is None:time.sleep(.08);continue
        assert len(values)<=150 and len(values)==len(set(values))
        indexes=[positions[v] for v in values]
        assert indexes==list(range(indexes[0],indexes[0]+len(indexes))) if indexes else True
        seen.update(values)
        top=ui.send(box,0x18E)
        if direction>0 and len(seen)==len(expected) and values[-1]==expected[-1]:return
        if direction<0 and values and values[0]==expected[0] and top==0:return
        for _ in range(8):ui.send(box,0x20A,((-120 if direction>0 else 120)&0xffff)<<16)
        time.sleep(.08)
    raise AssertionError('group paging did not reach the expected edge: '+repr((direction,len(seen),stable_numbers())))
try:
    assert os.name=='nt' and os.environ.get('GITHUB_ACTIONS')=='true'
    with (out/'seed.log').open('wb') as log:
        subprocess.run([str(seed),str(profile/'library.sqlite')],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
    app=Product(exe,exe.parent/'Reader.otf',profile,existing=True)
    app.wait(lambda:starts_with(list(range(2202))),timeout=180);app.wait_idle()
    phase='fixture-projection'
    database=str(profile/'library.sqlite')+'.product.sqlite'
    ids={'shelf':'a'*32,'tag':'b'*32,'series':'c'*32}
    with sqlite3.connect(database,timeout=30) as db:
        rows=db.execute("SELECT b.book_key,b.title FROM reader_books b JOIN reader_local_books l ON l.book_key=b.book_key ORDER BY b.title LIMIT 170").fetchall()
        assert len(rows)==170 and [int(re.search(r'Shelf (\d{4})',t)[1]) for _,t in rows]==list(range(170))
        db.execute('INSERT INTO reader_shelves(shelf_id,name) VALUES (?,?)',(ids['shelf'],'Paged shelf'))
        db.execute('INSERT INTO reader_tags(tag_id,name) VALUES (?,?)',(ids['tag'],'Paged tag'))
        db.execute('INSERT INTO reader_series(series_id,name) VALUES (?,?)',(ids['series'],'Paged series'))
        for i,(key,_) in enumerate(rows):
            db.execute('INSERT INTO reader_book_shelves(shelf_id,book_key,ordinal) VALUES (?,?,?)',(ids['shelf'],key,169-i))
            db.execute('INSERT INTO reader_book_tags(tag_id,book_key) VALUES (?,?)',(ids['tag'],key))
            db.execute('INSERT INTO reader_book_series(series_id,book_key,ordinal) VALUES (?,?,?)',(ids['series'],key,169-i))
        tag_order=[int(re.search(r'Shelf (\d{4})',title)[1]) for _,title in sorted(rows)]
    for kind,action,name,expected in [('shelf',2,'Paged shelf',list(range(169,-1,-1))),
                                      ('tag',4,'Paged tag',tag_order),
                                      ('series',6,'Paged series',list(range(169,-1,-1)))]:
        phase=kind;open_group(action,name);app.wait(lambda:starts_with(expected),timeout=90)
        walk(expected,1);walk(expected,-1);checks.append(kind+'-forward-reverse-bounded-170')
        app.search('Shelf 0001');app.wait(lambda:stable_numbers()==[1],timeout=90)
        app.search('');app.wait(lambda:starts_with(expected),timeout=90);checks.append(kind+'-literal-search')
        if kind=='shelf':
            phase='removed-anchor'
            app.scroll(1,lambda values:app.top() is not None and 25<app.top()<110)
            top=app.top();assert top is not None
            with sqlite3.connect(database,timeout=30) as db:
                db.execute('UPDATE reader_book_shelves SET ordinal=200 WHERE shelf_id=? AND book_key=?',(ids['shelf'],rows[top][0]))
            refresh();app.wait(lambda:app.top()==top and stable_numbers() and stable_numbers()[-1]==top,timeout=90)
            checks.append('moved-anchor-follows-current-order')
            with sqlite3.connect(database,timeout=30) as db:
                db.execute('UPDATE reader_book_shelves SET ordinal=? WHERE shelf_id=? AND book_key=?',(169-top,ids['shelf'],rows[top][0]))
            refresh();app.wait(lambda:app.top()==top and stable_numbers() and stable_numbers()[0]==top,timeout=90)
            with sqlite3.connect(database,timeout=30) as db:
                db.execute('DELETE FROM reader_book_shelves WHERE shelf_id=? AND book_key=?',(ids['shelf'],rows[top][0]))
            refresh();app.wait(lambda:stable_numbers() is not None and top not in stable_numbers(),timeout=90)
            assert app.top() is not None and abs(app.top()-top)<=2,(top,app.top(),stable_numbers())
            ui.M.screenshot(app.window,out/'removed-anchor.bmp')
            checks.append('removed-top-anchor-keeps-neighbor')
            phase='removed-tail'
            app.scroll(1,lambda values:values[-1]==0)
            top=app.top();assert top is not None and top<100
            with sqlite3.connect(database,timeout=30) as db:
                db.executemany('DELETE FROM reader_book_shelves WHERE shelf_id=? AND book_key=?',[(ids['shelf'],rows[i][0]) for i in range(top+1)])
            refresh();app.wait(lambda:stable_numbers() and all(n>top for n in stable_numbers()),timeout=90)
            assert min(stable_numbers())==top+1,(top,stable_numbers())
            ui.M.screenshot(app.window,out/'removed-tail.bmp')
            checks.append('removed-tail-falls-back-to-predecessors')
            phase='removed-all'
            with sqlite3.connect(database,timeout=30) as db:db.execute('DELETE FROM reader_book_shelves WHERE shelf_id=?',(ids['shelf'],))
            refresh();app.wait(lambda:stable_numbers()==[],timeout=90)
            ui.M.screenshot(app.window,out/'removed-all.bmp')
            checks.append('removed-all-shows-empty')
            with sqlite3.connect(database,timeout=30) as db:
                db.executemany('INSERT INTO reader_book_shelves(shelf_id,book_key,ordinal) VALUES (?,?,?)',[(ids['shelf'],key,169-i) for i,(key,_) in enumerate(rows)])
        show_all()
    checks.append('return-to-all-books-after-each-group')
    app.close();assert app.process.returncode==0,'host did not close cleanly'
    with sqlite3.connect(database,timeout=30) as db:db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchall()
    report.update(accepted=True,program_sha256=sha(exe),seed_sha256=sha(seed),fixture_catalog_sha256=sha(Path(database)),originals=2202,members_per_group=170)
except Exception as error:
    problems.append(phase+': '+type(error).__name__+': '+str(error));traceback.print_exc()
    if app and app.process.poll() is None:
        observed={}
        try:observed.update(status=app.status(),titles=app.titles(),process_id=app.process.pid)
        except Exception as diagnostic:observed['ui_error']=repr(diagnostic)
        try:
            catalog=Path(str(profile/'library.sqlite')+'.product.sqlite')
            assert catalog.is_file(),'product catalog absent'
            with sqlite3.connect(catalog.resolve().as_uri()+'?mode=ro',uri=True,timeout=1) as db:
                observed['book_count']=db.execute('SELECT count(*) FROM reader_books').fetchone()[0]
                observed['local_count']=db.execute('SELECT count(*) FROM reader_local_books').fetchone()[0]
        except Exception as diagnostic:observed['catalog_error']=repr(diagnostic)
        try:ui.M.screenshot(app.window,out/'failure.bmp')
        except Exception as diagnostic:observed['screenshot_error']=repr(diagnostic)
        report['failure_observation']=observed
finally:
    if app and app.process.poll() is None:
        app.process.kill();app.process.wait(timeout=20);app.log.close()
    (out/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report),flush=True)
if not report['accepted']:raise SystemExit('Group pagination rejected')
