// SPDX-License-Identifier: MIT
import XCTest
import Foundation

final class F04ReadingSyncUITests: XCTestCase {
    private let app = XCUIApplication()
    override func setUpWithError() throws { continueAfterFailure = false }
    override func tearDownWithError() throws { diagnosticReadingState("test-teardown", target: "reading.title") }
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
        #if os(macOS)
        if id.hasPrefix("reading.jump.") || id.hasPrefix("reading.edit.") {
            clickVisibleReadingRow(id)
            return
        }
        #endif
        XCTAssertTrue(e(id).waitForExistence(timeout: 30), id)
        if id.hasPrefix("reading.jump.") || id.hasPrefix("reading.edit.") {
            clickVisibleReadingRow(id)
            return
        }
        for _ in 0..<10 {
            if e(id).isHittable { break }
            let form = e("account.form")
            guard form.exists else { break }
            if e(id).frame.midY < form.frame.midY { form.swipeDown() } else { form.swipeUp() }
        }
        XCTAssertTrue(wait { e(id).exists && e(id).isEnabled && e(id).isHittable }, "\(id): \(app.debugDescription)")
        e(id).tap()
    }
    private func clickVisibleReadingRow(_ id: String) {
        #if os(macOS)
        clickVisibleMacReadingRow(id)
        #else
        let lists = app.descendants(matching: .any).matching(identifier: "reading.list")
        XCTAssertEqual(lists.count, 1, "Unique actual reading list required")
        for attempt in 0..<10 {
            let list = lists.element(boundBy: 0)
            let matches = list.descendants(matching: .button).matching(identifier: id)
            XCTAssertEqual(matches.count, 1, "Unique row action required: \(id)")
            let button = matches.element(boundBy: 0)
            let bounds = list.frame, frame = button.frame
            diagnosticReadingState("row-visibility-\(attempt)", target: id)
            XCTAssertTrue(bounds.width > 0 && bounds.height > 0 && frame.width > 0 && frame.height > 0)
            if bounds.contains(frame) {
                XCTAssertTrue(button.isEnabled && button.isHittable, "Visible row action must be enabled and hittable")
                #if os(macOS)
                button.click()
                #else
                button.tap()
                #endif
                return
            }
            XCTAssertTrue(frame.height <= bounds.height, "Row action cannot fit in the visible list")
            if frame.minY < bounds.minY { list.swipeDown() }
            else if frame.maxY > bounds.maxY { list.swipeUp() }
            else { XCTFail("Row action outside horizontal list bounds"); return }
            let deadline = Date().addingTimeInterval(3)
            var moved = false
            while Date() < deadline {
                let refreshed = lists.element(boundBy: 0).descendants(matching: .button).matching(identifier: id)
                if refreshed.count == 1 && refreshed.element(boundBy: 0).frame != frame { moved = true; break }
                RunLoop.current.run(until: Date().addingTimeInterval(0.1))
            }
            XCTAssertTrue(moved, "Actual list scroll did not move the target; no click issued")
        }
        XCTFail("Target did not enter the real list viewport; no click issued")
            #endif
    }
    #if os(macOS)
    private func clickVisibleMacReadingRow(_ id: String) {
        typealias State = (list: XCUIElement, bounds: CGRect, button: XCUIElement?, frame: CGRect?, anchors: [String: CGRect])
        var responseSign: CGFloat? = nil
        var stepLimit: CGFloat = 24
        var scrolls = 0
        guard let targetIndex = Int(id.split(separator: ".").last ?? "") else {
            XCTFail("Missing real row index"); return
        }
        func positive(_ frame: CGRect) -> Bool { frame.width > 0 && frame.height > 0 }
        func close(_ a: CGRect, _ b: CGRect) -> Bool {
            abs(a.minX - b.minX) <= 0.5 && abs(a.minY - b.minY) <= 0.5 &&
                abs(a.width - b.width) <= 0.5 && abs(a.height - b.height) <= 0.5
        }
        func same(_ a: State, _ b: State) -> Bool {
            guard close(a.bounds, b.bounds) else { return false }
            switch (a.frame, b.frame) {
            // A real target settles on its own geometry; unrelated anchors may virtualize.
            case let (x?, y?): return close(x, y)
            case (nil, nil):
                guard Set(a.anchors.keys) == Set(b.anchors.keys) else { return false }
                for (key, frame) in a.anchors {
                    guard let other = b.anchors[key], close(frame, other) else { return false }
                }
                return true
            default: return false
            }
        }
        func sample() -> State? {
            let deadline = Date().addingTimeInterval(3)
            var previous: State? = nil
            var stable = 0
            while Date() < deadline {
                let lists = app.descendants(matching: .any).matching(identifier: "reading.list")
                guard lists.count == 1 else { XCTFail("Unique actual reading list required"); return nil }
                let list = lists.element(boundBy: 0), bounds = list.frame
                guard positive(bounds) else { XCTFail("Positive actual list bounds required"); return nil }
                let matches = list.descendants(matching: .button).matching(identifier: id)
                guard matches.count <= 1 else { XCTFail("Unique row action required: \(id)"); return nil }
                let button: XCUIElement? = matches.count == 1 ? matches.element(boundBy: 0) : nil
                let rawFrame = button?.frame
                let frame = rawFrame.flatMap { positive($0) ? $0 : nil }
                var anchors: [String: CGRect] = [:]
                let candidates = list.descendants(matching: .any).matching(NSPredicate(
                    format: "identifier BEGINSWITH %@ OR identifier BEGINSWITH %@ OR identifier BEGINSWITH %@ OR identifier BEGINSWITH %@",
                    "reading.kind.", "reading.body.", "reading.jump.", "reading.edit."))
                var duplicates = Set<String>()
                for item in candidates.allElementsBoundByIndex {
                    let key = item.identifier, rect = item.frame
                    guard positive(rect), bounds.intersects(rect) else { continue }
                    if anchors[key] != nil { duplicates.insert(key) }
                    anchors[key] = rect
                }
                for key in duplicates { anchors.removeValue(forKey: key) }
                let current: State = (list, bounds, button, frame, anchors)
                if let old = previous, same(current, old) { stable += 1 } else { stable = 0 }
                previous = current
                // Unmaterialized targets get the full bounded fresh-query window.
                if frame != nil && stable >= 3 { return current }
                RunLoop.current.run(until: Date().addingTimeInterval(0.1))
            }
            guard let result = previous, stable >= 3 else {
                XCTFail("Actual list did not settle within three seconds; no click issued"); return nil
            }
            return result
        }
        func desiredMovement(_ frame: CGRect, _ bounds: CGRect) -> CGFloat {
            // Four pixels guide scrolling only, never admission.
            let padding: CGFloat = frame.height + 8 <= bounds.height ? 4 : 0
            if frame.minY < bounds.minY { return bounds.minY + padding - frame.minY }
            return bounds.maxY - padding - frame.maxY
        }
        guard var state = sample() else { return }
        // Both materialization and convergence share twenty scrolls / twenty-one checks.
        for attempt in 0...20 {
            diagnosticReadingState("row-visibility-\(attempt)", target: id)
            let bounds = state.bounds
            var wanted: CGFloat
            if let frame = state.frame {
                if bounds.contains(frame) {
                    guard let button = state.button else { XCTFail("Unique row action required"); return }
                    XCTAssertTrue(positive(frame) && positive(bounds))
                    XCTAssertTrue(button.isEnabled && button.isHittable, "Visible row action must be enabled and hittable")
                    button.click()
                    return
                }
                guard frame.height <= bounds.height else { XCTFail("Row action cannot fit in visible list"); return }
                guard frame.minX >= bounds.minX && frame.maxX <= bounds.maxX else {
                    XCTFail("Row action outside horizontal list bounds"); return
                }
                wanted = desiredMovement(frame, bounds)
            } else {
                // Row indices come from the real enumerated List; zero rects never imply a position.
                let indexed = state.anchors.compactMap { key, frame -> (Int, CGRect)? in
                    guard let index = Int(key.split(separator: ".").last ?? "") else { return nil }
                    return (index, frame)
                }
                guard let first = indexed.map({ $0.0 }).min(), let last = indexed.map({ $0.0 }).max() else {
                    XCTFail("No real visible row anchors for materialization"); return
                }
                if targetIndex > last { wanted = -24 }
                else if targetIndex < first { wanted = 24 }
                else if let peer = indexed.first(where: { $0.0 == targetIndex }) {
                    wanted = peer.1.midY >= bounds.midY ? -24 : 24
                } else {
                    XCTFail("Cannot infer target direction from real visible rows"); return
                }
            }
            guard scrolls < 20 else { break }
            let cap = scrolls == 0 ? min(CGFloat(16), stepLimit) : stepLimit
            let magnitude = min(cap, min(abs(wanted) + 4, bounds.height * 0.2))
            XCTAssertTrue(magnitude > 0, "A nonzero bounded scroll is required")
            let delta = (wanted > 0 ? magnitude : -magnitude) * (responseSign ?? 1)
            print("F04_MAC_SCROLL before target=\(id) scroll=\(scrolls + 1) delta=\(delta) wanted=\(wanted) frame=\(String(describing: state.frame)) bounds=\(bounds)")
            state.list.scroll(byDeltaX: 0, deltaY: delta)
            scrolls += 1
            guard let next = sample() else { return }
            var movements = state.anchors.compactMap { key, frame -> CGFloat? in
                guard let nextFrame = next.anchors[key] else { return nil }
                let movement = nextFrame.midY - frame.midY
                return abs(movement) > 0.5 ? movement : nil
            }
            if let oldFrame = state.frame, let nextFrame = next.frame {
                let movement = nextFrame.midY - oldFrame.midY
                if abs(movement) > 0.5 { movements.append(movement) }
            }
            if let movement = movements.first {
                guard movements.allSatisfy({ $0 * movement > 0 }) else {
                    XCTFail("Inconsistent real row movement; no click issued"); return
                }
                responseSign = movement * delta > 0 ? 1 : -1
            }
            let newlyMaterialized = state.frame == nil && next.frame != nil
            let changedVisibleSet = Set(state.anchors.keys) != Set(next.anchors.keys)
            // Set turnover proves progress, not signed movement; never calibrate from placeholders.
            guard !movements.isEmpty || newlyMaterialized || changedVisibleSet else {
                XCTFail("Actual list scroll made no measurable progress; no click issued"); return
            }
            if next.frame == nil && responseSign == nil {
                XCTFail("No common real anchor to calibrate materialization direction"); return
            }
            if let oldFrame = state.frame, let nextFrame = next.frame {
                let oldWanted = desiredMovement(oldFrame, bounds)
                let nextWanted = desiredMovement(nextFrame, next.bounds)
                if !next.bounds.contains(nextFrame) && oldWanted * nextWanted < 0 {
                    stepLimit = max(CGFloat(1), stepLimit / 2)
                }
            }
            print("F04_MAC_SCROLL after target=\(id) scroll=\(scrolls) responseSign=\(String(describing: responseSign)) limit=\(stepLimit) frame=\(String(describing: next.frame)) bounds=\(next.bounds)")
            state = next
        }
        XCTFail("Target did not enter the real list viewport; no click issued")
    }
    #endif
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
    private func diagnosticReadingState(_ event: String, target: String) {
        guard "__MAC_DIAGNOSTIC__" == "1" else { return }
        var fields: [String: Any] = ["event": event, "target": target]
        for id in ["reader.status", "reading.status", "reader.location", "reader.busy", "reading.cancel", "reading.list", target] {
            let item = e(id)
            var value: [String: Any] = ["exists": item.exists]
            if item.exists {
                value["enabled"] = item.isEnabled
                value["hittable"] = item.isHittable
                value["frame"] = String(describing: item.frame)
                if let snapshot = try? item.snapshot() {
                    value["label"] = String(snapshot.label.prefix(2048))
                    value["value"] = String(((snapshot.value as? String) ?? "").prefix(2048))
                }
            }
            fields[id] = value
        }
        if let bytes = try? JSONSerialization.data(withJSONObject: fields, options: [.sortedKeys]),
           let json = String(data: bytes, encoding: .utf8) { print("F04_READING_STATE " + json) }
    }
    private func jumpIncoming(_ kind: String, _ marker: String, _ checkpointName: String) {
        records()
        let i = row(kind, containing: marker); XCTAssertGreaterThanOrEqual(i, 0)
        diagnosticReadingState("before-jump", target: "reading.jump.\(i)")
        defer { diagnosticReadingState("jump-finally", target: "reading.jump.\(i)") }
        tap("reading.jump.\(i)")
        diagnosticReadingState("after-jump", target: "reading.jump.\(i)")
        XCTAssertTrue(wait { !e("reader.busy").exists && !e("reading.cancel").exists })
        diagnosticReadingState("before-close", target: "reading.jump.\(i)")
        tap("reading.close")
        diagnosticReadingState("after-close", target: "reading.jump.\(i)")
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
