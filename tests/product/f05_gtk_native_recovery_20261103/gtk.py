# SPDX-License-Identifier: MIT
"""Actions-only GTK two-real-host wire recovery; preparation subset, not F05 pass."""
import argparse
import base64
import configparser
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import ssl
import sqlite3
import subprocess
import sys
import time
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_linux_host import command
from native_runtime import Session
from fixture import Store, write_role_receipt
from driver import observation_snapshot, receive_precondition, receive_observation, verify_receive_trace

def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("Actions only")
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload", type=Path, required=True)
    parser.add_argument("--inspect", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--configuration-mode", choices=("ready", "legacy"), default="ready")
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    cert, key = out / "fixture.crt", out / "fixture.key"
    trust = Path("/usr/local/share/ca-certificates") / ("f05-" + secrets.token_hex(12) + ".crt")
    trust_owned, store = False, None
    user, password = "f05", secrets.token_hex(24)
    auth = "Basic " + base64.b64encode((user + ":" + password).encode()).decode()
    devices, checks = [], []
    receive_traces = []
    binary = (args.payload / "bin/exreader-linux").resolve()
    report = {"host": "linux", "F05_accepted": False, "cases": checks, "errors": [],
              "identity": {"source": os.environ["GITHUB_SHA"], "run": os.environ["GITHUB_RUN_ID"],
                           "attempt": os.environ["GITHUB_RUN_ATTEMPT"]},
              "program_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
              "dry_run": args.dry_run, "configuration_mode": args.configuration_mode,
              "configuration_events": [], "cleanup_timings": []}
    if not args.dry_run and args.configuration_mode != "ready":
        raise RuntimeError("legacy control is restricted to dry-run")
    normalized, claim_refs, evidence = [], {}, ["coverage.json", "receive-observations.json"]
    previous_wire, last_request = {}, 0
    def finish_case(claims, screenshot=None, screenshot_host=None, **semantic):
        nonlocal previous_wire, last_request
        raw = checks[-1]
        name = raw["name"]
        expected = original.read_bytes()
        observed = {"first":sdk_originals(first), "second":sdk_originals(second)}
        if any(len(items)!=1 or items[0]["bytes"]!=len(expected)
               or items[0]["sha256"]!=hashlib.sha256(expected).hexdigest() for items in observed.values()):
            raise AssertionError("GTK native case changed exact SDK original set")
        wire = {path:hashlib.sha256(body).hexdigest() for path,body in store.entries.items()}
        if any(wire.get(path)!=digest for path,digest in previous_wire.items()):
            raise AssertionError("GTK native case rewrote immutable peer wire")
        if screenshot is None:
            screenshot=name+".png"
            command("import","-window",(screenshot_host or first).window,out/screenshot)
        evidence.append(screenshot)
        raw["sdk_original_readback"]=observed
        raw["immutable_wire_inventory"]=wire
        raw["screenshot"]=screenshot
        normalized.append({"id":name,"outcome":raw["outcome"],
            "actual_host_actions":True,"receiver_database_injection":False,
            "original_identity_preserved":True,"revision_bytes_preserved":True,
            "peer_wire_observed":any(r["authenticated"] and r["method"] in ("PUT","GET","PROPFIND")
                                     for r in store.requests[last_request:]),
            "source_evidence":["coverage.json",screenshot],
            "source_pointer":"/cases/"+str(len(checks)-1),**semantic})
        for claim,role in claims.items():
            claim_refs.setdefault(claim,[]).append({"case_id":name,"role":role})
        previous_wire,last_request=wire,len(store.requests)
    def launch(name):
        folder = out / name
        folder.mkdir(exist_ok=True)
        host = Session(binary, (args.payload / "Reader.otf").resolve(), folder)
        devices.append(host)
        host.launch()
        return host
    def wait(host, predicate, timeout=120):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if host.process.poll() is not None: raise AssertionError("host exited")
            value = predicate()
            if value: return value
            time.sleep(.1)
        raise TimeoutError("GTK boundary not reached")
    def window(host, title, present=True):
        appearance_deadline = time.monotonic() + 5
        def find():
            remaining = appearance_deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("GTK window appearance exceeded 5 seconds")
            result = subprocess.run(["xdotool", "search", "--onlyvisible", "--all",
                    "--pid", str(host.process.pid), "--name", "^" + title + "$"],
                    capture_output=True, text=True, timeout=min(30, remaining))
            if result.returncode not in (0, 1):result.check_returncode()
            if not present: return not result.stdout.strip()
            return result.stdout.splitlines()[-1] if result.stdout.strip() else None
        target = wait(host, find, 5)
        if present: command("xdotool", "windowactivate", "--sync", target)
        return target
    def account(host):
        state = configparser.ConfigParser(interpolation=None)
        state.read(host.observe)
        return dict(state["account"]) if state.has_section("account") else {}
    def open_account(host):
        command("xdotool", "windowactivate", "--sync", host.window)
        host.key("F2", "ctrl+shift+a")
        window(host, "Account and Sync")
        wait(host, lambda: account(host).get("visible") == "1")
    def close_account(host):
        window(host, "Account and Sync")
        host.key("alt+F4")
        window(host, "Account and Sync", False)
        wait(host, lambda: account(host).get("session_present") == "0")
    def configure(host):
        open_account(host)
        event = {"host":host.folder.name,"pid":host.process.pid,"opened":time.monotonic(),
                 "mode":args.configuration_mode}
        report["configuration_events"].append(event)
        if args.configuration_mode == "ready":
            wait(host, lambda: all(account(host).get(k)==v for k,v in
                {"owner_busy":"0","form_enabled":"1","preparing":"0","closing":"0"}.items()))
        event["form_ready"] = time.monotonic()
        for shortcut, value in (("w", store.root), ("u", user), ("p", password)):
            host.key("alt+" + shortcut, "ctrl+a")
            host.paste(value)
        event["apply_dispatched"] = time.monotonic()
        host.key("alt+h", "alt+a")
        if args.configuration_mode == "ready":
            wait(host, lambda: all(account(host).get(k)==v for k,v in
                {"bound":"1","owner_busy":"0","credential_status":"0",
                 "has_user":"1","has_password":"1","form_enabled":"1"}.items())
                and account(host).get("notice")=="Using credentials for this app session only")
        else:
            wait(host, lambda: account(host).get("bound") == "1")
        event["apply_observed"] = time.monotonic()
        event["credential_state"] = {k:account(host).get(k) for k in
            ("bound","owner_busy","credential_status","has_user","has_password","notice")}
        close_account(host)
    def fixture_ready():
        record = {"at":time.monotonic(),"thread_alive":store.thread.is_alive(),
                  "tls_ready":False}
        if not record["thread_alive"]:
            raise AssertionError("network fixture thread exited")
        context = ssl.create_default_context(cafile=str(cert))
        with socket.create_connection(store.server.server_address, timeout=5) as connection:
            with context.wrap_socket(connection, server_hostname="127.0.0.1"):
                record["tls_ready"] = True
        record["ready_at"] = time.monotonic()
        return record
    def sdk_originals(host):
        db=host.folder/"profile/library.sqlite"
        with sqlite3.connect(db.resolve().as_uri()+"?mode=ro",uri=True,timeout=20) as connection:
            return [{"id":row[0],"bytes":len(row[1]),"sha256":hashlib.sha256(row[1]).hexdigest()}
                    for row in connection.execute("SELECT id,source FROM books ORDER BY id")]
    def snapshot(host, kind="book", entity=None):
        db = host.folder / "profile/library.sqlite.product.sqlite"
        with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True, timeout=20) as connection:
            records = [json.loads(r[0]) for r in connection.execute("SELECT body_json FROM reader_revisions")]
            pending = connection.execute("SELECT count(*) FROM reader_outbox").fetchone()[0]
        selected = [r for r in records if r["entity_kind"] == kind and (entity is None or r["entity_key"] == entity)]
        entity_keys = {r["entity_key"] for r in selected}
        if len(entity_keys) != 1:
            raise AssertionError("single-book producer cannot combine unrelated entity heads")
        ids = {r["id"] for r in selected}
        parents = {p for r in selected for p in r["parents"]}
        return {"entity_key": next(iter(entity_keys)), "heads": sorted(ids - parents), "records": records, "outbox": pending}
    def sync(host, heads=None):
        open_account(host)
        started=time.monotonic();network_deadline=started+240
        record={"index":len(receive_traces)+1,"host":host.folder.name,"pid":host.process.pid,
                "case_index":len(checks),"dispatch_count":0,"dispatch_ok":False,
                "network_samples":[],"samples":[],"completed":False}
        receive_traces.append(record)
        record["fixture_before_sync"] = fixture_ready()
        record["credential_before_sync"] = {k:account(host).get(k) for k in
            ("credential_status","has_user","has_password","owner_busy","bound")}
        record["session_handle_before_sync"] = account(host).get("session_present")
        def sample():
            if host.process.poll() is not None:raise AssertionError("Receive host exited")
            raw=account(host)
            if isinstance(raw.get("notice"),str):raw["notice"]=raw["notice"].replace(password,"<fixture-secret>")
            return observation_snapshot(raw)
        def elapsed():return time.monotonic()-started
        def record_sample(target,state):
            limit=2500 if target=="network_samples" else 1300
            if len(record[target])>=limit:raise AssertionError("observation sample budget")
            record[target].append({"elapsed":elapsed(),"pid":host.process.pid,"state":state})
        def save_trace():
            body={"identity":report["identity"],"program_sha256":report["program_sha256"],
                  "records":receive_traces,"full_F05_accepted":False}
            temporary=out/"receive-observations.tmp"
            temporary.write_text(json.dumps(body,indent=2,allow_nan=False)+"\n",encoding="utf-8")
            temporary.replace(out/"receive-observations.json")
        try:
            # Wait for the account-load owner to retire before the single Sync
            # click. This uses the existing 240-second network deadline.
            while True:
                if time.monotonic()>=network_deadline:raise TimeoutError("network readiness deadline")
                before=sample()
                if all(before[k]==v for k,v in {"visible":"1","owner_busy":"0","preparing":"0",
                       "closing":"0","session_present":"0"}.items()):break
                time.sleep(.1)
            record["before_network"]=before
            record["sync_at"] = time.monotonic()
            record["fixture_to_sync_seconds"] = record["sync_at"]-record["fixture_before_sync"]["ready_at"]
            host.key("alt+s")
            while True:
                if time.monotonic()>=network_deadline:raise TimeoutError("new network session deadline")
                state=sample();record_sample("network_samples",state)
                try:receive_precondition(before,state)
                except AssertionError:
                    time.sleep(.1);continue
                record["ready"]=state;record["generation"]=int(state["session_generation"]);break
            # One actual key dispatch. A new network-generation plus its exact
            # network-only notice excludes both old Receive completion and idle.
            record["dispatch_elapsed"]=elapsed()
            receive_deadline=started+record["dispatch_elapsed"]+120
            record["dispatch_count"]=1
            host.key("alt+r")
            record["dispatch_ok"]=True
            while True:
                if time.monotonic()>=receive_deadline:raise TimeoutError("Receive completion deadline")
                state=sample();record_sample("samples",state)
                outcome=receive_observation(record["ready"],state,record["dispatch_ok"])
                if outcome is not None:
                    record["outcome"]=outcome;record["completed"]=True
                    verify_receive_trace(record);break
                time.sleep(.1)
            if heads is not None:
                wait(host, lambda: set(snapshot(host)["heads"]) == set(heads))
            state = account(host)
            command("import", "-window", window(host, "Account and Sync"),
                    out / ("sync-" + host.folder.name + "-" + str(len(store.requests)) + ".png"))
            close_account(host)
            return state
        except BaseException as error:
            record["error"]=str(error).replace(password,"<fixture-secret>")[:2000]
            record["completed"]=False
            raise
        finally:
            try:save_trace()
            except BaseException as trace_error:
                print("F05 RECEIVE TRACE WRITE FAILED "+str(trace_error).replace(password,"<fixture-secret>")[:2000],flush=True)
                if "error" not in record:raise
            summary={k:record.get(k) for k in ("index","host","pid","case_index","generation",
                     "dispatch_count","dispatch_ok","completed","outcome","error")}
            summary["last_sample"]=record["samples"][-1] if record["samples"] else None
            print("F05 RECEIVE TRACE "+json.dumps(summary,allow_nan=False),flush=True)
    def collections(host):
        state = configparser.ConfigParser(interpolation=None)
        state.read(host.observe)
        return dict(state["collections"]) if state.has_section("collections") else {}
    def group_action(host, action, identifier=None, name=None):
        command("xdotool", "windowactivate", "--sync", host.window)
        host.key("F2", "ctrl+shift+c")
        window(host, "Library collections")
        wait(host, lambda: collections(host).get("visible") == "1")
        host.key("alt+t", "Home", "Down", "Tab")
        wait(host, lambda: collections(host).get("kind") == "1")
        if identifier:
            ids = collections(host).get("group_ids", "").split(",")
            if identifier not in ids: raise AssertionError("actual tag missing")
            host.key("alt+g", "Home")
            for _ in range(ids.index(identifier)): host.key("Down")
            wait(host, lambda: collections(host).get("selected_id") == identifier)
        host.key("alt+" + {"create":"n", "edit":"r", "delete":"d"}[action])
        window(host, "Collection details")
        if name is not None:
            host.key("alt+n", "ctrl+a")
            host.paste(name)
        host.key("Return")
        window(host, "Collection details", False)
        wait(host, lambda: collections(host).get("editor") == "0")
        selected = collections(host).get("selected_id")
        host.key("alt+F4")
        window(host, "Library collections", False)
        return identifier or selected
    def edit(host, title):
        command("xdotool", "windowactivate", "--sync", host.window)
        host.key("F2", "ctrl+e")
        window(host, "Book details")
        host.key("alt+t", "ctrl+a")
        host.paste(title)
        host.key("Return")
        window(host, "Book details", False)
        host.wait(lambda s: not s["error"] and not s.get("busy"), timeout=60)
    try:
        subprocess.run(["openssl","req","-x509","-newkey","rsa:2048","-nodes","-days","1",
                        "-keyout",str(key),"-out",str(cert),"-subj","/CN=127.0.0.1",
                        "-addext","subjectAltName=IP:127.0.0.1"],check=True,capture_output=True)
        trust_owned=True
        subprocess.run(["sudo","cp",str(cert),str(trust)],check=True,capture_output=True)
        subprocess.run(["sudo","update-ca-certificates"],check=True,capture_output=True)
        store=Store(cert,key,auth)
        first = launch("first")
        original = out / "F05.txt"
        original.write_text("F05 GTK original. " * 400)
        first.dialog(original)
        first.wait(lambda s: s["book"] > 0 and not s["error"], timeout=60)
        configure(first)
        sync(first)
        second = launch("second")
        configure(second)
        before_cancel=sdk_originals(second)
        store.hold_get=True;store.get_blocked.clear();store.release.clear()
        open_account(second);second.key("alt+s")
        if not store.get_blocked.wait(60):
            raise AssertionError("actual GTK original GET boundary missing")
        second.key("alt+c")
        wait(second,lambda:account(second).get("cancel_requested")=="1",10)
        store.release.set()
        wait(second,lambda:account(second).get("session_state")=="3",120)
        if sdk_originals(second)!=before_cancel:
            raise AssertionError("cancelled GTK transport changed SDK originals")
        close_account(second)
        sync(second, snapshot(first)["heads"])
        command("xdotool", "windowactivate", "--sync", second.window)
        second.key("F2", "Return")
        second.wait(lambda state: state["book"] > 0 and state["reader_visible"]
                    and not state["error"], timeout=120)
        after_retry=sdk_originals(second)
        if len(after_retry)!=1 or after_retry[0]["sha256"]!=hashlib.sha256(original.read_bytes()).hexdigest():
            raise AssertionError("cancel retry did not import exact one original")
        checks.append({"name":"cancel_sync_retry","outcome":"passed",
            "cancel_layer":"transport-original-GET-before-explicit-native-receive",
            "before":before_cancel,"retry":after_retry,"sdk_mid_import_cancel_tested":False})
        finish_case({"cancel_retry":"local"},screenshot_host=second,remote_boundary=True,cancel_layer="transport",
                    native_cancel_observed=True,explicit_retry_passed=True)
        baseline = snapshot(first)
        store.offline = True
        edit(first, "Offline GTK edit")
        offline = snapshot(first)
        if not offline["outbox"]: raise AssertionError("offline outbox absent")
        store.offline = False
        sync(first)
        sync(second, offline["heads"])
        if snapshot(first)["outbox"]: raise AssertionError("outbox not acknowledged")
        checks.append({"name": "offline_reconnect", "outcome": "passed",
                       "baseline": baseline, "offline": offline, "peer": snapshot(second)})
        finish_case({"offline_reconnect":"author"})
        edit(first, "Uncertain GTK commit")
        pending = snapshot(first)
        store.hold_put = True
        store.put_committed.clear()
        store.release.clear()
        open_account(first)
        first.key("alt+s")
        if not store.put_committed.wait(60): raise AssertionError("no committed PUT boundary")
        pid = first.process.pid
        first.process.kill()
        first.process.wait(timeout=20)
        first.log.close()
        before = dict(store.entries)
        store.release.set()
        first = launch("first")
        configure(first)
        sync(first)
        if args.dry_run:
            report["dry_run_checkpoint"] = {"passed":True,"sync_index":5,
                "new_pid":first.process.pid,"old_pid":pid,
                "generation":receive_traces[-1]["generation"],
                "session_present_at_network_ready":receive_traces[-1]["ready"]["session_present"]}
            return
        sync(second, pending["heads"])
        if snapshot(first)["outbox"] or any(store.entries.get(k) != v for k, v in before.items()):
            raise AssertionError("uncertain replay mismatch")
        checks.append({"name": "kill_commit_ack_replay", "outcome": "passed",
                       "terminated_pid": pid, "reopened_pid": first.process.pid,
                       "pending": pending, "after": snapshot(first)})
        if pid==first.process.pid:raise AssertionError("GTK actual process not replaced")
        finish_case({"process_recovery":"local"},remote_boundary=True,
                    terminated_pid=pid,reopened_pid=first.process.pid,actual_process_termination=True,
                    recovery_boundary="committed-PUT-before-ACK",durable_recovery_passed=True)
        # Both native peers share one actual group parent. The server checkpoints
        # are raw authenticated PUTs, not synthetic revisions or DB injection.
        tag = group_action(first, "create", name="F05 shared tag")
        sync(first)
        sync(second)
        parent = snapshot(first, "tag", tag)
        if parent["heads"] != snapshot(second, "tag", tag)["heads"]:
            raise AssertionError("group common ancestor not received")
        base_checkpoint = store.checkpoint(out / "peer-baseline", "gtk-native-group-create")
        group_action(first, "edit", tag, "F05 offline tag edit")
        local_put = snapshot(first, "tag", tag)
        group_action(second, "delete", tag)
        deletion = snapshot(second, "tag", tag)
        sync(second)
        store.checkpoint(out / "peer-delete", "gtk-native-group-delete")
        sync(first)
        right_group = sync(second)
        left_group = sync(first)
        combined = set(local_put["heads"]) | set(deletion["heads"])
        if len(local_put["heads"])!=1 or len(deletion["heads"])!=1 or len(combined)!=2:
            raise AssertionError("real old-put/delete scenario requires two distinct native heads")
        put_id,delete_id=local_put["heads"][0],deletion["heads"][0]
        put_row=next(row for row in local_put["records"] if row["id"]==put_id)
        delete_row=next(row for row in deletion["records"] if row["id"]==delete_id)
        if put_row["operation"]!="put" or delete_row["operation"]!="delete":
            raise AssertionError("native actions did not author typed put/delete")
        if set(put_row["parents"])!=set(parent["heads"]) or set(delete_row["parents"])!=set(parent["heads"]):
            raise AssertionError("native competing operations do not share the actual old parent")
        def actual_commit(revision_id):
            found=[]
            for index,commit in enumerate(store.commits):
                if "/revisions/" not in commit["path"]:continue
                body=store.entries[commit["path"]]
                row=json.loads(body)
                if row["id"]==revision_id:
                    if hashlib.sha256(body).hexdigest()!=commit["sha256"] or not commit["authenticated_native_put"]:
                        raise AssertionError("native PUT source identity changed")
                    found.append({"index":index,"path":commit["path"],"sha256":commit["sha256"]})
            if not found:raise AssertionError("actual native PUT commit evidence absent")
            return found[0]
        put_commit,delete_commit=actual_commit(put_id),actual_commit(delete_id)
        if delete_commit["index"]>=put_commit["index"]:
            raise AssertionError("old-parent put was not committed after actual tombstone")
        if any(row["operation"]=="restore" for row in snapshot(first,"tag",tag)["records"]):
            raise AssertionError("ordinary old-parent put became an implicit restore")
        stale_proof={"common_parent":parent["heads"],"put":put_row,"delete":delete_row,
            "put_commit":put_commit,"delete_commit":delete_commit,
            "scope":"actual old-parent native put after tombstone; not a repeated-ID replay",
            "restore_revision_created":False}

        for host, state in ((first, left_group), (second, right_group)):
            if set(snapshot(host, "tag", tag)["heads"]) != combined:
                raise AssertionError("delete-put conflict lost a head")
            if "conflicting or incomplete versions" not in state.get("notice", ""):
                raise AssertionError("native organization conflict notice missing")
        checks.append({"name":"delete_put_tombstone_preserved", "outcome":"partial",
            "preservation_passed":True,"deletion_conflict_ui_detail":False,
            "entity_kind":"tag", "entity_key":tag, "common_parent":parent["heads"],
            "local_put":local_put, "delete":deletion,
            "retained_heads":sorted(combined), "first_native_state":left_group,
            "second_native_state":right_group,
            "restore_revision_created":False, "implicit_single_head_selected":False,
            "old_put_after_tombstone":stale_proof})
        finish_case({"delete_put_tombstone_preserved":"receiver"},competing_heads=sorted(combined),
                    final_heads=snapshot(first,"tag",tag)["heads"],tombstone_preserved=True,
                    delete_conflict_displayed=False,stale_peer_did_not_resurrect=True,
                    old_put_after_tombstone=stale_proof,
                    uncovered="native deletion operation detail",explicit_user_restore=False)
        store.checkpoint(out/"peer-delete-put","gtk-native-delete-then-old-parent-put")
        (out / "peer-contract.json").write_text(json.dumps({
            "entity_kind":"tag", "entity_key":tag, "common_parent":parent["heads"],
            "baseline":"peer-baseline", "remote_delete":"peer-delete",
            "remote_delete_put":"peer-delete-put","old_put_after_tombstone":stale_proof,
            "simultaneous_online_peers":False}, indent=2) + "\n")
        edit(first, "Concurrent GTK first")
        edit(second, "Concurrent GTK second")
        heads = set(snapshot(first)["heads"]) | set(snapshot(second)["heads"])
        if len(heads) != 2: raise AssertionError("two true peer heads required")
        sync(first)
        right = sync(second, heads)
        left = sync(first, heads)
        entity_key = snapshot(first)["entity_key"]
        for state in (left, right):
            if (int(state.get("conflict_rows", "0")) < 1
                    or entity_key not in state.get("conflict_keys", "")
                    or not all(head in state.get("conflict_heads", "") for head in heads)):
                raise AssertionError("native conflict rows do not expose both retained heads")
        checks.append({"name": "concurrent_heads_preserved", "outcome": "passed",
                       "heads": sorted(heads), "first_native_state": left,
                       "second_native_state": right})
        finish_case({"concurrent_heads_preserved":"receiver"},competing_heads=sorted(heads),
                    final_heads=snapshot(first)["heads"],conflict_displayed=True,explicit_user_resolution=False)
        original_id=sdk_originals(first)[0]["id"]
        preserved=snapshot(first)
        first.close()
        store.offline=True
        previous_requests=len(store.requests)
        first=launch("first")
        first.key("F2","Home","Return")
        first.wait(lambda state:state["book"]==original_id and state["reader_visible"]
                   and not state["error"],timeout=120)
        if len(store.requests)!=previous_requests or snapshot(first)["heads"]!=preserved["heads"]:
            raise AssertionError("offline reopened reader changed heads or used network")
        command("import","-window",first.window,out/"offline-reader.png")
        first.close()
        exported=out/"offline-sdk-original.bin"
        inspected=subprocess.run([str(args.inspect.resolve()),
            str(first.folder/"profile/library.sqlite"),str(original_id),str(exported)],
            capture_output=True,text=True,timeout=60)
        (out/"offline-sdk-readback.log").write_text(inspected.stdout+inspected.stderr)
        if inspected.returncode or exported.read_bytes()!=original.read_bytes():
            raise AssertionError("installed SDK exact offline original readback failed")
        checks.append({"name":"restart_offline_read","outcome":"passed",
            "book":original_id,"heads":preserved["heads"],"network_requests":0,
            "public_sdk_readback":json.loads(inspected.stdout),
            "original_sha256":hashlib.sha256(exported.read_bytes()).hexdigest(),
            "measurement":"controlled F05 library sync endpoint only; not whole OS networking"})
        evidence.extend(["offline-sdk-original.bin","offline-sdk-readback.log"])
        finish_case({"offline_read":"local"},screenshot="offline-reader.png",
                    reopened_host_readable=True,network_requests=0,
                    network_measurement="controlled F05 library sync endpoint")
    except Exception as error:
        report["errors"].append(str(error))
        raise
    finally:
        cleanup_errors=[]
        def cleanup(label,action):
            started = time.monotonic()
            try:action()
            except BaseException as error:
                cleanup_errors.append({"action":label,"error":repr(error).replace(password,"<fixture-secret>")})
            finally:
                report["cleanup_timings"].append({"action":label,"seconds":time.monotonic()-started})
        def close_host(host):
            if host.process.poll() is None:
                try:host.close()
                except BaseException as primary:
                    try:host.process.kill();host.process.wait(timeout=5)
                    except BaseException as error:primary.f05_cleanup_errors = [repr(error)]
                    raise
        for index,host in enumerate(devices):
            cleanup("native-close-"+str(index),lambda host=host:close_host(host))
        if store is not None:cleanup("fixture-close",store.close)
        if trust_owned:
            cleanup("remove-fixture-trust",lambda:subprocess.run(
                ["sudo","rm","-f","--",str(trust)],check=True,capture_output=True))
            cleanup("refresh-runner-trust",lambda:subprocess.run(
                ["sudo","update-ca-certificates"],check=True,capture_output=True))
        def remove_fixture_key():
            key.unlink(missing_ok=True)
            if key.exists() or key.is_symlink():
                raise RuntimeError("fixture private key remains after cleanup")
        cleanup("remove-fixture-key",remove_fixture_key)
        report["requests"]=store.requests if store is not None else []
        report["cleanup_errors"]=cleanup_errors
        report["uncovered"]=["native deletion operation detail","repeated-ID replay after tombstone (additional, not original hard gate)",
            "conditional explicit restore parents","SDK mid-import cancellation (not universal prerequisite)",
            "independent original-artifact authentication"]
        try:
            (out/"coverage.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
            write_role_receipt(out,"linux",binary,report["identity"],normalized,claim_refs,evidence)
        except BaseException as error:
            print("F05 GTK evidence write failed: "+repr(error).replace(password,"<fixture-secret>"),flush=True)
            if not report["errors"]:raise
        if cleanup_errors and not report["errors"]:
            raise RuntimeError("F05 GTK cleanup failed; see coverage cleanup_errors")


def build():
    if os.environ.get("GITHUB_ACTIONS")!="true" or not sys.platform.startswith("linux"):
        raise RuntimeError("Linux Actions only")
    import runpy
    recipe=ROOT/"tests/gtk_sdk342_package/run.py"
    blob=subprocess.check_output(["git","hash-object",str(recipe)],cwd=ROOT,text=True).strip()
    if blob!="9c26c4670c402fdd5de8d6bf4d03110df7a43be6":
        raise AssertionError("original GTK SDK342 build recipe changed")
    prefix=ROOT/"build/f05-original-hash"
    def run(*args):
        subprocess.run(list(map(str,args)),cwd=ROOT,check=True)
    run("cmake","-S",ROOT/"extras/opds","-B",ROOT/"build/f05-original-hash-build",
        "-G","Ninja","-DCMAKE_BUILD_TYPE=Release","-DEXREADER_OPDS_HASH_ONLY=ON",
        "-DCMAKE_INSTALL_PREFIX="+str(prefix.resolve()))
    run("cmake","--build",ROOT/"build/f05-original-hash-build","--parallel","4")
    run("cmake","--install",ROOT/"build/f05-original-hash-build")
    os.environ["EXREADER_ORIGINAL_HASH_PREFIX"]=str(prefix.resolve(strict=True))
    # Its guard is specific to its historical package branch. F05 admission
    # separately locks the approved base and SDK. Execute its unchanged build
    # and retained raw/legacy assertions, never weaken their result predicates.
    sys.argv=[str(recipe),"build"]
    runpy.run_path(str(recipe),run_name="__main__")
    sdk=ROOT/"build/reading-library/stage"
    raw=ROOT/"build/gtk-raw-wave3/raw-stage"
    for label,source in (("inspect","tests/reader_gtk_receive"),
                         ("metadata-consumer","tests/reader_metadata/consumer"),
                         ("revision-consumer","tests/reader_revisions/consumer"),
                         ("reading-probe","tests/reader_reading_v2/consumer")):
        target=ROOT/"build/f05-consumers"/label
        run("cmake","-S",ROOT/source,"-B",target,"-G","Ninja",
            "-DCMAKE_BUILD_TYPE=Release","-DEXR_SDK_VERSION=3.42.0",
            "-DEXR_SDK="+str(sdk),"-DCMAKE_PREFIX_PATH="+str(raw)+";"+str(sdk))
        run("cmake","--build",target,"--parallel","4")
    run(sys.executable,"tests/reader_reading_state/make_fixtures.py","build/f05-receive-fixtures")

if __name__ == "__main__":
    if len(sys.argv)>1 and sys.argv[1]=="build":build()
    else:main()
