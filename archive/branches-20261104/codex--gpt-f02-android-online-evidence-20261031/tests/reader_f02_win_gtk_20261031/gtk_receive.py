#!/usr/bin/env python3
import configparser, json, os, shutil, sqlite3, subprocess, sys, tempfile, time
from pathlib import Path
from dav_store import BASE, Store, identity, need, save, sha
sys.path.insert(0,str(BASE/"tools"))
from check_linux_host import Session, command
OUT=BASE/"build/f02-gtk"
def main():
    need(os.environ.get("GITHUB_ACTIONS")=="true" and sys.platform.startswith("linux"),"Linux Actions only")
    OUT.mkdir(parents=True,exist_ok=True)
    incoming=BASE/"build/f02-input";sender=json.loads((incoming/"report.json").read_text())
    need(sender["accepted"] is True and sender["identity"]==identity(),"sender identity")
    store=None;checks=[];host=None
    private=tempfile.TemporaryDirectory(prefix="f02-gtk-");work=Path(private.name);hostfolder=work/"receiver";hostfolder.mkdir()
    payload=BASE/"build/gtk-raw-wave3/retained-package/EXReader-Linux"
    binary=payload/"bin/exreader-linux";inspector=BASE/"build/f02-inspector/received-sdk-inspect"
    key=sender["book_key"];title=sender["title"]
    report=dict(identity=identity(),accepted=False,checks=checks,book_key=key,original_bytes=sender["original_bytes"],
       original_sha256=sender["original_sha256"],sdk_version="3.42.0",
       sender_artifact=json.loads((BASE/"build/f02-fetch/receipt.json").read_text()),F02_accepted=False)
    def record(name):
        need(name not in checks,"duplicate check");checks.append(name);print("F02_GTK_CHECK "+name,flush=True)
    def sql(query,params=()):
        with sqlite3.connect(hostfolder/"profile/library.sqlite.product.sqlite",timeout=10) as conn:return conn.execute(query,params).fetchall()
    def account():
        ini=configparser.ConfigParser(interpolation=None);ini.read(host.observe)
        return dict(ini["account"]) if ini.has_section("account") else {}
    def ready(predicate,seconds=180):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            need(host.process.poll() is None,"GTK process exited")
            s=account()
            if s and not int(s.get("owner_busy","0")) and not int(s.get("preparing","0")) and not host.read().get("busy") and predicate(s):return s
            time.sleep(.1)
        raise TimeoutError("GTK account condition timeout")
    def window():
        end=time.monotonic()+30
        while time.monotonic()<end:
            p=subprocess.run(["xdotool","search","--onlyvisible","--all","--pid",str(host.process.pid),"--name","^Account and Sync$"],capture_output=True,text=True,timeout=5)
            if p.stdout.strip():
                w=p.stdout.splitlines()[-1];command("xdotool","windowactivate","--sync",w);return w
            time.sleep(.1)
        raise TimeoutError("GTK actual account dialog missing")
    def open_account():
        command("xdotool","windowactivate","--sync",host.window);host.key("F2","ctrl+shift+a")
        window();return ready(lambda s:s["visible"]=="1")
    def field(letter,value):
        window();host.key("alt+"+letter,"ctrl+a");host.paste(value)
    def search_open():
        command("xdotool","windowactivate","--sync",host.window)
        previous=host.read()["shelf_queries"];host.key("ctrl+f","ctrl+a");host.paste(title)
        host.wait(lambda s:s["shelf_queries"]>previous and not s["shelf_loading"] and not s["shelf_restoring"] and s["books"]==1,timeout=60)
        host.key("F2","Home","Return")
    try:
        store=Store(incoming)
        report.update(executable_sha256=sha(binary.read_bytes()),sdk_inspector_sha256=sha(inspector.read_bytes()))
        host=Session(binary.resolve(),(payload/"Reader.otf").resolve(),hostfolder)
        host.launch()
        need(sql("SELECT count(*) FROM reader_books")==[(0,)] and sql("SELECT count(*) FROM reader_local_books")==[(0,)],"receiver not fresh")
        record("receiver_starts_with_empty_independent_product_mapping")
        shutil.copyfile(binary,OUT/"host.bin");shutil.copyfile(inspector,OUT/"sdk-inspector.bin")
        shutil.copyfile(BASE/"build/gtk-raw-wave3/retained-host/CMakeCache.txt",OUT/"CMakeCache.txt")
        open_account();field("w",store.root);field("u",store.user);field("p",store.password)
        host.key("alt+h");host.key("alt+a")
        ready(lambda s:s.get("bound")=="1" and s.get("has_password")=="1")
        window();host.key("alt+s");ready(lambda s:s.get("session_state")=="4")
        need(sql("SELECT count(*) FROM reader_local_books")==[(0,)],"scan implicitly imported")
        for rev in sender["book_revisions"]:
            row=sql("SELECT body_json FROM reader_revisions WHERE revision_id=?",(rev["id"],))
            need(len(row)==1 and sha(row[0][0].encode())==rev["sha256"],"received wire hash")
        record("actual_HTTPS_scan_receives_sender_exact_wire_without_local_import")
        window();host.key("alt+r");ready(lambda s:s.get("phase")=="0" and s.get("projection_status")=="0" and sql("SELECT title FROM reader_books WHERE book_key=?",(key,))==[(title,)])
        need(sql("SELECT title FROM reader_books WHERE book_key=?",(key,))==[(title,)],"projected book missing")
        need(sql("SELECT sdk_book_id FROM reader_local_books WHERE book_key=?",(key,))==[],"projected row already imported")
        window();host.key("alt+F4");ready(lambda s:s["visible"]=="0" and s["session_present"]=="0")
        record("explicit_native_receive_projects_cloud_book_without_fake_sdk_mapping")
        search_open()
        def mapped():return sql("SELECT sdk_book_id FROM reader_local_books WHERE book_key=?",(key,))
        ready(lambda s:s["visible"]=="0" and mapped() and int(s["imported_book"])==mapped()[0][0])
        sdk_id=mapped()[0][0]
        host.wait(lambda s:s["book"]==sdk_id and s["reader_visible"]==1 and not s["saving"] and not s["error"],timeout=90)
        frame=host.read();command("import","-window",host.window,OUT/"01-receiver-open.png")
        report.update(receiver_sdk_id=sdk_id,first_open=frame)
        record("real_shelf_activation_downloads_imports_and_opens_mapped_book")
        entries,events=store.snapshot(OUT)
        need(any(e["method"]=="GET" and e["path"]==sender["object_path"] and e["status"]==200 and e["response_sha256"]==sender["original_sha256"] and e["response_bytes"]==sender["original_bytes"] for e in events),"missing actual original GET")
        record("server_records_exact_original_response_for_actual_GET")
        host.close()
        out=OUT/"sdk-original.txt"
        p=subprocess.run([str(inspector),str(hostfolder/"profile/library.sqlite"),str(sdk_id),str(out)],capture_output=True,text=True,timeout=60)
        need(p.returncode==0,"receiver installed SDK readback")
        readback=json.loads(p.stdout)
        need(readback["book"]==sdk_id and len(out.read_bytes())==sender["original_bytes"] and sha(out.read_bytes())==sender["original_sha256"],"receiver retained bytes")
        report["sdk_readback"]=readback;report["sdk_original_sha256"]=sha(out.read_bytes())
        record("closed_receiver_public_SDK_retained_original_matches_sender")
        store.stop();before=len(store.events)
        cache=hostfolder/"profile/sync-work"
        if cache.exists():
            for path in cache.iterdir():
                if path.is_file() and not path.is_symlink():path.unlink()
        host.launch();search_open()
        host.wait(lambda s:s["book"]==sdk_id and s["reader_visible"]==1 and not s["error"],timeout=90)
        need(len(store.events)==before,"offline reopen made server request")
        command("import","-window",host.window,OUT/"02-offline-reopen.png")
        report["offline_open"]=host.read()
        record("new_process_reopens_same_SDK_book_with_server_stopped_and_download_cache_removed")
        host.close()
        report.update(accepted=True,count=len(checks));save(OUT/"report.json",report)
        store.no_secrets(OUT)
        print("F02_GTK "+json.dumps(report,ensure_ascii=False),flush=True)
    except Exception as exc:
        report.update(accepted=False,error_type=type(exc).__name__,stage="native_transfer",count=len(checks))
        save(OUT/"report.json",report);raise
    finally:
        try:
            if host and host.process and host.process.poll() is None:host.close()
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
