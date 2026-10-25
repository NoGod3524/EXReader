// SPDX-License-Identifier: MIT
// No production hooks, review conditions, launch overrides or tap retries.
import XCTest
#if os(iOS)
import UIKit
#endif
final class DefaultUITests: XCTestCase {
    private var app: XCUIApplication!
    private let audit = A11yAuditRecorder()
    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication()
        app.launchArguments = []
        app.launch()
        XCTAssertTrue(node("account.choose").waitForExistence(timeout: 90))
        audit.emitEnvironment(app)
    }
    override func tearDownWithError() throws {
        // Never issue secondary AX/screenshot queries while unwinding a failed test.
        print("D10_TEARDOWN " + name)
#if os(iOS)
        XCUIDevice.shared.orientation = .portrait
#endif
        app.terminate()
    }
    private func node(_ id: String) -> XCUIElement {
        app.windows.firstMatch.descendants(matching: .any).matching(identifier: id).firstMatch
    }
    // Same label-or-value access as original ReaderAccessUITests.text.
    // AppKit StaticText publishes reader.location in value, not label.
    private func text(_ id: String) -> String {
        let item = node(id)
        return item.label.isEmpty ? item.value as? String ?? "" : item.label
    }
    private func capture(_ step: String) {
        let captured = audit.capture(app, test: name, step: name + "." + step,
                          screenshot: "d10-" + name + "-" + step) { self.add($0) }
        XCTAssertTrue(captured, "Missing real snapshot at " + step)
    }
    private func wait(_ condition: () -> Bool) -> Bool {
        let deadline = Date().addingTimeInterval(60)
        while Date() < deadline {
            if condition() { return true }
            RunLoop.current.run(until: Date().addingTimeInterval(0.15))
        }
        return condition()
    }
    private func tap(_ id: String) {
        XCTAssertTrue(node(id).waitForExistence(timeout: 60), id)
        if id.hasPrefix("reader."), node("reader.tools.scroll").exists,
           !["reader.more", "reader.back", "reader.records"].contains(id) {
            // Reach by the existing toolbar's native scrolling; never re-tap.
            for _ in 0..<12 {
                let e = node(id), tools = node("reader.tools.scroll")
                if tools.frame.contains(e.frame) && app.windows.firstMatch.frame.contains(e.frame) && e.isHittable { break }
                XCTAssertEqual(tools.elementType, .scrollView, "Only real scroll container may move")
                capture("offscreen-before-scroll-" + id)
                print("D10_TRACE scroll to " + id)
                if e.frame.midX < tools.frame.midX { tools.swipeRight() } else { tools.swipeLeft() }
            }
        }
        capture("before-" + id)
        XCTAssertTrue(node(id).isEnabled, id)
        XCTAssertTrue(node(id).isHittable, id)
        print("D10_TRACE tap once " + id)
        node(id).tap()
    }
    private func shelf() {
        if !node("library.title").exists && node("reader.back").exists {
            tap("reader.back")
            XCTAssertTrue(node("library.title").waitForExistence(timeout: 90))
        }
        XCTAssertTrue(node("library.title").waitForExistence(timeout: 90))
        XCTAssertTrue(wait { !self.node("library.busy").exists })
        XCTAssertFalse(node("library.import.epub").exists, "default launch must hide fixture controls")
    }
    func test01DefaultShelfAndAccountDismissal() throws {
        shelf(); capture("shelf")
        tap("account.choose")
        XCTAssertTrue(node("account.done").waitForExistence(timeout: 30))
        capture("account-settings")
        tap("account.done")
        XCTAssertTrue(wait { !self.node("account.done").exists && self.node("account.choose").isHittable })
        capture("account-dismissed-focus-unobservable")
#if os(macOS)
        print("D10_TRACE Tab then Escape on default shelf; focus owner unobservable")
        app.windows.firstMatch.typeKey(.tab, modifierFlags: [])
        capture("keyboard-tab")
        app.windows.firstMatch.typeKey(.escape, modifierFlags: [])
#else
        print("D10_PENDING mobile hardware/full keyboard access not enabled")
        XCUIDevice.shared.orientation = .landscapeLeft
        XCTAssertTrue(wait { self.app.windows.firstMatch.frame.width > self.app.windows.firstMatch.frame.height })
        capture("shelf-landscape")
        XCUIDevice.shared.orientation = .portrait
#endif
    }
    func test02DefaultReaderLowFrequencyJourney() throws {
        shelf()
        let book = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'library.book.' AND label BEGINSWITH %@", "Sample.epub")).firstMatch
        XCTAssertTrue(book.waitForExistence(timeout: 90), "unmodified prior import regression must seed Sample.epub")
        XCTAssertTrue(book.isHittable)
        print("D10_TRACE tap once Sample.epub"); book.tap()
        XCTAssertTrue(node("reader.page").waitForExistence(timeout: 90))
        XCTAssertTrue(wait { !self.node("reader.busy").exists })
        capture("reader")
        let location = text("reader.location")
        tap("reader.next")
        XCTAssertTrue(wait { !self.node("reader.busy").exists && self.text("reader.location") != location })
        capture("page-turned")
        let font = text("reader.font.value")
        tap("reader.font.increase")
        XCTAssertTrue(wait { self.text("reader.font.value") != font && !self.node("reader.busy").exists })
        capture("reader-font-settings")
        tap("reader.font.decrease")
        XCTAssertTrue(wait { self.text("reader.font.value") == font && !self.node("reader.busy").exists })
        for (open, close) in [("reader.search", "search.close"), ("reader.navigation", "navigation.close"), ("reader.notes", "notes.close")] {
            tap(open); XCTAssertTrue(node(close).waitForExistence(timeout: 30)); capture(open + "-dialog")
            tap(close)
            XCTAssertTrue(wait { !self.node(close).exists && self.node("reader.back").isHittable })
            capture(open + "-dismissed-focus-unobservable")
        }
#if os(iOS)
        capture("more-before-native-trigger")
        let menu = node("reader.more")
        let trigger = menu.buttons.firstMatch
        XCTAssertTrue(wait { menu.exists && trigger.exists && trigger.frame.width > 0 && trigger.frame.height > 0 && self.app.windows.firstMatch.frame.contains(trigger.frame) })
        // Exact native Menu technique documented by original ReadingUITests.
        // Raw AX false remains false; functional success requires popup below.
        A11yAudit.emit("D10_MENU_AX", ["wrapper_hittable": menu.isHittable,
            "trigger_hittable": trigger.isHittable, "functional_reachability": "not-yet-observed",
            "ax_semantics_accepted": false])
        trigger.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
#else
        tap("reader.more")
#endif
        XCTAssertTrue(wait { self.node("reader.records").exists || self.app.menuItems["阅读记录"].exists || self.app.buttons["阅读记录"].exists })
        capture("more-menu")
        if node("reader.records").exists { tap("reader.records") }
        else if app.menuItems["阅读记录"].exists { app.menuItems["阅读记录"].tap() }
        else { app.buttons["阅读记录"].tap() }
        XCTAssertTrue(node("reading.close").waitForExistence(timeout: 30)); capture("records")
        tap("reading.close")
        XCTAssertTrue(wait { !self.node("reading.close").exists && self.node("reader.back").isHittable })
#if os(iOS)
        XCUIDevice.shared.orientation = .landscapeLeft
        XCTAssertTrue(wait { self.app.windows.firstMatch.frame.width > self.app.windows.firstMatch.frame.height })
        capture("reader-landscape")
        XCUIDevice.shared.orientation = .portrait
#else
        let corner = app.windows.firstMatch.coordinate(withNormalizedOffset: CGVector(dx: 0.985, dy: 0.985))
        print("D10_TRACE native window resize -400,-400")
        corner.press(forDuration: 0.2, thenDragTo: corner.withOffset(CGVector(dx: -400, dy: -400)))
        capture("reader-window-small")
#endif
        tap("reader.back"); XCTAssertTrue(node("library.title").waitForExistence(timeout: 90)); shelf(); capture("returned-shelf")
    }
}
