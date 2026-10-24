// SPDX-License-Identifier: MIT
import XCTest

final class AccountUITests: XCTestCase {
    private var app: XCUIApplication!
    private var steps: [String] = []

    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication()
        app.launchArguments = ["-EXRUITestFixtures", "1"]
        steps = []
        app.launch()
        XCTAssertTrue(node("account.choose").waitForExistence(timeout: 90))
    }

    override func tearDownWithError() throws {
        let report: [String: Any] = ["test": name, "steps": steps]
        let data = try JSONSerialization.data(withJSONObject: report, options: [.sortedKeys])
        let attachment = XCTAttachment(string: String(decoding: data, as: UTF8.self))
        attachment.name = "account-steps-\(name).json"; attachment.lifetime = .keepAlways; add(attachment)
        let screenshot = XCTAttachment(screenshot: app.screenshot())
        screenshot.name = "account-screen-\(name)"; screenshot.lifetime = .keepAlways; add(screenshot)
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

    private func tap(_ identifier: String) {
        XCTAssertTrue(node(identifier).waitForExistence(timeout: 30), identifier)
        XCTAssertTrue(wait { self.node(identifier).isHittable && self.node(identifier).isEnabled }, identifier)
        node(identifier).tap()
    }

    private func replaceRoot(_ root: String) {
        let field = node("account.root")
        XCTAssertTrue(field.waitForExistence(timeout: 30))
        field.tap()
        XCTAssertFalse((field.value as? String ?? "").hasPrefix("http"), "new connection form must start empty")
        field.typeText(root + "\n")
    }

    private func selected(_ root: String) -> Bool {
        node("account.choose").label == (root == "本地书库" ? root : "云盘书库，" + root)
    }

    private func text(_ identifier: String) -> String {
        let item = node(identifier)
        return item.label.isEmpty ? item.value as? String ?? "" : item.label
    }

    private func create(_ root: String) {
        tap("account.choose")
        replaceRoot(root)
        tap("account.connect")
        XCTAssertTrue(wait { self.selected(root) && !self.node("account.connect").exists })
        XCTAssertTrue(node("account.sync.start").waitForExistence(timeout: 60))
    }

    private func library() {
        if node("reader.back").exists { tap("reader.back") }
        XCTAssertTrue(node("library.title").waitForExistence(timeout: 60))
        XCTAssertTrue(wait { !self.node("library.busy").exists })
    }

    private func choose(_ root: String) {
        tap("account.choose")
        let row = app.buttons.matching(NSPredicate(format: "label == %@", root)).firstMatch
        XCTAssertTrue(row.waitForExistence(timeout: 30))
        XCTAssertTrue(row.isHittable)
        row.tap()
        XCTAssertTrue(wait { self.selected(root) })
        library()
    }

    func test01RootValidationAnonymousRestartAndUpdate() throws {
        let suffix = UUID().uuidString.lowercased()
        let root = "https://example.invalid/account-ui-\(suffix)/"
        tap("account.choose")
        replaceRoot("http://example.invalid/account-ui-\(suffix)/")
        tap("account.connect")
        XCTAssertTrue(node("account.error").waitForExistence(timeout: 10))
        XCTAssertTrue(node("account.root").isEnabled)
        steps.append("http_root_rejected_with_recoverable_form")
        tap("account.done"); tap("account.choose")
        replaceRoot(root)
        tap("account.connect")
        XCTAssertTrue(wait { self.selected(root) })
        XCTAssertTrue(node("account.sync.start").waitForExistence(timeout: 60))
        steps.append("anonymous_profile_created_through_actual_swiftui")
        app.terminate(); app.launch()
        XCTAssertTrue(wait { self.selected(root) })
        XCTAssertTrue(node("account.sync.start").waitForExistence(timeout: 60))
        steps.append("selected_anonymous_profile_survives_actual_process_restart")
        tap("account.choose")
        let row = app.buttons.matching(NSPredicate(format: "label == %@", root)).firstMatch
        XCTAssertTrue(row.waitForExistence(timeout: 30))
        let profile = String(row.identifier.dropFirst("account.open.".count))
        XCTAssertNotNil(UUID(uuidString: profile))
        tap("account.update." + profile)
        XCTAssertFalse(node("account.root").isEnabled)
        tap("account.connect")
        XCTAssertTrue(wait { self.selected(root) && !self.node("account.connect").exists })
        steps.append("existing_profile_authorization_form_keeps_root_identity")
        tap("account.choose"); tap("account.local")
        XCTAssertTrue(wait { self.selected("本地书库") })
        steps.append("local_library_remains_selectable_without_network")
    }

    func test02SeparateAccountLibrariesAndRestart() throws {
        tap("account.choose"); tap("account.local"); library()
        let localRows = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'library.book.'")).count
        let suffix = UUID().uuidString.lowercased()
        let first = "https://example.invalid/isolation-a-\(suffix)/"
        let second = "https://example.invalid/isolation-b-\(suffix)/"
        create(first); library()
        XCTAssertTrue(node("library.empty").waitForExistence(timeout: 30))
        tap("library.import.epub")
        let book = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'library.book.'")).firstMatch
        XCTAssertTrue(book.waitForExistence(timeout: 90))
        XCTAssertTrue(wait { !self.node("library.busy").exists })
        steps.append("first_account_imports_actual_epub_fixture")
        create(second); library()
        XCTAssertTrue(node("library.empty").waitForExistence(timeout: 30))
        steps.append("second_account_does_not_inherit_first_account_original")
        choose(first)
        XCTAssertTrue(book.waitForExistence(timeout: 60))
        steps.append("switching_back_restores_first_account_import")
        app.terminate(); app.launch(); library()
        XCTAssertTrue(selected(first)); XCTAssertTrue(book.waitForExistence(timeout: 60))
        steps.append("selected_account_and_import_survive_process_restart")
        tap("account.choose"); tap("account.local"); library()
        XCTAssertEqual(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'library.book.'")).count, localRows)
        steps.append("account_import_does_not_change_local_library_rows")
    }

    func test03NativeHTTPSBackgroundCloseAndRetry() throws {
        let root = try XCTUnwrap(ProcessInfo.processInfo.environment["EXR_ACCOUNT_UI_ROOT"])
        create(root); library()
        tap("library.import.epub")
        let book = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'library.book.'")).firstMatch
        XCTAssertTrue(book.waitForExistence(timeout: 90))
        XCTAssertTrue(wait { !self.node("library.busy").exists })
        tap("account.sync.start")
        XCTAssertTrue(wait(180) { self.text("account.sync.state") == "本轮扫描完成" })
        steps.append("actual_ui_upload_and_256_shard_https_sweep")
        tap("account.sync.start")
        XCTAssertTrue(node("account.sync.cancel").waitForExistence(timeout: 30))
#if os(iOS)
        XCUIDevice.shared.press(.home)
#else
        XCUIApplication(bundleIdentifier: "com.apple.finder").activate()
#endif
        XCTAssertTrue(wait { self.app.state != .runningForeground })
        app.activate()
        XCTAssertTrue(wait { self.text("account.sync.state") == "已关闭" })
        steps.append("actual_background_transition_closes_active_account_session")
        tap("account.sync.start")
        XCTAssertTrue(wait(180) { self.text("account.sync.state") == "本轮扫描完成" })
        XCTAssertTrue(book.exists)
        steps.append("manual_retry_after_background_reopens_and_completes_native_session")
        tap("account.choose"); tap("account.local"); library()
        XCTAssertTrue(selected("本地书库"))
        steps.append("local_library_stays_accessible_after_real_network_sync")
    }
}
