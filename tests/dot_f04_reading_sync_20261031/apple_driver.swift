// SPDX-License-Identifier: MIT
import XCTest
import Foundation

final class F04ReadingSyncUITests: XCTestCase {
    private let app = XCUIApplication()
    #if os(macOS)
    private var pythonNetworkDenyAttempted = false
    private var pythonNetworkDismissalPending = false
    private var macStartupFinished = false
    private var macNextPermissionCheck = Date.distantPast
    #endif
    override func setUpWithError() throws { continueAfterFailure = false }
    override func tearDownWithError() throws {
        diagnosticReadingState("test-teardown", target: "reading.title")
        #if os(macOS)
        diagnosticMacObstruction("test-teardown", target: "reading.save-progress")
        #endif
    }
    private func e(_ id: String) -> XCUIElement { app.descendants(matching: .any).matching(identifier: id).firstMatch }
    private func text(_ id: String) -> String {
        guard let s = try? e(id).snapshot() else { return "" }
        return s.label.isEmpty ? (s.value as? String) ?? "" : s.label
    }
    private func wait(_ condition: () -> Bool) -> Bool {
        let deadline = Date().addingTimeInterval(150)
        while Date() < deadline {
            #if os(macOS)
            if !macNoLatePermission(force: false) { return false }
            #endif
            if condition() { return true }
            RunLoop.current.run(until: Date().addingTimeInterval(0.2))
        }
        return condition()
    }
    private func tap(_ id: String) {
        #if os(macOS)
        guard macNoLatePermission(force: true) else { return }
        if id.hasPrefix("reading.jump.") || id.hasPrefix("reading.edit.") {
            clickVisibleReadingRow(id)
            return
        }
        #endif
        XCTAssertTrue(e(id).waitForExistence(timeout: 30), id)
        #if os(macOS)
        if ["reading.save-progress", "reading.save-note", "reading.close",
            "reader.back", "account.sync.start"].contains(id) {
            var activationAttempted = false
            let ready = wait {
                let target = e(id)
                if target.exists && target.isEnabled && target.isHittable { return true }
                if !activationAttempted {
                    activationAttempted = true
                    restoreMacForeground(for: id)
                }
                return false
            }
            if !ready { diagnosticMacObstruction("fixed-control-timeout", target: id) }
            XCTAssertTrue(ready, "Original fixed control readiness not reached: \(id)")
            diagnosticMacObstruction("before-fixed-tap", target: id)
            e(id).tap()
            diagnosticMacObstruction("after-fixed-tap", target: id)
            return
        }
        #endif
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
        typealias Observation = (bounds: CGRect, frame: CGRect?, anchors: [String: CGRect])
        var responseSign: CGFloat? = nil
        var stepLimit: CGFloat = 24
        var scrolls = 0
        var pending: (observation: Observation, delta: CGFloat)? = nil
        guard let targetIndex = Int(id.split(separator: ".").last ?? "") else {
            XCTFail("Missing real row index"); return
        }
        let peerID = (id.hasPrefix("reading.jump.") ? "reading.edit." : "reading.jump.") + String(targetIndex)
        func positive(_ frame: CGRect) -> Bool { frame.width > 0 && frame.height > 0 }
        func desiredMovement(_ frame: CGRect, _ bounds: CGRect) -> CGFloat {
            let padding: CGFloat = frame.height + 8 <= bounds.height ? 4 : 0
            if frame.minY < bounds.minY { return bounds.minY + padding - frame.minY }
            return bounds.maxY - padding - frame.maxY
        }
        // At most 21 fresh admission checks, 20 snapshots and 20 native scrolls.
        // No settling timer or sample count is an additional success condition.
        for attempt in 0...20 {
            let lists = app.descendants(matching: .any).matching(identifier: "reading.list")
            let listCount = lists.count
            guard listCount == 1 else { XCTFail("Unique actual reading list required"); return }
            let list = lists.element(boundBy: 0)
            let matches = list.descendants(matching: .button).matching(identifier: id)
            let count = matches.count
            guard count <= 1 else { XCTFail("Unique row action required: \(id)"); return }
            let bounds = list.frame
            let button: XCUIElement? = count == 1 ? matches.element(boundBy: 0) : nil
            let frame = button?.frame
            // Fresh original admission always precedes movement/anchor evidence.
            if let button = button, let frame = frame,
               positive(bounds), positive(frame), bounds.contains(frame),
               button.isEnabled && button.isHittable {
                button.click()
                return
            }
            // Log captured values only: no AX traversal between admission and click.
            print("F04_MAC_PREP target=\(id) check=\(attempt + 1) scrolls=\(scrolls) count=\(count) frame=\(String(describing: frame)) bounds=\(bounds)")
            guard attempt < 20 else { break }
            RunLoop.current.run(until: Date().addingTimeInterval(0.1))
            let tree: any XCUIElementSnapshot
            do { tree = try list.snapshot() }
            catch {
                print("F04_MAC_PREP snapshot unavailable; pending next fresh admission")
                continue
            }
            // All descendant reads below are from this one returned snapshot, not live elements.
            var nodes: [any XCUIElementSnapshot] = tree.children
            var targets: [any XCUIElementSnapshot] = []
            var anchors: [String: CGRect] = [:]
            var duplicates = Set<String>()
            while let node = nodes.popLast() {
                nodes.append(contentsOf: node.children)
                let key = node.identifier
                if key == id && node.elementType == .button { targets.append(node) }
                guard key.hasPrefix("reading.kind.") || key.hasPrefix("reading.body.") ||
                    key.hasPrefix("reading.jump.") || key.hasPrefix("reading.edit.") else { continue }
                let rect = node.frame
                guard positive(rect), tree.frame.intersects(rect) else { continue }
                if anchors[key] != nil { duplicates.insert(key) }
                anchors[key] = rect
            }
            for key in duplicates { anchors.removeValue(forKey: key) }
            guard targets.count <= 1 else { XCTFail("Unique snapshot row action required: \(id)"); return }
            let targetFrame = targets.first.map { $0.frame }.flatMap { positive($0) ? $0 : nil }
            let observation: Observation = (tree.frame, targetFrame, anchors)
            guard positive(observation.bounds) else { continue }
            // A possibly ready target goes straight to the next fresh original admission.
            if let targetFrame = targetFrame, observation.bounds.contains(targetFrame) { continue }
            if let previous = pending {
                var measured: [(String, CGFloat)] = []
                for key in previous.observation.anchors.keys.sorted() {
                    guard let before = previous.observation.anchors[key], let after = anchors[key] else { continue }
                    let movement = after.midY - before.midY
                    if abs(movement) > 0.5 { measured.append((key, movement)) }
                }
                if let before = previous.observation.frame, let after = targetFrame {
                    let movement = after.midY - before.midY
                    if abs(movement) > 0.5 { measured.insert((id, movement), at: 0) }
                }
                // Insufficient/conflicting evidence consumes a bounded observation, not a blind scroll.
                guard let chosen = measured.first,
                      measured.allSatisfy({ $0.1 * chosen.1 > 0 }) else {
                    print("F04_MAC_PREP movement evidence pending; no further scroll")
                    continue
                }
                responseSign = chosen.1 * previous.delta > 0 ? 1 : -1
                if let before = previous.observation.frame, let after = targetFrame,
                   !observation.bounds.contains(after),
                   desiredMovement(before, previous.observation.bounds) * desiredMovement(after, observation.bounds) < 0 {
                    stepLimit = max(CGFloat(1), stepLimit / 2)
                }
                pending = nil
            }
            var wanted: CGFloat? = nil
            if let targetFrame = targetFrame {
                // Geometry unsuitable for native vertical preparation remains pending, not a fabricated click.
                if targetFrame.height <= observation.bounds.height &&
                   targetFrame.minX >= observation.bounds.minX && targetFrame.maxX <= observation.bounds.maxX {
                    wanted = desiredMovement(targetFrame, observation.bounds)
                }
            } else {
                let indices = anchors.keys.compactMap { Int($0.split(separator: ".").last ?? "") }
                if let first = indices.min(), let last = indices.max() {
                    if targetIndex < first { wanted = 24 }
                    else if targetIndex > last { wanted = -24 }
                    else if let peer = anchors[peerID] {
                        // Only the real sibling action in the same HStack can guide this case.
                        if peer.minY < observation.bounds.minY { wanted = 24 }
                        else if peer.maxY > observation.bounds.maxY { wanted = -24 }
                    }
                }
            }
            guard let wanted = wanted, wanted != 0, scrolls < 20 else { continue }
            // Exactly one uncalibrated probe is allowed, based on real geometry/visible row order.
            guard scrolls == 0 || responseSign != nil else { continue }
            let cap = scrolls == 0 ? min(CGFloat(16), stepLimit) : stepLimit
            let magnitude = min(cap, min(abs(wanted) + 4, observation.bounds.height * 0.2))
            guard magnitude > 0 else { continue }
            let delta = (wanted > 0 ? magnitude : -magnitude) * (responseSign ?? 1)
            print("F04_MAC_SCROLL target=\(id) scroll=\(scrolls + 1) delta=\(delta) wanted=\(wanted) frame=\(String(describing: targetFrame)) bounds=\(observation.bounds)")
            list.scroll(byDeltaX: 0, deltaY: delta)
            scrolls += 1
            pending = (observation, delta)
        }
        XCTFail("Reading row preparation-incomplete within bounded native observations; no click issued")
    }
    #endif
    #if os(macOS)
    // Environment preparation precedes credentials, connections, books and record sheets.
    private func macStartupReady() -> Bool {
        guard "__MAC_DIAGNOSTIC__" == "1" else {
            return wait { e("library.title").exists && !e("library.busy").exists }
        }
        let deadline = Date().addingTimeInterval(150)
        let observationEnd = Date().addingTimeInterval(10)
        var restored = false
        while Date() < deadline {
            if !pythonNetworkDenyAttempted && Date() < observationEnd {
                denyKnownPythonNetworkRequestIfPresent()
            }
            if macPythonPermissionStillPending() {
                RunLoop.current.run(until: Date().addingTimeInterval(0.2))
                continue
            }
            if pythonNetworkDenyAttempted && !restored {
                restored = true
                restoreMacForeground(for: "library.title")
            }
            if pythonNetworkDenyAttempted || Date() >= observationEnd {
                if e("library.title").exists && !e("library.busy").exists {
                    macStartupFinished = true
                    return macNoLatePermission(force: true)
                }
            }
            RunLoop.current.run(until: Date().addingTimeInterval(0.2))
        }
        diagnosticMacObstruction("startup-timeout", target: "library.title")
        return false
    }
    private func macNoLatePermission(force: Bool) -> Bool {
        guard "__MAC_DIAGNOSTIC__" == "1", macStartupFinished else { return true }
        if !force && Date() < macNextPermissionCheck { return true }
        macNextPermissionCheck = Date().addingTimeInterval(1)
        guard currentPythonPermissionDialog() != nil else { return true }
        diagnosticMacObstruction("late-permission-environment-blocked", target: "reading.title")
        XCTFail("Environment blocked: permission arrived after startup; no denial, reopening or write replay")
        return false
    }
    private func permissionText(_ text: String) -> String {
        text.replacingOccurrences(of: "“", with: "\"").replacingOccurrences(of: "”", with: "\"")
            .replacingOccurrences(of: "‘", with: "'").replacingOccurrences(of: "’", with: "'")
            .split(whereSeparator: { $0.isWhitespace }).joined(separator: " ")
    }
    private func permissionSemantics(_ snapshot: any XCUIElementSnapshot) -> Set<String> {
        var result = Set<String>()
        var nodes: [any XCUIElementSnapshot] = [snapshot]
        while let node = nodes.popLast() {
            if node.elementType == .textField || node.elementType == .secureTextField ||
               node.elementType == .textView { continue }
            nodes.append(contentsOf: node.children)
            if node.elementType == .dialog || node.elementType == .staticText || node.elementType == .button {
                for text in [node.title, node.label, node.value as? String ?? ""] {
                    let normalized = permissionText(text)
                    if !normalized.isEmpty { result.insert(normalized) }
                }
            }
        }
        return result
    }
    private func isExactPythonNetworkRequest(_ snapshot: any XCUIElementSnapshot) -> Bool {
        let text = permissionSemantics(snapshot)
        return text.contains("Allow \"Python\" to find devices on local networks?") &&
            text.contains("This will allow the app to discover, connect to, and collect data from devices on your networks.")
    }
    private func currentPythonPermissionDialog() -> XCUIElement? {
        let system = XCUIApplication(bundleIdentifier: "com.apple.UserNotificationCenter")
        let state = system.state
        if state == .notRunning { return nil }
        guard state == .runningForeground || state == .runningBackground else {
            XCTFail("Environment blocked: cannot identify current notification process"); return nil
        }
        let dialogs = system.dialogs.allElementsBoundByIndex.filter {
            $0.exists && $0.frame.width > 0 && $0.frame.height > 0
        }
        if dialogs.isEmpty { return nil }
        guard dialogs.count == 1, let snapshot = try? dialogs[0].snapshot(),
              isExactPythonNetworkRequest(snapshot) else {
            diagnosticMacObstruction("unrecognized-permission-dialog", target: "reading.save-progress")
            XCTFail("Environment blocked: current dialog is not the unique authorized Python local-network request")
            return nil
        }
        return dialogs[0]
    }
    private func macPythonPermissionStillPending() -> Bool {
        guard "__MAC_DIAGNOSTIC__" == "1", pythonNetworkDismissalPending else { return false }
        if currentPythonPermissionDialog() != nil { return true }
        pythonNetworkDismissalPending = false
        return false
    }
    private func denyKnownPythonNetworkRequestIfPresent() {
        guard "__MAC_DIAGNOSTIC__" == "1" else { return }
        guard !macStartupFinished else { XCTFail("Permission action forbidden after startup"); return }
        guard let dialog = currentPythonPermissionDialog() else { return }
        guard !pythonNetworkDenyAttempted else {
            diagnosticMacObstruction("permission-reappeared", target: "reading.save-progress")
            XCTFail("Environment blocked: authorized permission choice already attempted; no retry")
            return
        }
        func denialButton(in current: XCUIElement) -> XCUIElement? {
            var candidates: [XCUIElement] = []
            for button in current.descendants(matching: .button).allElementsBoundByIndex {
                guard let snapshot = try? button.snapshot() else { continue }
                let semantics = permissionSemantics(snapshot)
                if semantics.contains("Don't Allow") {
                    guard semantics == Set(["Don't Allow"]) else {
                        XCTFail("Environment blocked: conflicting permission-button semantics"); return nil
                    }
                    candidates.append(button)
                }
            }
            guard candidates.count == 1 else {
                XCTFail("Environment blocked: no unique explicitly named Don't Allow button"); return nil
            }
            return candidates[0]
        }
        guard denialButton(in: dialog) != nil else { return }
        // Requery the same exact prompt and semantic candidate immediately before the native action.
        guard let freshDialog = currentPythonPermissionDialog(),
              let button = denialButton(in: freshDialog),
              button.isEnabled && button.isHittable else {
            XCTFail("Environment blocked: fresh authorized denial action is not clickable"); return
        }
        pythonNetworkDenyAttempted = true
        pythonNetworkDismissalPending = true
        print("F04_MAC_PERMISSION choice=Don't Allow request=Python-local-network once=true")
        button.click()
        // The existing caller wait retains its original deadline and observes actual dismissal.
    }
    private func restoreMacForeground(for id: String) {
        diagnosticMacObstruction("before-activate", target: id)
        // activate() would launch a stopped process with EXRFreshState: never allow that path.
        let state = app.state
        guard state == .runningForeground || state == .runningBackground else {
            XCTFail("Application no longer running; refusing activation/relaunch")
            return
        }
        app.activate()
        diagnosticMacObstruction("after-activate", target: id)
    }
    private func diagnosticMacObstruction(_ phase: String, target: String) {
        guard "__MAC_DIAGNOSTIC__" == "1" else { return }
        func sanitized(_ value: String) -> String {
            var result = value
            for secret in ["__ROOT__", "__USER__", "__PASSWORD__", "__TOKEN__"].sorted(by: { $0.count > $1.count }) {
                if !secret.isEmpty { result = result.replacingOccurrences(of: secret, with: "[redacted]") }
            }
            result = result.replacingOccurrences(of: "https?://[^\\s]+", with: "[url]", options: .regularExpression)
            result = result.replacingOccurrences(of: "[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}", with: "[account]", options: .regularExpression)
            return String(result.prefix(512))
        }
        var fields: [String: Any] = ["phase": phase, "target": target,
            "timestamp": ISO8601DateFormatter().string(from: Date()), "app_state": String(describing: app.state)]
        var own: [[String: Any]] = []
        for id in [target, "reading.list", "reading.title", "reading.editor", "reading.status",
                   "reader.status", "reader.location", "reader.busy", "reading.pending", "reading.next",
                   "reading.cancel", "account.sync.cancel", "library.title"] {
            let item = e(id)
            var row: [String: Any] = ["id": id, "exists": item.exists]
            if item.exists {
                row["enabled"] = item.isEnabled
                row["hittable"] = item.isHittable
                row["frame"] = String(describing: item.frame)
                // Only status text is retained; never text-field/editor values.
                if ["reading.status", "reader.status", "reader.location"].contains(id), let snap = try? item.snapshot() {
                    row["status"] = sanitized(snap.label.isEmpty ? (snap.value as? String ?? "") : snap.label)
                }
            }
            own.append(row)
        }
        // Public UI proxies only: no internal bookID, record bodies or editor values.
        if e("reading.list").exists, let list = try? e("reading.list").snapshot() {
            var nodes: [any XCUIElementSnapshot] = [list]
            var identifiers = Set<String>()
            var visited = 0
            while let node = nodes.popLast(), visited < 512 {
                visited += 1
                nodes.append(contentsOf: node.children)
                if node.identifier.hasPrefix("reading.kind.") ||
                   node.identifier.hasPrefix("reading.jump.") || node.identifier.hasPrefix("reading.edit.") {
                    identifiers.insert(node.identifier)
                }
            }
            fields["record_ui_identifiers"] = Array(identifiers.sorted().prefix(96))
            fields["record_ui_snapshot_nodes"] = visited
            fields["record_ui_snapshot_truncated"] = !nodes.isEmpty
        }
        fields["own"] = own
        fields["windows"] = app.windows.allElementsBoundByIndex.map { ["frame": String(describing: $0.frame)] }
        fields["sheets"] = app.sheets.allElementsBoundByIndex.map { ["frame": String(describing: $0.frame)] }
        let notificationCenter = XCUIApplication(bundleIdentifier: "com.apple.UserNotificationCenter")
        let systemState = notificationCenter.state
        fields["notification_state"] = String(describing: systemState)
        var dialogs: [[[String: String]]] = []
        if systemState == .runningForeground || systemState == .runningBackground {
            // Read only currently exposed dialogs, not notifications/history, never activate this app.
            for dialog in notificationCenter.dialogs.allElementsBoundByIndex.prefix(3) {
                guard dialog.exists, dialog.frame.width > 0, dialog.frame.height > 0,
                      let snapshot = try? dialog.snapshot() else { continue }
                var nodes: [any XCUIElementSnapshot] = [snapshot]
                var rows: [[String: String]] = []
                while let node = nodes.popLast(), rows.count < 40 {
                    if node.elementType == .textField || node.elementType == .secureTextField ||
                       node.elementType == .textView { continue }
                    nodes.append(contentsOf: node.children)
                    guard [XCUIElement.ElementType.window, .dialog, .staticText, .button].contains(node.elementType) else { continue }
                    var row = ["type": String(describing: node.elementType), "id": sanitized(node.identifier),
                               "label": sanitized(node.label), "title": sanitized(node.title), "frame": String(describing: node.frame)]
                    if node.elementType == .staticText || node.elementType == .button {
                        row["text"] = sanitized(node.value as? String ?? "")
                    }
                    rows.append(row)
                }
                dialogs.append(rows)
            }
        }
        fields["current_notification_dialogs"] = dialogs
        fields["finished_at"] = ISO8601DateFormatter().string(from: Date())
        if let bytes = try? JSONSerialization.data(withJSONObject: fields, options: [.sortedKeys]),
           let json = String(data: bytes, encoding: .utf8) { print("F04_MAC_OBSTRUCTION " + json) }
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
        #if os(macOS)
        var activationAttempted = false
        let editorReady = wait {
            if editor.exists && editor.isHittable { return true }
            if !activationAttempted {
                activationAttempted = true
                restoreMacForeground(for: "reading.editor")
            }
            return false
        }
        if !editorReady { diagnosticMacObstruction("editor-timeout", target: "reading.editor") }
        XCTAssertTrue(editorReady, "Original editor readiness not reached")
        #else
        XCTAssertTrue(wait { editor.exists && editor.isHittable })
        #endif
        #if os(macOS)
        guard macNoLatePermission(force: true) else { return }
        diagnosticMacObstruction("before-editor-input", target: "reading.editor")
        #endif
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
        #if os(macOS)
        XCTAssertTrue(macStartupReady(), "Original library readiness after bounded startup environment preparation")
        #else
        XCTAssertTrue(wait { e("library.title").exists && !e("library.busy").exists })
        #endif
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
