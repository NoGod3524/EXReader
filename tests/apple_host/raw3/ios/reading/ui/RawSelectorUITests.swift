// SPDX-License-Identifier: MIT
import XCTest

final class RawSelectorUITests: XCTestCase {
    private var app: XCUIApplication!
    private var steps: [String] = []
    override func setUpWithError() throws { continueAfterFailure = false; app = XCUIApplication(); steps = [] }
    override func tearDownWithError() throws {
        let data = try JSONSerialization.data(withJSONObject: ["test": name, "steps": steps], options: [.sortedKeys])
        let proof = XCTAttachment(string: String(decoding: data, as: UTF8.self))
        proof.name = "raw3-steps.json"; proof.lifetime = .keepAlways; add(proof)
        app.terminate()
    }
    private func node(_ id: String) -> XCUIElement { app.descendants(matching: .any).matching(identifier: id).firstMatch }
    private func text(_ id: String) -> String {
        guard let value = try? node(id).snapshot() else { return "" }
        return value.label.isEmpty ? value.value as? String ?? "" : value.label
    }
    private func wait(_ seconds: TimeInterval = 90, _ ready: () -> Bool) -> Bool {
        let deadline = Date().addingTimeInterval(seconds)
        while Date() < deadline { if ready() { return true }; RunLoop.current.run(until: Date().addingTimeInterval(0.15)) }
        return ready()
    }
    private func tap(_ id: String) {
        XCTAssertTrue(wait { self.node(id).exists && self.node(id).isEnabled && self.node(id).isHittable }, "Unavailable \(id): \(app.debugDescription)")
        node(id).tap()
    }
    private func mark(_ value: String) {
        steps.append(value)
        let shot = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        shot.name = "raw3-" + value; shot.lifetime = .keepAlways; add(shot)
    }
    private func launch(fresh: Bool, boundary: String? = nil) {
        app.launchArguments = ["-EXRUITestFixtures", "1", "-EXRRaw3Case", name] + (fresh ? ["-EXRFreshState", "1"] : []) + (boundary.map { [$0] } ?? [])
        app.launch()
        XCTAssertTrue(wait { (self.node("library.title").exists && !self.node("library.busy").exists) ||
            (self.node("reader.page").exists && !self.node("reader.busy").exists) })
    }
    private func openPDF(boundary: String? = nil) {
        launch(fresh: true, boundary: boundary)
        tap("library.import.raw3-pdf")
        XCTAssertTrue(wait { self.node("library.book.0").exists && !self.node("library.busy").exists })
        tap("library.book.0")
        XCTAssertTrue(wait { self.node("reader.page").exists && !self.node("reader.busy").exists })
        mark("actual-8845B-PDF-opens")
    }
    private func records() {
        let trigger = node("reader.more").buttons.firstMatch
        XCTAssertTrue(wait { trigger.exists && trigger.frame.width > 0 && trigger.frame.height > 0 && self.app.windows.firstMatch.frame.contains(trigger.frame) })
        trigger.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        XCTAssertTrue(wait { self.node("reader.records").exists || self.app.buttons["阅读记录"].exists })
        if node("reader.records").exists { tap("reader.records") } else { app.buttons["阅读记录"].tap() }
        XCTAssertTrue(wait { self.text("reading.status") == "本书的书签与标注" })
    }
    private func complete(_ value: String) { XCTAssertTrue(wait { self.text("reading.status").contains(value) }, app.debugDescription) }
    private func index(_ kind: String) -> Int {
        guard let value = (0..<10).first(where: { text("reading.kind.\($0)") == kind }) else { XCTFail("Missing \(kind): \(app.debugDescription)"); return 0 }
        return value
    }
    private func confirm(_ id: String, _ title: String) {
        XCTAssertTrue(wait { self.node(id).exists || self.app.alerts.buttons[title].exists || self.app.dialogs.buttons[title].exists })
        if node(id).exists && node(id).isHittable { node(id).tap() }
        else if app.alerts.buttons[title].exists { app.alerts.buttons[title].tap() }
        else { app.dialogs.buttons[title].tap() }
    }
    private func editDeleteRestore(_ row: Int) {
        tap("reading.edit.\(row)")
        let editor = app.textViews.matching(identifier: "reading.editor").firstMatch
        XCTAssertTrue(wait { editor.exists && editor.isHittable })
        editor.tap(); editor.typeText("Actual mobile retained note")
        tap("reading.save-note"); complete("批注已保存")
        tap("reading.delete.\(row)"); confirm("reading.confirm-delete", "删除"); complete("阅读记录已删除")
        tap("reading.history.\(row)"); complete("请选择要恢复的保留版本")
        tap("reading.restore.0"); confirm("reading.confirm-restore", "恢复"); complete("已恢复阅读记录")
    }
    func testRawPDFPointsRangeEditRestoreJumpAndReopen() {
        openPDF(); let location = text("reader.location"), frame = text("reader.page")
        records(); tap("reading.save-progress"); complete("已保存阅读进度")
        tap("reading.add-bookmark"); complete("已添加书签"); mark("raw-points-saved")
        tap("reading.close"); tap("reader.select"); tap("selection.all")
        XCTAssertTrue(wait { !self.text("selection.quote").isEmpty })
        mark("real-PDF-native-selection")
        tap("selection.reading-highlight")
        XCTAssertTrue(wait { !self.node("reader.busy").exists && self.text("reader.status") == "已保存高亮到阅读记录" })
        tap("selection.close"); records(); let highlight = index("高亮")
        editDeleteRestore(highlight); mark("raw-range-note-delete-restore")
        tap("reading.jump.\(index("书签"))")
        XCTAssertTrue(wait { !self.node("reader.busy").exists }); tap("reading.close")
        XCTAssertEqual(text("reader.location"), location); XCTAssertEqual(text("reader.page"), frame)
        mark("real-independent-found-before-explicit-jump")
        app.terminate(); XCTAssertTrue(app.wait(for: .notRunning, timeout: 45)); launch(fresh: false)
        records(); XCTAssertTrue(node("reading.kind.2").exists); mark("new-process-raw-records-retained")
    }
    private func termination(_ argument: String, boundary: String) {
        openPDF(boundary: argument); records(); tap("reading.add-bookmark")
        XCTAssertTrue(wait { self.text("reading.native-boundary") == boundary })
        mark("actual-" + boundary)
        app.terminate(); XCTAssertTrue(app.wait(for: .notRunning, timeout: 45))
        launch(fresh: false); records(); XCTAssertTrue(node("reading.pending").exists)
        tap("reading.retry"); complete("待完成阅读记录已确认保存")
        XCTAssertFalse(node("reading.pending").exists); XCTAssertEqual(text("reading.kind.0"), "书签"); XCTAssertFalse(node("reading.kind.1").exists)
        mark("raw3-explicit-original-request-replay")
    }
    func testRawTerminationBeforeCommit() { termination("-EXRKillReadingAfterSave", boundary: "private-save") }
    func testRawTerminationAfterCommit() { termination("-EXRKillReadingAfterCommit", boundary: "post-commit") }
    func testLegacyOFFLeavesActualFailedV1Request() {
        openPDF(); records(); tap("reading.add-bookmark")
        XCTAssertTrue(wait { !self.node("reader.busy").exists && self.node("reading.pending").exists })
        XCTAssertFalse(node("reading.kind.0").exists); mark("actual-OFF-v1-NUL-refused")
    }
    func testRawBuildRetainsLegacyV1Failure() {
        launch(fresh: false); records(); XCTAssertTrue(node("reading.pending").exists)
        tap("reading.retry")
        XCTAssertTrue(wait { !self.node("reader.busy").exists && self.node("reading.pending").exists })
        XCTAssertFalse(node("reading.kind.0").exists); mark("raw-build-original-v1-remains-refused")
    }
    func testNativeHTTPSRetainedNullAndSourceVersions() throws {
        launch(fresh: true)
        let root = try XCTUnwrap(ProcessInfo.processInfo.environment["EXR_RAW3_IOS_ROOT"])
        tap("account.choose"); tap("account.root"); node("account.root").typeText(root + "\n"); tap("account.connect")
        XCTAssertTrue(wait { self.node("account.sync.start").exists && !self.node("library.busy").exists })
        tap("account.sync.start")
        XCTAssertTrue(wait(240) { self.text("account.sync.state") == "本轮扫描完成" })
        mark("actual-mobile-HTTPS-256-shard-receive")
        tap("library.import.raw3-pdf")
        XCTAssertTrue(wait { self.node("library.book.0").exists && !self.node("library.busy").exists })
        tap("library.book.0"); XCTAssertTrue(wait { self.node("reader.page").exists && !self.node("reader.busy").exists })
        let location = text("reader.location"), frame = text("reader.page")
        records(); XCTAssertTrue(node("reading.kind.0").exists)
        XCTAssertFalse(node("reading.jump.0").exists); XCTAssertFalse(node("reading.edit.0").exists)
        mark("actual-retained-NULL-has-no-navigation-action")
        tap("reading.close"); XCTAssertEqual(text("reader.location"), location); XCTAssertEqual(text("reader.page"), frame)
        tap("reader.back"); tap("library.import.raw3-mac-text")
        XCTAssertTrue(wait { self.node("library.book.1").exists && !self.node("library.busy").exists })
        tap("library.book.1"); XCTAssertTrue(wait { self.node("reader.page").exists && !self.node("reader.busy").exists })
        records(); XCTAssertTrue(node("reading.kind.1").exists)
        editDeleteRestore(0); editDeleteRestore(1); mark("actual-source-v1-v2-UI-edit-delete-restore")
        tap("reading.close"); app.terminate(); XCTAssertTrue(app.wait(for: .notRunning, timeout: 45)); launch(fresh: false)
        records(); XCTAssertTrue(node("reading.kind.1").exists); mark("account-raw-source-records-real-reopen")
    }
}
