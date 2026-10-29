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
    // DIAGNOSTIC_UI_BEGIN
    // Finite codes only. Separate detail queries run once per failed phase;
    // initial save-status queries run only in the already-open Update sheet.
    // Unknown label/value/error text is never printed or interpolated.
    private let observationOrigin = ProcessInfo.processInfo.systemUptime
    private var observationSequence = 0, lastObservationMS = -5000
    private var lastObservationState = ""
    private var observedFailedDetails: Set<String> = []
    private func observationMS() -> Int {
        Int(max(0, min(4800000, (ProcessInfo.processInfo.systemUptime - observationOrigin) * 1000)))
    }
    private func exactSyncState(label: String, value: Any?, allowMacValue: Bool) -> String {
        // Actual macOS evidence: expanded Text has empty label and state in
        // value. Never prefer a contradictory value over a nonempty label;
        // iOS retains its original label-only interpretation.
        if !label.isEmpty { return label }
        guard allowMacValue, let value = value as? String else { return "" }
        let states = ["未同步", "正在准备原书", "正在接收书架", "准备中", "正在同步",
                      "正在取消", "正在关闭", "已关闭", "本轮扫描完成", "已取消", "同步失败"]
        return states.contains(value) ? value : ""
    }
    private func observedSyncState(_ item: XCUIElementSnapshot) -> String {
#if os(macOS)
        return exactSyncState(label: item.label, value: item.value, allowMacValue: true)
#else
        return exactSyncState(label: item.label, value: item.value, allowMacValue: false)
#endif
    }
    private func assertStateAccessorControls() {
        XCTAssertEqual(exactSyncState(label: "", value: "本轮扫描完成", allowMacValue: true), "本轮扫描完成")
        XCTAssertEqual(exactSyncState(label: "", value: "正在同步", allowMacValue: true), "正在同步")
        XCTAssertEqual(exactSyncState(label: "正在同步", value: "本轮扫描完成", allowMacValue: true), "正在同步")
        XCTAssertEqual(exactSyncState(label: "同步失败", value: "本轮扫描完成", allowMacValue: true), "同步失败")
        XCTAssertEqual(exactSyncState(label: "", value: "可再次同步以接收后续变更", allowMacValue: true), "")
        XCTAssertEqual(exactSyncState(label: "", value: "not-a-state", allowMacValue: true), "")
        XCTAssertEqual(exactSyncState(label: "", value: NSNumber(value: 1), allowMacValue: true), "")
        XCTAssertEqual(exactSyncState(label: "", value: "本轮扫描完成", allowMacValue: false), "")
        XCTAssertTrue(exactMissingCredential(label: "请重新输入此账号的授权信息", value: nil, allowMacValue: true))
        XCTAssertTrue(exactMissingCredential(label: "", value: "请重新输入此账号的授权信息", allowMacValue: true))
        XCTAssertFalse(exactMissingCredential(label: "网络错误", value: "请重新输入此账号的授权信息", allowMacValue: true))
        XCTAssertFalse(exactMissingCredential(label: "", value: "请重新输入此账号的授权信息", allowMacValue: false))
        XCTAssertFalse(exactMissingCredential(label: "", value: NSNumber(value: 1), allowMacValue: true))
        XCTAssertFalse(exactMissingCredential(label: "", value: "not-the-fixed-detail", allowMacValue: true))
        let phrase = "请重新输入此账号的授权信息"
        let shadow = ["label": "网络错误", "value": phrase]
        let valid = ["label": phrase, "value": "not-the-fixed-detail"]
        let query = missingCredentialPredicate(allowMacValue: true)
        XCTAssertFalse(query.evaluate(with: shadow))
        XCTAssertEqual([shadow, valid].first { query.evaluate(with: $0) }?["label"], phrase)
        XCTAssertTrue(query.evaluate(with: ["label": "", "value": phrase]))
        XCTAssertFalse(missingCredentialPredicate(allowMacValue: false).evaluate(with: ["label": "", "value": phrase]))
    }
    private func exactMissingCredential(label: String, value: Any?, allowMacValue: Bool) -> Bool {
        let phrase = "请重新输入此账号的授权信息"
        if !label.isEmpty { return label.contains(phrase) }
        guard allowMacValue, let value = value as? String else { return false }
        return value.contains(phrase)
    }
    private func missingCredentialObserved() -> Bool {
#if os(macOS)
        let candidate = app.staticTexts.matching(missingCredentialPredicate(allowMacValue: true)).firstMatch
        guard let item = try? candidate.snapshot() else { return false }
        return exactMissingCredential(label: item.label, value: item.value, allowMacValue: true)
#else
        // Preserve the original iOS label-only existence predicate.
        return app.staticTexts.matching(missingCredentialPredicate(allowMacValue: false)).firstMatch.exists
#endif
    }
    private func missingCredentialPredicate(allowMacValue: Bool) -> NSPredicate {
        let phrase = "请重新输入此账号的授权信息"
        return allowMacValue ? NSPredicate(format: "label CONTAINS %@ OR (label == %@ AND value CONTAINS %@)", phrase, "", phrase) :
            NSPredicate(format: "label CONTAINS %@", phrase)
    }
    private func observeInitialSaveStatus() {
        guard stages.isEmpty else { return }
        let candidates = [
            ("saved", "授权信息已保存到钥匙串"),
            ("remember-update-incomplete", "本次使用新的授权，钥匙串更新未完成"),
            ("session-only", "授权信息仅保留在本次运行中"),
            ("anonymous", "匿名连接，未保存授权信息"),
            ("anonymous-remove-incomplete", "匿名连接；钥匙串中的旧授权未能移除"),
            ("session-remove-incomplete", "本次使用临时授权；钥匙串中的旧授权未能移除")]
        var matched: [String] = []
        for (code, phrase) in candidates {
            if app.staticTexts.matching(NSPredicate(format: "label == %@ OR value == %@", phrase, phrase)).firstMatch.exists {
                matched.append(code)
            }
        }
        let status = matched.count == 1 ? matched[0] : matched.isEmpty ? "absent" : "ambiguous"
        print("EXR_PRIVACY_UI_SAVE elapsed_ms=\(observationMS()) status=\(status)")
    }
    private func observationCode(_ value: String) -> String {
        switch value {
        case "": return "empty"
        case "未同步": return "idle"
        case "正在准备原书": return "preparing-original"
        case "正在接收书架": return "receiving-shelf"
        case "准备中": return "preparing"
        case "正在同步": return "running"
        case "正在取消": return "cancelling"
        case "正在关闭": return "closing"
        case "已关闭": return "closed"
        case "本轮扫描完成": return "finished"
        case "已取消": return "cancelled"
        case "同步失败": return "failed"
        case "可再次同步以接收后续变更": return "next-sync"
        case "已提交的历史会保留，可手动重试": return "retry-preserves-history"
        default: return "other"
        }
    }
    private func observedSnapshot(_ id: String) -> XCUIElementSnapshot? {
        let item = try? node(id).snapshot()
        if id == "account.sync.state" {
            observationSequence += 1
            let elapsed = observationMS()
            let phase = stages.last == "remember_closed" ? "remembered" :
                stages.last == "remember_reopened" ? "session" :
                stages.last == "session_closed" ? "missing-restart" : "unknown"
            let label = item?.label ?? "", value = (item?.value as? String) ?? ""
            let labelCode = item == nil ? "unavailable" : observationCode(label)
            let valueCode = item == nil ? "unavailable" : observationCode(value)
            let valueKind = item?.value == nil ? "none" : item?.value is String ? "string" :
                item?.value is NSNumber ? "number" : "other"
            let labelMissing = label.contains("请重新输入此账号的授权信息") ? 1 : 0
            let valueMissing = value.contains("请重新输入此账号的授权信息") ? 1 : 0
            let snapshot = item == nil ? 0 : 1
            let state = "phase=\(phase) snapshot=\(snapshot) label=\(labelCode) value=\(valueCode) value_kind=\(valueKind) missing_label=\(labelMissing) missing_value=\(valueMissing)"
            if state != lastObservationState || elapsed - lastObservationMS >= 5000 {
                print("EXR_PRIVACY_UI_STATE seq=\(observationSequence) elapsed_ms=\(elapsed) " + state)
                lastObservationState = state; lastObservationMS = elapsed
            }
            if let item = item, observedSyncState(item) == "同步失败", observedFailedDetails.insert(phase).inserted {
                let phrase = "请重新输入此账号的授权信息"
                let exists = app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@ OR value CONTAINS %@", phrase, phrase)).firstMatch.exists
                print("EXR_PRIVACY_UI_DETAIL elapsed_ms=\(observationMS()) phase=\(phase) missing_credential=\(exists ? 1 : 0)")
            }
        }
        return item
    }
    // DIAGNOSTIC_UI_END
    private func node(_ id: String) -> XCUIElement {
        app.descendants(matching: .any).matching(identifier: id).firstMatch
    }
    private func text(_ id: String) -> String {
        guard let item = observedSnapshot(id) else { return "" }
        // Compact sync controls expose the message in value, not the state.
        if id == "account.sync.state" { return observedSyncState(item) }
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
        observeInitialSaveStatus()
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
        assertStateAccessorControls()
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
        XCTAssertTrue(wait(30) { self.missingCredentialObserved() ||
            ((self.node("account.sync.state").value as? String) ?? "").contains("请重新输入此账号的授权信息") },
            "Session-only restart must require credentials")
        try closeAndObserve("session_reopened_missing")
    }
}
