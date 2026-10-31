"""Execute installed Android native organization suites and preserve their failure evidence."""
import argparse
import base64
import hashlib
import importlib.util
import os
import json
import shutil
import zipfile
from pathlib import Path
import subprocess
import sys
from identity import ROOT, identity, require, digest, same_identity, write_json, read_snapshot, TABLES, SCOPE, canonical

def adb(*args, timeout=120):
    return subprocess.check_output(["adb", *map(str, args)], stderr=subprocess.STDOUT, timeout=timeout)

def wire_server(previous, fixture):
    """Serve only prior authentic producer bytes using the CA already compiled into this test APK."""
    spec=importlib.util.spec_from_file_location("f03_android_relay",
        ROOT / "tests/reader_windows_gtk_interop/relay.py")
    relay=importlib.util.module_from_spec(spec);spec.loader.exec_module(relay)
    raw=previous.read_bytes(); saved=json.loads(raw)
    same_identity(saved,identity())
    require(saved.get("schema")==1,"unexpected actual wire schema")
    cert,key=fixture/"public/server.crt",fixture/"private/server.key"
    require(cert.is_file() and key.is_file(),"matching build-time fixture TLS material missing")
    user="f03-fixture";password="f03-"+os.urandom(24).hex()
    authorization="Basic "+base64.b64encode((user+":"+password).encode()).decode()
    server=relay.Dav(cert,key,authorization)
    server.certificate_sha256=digest(cert)
    server.previous_sha256=hashlib.sha256(raw).hexdigest()
    server.directories=set(saved["directories"])
    for path,entry in saved["entries"].items():
        body=base64.b64decode(entry["body"],validate=True)
        require(hashlib.sha256(body).hexdigest()==entry["sha256"],"prior wire differs")
        server.entries[path]=body
    server.prior_entries=dict(server.entries);server.prior_directories=set(server.directories)
    return relay,server,{"root":server.base+"/dav/","user":user,"password":password}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--host-apk", type=Path, required=True)
    p.add_argument("--owner-test-apk", type=Path, required=True)
    p.add_argument("--ui-apk", type=Path, required=True)
    p.add_argument("--ui-test-apk", type=Path, required=True)
    p.add_argument("--new-ui-class", action="store_true")
    p.add_argument("--reports", type=Path)
    p.add_argument("--mode", choices=["retained","receive"], default="retained")
    p.add_argument("--expectations", type=Path)
    p.add_argument("--projection-expectations", type=Path)
    p.add_argument("--connection", type=Path)
    p.add_argument("--wire", type=Path)
    p.add_argument("--tls-fixture", type=Path)

    a = p.parse_args()
    stamp = identity()
    a.output.mkdir(parents=True, exist_ok=False)
    passed = False
    server = None
    reversed_port = None
    names = ("host_apk", "owner_test_apk", "ui_apk", "ui_test_apk")
    apks = {name: digest(getattr(a, name)) for name in names}
    try:
        if a.mode == "retained":
            require(a.reports is not None and a.reports.is_dir(), "original connected-test XML required")
            shutil.copytree(a.reports, a.output / "reports")
        (a.output / "apks").mkdir()
        shutil.copyfile(a.host_apk, a.output / "apks/app-debug.apk")
        for name in names:
            adb("install", "-r", "-t", getattr(a, name))
        installed = adb("shell", "pm", "path", "org.exreader.host").decode().strip()
        require(installed.startswith("package:") and "\n" not in installed, "unexpected host APK layout")
        adb("pull", installed[len("package:"):], a.output / "installed.apk")
        require(digest(a.output / "installed.apk") == apks["host_apk"], "installed host differs")
        if a.mode == "receive":
            require(a.projection_expectations is not None, "identity-bound author projection required")
            expected_receipt=json.loads(a.projection_expectations.read_text(encoding="utf-8"))
            same_identity(expected_receipt,stamp)
            require(expected_receipt.get("sdk_version")==SCOPE["sdk_version"], "author SDK differs")
            require(a.expectations is not None and (a.connection is not None or
                    (a.wire is not None and a.tls_fixture is not None)),
                    "actual producer expectations and fixture connection required")
            groups = json.loads(a.expectations.read_text(encoding="utf-8"))
            if a.wire is not None:
                require(a.tls_fixture is not None, "matching build-time TLS fixture required")
                ca=(a.tls_fixture/"public/ca.crt").read_bytes()
                with zipfile.ZipFile(a.host_apk) as archive:
                    matches=[name for name in archive.namelist()
                             if name.endswith("/host_sync_fixture_ca.crt")]
                    require(len(matches)==1,"built APK fixture trust anchor not identifiable")
                    require(archive.read(matches[0])==ca,"server CA differs from actual built APK")
                relay, server, config = wire_server(a.wire, a.tls_fixture)
                reversed_port = "tcp:" + str(server.server.server_port)
                adb("reverse", reversed_port, reversed_port)
            else:
                config = json.loads(a.connection.read_text(encoding="utf-8"))
            require(config["root"].startswith("https://127.0.0.1:"), "local fixture only")
            require(isinstance(groups, list) and groups, "actual expected group IDs required")
            command = ["shell","am","instrument","-w","-r","-e","disableAnalytics","true",
                       "-e","class","org.exreader.host.uitest.OrganizationInteropTest#receivedOrganization",
                       "-e","f03_expected_groups",json.dumps(groups,ensure_ascii=False),
                       "-e","f03_dav_root",config["root"],
                       "-e","f03_dav_username",config["user"],
                       "-e","f03_dav_password",config["password"]]
            for key, value in stamp.items():
                command += ["-e","exr_"+key,value]
            raw = adb(*command, "org.exreader.host.uitest.test/androidx.test.runner.AndroidJUnitRunner",
                      timeout=1200)
            # Never emit the fixture password or connection config in evidence.
            require(config["password"].encode() not in raw, "credential leaked into instrumentation")
            (a.output / "receive-instrumentation.txt").write_bytes(raw)
            adb("pull","/sdcard/Android/data/org.exreader.host.uitest/files/f03-received-evidence",
                a.output / "received")
            receipt = json.loads((a.output / "received/result.json").read_text(encoding="utf-8"))
            same_identity(receipt, stamp)
            require(receipt.get("accepted") is True and receipt.get("native_sync_completed") is True and
                    receipt.get("restart_verified") is True, "actual receiver UI/restart failed")
            require(b"FAILURES" not in raw and b"OK (1 test)" in raw, "receiver test failed")
            # Pull a stopped real application's DB plus its WAL; never write its data.
            adb("shell","am","force-stop","org.exreader.host")
            database=a.output/"native-catalog"/"reader-catalog.db"
            database.parent.mkdir()
            database.write_bytes(adb("exec-out","run-as","org.exreader.host",
                                     "cat","files/reader-catalog.db"))
            for suffix in ("-wal","-shm"):
                remote="files/reader-catalog.db"+suffix
                exists=subprocess.run(["adb","shell","run-as","org.exreader.host","test","-f",remote],
                                      capture_output=True,check=False)
                if exists.returncode==0:
                    Path(str(database)+suffix).write_bytes(
                        adb("exec-out","run-as","org.exreader.host","cat",remote))
            actual=read_snapshot(database);expected=expected_receipt["snapshot"]
            for table in TABLES:
                require(actual[table]==expected[table],"Android projection differs: "+table)
            original={r["id"]:r["body"] for r in expected["revisions"]}
            received={r["id"]:r["body"] for r in actual["revisions"]}
            require(all(received.get(k)==v for k,v in original.items()),"Android exact revisions differ")
            write_json(a.output/"projection.json",{**stamp,"host":"android",
                "sdk_version":SCOPE["sdk_version"],"program_sha256":apks["host_apk"],
                "native_sync_completed":True,"restart_verified":True,"snapshot":actual,
                "snapshot_sha256":hashlib.sha256(canonical(actual)).hexdigest(),
                "complete_product_accepted":False})
            if server is not None:
                require(any(r["method"]=="GET" and "/revisions/" in r["path"] and
                            r["authenticated"] for r in server.requests), "no native revision download")
                relay.save(server,a.output/"wire","f03-android-receive",{"native_ui_receipt":"../received/result.json"})
                server=None
            passed = True
            return
        common = []
        for key, value in stamp.items():
            common += ["-e", key, value]
        raw = adb("shell", "am", "instrument", "-w", "-r", *common,
                  "org.exreader.host.test/org.exreader.host.OrganizationTest", timeout=900)
        (a.output / "instrumentation.txt").write_bytes(raw)
        native = json.loads(adb("exec-out", "run-as", "org.exreader.host",
                                "cat", "files/organization-report.json"))
        same_identity(native, stamp)
        write_json(a.output / "device-report.json", native)
        raw = adb("shell", "am", "instrument", "-w", "-r", "-e", "phase", "seed-ui",
                  *common, "org.exreader.host.test/org.exreader.host.OrganizationTest", timeout=900)
        (a.output / "seed-ui.txt").write_bytes(raw)
        # Previous evidence is deliberately not removed: dirty runner evidence is rejected.
        selected = "OrganizationInteropTest" if a.new_ui_class else "OrganizationWalkthroughTest"
        raw = adb("shell", "am", "instrument", "-w", "-r", "-e", "disableAnalytics", "true",
                  "-e", "class", "org.exreader.host.uitest." + selected + "#organize",
                  "-e", "exr_source_sha", stamp["source_sha"], "-e", "exr_run_id", stamp["run_id"],
                  "-e", "exr_attempt", stamp["attempt"],
                  "org.exreader.host.uitest.test/androidx.test.runner.AndroidJUnitRunner", timeout=1200)
        (a.output / "ui-instrumentation.txt").write_bytes(raw)
        adb("pull", "/sdcard/Android/data/org.exreader.host.uitest/files/organization-evidence",
            a.output / "ui")
        adb("pull", "/sdcard/Android/data/org.exreader.host/files/organization-tests",
            a.output / "phases")
        require(b"FAILURES!!!" not in raw and b"OK (1 test)" in raw, "native UI suite did not pass")
        # Original all-exits checker is a separate mandatory gate once all retained reports are
        # assembled by the producer; the focused runner must not claim those absent reports.
        subprocess.run([sys.executable, str(ROOT / "tools/check_reader_organization_android.py"),
                        "--evidence", str(a.output), "--all-exits"], cwd=ROOT, check=True)
        passed = True
    finally:
        if server is not None:
            write_json(a.output/"failed-requests.json",server.requests)
            server.server.shutdown();server.server.server_close()
        if reversed_port is not None:
            subprocess.run(["adb","reverse","--remove",reversed_port], check=False)
        write_json(a.output / "driver-result.json",
                   {**stamp, "host": "android", "apk_sha256": apks,
                    "native_lifecycle_passed": passed, "mode": a.mode, "complete_product_accepted": False,
                    "six_host_wire_verified": False,
                    "scope": "actual retained native organization lifecycle, not cross-host sync"})
if __name__ == "__main__":
    main()
