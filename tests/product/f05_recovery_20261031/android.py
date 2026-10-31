# SPDX-License-Identifier: MIT
"""Actions-only real Android UI offline peer; no synthetic revisions or SDK writers."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import sqlite3
import subprocess
import time
import xml.etree.ElementTree as ET
from fixture import Store

PACKAGE = "org.exreader.host"

def main():
    if os.environ.get("GITHUB_ACTIONS") != "true": raise RuntimeError("Actions only")
    p = argparse.ArgumentParser()
    for name in ("peer", "certificate", "key", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    contract = json.loads((a.peer / "peer-contract.json").read_text())
    user, password = "f05", secrets.token_hex(24)
    auth = "Basic " + base64.b64encode((user + ":" + password).encode()).decode()
    dav = Store(a.certificate, a.key, auth)
    producer = dav.expose_checkpoint(a.peer / contract["baseline"])
    report = {"source":os.environ["GITHUB_SHA"], "run":os.environ["GITHUB_RUN_ID"],
              "attempt":os.environ["GITHUB_RUN_ATTEMPT"], "host":"android",
              "F05_accepted":False, "producer":producer["author"], "cases":[],
              "simultaneous_online_peers":False}
    serial = 0
    def adb(*args, timeout=60):
        return subprocess.check_output(["adb", *map(str,args)], stderr=subprocess.STDOUT, timeout=timeout)
    def shell(*args, timeout=60):
        return adb("shell", shlex.join(list(map(str,args))), timeout=timeout)
    def wait(predicate, seconds=90):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            value = predicate()
            if value: return value
            time.sleep(.2)
        raise TimeoutError("Android actual UI boundary not reached")
    def nodes():
        shell("uiautomator", "dump", "/data/local/tmp/f05-window.xml")
        return [dict(n.attrib) for n in ET.fromstring(adb("exec-out","cat","/data/local/tmp/f05-window.xml")).iter("node")]
    def find(text=None, description=None, contains=False):
        for node in nodes():
            value = node.get("text","") if text is not None else node.get("content-desc","")
            wanted = text if text is not None else description
            if (wanted in value if contains else wanted == value): return node
        return None
    def tap(node):
        coords = list(map(int,re.findall(r"\d+",node.get("bounds",""))))
        if len(coords)!=4 or coords[2]<=coords[0] or coords[3]<=coords[1]:
            raise AssertionError("native UI target not visible")
        shell("input","tap",(coords[0]+coords[2])//2,(coords[1]+coords[3])//2)
    def click(text, contains=False):
        tap(wait(lambda:find(text=text,contains=contains)))
    def field(description,value):
        tap(wait(lambda:find(description=description)))
        shell("input","keycombination","KEYCODE_CTRL_LEFT","KEYCODE_A")
        shell("input","keyevent","KEYCODE_DEL")
        shell("input","text",value.replace(" ","%s"))
    def launch():
        shell("am","start","-W","-n",PACKAGE+"/.MainActivity")
        wait(lambda:find(text="More"))
    def panel():
        click("More");click("同步")
        wait(lambda:find(description="同步状态"))
    def configure():
        panel();click("云盘账号")
        root = find(description="云盘地址")
        if root is None: raise AssertionError("account root control absent")
        if root.get("text", "") not in ("", dav.root):
            raise AssertionError("nonfresh profile points to another server; do not overwrite")
        if not root.get("text"): field("云盘地址",dav.root)
        field("云盘用户名",user);field("云盘密码",password)
        click("仅本次使用")
        wait(lambda:find(description="同步状态"))
    def close_panel():
        shell("input","keyevent","KEYCODE_BACK")
        wait(lambda:find(text="More"))
    def sync():
        start = len(dav.requests)
        click("立即同步")
        wait(lambda:sum(r["method"]=="PROPFIND" and "/revisions/" in r["path"]
                        for r in dav.requests[start:]) >= 256,180)
        state = wait(lambda:find(description="同步状态"),30)
        def completed():
            node=find(description="同步状态")
            return node if node is not None and ("本轮同步结束" in node.get("text","")
                or "书架有冲突" in node.get("text","")) else None
        state=wait(completed,180)
        return state.get("text","")
    def group_edit(old,new):
        click("More");click("Organize");click("Kind");click("Tags")
        click(old);click("Edit");field("Name",new);click("Save")
        wait(lambda:find(text=new))
        click("Close");wait(lambda:find(text="More"))
    def snapshot(label):
        # Copy only known catalog files, not credentials; two stable reads avoid
        # treating an in-flight WAL copy as a coherent product observation.
        nonlocal serial
        def read_files():
            result={}
            for name in ("reader-catalog.db","reader-catalog.db-wal"):
                proc=subprocess.run(["adb","exec-out","run-as",PACKAGE,"cat","files/"+name],
                    capture_output=True,timeout=20)
                if proc.returncode==0: result[name]=proc.stdout
                elif name.endswith(".db"): raise AssertionError("actual product catalog missing")
            return result
        data=None
        for _ in range(10):
            first=read_files();time.sleep(.1);second=read_files()
            if first==second:data=first;break
        if data is None: raise AssertionError("catalog observation unstable")
        folder=a.output/(str(serial)+"-"+label);serial+=1;folder.mkdir()
        for name,body in data.items():(folder/name).write_bytes(body)
        with sqlite3.connect((folder/"reader-catalog.db").resolve().as_uri()+"?mode=ro",uri=True) as db:
            rows=[json.loads(x[0]) for x in db.execute("SELECT body_json FROM reader_revisions")]
            pending=db.execute("SELECT count(*) FROM reader_outbox").fetchone()[0]
        selected=[r for r in rows if r["entity_kind"]==contract["entity_kind"]
                  and r["entity_key"]==contract["entity_key"]]
        heads={r["id"] for r in selected}-{q for r in selected for q in r["parents"]}
        return {"records":selected,"heads":sorted(heads),"outbox":pending,
                "files":{k:hashlib.sha256(v).hexdigest() for k,v in data.items()}}
    def sdk_snapshot(label):
        nonlocal serial
        def read():
            values={}
            for name in ("library.db","library.db-wal"):
                proc=subprocess.run(["adb","exec-out","run-as",PACKAGE,"cat","files/"+name],
                    capture_output=True,timeout=20)
                if proc.returncode==0:values[name]=proc.stdout
                elif name=="library.db":raise AssertionError("SDK library absent")
            return values
        values=None
        for _ in range(10):
            before=read();time.sleep(.1);after=read()
            if before==after:values=before;break
        if values is None:raise AssertionError("SDK readonly observation unstable")
        folder=a.output/(str(serial)+"-sdk-"+label);serial+=1;folder.mkdir()
        for name,body in values.items():(folder/name).write_bytes(body)
        with sqlite3.connect((folder/"library.db").resolve().as_uri()+"?mode=ro",uri=True) as db:
            books=[{"id":row[0],"source_bytes":len(row[1]),
                    "source_sha256":hashlib.sha256(row[1]).hexdigest()}
                   for row in db.execute("SELECT id,source FROM books ORDER BY id")]
        return {"books":books,"count":len(books),"observation":"stable copied SDK DB read-only"}
    try:
        # CI supplies a fresh emulator/APK whose trust includes this test CA.
        # Do not silently clear an existing caller's profile.
        adb("reverse","tcp:"+str(dav.server.server_port),"tcp:"+str(dav.server.server_port))
        launch();configure();sync()
        book_rows=[json.loads(body) for path,body in dav.entries.items()
                   if "/revisions/" in path and json.loads(body)["entity_kind"]=="book"]
        book_parents={parent for row in book_rows for parent in row["parents"]}
        selected=[row for row in book_rows if row["id"] not in book_parents]
        if len(selected)!=1:raise AssertionError("receive cancellation needs one safe actual book")
        title=selected[0]["payload"]["title"]
        original=selected[0]["payload"]
        leaf=original["source_sha256"]+"."+original["format"]
        if not re.fullmatch(r"[0-9a-f]{64}\\.[a-z0-9]+",leaf):
            raise AssertionError("invalid fixed original cache identity")
        cache="files/sync-cache/"+leaf
        body=adb("exec-out","run-as",PACKAGE,"cat",cache)
        if len(body)!=original["source_bytes"] or hashlib.sha256(body).hexdigest()!=original["source_sha256"]:
            raise AssertionError("cache fault requires verified exact original identity")
        idle=find(description="同步状态")
        if idle is None or "本轮同步结束" not in idle.get("text",""):
            raise AssertionError("cache quarantine requires idle completed native owner")
        quarantine="files/f05-cache-quarantine-"+secrets.token_hex(12)
        shell("run-as",PACKAGE,"mkdir",quarantine)
        before_stat=adb("exec-out","run-as",PACKAGE,"stat","-c","%i:%s:%a",cache).decode().strip()
        shell("run-as",PACKAGE,"mv",cache,quarantine+"/"+leaf)
        after_stat=adb("exec-out","run-as",PACKAGE,"stat","-c","%i:%s:%a",quarantine+"/"+leaf).decode().strip()
        retained=adb("exec-out","run-as",PACKAGE,"cat",quarantine+"/"+leaf)
        if before_stat!=after_stat or retained!=body:
            raise AssertionError("cache quarantine was not same identity atomic rename")
        (a.output/"quarantined-cache.bin").write_bytes(retained)
        report["cache_fault"]={"path":cache,"quarantine":quarantine+"/"+leaf,
            "before_stat":before_stat,"after_stat":after_stat,"bytes":len(body),
            "sha256":hashlib.sha256(body).hexdigest(),"owner_idle_native_state":idle["text"],
            "sdk_original_untouched":True,"restored_before_retry":False}
        sdk_before=sdk_snapshot("before-cancel")
        dav.hold_get=True;dav.get_blocked.clear();dav.release.clear()
        click(title,contains=True);click("接收")
        if not dav.get_blocked.wait(30):
            raise AssertionError("real original receive did not reach GET boundary")
        click("取消同步")
        dav.release.set()
        wait(lambda:find(text="已取消",contains=True))
        sdk_cancelled=sdk_snapshot("cancelled")
        if sdk_cancelled["books"]!=sdk_before["books"]:
            raise AssertionError("cancel before original GET changed SDK originals")
        click(title,contains=True);click("接收")
        wait(lambda:find(text="书籍已接收",contains=True),120)
        sdk_retry=sdk_snapshot("retry")
        matches=[b for b in sdk_retry["books"] if b["source_sha256"]==original["source_sha256"]
                 and b["source_bytes"]==original["source_bytes"]]
        if len(matches)!=1 or sdk_retry["count"]!=sdk_before["count"]+1:
            raise AssertionError("actual retry did not import exactly one exact SDK original")
        click(title,contains=True);click("接收")
        wait(lambda:find(text="书籍已接收",contains=True),120)
        sdk_duplicate=sdk_snapshot("duplicate-receive")
        if sdk_duplicate["books"]!=sdk_retry["books"]:
            raise AssertionError("duplicate receive changed exact SDK original set")
        report["cases"].append({"name":"cancel_receive_retry","outcome":"passed",
            "actual_original_get_blocked":True,"native_cancel_clicked":True,
            "retry_native_state":"书籍已接收","original_key":selected[0]["entity_key"],
            "sdk_before":sdk_before,"sdk_cancelled":sdk_cancelled,
            "sdk_retry":sdk_retry,"sdk_duplicate":sdk_duplicate})
        close_panel()
        before=snapshot("baseline")
        if set(before["heads"])!=set(contract["common_parent"]):
            raise AssertionError("actual receiver lacks common native ancestor")
        dav.offline=True
        group_edit("F05 shared tag","F05 Android offline")
        local=snapshot("offline")
        if local["outbox"]<1 or local["heads"]==before["heads"]:
            raise AssertionError("native offline edit absent")
        dav.offline=False
        dav.hold_put=True;dav.put_committed.clear();dav.release.clear()
        panel();click("立即同步")
        if not dav.put_committed.wait(45):
            raise AssertionError("native local revision did not reach uncertain PUT ack boundary")
        killed=shell("pidof",PACKAGE).decode().strip()
        committed=dict(dav.entries)
        shell("am","force-stop",PACKAGE)
        dav.release.set()
        launch();configure();sync();close_panel()
        recovered=snapshot("uncertain-ack-retry")
        if recovered["outbox"] or any(dav.entries.get(k)!=v for k,v in committed.items()):
            raise AssertionError("kill/retry lost queued identity or rewrote committed bytes")
        reopened=shell("pidof",PACKAGE).decode().strip()
        if killed==reopened:raise AssertionError("actual process was not replaced")
        report["cases"].append({"name":"kill_commit_ack_replay","outcome":"passed",
            "terminated_pid":killed,"reopened_pid":reopened,"before":local,"after":recovered,
            "committed_wire_unchanged":True})
        # Publish only the real GTK deletion. A's new local branch is causally
        # concurrent because it was authored before this immutable branch exposure.
        remote=dav.expose_checkpoint(a.peer/contract["remote_delete"])
        dav.offline=False
        panel();status=sync()
        if "冲突" not in status: raise AssertionError("native conflict status missing")
        (a.output/"conflict.png").write_bytes(adb("exec-out","screencap","-p"))
        close_panel();after=snapshot("concurrent")
        if not set(local["heads"]).issubset(after["heads"]) or len(after["heads"])<2:
            raise AssertionError("offline local branch lost after reconnect")
        deleted=[r for r in after["records"] if r["operation"]=="delete"]
        if not deleted or not any(r["id"] in after["heads"] for r in deleted):
            raise AssertionError("actual deletion head lost")
        if any(r["operation"]=="restore" for r in after["records"]):
            raise AssertionError("ordinary concurrent put became implicit restore")
        report["cases"].append({"name":"offline_reconnect_delete_put",
            "outcome":"partial","preservation_passed":True,"deletion_conflict_ui_detail":False,"before":before,"offline":local,"after":after,
            "native_conflict_text":status,"peer_author":remote["author"]})
        dav.offline=True
        offline_requests=len(dav.requests)
        pid=shell("pidof",PACKAGE).decode().strip()
        shell("am","force-stop",PACKAGE)
        launch()
        restarted=snapshot("restart")
        if restarted["heads"]!=after["heads"]:
            raise AssertionError("retained conflict changed after process restart")
        click(title,contains=True)
        page=wait(lambda:next((n for n in nodes() if n.get("class")=="org.exreader.host.ReaderView"
            and n.get("content-desc","").startswith("Reading page 1.")),None),120)
        rendered=nodes()
        if not any("F05 GTK original" in n.get("content-desc","") or
                   "F05 GTK original" in n.get("text","") for n in rendered):
            raise AssertionError("offline original text not present in native reading nodes")
        if len(dav.requests)!=offline_requests:
            raise AssertionError("offline original reopening attempted network")
        (a.output/"offline-reader.png").write_bytes(adb("exec-out","screencap","-p"))
        report["cases"].append({"name":"restart_offline_read","outcome":"passed",
            "reader":page,"rendered_nodes":rendered,
            "sdk_originals":sdk_snapshot("offline-original"),"network_requests":0})
        report["cases"].append({"name":"restart_preserves_conflict","outcome":"passed",
            "terminated_pid":pid,"reopened_pid":shell("pidof",PACKAGE).decode().strip(),
            "after":restarted})
    except BaseException as error:
        safe = repr(error).replace(password, "<generated-fixture-secret>").replace(auth, "<generated-fixture-auth>")
        report["failure"]=safe
        raise RuntimeError(safe) from None
    finally:
        report["requests"]=dav.requests
        report["uncovered"]=["actual original offline reopening","independent artifact authentication"]
        (a.output/"coverage.json").write_text(json.dumps(report,indent=2)+"\n")
        dav.close()
        adb("reverse","--remove","tcp:"+str(dav.server.server_port))

if __name__=="__main__":main()
