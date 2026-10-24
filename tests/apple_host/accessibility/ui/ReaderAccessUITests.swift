// SPDX-License-Identifier: MIT
import XCTest
#if os(iOS)
import UIKit
#endif

final class ReaderAccessUITests: XCTestCase {
    private var app: XCUIApplication!
    private var observations: [[String: Any]] = []

    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication()
        let storedStress = name.contains("test02")
        app.launchArguments = storedStress ? [] : ["-EXRUITestFixtures", "1"]
        observations = []
#if os(iOS)
        XCUIDevice.shared.orientation = .portrait
#endif
        app.launch()
        if storedStress {
            XCTAssertTrue(node("account.choose").waitForExistence(timeout: 90))
            XCTAssertTrue(node("account.choose").label.hasPrefix("云盘书库，https://example.invalid/accessibility-"))
            XCTAssertTrue(wait {
                if self.node("reader.back").exists && !self.node("reader.busy").exists {
                    self.node("reader.back").tap(); return false
                }
                return self.node("library.title").exists && !self.node("library.busy").exists
            })
            return
        }
        tap("account.choose")
        tap("account.root")
        node("account.root").typeText("https://example.invalid/accessibility-\(UUID().uuidString.lowercased())/\n")
        tap("account.connect")
        XCTAssertTrue(wait { !self.node("account.connect").exists && self.node("library.empty").exists })
    }

    override func tearDownWithError() throws {
        let data = try JSONSerialization.data(withJSONObject: ["test": name, "observations": observations], options: [.sortedKeys])
        let record = XCTAttachment(string: String(decoding: data, as: UTF8.self))
        record.name = "access-observations-\(name).json"; record.lifetime = .keepAlways; add(record)
        let image = XCTAttachment(screenshot: app.screenshot())
        image.name = "access-screen-\(name)"; image.lifetime = .keepAlways; add(image)
#if os(iOS)
        XCUIDevice.shared.orientation = .portrait
#endif
        app.terminate()
    }

    private func node(_ identifier: String) -> XCUIElement {
        app.descendants(matching: .any).matching(identifier: identifier).firstMatch
    }

    private func wait(_ seconds: TimeInterval = 60, _ ready: () -> Bool) -> Bool {
        let end = Date().addingTimeInterval(seconds)
        while Date() < end {
            if ready() { return true }
            RunLoop.current.run(until: Date().addingTimeInterval(0.15))
        }
        return ready()
    }

    private func text(_ identifier: String) -> String {
        let item = node(identifier)
        return item.label.isEmpty ? item.value as? String ?? "" : item.label
    }

    private func tap(_ identifier: String) {
        XCTAssertTrue(node(identifier).waitForExistence(timeout: 60), identifier)
        let toolbarAction = ["reader.first", "reader.previous", "reader.next", "reader.font.decrease",
            "reader.font.increase", "reader.select", "reader.notes"].contains(identifier)
        func viewport() -> CGRect {
            let window = app.windows.firstMatch.frame.insetBy(dx: -2, dy: -2)
            if node("account.form").exists { return window.intersection(node("account.form").frame) }
            if toolbarAction, node("reader.tools.scroll").exists { return window.intersection(node("reader.tools.scroll").frame) }
            return window
        }
        for _ in 0..<12 {
            let frame = node(identifier).frame, bounds = viewport()
            // AX can throw while computing a hit point for an offscreen
            // button. Reach its actual viewport before asking for that point.
            if !frame.isEmpty, bounds.contains(frame), node(identifier).isHittable { break }
            print("EXR native reach \(identifier) frame=\(frame) viewport=\(bounds)")
            if node("account.form").exists {
                let form = node("account.form")
                let earlier = node(identifier).frame.midY < form.frame.midY
#if os(macOS)
                form.scroll(byDeltaX: 0, deltaY: earlier ? 260 : -260)
#else
                if earlier { form.swipeDown() } else { form.swipeUp() }
#endif
            } else if toolbarAction, node("reader.tools.scroll").exists {
                let tools = node("reader.tools.scroll")
                if !frame.isEmpty, frame.midX < tools.frame.midX { tools.swipeRight() } else { tools.swipeLeft() }
            } else { break }
        }
        XCTAssertFalse(node(identifier).frame.isEmpty, identifier)
        XCTAssertTrue(viewport().contains(node(identifier).frame), identifier)
        XCTAssertTrue(node(identifier).isHittable, identifier)
        XCTAssertTrue(app.windows.firstMatch.frame.insetBy(dx: -2, dy: -2).contains(node(identifier).frame), identifier)
        XCTAssertTrue(wait { viewport().contains(self.node(identifier).frame) && self.node(identifier).isEnabled && self.node(identifier).isHittable }, identifier)
        node(identifier).tap()
    }

    private func open(_ fixture: String, title: String? = nil) {
        if !fixture.isEmpty { tap(fixture) }
        let predicate = title.map { NSPredicate(format: "identifier BEGINSWITH 'library.book.' AND label BEGINSWITH %@", $0) }
            ?? NSPredicate(format: "identifier BEGINSWITH 'library.book.'")
        let book = app.buttons.matching(predicate).firstMatch
        XCTAssertTrue(book.waitForExistence(timeout: 90))
        XCTAssertTrue(wait { !self.node("library.busy").exists && book.isHittable })
        book.tap()
        XCTAssertTrue(node("reader.page").waitForExistence(timeout: 90))
        readyReader()
    }

    private func readyReader() {
        var previous = "", stableSince = Date()
        let ready = wait {
            guard self.node("reader.page").exists, !self.node("reader.busy").exists,
                  !self.text("reader.location").isEmpty else { previous = ""; return false }
            let value = self.text("reader.location") + self.text("reader.font.value") + String(describing: self.node("reader.page").frame)
            if value != previous { previous = value; stableSince = Date() }
            return Date().timeIntervalSince(stableSince) >= 0.6
        }
        if !ready { print("EXR production reader did not settle:\n\(app.debugDescription)") }
        XCTAssertTrue(ready)
    }

    private func record(_ identifier: String, _ values: [String: Any] = [:]) {
        observations.append(["id": identifier, "values": values])
    }

    private func rectangle(_ value: CGRect) -> [Double] {
        [Double(value.minX), Double(value.minY), Double(value.width), Double(value.height)]
    }

    func test01ProductionBodyNamesAndActualEdgeTap() throws {
        open("library.import.unicode")
        let body = text("reader.page")
        XCTAssertTrue(body.contains("annotations."), "the end of the actual page must remain accessible beyond 60 characters")
        record("complete_actual_page_body", ["body": body])
        XCTAssertEqual(text("reader.font.decrease"), "减小字号")
        XCTAssertEqual(text("reader.font.increase"), "增大字号")
        XCTAssertFalse(node("reader.state").exists)
        record("production_control_names_without_internal_hash", ["decrease": text("reader.font.decrease"),
            "increase": text("reader.font.increase"), "internal_hash_present": node("reader.state").exists])
        let back = node("reader.back")
        XCTAssertTrue(app.windows.firstMatch.frame.insetBy(dx: -2, dy: -2).contains(back.frame))
#if os(iOS)
        XCTAssertGreaterThanOrEqual(back.frame.height, 44)
        XCTAssertGreaterThanOrEqual(back.frame.width, 44)
#endif
        let frame = rectangle(back.frame)
        back.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.1)).tap()
        XCTAssertTrue(node("library.title").waitForExistence(timeout: 30))
        XCTAssertFalse(text("library.title").contains("token="))
        XCTAssertFalse((node("library.title").value as? String ?? "").contains("token="))
        record("actual_outer_hit_region_navigates_back", ["back_frame": frame, "tap_y_fraction": 0.1])
        // Seed through the normal public import path before Actions changes
        // the device's actual content size. The stress launch hides fixtures.
        tap("library.import.epub")
        XCTAssertTrue(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'library.book.' AND label BEGINSWITH %@", "Sample.epub")).firstMatch.waitForExistence(timeout: 90))
    }

    func test02CompactReaderActualTurnFontAndNotes() throws {
#if os(iOS)
        let caption = UIFont.preferredFont(forTextStyle: .caption1).pointSize
        XCTAssertGreaterThan(caption, 20, "Actions must set the actual device content size before launching the runner")
        record("platform_text_size_fixture", ["dynamic_type_tested": true, "caption1_points": Double(caption)])
#else
        record("platform_text_size_fixture", ["dynamic_type_tested": false])
#endif
        open("", title: "Sample.epub")
#if os(iOS)
        XCUIDevice.shared.orientation = .landscapeLeft
        XCTAssertTrue(wait { self.app.windows.firstMatch.frame.width > self.app.windows.firstMatch.frame.height })
        XCTAssertTrue(node("reader.tools.scroll").waitForExistence(timeout: 30))
#endif
        readyReader()
        let window = app.windows.firstMatch.frame
        XCTAssertTrue(window.insetBy(dx: -2, dy: -2).contains(node("reader.back").frame))
        XCTAssertTrue(window.insetBy(dx: -2, dy: -2).contains(node("reader.page").frame))
        XCTAssertGreaterThan(node("reader.page").frame.height, 0)
        record("compact_header_and_actual_page_inside_window", ["window": rectangle(window),
            "page": rectangle(node("reader.page").frame), "back": rectangle(node("reader.back").frame)])
        let location = text("reader.location")
        tap("reader.next")
        XCTAssertTrue(wait { !self.node("reader.busy").exists && self.text("reader.location") != location })
        record("actual_page_turn_in_compact_layout")
        let font = text("reader.font.value")
        tap("reader.font.increase")
        XCTAssertTrue(wait { !self.node("reader.busy").exists && self.text("reader.font.value") != font })
        readyReader()
        record("actual_font_change_after_reaching_toolbar_control")
        tap("reader.notes")
        XCTAssertTrue(node("notes.title").waitForExistence(timeout: 30))
        tap("notes.close")
        XCTAssertTrue(wait { !self.node("notes.title").exists && self.node("reader.back").isHittable })
        record("actual_notes_dialog_after_reaching_toolbar_control")
        let back = node("reader.back")
#if os(iOS)
        XCTAssertGreaterThanOrEqual(back.frame.height, 44)
#endif
        back.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.1)).tap()
        XCTAssertTrue(node("library.title").waitForExistence(timeout: 30))
        let book = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'library.book.'")).firstMatch
        XCTAssertTrue(wait { book.exists && book.isHittable &&
            self.app.windows.firstMatch.frame.insetBy(dx: -2, dy: -2).contains(book.frame) })
        record("actual_edge_back_after_toolbar_scroll")
    }
}
