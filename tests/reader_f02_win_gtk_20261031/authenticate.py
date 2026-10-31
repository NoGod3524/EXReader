#!/usr/bin/env python3
"""F02 source guard, authenticated same-attempt transfer and independent proof."""
import argparse, copy, hashlib, io, json, os, re, stat, subprocess, sys, zipfile
from pathlib import Path, PurePosixPath
from dav_store import BASE, identity, need, save, sha
def unique(pairs):
    out={}
    for k,v in pairs:
        need(k not in out,"duplicate_json_key");out[k]=v
    return out
def load(data):return json.loads(data,object_pairs_hook=unique)
def api(path):
    return load(subprocess.check_output(["gh","api","repos/NoGod3524/EXReader/"+path],timeout=90))
def guard():
    lock=load((Path(__file__).parent/"source_lock.json").read_bytes())
    actual=subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()
    need(actual==os.environ["GITHUB_SHA"],"source")
    subprocess.run(["git","merge-base","--is-ancestor",lock["base"],"HEAD"],check=True)
    changed=set(subprocess.check_output(["git","diff","--name-only",lock["base"],"HEAD"],text=True).splitlines())
    need(changed==set(lock["owned"]),"seven additive files")
    for path,expected in lock["frozen"].items():
        got=subprocess.check_output(["git","rev-parse","HEAD:"+path],text=True).strip()
        need(got==expected,"frozen:"+path)
    print("F02_SCOPE exact7 frozen SDK/product/old driver verified")
def unpack(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        infos=z.infolist();need(0<len(infos)<=5000,"zip count")
        names=set();norms=set();total=0
        for i in infos:
            p=PurePosixPath(i.filename);n=str(p).casefold()
            need(i.filename and not p.is_absolute() and ".." not in p.parts and "\\" not in i.filename and ":" not in i.filename,"zip path")
            need(i.filename not in names and n not in norms,"zip duplicate")
            names.add(i.filename);norms.add(n)
            need(stat.S_IFMT(i.external_attr>>16) in (0,stat.S_IFREG,stat.S_IFDIR) and not i.flag_bits&1,"zip kind")
            total+=i.file_size
            need(i.file_size<=64*1024*1024 and total<=128*1024*1024,"zip budget")
        return {i.filename:z.read(i) for i in infos if not i.is_dir()}
def fetch(aid,name,out,label):
    run=api("actions/runs/"+str(identity()["run"]))
    need(run["head_sha"]==identity()["source"] and run["run_attempt"]==identity()["attempt"],"run identity")
    meta=api("actions/artifacts/"+str(aid))
    expected=name+"-"+str(identity()["run"])+"-"+str(identity()["attempt"])
    need(meta["id"]==aid and meta["name"]==expected and meta["expired"] is False,"artifact identity")
    need(meta["workflow_run"]["id"]==identity()["run"] and meta["workflow_run"]["head_sha"]==identity()["source"],"artifact source")
    need(0<meta["size_in_bytes"]<=64*1024*1024 and re.fullmatch("sha256:[0-9a-f]{64}",meta.get("digest","")),"artifact budget")
    receipt=BASE/("build/f02-fetch"+("-"+label if label else ""));receipt.mkdir(parents=True,exist_ok=True)
    path=receipt/"original.zip"
    with path.open("wb") as stream:
        subprocess.run(["gh","api","repos/NoGod3524/EXReader/actions/artifacts/"+str(aid)+"/zip"],stdout=stream,check=True,timeout=180)
    data=path.read_bytes();need(len(data)==meta["size_in_bytes"] and sha(data)==meta["digest"].split(":")[1],"ZIP identity")
    files=unpack(data);out=Path(out);out.mkdir(parents=True,exist_ok=False)
    for name,body in files.items():
        p=out/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(body)
    proof=dict(artifact_id=aid,artifact_name=meta["name"],bytes=len(data),sha256=sha(data),identity=identity())
    save(receipt/"receipt.json",proof)
    return files,proof
def verify_sender(f):
    s=load(f["report.json"]);need(s["identity"]==identity() and s["accepted"] is True,"sender identity")
    need(s["count"]==6 and s["checks"]==["native_picker_imports_exact_original_and_creates_book_key_mapping","actual_sender_reader_visible","actual_account_sync_completes","closed_sender_installed_sdk_original_matches_input","server_stored_original_is_exact_authenticated_PUT_body","host_produced_book_revision_binds_original_hash_and_size"],"sender checks")
    need(s["sdk_version"]=="3.42.0" and sha(f["host.exe"])==s["executable_sha256"],"sender binary")
    need(sha(f["sdk-inspector.exe"])==s["sdk_inspector_sha256"],"sender inspector")
    need(s["book_key"]=="txt:"+s["original_sha256"],"book identity")
    need(type(s["sender_sdk_id"]) is int and s["sender_sdk_id"]>0 and s["sdk_readback"]["book"]==s["sender_sdk_id"],"sender mapping")
    need(s["sdk_original_sha256"]==s["original_sha256"],"sender readback")
    store=load(f["store.json"]);need(store["identity"]==identity(),"store identity")
    entries={}
    for item in store["entries"]:
        need(item["path"] not in entries and re.fullmatch("[0-9a-f]{64}",item["sha256"]),"store inventory")
        b=f["objects/"+item["sha256"]];need(len(b)==item["bytes"] and sha(b)==item["sha256"],"store body")
        entries[item["path"]]=b
    original=entries[s["object_path"]]
    need(len(original)==s["original_bytes"] and sha(original)==s["original_sha256"],"uploaded original")
    events=load(f["events.json"])
    need(all(e["authenticated"] is True and e["seq"]==i+1 for i,e in enumerate(events)),"sender request sequence")
    need(any(e["method"]=="PUT" and e["path"]==s["object_path"] and e["status"]==201 and e["request_sha256"]==s["original_sha256"] and e["request_bytes"]==s["original_bytes"] for e in events),"actual PUT")
    need(s["book_revisions"],"book revisions")
    for row in s["book_revisions"]:
        b=entries[row["path"]];v=load(b)
        need(sha(b)==row["sha256"] and v["id"]==row["id"] and v["entity_kind"]=="book" and v["entity_key"]==s["book_key"],"wire identity")
        need(v["payload"]["source_sha256"]==s["original_sha256"] and v["payload"]["source_bytes"]==s["original_bytes"] and v["payload"]["format"]=="txt","wire source")
        need(any(e["method"]=="PUT" and e["path"]==row["path"] and e["status"]==201 and e["request_sha256"]==sha(b) for e in events),"actual revision PUT")
    return s
def compare(s,f,sender_receipt):
    r=load(f["report.json"]);need(r["identity"]==identity() and r["accepted"] is True,"receiver identity")
    need(r["count"]==7 and r["checks"]==["receiver_starts_with_empty_independent_product_mapping","actual_HTTPS_scan_receives_sender_exact_wire_without_local_import","explicit_native_receive_projects_cloud_book_without_fake_sdk_mapping","real_shelf_activation_downloads_imports_and_opens_mapped_book","server_records_exact_original_response_for_actual_GET","closed_receiver_public_SDK_retained_original_matches_sender","new_process_reopens_same_SDK_book_with_server_stopped_and_download_cache_removed"],"receiver checks")
    need(r["sender_artifact"]==sender_receipt,"transfer artifact")
    need(r["sdk_version"]=="3.42.0" and sha(f["host.bin"])==r["executable_sha256"],"receiver binary")
    need(sha(f["sdk-inspector.bin"])==r["sdk_inspector_sha256"],"receiver inspector")
    need(r["book_key"]==s["book_key"] and r["original_sha256"]==s["original_sha256"] and r["original_bytes"]==s["original_bytes"],"cross-host key")
    need(type(r["receiver_sdk_id"]) is int and r["receiver_sdk_id"]>0 and r["sdk_readback"]["book"]==r["receiver_sdk_id"],"receiver mapping")
    need(sha(f["sdk-original.txt"])==s["original_sha256"] and len(f["sdk-original.txt"])==s["original_bytes"] and r["sdk_original_sha256"]==s["original_sha256"],"SDK original")
    for name in ("first_open","offline_open"):
        frame=r[name]
        need(frame["book"]==r["receiver_sdk_id"] and frame["reader_visible"]==1 and not frame["error"],"actual open")
    events=load(f["events.json"])
    need(all(e["authenticated"] is True and e["seq"]==i+1 for i,e in enumerate(events)),"receiver request sequence")
    need(any(e["method"]=="GET" and e["path"]==s["object_path"] and e["status"]==200 and e["response_sha256"]==s["original_sha256"] and e["response_bytes"]==s["original_bytes"] for e in events),"actual GET")
    need(r["F02_accepted"] is False and s["F02_accepted"] is False,"scope")
    return r
def controls(s,w,g,receipt):
    tests=[]
    def altered(files,name,fn):
        result=dict(files);v=load(result[name]);fn(v);result[name]=json.dumps(v).encode();return result
    cases=[
      ("sender-source",lambda:verify_sender(altered(w,"report.json",lambda d:d["identity"].update(source="0"*40)))),
      ("sender-PUT",lambda:verify_sender(altered(w,"events.json",lambda d:d.clear()))),
      ("wire-hash",lambda:verify_sender(altered(w,"report.json",lambda d:d["book_revisions"][0].update(sha256="0"*64)))),
      ("receiver-attempt",lambda:compare(s,altered(g,"report.json",lambda d:d["identity"].update(attempt=999)),receipt)),
      ("receiver-key",lambda:compare(s,altered(g,"report.json",lambda d:d.update(book_key="txt:"+"0"*64)),receipt)),
      ("receiver-GET",lambda:compare(s,altered(g,"events.json",lambda d:d.clear()),receipt)),
      ("receiver-SDK-bytes",lambda:compare(s,dict(g,**{"sdk-original.txt":b"changed"}),receipt)),
      ("receiver-open",lambda:compare(s,altered(g,"report.json",lambda d:d["first_open"].update(reader_visible=0)),receipt))]
    reasons=["sender identity","actual PUT","wire identity","receiver identity","cross-host key","actual GET","SDK original","actual open"]
    for (name,call),reason in zip(cases,reasons):
        try:call()
        except AssertionError as exc:
            need(str(exc)==reason,"wrong rejection:"+name)
            tests.append(dict(name=name,refused=True,reason=str(exc)))
        else:raise AssertionError("negative accepted:"+name)
    return dict(positive=1,negative=8,results=tests)
def main():
    need(os.environ.get("GITHUB_ACTIONS")=="true","Actions only")
    p=argparse.ArgumentParser();p.add_argument("mode",choices=["guard","fetch","verify"])
    p.add_argument("--id",type=int);p.add_argument("--name");p.add_argument("--out")
    p.add_argument("--windows-id",type=int);p.add_argument("--gtk-id",type=int);a=p.parse_args()
    if a.mode=="guard":return guard()
    if a.mode=="fetch":
        f,receipt=fetch(a.id,a.name,a.out,"")
        verify_sender(f);return
    out=BASE/"build/f02-auth";out.mkdir(parents=True,exist_ok=True)
    try:
        w,receipt=fetch(a.windows_id,"f02-windows",BASE/"build/f02-auth-windows","windows")
        g,greceipt=fetch(a.gtk_id,"f02-gtk",BASE/"build/f02-auth-gtk","gtk")
        jobs=api("actions/runs/"+str(identity()["run"])+"/attempts/"+str(identity()["attempt"])+"/jobs?per_page=100")["jobs"]
        for name in ("windows","gtk"):
            match=[j for j in jobs if j["name"]==name]
            need(len(match)==1 and match[0]["conclusion"]=="success","upstream job:"+name)
        s=verify_sender(w);r=compare(s,g,receipt);checked=controls(s,w,g,receipt)
        save(out/"controls.json",checked)
        summary=dict(identity=identity(),accepted=True,sender_artifact=receipt,receiver_artifact=greceipt,
            book_key=s["book_key"],original_bytes=s["original_bytes"],original_sha256=s["original_sha256"],
            sender_sdk_id=s["sender_sdk_id"],receiver_sdk_id=r["receiver_sdk_id"],windows_checks=6,gtk_checks=7,
            controls=checked,F02_accepted=False,formal="95/108",
            boundary="Windows real HTTPS PUT; byte-identical server store transferred via artifact; GTK real HTTPS GET and visible open. Not one continuously-online public server or six-target final acceptance.")
        save(out/"summary.json",summary);print("F02_AUTH "+json.dumps(summary),flush=True)
    except Exception as exc:
        save(out/"failure.json",dict(accepted=False,error=type(exc).__name__+":"+str(exc),F02_accepted=False));raise
if __name__=="__main__":main()
