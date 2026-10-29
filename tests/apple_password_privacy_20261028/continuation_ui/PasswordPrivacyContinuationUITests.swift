// SPDX-License-Identifier: MIT
import Foundation
import XCTest
#if os(iOS)
import UIKit
#endif

// Diagnostic observation acknowledgements are not privacy acceptance.
// The original strict test remains unchanged in its separate target/run.
final class PasswordPrivacyContinuationUITests: XCTestCase {
    private let app = XCUIApplication()
    private var root = "", profile = ""
    private var stages: [String] = []
    private func node(_ id: String) -> XCUIElement {
        app.descendants(matching: .any).matching(identifier: id).firstMatch
    }
    private func text(_ id: String) -> String {
        guard let item = try? node(id).snapshot() else { return "" }
        // Compact sync controls expose the message in value, not the state.
        if id == "account.sync.state" { return item.label }
        return (item.value as? String).flatMap { $0.isEmpty ? nil : $0 } ?? item.label
    }
    private func wait(_ seconds: TimeInterval = 90, _ condition: () -> Bool) -> Bool {
        let deadline = Date().addingTimeInterval(seconds)
        while Date() < deadline {
            if condition() { return true }
            RunLoop.current.run(until: Date().addingTimeInterval(0.15))
        }
        return condition()
    }
    private func reveal(_ id: String) {
        let target = node(id), scroll = node("account.form")
        XCTAssertTrue(target.waitForExistence(timeout: 30), id)
        for _ in 0..<16 {
            if target.isHittable && (!scroll.exists || scroll.frame.contains(CGPoint(x: target.frame.midX, y: target.frame.midY))) { break }
            guard scroll.exists else { break }
#if os(macOS)
            scroll.scroll(byDeltaX: 0, deltaY: target.frame.midY < scroll.frame.midY ? 180 : -180)
#else
            if target.frame.midY < scroll.frame.midY { scroll.swipeDown(velocity: .slow) }
            else { scroll.swipeUp(velocity: .slow) }
#endif
        }
        XCTAssertTrue(wait { target.isHittable && target.isEnabled }, "Unavailable control: " + id)
    }
    private func tap(_ id: String) { reveal(id); node(id).tap() }
    private func type(_ id: String, _ value: String) { tap(id); node(id).typeText(value + "\n") }
    private func remember(_ enabled: Bool) {
        reveal("account.remember")
        let tagged = node("account.remember")
#if os(macOS)
        let toggle = tagged.checkBoxes.firstMatch.exists ? tagged.checkBoxes.firstMatch : tagged
#else
        let toggle = tagged.switches.firstMatch.exists ? tagged.switches.firstMatch : tagged
#endif
        func state() -> String {
            ((toggle.value as? String) ?? (toggle.value as? NSNumber)?.stringValue ?? "").lowercased()
        }
        XCTAssertTrue(["0", "1", "on", "off", "true", "false"].contains(state()), "Native toggle value must be observable")
        let on = ["1", "on", "true"]
        if on.contains(state()) != enabled { toggle.tap() }
        let expected = enabled ? on : ["0", "off", "false"]
        XCTAssertTrue(wait { expected.contains(state()) }, "Actual Remember control did not change")
    }
    private func selected() {
        XCTAssertTrue(wait { self.node("account.choose").label == "云盘书库，" + self.root &&
            !self.node("account.connect").exists && !self.node("library.busy").exists })
    }
    private func launch() {
        app.launchArguments = ["-EXRUITestFixtures", "1", "-AppleLanguages", "(en)", "-AppleLocale", "en_US"]
        app.launch()
        XCTAssertTrue(node("account.choose").waitForExistence(timeout: 90))
    }
    private func chooseUpdate() throws {
        tap("account.choose")
        let row = app.buttons.matching(NSPredicate(format: "label == %@", root)).firstMatch
        XCTAssertTrue(row.waitForExistence(timeout: 30))
        let value = String(row.identifier.dropFirst("account.open.".count))
        XCTAssertNotNil(UUID(uuidString: value))
        if profile.isEmpty { profile = value } else { XCTAssertEqual(value, profile) }
        tap("account.update." + profile)
        // Display-only observation. A masked/empty SecureField is not proof that
        // its underlying secret is absent; restart/network/storage are the oracle.
        for id in ["account.form", "account.username", "account.password", "account.root"] {
            XCTAssertTrue(node(id).waitForExistence(timeout: 30), "Actual update field absent: " + id)
        }
        let username = try XCTUnwrap(node("account.username").value as? String, "Username field value unavailable")
        let password = try XCTUnwrap(node("account.password").value as? String, "Secure field value unavailable")
        XCTAssertTrue(username.isEmpty || username == "用户名（匿名访问可留空）", "Username field was prefilled")
        XCTAssertTrue(password.isEmpty || password == "密码或应用专用密码", "Secure field did not present an empty display")
        XCTAssertFalse(node("account.root").isEnabled)
    }
    private func sync() {
        tap("account.sync.start")
        XCTAssertTrue(wait(180) { self.text("account.sync.state") == "本轮扫描完成" })
    }
    private func closeAndObserve(_ stage: String) throws {
        let screenshot = XCTAttachment(screenshot: app.screenshot())
        screenshot.name = "privacy-" + stage; screenshot.lifetime = .keepAlways; add(screenshot)
        app.terminate(); XCTAssertTrue(app.wait(for: .notRunning, timeout: 20))
        let finished = expectation(description: stage)
        let url = try XCTUnwrap(URL(string: root + "__privacy__/" + stage))
        URLSession.shared.dataTask(with: url) { _, response, error in
            XCTAssertNil(error, "Loopback observation failed")
            XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 204,
                           "Complete evidence and strict verdict must be recorded before diagnostic continuation")
            finished.fulfill()
        }.resume()
        wait(for: [finished], timeout: 90)
        stages.append(stage)
    }
    func testDiagnosticContinuationRememberUpdateRestart() throws {
        continueAfterFailure = false
        let environment = ProcessInfo.processInfo.environment
        root = try XCTUnwrap(environment["EXR_PRIVACY_ROOT"])
        let user = try XCTUnwrap(environment["EXR_PRIVACY_USER"])
        let remembered = try XCTUnwrap(environment["EXR_PRIVACY_REMEMBERED"])
        let transient = try XCTUnwrap(environment["EXR_PRIVACY_SESSION"])
#if os(iOS)
#if EXR_PRIVACY_IPAD
        XCUIDevice.shared.orientation = .landscapeLeft
#else
        XCUIDevice.shared.orientation = .portrait
#endif
#endif
        defer {
            let data = try? JSONSerialization.data(withJSONObject: ["stages": stages, "profile": profile,
                "operation": "real Remember off and Update; not a dedicated Forget action",
                "diagnostic_continuation": true], options: [.sortedKeys])
            let item = XCTAttachment(data: data ?? Data(), uniformTypeIdentifier: "public.json")
            item.name = "privacy-stages.json"; item.lifetime = .keepAlways; add(item)
            app.terminate()
        }
        launch(); tap("account.choose")
        type("account.root", root); type("account.username", user); type("account.password", remembered)
        remember(true); tap("account.connect"); selected()
        tap("library.import.epub")
        XCTAssertTrue(wait { self.node("library.book.0").exists && !self.node("library.busy").exists })
        try chooseUpdate(); tap("account.done")
        try closeAndObserve("remember_closed")

        launch(); selected(); XCTAssertTrue(node("library.book.0").exists)
        sync() // The new process must retrieve the remembered value from Keychain.
        try closeAndObserve("remember_reopened")

        launch(); selected(); try chooseUpdate()
        type("account.username", user); type("account.password", transient)
        remember(false); tap("account.connect"); selected(); sync()
        try closeAndObserve("session_closed")

        launch(); selected(); XCTAssertTrue(node("library.book.0").exists)
        tap("account.sync.start")
        XCTAssertTrue(wait { self.text("account.sync.state") == "同步失败" })
        let missing = app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "请重新输入此账号的授权信息")).firstMatch
        XCTAssertTrue(wait(30) { missing.exists ||
            ((self.node("account.sync.state").value as? String) ?? "").contains("请重新输入此账号的授权信息") },
            "Session-only restart must require credentials")
        try closeAndObserve("session_reopened_missing")
    }
}
