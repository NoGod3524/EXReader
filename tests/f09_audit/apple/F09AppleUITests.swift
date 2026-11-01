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
        // macOS lays the reading tools out inline: no tools scroll view exists.
        guard let scroll, scroll.exists else { return true }
        return scroll.frame.contains(centre)
    }

    // Scrolls the view that contains the control, first forward then back,
    // the way a user (or VoiceOver's scroll-into-view) brings it on screen.
    @discardableResult
    private func reveal(_ target: XCUIElement, in scroll: XCUIElement?, horizontal: Bool = false) -> Int {
        guard let scroll, scroll.exists else { return 0 }
        var steps = 0
        for forward in [true, false] {
            // Accessibility sizes make a row of tools several screens wide.
            for _ in 0..<(forward ? 16 : 32) where !visible(target, in: scroll) && scroll.exists {
#if os(macOS)
                let delta: CGFloat = forward ? -200 : 200
                if horizontal { scroll.scroll(byDeltaX: delta, deltaY: 0) } else { scroll.scroll(byDeltaX: 0, deltaY: delta) }
#else
                // Short, slow drags: a swipe flings a whole screen and can jump over
                // a control that is only partly on screen (iPhone, largest size).
                let from = horizontal ? CGVector(dx: forward ? 0.7 : 0.3, dy: 0.5) : CGVector(dx: 0.5, dy: forward ? 0.7 : 0.3)
                let to = horizontal ? CGVector(dx: forward ? 0.4 : 0.6, dy: 0.5) : CGVector(dx: 0.5, dy: forward ? 0.4 : 0.6)
                scroll.coordinate(withNormalizedOffset: from).press(forDuration: 0.1, thenDragTo: scroll.coordinate(withNormalizedOffset: to))
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

    private func organizationSample(_ phase: String) {
        let row = bookRow(), add = element("organization.add")
        samples.append(["t": Date().timeIntervalSince1970, "phase": phase,
                        "message": text("organization.message"), "membership": text("organization.membership"),
                        "add_enabled": add.exists && add.isEnabled,
                        "row_exists": row.exists, "row_enabled": row.exists && row.isEnabled,
                        "row_hittable": row.exists && row.isHittable,
                        "row_frame": row.exists ? String(describing: row.frame) : ""])
    }

    // Membership versions re-read: the prepareMembership publish ("已读取成员版本。")
    // or 添加 enabled, sampled every 200 ms for about 20 s.
    private func awaitReread(_ phase: String) -> Bool {
        for _ in 0..<100 {
            organizationSample(phase)
            if text("organization.message") == "已读取成员版本。" || element("organization.add").isEnabled { return true }
            usleep(200_000)
        }
        return false
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
        // Diagnostic (run 41337069328 attempt 2): this re-read tap once had no
        // effect and 添加 stayed disabled. Sample the panel around it; if it has no
        // effect, tap once more only to learn whether a second tap works, then fail.
        organizationSample("before re-read tap")
        tapElement(bookRow(), name: "organization book")
        if !awaitReread("after re-read tap") {
            tapElement(bookRow(), name: "organization book (diagnostic second tap)")
            let second = awaitReread("after diagnostic second tap")
            XCTFail("the book-row tap after verification did not re-read the membership versions; second tap re-read=\(second)")
        }
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

    // 3. Hardware keyboard (Mac keyboard; iPad/iPhone simulator hardware
    //    keyboard events). Only typeKey/typeText drive the commands; each one is
    //    judged by its visible effect.
    func testHardwareKeyboardCommands() {
        launch(fresh: true)
        tap("library.import.epub")
        XCTAssertTrue(wait(90) { !self.element("library.busy").exists && self.element("library.book.0").exists })
        var results: [String: Bool] = [:]

        let search = element("library.search")
        // The shelf is ready for commands once its index work is done: search and
        // 整理 are disabled while the product index is pending.
        XCTAssertTrue(wait(60) { search.isEnabled && self.element("library.organization").isEnabled }, app.debugDescription)
        RunLoop.current.run(until: Date().addingTimeInterval(1.0))
        func searchFocused() -> Bool { (search.value(forKey: "hasKeyboardFocus") as? Bool) ?? false }
        var presses = 0
        for _ in 0..<2 where !searchFocused() {
            app.typeKey("f", modifierFlags: .command)
            presses += 1
            _ = wait(5) { searchFocused() }
        }
        let focusedBySearchKey = searchFocused()
        if focusedBySearchKey { search.typeText("Sample") }
        results["⌘F focuses search"] = focusedBySearchKey && wait(10) { ((search.value as? String) ?? "").contains("Sample") }
        samples.append(["command": "⌘F", "presses": presses, "focused": focusedBySearchKey,
                        "search_value": (search.value as? String) ?? "", "search_frame": "\(search.frame)"])
        // Clear the query and submit: the search field releases focus (and the
        // on-screen keyboard that otherwise hides the shelf on iPhone).
        if focusedBySearchKey { app.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: 6) + "\n") }

        XCTAssertTrue(wait(30) { self.element("library.organization").isEnabled }, app.debugDescription)
        app.typeKey("o", modifierFlags: [.command, .shift])
        results["⇧⌘O opens 整理"] = element("organization.kind.tag").waitForExistence(timeout: 10)
        if results["⇧⌘O opens 整理"] == true { tap("organization.close") }
        XCTAssertTrue(wait(10) { !self.element("organization.kind.tag").exists })

        tap("library.book.0")
        let page = element("reader.page")
        XCTAssertTrue(page.waitForExistence(timeout: 90), app.debugDescription)
        XCTAssertTrue(wait(60) { !self.element("reader.busy").exists })
        // The page label starts with "第 N 页" on every platform (macOS leaves the value empty).
        func position() -> String { page.label + "|" + ((page.value as? String) ?? "") }
        // ⌘→ turns pages on every platform; the Mac also turns them with a bare →
        // (iPadOS reserves bare arrows for its keyboard focus system).
        var turns: [(String, XCUIElement.KeyModifierFlags)] = [("⌘→ turns the page", .command)]
#if os(macOS)
        turns.append(("→ turns the page", []))
#endif
        for (label, flags) in turns {
            let before = position()
            app.typeKey(.rightArrow, modifierFlags: flags)
            results[label] = wait(20) { position() != before && !self.element("reader.busy").exists }
            samples.append(["command": label, "before": String(before.prefix(60)), "after": String(position().prefix(60))])
        }

        app.typeKey("[", modifierFlags: .command)
        results["⌘[ returns to the shelf"] = element("library.title").waitForExistence(timeout: 20)

        samples.append(["keyboard": results.mapValues { $0 ? "pass" : "fail" }])
        let failed = results.filter { !$0.value }.map { $0.key }.sorted()
        XCTAssertTrue(failed.isEmpty, "Keyboard commands without effect: \(failed) \(app.debugDescription)")
    }
}
