// SPDX-License-Identifier: MIT
import XCTest
import Foundation
final class ReceiveUITests: XCTestCase {
    func testRemoteBookFirstOpenAndRestart() throws {
        let app = XCUIApplication()
        func e(_ id: String) -> XCUIElement { app.descendants(matching: .any).matching(identifier: id).firstMatch }
        func wait(_ condition: () -> Bool) -> Bool {
            let deadline = Date().addingTimeInterval(150)
            while Date() < deadline { if condition() { return true }; RunLoop.current.run(until: Date().addingTimeInterval(0.2)) }
            return condition()
        }
        func tap(_ id: String) {
            XCTAssertTrue(e(id).waitForExistence(timeout: 30), id)
            for _ in 0..<8 {
                if e(id).isHittable { break }
                let form = e("account.form")
                guard form.exists else { break }
                let earlier = e(id).frame.midY < form.frame.midY
#if os(macOS)
                form.scroll(byDeltaX: 0, deltaY: earlier ? 260 : -260)
#else
                if earlier { form.swipeDown() } else { form.swipeUp() }
#endif
            }
            XCTAssertTrue(wait { e(id).exists && e(id).isHittable && e(id).isEnabled }, app.debugDescription); e(id).tap()
        }
        func control(_ action: String) {
            let completed = expectation(description: "HTTPS fixture control " + action)
            var request = URLRequest(url: URL(string: "__D21_CONTROL__" + action)!)
            request.httpMethod = "POST"; request.setValue("__D21_TOKEN__", forHTTPHeaderField: "Authorization")
            URLSession.shared.dataTask(with: request) { _, response, error in
                XCTAssertNil(error)
                XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200)
                completed.fulfill()
            }.resume()
            self.wait(for: [completed], timeout: 30)
        }
        app.launchArguments = ["-EXRUITestFixtures", "1", "-EXRFreshState", "1"]
        app.launch(); XCTAssertTrue(wait { e("library.title").exists && !e("library.busy").exists })
        tap("account.choose")
        tap("account.root"); e("account.root").typeText("__D21_ROOT__\n")
        tap("account.username"); e("account.username").typeText("reader\n")
        tap("account.password"); e("account.password").typeText("__D21_PASSWORD__\n")
        tap("account.connect")
        XCTAssertTrue(wait { e("account.sync.start").exists && !e("library.busy").exists })
        tap("account.sync.start")
        let remote = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "library.cloud.")).firstMatch
        XCTAssertTrue(wait { remote.exists && remote.isHittable }, app.debugDescription)
        control("corrupt")
        remote.tap()
        XCTAssertTrue(wait { e("library.error").exists && !e("library.busy").exists }, app.debugDescription)
        XCTAssertTrue(remote.exists)
        control("interrupt")
        remote.tap()
        XCTAssertTrue(wait { e("library.error").exists && !e("library.busy").exists }, app.debugDescription)
        XCTAssertTrue(remote.exists)
        control("delay")
        remote.tap(); tap("library.cancel")
        XCTAssertTrue(wait { !e("library.busy").exists && remote.exists }, app.debugDescription)
        control("missing")
        remote.tap()
        XCTAssertTrue(wait { e("reader.page").exists && !e("reader.busy").exists }, app.debugDescription)
        let screenshot = XCTAttachment(screenshot: XCUIScreen.main.screenshot()); screenshot.name = "received-original-reading"; screenshot.lifetime = .keepAlways; add(screenshot)
        let initialLocation = e("reader.location").label
        tap("reader.next")
        XCTAssertTrue(wait { !e("reader.busy").exists && e("reader.location").label != initialLocation })
        let savedLocation = e("reader.location").label
        tap("reader.back")
        app.terminate()
        control("offline")
        app.launchArguments = ["-EXRUITestFixtures", "1"]
        app.launch()
        XCTAssertTrue(wait { e("library.book.0").exists && !e("library.busy").exists }, app.debugDescription)
        tap("library.book.0")
        XCTAssertTrue(wait { e("reader.page").exists && !e("reader.busy").exists }, app.debugDescription)
        XCTAssertEqual(e("reader.location").label, savedLocation, "Offline restart must preserve reading position")
        let tree = XCTAttachment(string: app.debugDescription); tree.name = "restart-retained-book"; tree.lifetime = .keepAlways; add(tree)
        app.terminate()
        control("restore")
    }
}
