// SPDX-License-Identifier: MIT
import XCTest
import Foundation

final class F04ReadingSyncUITests: XCTestCase {
    private let app = XCUIApplication()
    override func setUpWithError() throws { continueAfterFailure = false }
    private func e(_ id: String) -> XCUIElement { app.descendants(matching: .any).matching(identifier: id).firstMatch }
    private func text(_ id: String) -> String {
        guard let s = try? e(id).snapshot() else { return "" }
        return s.label.isEmpty ? (s.value as? String) ?? "" : s.label
    }
    private func wait(_ condition: () -> Bool) -> Bool {
        let deadline = Date().addingTimeInterval(150)
        while Date() < deadline { if condition() { return true }; RunLoop.current.run(until: Date().addingTimeInterval(0.2)) }
        return condition()
    }
    private func tap(_ id: String) {
        XCTAssertTrue(e(id).waitForExistence(timeout: 30), id)
        for _ in 0..<10 {
            if e(id).isHittable { break }
            let form = e("account.form")
            guard form.exists else { break }
            if e(id).frame.midY < form.frame.midY { form.swipeDown() } else { form.swipeUp() }
        }
        XCTAssertTrue(wait { e(id).exists && e(id).isEnabled && e(id).isHittable }, "\(id): \(app.debugDescription)")
        e(id).tap()
    }
    private func records() {
        #if os(iOS)
        let trigger = e("reader.more").buttons.firstMatch
        XCTAssertTrue(wait { trigger.exists && trigger.frame.width > 0 })
        trigger.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        #else
        tap("reader.more")
        #endif
        XCTAssertTrue(wait { e("reader.records").exists || app.buttons["阅读记录"].exists })
        if e("reader.records").exists { tap("reader.records") } else { app.buttons["阅读记录"].tap() }
        XCTAssertTrue(wait { text("reading.status") == "本书的书签与标注" })
    }
    private func checkpoint(_ name: String) {
        let done = expectation(description: "read-only host evidence " + name)
        var request = URLRequest(url: URL(string: "__CONTROL__" + name)!)
        request.httpMethod = "POST"; request.setValue("__TOKEN__", forHTTPHeaderField: "Authorization")
        URLSession.shared.dataTask(with: request) { _, response, error in
            XCTAssertNil(error); XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200); done.fulfill()
        }.resume()
        self.wait(for: [done], timeout: 30)
        let tree = XCTAttachment(string: app.debugDescription); tree.name = name; tree.lifetime = .keepAlways; add(tree)
        let screen = XCTAttachment(screenshot: XCUIScreen.main.screenshot()); screen.name = name; screen.lifetime = .keepAlways; add(screen)
    }

    private func row(_ kind: String, containing marker: String = "") -> Int {
        for i in 0..<32 {
            if text("reading.kind.\(i)") == kind &&
                (marker.isEmpty || text("reading.body.\(i)").contains(marker)) { return i }
        }
        XCTFail("Required real record missing: \(kind) \(marker): \(app.debugDescription)")
        return -1
    }
    private func note(_ index: Int, _ value: String) {
        XCTAssertGreaterThanOrEqual(index, 0)
        tap("reading.edit.\(index)")
        let editor = app.textViews.matching(identifier: "reading.editor").firstMatch
        XCTAssertTrue(wait { editor.exists && editor.isHittable })
        editor.tap(); editor.typeText(value)
        tap("reading.save-note")
        XCTAssertTrue(wait { text("reading.status").contains("批注已保存") })
    }
    private func createExchangeRecords() {
        let unchanged = text("reader.location")
        records(); tap("reading.add-bookmark")
        XCTAssertTrue(wait { text("reading.status").contains("已添加书签") })
        note(row("书签"), "__OUTGOING_PREFIX___BOOKMARK")
        tap("reading.close")
        tap("reader.select"); tap("selection.all")
        XCTAssertTrue(wait { !text("selection.quote").isEmpty })
        tap("selection.reading-highlight")
        XCTAssertTrue(wait { text("reader.status") == "已保存高亮到阅读记录" })
        tap("selection.close")
        records(); note(row("高亮"), "__OUTGOING_PREFIX___NOTE"); tap("reading.close")
        XCTAssertEqual(text("reader.location"), unchanged, "Creating annotations must not navigate")
        checkpoint("created-records")
    }
    private func jumpIncoming(_ kind: String, _ marker: String, _ checkpointName: String) {
        records()
        let i = row(kind, containing: marker); XCTAssertGreaterThanOrEqual(i, 0)
        tap("reading.jump.\(i)")
        XCTAssertTrue(wait { !e("reader.busy").exists && !e("reading.cancel").exists })
        tap("reading.close")
        XCTAssertTrue(wait { text("reader.status") == "已精确定位阅读记录" })
        checkpoint(checkpointName)
    }
    func testActualApplicationRelay() {
        app.launchArguments = ["-EXRUITestFixtures", "1", "-EXRFreshState", "1"]
        app.launch()
        XCTAssertTrue(wait { e("library.title").exists && !e("library.busy").exists })
        tap("account.choose")
        tap("account.root"); e("account.root").typeText("__ROOT__\n")
        tap("account.username"); e("account.username").typeText("__USER__\n")
        tap("account.password"); e("account.password").typeText("__PASSWORD__\n")
        tap("account.connect")
        XCTAssertTrue(wait { e("account.sync.start").exists && !e("library.busy").exists })
        if "__PHASE__" == "apple-first" {
            tap("library.import.epub")
            XCTAssertTrue(wait { e("library.book.0").exists && !e("library.busy").exists })
            tap("library.book.0")
        } else {
            tap("account.sync.start")
            let remote = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "library.cloud.")).firstMatch
            XCTAssertTrue(wait { remote.exists && remote.isHittable && !e("account.sync.cancel").exists }, app.debugDescription)
            remote.tap()
        }
        XCTAssertTrue(wait { e("reader.page").exists && !e("reader.busy").exists })
        if "__PHASE__" == "apple-first" {
            for _ in 0..<3 {
                let before = text("reader.location")
                tap("reader.next")
                XCTAssertTrue(wait { !e("reader.busy").exists && text("reader.location") != before })
            }
            records(); tap("reading.save-progress")
            XCTAssertTrue(wait { text("reading.status") == "已保存阅读进度" })
            tap("reading.close")
        } else {
            records(); XCTAssertTrue(e("reading.jump.0").waitForExistence(timeout: 30))
            tap("reading.jump.0")
            XCTAssertTrue(wait { !e("reader.busy").exists && !e("reading.cancel").exists })
            tap("reading.close")
            XCTAssertTrue(wait { text("reader.status") == "已精确定位阅读记录" }, app.debugDescription)
        }
        XCTAssertTrue(wait { e("reader.page").exists && !e("reader.busy").exists })
        checkpoint("position")
        if "__PHASE__" == "apple-first" {
            createExchangeRecords()
        } else {
            jumpIncoming("书签", "__INCOMING_PREFIX___BOOKMARK", "incoming-bookmark")
            jumpIncoming("批注", "__INCOMING_PREFIX___NOTE", "incoming-note")
        }
        if "__PHASE__" != "apple-return" {
            if "__PHASE__" != "apple-first" {
                let unchanged = text("reader.location")
                records(); tap("reading.save-progress")
                XCTAssertTrue(wait { text("reading.status") == "已保存阅读进度" })
                note(row("书签", containing: "__INCOMING_PREFIX___BOOKMARK"), "__OUTGOING_PREFIX___BOOKMARK")
                note(row("批注", containing: "__INCOMING_PREFIX___NOTE"), "__OUTGOING_PREFIX___NOTE")
                tap("reading.close")
                XCTAssertEqual(text("reader.location"), unchanged)
                checkpoint("edited-records")
            }
            tap("reader.back"); tap("account.sync.start")
            XCTAssertTrue(wait { text("account.receive.state").hasPrefix("已接收") && !e("account.sync.cancel").exists })
            checkpoint("uploaded")
        }
        app.terminate()
    }
}
