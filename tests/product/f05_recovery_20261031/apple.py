# SPDX-License-Identifier: MIT
"""Actions-only native Apple reception of actual same-run Windows peer histories."""
import argparse
import base64
import secrets
import stat
import sqlite3
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from fixture import Store

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
    p.add_argument("--certificate",type=Path)
    p.add_argument("--key",type=Path)
    p.add_argument("--output",type=Path)
    p.add_argument("command",nargs=argparse.REMAINDER)
    a=p.parse_args()
    if a.prepare:
        a.tests.mkdir(parents=True,exist_ok=False)
        (a.tests/"F05RecoveryUITests.swift").write_text(SWIFT)
        return
    if any(v is None for v in (a.peer,a.certificate,a.key,a.output)):
        raise ValueError("peer/TLS/output required")
    command=a.command[1:] if a.command[:1]==["--"] else a.command
    if not command or command[0]!="xcodebuild":raise ValueError("actual xcodebuild required")
    if any("-only-testing" in v or "-resultBundlePath" in v for v in command):
        raise ValueError("driver owns exact phase/test result selection")
    a.output.mkdir(parents=True,exist_ok=False)
    contract=json.loads((a.peer/"peer-contract.json").read_text())
    if contract["entity_kind"]!="book":raise AssertionError("Apple book receiver requires book peers")
    user,password="f05",secrets.token_hex(24)
    authorization="Basic "+base64.b64encode((user+":"+password).encode()).decode()
    server=Store(a.certificate,a.key,authorization)
    origin=server.expose_checkpoint(a.peer/contract["baseline"])
    report={"source":os.environ["GITHUB_SHA"],"run":os.environ["GITHUB_RUN_ID"],
            "attempt":os.environ["GITHUB_RUN_ATTEMPT"],"host":a.platform,
            "F05_accepted":False,"cases":[],"producer":origin["author"],
            "simultaneous_online_peers":False,"generated_fixture_credentials_only":True}
    trusted=False
    app_folder=None
    label="macOS" if a.platform=="macos" else "iOS"
    def readback(folder):
        with sqlite3.connect((folder/"library.sqlite").resolve().as_uri()+"?mode=ro",uri=True) as db:
            originals=[{"id":row[0],"bytes":len(row[1]),"sha256":hashlib.sha256(row[1]).hexdigest()}
                       for row in db.execute("SELECT id,source FROM books ORDER BY id")]
        with sqlite3.connect((folder/"reader-catalog.db").resolve().as_uri()+"?mode=ro",uri=True) as db:
            revisions=[json.loads(row[0]) for row in db.execute("SELECT body_json FROM reader_revisions")]
        selected=[row for row in revisions if row["entity_kind"]=="book"
                  and row["entity_key"]==contract["entity_key"]]
        heads={row["id"] for row in selected}-{parent for row in selected for parent in row["parents"]}
        return {"originals":originals,"records":selected,"heads":sorted(heads),
                "observation":"actual app terminated; readonly SDK and product catalog"}
    try:
        if a.platform=="macos":
            subprocess.run(["sudo","security","add-trusted-cert","-d","-r","trustRoot",
                "-k","/Library/Keychains/System.keychain",str(a.certificate)],check=True,capture_output=True)
            trusted=True
        if a.platform!="macos":
            if not a.udid:raise ValueError("actual simulator UDID required")
            subprocess.run(["xcrun","simctl","keychain",a.udid,"add-root-cert",str(a.certificate)],check=True)
        for number,name in enumerate(("test01BaselineOriginal","test02CacheMissReceiveCancel","test03RetryOriginal","test04ReceiveRealConcurrentHeads","test05OfflineReopenOriginal")):
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
            start=len(server.requests)
            argv=command+["-only-testing:EXReaderHostUITests-"+label+"/F05RecoveryUITests/"+name,
                          "-resultBundlePath",str(a.output/(name+".xcresult"))]
            with (a.output/(name+".log")).open("wb") as log:
                done=subprocess.run(argv,stdout=log,stderr=subprocess.STDOUT,timeout=600,
                    env=dict(os.environ,TEST_RUNNER_F05_ROOT=server.root,
                        TEST_RUNNER_F05_USER=user,TEST_RUNNER_F05_PASSWORD=password))
            safe=(a.output/(name+".log")).read_text(errors="replace").replace(password,"<fixture-secret>").replace(authorization,"<fixture-auth>")
            (a.output/(name+".log")).write_text(safe)
            print(safe,flush=True)
            report["cases"].append({"test":name,"exit":done.returncode,"requests_start":start,
                                    "requests_end":len(server.requests),"argv":argv})
            if done.returncode:raise AssertionError("actual Apple UI failed: "+name)
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
                report["cases"][-1]["readback"]=observed
            server.release.set()
            if number==4 and len(server.requests)!=start:
                raise AssertionError("offline reopening unexpectedly requested network")
    except BaseException as error:
        safe=repr(error).replace(password,"<fixture-secret>").replace(authorization,"<fixture-auth>")
        report["failure"]=safe
        raise RuntimeError(safe) from None
    finally:
        report["requests"]=server.requests
        report["uncovered"]=["independent xcresult attachments and artifact authentication",
            "uncertain acknowledgment process kill",
            "organization projection (owner gap, not lower API injected)"]
        (a.output/"coverage.json").write_text(json.dumps(report,indent=2)+"\n")
        server.close()
        if trusted:
            digest=subprocess.check_output(["openssl","x509","-in",str(a.certificate),
                "-noout","-fingerprint","-sha1"],text=True).strip().split("=")[-1].replace(":","")
            subprocess.run(["sudo","security","delete-certificate","-Z",digest,
                "/Library/Keychains/System.keychain"],check=True,capture_output=True)

if __name__=="__main__":main()
