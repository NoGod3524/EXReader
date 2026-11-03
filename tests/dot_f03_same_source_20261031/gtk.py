"""Real GTK retained organization and DAV relay phases; never replaces native UI with SQL writes."""
import argparse
import configparser
import hashlib
import importlib.util
import json
import re
import time
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit
from identity import ROOT, identity, require, snapshot_receipt, write_json, read_snapshot, digest, SCOPE, canonical

def author(a, stamp):
    """Actual GTK UI authors the lifecycle; SQL is read-only and cannot manufacture a revision."""
    sys.path.insert(0, str(ROOT / "tools"))
    from check_linux_host import Session, command
    spec = importlib.util.spec_from_file_location("f03_original_relay",
        ROOT / "tests/reader_windows_gtk_interop/relay.py")
    relay = importlib.util.module_from_spec(spec); spec.loader.exec_module(relay)
    require(a.phase is not None and a.profile is not None, "author phase/profile required")
    require(a.book is not None and a.book.is_file(), "actual original book required")
    a.output.mkdir(parents=True, exist_ok=False)
    a.profile.mkdir(parents=True, exist_ok=True)
    (a.profile / "profile").mkdir(mode=0o700, exist_ok=True)
    (a.profile / "profile").chmod(0o700)
    program = a.package / "bin/exreader-linux"
    host = Session(program.resolve(), (a.package / "Reader.otf").resolve(), a.profile)
    catalog = a.profile / "profile/library.sqlite.product.sqlite"
    meta_path = a.profile / "f03-identities.json"
    known = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    dav = None
    events = []
    def state(section):
        ini = configparser.ConfigParser(interpolation=None); ini.read(host.observe)
        return dict(ini[section]) if ini.has_section(section) else {}
    def wait(condition, seconds=120):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            require(host.process.poll() is None, "actual host exited")
            if condition():
                return
            time.sleep(.1)
        raise TimeoutError("native GTK phase did not settle")
    def window(title, present=True):
        found = []
        def ready():
            result = subprocess.run(["xdotool","search","--onlyvisible","--all","--pid",
                                     str(host.process.pid),"--name","^"+re.escape(title)+"$"],
                                    capture_output=True,text=True,timeout=10)
            found[:] = result.stdout.splitlines()
            return bool(found) == present
        wait(ready, 40)
        if present:
            command("xdotool","windowactivate","--sync",found[-1])
            return found[-1]
    def org_ready():
        wait(lambda: state("collections").get("visible") == "1" and
             not host.read().get("shelf_loading") and not host.read().get("shelf_restoring") and
             state("collections").get("editor","0") == "0")
    def field(key, value):
        host.key("alt+"+key,"ctrl+a");host.paste(str(value))
    def save():
        host.key("Return");window("Collection details",False);org_ready()
    def kind(index):
        window("Library collections");host.key("alt+t","Home")
        wait(lambda:state("collections").get("kind")=="0")
        for value in range(index):
            host.key("Down");wait(lambda:state("collections").get("kind")==str(value+1))
        host.key("Tab");org_ready()
        while state("collections").get("parent_id"):
            host.key("alt+u");org_ready()
    def choose(identifier):
        ids = state("collections").get("group_ids","").split(",")
        require(identifier in ids,"actual group not present")
        host.key("alt+g","Home")
        for _ in range(ids.index(identifier)):host.key("Down")
        wait(lambda:state("collections").get("selected_id")==identifier)
    def create(name, ordinal=None):
        host.key("alt+n");window("Collection details");field("n",name)
        if ordinal is not None:field("p",ordinal)
        save();return state("collections")["selected_id"]
    def member(action, ordinal=None):
        host.key("alt+"+action);window("Book classification")
        if ordinal is not None:field("p",ordinal)
        host.key("Return");window("Book classification",False);org_ready()
    def event(operation, before):
        after = read_snapshot(catalog)
        prior = {r["id"] for r in before.get("revisions",[])}
        ids = [r["id"] for r in after["revisions"] if r["id"] not in prior]
        require(ids or operation=="restart","native operation made no revision")
        def group(table, key, identifier):
            rows = [row for row in after[table] if row[key] == identifier]
            require(len(rows) == 1, "expected one projected group")
            return rows[0]
        if operation == "nested-shelf":
            root = group("reader_shelves", "shelf_id", known["root"])
            child = group("reader_shelves", "shelf_id", known["child"])
            require(root["name"] == "F03 Root" and root["ordinal"] == 1 and not root["deleted"],
                    "root projection differs")
            require(child["name"] == "F03 Child" and child["parent_id"] == known["root"] and
                    child["ordinal"] == 2 and not child["deleted"], "nested projection differs")
        elif operation in ("tag", "series"):
            row = group("reader_tags" if operation == "tag" else "reader_series",
                        operation + "_id", known[operation])
            require(row["name"] == "F03 " + operation.title() and not row["deleted"],
                    "group projection differs")
        elif operation in ("group-delete", "group-restore"):
            wanted = 1 if operation == "group-delete" else 0
            for table, key, item in (("reader_shelves","shelf_id","child"),
                                     ("reader_tags","tag_id","tag"),
                                     ("reader_series","series_id","series")):
                require(group(table,key,known[item])["deleted"] == wanted, "tombstone projection differs")
        if operation in ("nested-shelf","tag","series","membership-remove","membership-restore"):
            mapping = [("reader_book_shelves","shelf_id","child",3),
                       ("reader_book_tags","tag_id","tag",None),
                       ("reader_book_series","series_id","series",7)]
            for table, key, item, ordinal in mapping:
                if item not in known:
                    continue
                rows = [row for row in after[table] if row[key] == known[item] and
                        row["book_key"] == known["book_key"]]
                require(len(rows) == (0 if operation == "membership-remove" else 1),
                        "membership projection differs")
                if rows and ordinal is not None:
                    require(rows[0]["ordinal"] == ordinal, "membership ordering differs")
        image = a.output / (operation+".png")
        command("import","-window",window("Library collections"),image)
        record = {**stamp,"host":"gtk","operation":operation,"passed":True,"native_ui":True,
                  "program_sha256":digest(program),"revision_ids":ids,"before":before,"after":after}
        write_json(a.output/(operation+".json"),record)
        events.append(operation)
    try:
        host.launch()
        if a.phase=="create":
            require(not known,"do not repeat an uncertain create")
            host.dialog(a.book.resolve())
            host.wait(lambda value:value["book"]>0 and value["books"]==1)
        else:
            require(known.get("source_sha")==stamp["source_sha"],"profile source differs")
        command("xdotool","windowactivate","--sync",host.window)
        host.key("F2","Home","ctrl+shift+c");window("Library collections");org_ready()
        if a.phase=="create":
            before=read_snapshot(catalog);kind(0)
            parent=create("F03 Root",1);host.key("alt+e")
            wait(lambda:state("collections").get("parent_id")==parent)
            child=create("F03 Child",2);member("a",3)
            book_key=state("collections")["member_keys"]
            require(book_key and "," not in book_key,"one actual original membership required")
            known={**stamp,"root":parent,"child":child,"book_key":book_key}
            event("nested-shelf",before)
            before=read_snapshot(catalog);kind(1);known["tag"]=create("F03 Tag");member("a")
            event("tag",before)
            before=read_snapshot(catalog);kind(2);known["series"]=create("F03 Series");member("a",7)
            event("series",before)
            write_json(meta_path,known)
        elif a.phase in ("delete","restore"):
            before=read_snapshot(catalog)
            # Root stays active; delete/restore child plus tag and series through native controls.
            for index,key in ((0,"child"),(1,"tag"),(2,"series")):
                kind(index)
                if a.phase=="restore":
                    if state("collections").get("removed")!="1":
                        host.key("alt+m");wait(lambda:state("collections").get("removed")=="1");org_ready()
                elif index==0:
                    choose(known["root"]);host.key("alt+e")
                    wait(lambda:state("collections").get("parent_id")==known["root"])
                choose(known[key]);host.key("alt+s" if a.phase=="restore" else "alt+d")
                window("Collection details");save()
                if a.phase=="restore":
                    host.key("alt+m");wait(lambda:state("collections").get("removed")=="0");org_ready()
            event("group-restore" if a.phase=="restore" else "group-delete",before)
        elif a.phase in ("member-remove","member-restore"):
            before=read_snapshot(catalog)
            for index,key in ((0,"child"),(1,"tag"),(2,"series")):
                kind(index)
                if index==0:
                    choose(known["root"]);host.key("alt+e")
                    wait(lambda:state("collections").get("parent_id")==known["root"])
                choose(known[key])
                if a.phase=="member-remove":
                    host.key("alt+b","Home");member("i")
                else:member("a",7 if index==2 else 3 if index==0 else None)
            event("membership-remove" if a.phase=="member-remove" else "membership-restore",before)
        elif a.phase=="restart":
            before=read_snapshot(catalog)
            host.key("alt+F4");window("Library collections",False)
            host.close();host.launch();host.key("F2","Home","ctrl+shift+c")
            window("Library collections");org_ready()
            require(read_snapshot(catalog)==before,"organization changed after restart")
            event("restart",before)
        host.key("alt+F4");window("Library collections",False)
        if a.previous is not None:
            previous = json.loads(a.previous.read_bytes())
            origin = urlsplit(previous["server"]["base"])
            require(origin.scheme == "https" and origin.hostname == "127.0.0.1" and
                    origin.port is not None and not origin.path and not origin.query and
                    not origin.fragment and origin.username is None and origin.password is None,
                    "predecessor must have a local HTTPS origin")
            # The real account identity includes its root URL. Keep that origin
            # while extending the preceding authentic wire, rather than switching
            # the author to a fresh account after every lifecycle phase.
            factory = relay.ThreadingHTTPServer
            def same_origin(address, handler):
                require(address == ("127.0.0.1", 0), "unexpected relay address")
                return factory(("127.0.0.1", origin.port), handler)
            relay.ThreadingHTTPServer = same_origin
            try:
                dav,user,password=relay.start(a.output/"wire",a.previous)
            finally:
                relay.ThreadingHTTPServer = factory
            require(dav.base == previous["server"]["base"], "author account origin changed")
        else:
            dav,user,password=relay.start(a.output/"wire",a.previous)
        host.key("F2","ctrl+shift+a");window("Account and Sync")
        field("w",dav.base+"/dav/");field("u",user);field("p",password)
        host.key("alt+h","alt+a")
        wait(lambda:state("account").get("bound")=="1" and state("account").get("owner_busy")=="0")
        generation=int(state("account").get("session_generation","0"))
        host.key("alt+s")
        wait(lambda:int(state("account").get("session_generation","0"))>generation and
             state("account").get("session_state") in ("4","5"),180)
        require(state("account").get("session_state")=="4","actual sync failed")
        require(any(r["method"]=="PUT" and "/revisions/" in r["path"] for r in dav.requests)
                or a.phase=="restart","no actual authored revision upload")
        host.key("alt+F4");window("Account and Sync",False)
        host.close()
        projected=read_snapshot(catalog)
        host.launch()
        # A restored reader may leave hidden-shelf viewport restoration pending.
        # Enter the actual shelf before waiting for its existing readiness flags.
        host.key("F2")
        host.wait(lambda current:current.get("reader_visible")==0 and
                  not current.get("shelf_loading") and
                  not current.get("shelf_restoring"),timeout=60)
        require(read_snapshot(catalog)==projected,"author projection changed after real restart")
        host.close()
        write_json(a.output/"projection.json",{**stamp,"host":"gtk","sdk_version":SCOPE["sdk_version"],
            "program_sha256":digest(program),"native_sync_completed":True,"restart_verified":True,
            "snapshot":projected,"snapshot_sha256":hashlib.sha256(canonical(projected)).hexdigest(),
            "complete_product_accepted":False})
        groups=[]
        for group_kind,table,key,item,title in (
            ("shelf","reader_shelves","shelf_id","root","F03 Root"),
            ("shelf","reader_shelves","shelf_id","child","F03 Child"),
            ("tag","reader_tags","tag_id","tag","F03 Tag"),
            ("series","reader_series","series_id","series","F03 Series")):
            row=next(row for row in projected[table] if row[key]==known[item])
            value={"kind":group_kind,"name":title,"deleted":bool(row["deleted"]),
                   "parents":["F03 Root"] if item=="child" else []}
            if item!="root":
                table_member={"shelf":"reader_book_shelves","tag":"reader_book_tags",
                              "series":"reader_book_series"}[group_kind]
                value.update(member_key=known["book_key"],member_title=a.book.stem,
                    member_present=any(x[key]==known[item] and x["book_key"]==known["book_key"]
                                       for x in projected[table_member]))
            groups.append(value)
        write_json(a.output/"expected-groups.json",groups)
        relay.save(dav,a.output/"wire","f03-gtk-"+a.phase,{"identities":known,"events":events})
        dav=None
    finally:
        if host.process and host.process.poll() is None:host.process.kill();host.process.wait(timeout=20)
        if dav:
            dav.server.shutdown();dav.server.server_close()
            (a.output/"wire/key.pem").unlink(missing_ok=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["retained", "relay-first", "relay-return", "snapshot", "author"], required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--package", type=Path, required=True)
    p.add_argument("--command-consumer", type=Path)
    p.add_argument("--inspect", type=Path)
    p.add_argument("--previous", type=Path)
    p.add_argument("--database", type=Path)
    p.add_argument("--phase", choices=["create","delete","restore","member-remove","member-restore","restart"])
    p.add_argument("--profile", type=Path)
    p.add_argument("--book", type=Path)
    a = p.parse_args()
    stamp = identity()
    require(sys.platform.startswith("linux"), "GTK Linux runner required")
    program = a.package / "bin/exreader-linux"
    require(program.is_file(), "actual GTK product missing")
    if a.mode == "author":
        author(a, stamp)
        return
    if a.mode == "snapshot":
        require(a.database is not None, "database required")
        snapshot_receipt("gtk", a.database, program, a.output, "readonly-projection")
        return
    if a.mode == "retained":
        require(a.command_consumer is not None and a.command_consumer.is_file(),
                "unchanged original command consumer required")
        command = [sys.executable, str(ROOT / "tests/linux_host/check_collections_ui.py"),
                   "--payload", str(a.package), "--command-consumer", str(a.command_consumer),
                   "--output", str(a.output)]
    else:
        require(a.previous is not None and a.previous.is_file(), "previous actual wire snapshot required")
        require(a.inspect is not None and a.inspect.is_file(), "public SDK readback consumer required")
        command = [sys.executable, str(ROOT / "tests/reader_windows_gtk_interop/gtk.py"),
                   "--phase", "gtk-first" if a.mode == "relay-first" else "gtk-return",
                   "--previous", str(a.previous), "--out", str(a.output),
                   "--package", str(a.package), "--inspect", str(a.inspect)]
    result = subprocess.run(command, cwd=ROOT, check=False)
    write_json(a.output.parent / (a.output.name + "-driver.json"),
               {**stamp, "host": "gtk", "mode": a.mode, "argv": command,
                "exit_code": result.returncode, "complete_product_accepted": False,
                "scope": "unchanged retained native UI or original two-host tag relay only"})
    require(result.returncode == 0, "original GTK failure retained")
if __name__ == "__main__":
    main()
