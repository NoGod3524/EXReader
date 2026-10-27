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
        let scroll = e("features.scroll")
        let scrollTarget = id.hasPrefix("features.") && !["features.close", "features.refresh", "features.share"].contains(id)
        for _ in 0..<24 {
            let target = e(id)
            let inViewport = !scrollTarget || !scroll.exists || (target.exists && scroll.frame.contains(CGPoint(x: target.frame.midX, y: target.frame.midY)))
            if target.exists && inViewport && target.isHittable { break }
            if scrollTarget && scroll.exists {
                let above = target.exists && target.frame.midY < scroll.frame.midY
#if os(macOS)
                scroll.scroll(byDeltaX: 0, deltaY: above ? 140 : -140)
#else
                if above { scroll.swipeDown(velocity: .slow) }
                else { scroll.swipeUp(velocity: .slow) }
#endif
            }
        }
        XCTAssertTrue(wait {
            let target = self.e(id)
            let inViewport = !scrollTarget || !scroll.exists || (target.exists && scroll.frame.contains(CGPoint(x: target.frame.midX, y: target.frame.midY)))
            return target.exists && inViewport && target.isEnabled && target.isHittable
        }, "Unavailable \(id) \(app.debugDescription)")
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
    private func features() { menu("reader.features", title: "文件、字体与同步详情"); XCTAssertTrue(wait { self.e("features.close").exists }) }
    private func status(_ contains: String) { XCTAssertTrue(wait { self.text("features.status").contains(contains) && !self.e("features.cancel").exists }, "Expected \(contains): \(app.debugDescription)") }
    func testBorrowedFontRollbackOriginalExportAndReadOnlySnapshot() {
        launch(); features()
        tap("features.font.fixture"); status("字体已导入")
        let rows = app.buttons.matching(NSPredicate(format: "identifier MATCHES %@", "features\\.font\\.[0-9a-f]{64}"))
        XCTAssertTrue(wait { rows.count == 1 }); let fontID = rows.firstMatch.identifier
        tap(fontID); status("字体已应用")
        XCTAssertEqual(text("features.font.selected"), "当前：已选导入字体"); mark("borrowed-lease-applied")
        tap("features.font.invalid")
        XCTAssertTrue(wait { !self.e("features.cancel").exists && !self.text("features.status").isEmpty && self.text("features.status") != "处理中…" && self.text("features.status") != "字体已应用" })
        XCTAssertEqual(text("features.font.selected"), "当前：已选导入字体")
        XCTAssertEqual(rows.count, 1); mark("invalid-font-old-lease-retained")
        tap("features.font.fixture"); status("字体已导入"); XCTAssertEqual(rows.count, 1)
        tap("features.font.default"); status("字体已应用")
        XCTAssertEqual(text("features.font.selected"), "当前：内置字体")
        tap("features.original.prepare"); status("原件已导出")
        let file = text("features.export.filename"); XCTAssertTrue(file.hasSuffix(".epub")); mark("original-native-export")
        XCTAssertTrue(e("features.share").exists)
        tap("features.share")
#if os(iOS)
        XCTAssertTrue(wait { self.e("features.share.native").exists }); mark("native-share-presented")
        let native = e("features.share.native")
        let systemClose = app.buttons["header.closeButton"].firstMatch
        let close = native.buttons["Close"].firstMatch, chineseClose = native.buttons["关闭"].firstMatch
        if systemClose.waitForExistence(timeout: 15) {
            XCTAssertTrue(wait { systemClose.isHittable })
            systemClose.tap()
        } else if close.exists && close.isHittable { close.tap() }
        else if chineseClose.exists && chineseClose.isHittable { chineseClose.tap() }
        else if native.exists {
            let start = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.55))
            let end = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.95))
            start.press(forDuration: 0.1, thenDragTo: end)
        }
        if !e("features.close").isHittable {
            app.coordinate(withNormalizedOffset: CGVector(dx: 0.05, dy: 0.15)).tap()
        }
        XCTAssertTrue(wait { !self.e("features.share.native").exists && self.e("features.close").isHittable })
#else
        // NSSharingServicePicker is exposed as a popover, not an AX menu.
        // Match the exported file preview so unrelated popovers cannot satisfy this check.
        let filePrefix = String(file.prefix(16))
        let pickerVisible = {
            self.app.popovers.allElementsBoundByIndex.contains { popover in
                guard popover.frame.width > 0 && popover.frame.height > 0 else { return false }
                return popover.staticTexts.allElementsBoundByIndex.contains { item in
                    guard let snapshot = try? item.snapshot() else { return false }
                    return snapshot.label.hasPrefix(filePrefix) ||
                        ((snapshot.value as? String) ?? "").hasPrefix(filePrefix)
                } && popover.buttons.count > 0
            }
        }
        XCTAssertTrue(wait { pickerVisible() },
                      "Native sharing picker did not appear: \(app.debugDescription)")
        mark("native-sharing-picker-presented")
        app.typeKey(XCUIKeyboardKey.escape.rawValue, modifierFlags: [])
        XCTAssertTrue(wait {
            !pickerVisible() &&
            self.e("features.close").isEnabled && self.e("features.close").isHittable
        }, "Native sharing picker did not close or the feature panel remained unavailable: \(app.debugDescription)")
        mark("native-sharing-picker-dismissed")
#endif
        tap("features.original.locked"); status("原件导出未完成")
        XCTAssertEqual(text("features.export.filename"), file); mark("locked-directory-rejected")
        tap("features.original.conflict"); status("原件导出未完成")
        XCTAssertEqual(text("features.export.filename"), file); mark("conflicting-target-refused")
        tap("features.refresh"); status("详情已刷新")
        let operations = text("features.sync.operations"), phase = text("features.sync.phase")
        XCTAssertFalse(operations.isEmpty); XCTAssertFalse(phase.isEmpty)
        tap("features.refresh"); status("详情已刷新")
        XCTAssertEqual(text("features.sync.operations"), operations)
        XCTAssertEqual(text("features.sync.phase"), phase); mark("read-only-sync-refresh-no-operation")
        tap("features.close"); ready()
    }
    func testNativeAnnotationPreviewConfirmCancelAndDuplicate() {
        launch(); menu("reader.records", title: "阅读记录")
        XCTAssertTrue(wait { self.text("reading.status") == "本书的书签与标注" })
        tap("reading.add-bookmark"); XCTAssertTrue(wait { self.text("reading.status") == "已添加书签" })
        tap("reading.close"); ready(); features()
        tap("features.annotations.roundtrip"); status("预览完成，请确认后导入"); XCTAssertTrue(e("features.preview.summary").exists); mark("native-preview-no-revisions-write")
        tap("features.preview.discard"); XCTAssertFalse(e("features.preview.summary").exists); mark("preview-cancel")
        tap("features.annotations.roundtrip"); status("预览完成，请确认后导入")
        tap("features.preview.confirm"); status("标注已导入：1"); XCTAssertFalse(e("features.preview.confirm").isEnabled); mark("confirmed-exact-duplicate")
        tap("features.close"); ready()
    }
    func testNativeHistoryAfterFoundAndLargeRotationExit() {
        launch(large: true); let original = text("reader.location")
        // Chapter zero is intentionally repeated by the navigation fixture.
        // Use the independently authored unique chapter for this FOUND jump.
        tap("reader.search"); tap("search.query"); e("search.query").typeText("C01P040W00"); tap("search.find")
        let hits = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'search.hit.'"))
        XCTAssertTrue(wait { hits.count == 1 }); hits.firstMatch.tap(); ready()
        XCTAssertNotEqual(text("reader.location"), original); let destination = text("reader.location")
        features(); tap("features.history.back"); status("已精确定位历史位置"); XCTAssertTrue(e("features.history.forward").isEnabled); mark("native-history-back-after-found")
        tap("features.history.forward"); status("已精确定位历史位置")
        XCTAssertTrue(wait { self.text("reader.location") == destination && self.e("features.history.back").isEnabled && !self.e("features.cancel").exists })
        mark("native-history-forward-after-found")
#if os(iOS)
        XCUIDevice.shared.orientation = .landscapeLeft
        XCTAssertTrue(wait { self.e("features.close").isHittable }); mark("large-font-landscape-close")
        XCUIDevice.shared.orientation = .portrait
#endif
        tap("features.close"); ready(); XCTAssertEqual(text("reader.location"), destination)
        app.terminate(); XCTAssertTrue(app.wait(for: .notRunning, timeout: 15)); mark("native-process-exit")
    }
    func testTypedNullAndConcurrentHeadsRequirePreviewConfirmation() {
        launch(); tap("reader.back")
        XCTAssertTrue(wait { self.e("library.title").exists })
        tap("library.import.pdf")
        let pdf = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@ AND label CONTAINS %@", "library.book.", "Sample.pdf")).firstMatch
        XCTAssertTrue(wait { pdf.exists && !self.e("library.busy").exists }); pdf.tap(); ready()
        let position = text("reader.location")
        features(); tap("features.annotations.null"); status("预览完成，请确认后导入")
        XCTAssertTrue(text("features.preview.null").contains("NULL 选择器：1"))
        XCTAssertTrue(text("features.preview.unresolved").contains("未能定位：0")); mark("typed-null-preview-preserved")
        tap("features.preview.confirm"); status("标注已导入")
        XCTAssertFalse(e("features.preview.confirm").isEnabled)
        tap("features.close"); ready(); XCTAssertEqual(text("reader.location"), position)
        features(); tap("features.annotations.conflict"); status("预览完成，请确认后导入")
        XCTAssertTrue(text("features.preview.conflicts").contains("确认后读取")); mark("concurrent-heads-await-confirmation")
        tap("features.preview.confirm"); status("标注已导入")
        XCTAssertTrue(text("features.preview.conflicts").contains("冲突：1")); mark("concurrent-heads-retained")
        tap("features.close"); ready(); XCTAssertEqual(text("reader.location"), position)
    }
    func testDirectoryPickerCancellationPreservesReader() {
        launch(); let page = text("reader.page"); features(); tap("features.original.export")
        let cancel = app.buttons["Cancel"].firstMatch, chinese = app.buttons["取消"].firstMatch
        XCTAssertTrue(wait { cancel.exists || chinese.exists })
        if cancel.exists { cancel.tap() } else { chinese.tap() }
        XCTAssertTrue(wait { self.e("features.close").exists }); mark("native-directory-picker-cancel")
        tap("features.close"); ready(); XCTAssertEqual(text("reader.page"), page)
    }
}
