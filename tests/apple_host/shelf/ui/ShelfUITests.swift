// SPDX-License-Identifier: MIT
import XCTest
#if os(macOS)
import AppKit
#endif

final class ShelfUITests: XCTestCase {
    private var app: XCUIApplication!
    private var observations: [[String: Any]] = []
    private var lastReadDiagnostic = ""
    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication()
        observations = []
        lastReadDiagnostic = ""
        app.launchArguments = ["-EXRShelfSeed"]
        app.launch()
    }
    override func tearDownWithError() throws {
        let payload: [String: Any] = ["test": name, "observations": observations]
        if let data = try? JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys]),
           let string = String(data: data, encoding: .utf8) {
            let attachment = XCTAttachment(string: string)
            attachment.name = "shelf-observations-\(name).json"; attachment.lifetime = .keepAlways; add(attachment)
        }
        let screenshot = XCTAttachment(screenshot: app.screenshot())
        screenshot.name = "shelf-screen-\(name)"; screenshot.lifetime = .keepAlways; add(screenshot)
        app.terminate()
    }
    private func element(_ id: String) -> XCUIElement { app.descendants(matching: .any).matching(identifier: id).firstMatch }
    private func text(_ id: String) -> String {
        guard let node = try? element(id).snapshot() else { return "" }
        return node.label.isEmpty ? (node.value as? String) ?? "" : node.label
    }
    private func state() -> [String: Any]? {
        guard let root = try? element("library.shelf.state").snapshot() else { return nil }
        var nodes = [root], parts: [Int: String] = [:], count: Int?
        while let node = nodes.popLast() {
            let value = node.label.isEmpty ? (node.value as? String) ?? "" : node.label
            if node.identifier == "library.shelf.count", let parsed = Int(value) { count = parsed }
            let prefix = "library.shelf.part."
            if node.identifier.hasPrefix(prefix), let index = Int(node.identifier.dropFirst(prefix.count)), !value.isEmpty {
                if let previous = parts[index], previous != value { return nil }
                parts[index] = value
            }
            nodes.append(contentsOf: node.children)
        }
        guard let count, (1...256).contains(count), parts.count == count,
              (0..<count).allSatisfy({ parts[$0] != nil }) else {
            let detail = "SHELF AX incomplete count=\(String(describing: count)) parts=\(parts.count)"
            if detail != lastReadDiagnostic { print(detail); lastReadDiagnostic = detail }
            return nil
        }
        let raw = (0..<count).map { parts[$0]! }.joined()
        guard let data = raw.data(using: .utf8) else { return nil }
        do { return try JSONSerialization.jsonObject(with: data) as? [String: Any] }
        catch {
            let detail = "SHELF AX decode failed parts=\(count) raw_chars=\(raw.count) error=\(error) tail=\(String(raw.suffix(100)).debugDescription)"
            if detail != lastReadDiagnostic { print(detail); lastReadDiagnostic = detail }
            return nil
        }
    }
    private func wait(_ timeout: TimeInterval = 60, _ condition: () -> Bool) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if condition() { return true }
            RunLoop.current.run(until: Date().addingTimeInterval(0.15))
        }
        return condition()
    }
    private func ready(_ query: String) -> [String: Any] {
        var accepted: [String: Any] = [:], previous = ""
        var stableAt = Date()
        var polls = 0
        XCTAssertTrue(wait(120) {
            polls += 1
            let candidate = self.state()
            guard let value = candidate, value["query"] as? String == query,
                  value["loading"] as? Bool == false,
                  value["restoring_layout"] as? Bool == false,
                  value["generation"] as? Int == value["applied_generation"] as? Int,
                  let keys = value["keys"] as? [String], let visible = value["visible_keys"] as? [String],
                  keys.isEmpty || (!visible.isEmpty && !(value["top_key"] as? String ?? "").isEmpty) else {
                if polls == 1 || polls % 20 == 0 {
                    print("SHELF READY rejected decoded=\(candidate != nil) query=\(String(describing: candidate?["query"])) loading=\(String(describing: candidate?["loading"])) restoring=\(String(describing: candidate?["restoring_layout"])) gen=\(String(describing: candidate?["generation"] as? Int))/\(String(describing: candidate?["applied_generation"] as? Int)) keys=\((candidate?["keys"] as? [String])?.count ?? -1) visible=\((candidate?["visible_keys"] as? [String])?.count ?? -1) top=\(String(describing: candidate?["top_key"])) requested=\(String(describing: candidate?["requested_restore_key"])) epoch=\(String(describing: candidate?["geometry_revision"])) issued=\(String(describing: candidate?["issued_restore_revision"]))")
                    if let geometry = candidate?.filter({ ["visible_frames", "viewport_height", "requested_restore_key", "geometry_revision"].contains($0.key) }),
                       let data = try? JSONSerialization.data(withJSONObject: geometry, options: [.sortedKeys]),
                       let text = String(data: data, encoding: .utf8) { print("SHELF PENDING GEOMETRY \(text)") }
                }
                previous = ""; return false
            }
            let signature = [value["top_key"] as? String ?? "", visible.joined(separator: "|"), keys.joined(separator: "|")].joined(separator: ";")
            if polls == 1 || polls % 20 == 0 {
                print("SHELF READY eligible same_signature=\(signature == previous) stable_ms=\(Date().timeIntervalSince(stableAt) * 1000) visible=\(visible.count) keys=\(keys.count)")
            }
            if signature != previous { previous = signature; stableAt = Date() }
            accepted = value
            let settled = Date().timeIntervalSince(stableAt) >= 0.35
            if settled {
                let detail = value.filter { ["query", "top_key", "requested_restore_key", "visible_frames", "viewport_height", "generation"].contains($0.key) }
                if let data = try? JSONSerialization.data(withJSONObject: detail, options: [.sortedKeys]),
                   let text = String(data: data, encoding: .utf8) { print("SHELF SETTLED \(text)") }
            }
            return settled
        }, "Shelf did not reach a stable native layout for \(query): \(text("library.shelf.state"))")
        XCTAssertLessThanOrEqual(accepted["cached_rows"] as? Int ?? 999, 150)
        XCTAssertLessThanOrEqual(accepted["max_cached_rows"] as? Int ?? 999, 150)
        return accepted
    }
    private func record(_ id: String, _ value: [String: Any]) {
        observations.append(["id": id, "state": value, "uptime": ProcessInfo.processInfo.systemUptime])
    }
    private func search(_ query: String) {
        let field = element("library.search")
        XCTAssertTrue(field.waitForExistence(timeout: 120)); field.tap()
#if os(macOS)
        field.typeKey("a", modifierFlags: .command)
        field.typeText(XCUIKeyboardKey.delete.rawValue)
#else
        let previous = (field.value as? String) ?? ""
        if !previous.isEmpty { field.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: previous.count)) }
#endif
        if !query.isEmpty { field.typeText(query) }
        field.typeText(XCUIKeyboardKey.return.rawValue)
    }
    private func scroll(previous: Bool) {
        let list = element("library.list")
        XCTAssertTrue(list.exists)
#if os(macOS)
        list.scroll(byDeltaX: 0, deltaY: previous ? 260 : -260)
#else
        if previous { list.swipeDown(velocity: .slow) } else { list.swipeUp(velocity: .slow) }
#endif
    }
    func test01RealShelfAndBoundedInteractiveRows() {
        search("")
        let value = ready("")
        XCTAssertEqual(value["page_limit"] as? Int, 50)
        XCTAssertEqual(value["cache_limit"] as? Int, 150)
        XCTAssertGreaterThan(value["process_peak_rss_bytes"] as? Int ?? 0, 0)
        XCTAssertGreaterThan(value["shelf_created_to_first_visible_layout_ms"] as? Double ?? -1, 0)
        record("initial-real-shelf", value)
    }
    func test02ForwardTraversalOfAllOriginals() {
        search(""); var value = ready(""); var seen = Set<String>(); var gestures = 0
        repeat {
            seen.formUnion(value["keys"] as? [String] ?? [])
            if value["has_after"] as? Bool == false { break }
            gestures += 1; XCTAssertLessThan(gestures, 1200)
            scroll(previous: false); value = ready("")
        } while true
        XCTAssertEqual(seen.count, 2202)
        record("forward-every-original", ["sources": seen.count, "gestures": gestures, "last": value])
        seen = []; gestures = 0
        repeat {
            seen.formUnion(value["keys"] as? [String] ?? [])
            if value["has_before"] as? Bool == false { break }
            gestures += 1; XCTAssertLessThan(gestures, 1200)
            scroll(previous: true); value = ready("")
        } while true
        XCTAssertEqual(seen.count, 2202)
        record("reverse-every-original", ["sources": seen.count, "gestures": gestures, "first": value])
    }
    func test03StableEqualTitles() {
        search("Tie title"); var value = ready("Tie title"); var ties = Set<String>(); var gestures = 0
        repeat {
            ties.formUnion(value["keys"] as? [String] ?? [])
            if value["has_after"] as? Bool == false { break }
            gestures += 1; XCTAssertLessThan(gestures, 100); scroll(previous: false); value = ready("Tie title")
        } while true
        XCTAssertEqual(ties.count, 130)
        record("equal-titles", ["ties": ties.count, "last": value])
    }
    func test04TitleAuthorAndLiteralSearch() {
        for query in ["bOoK 0201", "Unique Shelf Author", "100%_", "no matching shelf book"] {
            search(query); let value = ready(query)
            XCTAssertEqual(value["cached_rows"] as? Int, query.hasPrefix("no matching") ? 0 : 1)
            record(query, value)
        }
    }
    func test05RapidSearchRefreshAndNativeViewport() {
        search("Tie title"); search("Book 0300"); search("Book 0201")
        let latest = ready("Book 0201"); XCTAssertEqual(latest["cached_rows"] as? Int, 1)
        search(""); _ = ready("")
        for _ in 0..<16 { scroll(previous: false); _ = ready("") }
        let before = ready(""); element("library.refresh").tap(); let after = ready("")
        XCTAssertEqual(before["top_key"] as? String, after["top_key"] as? String)
        record("refresh-keeps-source-anchor", ["before": before, "after": after, "latest": latest])
    }
    func test06RotationBackgroundAndProcessRestore() {
        search(""); _ = ready("")
        for _ in 0..<12 { scroll(previous: false); _ = ready("") }
        let before = ready("")
#if os(iOS)
        XCUIDevice.shared.orientation = .landscapeLeft
        _ = ready(""); XCUIDevice.shared.orientation = .portrait
#else
        let window = app.windows.firstMatch
        let corner = window.coordinate(withNormalizedOffset: CGVector(dx: 1, dy: 1))
        corner.press(forDuration: 0.1, thenDragTo: corner.withOffset(CGVector(dx: -100, dy: 80)))
#endif
        let resized = ready("")
        XCTAssertEqual(before["top_key"] as? String, resized["top_key"] as? String)
        app.terminate(); app.launch()
        let directlyReopened = ready("")
        XCTAssertEqual(before["top_key"] as? String, directlyReopened["top_key"] as? String)
#if os(iOS)
        XCUIDevice.shared.press(.home)
#else
        NSRunningApplication.runningApplications(withBundleIdentifier: "com.apple.finder").first?.activate(options: [])
#endif
        RunLoop.current.run(until: Date().addingTimeInterval(1))
        app.terminate(); app.launch(); let restored = ready("")
        XCTAssertEqual(before["top_key"] as? String, restored["top_key"] as? String)
        record("native-resize-and-fresh-process", ["before": before, "resized": resized,
            "direct_reopened": directlyReopened, "restored": restored])
    }
    func test07StoredOriginalReadingAndFilteredReturn() {
        search("Book 0201"); let before = ready("Book 0201")
        let buttons = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'library.book.'"))
        XCTAssertEqual(buttons.count, 1); buttons.firstMatch.tap()
        XCTAssertTrue(element("reader.page").waitForExistence(timeout: 90))
        element("reader.select").tap(); XCTAssertTrue(element("selection.all").waitForExistence(timeout: 20))
        element("selection.all").tap()
        XCTAssertTrue(wait { self.text("selection.quote").contains("Stored native shelf book 201.") })
        element("selection.close").tap(); element("reader.back").tap()
        let after = ready("Book 0201")
        XCTAssertEqual(before["keys"] as? [String], after["keys"] as? [String])
        XCTAssertEqual(after["selected_key"] as? String, (after["keys"] as? [String])?.first)
        record("stored-original-and-filtered-return", after)
    }
}
