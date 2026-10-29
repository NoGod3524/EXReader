// SPDX-License-Identifier: MIT
import XCTest

final class IOSOrganizationAcceptanceTests: XCTestCase {
    private var app: XCUIApplication!
    private var steps: [String] = []
    private var observations: [String: String] = [:]

    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication()
    }
    override func tearDownWithError() throws {
        let payload: [String: Any] = ["test": name, "steps": steps, "observations": observations]
        let data = try JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys])
        let record = XCTAttachment(data: data, uniformTypeIdentifier: "public.json")
        record.name = "ios-organization-steps-\(name).json"; record.lifetime = .keepAlways; add(record)
        let screen = XCTAttachment(screenshot: app.screenshot())
        screen.name = "ios-organization-screen-\(name)"; screen.lifetime = .keepAlways; add(screen)
        let tree = XCTAttachment(string: app.debugDescription)
        tree.name = "ios-organization-tree-\(name).txt"; tree.lifetime = .keepAlways; add(tree)
        app.terminate()
    }
    private func node(_ id: String) -> XCUIElement {
        app.descendants(matching: .any).matching(identifier: id).firstMatch
    }
    private func wait(_ timeout: TimeInterval = 60, _ condition: () -> Bool) -> Bool {
        let until = Date().addingTimeInterval(timeout)
        repeat {
            if condition() { return true }
            RunLoop.current.run(until: Date().addingTimeInterval(0.2))
        } while Date() < until
        return condition()
    }
    private func tap(_ element: XCUIElement) {
        XCTAssertTrue(element.waitForExistence(timeout: 60), app.debugDescription)
        if !element.isHittable {
            let scroll = app.scrollViews.firstMatch
            if scroll.exists {
                for _ in 0..<5 where !element.isHittable {
                    if element.frame.midY < scroll.frame.midY { scroll.swipeDown() }
                    else { scroll.swipeUp() }
                }
            }
        }
        XCTAssertTrue(wait { element.isEnabled && element.isHittable }, app.debugDescription)
        element.tap()
    }
    private func tap(_ id: String) { tap(node(id)) }
    private func label(_ id: String) -> String { node(id).exists ? node(id).label : "" }
    private func enter(_ id: String, _ value: String) {
        let field = app.textFields.matching(identifier: id).firstMatch
        tap(field)
        let previous = field.value as? String ?? ""
        if !previous.isEmpty && previous != field.placeholderValue {
            field.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: previous.count))
        }
        field.typeText(value)
        XCTAssertEqual(field.value as? String, value, app.debugDescription)
    }
    private func launch(fresh: Bool, stage: Bool = false, compete: Bool = false) {
        app.launchEnvironment = stage ? ["EXR_ORGANIZATION_PAUSE_AFTER_STAGE": "1"] : [:]
        app.launchArguments = ["-EXRUITestFixtures", "1"] + (fresh ? ["-EXRFreshState", "1"] : [])
            + (compete ? ["-EXROrganizationConflictReview"] : [])
        app.launch()
        XCTAssertTrue(node("library.organization").waitForExistence(timeout: 90), app.debugDescription)
        XCTAssertTrue(wait { !self.node("library.busy").exists })
    }
    private func restart() {
        app.terminate()
        XCTAssertTrue(wait(15) { self.app.state == .notRunning })
        launch(fresh: false)
        tap("library.organization")
    }
    private func groups(_ name: String) -> XCUIElementQuery {
        app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@ AND label == %@", "organization.group.", name))
    }
    private func select(_ name: String, identity: String? = nil) -> String {
        let group = groups(name).firstMatch
        tap(group)
        XCTAssertEqual(groups(name).count, 1, "duplicate group")
        XCTAssertTrue(wait { self.label("organization.selected") == name })
        let id = group.identifier
        if let identity { XCTAssertEqual(id, identity, "rename/restart changed group identity") }
        return id
    }
    private func create(_ name: String) -> String {
        tap("organization.create"); enter("organization.name", name); tap("organization.save")
        XCTAssertTrue(groups(name).firstMatch.waitForExistence(timeout: 60), app.debugDescription)
        return select(name)
    }
    // SwiftUI exposes a wide labelled switch plus a nested, unlabelled native
    // UISwitch. The historical generic tap hit the label and left value 0.
    // Target the native switch itself, and fail if its state did not change.
    private func removed(_ enabled: Bool) {
        let wrapper = app.switches.matching(identifier: "organization.removed").firstMatch
        XCTAssertTrue(wrapper.waitForExistence(timeout: 30), app.debugDescription)
        let wanted = enabled ? "1" : "0"
        if wrapper.value as? String != wanted {
            let native = wrapper.descendants(matching: .switch).firstMatch
            tap(native.exists ? native : wrapper)
        }
        XCTAssertTrue(wait { wrapper.value as? String == wanted }, "Removed filter did not change: \(app.debugDescription)")
        observations[enabled ? "removed_on" : "removed_off"] = wrapper.value as? String
    }
    private func member(_ bookID: String) -> XCUIElement {
        node("organization.member." + bookID.replacingOccurrences(of: "organization.book.", with: ""))
    }
    private func chooseBook(_ id: String) { tap(id) }
    private func assertRelation(_ id: String, present: Bool, ordinal: String) {
        let row = member(id)
        XCTAssertTrue(wait { row.exists == present }, app.debugDescription)
        XCTAssertTrue(wait { self.label("organization.membership") == (present ? "member" : "not member") }, app.debugDescription)
        if present { XCTAssertTrue(row.label.hasSuffix(" · " + ordinal), row.label) }
    }
    private func lifecycle(_ kind: String) {
        launch(fresh: true)
        tap("library.import.epub")
        XCTAssertTrue(wait(90) { !self.node("library.busy").exists && self.node("library.book.0").exists })
        tap("library.organization"); tap("organization.kind." + kind)
        let original = "Mobile " + kind, renamed = "Restored " + kind
        let groupID = create(original)
        observations["kind"] = kind; observations["group_id"] = groupID
        steps.append("created")
        let books = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "organization.book."))
        XCTAssertEqual(books.count, 1, "one imported real book required")
        let bookID = books.firstMatch.identifier
        observations["book_id"] = bookID
        chooseBook(bookID); tap("organization.verify-original")
        XCTAssertTrue(wait { self.label("organization.message").contains("原件验证完成") })
        chooseBook(bookID)
        let ordinal = kind == "tag" ? "0" : "2"
        enter("organization.ordinal", ordinal); tap("organization.add")
        assertRelation(bookID, present: true, ordinal: ordinal)
        steps.append("member_added")
        restart(); tap("organization.kind." + kind)
        _ = select(original, identity: groupID); chooseBook(bookID)
        assertRelation(bookID, present: true, ordinal: ordinal)
        steps.append("member_restart")
        tap("organization.remove"); assertRelation(bookID, present: false, ordinal: ordinal)
        steps.append("member_removed")
        restart(); tap("organization.kind." + kind)
        _ = select(original, identity: groupID); chooseBook(bookID)
        XCTAssertTrue(wait { self.node("organization.restore-member").isEnabled })
        assertRelation(bookID, present: false, ordinal: ordinal)
        steps.append("member_tombstone_restart")
        enter("organization.ordinal", ordinal); tap("organization.restore-member")
        assertRelation(bookID, present: true, ordinal: ordinal)
        steps.append("member_restored")
        _ = select(original, identity: groupID)
        enter("organization.name", renamed); tap("organization.rename")
        XCTAssertTrue(groups(renamed).firstMatch.waitForExistence(timeout: 60))
        XCTAssertFalse(groups(original).firstMatch.exists)
        _ = select(renamed, identity: groupID); steps.append("renamed")
        tap("organization.delete")
        XCTAssertTrue(wait { !self.groups(renamed).firstMatch.exists })
        steps.append("group_removed")
        removed(true); _ = select(renamed, identity: groupID)
        steps.append("removed_filter_on")
        restart(); tap("organization.kind." + kind)
        XCTAssertFalse(groups(renamed).firstMatch.exists, "group tombstone lost on restart")
        removed(true); _ = select(renamed, identity: groupID)
        steps.append("group_tombstone_restart")
        tap("organization.restore")
        XCTAssertTrue(wait { !self.groups(renamed).firstMatch.exists })
        removed(false); _ = select(renamed, identity: groupID)
        chooseBook(bookID); assertRelation(bookID, present: true, ordinal: ordinal)
        steps.append("group_restored")
        restart(); tap("organization.kind." + kind)
        _ = select(renamed, identity: groupID); chooseBook(bookID)
        assertRelation(bookID, present: true, ordinal: ordinal)
        observations["final_membership"] = label("organization.membership")
        observations["final_member_label"] = member(bookID).label
        observations["ordinal"] = ordinal
        steps.append("final_restart")
    }
    func testShelfLifecycleMembershipAndRestart() { lifecycle("shelf") }
    func testTagLifecycleMembershipAndRestart() { lifecycle("tag") }
    func testSeriesLifecycleMembershipAndRestart() { lifecycle("series") }

    func testNestedShelfIdentityAndParentNavigation() {
        launch(fresh: true); tap("library.organization"); tap("organization.kind.shelf")
        let parent = create("Mobile Parent")
        tap("organization.children"); let child = create("Mobile Child")
        observations["parent_id"] = parent; observations["child_id"] = child
        XCTAssertNotEqual(parent, child); steps.append("nested_created")
        tap("organization.parent")
        XCTAssertTrue(groups("Mobile Parent").firstMatch.waitForExistence(timeout: 60))
        XCTAssertFalse(groups("Mobile Child").firstMatch.exists)
        steps.append("parent_navigation")
        restart(); tap("organization.kind.shelf")
        _ = select("Mobile Parent", identity: parent); tap("organization.children")
        _ = select("Mobile Child", identity: child)
        steps.append("nested_restart")
    }
    func testStagedIntentTerminationRetryIsIdempotent() {
        launch(fresh: true, stage: true); tap("library.organization"); tap("organization.kind.shelf")
        tap("organization.create"); enter("organization.name", "Mobile Recovered"); tap("organization.save")
        XCTAssertTrue(node("organization.staged").waitForExistence(timeout: 20))
        steps.append("staged")
        restart(); XCTAssertTrue(node("organization.retry").waitForExistence(timeout: 60))
        steps.append("pending_restart")
        tap("organization.retry")
        XCTAssertTrue(wait { !self.node("organization.retry").exists })
        let identity = select("Mobile Recovered")
        observations["group_id"] = identity; steps.append("retried_once")
        tap("organization.refresh")
        XCTAssertTrue(groups("Mobile Recovered").firstMatch.waitForExistence(timeout: 60))
        XCTAssertEqual(groups("Mobile Recovered").count, 1)
        restart(); _ = select("Mobile Recovered", identity: identity)
        XCTAssertFalse(node("organization.retry").exists)
        steps.append("single_identity_restart")
    }
    func testStaleSnapshotRejectsIndependentWriterAndSurvivesRestart() {
        launch(fresh: true, compete: true); tap("library.organization"); tap("organization.kind.shelf")
        let identity = create("Mobile Original")
        observations["group_id"] = identity
        tap("organization.review-compete")
        XCTAssertTrue(wait { self.label("organization.message").contains("竞争版本已提交") })
        steps.append("independent_writer_committed")
        enter("organization.name", "Mobile Stale Edit"); tap("organization.rename")
        XCTAssertTrue(node("organization.retry").waitForExistence(timeout: 60))
        steps.append("stale_refused")
        restart(); XCTAssertTrue(node("organization.retry").waitForExistence(timeout: 60))
        steps.append("stale_pending_restart")
        tap("organization.retry")
        XCTAssertTrue(wait { self.label("organization.message").contains("恢复未完成") })
        XCTAssertTrue(node("organization.retry").exists)
        steps.append("stale_retry_refused")
        tap("organization.abandon"); tap("organization.refresh")
        _ = select("Concurrent Shelf", identity: identity)
        XCTAssertFalse(groups("Mobile Stale Edit").firstMatch.exists)
        steps.append("competitor_preserved")
        restart(); _ = select("Concurrent Shelf", identity: identity)
        XCTAssertFalse(groups("Mobile Stale Edit").firstMatch.exists)
        XCTAssertFalse(node("organization.retry").exists)
        steps.append("competitor_restart")
    }
}
