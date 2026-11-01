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
import sqlite3
import subprocess
import sys
import time
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_linux_host import Session, command
from fixture import Store

def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("Actions only")
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload", type=Path, required=True)
    parser.add_argument("--inspect", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    cert, key = out / "fixture.crt", out / "fixture.key"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                    "-keyout", str(key), "-out", str(cert), "-subj", "/CN=127.0.0.1",
                    "-addext", "subjectAltName=IP:127.0.0.1"], check=True, capture_output=True)
    trust = Path("/usr/local/share/ca-certificates") / ("f05-" + secrets.token_hex(12) + ".crt")
    subprocess.run(["sudo", "cp", str(cert), str(trust)], check=True, capture_output=True)
    subprocess.run(["sudo", "update-ca-certificates"], check=True, capture_output=True)
    user, password = "f05", secrets.token_hex(24)
    auth = "Basic " + base64.b64encode((user + ":" + password).encode()).decode()
    store = Store(cert, key, auth)
    devices, checks = [], []
    binary = (args.payload / "bin/exreader-linux").resolve()
    report = {"host": "linux", "F05_accepted": False, "cases": checks, "errors": [],
              "identity": {"source": os.environ["GITHUB_SHA"], "run": os.environ["GITHUB_RUN_ID"],
                           "attempt": os.environ["GITHUB_RUN_ATTEMPT"]},
              "program_sha256": hashlib.sha256(binary.read_bytes()).hexdigest()}
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
        def find():
            result = subprocess.run(["xdotool", "search", "--onlyvisible", "--all",
                    "--pid", str(host.process.pid), "--name", "^" + title + "$"],
                    capture_output=True, text=True, timeout=5)
            if not present: return not result.stdout.strip()
            return result.stdout.splitlines()[-1] if result.stdout.strip() else None
        target = wait(host, find, 30)
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
        for shortcut, value in (("w", store.root), ("u", user), ("p", password)):
            host.key("alt+" + shortcut, "ctrl+a")
            host.paste(value)
        host.key("alt+h", "alt+a")
        wait(host, lambda: account(host).get("bound") == "1")
        close_account(host)
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
        host.key("alt+s")
        wait(host, lambda: account(host).get("session_state") == "4", 240)
        # Retained history is not shelf projection. Observe the actual Receive
        # action crossing its owner boundary; three pre-existing idle zeros
        # cannot be accepted as completion of a click not yet processed.
        before_receive = account(host)
        host.key("alt+r")
        wait(host, lambda: account(host).get("preparing") == "1"
             or account(host).get("phase") != "0"
             or int(account(host).get("receive_seen", "0")) >
                int(before_receive.get("receive_seen", "0")), 120)
        wait(host, lambda: account(host).get("phase") == "0"
             and account(host).get("preparing") == "0"
             and account(host).get("owner_busy") == "0"
             and (account(host).get("notice", "").startswith("Sync finished.")
                  or account(host).get("notice", "").startswith("Shelf organization:")), 120)
        if heads is not None:
            wait(host, lambda: set(snapshot(host)["heads"]) == set(heads))
        state = account(host)
        command("import", "-window", window(host, "Account and Sync"),
                out / ("sync-" + host.folder.name + "-" + str(len(store.requests)) + ".png"))
        close_account(host)
        return state
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
        sync(second, pending["heads"])
        if snapshot(first)["outbox"] or any(store.entries.get(k) != v for k, v in before.items()):
            raise AssertionError("uncertain replay mismatch")
        checks.append({"name": "kill_commit_ack_replay", "outcome": "passed",
                       "terminated_pid": pid, "reopened_pid": first.process.pid,
                       "pending": pending, "after": snapshot(first)})
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
            "restore_revision_created":False, "implicit_single_head_selected":False})
        (out / "peer-contract.json").write_text(json.dumps({
            "entity_kind":"tag", "entity_key":tag, "common_parent":parent["heads"],
            "baseline":"peer-baseline", "remote_delete":"peer-delete",
            "simultaneous_online_peers":False}, indent=2) + "\n")
        edit(first, "Concurrent GTK first")
        edit(second, "Concurrent GTK second")
        heads = set(snapshot(first)["heads"]) | set(snapshot(second)["heads"])
        if len(heads) != 2: raise AssertionError("two true peer heads required")
        sync(first)
        right = sync(second, heads)
        left = sync(first, heads)
        key = snapshot(first)["entity_key"]
        for state in (left, right):
            if (int(state.get("conflict_rows", "0")) < 1
                    or key not in state.get("conflict_keys", "")
                    or not all(head in state.get("conflict_heads", "") for head in heads)):
                raise AssertionError("native conflict rows do not expose both retained heads")
        checks.append({"name": "concurrent_heads_preserved", "outcome": "passed",
                       "heads": sorted(heads), "first_native_state": left,
                       "second_native_state": right})
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
            "original_sha256":hashlib.sha256(exported.read_bytes()).hexdigest()})
    except Exception as error:
        report["errors"].append(str(error))
        raise
    finally:
        for host in devices:
            if host.process.poll() is None:
                try: host.close()
                except Exception:
                    host.process.kill()
                    host.process.wait(timeout=20)
        store.close()
        report["requests"] = store.requests
        report["uncovered"] = ["stale-put replay after tombstone", "conditional explicit restore parents",
                               "SDK mid-import cancellation (additional, not universal prerequisite)",
                               "independent original-artifact authentication"]
        (out / "coverage.json").write_text(json.dumps(report, indent=2) + "\n")
        subprocess.run(["sudo", "rm", "--", str(trust)], check=True, capture_output=True)
        subprocess.run(["sudo", "update-ca-certificates"], check=True, capture_output=True)
        key.unlink(missing_ok=True)


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
