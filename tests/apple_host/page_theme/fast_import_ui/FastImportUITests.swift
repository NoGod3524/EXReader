// SPDX-License-Identifier: MIT
import XCTest

final class FastImportUITests: XCTestCase {
    private var app: XCUIApplication!
    private var evidence: [String: Any] = [:]
    override func setUpWithError() throws {
        continueAfterFailure = false; app = XCUIApplication(); evidence = [:]
        app.launchArguments = ["-EXRUITestFixtures", "1", "-EXRFreshState", "1", "-EXRFastImportOneMainTurn"]
        if name.contains("InitializationGate") { app.launchArguments += ["-EXRHoldInitializationBeforeStart"] }
        app.launch()
    }
    override func tearDownWithError() throws {
        evidence["test"] = name
        let data = try JSONSerialization.data(withJSONObject: evidence, options: [.sortedKeys])
        let attachment = XCTAttachment(string: String(decoding: data, as: UTF8.self))
        attachment.name = "fast-import-observation.json"; attachment.lifetime = .keepAlways; add(attachment)
        app.terminate()
    }
    private func element(_ id: String) -> XCUIElement { app.descendants(matching: .any).matching(identifier: id).firstMatch }
    private func text(_ id: String) -> String {
        guard let item = try? element(id).snapshot() else { return "" }
        return item.label.isEmpty ? (item.value as? String) ?? "" : item.label
    }
    private func fast() -> [String: Any]? {
        guard let data = text("library.fast-import-state").data(using: .utf8) else { return nil }
        return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
    }
    private func gate() -> [String: Any]? {
        guard let data = text("initialization.state").data(using: .utf8) else { return nil }
        return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
    }
    private func shelf() -> [String: Any]? {
        guard let root = try? element("library.shelf.state").snapshot() else { return nil }
        var pending = [root], parts: [Int: String] = [:], count: Int?
        while let node = pending.popLast() {
            let value = node.label.isEmpty ? (node.value as? String) ?? "" : node.label
            if node.identifier == "library.shelf.count" { count = Int(value) }
            let prefix = "library.shelf.part."
            if node.identifier.hasPrefix(prefix), let index = Int(node.identifier.dropFirst(prefix.count)) { parts[index] = value }
            pending.append(contentsOf: node.children)
        }
        guard let count, (1...256).contains(count), parts.count == count,
              (0..<count).allSatisfy({ parts[$0] != nil }),
              let bytes = (0..<count).map({ parts[$0]! }).joined().data(using: .utf8) else { return nil }
        return (try? JSONSerialization.jsonObject(with: bytes)) as? [String: Any]
    }
    private func wait(_ condition: () -> Bool) -> Bool {
        let deadline = Date().addingTimeInterval(90)
        while Date() < deadline {
            if condition() { return true }
            RunLoop.current.run(until: Date().addingTimeInterval(0.15))
        }
        return condition()
    }
    private func mark(_ role: String) {
        let item = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        item.name = "fast-import-" + role; item.lifetime = .keepAlways; add(item)
    }
    func testFastOwnerImportPublishesWithoutBusyTransition() {
        XCTAssertTrue(wait {
            self.element("library.fast-import-run").isEnabled && self.shelf()?["loading"] as? Bool == false &&
                self.shelf()?["cached_rows"] as? Int == 0 && !self.element("library.busy").exists
        }, "Initial real shelf did not settle: \(app.debugDescription)")
        let initial = shelf()!; evidence["before"] = initial
        let button = element("library.fast-import-run")
        XCTAssertTrue(button.isEnabled && button.isHittable, "Real import action unavailable")
        button.tap()
        XCTAssertTrue(wait {
            self.fast()?["completed"] as? Bool == true && self.shelf()?["loading"] as? Bool == false &&
                self.element("library.book.0").exists
        }, "Committed SDK book was not published to the actual shelf: \(app.debugDescription)")
        let observed = fast()!, current = shelf()!
        evidence["fast"] = observed; evidence["after"] = current
        XCTAssertEqual(observed["observed_busy_changes"] as? Int, 0)
        XCTAssertEqual(observed["same_main_turn"] as? Bool, true)
        XCTAssertEqual(observed["sdk_books"] as? Int, 1)
        XCTAssertEqual(observed["busy"] as? Bool, false)
        XCTAssertEqual(current["cached_rows"] as? Int, 1)
        XCTAssertGreaterThan(current["generation"] as? Int ?? -1, initial["generation"] as? Int ?? -1)
        XCTAssertEqual(current["generation"] as? Int, current["applied_generation"] as? Int)
        XCTAssertFalse(element("library.error").exists)
        mark("real-committed-row")
        element("library.book.0").tap()
        XCTAssertTrue(wait { self.element("reader.page").exists && !self.element("reader.busy").exists && self.text("reader.page").contains("C00P000W00") })
        evidence["real_reader_page"] = text("reader.page")
        mark("actual-sdk-page")
    }
    func testInitializationGateHasNoEarlyImportWindow() {
        XCTAssertTrue(wait { self.gate()?["held"] as? Bool == true && self.element("library.import.epub").exists })
        let initial = gate()!; evidence["before_gate"] = initial
        XCTAssertEqual(initial["library_ready"] as? Bool, false)
        XCTAssertEqual(initial["started"] as? Bool, false)
        XCTAssertEqual(initial["busy"] as? Bool, false)
        XCTAssertEqual(initial["token"] as? Int, 0)
        XCTAssertFalse(element("library.import.epub").isEnabled)
        mark("unready-controls-disabled")
        element("initialization.try-import").tap()
        XCTAssertTrue(wait { self.gate()?["rejected_unready"] as? Int == 1 })
        let rejected = gate()!; evidence["rejected_gate"] = rejected
        XCTAssertEqual(rejected["token"] as? Int, 0)
        XCTAssertEqual(rejected["retained_ui_books"] as? Int, 0)
        XCTAssertEqual(rejected["library_ready"] as? Bool, false)
        XCTAssertEqual(rejected["busy"] as? Bool, false)
        mark("actual-backend-rejected-before-begin")
        element("initialization.release").tap()
        XCTAssertTrue(wait {
            self.gate()?["library_ready"] as? Bool == true && self.gate()?["busy"] as? Bool == false &&
                self.element("library.import.epub").isEnabled
        }, "Real SDK initialization did not publish readiness: \(app.debugDescription)")
        evidence["after_gate"] = gate()!
        element("library.import.epub").tap()
        XCTAssertTrue(wait { self.element("library.book.0").exists && !self.element("library.busy").exists })
        XCTAssertFalse(element("library.error").exists)
        mark("ordinary-first-import-visible")
        element("library.book.0").tap()
        XCTAssertTrue(wait { self.element("reader.page").exists && !self.element("reader.busy").exists && self.text("reader.page").contains("C00P000W00") })
        evidence["real_reader_page"] = text("reader.page")
        mark("ordinary-first-sdk-page")
    }
}
