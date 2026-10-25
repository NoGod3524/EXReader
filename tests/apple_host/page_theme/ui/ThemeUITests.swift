// SPDX-License-Identifier: MIT
import XCTest

final class ThemeUITests: XCTestCase {
    private var app: XCUIApplication!
    private var observations: [[String: String]] = []
    override func setUpWithError() throws { continueAfterFailure = false; app = XCUIApplication(); observations = [] }
    override func tearDownWithError() throws {
        let value: [String: Any] = ["test": name, "observations": observations]
        let data = try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])
        let attachment = XCTAttachment(string: String(decoding: data, as: UTF8.self))
        attachment.name = "theme-observations-\(name).json"; attachment.lifetime = .keepAlways; add(attachment)
        app.terminate()
    }
    private func element(_ id: String) -> XCUIElement { app.descendants(matching: .any).matching(identifier: id).firstMatch }
    private func text(_ id: String) -> String {
        guard let snapshot = try? element(id).snapshot() else { return "" }
        return snapshot.label.isEmpty ? (snapshot.value as? String) ?? "" : snapshot.label
    }
    private func wait(_ condition: () -> Bool) -> Bool {
        let end = Date().addingTimeInterval(90)
        while Date() < end { if condition() { return true }; RunLoop.current.run(until: Date().addingTimeInterval(0.15)) }
        return condition()
    }
    private func tap(_ id: String) {
        XCTAssertTrue(wait { self.element(id).exists && self.element(id).isEnabled && self.element(id).isHittable }, "Unavailable \(id): \(app.debugDescription)")
        element(id).tap()
    }
    private func mark(_ role: String) {
        observations.append(["role": role, "bitmap": text("theme.bitmap")])
        let image = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        image.name = "theme-\(role)"; image.lifetime = .keepAlways; add(image)
    }
    private func open(_ kind: String) {
        app.launchArguments = ["-EXRUITestFixtures", "1", "-EXRFreshState", "1"]
        app.launch()
        XCTAssertTrue(wait { self.element("library.title").exists && !self.element("library.busy").exists })
        tap("library.import." + kind)
        XCTAssertTrue(wait { self.element("library.book.0").exists && !self.element("library.busy").exists })
        tap("library.book.0")
        XCTAssertTrue(wait { self.element("reader.page").exists && !self.element("reader.busy").exists })
    }
    private func themes() {
#if os(iOS)
        let menu = element("reader.more"), trigger = menu.buttons.firstMatch
        XCTAssertTrue(wait { menu.exists && trigger.exists && trigger.frame.width > 0 && trigger.frame.height > 0 && self.app.windows.firstMatch.frame.contains(trigger.frame) }, "Theme menu outside window")
        trigger.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
#else
        tap("reader.more")
#endif
        XCTAssertTrue(wait { self.element("reader.theme").exists || self.app.menuItems["阅读主题"].exists || self.app.buttons["阅读主题"].exists })
        if element("reader.theme").exists { tap("reader.theme") }
        else if app.menuItems["阅读主题"].exists { app.menuItems["阅读主题"].tap() }
        else { app.buttons["阅读主题"].tap() }
        XCTAssertTrue(wait { self.element("theme.choice.original").exists && self.text("theme.bitmap").hasPrefix("original|") })
    }
    private func choice(_ value: String, corner: String? = nil) {
        tap("theme.choice." + value)
        XCTAssertTrue(wait { self.text("theme.bitmap").hasPrefix(value + "|") && (corner == nil || self.text("theme.bitmap").split(separator: "|").dropFirst().first == Substring(corner!)) }, "Theme frame not accepted: \(app.debugDescription)")
        XCTAssertEqual(element("theme.choice." + value).value as? String, "已选")
    }
    private func fields() -> [String] { text("theme.bitmap").split(separator: "|", omittingEmptySubsequences: false).map(String.init) }
    func testTextThemesPreserveNonzeroPosition() {
        open("records-text"); tap("reader.next")
        XCTAssertTrue(wait { !self.element("reader.busy").exists })
        themes(); let original = fields(); XCTAssertEqual(original.count, 5); XCTAssertGreaterThan(Int(original[3]) ?? 0, 0)
        mark("text-original")
        choice("dark", corner: "101010ff"); let dark = fields(); XCTAssertNotEqual(dark[2], original[2]); XCTAssertEqual(Array(dark[3...]), Array(original[3...])); mark("text-dark")
        choice("light", corner: "ffffffff"); XCTAssertEqual(Array(fields()[3...]), Array(original[3...])); mark("text-light")
        choice("original"); XCTAssertEqual(fields(), original); mark("text-original-roundtrip")
        tap("theme.close")
    }
    func testEPUBThemesAndNativeReachability() {
        open("epub"); themes(); let original = fields(); mark("epub-original")
        choice("dark", corner: "101010ff"); XCTAssertEqual(Array(fields()[3...]), Array(original[3...])); mark("epub-dark")
#if os(iOS)
        XCUIDevice.shared.orientation = .landscapeLeft
        if !element("theme.choice.light").isHittable { element("theme.choices").swipeUp() }
        XCTAssertTrue(wait { self.element("theme.close").isHittable && self.element("theme.choice.light").isHittable })
        mark("landscape-choices-reachable")
        XCUIDevice.shared.orientation = .portrait
#else
        XCTAssertTrue(element("theme.close").isHittable); mark("native-choices-reachable")
#endif
        choice("light", corner: "ffffffff"); mark("epub-light")
        choice("original"); mark("epub-original-roundtrip"); tap("theme.close")
    }
    func testFixedPDFAndCBZRemainOriginal() {
        for kind in ["pdf", "records-cbz"] {
            open(kind); themes(); let original = fields(); mark(kind + "-original")
            choice("dark"); let dark = fields(); XCTAssertEqual(Array(dark[1...]), Array(original[1...])); mark(kind + "-dark-original-pixels")
            choice("original"); XCTAssertEqual(fields(), original); tap("theme.close"); app.terminate()
        }
    }
    func testLiveSystemAppearance() {
        open("records-text"); themes(); choice("system", corner: "ffffffff")
        let original = fields(); mark("system-initial-light")
        tap("theme.system-dark-review")
        XCTAssertTrue(wait { self.text("theme.bitmap").hasPrefix("system|101010ff|") }, "Real OS dark notification missing")
        XCTAssertEqual(Array(fields()[3...]), Array(original[3...])); mark("system-os-dark")
        tap("theme.system-light-review")
        XCTAssertTrue(wait { self.text("theme.bitmap").hasPrefix("system|ffffffff|") }, "Real OS light notification missing")
        XCTAssertEqual(fields(), original); mark("system-os-light")
        tap("theme.close")
    }
}
