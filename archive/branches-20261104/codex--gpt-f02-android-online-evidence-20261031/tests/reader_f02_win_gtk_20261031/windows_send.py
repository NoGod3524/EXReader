#!/usr/bin/env python3
import importlib.util, json, os, shutil, sqlite3, subprocess, sys, tempfile
from pathlib import Path
from dav_store import BASE, Store, body, identity, need, save, sha
sys.path.insert(0,str(BASE/"tests/reader_windows_account"))
import check_account_ui as A
sys.path.insert(0,str(BASE/"tests/reader_windows_compact"))
spec=importlib.util.spec_from_file_location("f02_compact_driver",BASE/"tests/reader_windows_compact/check_ui.py")
compact=importlib.util.module_from_spec(spec);spec.loader.exec_module(compact)
OUT=BASE/"build/f02-windows"
def main():
    need(os.environ.get("GITHUB_ACTIONS")=="true" and os.name=="nt","Windows Actions only")
    OUT.mkdir(parents=True,exist_ok=True);checks=[]
    def record(name):
        need(name not in checks,"duplicate check");checks.append(name)
        print("F02_WINDOWS_CHECK "+name,flush=True)
    binary=BASE/"build/windows-sdk342/package/EXReader/EXReader.exe"
    font=BASE/"build/windows-sdk342/package/EXReader/Reader.otf"
    inspector=BASE/"build/f02-inspector/received-sdk-inspect.exe"
    private=tempfile.TemporaryDirectory(prefix="f02-windows-");work=Path(private.name)
    source=work/"F02 Original.txt";source.write_bytes(body());store=None;device=None
    report=dict(identity=identity(),accepted=False,checks=checks,book_key="txt:"+sha(body()),original_bytes=len(body()),original_sha256=sha(body()),
                sdk_version="3.42.0",F02_accepted=False)
    try:
        store=Store()
        report.update(executable_sha256=sha(binary.read_bytes()),sdk_inspector_sha256=sha(inspector.read_bytes()))
        device=A.Device(binary.resolve(),font.resolve(),work/"profile")
        db=work/"profile/library.sqlite.product.sqlite"
        def sql(query,params=()):
            with sqlite3.connect(db,timeout=10) as conn:return conn.execute(query,params).fetchall()
        need(sql("SELECT count(*) FROM reader_books")==[(0,)],"sender profile not empty")
        compact.picker(device,source)
        device.wait(lambda: "已导入" in device.status() or "去重" in device.status(),timeout=180)
        device.wait_idle()
        rows=sql("SELECT b.book_key,b.title,l.sdk_book_id FROM reader_books b JOIN reader_local_books l USING(book_key)")
        need(len(rows)==1 and rows[0][0]==report["book_key"],"native import mapping")
        key,title,sdk_id=rows[0];need(type(sdk_id) is int and sdk_id>0,"sender sdk id")
        report.update(sender_sdk_id=sdk_id,title=title)
        record("native_picker_imports_exact_original_and_creates_book_key_mapping")
        device.open(title);device.wait(lambda:A.U.IsWindowVisible(device.control("page")))
        A.M.screenshot(device.window,OUT/"01-sender-open.bmp")
        record("actual_sender_reader_visible")
        dialog=device.open_account();device.fill(dialog,store.root,store.user,store.password,False)
        device.press(dialog,A.APPLY);device.wait(lambda:device.enabled(dialog,A.SYNC),timeout=120)
        device.run_sync(dialog,timeout=240);device.close_account(dialog)
        record("actual_account_sync_completes")
        shutil.copyfile(binary,OUT/"host.exe");shutil.copyfile(inspector,OUT/"sdk-inspector.exe")
        shutil.copyfile(BASE/"build/windows-sdk342/host/CMakeCache.txt",OUT/"CMakeCache.txt")
        device.close();need(device.process.returncode==0,"sender unclean exit")
        inspect=work/"sender.original"
        done=subprocess.run([str(inspector),str(work/"profile/library.sqlite"),str(sdk_id),str(inspect)],capture_output=True,text=True,timeout=60)
        need(done.returncode==0,"sender public SDK readback")
        readback=json.loads(done.stdout);need(readback["book"]==sdk_id and inspect.read_bytes()==body(),"sender SDK bytes")
        report["sdk_readback"]=readback;report["sdk_original_sha256"]=sha(inspect.read_bytes())
        record("closed_sender_installed_sdk_original_matches_input")
        store.stop();entries,events=store.snapshot(OUT)
        object_path="/dav/exreader-sync-v1/objects/"+sha(body())[:2]+"/"+sha(body())+".txt"
        need(entries.get(object_path)==body(),"actual PUT stored original")
        need(any(e["method"]=="PUT" and e["path"]==object_path and e["status"]==201 and e["request_sha256"]==sha(body()) and e["request_bytes"]==len(body()) for e in events),"missing real object PUT")
        need(all(e["authenticated"] for e in events),"unauthenticated request")
        record("server_stored_original_is_exact_authenticated_PUT_body")
        revision_records=[]
        for path,data in entries.items():
            if "/revisions/" not in path:continue
            value=json.loads(data)
            if value.get("entity_kind")=="book" and value.get("entity_key")==key:
                payload=value["payload"]
                need(payload["source_sha256"]==sha(body()) and payload["source_bytes"]==len(body()) and payload["format"]=="txt","book wire identity")
                need(any(e["method"]=="PUT" and e["path"]==path and e["status"]==201 and e["request_sha256"]==sha(data) for e in events),"revision was not PUT")
                revision_records.append(dict(id=value["id"],path=path,sha256=sha(data)))
        need(revision_records,"missing host-produced book revision")
        report.update(book_revisions=revision_records,object_path=object_path,accepted=True,count=len(checks))
        record("host_produced_book_revision_binds_original_hash_and_size")
        report["count"]=len(checks);save(OUT/"report.json",report)
        store.no_secrets(OUT)
        print("F02_WINDOWS "+json.dumps(report,ensure_ascii=False),flush=True)
    except Exception as exc:
        report.update(accepted=False,error_type=type(exc).__name__,stage="native_transfer",count=len(checks))
        save(OUT/"report.json",report);raise
    finally:
        try:
            if device and device.process and device.process.poll() is None:device.close()
        finally:
            try:
                if store is not None:store.authorize_upload(OUT)
            finally:
                try:
                    if store is not None:store.close()
                finally:private.cleanup()
if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("F02_FAILED stage=native_transfer error_type="+type(exc).__name__,flush=True)
        sys.exit(1)
