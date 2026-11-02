// Candidate-only, exact current-app XCUI observations; not an OS-wide AX tree.
import XCTest

final class G16ProductionEvidenceUITests: XCTestCase {
    private var app: XCUIApplication!
    private var records: [[String: Any]] = []
    private let session = UUID().uuidString

    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication()
    }

    override func tearDownWithError() throws {
        let data = try JSONSerialization.data(withJSONObject: records, options: [.sortedKeys])
        let attachment = XCTAttachment(data: data, uniformTypeIdentifier: "public.json")
        attachment.name = "g16-production-evidence.json"
        attachment.lifetime = .keepAlways
        add(attachment)
        app.terminate()
    }

    private func element(_ id: String) -> XCUIElement {
        app.descendants(matching: .any).matching(identifier: id).firstMatch
    }

    private func wait(_ timeout: TimeInterval, _ condition: () -> Bool) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if condition() { return true }
            RunLoop.current.run(until: Date().addingTimeInterval(0.1))
        }
        return condition()
    }

    private func capture(_ state: String, _ id: String, anchor: String) throws -> Int {
        XCTAssertEqual(app.state, .runningForeground)
        XCTAssertTrue(element(anchor).exists)
        let query = app.descendants(matching: .any).matching(identifier: id)
        let count = query.count
        var nodes: [[String: Any]] = []
        if count <= 4 {
            for i in 0..<count {
                let node = try query.element(boundBy: i).snapshot()
                nodes.append(["id": node.identifier, "role_raw": node.elementType.rawValue,
                              "is_static_text": node.elementType == .staticText,
                              "label": node.label, "value": node.value as? String ?? "",
                              "value_is_string": node.value is String])
            }
        }
        let record: [String: Any] = [
            "schema": 1, "session": session, "case": "testProductionG16Evidence",
            "state": state, "target_id": id, "query_count": count,
            "query_completed": true, "nodes_truncated": count > 4,
            "scope": "current-app XCUI descendants matching exact identifier",
            "anchor_id": anchor, "anchor_exists": element(anchor).exists,
            "app_foreground": app.state == .runningForeground,
            "captured_at": Date().timeIntervalSince1970, "nodes": nodes,
            "acceptance_eligible": false
        ]
        records.append(record)
        let bytes = try JSONSerialization.data(withJSONObject: record, options: [.sortedKeys])
        print("F09_G16_EXACT_QUERY " + String(decoding: bytes, as: UTF8.self))
        XCTAssertLessThanOrEqual(count, 4, "Ambiguous or oversized exact query")
        return count
    }

    func testProductionG16Evidence() throws {
        app.launchArguments = ["-EXRUITestFixtures", "1", "-EXRFreshState", "1"]
        app.launch()
        XCTAssertTrue(element("library.organization").waitForExistence(timeout: 90))
        XCTAssertTrue(element("library.empty").waitForExistence(timeout: 30))
        XCTAssertTrue(wait(60) { !self.element("library.busy").exists })
        let emptyCount = try capture("library.empty", "library.empty", anchor: "library.organization")
        XCTAssertEqual(emptyCount, 1)
        let empty = try element("library.empty").snapshot()
        XCTAssertEqual(empty.elementType, .staticText)
        let label = empty.label
        let name = label.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            ? (empty.value as? String ?? "") : label
        XCTAssertEqual(name.trimmingCharacters(in: .whitespacesAndNewlines),
                       "\u{4e66}\u{67b6}\u{4e3a}\u{7a7a}\u{ff0c}\u{6253}\u{5f00}\u{6587}\u{4ef6}\u{5373}\u{53ef}\u{5bfc}\u{5165}\u{3002}")
        let importButton = element("library.import.epub")
        XCTAssertTrue(importButton.waitForExistence(timeout: 30))
        XCTAssertTrue(importButton.isEnabled && importButton.isHittable)
        importButton.tap()
        XCTAssertTrue(wait(90) {
            !self.element("library.busy").exists && self.element("library.book.0").exists
        })
        let book = element("library.book.0")
        XCTAssertTrue(book.isEnabled && book.isHittable)
        book.tap()
        XCTAssertTrue(element("reader.page").waitForExistence(timeout: 90))
        XCTAssertTrue(wait(60) { !self.element("reader.busy").exists })
        RunLoop.current.run(until: Date().addingTimeInterval(1))
        XCTAssertTrue(element("reader.page").exists && !element("reader.busy").exists)
        let stateCount = try capture("reader.epub", "reader.state", anchor: "reader.page")
        XCTAssertEqual(stateCount, 0)
    }
}
