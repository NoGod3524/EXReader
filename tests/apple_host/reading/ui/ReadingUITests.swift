// SPDX-License-Identifier: MIT
import XCTest

final class ReadingUITests: XCTestCase {
    private var app: XCUIApplication!
    private var steps: [String] = []
    override func setUpWithError() throws { continueAfterFailure = false; app = XCUIApplication(); steps = [] }
    override func tearDownWithError() throws {
        let data = try JSONSerialization.data(withJSONObject: ["test": name, "steps": steps], options: [.sortedKeys])
        let attachment = XCTAttachment(string: String(decoding: data, as: UTF8.self))
        attachment.name = "reading-steps-\(name).json"; attachment.lifetime = .keepAlways; add(attachment)
        app.terminate()
    }
    private func element(_ id: String) -> XCUIElement { app.descendants(matching: .any).matching(identifier: id).firstMatch }
    private func text(_ id: String) -> String {
        guard let value = try? element(id).snapshot() else { return "" }
        return value.label.isEmpty ? (value.value as? String) ?? "" : value.label
    }
    private func wait(_ condition: () -> Bool) -> Bool {
        let limit = Date().addingTimeInterval(90)
        while Date() < limit { if condition() { return true }; RunLoop.current.run(until: Date().addingTimeInterval(0.15)) }
        return condition()
    }
    private func tap(_ id: String) {
        XCTAssertTrue(wait { self.element(id).exists && self.element(id).isEnabled && self.element(id).isHittable }, "Action unavailable \(id): \(app.debugDescription)")
        element(id).tap()
    }
    private func confirm(_ id: String, title: String) {
        XCTAssertTrue(wait { self.element(id).exists || self.app.alerts.buttons[title].exists || self.app.dialogs.buttons[title].exists })
        if element(id).exists && element(id).isHittable { element(id).tap() }
        else if app.alerts.buttons[title].exists { app.alerts.buttons[title].tap() }
        else { app.dialogs.buttons[title].tap() }
    }
    private func mark(_ id: String) {
        steps.append(id)
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = "reading-\(id)"; attachment.lifetime = .keepAlways; add(attachment)
    }
    private func launch(fresh: Bool, kill: String? = nil) {
        app.launchArguments = ["-EXRUITestFixtures", "1"] + (fresh ? ["-EXRFreshState", "1"] : []) + (kill.map { [$0] } ?? [])
        app.launch()
        XCTAssertTrue(wait { (self.element("library.title").exists && !self.element("library.busy").exists) ||
            (self.element("reader.page").exists && !self.element("reader.busy").exists) })
    }
    private func openFixture(_ type: String = "epub", kill: String? = nil) {
        launch(fresh: true, kill: kill)
        tap("library.import." + type)
        XCTAssertTrue(wait { self.element("library.book.0").exists && !self.element("library.busy").exists })
        tap("library.book.0")
        XCTAssertTrue(wait { self.element("reader.page").exists && !self.element("reader.busy").exists })
        mark("original-opens")
    }
    private func records() {
        tap("reader.more")
        XCTAssertTrue(wait { self.element("reader.records").exists || self.app.menuItems["阅读记录"].exists || self.app.buttons["阅读记录"].exists })
        if element("reader.records").exists { tap("reader.records") }
        else if app.menuItems["阅读记录"].exists { app.menuItems["阅读记录"].tap() }
        else { app.buttons["阅读记录"].tap() }
        XCTAssertTrue(wait { self.text("reading.status") == "本书的书签与标注" })
    }
    private func complete(_ status: String) {
        XCTAssertTrue(wait { self.text("reading.status").contains(status) }, "Reading action failed: \(app.debugDescription)")
    }
    private func highlight() {
        tap("reader.select"); tap("selection.all")
        XCTAssertTrue(wait { !self.text("selection.quote").isEmpty })
        mark("actual-visible-selection")
        tap("selection.reading-highlight")
        XCTAssertTrue(wait { !self.element("reader.busy").exists && self.text("reader.status") == "已保存高亮到阅读记录" })
        tap("selection.close")
    }
    func testProgressBookmarkAndRestart() {
        openFixture(); records()
        tap("reading.save-progress"); complete("已保存阅读进度")
        XCTAssertEqual(text("reading.kind.0"), "阅读进度"); mark("saved-product-progress")
        tap("reading.add-bookmark"); complete("已添加书签")
        XCTAssertEqual(text("reading.kind.1"), "书签"); mark("point-bookmark")
        tap("reading.close"); let location = text("reader.location"), frame = text("reader.page")
        app.terminate(); XCTAssertTrue(app.wait(for: .notRunning, timeout: 15)); launch(fresh: false)
        XCTAssertEqual(text("reader.location"), location); XCTAssertEqual(text("reader.page"), frame)
        records(); XCTAssertEqual(text("reading.kind.0"), "阅读进度"); XCTAssertEqual(text("reading.kind.1"), "书签")
        mark("restart-retained-records")
    }
    func testHighlightEditDeleteAndExplicitRestore() {
        openFixture(); let location = text("reader.location"), frame = text("reader.page")
        highlight(); records(); XCTAssertEqual(text("reading.kind.0"), "高亮"); mark("product-highlight")
        tap("reading.edit.0"); tap("reading.editor"); element("reading.editor").typeText("Retained reader note")
        tap("reading.save-note"); complete("批注已保存")
        XCTAssertEqual(text("reading.kind.0"), "批注"); XCTAssertTrue(text("reading.body.0").contains("Retained reader note"))
        mark("selector-preserving-note-edit")
        tap("reading.delete.0"); confirm("reading.confirm-delete", title: "删除"); complete("阅读记录已删除")
        XCTAssertEqual(text("reading.kind.0"), "已删除的记录"); mark("product-tombstone")
        tap("reading.history.0"); complete("请选择要恢复的保留版本")
        tap("reading.restore.0"); confirm("reading.confirm-restore", title: "恢复"); complete("已恢复阅读记录")
        tap("reading.close")
        XCTAssertEqual(text("reader.location"), location); XCTAssertEqual(text("reader.page"), frame)
        mark("explicit-version-restore-no-navigation")
    }
    func testIndependentFoundBeforeUserJump() {
        openFixture(); let location = text("reader.location"), frame = text("reader.page")
        records(); tap("reading.add-bookmark"); complete("已添加书签"); mark("bookmark-at-actual-page")
        tap("reading.close"); tap("reader.next")
        XCTAssertTrue(wait { !self.element("reader.busy").exists && self.text("reader.location") != location }); mark("reader-moved")
        records(); tap("reading.jump.0")
        XCTAssertTrue(wait { !self.element("reader.busy").exists })
        tap("reading.close")
        XCTAssertEqual(text("reader.location"), location); XCTAssertEqual(text("reader.page"), frame)
        mark("independent-found-user-jump")
    }
    func testRealTerminationBeforeCommitRequiresExplicitReplay() {
        openFixture(kill: "-EXRKillReadingAfterSave"); records(); tap("reading.add-bookmark")
        XCTAssertTrue(app.wait(for: .notRunning, timeout: 45)); mark("real-private-save-process-exit")
        launch(fresh: false); records()
        XCTAssertTrue(element("reading.pending").exists); XCTAssertFalse(element("reading.kind.0").exists)
        mark("private-request-awaits-explicit-action")
        tap("reading.retry"); complete("待完成阅读记录已确认保存")
        XCTAssertFalse(element("reading.pending").exists); XCTAssertEqual(text("reading.kind.0"), "书签"); XCTAssertFalse(element("reading.kind.1").exists)
        mark("explicit-first-commit-replay")
    }
    func testRealTerminationAfterCommitReplaysExactlyOnce() {
        openFixture(kill: "-EXRKillReadingAfterCommit"); records(); tap("reading.add-bookmark")
        XCTAssertTrue(app.wait(for: .notRunning, timeout: 45)); mark("real-post-commit-process-exit")
        launch(fresh: false); records()
        XCTAssertTrue(element("reading.pending").exists); XCTAssertEqual(text("reading.kind.0"), "书签"); XCTAssertFalse(element("reading.kind.1").exists)
        mark("one-retained-record-with-pending-request")
        tap("reading.retry"); complete("待完成阅读记录已确认保存")
        XCTAssertFalse(element("reading.pending").exists); XCTAssertEqual(text("reading.kind.0"), "书签"); XCTAssertFalse(element("reading.kind.1").exists)
        mark("exact-replay-no-duplicate")
    }
    func testFixedCbzAndPdfRealPointRecords() {
        openFixture("records-cbz"); let firstPage = text("reader.location")
        records(); tap("reading.add-bookmark"); complete("已添加书签")
        XCTAssertEqual(text("reading.kind.0"), "书签"); mark("cbz-empty-text-point-bookmark")
        tap("reading.close"); tap("reader.next")
        XCTAssertTrue(wait { !self.element("reader.busy").exists && self.text("reader.location") != firstPage })
        records(); tap("reading.jump.0"); XCTAssertTrue(wait { !self.element("reader.busy").exists }); tap("reading.close")
        XCTAssertEqual(text("reader.location"), firstPage); mark("cbz-second-found-renderer-jump")
        tap("reader.back"); tap("library.import.pdf")
        XCTAssertTrue(wait { self.element("library.book.1").exists && !self.element("library.busy").exists }); tap("library.book.1")
        XCTAssertTrue(wait { self.element("reader.page").exists && !self.element("reader.busy").exists })
        records(); tap("reading.add-bookmark"); complete("已添加书签")
        XCTAssertEqual(text("reading.kind.0"), "书签"); mark("pdf-real-point-bookmark")
    }
    func testTxtPointSelectionAndExplicitJump() {
        openFixture("records-text"); let location = text("reader.location")
        records(); tap("reading.add-bookmark"); complete("已添加书签"); mark("txt-point-bookmark")
        tap("reading.close"); highlight(); records()
        XCTAssertTrue((0..<2).contains { self.text("reading.kind.\($0)") == "高亮" }); mark("txt-visible-selection-highlight")
        guard let index = (0..<2).first(where: { text("reading.kind.\($0)") == "书签" }) else { XCTFail("Real TXT bookmark absent"); return }
        tap("reading.jump.\(index)"); XCTAssertTrue(wait { !self.element("reader.busy").exists }); tap("reading.close")
        XCTAssertEqual(text("reader.location"), location); mark("txt-explicit-record-jump")
    }
}
