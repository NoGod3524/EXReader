// SPDX-License-Identifier: MIT
// G16: independent macOS / iPhone / iPad accessibility audit of the shipped
// Apple host. These cases never edit the host: they drive the real UI through
// its public fixture path and record the accessibility tree, state exposure,
// text-size behaviour, rotation and keyboard reachability for the cloud gate.
//
// An audit records evidence; it does not gate on findings. Objective violations
// are written into the emitted records and judged in the cloud against
// a11y_contract.json, so "audit completed" and "accessibility accepted" stay
// separate facts.
import XCTest
#if os(iOS)
import UIKit
#endif

final class EXReaderA11yAuditTests: XCTestCase {
    private var app: XCUIApplication!
    private let audit = A11yAuditRecorder()

    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication()
    }

    override func tearDownWithError() throws {
#if os(iOS)
        XCUIDevice.shared.orientation = .portrait
#endif
        if app != nil, app.state != .notRunning { app.terminate() }
    }

    // MARK: - Queries

    private func element(_ identifier: String) -> XCUIElement {
        app.descendants(matching: .any).matching(identifier: identifier).firstMatch
    }

    @discardableResult
    private func waitElement(_ identifier: String, _ timeout: TimeInterval = 120,
                             file: StaticString = #filePath, line: UInt = #line) -> XCUIElement {
        let target = element(identifier)
        XCTAssertTrue(target.waitForExistence(timeout: timeout),
                      "missing " + identifier + "\n" + app.debugDescription, file: file, line: line)
        return target
    }

    private func axText(_ identifier: String) -> String {
        let target = element(identifier)
        guard target.exists else { return "" }
        if !target.label.isEmpty { return target.label }
        return (target.value as? String) ?? ""
    }

    private func shelfRows() -> XCUIElementQuery {
        app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "library.book."))
    }

    private func bookCount() -> Int { shelfRows().count }

    private func bookRow(_ title: String) -> XCUIElement {
        app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@ AND label CONTAINS %@",
                                          "library.book.", title)).firstMatch
    }

    private func bookLabels() -> [String] {
        let query = shelfRows()
        var labels: [String] = []
        for index in 0..<min(query.count, 8) { labels.append(query.element(boundBy: index).label) }
        return labels
    }

    // MARK: - Settling

    private func idleIdentity() -> String {
        if element("reader.page").exists {
            guard !element("reader.busy").exists, element("reader.next").isEnabled else { return "" }
            let location = axText("reader.location")
            guard !location.isEmpty else { return "" }
            return "reader|" + location + "|" + axText("reader.font.value") + "|" + axText("reader.state")
        }
        if element("library.title").exists {
            guard !element("library.busy").exists, element("library.import.epub").isEnabled else { return "" }
            let status = axText("library.status")
            guard !status.isEmpty else { return "" }
            return "library|\(bookCount())|" + status
        }
        return ""
    }

    @discardableResult
    private func waitIdle(_ timeout: TimeInterval = 240) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        var previous = ""
        var stableSince: Date?
        while Date() < deadline {
            let current = idleIdentity()
            if current.isEmpty {
                previous = ""
                stableSince = nil
            } else if current == previous {
                if let stableSince, Date().timeIntervalSince(stableSince) >= 0.7 { return true }
            } else {
                previous = current
                stableSince = Date()
            }
            RunLoop.current.run(until: Date().addingTimeInterval(0.2))
        }
        return false
    }

    @discardableResult
    private func waitText(_ identifier: String, contains expected: String,
                          timeout: TimeInterval = 240) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if axText(identifier).contains(expected) { return true }
            RunLoop.current.run(until: Date().addingTimeInterval(0.3))
        }
        print("EXR_A11Y_WAIT id=" + identifier + " expected=" + expected + " observed=" + axText(identifier))
        return false
    }

    @discardableResult
    private func waitText(_ identifier: String, containsAny expected: [String],
                          timeout: TimeInterval = 240) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            let current = axText(identifier)
            if expected.contains(where: { current.contains($0) }) { return true }
            RunLoop.current.run(until: Date().addingTimeInterval(0.3))
        }
        print("EXR_A11Y_WAIT id=" + identifier + " expected=" + expected.joined(separator: "|")
              + " observed=" + axText(identifier))
        return false
    }

    // MARK: - Host driving

    private func launch(fresh: Bool = false, extra: [String] = []) {
        var arguments = ["-EXRUITestFixtures", "1"]
        if fresh { arguments.append("-EXRFreshState") }
        arguments.append(contentsOf: extra)
        app.launchArguments = arguments
        app.launch()
        XCTAssertTrue(waitIdle(300), "host did not settle after launch\n" + app.debugDescription)
        audit.emitEnvironment(app)
    }

    private func openLibrary() {
        if !element("library.title").exists, element("reader.back").exists { element("reader.back").tap() }
        _ = waitElement("library.title", 120)
        XCTAssertTrue(waitIdle(240), "library did not settle")
    }

    private func waitUntil(_ timeout: TimeInterval, _ condition: () -> Bool) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if condition() { return true }
            RunLoop.current.run(until: Date().addingTimeInterval(0.3))
        }
        return condition()
    }

    /// A single recorded retry covers a dropped first tap; the import still has to
    /// reach the expected status, so nothing is asserted more weakly.
    private func importFixture(_ identifier: String, expects: [String], timeout: TimeInterval = 300) {
        for attempt in 1...2 {
            let button = waitElement(identifier, 120)
            XCTAssertTrue(button.isEnabled, identifier + " must be enabled for the audited import")
            button.tap()
            if waitUntil(20, { self.importLeftIdle() }) { break }
            print("EXR_A11Y_TAP_RETRY import " + identifier + " attempt=" + String(attempt))
        }
        XCTAssertTrue(waitText("library.status", containsAny: expects, timeout: timeout),
                      identifier + " did not report " + expects.joined(separator: "|"))
        XCTAssertTrue(waitIdle(300), "library did not settle after " + identifier)
    }

    /// True once the import produced any reaction: the busy marker appeared or the
    /// status text left the idle value.
    private func importLeftIdle() -> Bool {
        if element("library.busy").exists { return true }
        let status = axText("library.status")
        return !status.isEmpty && status != "就绪"
    }

    private func ensureBooks() {
        if !element("library.title").exists { openLibrary() }
        // Only an empty shelf triggers imports. Probing for a specific row is
        // unreliable at accessibility text sizes, where the lazy shelf builds
        // only the rows that fit on screen.
        if bookCount() == 0 {
            importFixture("library.import.epub", expects: ["已导入", "已存在"])
            importFixture("library.import.pdf", expects: ["已导入", "已存在"])
        }
    }

    private func openAnyBook() {
        XCTAssertTrue(waitIdle(240), "library did not settle before opening a book")
        let rows = shelfRows()
        XCTAssertGreaterThan(rows.count, 0, "library exposes no book row")
        rows.element(boundBy: 0).tap()
        if !element("reader.page").waitForExistence(timeout: 30) {
            print("EXR_A11Y_TAP_RETRY open-first-row")
            shelfRows().element(boundBy: 0).tap()
        }
        _ = waitElement("reader.page", 360)
        XCTAssertTrue(waitIdle(360), "reader did not settle")
    }

    private func openBook(_ title: String, timeout: TimeInterval = 360) {
        if element("reader.page").exists {
            if axText("reader.title").contains(title) {
                XCTAssertTrue(waitIdle(timeout), "reader did not settle")
                return
            }
            openLibrary()
        }
        if !element("library.title").exists { openLibrary() }
        if !bookRow(title).exists {
            importFixture(title.hasSuffix(".pdf") ? "library.import.pdf" : "library.import.epub",
                          expects: ["已导入", "已存在"])
        }
        let row = bookRow(title)
        XCTAssertTrue(row.waitForExistence(timeout: 180), "book row " + title + " missing")
        XCTAssertTrue(waitIdle(180), "library did not settle before opening " + title)
        row.tap()
        if !element("reader.page").waitForExistence(timeout: 30) {
            print("EXR_A11Y_TAP_RETRY open " + title)
            bookRow(title).tap()
        }
        _ = waitElement("reader.page", 360)
        XCTAssertTrue(waitIdle(timeout), "reader did not settle for " + title)
    }

    private func createAnnotation() {
        waitElement("reader.select").tap()
        _ = waitElement("selection.title", 120)
        waitElement("selection.all").tap()
        let deadline = Date().addingTimeInterval(120)
        while Date() < deadline && axText("selection.quote").contains("尚未选择文字") {
            RunLoop.current.run(until: Date().addingTimeInterval(0.3))
        }
        XCTAssertFalse(axText("selection.quote").contains("尚未选择文字"),
                       "annotate needs a published quote\n" + app.debugDescription)
        waitElement("selection.annotate").tap()
        XCTAssertTrue(waitText("reader.status", contains: "已保存标注", timeout: 300),
                      "annotation must be saved before the notes sheet is audited")
        XCTAssertTrue(waitIdle(300), "reader did not settle after annotation")
    }

    // MARK: - Recording

    private func capture(_ step: String, screenshot: String? = nil, detail: [String: Any] = [:],
                         file: StaticString = #filePath, line: UInt = #line) {
        let recorded = audit.capture(app, test: name, step: step, screenshot: screenshot,
                                     detail: detail) { [weak self] attachment in
            self?.add(attachment)
        }
        XCTAssertTrue(recorded, "accessibility tree unavailable for " + step, file: file, line: line)
    }

    private func step(_ label: String, _ body: () throws -> Void) rethrows {
        try XCTContext.runActivity(named: label) { _ in try body() }
    }

    // MARK: - Audit cases

    func test01LibraryEmptyNamesRolesStates() throws {
        try step("a11y-01-launch-empty-library") {
            launch(fresh: true)
            _ = waitElement("library.title", 180)
            XCTAssertTrue(waitIdle(300), "empty library did not settle")
            XCTAssertTrue(element("library.empty").exists, "empty shelf marker missing")
            capture("library.empty", screenshot: "a11y-01-library-empty",
                    detail: ["book_count": bookCount()])
        }
    }

    func test02ImportReachability() throws {
        try step("a11y-02-import-epub") {
            launch(fresh: true)
            _ = waitElement("library.title", 180)
            importFixture("library.import.epub", expects: ["已导入", "已存在"])
        }
        try step("a11y-03-import-pdf") {
            importFixture("library.import.pdf", expects: ["已导入", "已存在"])
            XCTAssertEqual(bookCount(), 2, "the two audited imports must yield two shelf rows")
            capture("library.populated", screenshot: "a11y-02-library-populated",
                    detail: ["book_count": bookCount(), "row_labels": bookLabels()])
        }
    }

    func test03ReaderNamesRolesStates() throws {
        try step("a11y-04-open-reader") {
            launch()
            ensureBooks()
            openBook("Sample.epub")
            waitElement("reader.first").tap()
            XCTAssertTrue(waitText("reader.location", contains: "第 1 页", timeout: 240),
                          "首页 must return the reader to page 1 for the audited baseline")
            XCTAssertTrue(waitText("reader.status", contains: "就绪", timeout: 240))
            XCTAssertTrue(waitIdle(360), "reader did not settle at page 1")
            capture("reader.epub", screenshot: "a11y-03-reader",
                    detail: ["page_label": axText("reader.page"),
                             "page_value": (element("reader.page").value as? String) ?? ""])
            XCTAssertFalse(axText("reader.page").isEmpty, "reading surface exposes no accessible name")
        }
        try step("a11y-05-turn-page") {
            waitElement("reader.next").tap()
            XCTAssertTrue(waitIdle(300), "reader did not settle after a page turn")
            XCTAssertTrue(waitText("reader.location", contains: "第 2 页", timeout: 120),
                          "page turn must publish the new location")
            capture("reader.second_page", screenshot: "a11y-04-reader-second-page")
        }
    }

    func test04BusyAndCancelStateExposure() throws {
        try step("a11y-06-busy-import") {
            launch(extra: ["-EXRHostDelayMs", "8000"])
            ensureBooks()
            waitElement("library.import.large", 120).tap()
            XCTAssertTrue(waitElement("library.cancel", 60).exists,
                          "a slow import must expose its cancel control")
            capture("library.busy", screenshot: "a11y-05-library-busy",
                    detail: ["busy_text": axText("library.busy"),
                             "cancel_enabled": element("library.cancel").isEnabled])
            waitElement("library.cancel").tap()
            XCTAssertTrue(waitText("library.status", contains: "已取消", timeout: 300),
                          "cancel must report 已取消")
            XCTAssertTrue(waitIdle(300), "library did not settle after cancel")
            capture("library.after_cancel", screenshot: "a11y-06-library-after-cancel")
        }
    }

    func test05SelectionSheetReachability() throws {
        try step("a11y-07-selection-sheet") {
            launch()
            ensureBooks()
            openBook("Sample.epub")
            waitElement("reader.select").tap()
            _ = waitElement("selection.title", 120)
            capture("selection.sheet", screenshot: "a11y-07-selection-sheet",
                    detail: ["selectable_label": axText("selection.text"),
                             "selectable_value_length": ((element("selection.text").value as? String) ?? "").count])
        }
        try step("a11y-08-select-all") {
            waitElement("selection.all").tap()
            let deadline = Date().addingTimeInterval(120)
            while Date() < deadline && axText("selection.quote").contains("尚未选择文字") {
                RunLoop.current.run(until: Date().addingTimeInterval(0.3))
            }
            XCTAssertFalse(axText("selection.quote").contains("尚未选择文字"),
                           "select-all must publish a quote")
            capture("selection.selected", screenshot: "a11y-08-selection-selected")
        }
        try step("a11y-09-annotate") {
            waitElement("selection.annotate").tap()
            XCTAssertTrue(waitText("reader.status", contains: "已保存标注", timeout: 300))
            XCTAssertTrue(waitIdle(300))
            capture("reader.with_note", screenshot: "a11y-09-reader-with-note",
                    detail: ["notes_label": axText("reader.notes")])
        }
    }

    func test06NotesSheetReachability() throws {
        try step("a11y-10-notes-sheet") {
            if !element("reader.page").exists {
                launch()
                ensureBooks()
                openBook("Sample.epub")
            }
            if axText("reader.notes").contains("标注 0") { createAnnotation() }
            waitElement("reader.notes").tap()
            _ = waitElement("notes.title", 120)
            capture("notes.sheet", screenshot: "a11y-10-notes-sheet",
                    detail: ["quote": axText("notes.quote.0"), "comment": axText("notes.comment.0"),
                             "state": axText("notes.state.0")])
        }
        try step("a11y-11-note-editor") {
            waitElement("notes.edit.0").tap()
            _ = waitElement("notes.edit.title", 120)
            capture("notes.editor", screenshot: "a11y-11-notes-editor",
                    detail: ["draft_value": (element("notes.editor").value as? String) ?? ""])
            waitElement("notes.cancel").tap()
            waitElement("notes.close").tap()
            XCTAssertTrue(waitIdle(300))
        }
    }

    func test07DynamicTypeAudit() throws {
#if os(macOS)
        throw XCTSkip("macOS has no system Dynamic Type scale; window stress is recorded as reader.window_min")
#else
        try step("a11y-12-large-type-reader") {
            // The container already holds the imported fixtures from the default-size
            // pass. The device content size is the fixture here; a launch-argument
            // override resets the app to the default category, so it is not used.
            launch()
            if !element("reader.page").waitForExistence(timeout: 180) {
                _ = element("library.title").waitForExistence(timeout: 120)
                ensureBooks()
                openAnyBook()
            }
            XCTAssertTrue(waitIdle(360), "reader did not settle at the accessibility text size")
            capture("reader.large_type", screenshot: "a11y-12-reader-large-type",
                    detail: ["content_size": "device-level accessibility-extra-extra-extra-large"])
        }
        try step("a11y-13-large-type-library") {
            waitElement("reader.back").tap()
            _ = waitElement("library.title", 180)
            XCTAssertTrue(waitIdle(300), "library did not settle at the accessibility text size")
            capture("library.large_type", screenshot: "a11y-13-library-large-type")
        }
#endif
    }

    func test08RotationAndWindowResize() throws {
#if os(iOS)
        try step("a11y-14-landscape") {
            launch()
            ensureBooks()
            openBook("Sample.epub")
            XCUIDevice.shared.orientation = .landscapeLeft
            Thread.sleep(forTimeInterval: 1.5)
            XCTAssertTrue(waitIdle(360), "reader did not settle after rotation")
            capture("reader.landscape", screenshot: "a11y-14-reader-landscape")
        }
        try step("a11y-15-portrait-restore") {
            XCUIDevice.shared.orientation = .portrait
            Thread.sleep(forTimeInterval: 1.5)
            XCTAssertTrue(waitIdle(360), "reader did not settle after restoring portrait")
            capture("reader.portrait", screenshot: "a11y-15-reader-portrait")
        }
#else
        try step("a11y-16-window-min") {
            launch()
            ensureBooks()
            openBook("Sample.epub")
            resizeWindow(dx: -400, dy: -400)
            Thread.sleep(forTimeInterval: 1.5)
            XCTAssertTrue(waitIdle(360), "reader did not settle at the minimum window")
            capture("reader.window_min", screenshot: "a11y-16-reader-window-min")
        }
        try step("a11y-17-window-restore") {
            resizeWindow(dx: 400, dy: 400)
            Thread.sleep(forTimeInterval: 1.5)
            XCTAssertTrue(waitIdle(360), "reader did not settle after restoring the window")
            capture("reader.window_default", screenshot: "a11y-17-reader-window-default")
        }
#endif
    }

    func test09KeyboardPath() throws {
#if os(iOS)
        throw XCTSkip("iOS full keyboard access is not enabled on the cloud simulator; keyboard path stays uncovered")
#else
        try step("a11y-18-keyboard-path") {
            launch()
            ensureBooks()
            openBook("Sample.epub")
            let window = app.windows.firstMatch
            XCTAssertTrue(window.exists, "macOS host window missing")
            let candidates = keyboardCandidates()
            XCTAssertFalse(candidates.isEmpty, "no identified controls to probe")
            capture("reader.keyboard", screenshot: "a11y-18-reader-keyboard",
                    detail: ["candidates": candidates])
            var presses: [[String: Any]] = []
            var sampled: [String] = [keyboardState()]
            for index in 0..<16 {
                window.typeKey(.tab, modifierFlags: [])
                RunLoop.current.run(until: Date().addingTimeInterval(0.25))
                var record: [String: Any] = ["press": index + 1, "state": keyboardState()]
                if (index + 1) % 4 == 0 {
                    window.typeKey(.space, modifierFlags: [])
                    RunLoop.current.run(until: Date().addingTimeInterval(0.9))
                    let activated = keyboardState()
                    record["activated_state"] = activated
                    sampled.append(activated)
                }
                presses.append(record)
            }
            let distinct = Array(Set(sampled)).sorted()
            audit.emitKeyboard(test: name, presses: presses, candidates: candidates,
                               step: "reader.keyboard", distinctStates: distinct,
                               changed: distinct.count > 1)
        }
#endif
    }

#if os(macOS)
    private func resizeWindow(dx: CGFloat, dy: CGFloat) {
        let window = app.windows.firstMatch
        guard window.exists else { return }
        let corner = window.coordinate(withNormalizedOffset: CGVector(dx: 0.985, dy: 0.985))
        corner.press(forDuration: 0.2, thenDragTo: corner.withOffset(CGVector(dx: dx, dy: dy)))
    }

    private func keyboardCandidates() -> [String] {
        var identifiers: [String] = []
        for control in app.buttons.allElementsBoundByIndex where !control.identifier.isEmpty {
            identifiers.append(control.identifier)
        }
        for control in app.textFields.allElementsBoundByIndex where !control.identifier.isEmpty {
            identifiers.append(control.identifier)
        }
        return identifiers
    }

    /// Observable reader state used by the keyboard probe: any change here means
    /// a keyboard press actually drove the host, without claiming to know which
    /// control owned focus.
    private func keyboardState() -> String {
        var parts: [String] = []
        parts.append(element("library.title").exists ? "library" : "reader")
        parts.append(axText("reader.location"))
        parts.append(axText("reader.font.value"))
        parts.append(axText("reader.status"))
        if element("selection.title").exists { parts.append("selection-sheet") }
        if element("notes.title").exists { parts.append("notes-sheet") }
        return parts.joined(separator: "|")
    }
#endif
}
