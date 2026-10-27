// SPDX-License-Identifier: MIT
import XCTest
final class ReceiveUITests: XCTestCase {
    func testRemoteBookFirstOpenAndRestart() throws {
        let app = XCUIApplication()
        func e(_ id: String) -> XCUIElement { app.descendants(matching: .any).matching(identifier: id).firstMatch }
        func wait(_ condition: () -> Bool) -> Bool {
            let deadline = Date().addingTimeInterval(150)
            while Date() < deadline { if condition() { return true }; RunLoop.current.run(until: Date().addingTimeInterval(0.2)) }
            return condition()
        }
        func tap(_ id: String) { XCTAssertTrue(wait { e(id).exists && e(id).isHittable && e(id).isEnabled }, app.debugDescription); e(id).tap() }
        app.launchArguments = ["-EXRUITestFixtures", "1", "-EXRFreshState", "1"]
        app.launch(); XCTAssertTrue(wait { e("library.title").exists && !e("library.busy").exists })
        tap("account.choose")
        tap("account.root"); e("account.root").typeText("__D21_ROOT__")
        tap("account.username"); e("account.username").typeText("reader")
        tap("account.password"); e("account.password").typeText("__D21_PASSWORD__")
        tap("account.connect")
        XCTAssertTrue(wait { e("account.sync.start").exists && !e("library.busy").exists })
        tap("account.sync.start")
        let remote = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "library.cloud.")).firstMatch
        XCTAssertTrue(wait { remote.exists && remote.isHittable }, app.debugDescription)
        remote.tap()
        XCTAssertTrue(wait { e("reader.page").exists && !e("reader.busy").exists }, app.debugDescription)
        let screenshot = XCTAttachment(screenshot: XCUIScreen.main.screenshot()); screenshot.name = "received-original-reading"; screenshot.lifetime = .keepAlways; add(screenshot)
        tap("reader.back")
        app.terminate()
        app.launchArguments = ["-EXRUITestFixtures", "1"]
        app.launch()
        XCTAssertTrue(wait { e("library.book.0").exists && !e("library.busy").exists }, app.debugDescription)
        tap("library.book.0")
        XCTAssertTrue(wait { e("reader.page").exists && !e("reader.busy").exists }, app.debugDescription)
        let tree = XCTAttachment(string: app.debugDescription); tree.name = "restart-retained-book"; tree.lifetime = .keepAlways; add(tree)
        app.terminate()
    }
}
