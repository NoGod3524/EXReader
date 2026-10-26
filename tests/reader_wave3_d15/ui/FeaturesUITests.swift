// SPDX-License-Identifier: MIT
import XCTest
final class FeaturesUITests: XCTestCase {
    private var app: XCUIApplication!
    override func setUpWithError() throws { continueAfterFailure = false; app = XCUIApplication() }
    override func tearDownWithError() throws {
        let tree = XCTAttachment(string: app.debugDescription); tree.name = "final-native-tree"; tree.lifetime = .keepAlways; add(tree)
        app.terminate()
    }
    private func e(_ id: String) -> XCUIElement { app.descendants(matching: .any).matching(identifier: id).firstMatch }
    private func text(_ id: String) -> String {
        guard let value = try? e(id).snapshot() else { return "" }
        return value.label.isEmpty ? (value.value as? String) ?? "" : value.label
    }
    private func wait(_ check: () -> Bool) -> Bool {
        let deadline = Date().addingTimeInterval(90)
        while Date() < deadline { if check() { return true }; RunLoop.current.run(until: Date().addingTimeInterval(0.15)) }
        return check()
    }
    private func tap(_ id: String) {
        for _ in 0..<5 {
            if e(id).exists && e(id).isHittable { break }
            if e("features.close").exists { app.scrollViews.firstMatch.swipeUp() }
        }
        XCTAssertTrue(wait { self.e(id).exists && self.e(id).isEnabled && self.e(id).isHittable }, "Unavailable \(id) \(app.debugDescription)")
        e(id).tap()
    }
    private func mark(_ name: String) {
        let a = XCTAttachment(screenshot: XCUIScreen.main.screenshot()); a.name = name; a.lifetime = .keepAlways; add(a)
    }
    private func ready() { XCTAssertTrue(wait { self.e("reader.page").exists && !self.e("reader.busy").exists }) }
    private func launch(large: Bool = false) {
        app.launchArguments = ["-EXRUITestFixtures", "1", "-EXRFreshState", "1"] + (large ? ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"] : [])
        app.launch(); XCTAssertTrue(wait { self.e("library.title").exists && !self.e("library.busy").exists })
        tap("library.import.epub"); XCTAssertTrue(wait { self.e("library.book.0").exists && !self.e("library.busy").exists })
        tap("library.book.0"); ready()
    }
    private func menu(_ id: String, title: String) {
#if os(iOS)
        let trigger = e("reader.more").buttons.firstMatch
        XCTAssertTrue(wait { trigger.exists && trigger.frame.width > 0 }); trigger.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
#else
        tap("reader.more")
#endif
        XCTAssertTrue(wait { self.e(id).exists || self.app.menuItems[title].exists || self.app.buttons[title].exists })
        if e(id).exists { tap(id) } else if app.menuItems[title].exists { app.menuItems[title].tap() } else { app.buttons[title].tap() }
    }
    private func features() { menu("reader.features", title: "阅读工具与同步状态"); XCTAssertTrue(wait { self.e("features.close").exists }) }
    private func status(_ contains: String) { XCTAssertTrue(wait { self.text("features.status").contains(contains) && !self.e("features.cancel").exists }, "Expected \(contains): \(app.debugDescription)") }
    func testBorrowedFontRollbackOriginalExportAndReadOnlySnapshot() {
        launch(); features()
        tap("features.font.fixture"); status("字体已应用"); XCTAssertEqual(text("features.font.name"), "Reader.otf"); mark("borrowed-lease-applied")
        tap("features.font.invalid"); status("字体未应用"); XCTAssertEqual(text("features.font.name"), "Reader.otf"); mark("invalid-font-old-lease-retained")
        tap("features.font.fixture"); status("字体已应用"); mark("repeat-selection-shared-library")
        tap("features.font.reset"); status("字体已应用"); XCTAssertEqual(text("features.font.name"), "内置字体")
        tap("features.original.prepare"); status("已导出原件"); let file = text("features.original.file"); XCTAssertTrue(file.hasSuffix(".epub")); mark("original-native-export")
        tap("features.original.prepare"); status("已导出原件"); XCTAssertEqual(text("features.original.file"), file)
        tap("features.original.locked"); status("真实锁定目录拒绝"); mark("locked-directory-rejected")
        tap("features.original.conflict"); status("真实目标冲突拒绝"); mark("conflict-bytes-preserved")
        tap("features.sync.idle"); status("原生只读快照"); XCTAssertTrue(text("features.sync.snapshot").contains("无网络启动")); mark("installed-sync-view-readonly")
        tap("features.close"); ready()
    }
    func testNativeAnnotationPreviewConfirmCancelAndDuplicate() {
        launch(); menu("reader.records", title: "阅读记录")
        XCTAssertTrue(wait { self.text("reading.status") == "本书的书签与标注" })
        tap("reading.add-bookmark"); XCTAssertTrue(wait { self.text("reading.status") == "已添加书签" })
        tap("reading.close"); ready(); features()
        tap("features.annotations.roundtrip"); status("预览完成，尚未写入"); XCTAssertTrue(e("features.annotations.preview").exists); mark("native-preview-no-revisions-write")
        tap("features.annotations.cancel"); XCTAssertFalse(e("features.annotations.preview").exists); mark("preview-cancel")
        tap("features.annotations.roundtrip"); status("预览完成，尚未写入")
        tap("features.annotations.confirm"); status("重复 1"); XCTAssertFalse(e("features.annotations.preview").exists); mark("confirmed-exact-duplicate")
        tap("features.close"); ready()
    }
    func testNativeHistoryAfterFoundAndLargeRotationExit() {
        launch(large: true); let original = text("reader.location")
        tap("reader.search"); tap("search.query"); e("search.query").typeText("C00P040W00"); tap("search.find")
        let hits = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'search.hit.'"))
        XCTAssertTrue(wait { hits.count == 1 }); hits.firstMatch.tap(); ready()
        XCTAssertNotEqual(text("reader.location"), original); let destination = text("reader.location")
        features(); tap("features.history.back"); XCTAssertTrue(wait { self.e("features.history.forward").isEnabled }); mark("native-history-back-after-found")
        tap("features.history.forward"); XCTAssertTrue(wait { self.e("features.history.back").isEnabled }); mark("native-history-forward-after-found")
#if os(iOS)
        XCUIDevice.shared.orientation = .landscapeLeft
        XCTAssertTrue(wait { self.e("features.close").isHittable }); mark("large-font-landscape-close")
        XCUIDevice.shared.orientation = .portrait
#endif
        tap("features.close"); ready(); XCTAssertEqual(text("reader.location"), destination)
        app.terminate(); XCTAssertTrue(app.wait(for: .notRunning, timeout: 15)); mark("native-process-exit")
    }
    func testDirectoryPickerCancellationPreservesReader() {
        launch(); let page = text("reader.page"); features(); tap("features.original.directory")
        let cancel = app.buttons["Cancel"].firstMatch, chinese = app.buttons["取消"].firstMatch
        XCTAssertTrue(wait { cancel.exists || chinese.exists })
        if cancel.exists { cancel.tap() } else { chinese.tap() }
        XCTAssertTrue(wait { self.e("features.close").exists }); mark("native-directory-picker-cancel")
        tap("features.close"); ready(); XCTAssertEqual(text("reader.page"), page)
    }
}
