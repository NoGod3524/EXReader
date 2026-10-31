"""Run real retained Windows organization/relay UI. No manufactured revision or success."""
import argparse
import importlib.util
import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
from identity import ROOT, identity, require, snapshot_receipt, write_json, read_snapshot, canonical, digest, TABLES, SCOPE, same_identity

def receive(a, stamp):
    """A fresh real Windows profile receives authentic GTK/Apple wire and survives restart."""
    require(a.previous is not None and a.expectations is not None, "wire and author snapshot required")
    a.output.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(ROOT / "tests/reader_windows_gtk_interop"))
    spec = importlib.util.spec_from_file_location("f03_windows_interop",
        ROOT / "tests/reader_windows_gtk_interop/windows.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    author_receipt = json.loads(a.expectations.read_text(encoding="utf-8"))
    same_identity(author_receipt, stamp)
    require(author_receipt.get("sdk_version") == SCOPE["sdk_version"], "author SDK differs")
    expected = author_receipt["snapshot"]
    app = None
    dav, user, password = module.relay.start(a.output / "wire", a.previous)
    exe, font = (a.package / "EXReader.exe").resolve(), (a.package / "Reader.otf").resolve()
    try:
        app = module.ui.App(exe, font, a.output / "profile")
        app.wait_initial_shelf();app.wait_idle()
        dialog = app.open_account()
        app.fill(dialog,root=dav.base+"/dav/",user=user,password=password,remember=False)
        app.apply(dialog,"仅本次会话");app.close_account(dialog)
        dialog=app.open_account();app.run_sync(dialog);app.close_account(dialog);app.wait_idle()
        database=Path(str(app.db)+".product.sqlite")
        def projected():
            if not database.is_file():return False
            value=read_snapshot(database)
            return all(value[table] == expected[table] for table in TABLES)
        app.wait(projected,timeout=120)
        actual=read_snapshot(database)
        for table in TABLES:
            require(actual[table] == expected[table], "Windows projection differs: "+table)
        prior={row["id"]:row["body"] for row in expected["revisions"]}
        received={row["id"]:row["body"] for row in actual["revisions"]}
        require(all(received.get(key)==value for key,value in prior.items()), "Windows lost authentic revisions")
        require(any(r["method"]=="GET" and "/revisions/" in r["path"] and r["authenticated"]
                    for r in dav.requests), "no authenticated native receive")
        module.ui.M.screenshot(app.window,a.output/"received.bmp")
        # An actual process exit/relaunch, not a fresh DB or replayed receipt.
        app.process.kill();app.process.wait(timeout=20)
        app=module.ui.App(exe,font,a.output/"profile",existing=True)
        app.wait_initial_shelf();app.wait_idle()
        require(read_snapshot(database)==actual,"Windows restart projection changed")
        module.ui.M.screenshot(app.window,a.output/"restarted.bmp")
        value={**stamp,"host":"windows","sdk_version":SCOPE["sdk_version"],
               "program_sha256":digest(exe),"native_sync_completed":True,"restart_verified":True,
               "snapshot":actual,"snapshot_sha256":hashlib.sha256(canonical(actual)).hexdigest(),
               "complete_product_accepted":False}
        write_json(a.output/"projection.json",value)
        module.relay.save(dav,a.output/"wire","f03-windows-receive",{"projection":"../projection.json"})
        dav=None
    finally:
        if app and app.process.poll() is None:app.process.kill();app.process.wait(timeout=20)
        if dav:
            write_json(a.output/"failed-requests.json",dav.requests)
            dav.server.shutdown();dav.server.server_close()
            (a.output/"wire/key.pem").unlink(missing_ok=True)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["retained", "relay-first", "relay-return", "snapshot", "receive"], required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--package", type=Path, required=True)
    p.add_argument("--fixtures", type=Path)
    p.add_argument("--probe", type=Path)
    p.add_argument("--command-consumer", type=Path)
    p.add_argument("--revision-consumer", type=Path)
    p.add_argument("--previous", type=Path)
    p.add_argument("--database", type=Path)
    p.add_argument("--expectations", type=Path)
    a = p.parse_args()
    stamp = identity()
    require(os.name == "nt", "actual Windows runner required")
    exe = a.package / "EXReader.exe"
    require(exe.is_file(), "missing actual product executable")
    if a.mode == "receive":
        receive(a, stamp)
        return
    if a.mode == "snapshot":
        require(a.database is not None, "database required")
        snapshot_receipt("windows", a.database, exe, a.output, "readonly-projection")
        return
    require(a.probe is not None and a.probe.is_file(), "installed public readback probe required")
    if a.mode == "retained":
        require(all(x is not None and x.exists() for x in
                    (a.fixtures, a.command_consumer, a.revision_consumer)), "retained inputs missing")
        command = [sys.executable, str(ROOT / "tests/reader_windows_import_organize/check_ui.py"),
                   "--candidate", str(exe), "--font", str(a.package / "Reader.otf"),
                   "--fixtures", str(a.fixtures), "--cloud-probe", str(a.probe),
                   "--command-consumer", str(a.command_consumer),
                   "--revision-consumer", str(a.revision_consumer), "--output", str(a.output)]
    else:
        command = [sys.executable, str(ROOT / "tests/reader_windows_gtk_interop/windows.py"),
                   "--phase", "windows-first" if a.mode == "relay-first" else "windows-return",
                   "--out", str(a.output), "--package", str(a.package), "--probe", str(a.probe)]
        if a.mode == "relay-return":
            require(a.previous is not None and a.previous.is_file(), "real predecessor snapshot required")
            command += ["--previous", str(a.previous)]
    result = subprocess.run(command, cwd=ROOT, check=False)
    write_json(a.output.parent / (a.output.name + "-driver.json"),
               {**stamp, "host": "windows", "mode": a.mode, "argv": command,
                "exit_code": result.returncode, "complete_product_accepted": False,
                "scope": "unchanged native suite or original Windows/GTK tag relay only"})
    require(result.returncode == 0, "retained Windows failure; do not waive")
if __name__ == "__main__":
    main()
