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
        capture("terminal")
        let tree = XCTAttachment(string: app.debugDescription)
        tree.name = "default-tree-" + name; tree.lifetime = .keepAlways; add(tree)
#if os(iOS)
        XCUIDevice.shared.orientation = .portrait
#endif
        app.terminate()
    }
    private func node(_ id: String) -> XCUIElement {
        app.descendants(matching: .any).matching(identifier: id).firstMatch
    }
    private func capture(_ step: String) {
        _ = audit.capture(app, test: name, step: name + "." + step,
                          screenshot: "d04-" + name + "-" + step) { self.add($0) }
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
                if tools.frame.contains(e.frame) && e.isHittable { break }
                print("D04_TRACE scroll to " + id)
                if e.frame.midX < tools.frame.midX { tools.swipeRight() } else { tools.swipeLeft() }
            }
        }
        capture("before-" + id)
        XCTAssertTrue(node(id).isEnabled, id)
        XCTAssertTrue(node(id).isHittable, id)
        print("D04_TRACE tap once " + id)
        node(id).tap()
    }
    private func shelf() {
        if node("reader.back").exists { tap("reader.back") }
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
        print("D04_TRACE Tab then Escape on default shelf; focus owner unobservable")
        app.windows.firstMatch.typeKey(.tab, modifierFlags: [])
        capture("keyboard-tab")
        app.windows.firstMatch.typeKey(.escape, modifierFlags: [])
#else
        print("D04_PENDING mobile hardware/full keyboard access not enabled")
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
        print("D04_TRACE tap once Sample.epub"); book.tap()
        XCTAssertTrue(node("reader.page").waitForExistence(timeout: 90))
        XCTAssertTrue(wait { !self.node("reader.busy").exists })
        capture("reader")
        let location = node("reader.location").label
        tap("reader.next")
        XCTAssertTrue(wait { !self.node("reader.busy").exists && self.node("reader.location").label != location })
        capture("page-turned")
        for (open, close) in [("reader.search", "search.close"), ("reader.navigation", "navigation.close"), ("reader.notes", "notes.close")] {
            tap(open); XCTAssertTrue(node(close).waitForExistence(timeout: 30)); capture(open + "-dialog")
            tap(close)
            XCTAssertTrue(wait { !self.node(close).exists && self.node("reader.back").isHittable })
            capture(open + "-dismissed-focus-unobservable")
        }
        tap("reader.more"); capture("more-menu")
        tap("reader.records")
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
        print("D04_TRACE native window resize -400,-400")
        corner.press(forDuration: 0.2, thenDragTo: corner.withOffset(CGVector(dx: -400, dy: -400)))
        capture("reader-window-small")
#endif
        tap("reader.back"); shelf(); capture("returned-shelf")
    }
}
