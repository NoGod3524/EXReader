// SPDX-License-Identifier: MIT
import XCTest

final class NavigationUITests: XCTestCase {
    private var app: XCUIApplication!
    private var steps: [String] = []
    override func setUpWithError() throws { continueAfterFailure = false; app = XCUIApplication(); steps = [] }
    override func tearDownWithError() throws {
        if let data = try? JSONSerialization.data(withJSONObject: ["test": name, "steps": steps]),
           let text = String(data: data, encoding: .utf8) {
            let attachment = XCTAttachment(string: text)
            attachment.name = "navigation-steps-\(name).json"; attachment.lifetime = .keepAlways; add(attachment)
        }
        app?.terminate()
    }
    private func element(_ id: String) -> XCUIElement { app.descendants(matching: .any).matching(identifier: id).firstMatch }
    private func text(_ id: String) -> String {
        guard let value = try? element(id).snapshot() else { return "" }
        return value.label.isEmpty ? (value.value as? String) ?? "" : value.label
    }
    private func wait(_ condition: () -> Bool) -> Bool {
        let end = Date().addingTimeInterval(90)
        while Date() < end {
            if condition() { return true }
            RunLoop.current.run(until: Date().addingTimeInterval(0.15))
        }
        return condition()
    }
    private func tap(_ id: String) {
        XCTAssertTrue(wait { self.element(id).exists && self.element(id).isEnabled && self.element(id).isHittable },
            "Action unavailable \(id): \(app.debugDescription)")
        element(id).tap()
    }
    private func mark(_ step: String) {
        steps.append(step)
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = "navigation-\(step)"; attachment.lifetime = .keepAlways; add(attachment)
    }
    private func launch(fresh: Bool, hold: Bool = false) {
        app.launchArguments = ["-EXRUITestFixtures", "1"] + (fresh ? ["-EXRFreshState", "1"] : []) +
            (hold ? ["-EXRHoldNavigationCancellation"] : [])
        app.launch()
        XCTAssertTrue(wait { (self.element("library.title").exists && !self.element("library.busy").exists) ||
            (self.element("reader.page").exists && !self.element("reader.busy").exists) })
    }
    private func openFixture(pdf: Bool = false, hold: Bool = false) {
        launch(fresh: true, hold: hold)
        tap(pdf ? "library.import.pdf" : "library.import.epub")
        XCTAssertTrue(wait { !self.element("library.busy").exists && self.app.buttons["library.book.0"].exists })
        tap("library.book.0")
        XCTAssertTrue(wait { self.element("reader.page").exists && !self.element("reader.busy").exists })
        mark("original-opens")
    }
    private func directory() {
        tap("reader.navigation")
        XCTAssertTrue(wait { self.text("navigation.status").contains("本页 32 项") || self.text("navigation.status").contains("按页入口") })
    }
    func testHierarchyIndependentFoundAndRestart() {
        openFixture(); let originalLocation = text("reader.location")
        directory(); tap("navigation.children.0")
        XCTAssertTrue(wait { self.text("navigation.status") == "本页 1 项 · 共 1 项" && self.element("navigation.row.1").exists })
        mark("hierarchical-child")
        tap("navigation.row.1")
        XCTAssertTrue(wait { !self.element("navigation.close").exists && !self.element("reader.busy").exists &&
            self.text("reader.page").contains("C01P040W00") && self.text("reader.location") != originalLocation },
            "Independent directory selection failed: \(app.debugDescription)")
        XCTAssertFalse(element("reader.error").exists)
        mark("independent-found-selected")
        let location = text("reader.location"), page = text("reader.page")
        app.terminate(); XCTAssertTrue(app.wait(for: .notRunning, timeout: 15)); launch(fresh: false)
        XCTAssertTrue(wait { self.text("reader.location") == location && self.text("reader.page") == page })
        directory()
        XCTAssertTrue(element("navigation.children.0").exists)
        mark("restart-rebuilds-directory")
    }
    func testPagedDirectoryClosePreservesFrame() {
        openFixture(); let location = text("reader.location"), page = text("reader.page")
        directory(); mark("first-32-roots")
        tap("navigation.next")
        XCTAssertTrue(wait { self.element("navigation.previous").exists && self.element("navigation.row.33").exists })
        mark("second-32-roots")
        tap("navigation.next")
        XCTAssertTrue(wait { self.text("navigation.status") == "本页 6 项 · 共 70 项" && !self.element("navigation.next").exists })
        mark("last-six-roots")
        tap("navigation.close")
        XCTAssertEqual(text("reader.location"), location); XCTAssertEqual(text("reader.page"), page)
        mark("close-reader-unchanged")
    }
    func testPartConfirmationAndExplicitDuplicate() {
        openFixture(); let location = text("reader.location"), page = text("reader.page")
        directory(); tap("navigation.row.2")
        XCTAssertTrue(wait { self.element("navigation.confirm.part").exists })
        mark("missing-fragment-confirmation")
        tap("navigation.keep"); tap("navigation.close")
        XCTAssertEqual(text("reader.location"), location); XCTAssertEqual(text("reader.page"), page)
        mark("missing-fragment-keeps-reader")
        directory(); tap("navigation.row.3")
        XCTAssertTrue(wait { self.element("navigation.part.0").exists && self.element("navigation.part.3").exists })
        mark("duplicate-spine-explicit-options")
        tap("navigation.part.3")
        XCTAssertTrue(wait { !self.element("navigation.close").exists && !self.element("reader.busy").exists &&
            self.text("reader.location").contains("第 4 章") && self.text("reader.page").contains("C00P010W00") })
        XCTAssertFalse(element("reader.error").exists)
        mark("chosen-spine-found")
    }
    func testActualSnapshotCancellation() {
        openFixture(hold: true); let location = text("reader.location"), page = text("reader.page")
        tap("reader.navigation")
        XCTAssertTrue(wait { self.text("navigation.status") == "正在读取目录（可取消）" })
        mark("actual-f2-cancel-poll")
        tap("navigation.cancel")
        XCTAssertTrue(wait { self.text("navigation.status").contains("已取消") })
        tap("navigation.close")
        XCTAssertEqual(text("reader.location"), location); XCTAssertEqual(text("reader.page"), page)
        mark("cancel-reader-unchanged")
    }
    func testPdfByPageNeverAuthoredOutline() {
        openFixture(pdf: true); let location = text("reader.location"), page = text("reader.page")
        directory()
        XCTAssertEqual(text("navigation.status"), "按页入口 · 非作者目录")
        mark("fixed-pages-labeled")
        tap("navigation.close")
        XCTAssertEqual(text("reader.location"), location); XCTAssertEqual(text("reader.page"), page)
        mark("fixed-directory-close-unchanged")
    }
    func testAuthorCfiEntryUsesReaderLabel() {
        openFixture(); directory()
        XCTAssertFalse(element("navigation.cfi").exists)
        XCTAssertEqual(element("navigation.row.6").label, "Unicode destination")
        mark("author-position-reader-label")
        tap("navigation.row.6")
        XCTAssertTrue(wait { !self.element("navigation.close").exists && !self.element("reader.busy").exists &&
            self.text("reader.location").contains("第 2 章") && self.text("reader.page").contains("A😀Z") },
            "Author CFI did not independently locate: \(app.debugDescription)")
        XCTAssertFalse(element("reader.error").exists)
        mark("author-position-independent-found")
    }
}
