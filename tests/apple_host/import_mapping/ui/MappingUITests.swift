// SPDX-License-Identifier: MIT
import XCTest

final class ImportMappingUITests: XCTestCase {
    private var app: XCUIApplication!
    private var steps: [[String: Any]] = []

    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication()
        steps = []
    }

    override func tearDownWithError() throws {
        if let data = try? JSONSerialization.data(withJSONObject: ["test": name, "steps": steps], options: [.prettyPrinted, .sortedKeys]),
           let text = String(data: data, encoding: .utf8) {
            let attachment = XCTAttachment(string: text)
            attachment.name = "mapping-steps-\(name).json"
            attachment.lifetime = .keepAlways
            add(attachment)
        }
        app?.terminate()
    }

    private func element(_ identifier: String) -> XCUIElement {
        app.descendants(matching: .any).matching(identifier: identifier).firstMatch
    }
    private func wait(_ timeout: TimeInterval = 90, _ condition: () -> Bool) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if condition() { return true }
            RunLoop.current.run(until: Date().addingTimeInterval(0.15))
        }
        return condition()
    }
    private var probe: String { element("library.import.mapping-state").label }
    private func launch(fresh: Bool, extra: [String] = []) {
        app.launchArguments = ["-EXRUITestFixtures", "1"] + (fresh ? ["-EXRFreshState", "1"] : []) + extra
        app.launch()
        XCTAssertTrue(wait { self.element("library.import.mapping-state").exists &&
            !self.element("library.busy").exists && !self.probe.isEmpty }, "Startup/mapping repair did not finish: \(app.debugDescription)")
        mark(fresh ? "fresh-start" : "restart-and-repair")
    }
    private func mark(_ id: String, screenshot: Bool = false) {
        steps.append(["id": id, "probe": element("library.import.mapping-state").exists ? probe : "",
                      "status": element("library.status").exists ? element("library.status").label : "",
                      "app_state": app.state.rawValue])
        if screenshot {
            let image = XCTAttachment(screenshot: app.screenshot())
            image.name = "mapping-\(id)"
            image.lifetime = .keepAlways
            add(image)
        }
    }
    private func importBook(_ button: String, count: Int, duplicate: Bool = false) {
        let target = app.buttons.matching(identifier: button).firstMatch
        XCTAssertTrue(target.waitForExistence(timeout: 30))
        XCTAssertTrue(wait(30) { target.isEnabled && target.isHittable })
        target.tap()
        XCTAssertTrue(wait { !self.element("library.busy").exists &&
            self.probe.contains("books=\(count);local=\(count);") &&
            self.element("library.status").label.contains(duplicate ? "已存在" : "已导入") }, "Import mapping did not complete: \(app.debugDescription)")
        XCTAssertTrue(probe.contains("staging=0;"))
        XCTAssertFalse(element("library.error").exists)
        mark(button)
    }

    func testFormatsDuplicateUnicodeAndStoredReading() {
        launch(fresh: true)
        importBook("library.import.epub", count: 1)
        importBook("library.import.pdf", count: 2)
        importBook("library.import.mapping-text", count: 3)
        importBook("library.import.epub.duplicate", count: 3, duplicate: true)
        importBook("library.import.unicode", count: 4)
        XCTAssertTrue(probe.contains("epub_chapter=2;reflow_global=1;fixed_page=1;"))
        let keys = probe.components(separatedBy: "keys=").last!.components(separatedBy: "|")
        XCTAssertEqual(keys.count, 4)
        for key in keys {
            XCTAssertNotNil(key.range(of: "^(epub|pdf|txt):[0-9a-f]{64}$", options: .regularExpression))
        }
        mark("four-source-mappings", screenshot: true)
        app.buttons["library.book.0"].tap()
        XCTAssertTrue(wait { self.element("reader.page").exists && !self.element("reader.busy").exists })
        mark("stored-original-opens", screenshot: true)
    }

    func testPrepublicationCancellationLeavesNoBookOrCopy() {
        launch(fresh: true, extra: ["-EXRHostDelayMs", "3000"])
        app.buttons["library.import.epub"].tap()
        let cancel = app.buttons["library.cancel"]
        XCTAssertTrue(cancel.waitForExistence(timeout: 10))
        cancel.tap()
        XCTAssertTrue(wait { !self.element("library.busy").exists && self.element("library.status").label == "已取消" })
        XCTAssertTrue(probe.contains("books=0;local=0;"))
        XCTAssertTrue(probe.contains("staging=0;"))
        XCTAssertTrue(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'library.book.'")).allElementsBoundByIndex.isEmpty)
        mark("cancelled-without-publication", screenshot: true)
    }

    private func killedImport(extra: String, button: String, phase: String, kind: String) {
        launch(fresh: true, extra: [extra])
        app.buttons[button].tap()
        XCTAssertTrue(wait { self.element("library.status").label == phase }, "Real import did not reach the interruption boundary")
        mark("before-process-termination", screenshot: true)
        app.terminate()
        XCTAssertTrue(app.wait(for: .notRunning, timeout: 15))
        launch(fresh: false)
        XCTAssertTrue(probe.contains("books=1;local=1;"))
        XCTAssertTrue(probe.contains(kind + "=1;"))
        XCTAssertTrue(probe.contains("staging=0;"))
        XCTAssertFalse(element("library.error").exists)
        XCTAssertEqual(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'library.book.'")).count, 1)
        mark("recovered-original-with-one-mapping", screenshot: true)
    }

    func testRecoversAfterProcessTerminationBetweenDatabases() {
        killedImport(extra: "-EXRMappingPausePublished", button: "library.import.epub",
                     phase: "导入已保存，正在登记", kind: "epub_chapter")
    }

    func testRecoversAfterProcessTerminationInsideProductTransaction() {
        killedImport(extra: "-EXRMappingPauseTransaction", button: "library.import.pdf",
                     phase: "登记事务已开始", kind: "fixed_page")
    }

    func testSavedBookRemainsVisibleWhenProductIndexFails() {
        launch(fresh: true, extra: ["-EXRMappingRejectTransaction"])
        app.buttons["library.import.mapping-text"].tap()
        XCTAssertTrue(wait { !self.element("library.busy").exists &&
            self.element("library.status").label == "书籍已保存，产品索引待修复" })
        XCTAssertTrue(element("library.error").label.contains("书籍已保存"))
        XCTAssertTrue(probe.contains("books=0;local=0;"))
        XCTAssertTrue(probe.contains("staging=0;"))
        XCTAssertEqual(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'library.book.'")).count, 1)
        mark("saved-with-pending-index", screenshot: true)
        app.terminate()
        launch(fresh: false)
        XCTAssertTrue(probe.contains("books=1;local=1;"))
        XCTAssertTrue(probe.contains("reflow_global=1;"))
        XCTAssertTrue(probe.contains("staging=0;"))
        XCTAssertFalse(element("library.error").exists)
        mark("recovered-saved-book", screenshot: true)
    }
}
