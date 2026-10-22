// SPDX-License-Identifier: MIT
import XCTest
#if os(macOS)
import AppKit
#endif

final class EXReaderHostUITests: XCTestCase {
    private var app: XCUIApplication!

    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication()
    }

    override func tearDownWithError() throws {
#if os(iOS)
        XCUIDevice.shared.orientation = .portrait
#endif
        if app != nil { app.terminate() }
    }

    // MARK: - Helpers

    private func launch(fresh: Bool = false, extra: [String] = []) {
        var args = ["-EXRUITestFixtures", "1"]
        if fresh { args += ["-EXRFreshState", "1"] }
        args += extra
        app.launchArguments = args
        app.launch()
    }

    private func element(_ identifier: String) -> XCUIElement {
        app.descendants(matching: .any).matching(identifier: identifier).firstMatch
    }

    @discardableResult
    private func waitElement(_ identifier: String, _ timeout: TimeInterval = 30,
                             file: StaticString = #filePath, line: UInt = #line) -> XCUIElement {
        let target = element(identifier)
        XCTAssertTrue(target.waitForExistence(timeout: timeout),
                      "missing \(identifier)\n\(app.debugDescription)", file: file, line: line)
        return target
    }

    private func text(_ identifier: String) -> String {
        let target = element(identifier)
        let label = target.label
        if !label.isEmpty { return label }
        return (target.value as? String) ?? ""
    }

    private func waitUntil(_ timeout: TimeInterval, _ condition: () -> Bool) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if condition() { return true }
            RunLoop.current.run(until: Date().addingTimeInterval(0.2))
        }
        return condition()
    }

    private func waitLabel(_ identifier: String, contains text: String,
                           _ timeout: TimeInterval = 30) -> Bool {
        _ = element(identifier).waitForExistence(timeout: min(timeout, 10))
        return waitUntil(timeout) { self.text(identifier).contains(text) }
    }

    private func waitLabelAny(_ identifier: String, _ texts: [String],
                              _ timeout: TimeInterval = 30) -> Bool {
        _ = element(identifier).waitForExistence(timeout: min(timeout, 10))
        return waitUntil(timeout) { texts.contains(where: { self.text(identifier).contains($0) }) }
    }

    private func waitLabelFilled(_ identifier: String, excluding: [String],
                                 _ timeout: TimeInterval = 15) -> Bool {
        _ = element(identifier).waitForExistence(timeout: min(timeout, 10))
        return waitUntil(timeout) {
            let value = text(identifier)
            return !value.isEmpty && !excluding.contains(value)
        }
    }

    private func step(_ name: String, _ body: () throws -> Void) rethrows {
        try XCTContext.runActivity(named: name) { _ in try body() }
    }

    private func attach(_ name: String) {
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }

    private func attachTree(_ name: String) {
        let attachment = XCTAttachment(string: app.debugDescription)
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }

    private func bookRow(_ title: String) -> XCUIElement {
        app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@ AND label CONTAINS %@",
                                          "library.book.", title)).firstMatch
    }

    private func bookRows() -> [XCUIElement] {
        let query = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "library.book."))
        return (0..<query.count).map { query.element(boundBy: $0) }
    }

    private func openLibrary() {
        if element("library.title").waitForExistence(timeout: 2) { return }
        if element("reader.back").waitForExistence(timeout: 5) {
            element("reader.back").tap()
        }
        _ = waitElement("library.title", 20)
    }

    private func ensureReader(_ title: String) throws {
        if element("reader.page").waitForExistence(timeout: 3) {
            if text("reader.title").contains(title) { return }
            if element("reader.back").exists {
                element("reader.back").tap()
                _ = element("library.title").waitForExistence(timeout: 20)
            }
        }
        _ = waitElement("library.title", 60)
        var row = bookRow(title)
        if !row.exists {
            waitElement("library.import.epub").tap()
            XCTAssertTrue(waitLabelAny("library.status", ["已导入", "已存在"], 90))
            row = bookRow(title)
        }
        XCTAssertTrue(row.waitForExistence(timeout: 30), "book \(title) missing")
        row.tap()
        _ = waitElement("reader.page", 90)
    }

    private func selectionTextView() -> XCUIElement {
        let identifierMatch = app.textViews["selection.text"]
        if identifierMatch.waitForExistence(timeout: 5) { return identifierMatch }
        return app.textViews.firstMatch
    }

    private func selectWord() {
        let view = selectionTextView()
        view.tap()
#if os(iOS)
        view.doubleTap()
#else
        view.doubleClick()
#endif
        if !waitLabelFilled("selection.quote", excluding: ["尚未选择文字"], 5) {
            view.press(forDuration: 1.2)
        }
    }

    private func clearNotes() {
        guard element("reader.notes").exists else { return }
        element("reader.notes").tap()
        _ = waitElement("notes.title", 20)
        var guardCount = 0
        while element("notes.delete.0").exists && guardCount < 20 {
            element("notes.delete.0").tap()
            guardCount += 1
            _ = element("notes.empty").waitForExistence(timeout: 5)
        }
        element("notes.close").tap()
    }

#if os(macOS)
    private func resizeWindow(dx: CGFloat, dy: CGFloat) {
        let window = app.windows.firstMatch
        guard window.exists else { return }
        let corner = window.coordinate(withNormalizedOffset: CGVector(dx: 0.985, dy: 0.985))
        corner.press(forDuration: 0.2, thenDragTo: corner.withOffset(CGVector(dx: dx, dy: dy)))
    }
#endif

    // MARK: - Tests

    func test01ImportDeduplicateAndErrors() throws {
        try step("step01_launch_fresh_state") {
            launch(fresh: true)
            _ = waitElement("library.title", 60)
            XCTAssertTrue(waitElement("library.empty", 30).exists)
            attach("01-empty-library")
        }
        try step("step02_import_epub_fixture") {
            waitElement("library.import.epub").tap()
            XCTAssertTrue(waitLabelAny("library.status", ["已导入"], 90))
            XCTAssertTrue(bookRow("Sample.epub").waitForExistence(timeout: 20))
            attach("02-imported-epub")
        }
        try step("step03_duplicate_import_reuses_row") {
            waitElement("library.import.epub.duplicate").tap()
            XCTAssertTrue(waitLabelAny("library.status", ["已存在"], 60))
            XCTAssertEqual(bookRows().count, 1, "duplicate import must reuse the stored record")
        }
        try step("step04_import_pdf_fixture") {
            waitElement("library.import.pdf").tap()
            XCTAssertTrue(waitLabelAny("library.status", ["已导入"], 90))
            XCTAssertEqual(bookRows().count, 2)
            XCTAssertTrue(bookRow("Sample.pdf").exists)
            attach("03-library-two-books")
        }
        try step("step05_broken_import_error_is_recoverable") {
            waitElement("library.import.broken").tap()
            XCTAssertTrue(waitLabelAny("library.status", ["操作失败"], 60))
            XCTAssertTrue(waitElement("library.error", 10).exists)
            attach("04-broken-import-error")
        }
        try step("step06_reopen_epub_after_error") {
            waitElement("library.import.epub").tap()
            XCTAssertTrue(waitLabelAny("library.status", ["已存在", "已导入"], 60))
            let row = bookRow("Sample.epub")
            XCTAssertTrue(row.waitForExistence(timeout: 20))
            row.tap()
            _ = waitElement("reader.page", 90)
        }
        try step("step07_element_tree_import") {
            attachTree("05-import-tree")
        }
    }

    func test02PagingTypographyAndLayout() throws {
        try step("step08_launch_and_open_reader") {
            launch()
            try ensureReader("Sample.epub")
            attach("06-reader-open")
        }
        try step("step09_first_page") {
            waitElement("reader.first").tap()
            XCTAssertTrue(waitLabel("reader.location", contains: "第 1 页", 30))
            XCTAssertTrue(waitLabel("reader.font.value", contains: "28", 10))
        }
        try step("step10_next_page_progress") {
            waitElement("reader.next").tap()
            XCTAssertTrue(waitLabel("reader.location", contains: "第 2 页", 30))
            XCTAssertTrue(waitLabel("reader.progress", contains: "%", 10))
        }
        try step("step11_next_page_again") {
            waitElement("reader.next").tap()
            XCTAssertTrue(waitLabel("reader.location", contains: "第 3 页", 30))
        }
        try step("step12_previous_page") {
            waitElement("reader.previous").tap()
            XCTAssertTrue(waitLabel("reader.location", contains: "第 2 页", 30))
        }
        try step("step13_font_increase_repaginates") {
            waitElement("reader.font.increase").tap()
            XCTAssertTrue(waitLabel("reader.font.value", contains: "字号 30", 30))
        }
        try step("step14_font_decrease_restores_size") {
            waitElement("reader.font.decrease").tap()
            XCTAssertTrue(waitLabel("reader.font.value", contains: "字号 28", 30))
        }
        var before = CGRect.zero
        try step("step15_rotate_or_resize_viewport") {
            before = element("reader.page").frame
#if os(iOS)
            XCUIDevice.shared.orientation = .landscapeLeft
#else
            resizeWindow(dx: -220, dy: -160)
#endif
            Thread.sleep(forTimeInterval: 1.5)
            XCTAssertTrue(waitLabel("reader.status", contains: "就绪", 40))
            attach("07-layout-resized")
        }
        try step("step16_layout_fits_new_size") {
            let page = element("reader.page").frame
            let window = app.windows.firstMatch.frame
            XCTAssertGreaterThan(page.width, 0)
            XCTAssertGreaterThan(page.height, 0)
            XCTAssertLessThanOrEqual(page.maxX, window.maxX + 2)
            XCTAssertLessThanOrEqual(page.maxY, window.maxY + 2)
            XCTAssertGreaterThan(abs(page.width - before.width) + abs(page.height - before.height), 10)
        }
        try step("step17_restore_original_orientation") {
#if os(iOS)
            XCUIDevice.shared.orientation = .portrait
#else
            resizeWindow(dx: 220, dy: 160)
#endif
            Thread.sleep(forTimeInterval: 1.5)
            XCTAssertTrue(waitLabel("reader.status", contains: "就绪", 40))
            attach("08-layout-restored")
        }
        try step("step18_element_tree_reader") {
            attachTree("09-reader-tree")
        }
    }

    func test03SelectionCopyAnnotation() throws {
        try step("step19_open_selection_sheet") {
            launch()
            try ensureReader("Sample.epub")
            clearNotes()
            waitElement("reader.select").tap()
            XCTAssertTrue(waitElement("selection.title", 20).exists)
            attach("10-selection-sheet")
        }
        try step("step20_keyboard_select_text") {
            selectWord()
            XCTAssertTrue(waitLabelFilled("selection.quote", excluding: ["尚未选择文字"], 20))
        }
        try step("step21_copy_selection") {
            waitElement("selection.copy").tap()
            waitElement("selection.verifyPaste").tap()
            XCTAssertTrue(waitLabelFilled("selection.clipboard", excluding: ["剪贴板为空"], 20))
            let quote = text("selection.quote")
            let clipboard = text("selection.clipboard")
            XCTAssertTrue(clipboard.contains(quote) || quote.contains(clipboard),
                          "clipboard \(clipboard) does not contain quote \(quote)")
            attach("11-selection-copied")
        }
        try step("step22_create_annotation") {
            waitElement("selection.annotate").tap()
            XCTAssertTrue(waitLabel("reader.notes", contains: "标注 1", 40))
            XCTAssertTrue(waitElement("reader.page", 20).exists)
        }
        try step("step23_annotation_list_navigation") {
            waitElement("reader.notes").tap()
            XCTAssertTrue(waitElement("notes.quote.0", 30).exists)
            let quote = text("notes.quote.0")
            XCTAssertFalse(quote.isEmpty)
            attach("12-annotation-list")
        }
        try step("step24_edit_annotation") {
            waitElement("notes.edit.0").tap()
            let field = waitElement("notes.editor", 20)
            field.tap()
            field.typeText("edited-note")
            waitElement("notes.save").tap()
            XCTAssertTrue(waitLabel("notes.comment.0", contains: "edited-note", 40))
        }
        try step("step25_jump_to_annotation") {
            waitElement("notes.jump.0").tap()
            XCTAssertTrue(waitLabel("reader.location", contains: "第", 40))
            attach("13-annotation-jump")
        }
        try step("step26_delete_annotation") {
            waitElement("reader.notes").tap()
            _ = waitElement("notes.title", 20)
            var guardCount = 0
            while element("notes.delete.0").exists && guardCount < 20 {
                element("notes.delete.0").tap()
                guardCount += 1
                _ = element("notes.empty").waitForExistence(timeout: 5)
            }
            XCTAssertTrue(waitElement("notes.empty", 20).exists)
            waitElement("notes.close").tap()
            attach("14-annotation-deleted")
        }
    }

    func test04LifecycleAndPersistence() throws {
        var location = ""
        try step("step27_open_and_navigate") {
            launch()
            try ensureReader("Sample.epub")
            clearNotes()
            waitElement("reader.first").tap()
            _ = waitLabel("reader.location", contains: "第 1 页", 30)
            waitElement("reader.next").tap()
            XCTAssertTrue(waitLabel("reader.location", contains: "第 2 页", 30))
            location = text("reader.location")
        }
        var hash = ""
        try step("step28_create_note_and_read_state") {
            waitElement("reader.select").tap()
            _ = waitElement("selection.title", 20)
            selectWord()
            XCTAssertTrue(waitLabelFilled("selection.quote", excluding: ["尚未选择文字"], 20))
            waitElement("selection.annotate").tap()
            XCTAssertTrue(waitLabel("reader.notes", contains: "标注 1", 40))
            Thread.sleep(forTimeInterval: 0.5)
            hash = text("reader.state")
            XCTAssertTrue(hash.contains("#"))
        }
        try step("step29_background_and_foreground") {
#if os(iOS)
            XCUIDevice.shared.press(.home)
            Thread.sleep(forTimeInterval: 1.5)
            app.activate()
#else
            NSRunningApplication.runningApplications(withBundleIdentifier: "com.apple.finder").first?.activate(options: [])
            Thread.sleep(forTimeInterval: 1.5)
            app.activate()
#endif
            _ = waitElement("reader.page", 40)
            XCTAssertEqual(text("reader.location"), location)
            attach("15-after-background")
        }
        try step("step30_relaunch_restores_position_and_state") {
            app.terminate()
            launch()
            _ = waitElement("reader.page", 90)
            XCTAssertEqual(text("reader.location"), location)
            XCTAssertEqual(text("reader.state"), hash)
            attach("16-after-relaunch")
        }
        try step("step31_notes_survive_relaunch") {
            waitElement("reader.notes").tap()
            XCTAssertTrue(waitElement("notes.quote.0", 30).exists)
            waitElement("notes.close").tap()
            attach("17-notes-after-relaunch")
        }
        try step("step32_view_rebuild_via_library") {
            waitElement("reader.back").tap()
            _ = waitElement("library.title", 30)
            let row = bookRow("Sample.epub")
            XCTAssertTrue(row.waitForExistence(timeout: 20))
            row.tap()
            _ = waitElement("reader.page", 90)
            XCTAssertEqual(text("reader.location"), location)
        }
    }

    func test05CancellationAndRecovery() throws {
        try step("step33_launch_with_deterministic_slow_import") {
            launch(extra: ["-EXRHostDelayMs", "2500"])
            openLibrary()
            attach("18-library-slow-mode")
        }
        try step("step34_cancel_in_flight_import") {
            waitElement("library.import.large").tap()
            XCTAssertTrue(waitElement("library.cancel", 4).exists)
            element("library.cancel").tap()
            XCTAssertTrue(waitLabel("library.status", contains: "已取消", 40))
            attach("19-import-cancelled")
        }
        try step("step35_recover_with_valid_import") {
            waitElement("library.import.epub").tap()
            XCTAssertTrue(waitLabelAny("library.status", ["已导入", "已存在"], 90))
            let row = bookRow("Sample.epub")
            XCTAssertTrue(row.waitForExistence(timeout: 20))
            row.tap()
            _ = waitElement("reader.page", 90)
            attach("20-after-cancel-recovery")
        }
        try step("step36_reader_remains_usable") {
            waitElement("reader.next").tap()
            XCTAssertTrue(waitLabel("reader.location", contains: "第", 40))
        }
        try step("step37_state_tree_after_cancel") {
            attachTree("21-cancel-tree")
        }
    }

    func test06FixedPagePdfAndAnchor() throws {
        var location = ""
        try step("step38_open_pdf_fixed_layout") {
            launch()
            openLibrary()
            if !bookRow("Sample.pdf").exists {
                waitElement("library.import.pdf").tap()
                XCTAssertTrue(waitLabelAny("library.status", ["已导入", "已存在"], 90))
            }
            let row = bookRow("Sample.pdf")
            XCTAssertTrue(row.waitForExistence(timeout: 30))
            row.tap()
            _ = waitElement("reader.page", 90)
            XCTAssertTrue(waitLabel("reader.location", contains: "/", 30))
            attach("22-pdf-first-page")
        }
        try step("step39_fixed_page_navigation") {
            waitElement("reader.first").tap()
            _ = waitLabel("reader.location", contains: "第 1 /", 30)
            waitElement("reader.next").tap()
            XCTAssertTrue(waitLabel("reader.location", contains: "第 2 /", 30))
            location = text("reader.location")
        }
        try step("step40_fixed_annotation") {
            clearNotes()
            waitElement("reader.select").tap()
            _ = waitElement("selection.title", 20)
            selectWord()
            XCTAssertTrue(waitLabelFilled("selection.quote", excluding: ["尚未选择文字"], 20))
            waitElement("selection.annotate").tap()
            XCTAssertTrue(waitLabel("reader.status", contains: "已保存标注", 40))
            waitElement("reader.notes").tap()
            XCTAssertTrue(waitElement("notes.quote.0", 30).exists)
            attach("23-pdf-annotation")
        }
        try step("step41_fixed_annotation_jump") {
            waitElement("notes.jump.0").tap()
            XCTAssertTrue(waitLabel("reader.location", contains: "第 2 /", 30))
        }
        try step("step42_fixed_progress_survives_relaunch") {
            app.terminate()
            launch()
            _ = waitElement("reader.page", 90)
            XCTAssertEqual(text("reader.location"), location)
            attach("24-pdf-after-relaunch")
        }
    }

    func test07AccessibilityAndDynamicType() throws {
        try step("step43_identifiers_and_labels") {
            launch()
            try ensureReader("Sample.epub")
            for identifier in ["reader.page", "reader.location", "reader.progress",
                               "reader.next", "reader.previous", "reader.select",
                               "reader.notes", "reader.state"] {
                _ = waitElement(identifier, 30)
                XCTAssertFalse(text(identifier).isEmpty, "empty accessible text for \(identifier)")
            }
            attach("25-accessibility-reader")
        }
        try step("step44_reading_order") {
            let title = element("reader.title").frame
            let page = element("reader.page").frame
            let controls = element("reader.next").frame
            XCTAssertLessThan(title.minY, page.minY)
            XCTAssertLessThan(page.minY, controls.minY)
        }
        try step("step45_element_tree") {
            attachTree("26-accessibility-tree")
        }
        try step("step46_dynamic_type_launch") {
            app.terminate()
            launch(extra: ["-UIPreferredContentSizeCategoryName",
                           "UICTContentSizeCategoryAccessibilityExtraExtraExtraLarge"])
            _ = waitElement("reader.page", 90)
            XCTAssertTrue(waitElement("reader.next").exists)
            XCTAssertTrue(waitElement("reader.location").exists)
            attach("27-dynamic-type")
        }
    }
}