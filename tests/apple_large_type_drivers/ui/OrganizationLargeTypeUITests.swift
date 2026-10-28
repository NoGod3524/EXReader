// SPDX-License-Identifier: MIT
import XCTest
import UIKit

final class OrganizationLargeTypeUITests: XCTestCase {
    private let app = XCUIApplication()
    private func element(_ id: String) -> XCUIElement { app.descendants(matching: .any).matching(identifier: id).firstMatch }
    private func wait(_ check: () -> Bool) -> Bool {
        let end = Date().addingTimeInterval(60)
        while Date() < end { if check() { return true }; RunLoop.current.run(until: Date().addingTimeInterval(0.15)) }
        return check()
    }
    override func setUpWithError() throws { continueAfterFailure = false }
    override func tearDownWithError() throws { record("terminal"); app.terminate() }
    private func record(_ name: String) {
        let screen = XCTAttachment(screenshot: app.screenshot()); screen.name = "organization-large-" + name; screen.lifetime = .keepAlways; add(screen)
        let tree = XCTAttachment(string: app.debugDescription); tree.name = "organization-large-" + name + "-tree"; tree.lifetime = .keepAlways; add(tree)
        print("ORGANIZATION LARGE \(name): \(app.debugDescription)")
    }
    private func tap(_ id: String) {
        let target = element(id)
        XCTAssertTrue(target.waitForExistence(timeout: 60), id)
        if id.hasPrefix("organization.") && id != "organization.close" {
            let scroll = element("organization.scroll")
            for _ in 0..<8 {
                if !scroll.exists || scroll.frame.contains(target.frame) { break }
                if target.frame.midY < scroll.frame.midY { scroll.swipeDown() } else { scroll.swipeUp() }
            }
            if scroll.exists { XCTAssertTrue(scroll.frame.contains(target.frame), "Clipped in organizer viewport: \(id)") }
        }
        XCTAssertTrue(wait { target.isEnabled && target.isHittable }, "Unreachable \(id): \(app.debugDescription)")
        XCTAssertTrue(app.windows.firstMatch.frame.insetBy(dx: -2, dy: -2).contains(target.frame), "Offscreen \(id): \(target.frame)")
        target.tap()
    }
    private func start(_ orientation: UIDeviceOrientation) {
        XCTAssertGreaterThan(UIFont.preferredFont(forTextStyle: .caption1).pointSize, 20)
        XCUIDevice.shared.orientation = orientation
        app.launchArguments = ["-EXRUITestFixtures", "1"]
        app.launch()
        if element("reader.back").exists { tap("reader.back") }
        XCTAssertTrue(wait { self.element("library.book.0").exists && !self.element("library.busy").exists })
        tap("library.book.0")
        XCTAssertTrue(wait { self.element("reader.page").exists && !self.element("reader.busy").exists })
        record("reading")
        tap("reader.back")
        XCTAssertTrue(element("library.title").waitForExistence(timeout: 60))
        tap("library.organization")
        XCTAssertTrue(element("organization.close").waitForExistence(timeout: 60))
        record("opened")
    }
    private func checkKindsAndReturn() {
        for kind in ["shelf", "tag", "series"] { tap("organization.kind." + kind) }
        tap("organization.refresh")
        tap("organization.create")
        tap("organization.name")
        let groupName = "Maximum Type Group"
        element("organization.name").typeText(groupName + "\n")
        XCTAssertTrue(wait { self.app.keyboards.count == 0 }, "Done must dismiss the keyboard before continuing")
        tap("organization.save")
        let group = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@ AND label == %@", "organization.group.", groupName)).firstMatch
        XCTAssertTrue(group.waitForExistence(timeout: 60), "Created group did not appear")
        record("created-at-maximum-type")
        tap("organization.close")
        XCTAssertTrue(element("library.title").waitForExistence(timeout: 60))
        tap("library.book.0")
        XCTAssertTrue(wait { self.element("reader.page").exists && !self.element("reader.busy").exists })
        tap("reader.back")
        record("returned")
    }
    // Setup-only: the test-only fixture control is taller than its scroll viewport
    // at maximum type. Import via the actual app at default size, then the runner
    // independently sets and records the real OS maximum size for both tests.
    func testPrepareOriginalThroughApp() {
        XCUIDevice.shared.orientation = .portrait
        app.launchArguments = ["-EXRUITestFixtures", "1", "-EXRFreshState", "1"]
        app.launch()
        XCTAssertTrue(wait { self.element("library.import.epub").exists && !self.element("library.busy").exists })
        tap("library.import.epub")
        XCTAssertTrue(wait { self.element("library.book.0").exists && !self.element("library.busy").exists })
        record("default-size-setup-only")
    }
    func testMaximumTypePortraitOrganizationAndReturn() {
        start(.portrait)
        checkKindsAndReturn()
    }
    func testMaximumTypeLandscapeOrganizationAndReturn() {
        start(.landscapeLeft)
        checkKindsAndReturn()
        XCUIDevice.shared.orientation = .portrait
    }
}
