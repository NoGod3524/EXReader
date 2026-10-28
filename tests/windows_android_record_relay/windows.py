"""Actions-only actual Win32 author/receiver. SQLite queries are read-only evidence."""
import argparse, ctypes as C, hashlib, importlib.util, json, os, sqlite3, sys, traceback, zipfile
from ctypes import wintypes as W
from pathlib import Path
import relay
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('record_relay_ui',ROOT/'tests/reader_windows_import_organize/check_ui.py')
ui=importlib.util.module_from_spec(spec);spec.loader.exec_module(ui)
BUTTON,ROWS,MESSAGE,BODY,PROGRESS,BOOKMARK,HIGHLIGHT,EDIT,DELETE,RESTORE,OPEN,PREVIOUS,NEXT,REFRESH,RETRY,DISCARD,CANCEL,CLOSE=range(210,228)

def original(path):
    # A real EPUB original generated only on Actions; no application data is seeded.
    sys.path.insert(0,str(ROOT/'tests/reader_reading_state'))
    from make_fixtures import epub,entry,xhtml
    epub(path)
    with zipfile.ZipFile(path) as z:parts={n:z.read(n) for n in z.namelist()}
    parts['book.opf']=parts['book.opf'].replace(b'Reading state fixture',b'Record relay').replace(b'<itemref idref="b"/><itemref idref="a"/>',b'')
    parts['a.xhtml']=xhtml(''.join('<p>Relay unique paragraph %03d. '%i+''.join('Distinct reading evidence token %03d-%03d. '%(i,j) for j in range(10))+'</p>' for i in range(20))+'<p>'+('Ambiguous context repeats without a unique discriminator. '*4000)+'</p>')
    with zipfile.ZipFile(path,'w') as z:
        for n,b in parts.items():entry(z,n,b)

def main():
    p=argparse.ArgumentParser();p.add_argument('--phase',choices=['windows-first','windows-return'],required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--previous',type=Path);p.add_argument('--package',type=Path,required=True);a=p.parse_args()
    assert os.name=='nt';identity=relay.identity();a.out.mkdir(parents=True,exist_ok=False)
    exe=(a.package/'EXReader.exe').resolve();font=(a.package/'Reader.otf').resolve();app=dav=None
    report={**identity,'phase':a.phase,'passed':False,'checks':[],'program_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),'raw_records':[],'actual_pages':[]}
    def sql(q,args=()):
        with sqlite3.connect('file:'+str(app.db)+'.product.sqlite?mode=ro',uri=True) as db:return db.execute(q,args).fetchall()
    def annotations():return [json.loads(x[0]) for x in sql("SELECT body_json FROM reader_revisions WHERE entity_kind='annotation' ORDER BY rowid")]
    def settle(d):app.wait(lambda:not ui.U.IsWindowEnabled(ui.U.GetDlgItem(d,CANCEL)),timeout=90);app.wait_idle()
    def dialog():
        found=[]
        @ui.ENUM
        def visit(w,unused):
            pid=W.DWORD();ui.U.GetWindowThreadProcessId(w,C.byref(pid))
            if pid.value==app.process.pid and ui.U.IsWindowVisible(w) and ui.U.GetDlgItem(w,ROWS):found.append(w)
            return True
        ui.U.EnumWindows(visit,0);return found[0] if found else None
    def show():ui.send(ui.U.GetDlgItem(app.window,BUTTON),0xF5);d=app.wait(dialog);settle(d);return d
    def press(d,id):ui.send(ui.U.GetDlgItem(d,id),0xF5);settle(d);return ui.text(ui.U.GetDlgItem(d,MESSAGE))
    def close(d):ui.send(ui.U.GetDlgItem(d,CLOSE),0xF5);app.wait(lambda:not ui.U.IsWindow(d));app.wait_idle()
    def labels(d):
        box=ui.U.GetDlgItem(d,ROWS);out=[]
        for i in range(ui.send(box,0x18B)):
            n=ui.send(box,0x18A,i);buf=C.create_unicode_buffer(n+1);ui.send(box,0x189,i,C.addressof(buf));out.append(buf.value)
        return out
    def choose(d,value):
        rows=labels(d);i=next(i for i,x in enumerate(rows) if value in x);ui.send(ui.U.GetDlgItem(d,ROWS),0x186,i);ui.send(d,0x111,(1<<16)|ROWS,ui.U.GetDlgItem(d,ROWS))
    def sync():
        d=app.open_account();app.fill(d,root=dav.base+'/dav/',user=user,password=password,remember=False);app.apply(d,'仅本次会话');app.run_sync(d);app.close_account(d)
    def check(value):report['checks'].append(value);print('PASS '+value,flush=True)
    try:
        print('START authenticated HTTPS runner fixture',flush=True)
        dav,user,password=relay.start(a.out,a.previous)
        print('HTTPS ready; launching actual native host',flush=True)
        app=ui.App(exe,font,a.out/'profile');app.wait_initial_shelf();app.wait_idle()
        if a.phase=='windows-first':
            book=a.out/'Record relay.epub';original(book);raw=book.read_bytes();digest=hashlib.sha256(raw).hexdigest()
            report.update(windows_program_sha256=report['program_sha256'],original_sha256=digest,original_bytes=len(raw),book_identity='epub:'+digest,remote_title='Record relay')
            app.import_file(book.resolve());app.wait(lambda:app.has_row('Record relay'));app.open('Record relay');app.wait_idle()
            d=show();ui.M.set_text(ui.U.GetDlgItem(d,BODY),'Windows bookmark');press(d,BOOKMARK);assert any('Windows bookmark' in x for x in labels(d)),labels(d);close(d)
            app.click('select');app.wait_idle();d=show();ui.M.set_text(ui.U.GetDlgItem(d,BODY),'Windows note');press(d,HIGHLIGHT);assert any('Windows note' in x for x in labels(d)),labels(d);close(d)
            records=annotations();assert len(records)==2,records;assert records[0]['payload']['location']['selector']['exact']=='';assert records[1]['payload']['location']['selector']['exact']
            report['raw_records']=records;check('windows_native_ui_creates_bookmark_and_annotation')
            for _ in range(12):app.click('next');app.wait_idle()
            d=show();ui.M.set_text(ui.U.GetDlgItem(d,BODY),'Ambiguous bookmark');press(d,BOOKMARK);assert any('Ambiguous bookmark' in x for x in labels(d)),labels(d)
            choose(d,'Ambiguous bookmark');message=press(d,OPEN);report['ambiguous_message']=message
            assert '歧义' in message or 'ambiguous' in message.lower(),message
            ui.M.screenshot(d,a.out/'ambiguous-record.bmp');close(d);check('ambiguous_actual_record_refuses_navigation_explicitly')
            sync();check('windows_actual_authenticated_upload')
        else:
            previous,_=relay.load(a.previous,'android')
            for k in ('original_sha256','original_bytes','book_identity','remote_title','windows_program_sha256'):report[k]=previous['data'][k]
            assert report['program_sha256']==report['windows_program_sha256'],'Windows binary changed between phases'
            sync();app.wait(lambda:app.has_row(report['remote_title']),timeout=120);app.open(report['remote_title']);app.wait_idle()
            records=annotations();report['raw_records']=records
            for target in ('Windows bookmark','Android edited note','Android new bookmark'):
                d=show();choose(d,target);message=press(d,OPEN)
                assert '独立原书与当前绘图文档' in message,message
                close(d);app.click('select');app.click('copy');text=ui.ACCOUNT.clipboard_text(app)
                expected=next(r for r in previous['data']['outgoing_records'] if r['body']==target)
                selector=expected['exact'] or expected['suffix'];assert selector,expected
                assert selector[:24] in text,(target,selector,text)
                assert 'Relay unique paragraph' in text or 'Distinct reading evidence' in text,text
                ui.M.screenshot(app.window,a.out/(target.replace(' ','-')+'.bmp'))
                report['actual_pages'].append({'record':target,'public_resolver_status':message,'actual_copied_page':text})
            check('windows_receives_android_edit_and_new_bookmark_real_resolution')
            d=show();choose(d,'Ambiguous bookmark');message=press(d,OPEN);assert '歧义' in message or 'ambiguous' in message.lower(),message
            report['ambiguous_message']=message;close(d);check('received_ambiguous_record_refuses_navigation_explicitly')
        before=annotations();sync();after=annotations();assert before==after,'repeat sync appended records';check('repeated_sync_preserves_records_exactly')
        report['raw_records']=after;report['passed']=True;report['transport']='authenticated staged HTTPS; not concurrent online service'
        relay.save(dav,a.out,a.phase,report);dav=None
    except Exception as error:
        report['failure']=str(error);report['traceback']=traceback.format_exc();print(report['traceback'],flush=True)
        if app:
            try:app.diagnose(a.out)
            except Exception:traceback.print_exc()
        raise
    finally:
        (a.out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        if app and app.process.poll() is None:app.process.kill();app.process.wait(timeout=20);app.log.close()
        if dav:
            (a.out/'requests.json').write_text(json.dumps(dav.requests),encoding='utf-8');dav.server.shutdown();dav.server.server_close();(a.out/'key.pem').unlink(missing_ok=True)
if __name__=='__main__':main()
