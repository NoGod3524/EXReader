// SPDX-License-Identifier: MIT
import XCTest

final class OrganizationUITests: XCTestCase {
    private var app: XCUIApplication!
    private var steps: [String] = []

    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication()
        steps = []
    }

    override func tearDownWithError() throws {
        let payload: [String: Any] = ["test": name, "steps": steps]
        if let data = try? JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys]),
           let value = String(data: data, encoding: .utf8) {
            let attachment = XCTAttachment(string: value)
            attachment.name = "organization-steps-\(name).json"
            attachment.lifetime = .keepAlways
            add(attachment)
        }
        let screen = XCTAttachment(screenshot: app.screenshot())
        screen.name = "organization-screen-\(name)"
        screen.lifetime = .keepAlways
        add(screen)
        app.terminate()
    }

    private func element(_ id: String) -> XCUIElement {
        app.descendants(matching: .any).matching(identifier: id).firstMatch
    }
    private func wait(_ timeout: TimeInterval = 60, _ condition: () -> Bool) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if condition() { return true }
            RunLoop.current.run(until: Date().addingTimeInterval(0.2))
        }
        return condition()
    }
    private func tapElement(_ target: XCUIElement, name: String) {
        XCTAssertTrue(target.waitForExistence(timeout: 60), "Missing \(name): \(app.debugDescription)")
        if !target.isHittable {
            let scroll = app.scrollViews.firstMatch
            if scroll.exists {
                for _ in 0..<5 where !target.isHittable {
#if os(macOS)
                    scroll.scroll(byDeltaX: 0, deltaY: -200)
#else
                    scroll.swipeUp()
#endif
                }
            }
        }
        XCTAssertTrue(wait { target.isEnabled && target.isHittable }, "Unavailable \(name): \(app.debugDescription)")
        target.tap()
    }
    private func tap(_ id: String) { tapElement(element(id), name: id) }
    private func text(_ id: String) -> String {
        guard let node = try? element(id).snapshot() else { return "" }
        return node.label.isEmpty ? (node.value as? String ?? "") : node.label
    }
    private func launch(fresh: Bool, pauseAfterStage: Bool = false, conflictReview: Bool = false) {
        app.launchEnvironment = pauseAfterStage ? ["EXR_ORGANIZATION_PAUSE_AFTER_STAGE": "1"] : [:]
        app.launchArguments = ["-EXRUITestFixtures", "1"] + (fresh ? ["-EXRFreshState", "1"] : [])
            + (conflictReview ? ["-EXROrganizationConflictReview"] : [])
        app.launch()
        XCTAssertTrue(element("library.organization").waitForExistence(timeout: 90), app.debugDescription)
        XCTAssertTrue(wait { !self.element("library.busy").exists })
    }
    private func restart() {
        app.terminate()
        XCTAssertTrue(wait(15) { self.app.state == .notRunning })
        launch(fresh: false)
        tap("library.organization")
    }
    private func enterName(_ value: String) {
        let field = element("organization.name")
        XCTAssertTrue(field.waitForExistence(timeout: 30))
        XCTAssertTrue(wait { field.isEnabled && field.isHittable }, app.debugDescription)
        field.tap()
#if os(macOS)
        field.typeKey("a", modifierFlags: .command)
        field.typeText(XCUIKeyboardKey.delete.rawValue)
#else
        let old = (field.value as? String) ?? ""
        if !old.isEmpty { field.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: old.count)) }
#endif
        field.typeText(value)
    }
    private func row(_ name: String) -> XCUIElement {
        app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@ AND label == %@", "organization.group.", name)).firstMatch
    }
    private func select(_ name: String) {
        let group = row(name)
        XCTAssertTrue(group.waitForExistence(timeout: 60), "Missing group \(name): \(app.debugDescription)")
        tapElement(group, name: name)
        XCTAssertTrue(wait { self.text("organization.selected").contains(name) }, app.debugDescription)
    }
    private func create(_ name: String) {
        tap("organization.create")
        enterName(name)
        tap("organization.save")
        XCTAssertTrue(row(name).waitForExistence(timeout: 60), app.debugDescription)
    }
    private func kind(_ value: String) { tap("organization.kind.\(value)") }
    private func book() -> XCUIElement {
        app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "organization.book.")).firstMatch
    }

    func testGroupLifecycleAndProcessRestart() {
        launch(fresh: true)
        tap("library.organization")
        kind("shelf")
        create("Acceptance Shelf")
        steps.append("created")
        select("Acceptance Shelf")
        enterName("Renamed Shelf")
        tap("organization.rename")
        XCTAssertTrue(row("Renamed Shelf").waitForExistence(timeout: 60))
        XCTAssertFalse(row("Acceptance Shelf").exists)
        steps.append("renamed")
        select("Renamed Shelf")
        tap("organization.delete")
        XCTAssertTrue(wait { !self.row("Renamed Shelf").exists })
        steps.append("deleted")
        tap("organization.removed")
        select("Renamed Shelf")
        tap("organization.restore")
        tap("organization.removed")
        XCTAssertTrue(row("Renamed Shelf").waitForExistence(timeout: 60))
        steps.append("restored")
        restart()
        kind("shelf")
        select("Renamed Shelf")
        steps.append("restart")
    }

    func testMembershipAndProcessRestart() {
        launch(fresh: true)
        tap("library.import.epub")
        XCTAssertTrue(wait(90) { !self.element("library.busy").exists && self.element("library.book.0").exists }, app.debugDescription)
        steps.append("imported")
        tap("library.organization")
        kind("shelf")
        create("Membership Shelf")
        select("Membership Shelf")
        XCTAssertTrue(book().waitForExistence(timeout: 60))
        tapElement(book(), name: "organization book")
        tap("organization.verify-original")
        XCTAssertTrue(wait { self.text("organization.message").contains("原件验证完成") }, app.debugDescription)
        XCTAssertTrue(wait { self.book().exists && self.book().isEnabled && self.book().isHittable })
        tapElement(book(), name: "organization book")
        tap("organization.add")
        XCTAssertTrue(wait { self.text("organization.membership") == "member" }, app.debugDescription)
        steps.append("added")
        restart()
        kind("shelf")
        select("Membership Shelf")
        XCTAssertTrue(book().waitForExistence(timeout: 60))
        tapElement(book(), name: "organization book")
        XCTAssertTrue(wait { self.text("organization.membership") == "member" }, app.debugDescription)
        steps.append("restart")
        tapElement(book(), name: "organization book")
        tap("organization.remove")
        XCTAssertTrue(wait { self.text("organization.membership") == "not member" }, app.debugDescription)
        steps.append("removed")
    }

    func testTagAndSeriesPersist() {
        launch(fresh: true)
        tap("library.organization")
        kind("tag")
        create("Acceptance Tag")
        steps.append("tag")
        kind("series")
        create("Acceptance Series")
        steps.append("series")
        restart()
        kind("tag")
        select("Acceptance Tag")
        kind("series")
        select("Acceptance Series")
        steps.append("restart")
    }
    func testStagedIntentSurvivesTerminationAndRetry() {
        launch(fresh: true, pauseAfterStage: true)
        tap("library.organization")
        kind("shelf")
        tap("organization.create")
        enterName("Recovered Shelf")
        tap("organization.save")
        XCTAssertTrue(element("organization.staged").waitForExistence(timeout: 60), app.debugDescription)
        steps.append("staged")
        app.terminate()
        XCTAssertTrue(wait(15) { self.app.state == .notRunning })
        launch(fresh: false)
        tap("library.organization")
        XCTAssertTrue(element("organization.retry").waitForExistence(timeout: 60), app.debugDescription)
        steps.append("reopened")
        tap("organization.retry")
        kind("shelf")
        XCTAssertTrue(row("Recovered Shelf").waitForExistence(timeout: 60), app.debugDescription)
        steps.append("retried")
        restart()
        kind("shelf")
        select("Recovered Shelf")
        steps.append("persisted")
    }

    func testNestedShelfSurvivesRestart() {
        launch(fresh: true)
        tap("library.organization")
        kind("shelf")
        create("Parent Shelf")
        select("Parent Shelf")
        tap("organization.children")
        create("Child Shelf")
        steps.append("created")
        restart()
        kind("shelf")
        select("Parent Shelf")
        tap("organization.children")
        select("Child Shelf")
        steps.append("restart")
    }

    func testStaleEditDoesNotOverwriteCompetingRevision() {
        launch(fresh: true, conflictReview: true)
        tap("library.organization")
        kind("shelf")
        create("Original Shelf")
        select("Original Shelf")
        tap("organization.review-compete")
        XCTAssertTrue(wait { self.text("organization.message").contains("竞争版本已提交") }, app.debugDescription)
        steps.append("competing")
        enterName("Stale Edit")
        tap("organization.rename")
        XCTAssertTrue(element("organization.retry").waitForExistence(timeout: 60), app.debugDescription)
        steps.append("refused")
        tap("organization.abandon")
        tap("organization.refresh")
        XCTAssertTrue(row("Concurrent Shelf").waitForExistence(timeout: 60), app.debugDescription)
        XCTAssertFalse(row("Stale Edit").exists)
        steps.append("preserved")
    }

}
