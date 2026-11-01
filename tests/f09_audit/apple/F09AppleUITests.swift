// SPDX-License-Identifier: MIT
// F09 Apple UI checks on the installed same-source product host.
// 1. Organization entry after a restart that follows a membership removal
//    (run 41170540560 / job 124448286050 opened no panel on the third entry):
//    samples the 整理 button state every 50 ms around the tap and records the
//    full host state value, then requires the panel to appear.
// 2. Reading tools at the current content size: each tool is scrolled into the
//    visible part of its row before it must be hittable, the way VoiceOver and
//    Full Keyboard Access reach it.
import XCTest

final class F09AppleUITests: XCTestCase {
    private var app: XCUIApplication!
    private var samples: [[String: Any]] = []

    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication()
        samples = []
    }

    override func tearDownWithError() throws {
        if let data = try? JSONSerialization.data(withJSONObject: ["test": name, "samples": samples],
                                                  options: [.prettyPrinted, .sortedKeys]),
           let value = String(data: data, encoding: .utf8) {
            let record = XCTAttachment(string: value)
            record.name = "f09-samples-\(name).json"
            record.lifetime = .keepAlways
            add(record)
        }
        let screen = XCTAttachment(screenshot: app.screenshot())
        screen.name = "f09-screen-\(name)"
        screen.lifetime = .keepAlways
        add(screen)
        app.terminate()
    }

    private func element(_ id: String) -> XCUIElement {
        app.descendants(matching: .any).matching(identifier: id).firstMatch
    }

    private func wait(_ timeout: TimeInterval = 60, _ condition: () -> Bool) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if condition() { return true }
            RunLoop.current.run(until: Date().addingTimeInterval(0.05))
        }
        return condition()
    }

    private func tap(_ id: String) {
        let target = element(id)
        XCTAssertTrue(target.waitForExistence(timeout: 60), "Missing \(id): \(app.debugDescription)")
        // At accessibility sizes a control can sit below the visible part of
        // its scroll view; scroll that view the way a user would.
        if !target.isHittable,
           let scroll = app.scrollViews.allElementsBoundByIndex.last(where: {
               $0.descendants(matching: .any).matching(identifier: id).count > 0 }) {
            for _ in 0..<8 where !target.isHittable {
#if os(macOS)
                scroll.scroll(byDeltaX: 0, deltaY: -200)
#else
                scroll.swipeUp()
#endif
            }
        }
        XCTAssertTrue(wait { target.isEnabled && target.isHittable }, "Unavailable \(id): \(app.debugDescription)")
        target.tap()
    }

    // The retained helper: macOS keeps StaticText content in value, iOS in label.
    private func text(_ id: String) -> String {
        guard let node = try? element(id).snapshot() else { return "" }
        return node.label.isEmpty ? (node.value as? String ?? "") : node.label
    }

    private func state() -> String {
        let title = element("library.title")
        guard title.exists else { return "" }
        return (title.value as? String) ?? title.label
    }

    private func sample(_ phase: String) {
        let button = element("library.organization")
        samples.append(["t": Date().timeIntervalSince1970, "phase": phase,
                        "exists": button.exists, "enabled": button.exists && button.isEnabled,
                        "hittable": button.exists && button.isHittable,
                        "busy": element("library.busy").exists, "state": state()])
    }

    private func launch(fresh: Bool) {
        app.launchArguments = ["-EXRUITestFixtures", "1"] + (fresh ? ["-EXRFreshState", "1"] : [])
        app.launch()
        XCTAssertTrue(element("library.organization").waitForExistence(timeout: 90), app.debugDescription)
    }

    private func groupRow(_ name: String) -> XCUIElement {
        app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@ AND label == %@", "organization.group.", name)).firstMatch
    }

    private func bookRow() -> XCUIElement {
        app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "organization.book.")).firstMatch
    }

    func testOrganizationOpensAfterRestartFollowingRemoval() {
        launch(fresh: true)
        tap("library.import.epub")
        XCTAssertTrue(wait(90) { !self.element("library.busy").exists && self.element("library.book.0").exists })
        tap("library.organization")
        tap("organization.kind.tag")
        tap("organization.create")
        let field = element("organization.name")
        XCTAssertTrue(field.waitForExistence(timeout: 30))
        field.tap()
        field.typeText("F09 Tag")
        tap("organization.save")
        let group = groupRow("F09 Tag")
        XCTAssertTrue(group.waitForExistence(timeout: 60), app.debugDescription)
        group.tap()
        XCTAssertTrue(bookRow().waitForExistence(timeout: 60))
        bookRow().tap()
        // The retained G16 path (OrganizationUITests.testTagAndSeriesPersist):
        // verify the original, add, restart (second entry), remove, restart
        // (third entry, the one that opened no panel in run 41170540560).
        tap("organization.verify-original")
        XCTAssertTrue(wait { self.text("organization.message").contains("原件验证完成") }, app.debugDescription)
        bookRow().tap()
        tap("organization.add")
        XCTAssertTrue(wait { self.text("organization.membership") == "member" }, app.debugDescription)
        app.terminate()
        XCTAssertTrue(wait(15) { self.app.state == .notRunning })
        launch(fresh: false)
        tap("library.organization")
        tap("organization.kind.tag")
        XCTAssertTrue(groupRow("F09 Tag").waitForExistence(timeout: 60), app.debugDescription)
        groupRow("F09 Tag").tap()
        XCTAssertTrue(bookRow().waitForExistence(timeout: 60))
        bookRow().tap()
        tap("organization.remove")
        XCTAssertTrue(wait { self.text("organization.membership") == "not member" }, app.debugDescription)
        app.terminate()
        XCTAssertTrue(wait(15) { self.app.state == .notRunning })
        launch(fresh: false)
        // Sample the entry for five seconds after launch, then tap and keep sampling.
        let settle = Date().addingTimeInterval(5)
        while Date() < settle { sample("before-tap"); RunLoop.current.run(until: Date().addingTimeInterval(0.05)) }
        let button = element("library.organization")
        XCTAssertTrue(wait { button.isEnabled && button.isHittable }, app.debugDescription)
        sample("tap")
        button.tap()
        var opened = false
        let deadline = Date().addingTimeInterval(10)
        while Date() < deadline {
            sample("after-tap")
            if element("organization.kind.tag").exists { opened = true; break }
            RunLoop.current.run(until: Date().addingTimeInterval(0.05))
        }
        XCTAssertTrue(opened, "整理 tap after restart opened no organization panel: \(app.debugDescription)")
    }

    func testReadingToolsReachableAtCurrentContentSize() {
        launch(fresh: true)
        tap("library.import.epub")
        XCTAssertTrue(wait(90) { !self.element("library.busy").exists && self.element("library.book.0").exists })
        tap("library.book.0")
        XCTAssertTrue(element("reader.page").waitForExistence(timeout: 90), app.debugDescription)
        let toggle = element("reader.tools.toggle")
        let scroll = element("reader.tools.scroll")
        if toggle.waitForExistence(timeout: 10) {
            for attempt in 0..<3 where !scroll.exists {
                XCTAssertTrue(wait(20) { toggle.isHittable }, app.debugDescription)
                toggle.tap()
                let shown = scroll.waitForExistence(timeout: 5)
                samples.append(["toggle_attempt": attempt, "tools_shown": shown, "toggle_label": toggle.label])
            }
            XCTAssertTrue(scroll.exists, "显示阅读工具 did not show the tools row: \(app.debugDescription)")
        }
        var reached: [String: Bool] = [:]
        for id in ["reader.search", "reader.select", "reader.notes", "reader.navigation", "reader.first",
                   "reader.previous", "reader.next", "reader.font.decrease", "reader.font.increase"] {
            let target = element(id)
            XCTAssertTrue(target.waitForExistence(timeout: 30), "Missing \(id): \(app.debugDescription)")
            var attempts = 0
            while !target.isHittable && scroll.exists && attempts < 12 {
#if os(macOS)
                scroll.scroll(byDeltaX: -120, deltaY: 0)
#else
                scroll.swipeLeft()
#endif
                attempts += 1
            }
            if !target.isHittable && scroll.exists {
                for _ in 0..<12 where !target.isHittable {
#if os(macOS)
                    scroll.scroll(byDeltaX: 120, deltaY: 0)
#else
                    scroll.swipeRight()
#endif
                }
            }
            reached[id] = target.isHittable
            samples.append(["tool": id, "hittable": target.isHittable, "scroll_steps": attempts,
                            "frame": "\(target.frame)"])
        }
        let unreachable = reached.filter { !$0.value }.map { $0.key }.sorted()
        XCTAssertTrue(unreachable.isEmpty, "Unreachable after scrolling: \(unreachable) \(app.debugDescription)")
    }
}
