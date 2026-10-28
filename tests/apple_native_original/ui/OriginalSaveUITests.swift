// SPDX-License-Identifier: MIT
import XCTest

final class OriginalSaveUITests: XCTestCase {
    private let app = XCUIApplication()
    override func setUpWithError() throws { continueAfterFailure = false }
    override func tearDownWithError() throws {
        let tree = XCTAttachment(string: app.debugDescription)
        tree.name = "native-tree"; tree.lifetime = .keepAlways; add(tree)
        let screen = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        screen.name = "native-screen"; screen.lifetime = .keepAlways; add(screen)
        app.terminate()
    }
    private func e(_ id: String) -> XCUIElement { app.descendants(matching: .any).matching(identifier: id).firstMatch }
    private func wait(_ predicate: () -> Bool) -> Bool {
        let end = Date().addingTimeInterval(90)
        while Date() < end { if predicate() { return true }; RunLoop.current.run(until: Date().addingTimeInterval(0.2)) }
        return predicate()
    }
    private func tap(_ id: String) {
        XCTAssertTrue(wait { self.e(id).exists && self.e(id).isHittable }, "Missing \(id): \(app.debugDescription)")
        e(id).tap()
    }
    func testSystemFolderSave() {
        app.launchArguments = ["-EXRUITestFixtures", "1", "-EXRFreshState", "1"]
        app.launch()
        XCTAssertTrue(wait { self.e("library.title").exists && !self.e("library.busy").exists })
        tap("library.import.epub")
        XCTAssertTrue(wait { self.e("library.book.0").exists && !self.e("library.busy").exists })
        tap("library.book.0")
        XCTAssertTrue(wait { self.e("reader.page").exists && !self.e("reader.busy").exists })
#if os(iOS)
        let more = e("reader.more").buttons.firstMatch
        XCTAssertTrue(wait { more.exists && more.frame.width > 0 })
        more.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
#else
        tap("reader.more")
#endif
        let title = "文件、字体与同步详情"
        XCTAssertTrue(wait { self.e("reader.features").exists || self.app.menuItems[title].exists || self.app.buttons[title].exists })
        if e("reader.features").exists { tap("reader.features") }
        else if app.menuItems[title].exists { app.menuItems[title].tap() }
        else { app.buttons[title].tap() }
        tap("features.original.export")
#if os(macOS)
        // The runner creates this empty directory before launch. Navigate in the real NSOpenPanel.
        app.typeKey("g", modifierFlags: [.command, .shift])
        let path = app.textFields.firstMatch
        XCTAssertTrue(wait { path.exists && path.isHittable }, app.debugDescription)
        path.typeText("/tmp/exreader-native-original-export\n")
        let open = app.buttons["Open"].firstMatch
        XCTAssertTrue(wait { open.exists && open.isHittable }, app.debugDescription)
        open.tap()
#else
        // Create a destination in the Files local provider through the real picker.
        let browse = app.buttons["Browse"].firstMatch
        if browse.waitForExistence(timeout: 10) && browse.isHittable { browse.tap() }
        let local = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "On My ")).firstMatch
        XCTAssertTrue(wait { local.exists && local.isHittable }, app.debugDescription)
        local.tap()
        let newFolder = app.buttons["New Folder"].firstMatch
        if !newFolder.exists {
            let overflow = app.buttons["OverflowBarButtonItem"].firstMatch
            XCTAssertTrue(wait { overflow.exists && overflow.isHittable }, app.debugDescription)
            overflow.tap()
        }
        XCTAssertTrue(wait { newFolder.exists && newFolder.isHittable }, app.debugDescription)
        newFolder.tap()
        let inline = app.textViews["DOC.inlineRenameField"].firstMatch
        if inline.waitForExistence(timeout: 10) {
            XCTAssertTrue(wait { inline.isHittable }, app.debugDescription)
            let old = (inline.value as? String) ?? ""
            inline.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: old.count))
            inline.typeText("EXReaderOriginalSave\n")
        } else {
            let name = app.textFields.firstMatch
            XCTAssertTrue(wait { name.exists && name.isHittable }, app.debugDescription)
            name.tap(); name.typeText("EXReaderOriginalSave")
            let done = app.buttons["Done"].firstMatch
            XCTAssertTrue(wait { done.exists && done.isHittable }, app.debugDescription)
            done.tap()
        }
        let folder = app.staticTexts["EXReaderOriginalSave"].firstMatch
        if folder.waitForExistence(timeout: 10) && folder.isHittable { folder.tap() }
        let open = app.buttons["Open"].firstMatch
        XCTAssertTrue(wait { open.exists && open.isHittable }, app.debugDescription)
        open.tap()
#endif
        XCTAssertTrue(wait {
            let status = self.e("features.status")
            return (status.label.contains("原件已导出") || ((status.value as? String) ?? "").contains("原件已导出")) && !self.e("features.cancel").exists
        }, app.debugDescription)
        XCTAssertTrue(e("features.export.filename").exists)
    }
}
