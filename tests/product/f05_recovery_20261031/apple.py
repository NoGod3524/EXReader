# SPDX-License-Identifier: MIT
"""Actions-only native Apple reception of actual same-run Windows peer histories."""
import argparse
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
    }
    private func gateReached() -> Bool {
        guard let root=ProcessInfo.processInfo.environment["F05_ROOT"],
              let url=URL(string:root.replacingOccurrences(of:"/dav/",with:"/__f05_gate")) else {return false}
        let done=expectation(description:"read-only fixture boundary")
        var reached=false
        let task=URLSession.shared.dataTask(with:url){data,_,_ in
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
        openBook()
    }
    func test01BaselineOriginal() throws {
        let root=try XCTUnwrap(ProcessInfo.processInfo.environment["F05_ROOT"])
        tap("account.choose")
        let field=node("account.root")
        XCTAssertTrue(field.waitForExistence(timeout:30))
        XCTAssertFalse((field.value as? String ?? "").hasPrefix("http"),"fresh test profile required")
        field.tap();field.typeText(root+"\n")
        tap("account.connect")
        XCTAssertTrue(wait{self.node("account.choose").label=="云盘书库，"+root})
        sync()
        XCTAssertTrue(text("account.receive.state").contains("待处理冲突 0 项"))
        cancelRealReceiveThenRetry()
    }
    func test02ReceiveRealConcurrentHeads() {
        sync()
        XCTAssertTrue(text("account.receive.state").contains("待处理冲突 1 项"),
            "actual native conflict must be visible; never select one head")
        openBook()
    }
    func test03OfflineReopenOriginal() {
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
    server=Store(a.certificate,a.key,None) # Explicit anonymous fixture, no account credentials.
    origin=server.expose_checkpoint(a.peer/contract["baseline"])
    report={"source":os.environ["GITHUB_SHA"],"run":os.environ["GITHUB_RUN_ID"],
            "attempt":os.environ["GITHUB_RUN_ATTEMPT"],"host":a.platform,
            "F05_accepted":False,"cases":[],"producer":origin["author"],
            "simultaneous_online_peers":False,"anonymous_fixture":True}
    label="macOS" if a.platform=="macos" else "iOS"
    try:
        if a.platform!="macos":
            if not a.udid:raise ValueError("actual simulator UDID required")
            subprocess.run(["xcrun","simctl","keychain",a.udid,"add-root-cert",str(a.certificate)],check=True)
        for number,name in enumerate(("test01BaselineOriginal","test02ReceiveRealConcurrentHeads","test03OfflineReopenOriginal")):
            if number==0:
                server.hold_get=True;server.get_blocked.clear();server.release.clear()
            if number==1:server.expose_checkpoint(a.peer/contract["remote_conflict"])
            if number==2:server.offline=True
            start=len(server.requests)
            argv=command+["-only-testing:EXReaderHostUITests-"+label+"/F05RecoveryUITests/"+name,
                          "-resultBundlePath",str(a.output/(name+".xcresult"))]
            with (a.output/(name+".log")).open("wb") as log:
                done=subprocess.run(argv,stdout=log,stderr=subprocess.STDOUT,timeout=600,
                    env=dict(os.environ,TEST_RUNNER_F05_ROOT=server.root))
            print((a.output/(name+".log")).read_text(errors="replace"),flush=True)
            report["cases"].append({"test":name,"exit":done.returncode,"requests_start":start,
                                    "requests_end":len(server.requests),"argv":argv})
            if done.returncode:raise AssertionError("actual Apple UI failed: "+name)
            if number==0 and not server.get_blocked.is_set():
                raise AssertionError("native original receive gate was never reached")
            server.release.set()
            if number==2 and len(server.requests)!=start:
                raise AssertionError("offline reopening unexpectedly requested network")
    except BaseException as error:
        report["failure"]=repr(error)
        raise
    finally:
        report["requests"]=server.requests
        report["uncovered"]=["independent xcresult attachments and catalog head audit",
            "receive cancellation exact SDK count/readback","uncertain acknowledgment process kill",
            "organization projection (owner gap, not lower API injected)",
            "actual displayed original byte/readback authentication"]
        (a.output/"coverage.json").write_text(json.dumps(report,indent=2)+"\n")
        server.close()

if __name__=="__main__":main()
