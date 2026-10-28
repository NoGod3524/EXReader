// SPDX-License-Identifier: MIT
import Foundation
import XCTest

final class AccountFailureUITests: XCTestCase {
    private let app = XCUIApplication()

    private func node(_ id: String) -> XCUIElement {
        app.descendants(matching: .any).matching(identifier: id).firstMatch
    }
    private func wait(_ seconds: TimeInterval = 60, _ condition: () -> Bool) -> Bool {
        let deadline = Date().addingTimeInterval(seconds)
        while Date() < deadline {
            if condition() { return true }
            RunLoop.current.run(until: Date().addingTimeInterval(0.15))
        }
        return condition()
    }
    private func tap(_ id: String) {
        let item = node(id)
        XCTAssertTrue(item.waitForExistence(timeout: 30), id)
        for _ in 0..<8 where !item.isHittable {
            let form = node("account.form")
            guard form.exists else { break }
#if os(macOS)
            form.scroll(byDeltaX: 0, deltaY: item.frame.midY < form.frame.midY ? 260 : -260)
#else
            if item.frame.midY < form.frame.midY { form.swipeDown() } else { form.swipeUp() }
#endif
        }
        XCTAssertTrue(wait { item.isHittable && item.isEnabled }, id)
        item.tap()
    }
    private func value(_ id: String) -> String {
        let item = node(id)
        return item.label.isEmpty ? item.value as? String ?? "" : item.label
    }
    private func type(_ id: String, _ text: String) {
        tap(id)
        node(id).typeText(text + "\n")
    }

    func testAuthorizationFailurePreservesBookAndRetry() throws {
        continueAfterFailure = false
        let root = try XCTUnwrap(ProcessInfo.processInfo.environment["EXR_FAILURE_UI_ROOT"])
        app.launchArguments = ["-EXRUITestFixtures", "1"]
        app.launch()
        defer {
            let attachment = XCTAttachment(screenshot: app.screenshot())
            attachment.name = "account-failure-final-screen"; attachment.lifetime = .keepAlways; add(attachment)
            app.terminate()
        }
        tap("account.choose")
        type("account.root", root)
        type("account.username", "wrong")
        type("account.password", "wrong")
        tap("account.connect")
        XCTAssertTrue(wait { self.node("account.choose").label == "云盘书库，" + root && !self.node("account.connect").exists })
        XCTAssertTrue(wait(90) { self.node("library.title").exists && !self.node("library.busy").exists && self.node("library.import.epub").exists })
        tap("library.import.epub")
        let book = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'library.book.'")).firstMatch
        XCTAssertTrue(book.waitForExistence(timeout: 90))
        XCTAssertTrue(wait { !self.node("library.busy").exists })
        tap("account.sync.start")
        XCTAssertTrue(wait(180) { self.value("account.sync.state") == "同步失败" })
        XCTAssertTrue(book.exists, "the local original must remain available after failure")
        XCTAssertTrue(node("account.sync.start").isEnabled, "failure must allow a retry")

        // The fixture reads the real catalog after the displayed terminal state,
        // and responds only after the outbox observation has been persisted.
        let observed = expectation(description: "capture failed-state outbox before retry")
        let url = try XCTUnwrap(URL(string: root + "__exreader_test_failure_observed__"))
        URLSession.shared.dataTask(with: url) { _, response, error in
            XCTAssertNil(error)
            XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 204)
            observed.fulfill()
        }.resume()
        wait(for: [observed], timeout: 60)

        tap("account.choose")
        let row = app.buttons.matching(NSPredicate(format: "label == %@", root)).firstMatch
        XCTAssertTrue(row.waitForExistence(timeout: 30))
        let profile = String(row.identifier.dropFirst("account.open.".count))
        XCTAssertNotNil(UUID(uuidString: profile))
        tap("account.update." + profile)
        type("account.username", "reader")
        type("account.password", "failure-fixture-password")
        tap("account.connect")
        XCTAssertTrue(wait { !self.node("account.connect").exists })
        XCTAssertTrue(wait(60) { self.value("account.sync.state") == "已关闭" })
        tap("account.sync.start")
        XCTAssertTrue(wait(180) { self.value("account.sync.state") == "本轮扫描完成" })
        XCTAssertTrue(book.exists, "successful retry must preserve the original")
    }
}
