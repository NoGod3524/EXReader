# SPDX-License-Identifier: MIT
"""Actions-only native Apple reception of actual same-run Windows peer histories."""
import argparse
import base64
import secrets
import stat
import sqlite3
import signal
import threading
import time
import hashlib
import json
import plistlib
import os
from pathlib import Path
import subprocess
import sys
from fixture import Store, write_role_receipt

SWIFT = r'''
import XCTest
final class F05RecoveryUITests: XCTestCase {
    private var app = XCUIApplication()
    private func node(_ id:String)->XCUIElement {
        app.descendants(matching:.any).matching(identifier:id).firstMatch
    }
    private func wait(_ body:()->Bool)->Bool {
        let end=Date().addingTimeInterval(120)
        while Date()<end { if body(){return true}; RunLoop.current.run(until:Date().addingTimeInterval(0.15)) }
        return body()
    }
    private func tap(_ id:String) {
        let target=node(id)
        XCTAssertTrue(target.waitForExistence(timeout:60),id)
        for _ in 0..<8 {
            if target.isHittable { break }
            let form=node("account.form")
            if !form.exists { break }
            let earlier=target.frame.midY < form.frame.midY
#if os(macOS)
            form.scroll(byDeltaX:0,deltaY:earlier ? 260 : -260)
#else
            if earlier { form.swipeDown() } else { form.swipeUp() }
#endif
        }
        XCTAssertTrue(wait{target.isEnabled && target.isHittable},id)
        target.tap()
    }
    private func text(_ id:String)->String {
        let item=node(id)
        return item.label.isEmpty ? (item.value as? String ?? "") : item.label
    }
    override func setUpWithError() throws {
        continueAfterFailure=false
        app.launchArguments=["-EXRUITestFixtures","1"]
        app.launch()
        XCTAssertTrue(wait{self.node("account.choose").exists || self.node("reader.back").exists})
        if node("reader.back").exists { tap("reader.back") }
        XCTAssertTrue(node("account.choose").waitForExistence(timeout:90))
    }
    override func tearDownWithError() throws {
        let screen=XCTAttachment(screenshot:app.screenshot())
        screen.name="f05-"+name;screen.lifetime = .keepAlways;add(screen)
        let receipt=XCTAttachment(string:app.debugDescription)
        receipt.name="native-ui-"+name;receipt.lifetime = .keepAlways;add(receipt)
        app.terminate()
    }
    private func sync() {
        tap("account.sync.start")
        XCTAssertTrue(wait{self.text("account.sync.state")=="本轮扫描完成"})
        XCTAssertTrue(wait{self.text("account.receive.state").hasPrefix("已接收 ")})
        XCTAssertFalse(node("account.receive.cancel").exists)
    }
    private func openBook() {
        let book=app.buttons.matching(NSPredicate(format:"identifier BEGINSWITH 'library.book.'")).firstMatch
        XCTAssertTrue(book.waitForExistence(timeout:60))
        XCTAssertTrue(wait{book.isEnabled && book.isHittable})
        book.tap()
        XCTAssertTrue(node("reader.back").waitForExistence(timeout:90))
        XCTAssertTrue(wait{!self.node("reader.busy").exists})
        XCTAssertTrue(wait{self.node("reader.page").label.contains("F05 original remains readable")},
            "actual native rendered text must match retained original")
    }
    private func gateReached() -> Bool {
        guard let root=ProcessInfo.processInfo.environment["F05_ROOT"],
              let url=URL(string:root.replacingOccurrences(of:"/dav/",with:"/__f05_gate")) else {return false}
        let done=expectation(description:"read-only fixture boundary")
        var reached=false
        var request=URLRequest(url:url)
        let env=ProcessInfo.processInfo.environment
        let pair=(env["F05_USER"] ?? "")+":"+(env["F05_PASSWORD"] ?? "")
        request.setValue("Basic "+Data(pair.utf8).base64EncodedString(),forHTTPHeaderField:"Authorization")
        let task=URLSession.shared.dataTask(with:request){data,_,_ in
            if let data,let object=try? JSONSerialization.jsonObject(with:data) as? [String:Bool] {
                reached=object["original_get_blocked"] == true
            }
            done.fulfill()
        }
        task.resume()
        wait(for:[done],timeout:5)
        return reached
    }
    private func cancelRealReceiveThenRetry() {
        let book=app.buttons.matching(NSPredicate(format:"identifier BEGINSWITH 'library.book.'")).firstMatch
        XCTAssertTrue(book.waitForExistence(timeout:60))
        book.tap()
        XCTAssertTrue(wait{self.gateReached()},"native original GET must reach held boundary")
        tap("library.cancel")
        XCTAssertTrue(wait{!self.node("library.busy").exists})
        XCTAssertTrue(book.waitForExistence(timeout:60))
    }
    func test01BaselineOriginal() throws {
        let root=try XCTUnwrap(ProcessInfo.processInfo.environment["F05_ROOT"])
        tap("account.choose")
        let field=node("account.root")
        XCTAssertTrue(field.waitForExistence(timeout:30))
        XCTAssertFalse((field.value as? String ?? "").hasPrefix("http"),"fresh test profile required")
        field.tap();field.typeText(root+"\n")
        let username=try XCTUnwrap(ProcessInfo.processInfo.environment["F05_USER"])
        let password=try XCTUnwrap(ProcessInfo.processInfo.environment["F05_PASSWORD"])
        tap("account.username");node("account.username").typeText(username)
        tap("account.password");node("account.password").typeText(password)
        tap("account.connect")
        XCTAssertTrue(wait{self.node("account.choose").label=="云盘书库，"+root})
        sync()
        XCTAssertTrue(text("account.receive.state").contains("待处理冲突 0 项"))
    }
    func test02CacheMissReceiveCancel() { cancelRealReceiveThenRetry() }
    func test03RetryOriginal() { openBook() }
    func test04ReceiveRealConcurrentHeads() {
        sync()
        XCTAssertTrue(text("account.receive.state").contains("待处理冲突 1 项"),
            "actual native conflict must be visible; never select one head")
        openBook()
    }
    func test06UnknownPutAckProcessKill() {
        tap("library.organization")
        tap("organization.kind.tag")
        tap("organization.create")
        tap("organization.name")
        node("organization.name").typeText("F05 Apple uncertain")
        tap("organization.save")
        let row=app.buttons.matching(NSPredicate(format:"identifier BEGINSWITH 'organization.group.' AND label == 'F05 Apple uncertain'")).firstMatch
        XCTAssertTrue(row.waitForExistence(timeout:60))
        tap("organization.close")
        tap("account.sync.start")
        // The external fixture monitor sends SIGKILL only after authenticated
        // native PUT bytes are committed while its acknowledgement is held.
        XCTAssertTrue(wait{self.app.state == .notRunning})
        app.launch()
        XCTAssertTrue(node("account.sync.start").waitForExistence(timeout:90))
        sync()
    }
    func test05OfflineReopenOriginal() {
        // Server is offline before this new actual process starts.
        openBook()
    }
}
'''

def main():
    if os.environ.get("GITHUB_ACTIONS")!="true" or sys.platform!="darwin":
        raise RuntimeError("Apple Actions only")
    p=argparse.ArgumentParser()
    p.add_argument("--prepare",action="store_true")
    p.add_argument("--tests",type=Path,required=True)
    p.add_argument("--platform",choices=("macos","iphone","ipad"),required=True)
    p.add_argument("--udid")
    p.add_argument("--peer",type=Path)
    p.add_argument("--container",type=Path)
    p.add_argument("--app",type=Path)
    p.add_argument("--certificate",type=Path)
    p.add_argument("--key",type=Path)
    p.add_argument("--output",type=Path)
    p.add_argument("command",nargs=argparse.REMAINDER)
    a=p.parse_args()
    if a.prepare:
        a.tests.mkdir(parents=True,exist_ok=False)
        (a.tests/"F05RecoveryUITests.swift").write_text(SWIFT)
        return
    if any(v is None for v in (a.peer,a.certificate,a.key,a.output,a.app)):
        raise ValueError("peer/TLS/output/actual app bundle required")
    command=a.command[1:] if a.command[:1]==["--"] else a.command
    if not command or command[0]!="xcodebuild":raise ValueError("actual xcodebuild required")
    if any("-only-testing" in v or "-resultBundlePath" in v for v in command):
        raise ValueError("driver owns exact phase/test result selection")
    a.output.mkdir(parents=True,exist_ok=False)
    contract=json.loads((a.peer/"peer-contract.json").read_text())
    if contract["entity_kind"]!="book":raise AssertionError("Apple book receiver requires book peers")
    user,password="f05",secrets.token_hex(24)
    authorization="Basic "+base64.b64encode((user+":"+password).encode()).decode()
    server,origin=None,None
    report={"source":os.environ["GITHUB_SHA"],"run":os.environ["GITHUB_RUN_ID"],
            "attempt":os.environ["GITHUB_RUN_ATTEMPT"],"host":a.platform,
            "F05_accepted":False,"cases":[],"producer":None,
            "simultaneous_online_peers":False,"generated_fixture_credentials_only":True}
    trusted=False
    app_folder=None
    monitor=None
    monitor_stop=threading.Event()
    label="macOS" if a.platform=="macos" else "iOS"
    normalized,claim_refs,evidence=[],{},["coverage.json"]
    program_hash=None
    previous_wire={}
    def collect_phase(name,bundle):
        nonlocal program_hash,previous_wire
        info_path=a.app/("Contents/Info.plist" if a.platform=="macos" else "Info.plist")
        info=plistlib.loads(info_path.read_bytes())
        if info.get("EXRSourceSHA")!=os.environ["GITHUB_SHA"] or info.get("EXRSDKVersion")!="3.42.0" or info.get("CFBundleIdentifier")!="org.exreader.host":
            raise AssertionError("actual built Apple app source/SDK/bundle identity mismatch")
        binary=a.app/("Contents/MacOS/EXReaderHost" if a.platform=="macos" else "EXReaderHost")
        content=binary.read_bytes()
        current=hashlib.sha256(content).hexdigest()
        if program_hash is not None and current!=program_hash:
            raise AssertionError("Apple phase changed native executable")
        if a.platform!="macos":
            installed=Path(subprocess.check_output(["xcrun","simctl","get_app_container",
                a.udid,"org.exreader.host","app"],text=True).strip())
            if hashlib.sha256((installed/"EXReaderHost").read_bytes()).hexdigest()!=current:
                raise AssertionError("actual installed simulator app differs from retained build")
        program_hash=current
        (a.output/"program.bin").write_bytes(content)
        (a.output/"program-info.plist").write_bytes(info_path.read_bytes())
        payload=json.loads(subprocess.check_output(["xcrun","xcresulttool","get","test-results","tests",
            "--path",str(bundle),"--format","json"],text=True))
        cases=[]
        def walk(node):
            if node.get("nodeType")=="Test Case":cases.append(node)
            for child in node.get("children",[]):walk(child)
        for node in payload["testNodes"]:walk(node)
        if len(cases)!=1 or cases[0].get("result")!="Passed" or name not in cases[0].get("name",""):
            raise AssertionError("actual xcresult missing, skipped, failed or wrong phase")
        attachments=a.output/(name+"-attachments")
        subprocess.run(["xcrun","xcresulttool","export","attachments","--path",str(bundle),
                        "--output-path",str(attachments)],check=True)
        listing=json.loads((attachments/"manifest.json").read_text())
        roles=set()
        for group in listing:
            for row in group["attachments"]:
                leaf=row["exportedFileName"]
                if Path(leaf).name!=leaf:raise AssertionError("unsafe xcresult attachment path")
                path=attachments/leaf
                label=row["suggestedHumanReadableName"]
                if label.startswith("f05-"):
                    if not path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
                        raise AssertionError("native XCTest screenshot is not PNG")
                    roles.add("screen")
                elif label.startswith("native-ui-"):
                    if not path.read_text().strip():raise AssertionError("native UI hierarchy absent")
                    roles.add("hierarchy")
        if roles!={"screen","hierarchy"}:raise AssertionError("both native UI attachments required")
        members=[]
        for folder in (bundle,attachments):
            for path in folder.rglob("*"):
                if path.is_symlink():raise AssertionError("symlink xcresult evidence refused")
                if path.is_file():members.append(path.relative_to(a.output).as_posix())
        members.extend([name+".log","program-info.plist"])
        evidence.extend(members)
        wire={path:hashlib.sha256(body).hexdigest() for path,body in server.entries.items()}
        if any(wire.get(path)!=digest for path,digest in previous_wire.items()):
            raise AssertionError("Apple phase changed immutable peer bytes")
        previous_wire=wire
        report["cases"][-1]["xcresult"]={"test":cases[0]["name"],"result":"Passed",
            "members":members,"program_sha256":current,"immutable_wire_inventory":wire}
        return members
    def finish_case(case_id,claims,members,**semantic):
        raw=report["cases"][-1]
        normalized.append({"id":case_id,"outcome":"passed",
            "actual_host_actions":True,"receiver_database_injection":False,
            "original_identity_preserved":True,"revision_bytes_preserved":True,
            "peer_wire_observed":any(row["authenticated"] and row["method"] in ("PUT","GET","PROPFIND")
                and row["path"]!="/__f05_gate" for row in server.requests[raw["requests_start"]:raw["requests_end"]]),
            "source_evidence":["coverage.json",*members],
            "source_pointer":"/cases/"+str(len(report["cases"])-1),**semantic})
        for claim,role in claims.items():
            claim_refs.setdefault(claim,[]).append({"case_id":case_id,"role":role})
    def readback(folder):
        with sqlite3.connect((folder/"library.sqlite").resolve().as_uri()+"?mode=ro",uri=True) as db:
            originals=[{"id":row[0],"bytes":len(row[1]),"sha256":hashlib.sha256(row[1]).hexdigest()}
                       for row in db.execute("SELECT id,source FROM books ORDER BY id")]
        with sqlite3.connect((folder/"reader-catalog.db").resolve().as_uri()+"?mode=ro",uri=True) as db:
            revisions=[json.loads(row[0]) for row in db.execute("SELECT body_json FROM reader_revisions")]
            pending=db.execute("SELECT count(*) FROM reader_outbox").fetchone()[0]
        selected=[row for row in revisions if row["entity_kind"]=="book"
                  and row["entity_key"]==contract["entity_key"]]
        heads={row["id"] for row in selected}-{parent for row in selected for parent in row["parents"]}
        return {"originals":originals,"records":selected,"heads":sorted(heads),"outbox":pending,
                "observation":"actual app terminated; readonly SDK and product catalog"}
    try:
        server=Store(a.certificate,a.key,authorization)
        origin=server.expose_checkpoint(a.peer/contract["baseline"])
        report["producer"]=origin["author"]
        if a.platform=="macos":
            expected_container=(Path.home()/"Library/Application Support/EXReader").resolve()
            if a.container is None or a.container.resolve()!=expected_container:
                raise AssertionError("macOS container must be actual fixed EXReader app support root")
            trusted=True
            subprocess.run(["sudo","security","add-trusted-cert","-d","-r","trustRoot",
                "-k","/Library/Keychains/System.keychain",str(a.certificate)],check=True,capture_output=True)
            trusted=True
        if a.platform!="macos":
            if not a.udid:raise ValueError("actual simulator UDID required")
            subprocess.run(["xcrun","simctl","keychain",a.udid,"add-root-cert",str(a.certificate)],check=True)
        for number,name in enumerate(("test01BaselineOriginal","test02CacheMissReceiveCancel","test03RetryOriginal","test04ReceiveRealConcurrentHeads","test05OfflineReopenOriginal","test06UnknownPutAckProcessKill")):
            if number==1:
                if a.platform=="macos":
                    if a.container is None:raise ValueError("isolated actual app container required")
                    container=a.container.resolve()
                else:
                    container=Path(subprocess.check_output(["xcrun","simctl","get_app_container",
                        a.udid,"org.exreader.host","data"],text=True).strip()).resolve()
                leaf=contract["entity_key"].split(":",1)[1]+"."+contract["entity_key"].split(":",1)[0]
                matches=list(container.rglob("sync/"+leaf))
                if len(matches)!=1:raise AssertionError("one exact test-profile cache required")
                cache=matches[0]
                if cache.is_symlink() or not stat.S_ISREG(cache.stat().st_mode):
                    raise AssertionError("unsafe cache identity")
                content=cache.read_bytes()
                if hashlib.sha256(content).hexdigest()!=contract["entity_key"].split(":",1)[1]:
                    raise AssertionError("cache bytes differ from actual peer original")
                app_folder=cache.parent.parent
                baseline=readback(app_folder)
                if baseline["originals"] or set(baseline["heads"])!=set(contract["common_parent"]):
                    raise AssertionError("baseline received catalog must not import SDK original before native open")
                report["baseline_readback"]=baseline
                before=cache.stat()
                quarantine=cache.parent.parent/("f05-cache-quarantine-"+secrets.token_hex(12))
                quarantine.mkdir(mode=0o700)
                isolated=quarantine/leaf
                cache.rename(isolated)
                after=isolated.stat()
                if (before.st_ino,before.st_dev,before.st_size)!=(after.st_ino,after.st_dev,after.st_size):
                    raise AssertionError("cache isolation did not preserve inode/size")
                (a.output/"quarantined-cache.bin").write_bytes(isolated.read_bytes())
                report["cache_fault"]={"path":str(cache),"quarantine":str(isolated),
                    "sha256":hashlib.sha256(content).hexdigest(),"bytes":len(content),
                    "inode":before.st_ino,"device":before.st_dev,
                    "owner_state":"prior XCTest teardown terminated actual application",
                    "sdk_original_untouched":True,"restored_before_retry":False}
                server.hold_get=True;server.get_blocked.clear();server.release.clear()
            if number==3:server.expose_checkpoint(a.peer/contract["remote_conflict"])
            if number==4:server.offline=True
            monitor=None;monitor_errors=[];kill_receipt={}
            if number==5:
                server.offline=False
                server.hold_put=True;server.put_committed.clear();server.release.clear()
                def kill_at_commit():
                    try:
                        deadline=time.monotonic()+180
                        while not server.put_committed.wait(.1):
                            if monitor_stop.is_set():return
                            if time.monotonic()>=deadline:
                                raise AssertionError("native PUT never reached committed/unknown-ack boundary")
                        if monitor_stop.is_set():return
                        pids=subprocess.check_output(["pgrep","-x","EXReaderHost"],text=True).split()
                        if len(pids)!=1:raise AssertionError("unique actual EXReaderHost PID required")
                        pid=int(pids[0])
                        command_line=subprocess.check_output(["ps","-p",str(pid),"-o","command="],text=True).strip()
                        executable_suffix="/EXReaderHost.app/Contents/MacOS/EXReaderHost" if a.platform=="macos" else "/EXReaderHost.app/EXReaderHost"
                        if executable_suffix not in command_line:
                            raise AssertionError("unexpected host PID executable")
                        kill_receipt.update({"pid":pid,"command":command_line,
                            "signal":"SIGKILL","wire_commits_before_kill":list(server.commits),
                            "immutable_before":{k:hashlib.sha256(v).hexdigest() for k,v in server.entries.items()}})
                        os.kill(pid,signal.SIGKILL)
                        server.release.set()
                        end=time.monotonic()+120
                        while time.monotonic()<end and not monitor_stop.is_set():
                            found=subprocess.run(["pgrep","-x","EXReaderHost"],capture_output=True,text=True)
                            new=[int(value) for value in found.stdout.split() if int(value)!=pid]
                            if len(new)==1:
                                reopened=subprocess.check_output(["ps","-p",str(new[0]),"-o","command="],text=True).strip()
                                if executable_suffix not in reopened:raise AssertionError("foreign reopened process")
                                kill_receipt.update({"reopened_pid":new[0],"reopened_command":reopened})
                                break
                            time.sleep(.05)
                        if "reopened_pid" not in kill_receipt:
                            raise AssertionError("actual replacement Apple process not observed")
                    except BaseException as error:monitor_errors.append(repr(error))
                    finally:server.release.set()
                monitor=threading.Thread(target=kill_at_commit,daemon=True);monitor.start()
            start=len(server.requests)
            argv=command+["-only-testing:EXReaderHostUITests-"+label+"/F05RecoveryUITests/"+name,
                          "-resultBundlePath",str(a.output/(name+".xcresult"))]
            try:
                with (a.output/(name+".log")).open("wb") as log:
                    done=subprocess.run(argv,stdout=log,stderr=subprocess.STDOUT,timeout=600,
                        env=dict(os.environ,TEST_RUNNER_F05_ROOT=server.root,
                            TEST_RUNNER_F05_USER=user,TEST_RUNNER_F05_PASSWORD=password))
            finally:
                safe=(a.output/(name+".log")).read_text(errors="replace").replace(password,"<fixture-secret>").replace(authorization,"<fixture-auth>")
                (a.output/(name+".log")).write_text(safe,encoding="utf-8")
                print(safe,flush=True)
            report["cases"].append({"test":name,"exit":done.returncode,"requests_start":start,
                                    "requests_end":len(server.requests),"argv":argv})
            if monitor is not None:
                monitor.join(190)
                if monitor.is_alive() or monitor_errors:
                    raise AssertionError("kill fixture failed: "+repr(monitor_errors))
                if not kill_receipt:raise AssertionError("missing actual process kill receipt")
                if any(k not in server.entries or hashlib.sha256(server.entries[k]).hexdigest()!=v
                       for k,v in kill_receipt["immutable_before"].items()):
                    raise AssertionError("uncertain retry changed immutable committed wire")
                report["cases"][-1]["kill"]=kill_receipt
            if done.returncode:raise AssertionError("actual Apple UI failed: "+name)
            members=collect_phase(name,a.output/(name+".xcresult"))
            if number==1 and not server.get_blocked.is_set():
                raise AssertionError("real cache-miss receive gate never reached")
            if number>=1:
                observed=readback(app_folder)
                expected=contract["common_parent"] if number<=2 else contract["competing_heads"]
                if set(observed["heads"])!=set(expected):
                    raise AssertionError("actual retained Apple book heads differ")
                if number==1 and observed["originals"]:
                    raise AssertionError("cancel before original response published SDK original")
                if number>1 and (len(observed["originals"])!=1 or observed["originals"][0]["sha256"]!=contract["entity_key"].split(":",1)[1]):
                    raise AssertionError("actual Apple SDK original is absent, duplicate, or changed")
                if number==5 and observed["outbox"]!=0:
                    raise AssertionError("killed native PUT was not acknowledged on actual retry")
                report["cases"][-1]["readback"]=observed
            server.release.set()
            if number==4 and len(server.requests)!=start:
                raise AssertionError("offline reopening requested controlled sync endpoint")
            if number==2:
                finish_case("cancel_receive_retry",{"cancel_retry":"local"},members,
                    remote_boundary=True,cancel_layer="receive",native_cancel_observed=True,
                    explicit_retry_passed=True,source_pointers=["/cases/1","/cases/2"])
            elif number==3:
                finish_case("concurrent_heads_preserved",{"concurrent_heads_preserved":"receiver"},members,
                    competing_heads=contract["competing_heads"],final_heads=observed["heads"],
                    conflict_displayed=True,explicit_user_resolution=False)
            elif number==4:
                finish_case("restart_offline_read",{"offline_read":"local"},members,
                    reopened_host_readable=True,network_requests=0,
                    network_measurement="controlled F05 sync endpoint only, not whole OS")
            elif number==5:
                finish_case("kill_commit_ack_replay",{"process_recovery":"local"},members,
                    remote_boundary=True,terminated_pid=kill_receipt["pid"],
                    reopened_pid=kill_receipt["reopened_pid"],actual_process_termination=True,
                    recovery_boundary="committed-PUT-before-ACK",durable_recovery_passed=True)
    except BaseException as error:
        safe=repr(error).replace(password,"<fixture-secret>").replace(authorization,"<fixture-auth>")
        report["failure"]=safe
        raise RuntimeError(safe) from None
    finally:
        cleanup_errors=[]
        monitor_stop.set()
        def cleanup(label, action):
            try:action()
            except BaseException as error:
                cleanup_errors.append({"step":label,"failure":repr(error).replace(password,"<fixture-secret>")})
        if server is not None:cleanup("server-close",server.close)
        if monitor is not None:cleanup("kill-monitor-join",lambda:monitor.join(5))
        if monitor is not None and monitor.is_alive():
            cleanup_errors.append({"step":"kill-monitor-join","failure":"monitor still alive"})
        def remove_trust():
            digest=subprocess.check_output(["openssl","x509","-in",str(a.certificate),
                "-noout","-fingerprint","-sha1"],text=True).strip().split("=")[-1].replace(":","")
            subprocess.run(["sudo","security","delete-certificate","-Z",digest,
                "/Library/Keychains/System.keychain"],check=True,capture_output=True)
        if trusted:cleanup("fixture-trust-remove",remove_trust)
        report["requests"]=server.requests if server is not None else []
        report["uncovered"]=["independent original-artifact authentication","native offline mutation/reconnect","deletion conflict presentation",
            "organization projection (owner delta not yet composed)"]
        report["cleanup_errors"]=cleanup_errors
        cleanup("coverage-write",lambda:(a.output/"coverage.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8"))
        if program_hash is not None:
            cleanup("role-receipt-write",lambda:write_role_receipt(a.output,a.platform,a.output/"program.bin",
                {"source":report["source"],"run":report["run"],"attempt":report["attempt"]},
                normalized,claim_refs,evidence))
        if cleanup_errors:
            print(json.dumps({"cleanup_errors":cleanup_errors,"primary_failure":report.get("failure")}),flush=True)
            if "failure" not in report:raise RuntimeError("F05 cleanup failed; preserve evidence")

if __name__=="__main__":main()
