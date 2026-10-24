// SPDX-License-Identifier: MIT
import XCTest

final class SearchUITests: XCTestCase {
    private var app: XCUIApplication!
    private var steps: [String] = []
    override func setUpWithError() throws { continueAfterFailure = false; app = XCUIApplication(); steps = [] }
    override func tearDownWithError() throws {
        if let data = try? JSONSerialization.data(withJSONObject: ["test": name, "steps": steps]),
           let text = String(data: data, encoding: .utf8) {
            let attachment = XCTAttachment(string: text)
            attachment.name = "search-steps-\(name).json"; attachment.lifetime = .keepAlways; add(attachment)
        }
        app?.terminate()
    }
    private func element(_ id: String) -> XCUIElement { app.descendants(matching: .any).matching(identifier: id).firstMatch }
    private func text(_ id: String) -> String {
        guard let value = try? element(id).snapshot() else { return "" }
        return value.label.isEmpty ? (value.value as? String) ?? "" : value.label
    }
    private func wait(_ condition: () -> Bool) -> Bool {
        let deadline = Date().addingTimeInterval(90)
        while Date() < deadline {
            if condition() { return true }
            RunLoop.current.run(until: Date().addingTimeInterval(0.15))
        }
        return condition()
    }
    private func tap(_ id: String) {
        XCTAssertTrue(wait { self.element(id).exists && self.element(id).isEnabled && self.element(id).isHittable }, "Action unavailable: \(id)")
        element(id).tap()
    }
    private func mark(_ step: String) {
        steps.append(step)
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = "search-\(step)"; attachment.lifetime = .keepAlways; add(attachment)
    }
    private func launch(fresh: Bool, hold: Bool = false) {
        app.launchArguments = ["-EXRUITestFixtures", "1"] + (fresh ? ["-EXRFreshState", "1"] : []) + (hold ? ["-EXRHoldSearchCancellation"] : [])
        app.launch()
        XCTAssertTrue(wait { (self.element("library.title").exists && !self.element("library.busy").exists) ||
            (self.element("reader.page").exists && !self.element("reader.busy").exists) })
    }
    private func openFixture(hold: Bool = false) {
        launch(fresh: true, hold: hold)
        tap("library.import.epub")
        XCTAssertTrue(wait { !self.element("library.busy").exists && self.app.buttons["library.book.0"].exists })
        tap("library.book.0")
        XCTAssertTrue(wait { self.element("reader.page").exists && !self.element("reader.busy").exists })
        mark("original-opens")
    }
    private func query(_ value: String) {
        tap("reader.search")
        let field = element("search.query")
        XCTAssertTrue(field.waitForExistence(timeout: 15))
        field.tap(); field.typeText(value)
        tap("search.find")
    }
    func testFindSelectAndProcessRestart() {
        openFixture()
        query("C00P040W00")
        XCTAssertTrue(wait { self.app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'search.hit.'")).count == 1 })
        XCTAssertTrue(text("search.status").contains("已查找完毕"))
        mark("one-exact-result")
        app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'search.hit.'")).firstMatch.tap()
        XCTAssertTrue(wait { self.text("reader.status") == "已精确定位选文" && !self.element("reader.busy").exists })
        XCTAssertTrue(text("reader.page").contains("C00P040W00"))
        let location = text("reader.location")
        mark("independent-found-selected")
        app.terminate(); XCTAssertTrue(app.wait(for: .notRunning, timeout: 15))
        launch(fresh: false)
        XCTAssertTrue(wait { self.text("reader.location") == location && self.text("reader.page").contains("C00P040W00") })
        tap("reader.search")
        XCTAssertEqual(element("search.query").value as? String, "C00P040W00")
        XCTAssertEqual(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'search.hit.'")).count, 0)
        tap("search.find")
        XCTAssertTrue(wait { self.app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'search.hit.'")).count == 1 })
        mark("restart-recomputes-query")
    }
    func testNoHitPreservesReader() {
        openFixture()
        let location = text("reader.location"), page = text("reader.page")
        query("MissingLiteral_159873")
        XCTAssertTrue(wait { self.text("search.status") == "没有匹配结果" })
        XCTAssertEqual(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'search.hit.'")).count, 0)
        mark("no-hit-complete")
        tap("search.close")
        XCTAssertEqual(text("reader.location"), location)
        XCTAssertEqual(text("reader.page"), page)
        mark("no-hit-reader-unchanged")
    }
    func testCancelActualSearchPoll() {
        openFixture(hold: true)
        let location = text("reader.location"), page = text("reader.page")
        query("reading")
        XCTAssertTrue(wait { self.text("search.status") == "正在查找（可取消）" })
        mark("actual-f1-cancel-poll")
        tap("search.cancel")
        XCTAssertTrue(wait { self.text("search.status").contains("已取消") })
        XCTAssertEqual(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'search.hit.'")).count, 0)
        tap("search.close")
        XCTAssertEqual(text("reader.location"), location)
        XCTAssertEqual(text("reader.page"), page)
        mark("cancel-reader-unchanged")
    }
}
