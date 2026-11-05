// SPDX-License-Identifier: MIT
import XCTest

// Runs against the actual review host on macOS, iPhone and iPad. The small
// observation reports renderer/lease state; navigation and font operations use
// the same native controls as the product.
final class FontReaderUITests: XCTestCase {
    private var app: XCUIApplication!
    override func setUpWithError() throws { continueAfterFailure = false; app = XCUIApplication() }
    override func tearDownWithError() throws {
        let tree = XCTAttachment(string: app.debugDescription)
        tree.name = "font-final-native-tree"; tree.lifetime = .keepAlways; add(tree)
        app.terminate()
    }
    private func element(_ id: String) -> XCUIElement {
#if os(iOS)
        if id == "features.scroll" { return app.scrollViews.matching(identifier: id).firstMatch }
        let labels: Set<String> = [
            "features.status", "features.font.observation", "library.title",
            "library.busy", "library.font.observation", "reader.location"
        ]
        if labels.contains(id) { return app.staticTexts.matching(identifier: id).firstMatch }
        let buttons: Set<String> = [
            "features.close", "features.cancel", "library.import.epub", "reader.next", "reader.back"
        ]
        if buttons.contains(id) || id.hasPrefix("library.book.") || id.hasPrefix("features.font.") {
            return app.buttons.matching(identifier: id).firstMatch
        }
#endif
        return app.descendants(matching: .any).matching(identifier: id).firstMatch
    }
    private func text(_ id: String) -> String {
        guard let value = try? element(id).snapshot() else { return "" }
        return value.label.isEmpty ? (value.value as? String) ?? "" : value.label
    }
    private func wait(_ predicate: () -> Bool) -> Bool {
        let deadline = Date().addingTimeInterval(90)
        while Date() < deadline {
            if predicate() { return true }
            RunLoop.current.run(until: Date().addingTimeInterval(0.15))
        }
        return predicate()
    }
    private func tap(_ id: String) {
        let scroll = element("features.scroll")
        let scrollTarget = id.hasPrefix("features.") && id != "features.close"
        for _ in 0..<24 {
            let target = element(id)
            let inViewport = !scrollTarget || !scroll.exists ||
                (target.exists && scroll.frame.contains(CGPoint(x: target.frame.midX, y: target.frame.midY)))
            if target.exists && inViewport && target.isHittable { break }
            if scrollTarget && scroll.exists {
                let above = target.exists && target.frame.midY < scroll.frame.midY
#if os(macOS)
                scroll.scroll(byDeltaX: 0, deltaY: above ? 140 : -140)
#else
                if above { scroll.swipeDown(velocity: .slow) } else { scroll.swipeUp(velocity: .slow) }
#endif
            }
        }
        XCTAssertTrue(wait {
            let target = self.element(id)
            let visible = !scrollTarget || !scroll.exists ||
                (target.exists && scroll.frame.contains(CGPoint(x: target.frame.midX, y: target.frame.midY)))
            return target.exists && visible && target.isEnabled && target.isHittable
        }, "Unavailable \(id): \(app.debugDescription)")
        element(id).tap()
    }
    private func mark(_ name: String) {
        let shot = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        shot.name = name; shot.lifetime = .keepAlways; add(shot)
    }
    private func ready() {
        XCTAssertTrue(wait { self.element("reader.page").exists && !self.element("reader.busy").exists })
    }
    private func launch(fresh: Bool) {
        app.launchArguments = ["-EXRUITestFixtures", "1"] + (fresh ? ["-EXRFreshState", "1"] : [])
        app.launch()
        XCTAssertTrue(wait { (self.element("library.title").exists && !self.element("library.busy").exists) ||
            (self.element("reader.page").exists && !self.element("reader.busy").exists) })
    }
    private func features() {
#if os(iOS)
        let trigger = element("reader.more").buttons.firstMatch
        XCTAssertTrue(wait { trigger.exists && trigger.frame.width > 0 })
        trigger.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
#else
        tap("reader.more")
#endif
        let title = "文件、字体与同步详情"
        XCTAssertTrue(wait { self.element("reader.features").exists || self.app.menuItems[title].exists || self.app.buttons[title].exists })
        if element("reader.features").exists { tap("reader.features") }
        else if app.menuItems[title].exists { app.menuItems[title].tap() }
        else { app.buttons[title].tap() }
        XCTAssertTrue(wait { self.element("features.close").exists })
    }
    private func status(_ value: String) {
        XCTAssertTrue(wait { self.text("features.status").contains(value) && !self.element("features.cancel").exists },
                      "Expected \(value): \(app.debugDescription)")
    }
    private func fields(_ id: String) -> [String: String] {
        let raw = text(id)
        var values: [String: String] = [:]
        for field in raw.split(separator: ";") {
            let pair = field.split(separator: "=", maxSplits: 1).map(String.init)
            if pair.count == 2 { values[pair[0]] = pair[1] }
        }
        return values
    }
    private func observation(_ id: String = "features.font.observation") -> [String: String] {
        XCTAssertTrue(wait { !self.text(id).isEmpty })
        let raw = text(id)
        let values = fields(id)
        for key in ["live", "acquired", "released", "part", "offset", "range", "selected", "bitmap"] {
            XCTAssertNotNil(values[key], "Missing \(key) in \(raw)")
        }
        return values
    }
    private func number(_ values: [String: String], _ key: String) -> Int {
        guard let value = values[key], let result = Int(value) else {
            XCTFail("Invalid \(key): \(values)"); return -1
        }
        return result
    }

    func testDistinctFontInvalidRollbackLeaseAndReopen() {
        launch(fresh: true)
        tap("library.import.epub")
        XCTAssertTrue(wait { self.element("library.book.0").exists && !self.element("library.busy").exists })
        tap("library.book.0"); ready()
        let first = text("reader.location")
        tap("reader.next")
        XCTAssertTrue(wait { !self.element("reader.busy").exists && self.text("reader.location") != first })
        features()
        let before = observation()
        XCTAssertGreaterThan(number(before, "offset"), 0)
        tap("features.font.distinct"); status("字体已导入")
        let rows = app.buttons.matching(NSPredicate(format: "identifier MATCHES %@", "features\\.font\\.[0-9a-f]{64}"))
        XCTAssertTrue(wait { rows.count == 1 })
        let fontID = rows.firstMatch.identifier
        let hash = String(fontID.dropFirst("features.font.".count))
        tap(fontID); status("字体已应用")
        XCTAssertTrue(wait {
            let state = self.fields("features.font.observation")
            return state["selected"] == hash && state["live"] == "1" &&
                (Int(state["acquired"] ?? "") ?? -1) > self.number(before, "acquired")
        })
        let selected = observation()
        XCTAssertEqual(selected["selected"], hash)
        XCTAssertEqual(selected["part"], before["part"])
        XCTAssertEqual(selected["offset"], before["offset"])
        XCTAssertEqual(number(selected, "live"), 1)
        XCTAssertGreaterThan(number(selected, "acquired"), number(before, "acquired"))
        tap("features.close"); ready()
        XCTAssertNotEqual(selected["bitmap"], before["bitmap"], "Distinct selected font must change rendered pixels")
        let location = text("reader.location"), page = text("reader.page")
        mark("font-distinct-applied")

        features(); tap("features.font.invalid")
        XCTAssertTrue(wait { !self.element("features.cancel").exists && !self.text("features.status").isEmpty &&
            self.text("features.status") != "处理中…" && self.text("features.status") != "字体已应用" })
        XCTAssertTrue(wait { self.fields("features.font.observation")["bitmap"] == selected["bitmap"] })
        let rejected = observation()
        for key in ["selected", "part", "offset", "range", "bitmap", "live", "acquired", "released"] {
            XCTAssertEqual(rejected[key], selected[key], "Invalid import changed \(key)")
        }
        XCTAssertEqual(rows.count, 1)
        tap("features.close"); ready()
        XCTAssertEqual(text("reader.location"), location)
        XCTAssertEqual(text("reader.page"), page)
        mark("font-invalid-preserved")

        // Closing the reader must release the borrowed font while the process
        // remains alive. Reopen the same book and measure reacquisition.
        tap("reader.back")
        XCTAssertTrue(wait { self.element("library.book.0").exists && !self.element("library.busy").exists })
        XCTAssertTrue(wait {
            let state = self.fields("library.font.observation")
            return state["live"] == "0" &&
                (Int(state["released"] ?? "") ?? -1) > self.number(selected, "released")
        }, "Reader exit did not release its font lease: \(app.debugDescription)")
        let shelf = observation("library.font.observation")
        mark("font-reader-exit-released")
        tap("library.book.0"); ready()
        XCTAssertEqual(text("reader.location"), location)
        XCTAssertEqual(text("reader.page"), page)
        features()
        XCTAssertTrue(wait {
            let state = self.fields("features.font.observation")
            return state["selected"] == hash && state["live"] == "1" &&
                (Int(state["acquired"] ?? "") ?? -1) > self.number(shelf, "acquired")
        }, "Reopening did not reacquire the selected font: \(app.debugDescription)")
        let afterShelf = observation()
        for key in ["selected", "part", "offset", "range", "bitmap"] {
            XCTAssertEqual(afterShelf[key], selected[key], "Reopening changed \(key)")
        }
        tap("features.close"); ready()
        app.terminate(); XCTAssertTrue(app.wait(for: .notRunning, timeout: 15))
        launch(fresh: false); ready()
        XCTAssertEqual(text("reader.location"), location)
        XCTAssertEqual(text("reader.page"), page)
        features()
        XCTAssertTrue(wait {
            let state = self.fields("features.font.observation")
            return state["selected"] == hash && state["live"] == "1"
        })
        let reopened = observation()
        XCTAssertEqual(reopened["selected"], hash)
        XCTAssertEqual(reopened["part"], selected["part"])
        XCTAssertEqual(reopened["offset"], selected["offset"])
        XCTAssertEqual(reopened["bitmap"], selected["bitmap"])
        XCTAssertEqual(number(reopened, "live"), 1)
        tap("features.font.default"); status("字体已应用")
        XCTAssertTrue(wait {
            let state = self.fields("features.font.observation")
            return state["selected"] == "default" && state["live"] == "0" &&
                (Int(state["released"] ?? "") ?? -1) > self.number(reopened, "released")
        })
        let released = observation()
        XCTAssertEqual(released["selected"], "default")
        XCTAssertEqual(released["part"], reopened["part"])
        XCTAssertEqual(released["offset"], reopened["offset"])
        XCTAssertEqual(number(released, "live"), 0)
        XCTAssertGreaterThan(number(released, "released"), number(reopened, "released"))
        mark("font-lease-released")
    }
}
