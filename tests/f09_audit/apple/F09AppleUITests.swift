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
        XCTAssertTrue(wait { target.isEnabled && target.isHittable }, "Unavailable \(id): \(app.debugDescription)")
        target.tap()
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
        tap("organization.add")
        XCTAssertTrue(wait { (self.element("organization.membership").label) == "member" })
        tap("organization.remove")
        // The original failure: terminate about one second after the removal.
        RunLoop.current.run(until: Date().addingTimeInterval(1.0))
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
        if toggle.exists && toggle.isHittable { toggle.tap() }
        let scroll = element("reader.tools.scroll")
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
                            "frame": NSCoder.string(for: target.frame)])
        }
        let unreachable = reached.filter { !$0.value }.map { $0.key }.sorted()
        XCTAssertTrue(unreachable.isEmpty, "Unreachable after scrolling: \(unreachable) \(app.debugDescription)")
    }
}
