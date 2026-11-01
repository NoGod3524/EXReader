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

    // Visible means its centre lies inside the window and inside the scroll
    // view that clips it. XCUI's isHittable throws for controls a horizontal
    // scroll view has moved off screen, so the frame is read instead.
    private func visible(_ target: XCUIElement, in scroll: XCUIElement?) -> Bool {
        guard target.exists, !target.frame.isEmpty else { return false }
        let centre = CGPoint(x: target.frame.midX, y: target.frame.midY)
        guard app.windows.firstMatch.frame.contains(centre) else { return false }
        return scroll.map { $0.frame.contains(centre) } ?? true
    }

    // Scrolls the view that contains the control, first forward then back,
    // the way a user (or VoiceOver's scroll-into-view) brings it on screen.
    @discardableResult
    private func reveal(_ target: XCUIElement, in scroll: XCUIElement?, horizontal: Bool = false) -> Int {
        guard let scroll, scroll.exists else { return 0 }
        var steps = 0
        for forward in [true, false] {
            for _ in 0..<(forward ? 8 : 16) where !visible(target, in: scroll) {
#if os(macOS)
                let delta: CGFloat = forward ? -200 : 200
                if horizontal { scroll.scroll(byDeltaX: delta, deltaY: 0) } else { scroll.scroll(byDeltaX: 0, deltaY: delta) }
#else
                if horizontal { forward ? scroll.swipeLeft() : scroll.swipeRight() } else { forward ? scroll.swipeUp() : scroll.swipeDown() }
#endif
                steps += 1
            }
        }
        return steps
    }

    private func container(of id: String) -> XCUIElement? {
        app.scrollViews.allElementsBoundByIndex.last(where: { $0.descendants(matching: .any).matching(identifier: id).count > 0 })
    }

    private func tapElement(_ target: XCUIElement, name: String) {
        XCTAssertTrue(target.waitForExistence(timeout: 60), "Missing \(name): \(app.debugDescription)")
        let scroll = container(of: target.identifier)
        if !visible(target, in: scroll) { reveal(target, in: scroll) }
        XCTAssertTrue(wait { target.isEnabled && self.visible(target, in: scroll) }, "Unavailable \(name): \(app.debugDescription)")
        target.tap()
    }

    private func tap(_ id: String) { tapElement(element(id), name: id) }

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
        tapElement(group, name: "F09 Tag group")
        XCTAssertTrue(bookRow().waitForExistence(timeout: 60))
        tapElement(bookRow(), name: "organization book")
        // The retained G16 path (OrganizationUITests.testTagAndSeriesPersist):
        // verify the original, add, restart (second entry), remove, restart
        // (third entry, the one that opened no panel in run 41170540560).
        tap("organization.verify-original")
        XCTAssertTrue(wait { self.text("organization.message").contains("原件验证完成") }, app.debugDescription)
        tapElement(bookRow(), name: "organization book")
        tap("organization.add")
        XCTAssertTrue(wait { self.text("organization.membership") == "member" }, app.debugDescription)
        app.terminate()
        XCTAssertTrue(wait(15) { self.app.state == .notRunning })
        launch(fresh: false)
        tap("library.organization")
        tap("organization.kind.tag")
        XCTAssertTrue(groupRow("F09 Tag").waitForExistence(timeout: 60), app.debugDescription)
        tapElement(groupRow("F09 Tag"), name: "F09 Tag group")
        XCTAssertTrue(bookRow().waitForExistence(timeout: 60))
        tapElement(bookRow(), name: "organization book")
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
            let steps = visible(target, in: scroll) ? 0 : reveal(target, in: scroll, horizontal: true)
            let shown = visible(target, in: scroll)
            reached[id] = shown
            samples.append(["tool": id, "visible": shown, "enabled": target.isEnabled, "scroll_steps": steps,
                            "frame": "\(target.frame)"])
        }
        let unreachable = reached.filter { !$0.value }.map { $0.key }.sorted()
        XCTAssertTrue(unreachable.isEmpty, "Unreachable after scrolling: \(unreachable) \(app.debugDescription)")
    }
}
