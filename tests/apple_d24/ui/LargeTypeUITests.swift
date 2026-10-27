// SPDX-License-Identifier: MIT
import XCTest
#if os(iOS)
import UIKit
#endif

final class LargeTypeUITests: XCTestCase {
    let app = XCUIApplication()
    func e(_ id: String) -> XCUIElement { app.descendants(matching: .any).matching(identifier: id).firstMatch }
    func wait(_ check: () -> Bool) -> Bool {
        let end = Date().addingTimeInterval(60)
        while Date() < end { if check() { return true }; RunLoop.current.run(until: Date().addingTimeInterval(0.15)) }
        return check()
    }
    func text(_ id: String) -> String { e(id).label.isEmpty ? (e(id).value as? String ?? "") : e(id).label }
    func ready() { XCTAssertTrue(wait { self.e("reader.page").exists && !self.e("reader.busy").exists }) }
    func tap(_ id: String) {
        let scroll = e("reader.tools.scroll")
        for _ in 0..<12 {
            let f = e(id).frame
            if !f.isEmpty && app.windows.firstMatch.frame.contains(f) && (!scroll.exists || !id.hasPrefix("reader.") || ["reader.tools.toggle", "reader.back"].contains(id) || scroll.frame.contains(f)) { break }
            if scroll.exists {
                if f.midX < scroll.frame.midX { scroll.swipeRight() } else { scroll.swipeLeft() }
            }
        }
        XCTAssertTrue(wait { self.e(id).exists && self.e(id).isEnabled && self.e(id).isHittable }, id)
        e(id).tap()
    }
    func record(_ name: String) {
        let a = XCTAttachment(screenshot: app.screenshot()); a.name = name; a.lifetime = .keepAlways; add(a)
        print("D24 native hierarchy \(name): \(app.debugDescription)")
        let t = XCTAttachment(string: app.debugDescription); t.name = name + "-tree"; t.lifetime = .keepAlways; add(t)
    }
    func area(_ minimum: CGFloat) {
        ready()
        let window = app.windows.firstMatch.frame
        let page = e("reader.page").frame
        print("D24 page \(page) window \(window) ratio \(page.height / window.height)")
        XCTAssertTrue(window.insetBy(dx: -2, dy: -2).contains(page))
        XCTAssertGreaterThanOrEqual(page.height / window.height, minimum, "Real readable page area: \(page), window: \(window)")
        XCTAssertTrue(e("reader.back").isHittable)
        XCTAssertTrue(window.contains(e("reader.back").frame))
        XCTAssertTrue(e("reader.tools.toggle").isHittable)
    }
    func testMaximumSystemTypeSmallLandscapeAndRecovery() throws {
#if os(iOS)
        XCTAssertGreaterThan(UIFont.preferredFont(forTextStyle: .caption1).pointSize, 20)
        XCUIDevice.shared.orientation = .portrait
        app.launchArguments = ["-EXRUITestFixtures", "1", "-EXRFreshState", "1"]
        app.launch()
        XCTAssertTrue(wait { self.e("library.import.epub").exists && !self.e("library.busy").exists })
        tap("library.import.epub")
        XCTAssertTrue(wait { self.e("library.book.0").exists && !self.e("library.busy").exists })
        tap("library.book.0"); ready()
        area(0.45); record("maximum-type-portrait")
        XCUIDevice.shared.orientation = .landscapeLeft
        XCTAssertTrue(wait { self.app.windows.firstMatch.frame.width > self.app.windows.firstMatch.frame.height })
        area(0.35); record("maximum-type-landscape-tools-visible")
        let expanded = e("reader.page").frame.height
        tap("reader.tools.toggle")
        XCTAssertTrue(wait { !self.e("reader.tools.scroll").exists })
        area(0.5)
        XCTAssertGreaterThan(e("reader.page").frame.height, expanded)
        record("maximum-type-landscape-tools-hidden")
        tap("reader.tools.toggle")
        XCTAssertTrue(e("reader.tools.scroll").waitForExistence(timeout: 30))
        let before = text("reader.location")
        tap("reader.next")
        XCTAssertTrue(wait { !self.e("reader.busy").exists && self.text("reader.location") != before })
        let font = text("reader.font.value")
        tap("reader.font.increase")
        XCTAssertTrue(wait { !self.e("reader.busy").exists && self.text("reader.font.value") != font })
        let savedFont = text("reader.font.value")
        let savedLocation = text("reader.location")
        tap("reader.notes")
        XCTAssertTrue(e("notes.title").waitForExistence(timeout: 30))
        tap("notes.close")
        XCTAssertTrue(wait { !self.e("notes.title").exists })
        area(0.35)
        XCTAssertEqual(text("reader.font.value"), savedFont)
        XCTAssertEqual(text("reader.location"), savedLocation)
        XCUIDevice.shared.orientation = .portrait
        XCTAssertTrue(wait { self.app.windows.firstMatch.frame.height > self.app.windows.firstMatch.frame.width })
        area(0.45); record("maximum-type-portrait-restored")
        tap("reader.back")
        XCTAssertTrue(e("library.title").waitForExistence(timeout: 30))
        tap("library.book.0"); ready()
        XCTAssertEqual(text("reader.font.value"), savedFont)
        record("maximum-type-reopened")
        app.terminate()
#else
        throw XCTSkip("D24 requires actual iOS simulator system text sizing")
#endif
    }
}
