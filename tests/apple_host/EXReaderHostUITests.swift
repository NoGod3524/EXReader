// SPDX-License-Identifier: MIT
import XCTest
#if os(macOS)
import AppKit
#endif

final class EXReaderHostUITests: XCTestCase {
    private var app: XCUIApplication!
    private static var recordedSteps: [String] = []

    override func setUpWithError() throws {
        continueAfterFailure = false
        Self.recordedSteps = []
        app = XCUIApplication()
    }

    override func tearDownWithError() throws {
        if !Self.recordedSteps.isEmpty,
           let data = try? JSONSerialization.data(withJSONObject: ["test": name, "steps": Self.recordedSteps],
                                                   options: [.prettyPrinted, .sortedKeys]),
           let text = String(data: data, encoding: .utf8) {
            let attachment = XCTAttachment(string: text)
            attachment.name = "steps-\(name).json"
            attachment.lifetime = .keepAlways
            add(attachment)
        }
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
        XCTAssertTrue(waitStableState(90) {
            guard let state = self.screenSnapshot() else { return nil }
            return self.readerIdleIdentity(state) ?? self.libraryIdleIdentity(state)
        }, "host did not finish startup and saved-book restoration")
    }

    private struct ScreenSnapshot {
        let elements: [String: XCUIElementSnapshot]
        let bookCount: Int
        let frame: CGRect

        init(_ root: XCUIElementSnapshot) {
            var indexed: [String: XCUIElementSnapshot] = [:]
            var books = 0
            var windowFrame: CGRect?
            func visit(_ node: XCUIElementSnapshot) {
                if windowFrame == nil && node.elementType == .window && !node.frame.isEmpty { windowFrame = node.frame }
                if !node.identifier.isEmpty && indexed[node.identifier] == nil { indexed[node.identifier] = node }
                if node.elementType == .button && node.identifier.hasPrefix("library.book.") { books += 1 }
                for child in node.children { visit(child) }
            }
            visit(root)
            elements = indexed
            bookCount = books
            frame = windowFrame ?? root.frame
        }

        func text(_ identifier: String) -> String? {
            guard let node = elements[identifier] else { return nil }
            return node.label.isEmpty ? (node.value as? String) ?? "" : node.label
        }
    }

    private func screenSnapshot() -> ScreenSnapshot? {
        guard let snapshot = try? app.snapshot() else { return nil }
        return ScreenSnapshot(snapshot)
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
        screenSnapshot()?.text(identifier) ?? ""
    }

    private func waitUntil(_ timeout: TimeInterval, _ condition: () -> Bool) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if condition() { return true }
            RunLoop.current.run(until: Date().addingTimeInterval(0.2))
        }
        return condition()
    }

    // The accepted frame and controls must remain idle through the viewport
    // debounce, rather than treating one transient enabled AX snapshot as ready.
    private func waitStableState(_ timeout: TimeInterval, _ state: () -> String?) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        var previous: String?, stableSince: Date?
        while Date() < deadline {
            let current = state()
            let observed = Date()
            if let current {
                if previous == current {
                    if let stableSince, observed.timeIntervalSince(stableSince) >= 0.6 { return true }
                } else {
                    previous = current
                    stableSince = observed
                }
            } else {
                previous = nil
                stableSince = nil
            }
            RunLoop.current.run(until: Date().addingTimeInterval(0.2))
        }
        return false
    }

    private func readerIdleIdentity(_ state: ScreenSnapshot) -> String? {
        guard let page = state.elements["reader.page"], state.elements["reader.busy"] == nil,
              state.elements["reader.next"]?.isEnabled == true,
              let title = state.text("reader.title"), let location = state.text("reader.location"),
              let font = state.text("reader.font.value"), let hash = state.text("reader.state") else { return nil }
        return "reader|" + [title, location, font, hash, String(describing: page.frame)].joined(separator: "|")
    }

    private func libraryIdleIdentity(_ state: ScreenSnapshot) -> String? {
        guard state.elements["library.title"] != nil, state.elements["library.busy"] == nil,
              let importButton = state.elements["library.import.epub"], importButton.isEnabled,
              let status = state.text("library.status") else { return nil }
        return "library|\(state.bookCount)|\(status)|\(state.frame)|\(importButton.frame)"
    }

    @discardableResult
    private func tapLibraryImport(_ identifier: String, expecting statuses: [String]? = nil,
                                  timeout: TimeInterval = 90, file: StaticString = #filePath, line: UInt = #line) -> Date {
        let deadline = Date().addingTimeInterval(timeout)
        let ready = waitStableState(max(0, deadline.timeIntervalSinceNow)) {
            let buttons = self.app.buttons.matching(identifier: identifier)
            guard self.app.state == .runningForeground, buttons.count == 1,
                  let state = self.screenSnapshot(), let idle = self.libraryIdleIdentity(state),
                  let node = try? buttons.element(boundBy: 0).snapshot(), node.elementType == .button, node.isEnabled,
                  !node.frame.isEmpty, state.frame.contains(node.frame), buttons.element(boundBy: 0).isHittable else { return nil }
            return "\(idle)|\(node.frame)"
        }
        reportImportAction(identifier, phase: "before-single-press")
        let inBudget = Date() < deadline
        XCTAssertTrue(ready && inBudget, "import button must be unique, enabled, hittable and stable", file: file, line: line)
        guard ready && inBudget else { return deadline }
        app.buttons.matching(identifier: identifier).element(boundBy: 0).press(forDuration: 0.1)
        if let statuses {
            reportImportAction(identifier, phase: "after-single-press")
            let matched = waitUntil(max(0, deadline.timeIntervalSinceNow)) {
                let status = self.text("library.status")
                return Date() < deadline && statuses.contains(where: { status.contains($0) })
            }
            if !matched { reportWaitFailure("library.status", expected: statuses.joined(separator: "|")) }
            XCTAssertTrue(matched, "import result must arrive within its original budget", file: file, line: line)
        }
        return deadline
    }

    private func reportImportAction(_ identifier: String, phase: String) {
        let state = screenSnapshot()
        let query = app.buttons.matching(identifier: identifier)
        let controls: [[String: Any]] = (0..<min(query.count, 4)).map {
            let button = query.element(boundBy: $0)
            return ["type": String(describing: button.elementType), "enabled": button.isEnabled,
                    "hittable": button.isHittable, "frame": String(describing: button.frame)]
        }
        let record: [String: Any] = ["phase": phase, "identifier": identifier, "input": "single-press", "duration_seconds": 0.1,
            "app_state": String(describing: app.state),
            "any_matches": app.descendants(matching: .any).matching(identifier: identifier).count,
            "button_matches": query.count, "controls": controls,
            "frame": String(describing: state?.frame), "status": state?.text("library.status") ?? "<absent>",
            "busy": state?.elements["library.busy"] != nil,
            "trace": (state?.elements["library.title"]?.value as? String) ?? "<absent>"]
        if let data = try? JSONSerialization.data(withJSONObject: record, options: [.sortedKeys]),
           let value = String(data: data, encoding: .utf8) { print("EXR_UI_IMPORT_ACTION " + value) }
    }

    private func waitLabel(_ identifier: String, contains text: String,
                           _ timeout: TimeInterval = 30) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        _ = element(identifier).waitForExistence(timeout: min(timeout, 10))
        let matched: Bool
        if identifier == "reader.status" && text == "就绪" {
            // A completed open may hand a pending viewport directly to its next
            // worker while retaining the previous status text. Only one stable,
            // current AX snapshot with an accepted frame and enabled controls is ready.
            matched = waitStableState(max(0, deadline.timeIntervalSinceNow)) {
                guard let state = self.screenSnapshot(), state.text(identifier)?.contains(text) == true else { return nil }
                return self.readerIdleIdentity(state)
            }
        } else {
            matched = waitUntil(timeout) { self.text(identifier).contains(text) }
        }
        if !matched { reportWaitFailure(identifier, expected: text) }
        return matched
    }

    private func waitLabelAny(_ identifier: String, _ texts: [String],
                              _ timeout: TimeInterval = 30) -> Bool {
        _ = element(identifier).waitForExistence(timeout: min(timeout, 10))
        let matched = waitUntil(timeout) { texts.contains(where: { self.text(identifier).contains($0) }) }
        if !matched { reportWaitFailure(identifier, expected: texts.joined(separator: "|")) }
        return matched
    }

    private func waitLabelFilled(_ identifier: String, excluding: [String],
                                 _ timeout: TimeInterval = 15) -> Bool {
        _ = element(identifier).waitForExistence(timeout: min(timeout, 10))
        let matched = waitUntil(timeout) {
            let value = text(identifier)
            return !value.isEmpty && !excluding.contains(value)
        }
        if !matched { reportWaitFailure(identifier, expected: "nonempty, excluding " + excluding.joined(separator: "|")) }
        return matched
    }

    private func reportWaitFailure(_ identifier: String, expected: String) {
        if identifier == "library.status" { reportImportAction("library.import.epub", phase: "result-wait-failed") }
        guard let state = screenSnapshot() else { return }
        var observed: [String: Any] = ["identifier": identifier, "expected": expected,
            "book_count": state.bookCount]
        for key in [identifier, "library.status", "library.error", "library.busy",
                    "reader.status", "reader.busy", "reader.location", "reader.state", "selection.hint"] {
            observed[key] = String((state.text(key) ?? "<absent>").prefix(400))
        }
        for key in ["library.import.epub", "selection.text", "selection.copy"] {
            if let node = state.elements[key] {
                observed[key] = ["enabled": node.isEnabled, "frame": String(describing: node.frame)]
            }
        }
        if let data = try? JSONSerialization.data(withJSONObject: observed, options: [.sortedKeys]),
           let json = String(data: data, encoding: .utf8) {
            print("EXR_UI_WAIT_FAILED " + json)
        }
    }

    private func waitReaderIdle(_ timeout: TimeInterval = 45) -> Bool {
        waitStableState(timeout) { self.screenSnapshot().flatMap { self.readerIdleIdentity($0) } }
    }

    private func step(_ name: String, _ body: () throws -> Void) rethrows {
        Self.recordedSteps.append(name)
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
        if !element("library.title").exists && element("reader.back").waitForExistence(timeout: 5) {
            element("reader.back").tap()
        }
        _ = waitElement("library.title", 20)
        XCTAssertTrue(waitStableState(45) { self.screenSnapshot().flatMap { self.libraryIdleIdentity($0) } })
    }

    private func ensureReader(_ title: String) throws {
        if element("reader.page").waitForExistence(timeout: 3) {
            if text("reader.title").contains(title) {
                XCTAssertTrue(waitReaderIdle(90))
                return
            }
            if element("reader.back").exists {
                element("reader.back").tap()
                _ = element("library.title").waitForExistence(timeout: 20)
            }
        }
        _ = waitElement("library.title", 60)
        var row = bookRow(title)
        if !row.exists {
            tapLibraryImport("library.import.epub", expecting: ["已导入", "已存在"])
            row = bookRow(title)
        }
        XCTAssertTrue(row.waitForExistence(timeout: 30), "book \(title) missing")
        row.tap()
        _ = waitElement("reader.page", 90)
        XCTAssertTrue(waitReaderIdle(90))
    }

    private func selectionTextView() -> XCUIElement {
        let identifierMatch = app.textViews["selection.text"]
        if identifierMatch.waitForExistence(timeout: 5) { return identifierMatch }
        return app.textViews.firstMatch
    }

    private func selectWord() {
        XCTAssertTrue(waitUntil(10) { self.screenSnapshot()?.elements["selection.copy"]?.isEnabled == true },
                      "selection sheet must still own a stable frame before native word selection")
        let view = selectionTextView()
#if os(iOS)
        // Hit the fixed fixture's first visible text line. The centre of the
        // larger iPad text view can be blank space below the native text.
        let word = view.coordinate(withNormalizedOffset: .zero)
            .withOffset(CGVector(dx: 30, dy: 22))
        word.tap()
        word.doubleTap()
#else
        view.tap()
        view.doubleClick()
#endif
        if !waitLabelFilled("selection.quote", excluding: ["尚未选择文字"], 5) {
#if os(iOS)
            word.press(forDuration: 1.2)
#else
            view.press(forDuration: 1.2)
#endif
        }
#if os(iOS)
        // Native word selection can leave UIKit's edit menu above the host.
        // Dismiss it with a separate outside tap before activating a host button;
        // the selected quote must survive through the normal selection owner.
        if waitLabelFilled("selection.quote", excluding: ["尚未选择文字"], 10) {
            let selected = text("selection.quote")
            waitElement("selection.quote").tap()
            XCTAssertTrue(waitUntil(10) {
                self.text("selection.quote") == selected && self.element("selection.annotate").isEnabled
            })
        }
#endif
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
        XCTAssertTrue(waitReaderIdle())
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
            let deadline = tapLibraryImport("library.import.epub", expecting: ["已导入"])
            XCTAssertTrue(bookRow("Sample.epub").waitForExistence(timeout: min(20, max(0, deadline.timeIntervalSinceNow))))
            attach("02-imported-epub")
        }
        try step("step03_duplicate_import_reuses_row") {
            tapLibraryImport("library.import.epub.duplicate", expecting: ["已存在"], timeout: 60)
            XCTAssertEqual(bookRows().count, 1, "duplicate import must reuse the stored record")
        }
        try step("step04_import_pdf_fixture") {
            tapLibraryImport("library.import.pdf", expecting: ["已导入"])
            XCTAssertEqual(bookRows().count, 2)
            XCTAssertTrue(bookRow("Sample.pdf").exists)
            attach("03-library-two-books")
        }
        try step("step05_broken_import_error_is_recoverable") {
            tapLibraryImport("library.import.broken", expecting: ["操作失败"], timeout: 60)
            XCTAssertTrue(waitElement("library.error", 10).exists)
            attach("04-broken-import-error")
        }
        try step("step06_reopen_epub_after_error") {
            tapLibraryImport("library.import.epub", expecting: ["已存在", "已导入"], timeout: 60)
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
            XCTAssertTrue(waitUntil(15) { self.text("reader.state") == hash })
            attach("15-after-background")
        }
        try step("step30_relaunch_restores_position_and_state") {
            app.terminate()
            launch()
            _ = waitElement("reader.page", 90)
            XCTAssertTrue(text("reader.location").contains("第"))
            XCTAssertTrue(waitUntil(15) { self.text("reader.state") == hash })
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
            XCTAssertTrue(waitUntil(15) { self.text("reader.state") == hash })
        }
    }

    func test05CancellationAndRecovery() throws {
        try step("step33_launch_with_deterministic_slow_import") {
            launch(extra: ["-EXRHostDelayMs", "2500"])
            openLibrary()
            attach("18-library-slow-mode")
        }
        try step("step34_cancel_in_flight_import") {
            tapLibraryImport("library.import.large", timeout: 30)
            XCTAssertTrue(waitElement("library.cancel", 4).exists)
            element("library.cancel").tap()
            XCTAssertTrue(waitLabel("library.status", contains: "已取消", 40))
            attach("19-import-cancelled")
        }
        try step("step35_recover_with_valid_import") {
            tapLibraryImport("library.import.epub", expecting: ["已导入", "已存在"])
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
                tapLibraryImport("library.import.pdf", expecting: ["已导入", "已存在"])
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

    func test08BusyImportGuardsAndCancellationRecovery() throws {
        var count = 0
        try step("regression01_busy_import_disables_competing_actions") {
            launch(extra: ["-EXRHostDelayMs", "8000"])
            openLibrary()
            count = bookRows().count
            XCTAssertGreaterThanOrEqual(count, 2)
            tapLibraryImport("library.import.large", timeout: 30)
            _ = waitElement("library.cancel", 5)
            XCTAssertTrue(waitUntil(3) {
                !self.element("library.import.epub").isEnabled &&
                !self.element("library.import.pdf").isEnabled &&
                !self.element("library.import.picker").isEnabled &&
                self.bookRows().allSatisfy { !$0.isEnabled }
            })
            attach("28-busy-import-guards")
        }
        try step("regression02_cancel_restores_real_shelf") {
            waitElement("library.cancel").tap()
            XCTAssertTrue(waitLabel("library.status", contains: "已取消", 40))
            XCTAssertEqual(bookRows().count, count)
            XCTAssertTrue(waitUntil(10) { self.bookRows().allSatisfy { $0.isEnabled } })
            XCTAssertTrue(element("library.import.epub").isEnabled)
        }
        try step("regression03_cancel_then_open_and_turn") {
            bookRow("Sample.epub").tap()
            _ = waitElement("reader.page", 90)
            XCTAssertTrue(waitLabel("reader.status", contains: "就绪", 40))
            waitElement("reader.first").tap()
            XCTAssertTrue(waitLabel("reader.location", contains: "第 1 页", 40))
            XCTAssertTrue(waitReaderIdle())
            waitElement("reader.next").tap()
            XCTAssertTrue(waitLabel("reader.location", contains: "第 2 页", 40))
            attach("29-after-cancel-real-page")
        }
    }

    func test09BusyReadingBackAndBookOwnership() throws {
        try step("regression04_reading_busy_guards") {
            launch(extra: ["-EXRHostDelayMs", "10000"])
            try ensureReader("Sample.epub")
            XCTAssertTrue(waitLabel("reader.status", contains: "就绪", 40))
            waitElement("reader.next").tap()
            _ = waitElement("reader.cancel", 5)
            XCTAssertTrue(waitUntil(3) {
                !self.element("reader.next").isEnabled && !self.element("reader.select").isEnabled &&
                !self.element("reader.font.increase").isEnabled && !self.element("reader.notes").isEnabled
            })
            XCTAssertTrue(element("reader.back").isEnabled)
        }
        try step("regression05_back_cancels_before_other_book") {
            waitElement("reader.back").tap()
            _ = waitElement("library.title", 40)
            XCTAssertTrue(waitUntil(40) { self.bookRow("Sample.pdf").isEnabled })
            bookRow("Sample.pdf").tap()
            XCTAssertTrue(waitLabel("reader.title", contains: "Sample.pdf", 90))
            XCTAssertTrue(waitLabel("reader.status", contains: "就绪", 40))
            attach("30-other-book-after-back")
        }
        try step("regression06_other_book_remains_owner_after_prior_completion") {
            Thread.sleep(forTimeInterval: 6)
            XCTAssertTrue(text("reader.title").contains("Sample.pdf"))
            XCTAssertTrue(text("reader.location").contains("/"))
            waitElement("reader.first").tap()
            XCTAssertTrue(waitLabel("reader.location", contains: "第 1 /", 40))
            XCTAssertTrue(waitReaderIdle())
            waitElement("reader.next").tap()
            XCTAssertTrue(waitLabel("reader.location", contains: "第 2 /", 40))
        }
    }

    func test10UnicodeSelectionAndCrossBookIsolation() throws {
        var originalNotes = ""
        try step("regression07_capture_original_book_notes") {
            launch()
            try ensureReader("Sample.epub")
            originalNotes = text("reader.notes")
            openLibrary()
            tapLibraryImport("library.import.unicode", expecting: ["已导入", "已存在"])
            bookRow("Unicode.epub").tap()
            XCTAssertTrue(waitLabel("reader.title", contains: "Unicode.epub", 90))
        }
        try step("regression08_select_and_copy_complete_unicode_scalars") {
            clearNotes()
            waitElement("reader.select").tap()
            _ = waitElement("selection.title", 20)
            waitElement("selection.all").tap()
            XCTAssertTrue(waitLabel("selection.quote", contains: "A😀é中", 20))
            XCTAssertFalse(text("selection.quote").contains("\u{FFFD}"))
            waitElement("selection.copy").tap()
            waitElement("selection.verifyPaste").tap()
            XCTAssertTrue(waitLabel("selection.clipboard", contains: "👩🏽‍💻 🇺🇳", 20))
            XCTAssertFalse(text("selection.clipboard").contains("\u{FFFD}"))
            attach("31-unicode-native-selection")
        }
        try step("regression09_unicode_annotation_matches_selected_source") {
            waitElement("selection.annotate").tap()
            XCTAssertTrue(waitLabel("reader.notes", contains: "标注 1", 40))
            waitElement("reader.notes").tap()
            XCTAssertTrue(waitLabel("notes.quote.0", contains: "A😀é中", 30))
            XCTAssertTrue(text("notes.quote.0").contains("👩🏽‍💻 🇺🇳"))
            XCTAssertFalse(text("notes.quote.0").contains("\u{FFFD}"))
            waitElement("notes.close").tap()
        }
        try step("regression10_unicode_selection_never_writes_other_book") {
            openLibrary()
            bookRow("Sample.epub").tap()
            XCTAssertTrue(waitLabel("reader.title", contains: "Sample.epub", 90))
            XCTAssertEqual(text("reader.notes"), originalNotes)
            waitElement("reader.select").tap()
            _ = waitElement("selection.title", 20)
            XCTAssertEqual(text("selection.quote"), "尚未选择文字")
            waitElement("selection.close").tap()
            attach("32-cross-book-selection-cleared")
        }
    }

    func test11SelectionInvalidatedByViewportChange() throws {
        try step("regression11_select_before_viewport_change") {
            launch()
            try ensureReader("Sample.epub")
            waitElement("reader.select").tap()
            _ = waitElement("selection.title", 20)
            waitElement("selection.all").tap()
            XCTAssertTrue(waitLabelFilled("selection.quote", excluding: ["尚未选择文字"], 20))
        }
        try step("regression12_changed_frame_rejects_old_selection") {
#if os(iOS)
            XCUIDevice.shared.orientation = .landscapeLeft
#else
            resizeWindow(dx: -160, dy: -100)
#endif
            XCTAssertTrue(waitLabel("selection.hint", contains: "页面已变化", 40))
            XCTAssertEqual(text("selection.quote"), "尚未选择文字")
            XCTAssertFalse(element("selection.annotate").isEnabled)
            XCTAssertFalse(element("selection.copy").isEnabled)
            attach("33-old-frame-selection-rejected")
        }
        try step("regression13_new_frame_requires_fresh_selection") {
            waitElement("selection.close").tap()
#if os(iOS)
            XCUIDevice.shared.orientation = .portrait
#else
            resizeWindow(dx: 160, dy: 100)
#endif
            Thread.sleep(forTimeInterval: 1.5)
            XCTAssertTrue(waitReaderIdle())
            waitElement("reader.select").tap()
            _ = waitElement("selection.title", 20)
            XCTAssertEqual(text("selection.quote"), "尚未选择文字")
            waitElement("selection.all").tap()
            XCTAssertTrue(waitLabelFilled("selection.quote", excluding: ["尚未选择文字"], 20))
            waitElement("selection.close").tap()
        }
    }

    func test13BoundedChapterNotesAndRelaunch() throws {
        var location = ""
        try step("bounded01_import_source_and_open") {
            launch(); openLibrary()
            tapLibraryImport("library.import.bounded", expecting: ["已导入", "已存在"])
            bookRow("Bounded.epub").tap()
            XCTAssertTrue(waitReaderIdle(90))
            XCTAssertTrue(text("reader.progress").contains("有界 EPUB"))
            waitElement("reader.first").tap()
            XCTAssertTrue(waitLabel("reader.location", contains: "第 1 章", 40))
            XCTAssertTrue(waitReaderIdle())
            attach("35-bounded-first-chapter")
        }
        try step("bounded02_cross_chapter_same_local_offset") {
            waitElement("reader.next").tap()
            XCTAssertTrue(waitLabel("reader.location", contains: "第 2 章", 40))
            XCTAssertTrue(waitReaderIdle())
            location = text("reader.location")
        }
        try step("bounded03_note_current_chapter") {
            clearNotes()
            waitElement("reader.select").tap(); _ = waitElement("selection.title", 20)
            waitElement("selection.all").tap()
            XCTAssertTrue(waitLabelFilled("selection.quote", excluding: ["尚未选择文字"], 20))
            waitElement("selection.annotate").tap()
            XCTAssertTrue(waitLabel("reader.notes", contains: "标注 1", 40))
        }
        try step("bounded04_repeat_path_rejects_old_frame") {
            waitElement("reader.next").tap()
            XCTAssertTrue(waitLabel("reader.location", contains: "第 3 章", 40))
            XCTAssertTrue(waitReaderIdle())
            waitElement("reader.notes").tap(); _ = waitElement("notes.title", 20)
            waitElement("notes.jump.0").tap()
            XCTAssertTrue(waitLabel("reader.location", contains: "第 2 章", 40))
            XCTAssertTrue(waitReaderIdle())
            attach("36-bounded-note-cross-chapter-jump")
        }
        try step("bounded05_process_reopen_restores_route") {
            app.terminate(); launch()
            XCTAssertTrue(waitReaderIdle(90))
            XCTAssertEqual(text("reader.location"), location)
            XCTAssertTrue(text("reader.notes").contains("标注 1"))
            attach("37-bounded-reopen-route")
        }
        try step("bounded06_backwards_cross_chapter") {
            waitElement("reader.previous").tap()
            XCTAssertTrue(waitLabel("reader.location", contains: "第 1 章", 40))
            XCTAssertTrue(waitReaderIdle())
        }
    }

    func test12NondefaultFontAndExactProgressRelaunch() throws {
        var font = "", location = ""
        try step("regression14_save_nondefault_font_and_progress") {
            launch()
            try ensureReader("Sample.epub")
            let priorFont = text("reader.font.value")
            waitElement("reader.font.increase").tap()
            XCTAssertTrue(waitUntil(40) { self.text("reader.font.value") != priorFont })
            XCTAssertTrue(waitReaderIdle())
            font = text("reader.font.value")
            XCTAssertFalse(font.isEmpty)
            waitElement("reader.first").tap()
            XCTAssertTrue(waitLabel("reader.location", contains: "第 1 页", 40))
            XCTAssertTrue(waitReaderIdle())
            waitElement("reader.next").tap()
            XCTAssertTrue(waitLabel("reader.location", contains: "第 2 页", 40))
            location = text("reader.location")
        }
        try step("regression15_real_process_relaunch_restores_font_and_page") {
            app.terminate()
            launch()
            _ = waitElement("reader.page", 90)
            XCTAssertTrue(waitUntil(30) {
                self.text("reader.font.value") == font && self.text("reader.location") == location
            })
            attach("34-nondefault-font-restored")
        }
    }
}
