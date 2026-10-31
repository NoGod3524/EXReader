
    func test08F08ScrollMetrics() {
        search("")
        _ = ready("")
        let options = XCTMeasureOptions()
        options.iterationCount = 5
        options.invocationOptions = [.manuallyStop]
        measure(metrics: [XCTOSSignpostMetric.scrollingAndDecelerationMetric,
                          XCTMemoryMetric(application: app)], options: options) {
            for _ in 0..<10 { scroll(previous: false) }
            stopMeasuring()
            for _ in 0..<10 { scroll(previous: true) }
            _ = ready("")
        }
        record("f08-scroll-metrics", ready(""))
    }

// F08_STANDALONE_CLASSES

final class F08LaunchUITests: XCTestCase {
    private var app: XCUIApplication!
    private var samples: [[String: Any]] = []
    override func setUpWithError() throws {
        continueAfterFailure = false; app = XCUIApplication(); samples = []
        app.launchArguments = ["-EXRShelfSeed", "-EXRFreshState", "1", "-EXRF08Launch"]
    }
    override func tearDownWithError() throws {
        let data = try JSONSerialization.data(withJSONObject: ["test": name, "samples": samples], options: [.sortedKeys])
        let attachment = XCTAttachment(string: String(decoding: data, as: UTF8.self))
        attachment.name = "f08-launch-observations"; attachment.lifetime = .keepAlways; add(attachment)
        app?.terminate()
    }
    private func shelf() -> [String: Any]? {
        let element = app.descendants(matching: .any).matching(identifier: "library.shelf.state").firstMatch
        guard let root = try? element.snapshot() else { return nil }
        var nodes = [root], parts: [Int: String] = [:], count: Int?
        while let node = nodes.popLast() {
            let value = node.label.isEmpty ? (node.value as? String) ?? "" : node.label
            if node.identifier == "library.shelf.count" { count = Int(value) }
            if node.identifier.hasPrefix("library.shelf.part."), let index = Int(node.identifier.dropFirst("library.shelf.part.".count)) { parts[index] = value }
            nodes.append(contentsOf: node.children)
        }
        guard let count, count > 0, count <= 256, parts.count == count,
              (0..<count).allSatisfy({ parts[$0] != nil }),
              let data = (0..<count).map({ parts[$0]! }).joined().data(using: .utf8) else { return nil }
        return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
    }
    private func ready() -> [String: Any] {
        let end = Date().addingTimeInterval(30)
        while Date() < end {
            if let value = shelf(), value["query"] as? String == "", value["loading"] as? Bool == false,
               value["restoring_layout"] as? Bool == false, value["generation"] as? Int == value["applied_generation"] as? Int,
               value["f08_launch_task_status"] as? String == "finished",
               let visible = value["visible_keys"] as? [String], !visible.isEmpty,
               !(value["top_key"] as? String ?? "").isEmpty {
                let field = app.descendants(matching: .any).matching(identifier: "library.search").firstMatch
                if field.exists && field.isEnabled && field.isHittable { return value }
            }
            RunLoop.current.run(until: Date().addingTimeInterval(0.05))
        }
        XCTFail("Native shelf launch task did not finish: \(String(describing: shelf()))")
        return [:]
    }
    private func launchMetric(responsive: Bool) {
        let options = XCTMeasureOptions(); options.iterationCount = 5; options.invocationOptions = [.manuallyStop]
        measure(metrics: [XCTApplicationLaunchMetric(waitUntilResponsive: responsive), XCTClockMetric()], options: options) {
            app.launch()
            let value = ready()
            stopMeasuring()
            samples.append(["native_wait_until_responsive": responsive, "shelf": value,
                "scope": "fresh process and fresh copy of the frozen 2202-original library; XCTest clock includes launch/quiescence/AX polling"])
            let screen = XCTAttachment(screenshot: app.screenshot()); screen.name = "f08-launch-ready"; screen.lifetime = .keepAlways; add(screen)
            app.terminate()
            XCTAssertTrue(app.wait(for: .notRunning, timeout: 15))
        }
    }
    func test09NativeExtendedLaunchThroughShelfReady() { launchMetric(responsive: false) }
    func test10NativeResponsiveLaunchAndShelfUpperBound() { launchMetric(responsive: true) }
}

final class F08ReaderUITests: XCTestCase {
    private var app: XCUIApplication!
    private var samples: [[String: Any]] = []
    override func setUpWithError() throws {
        continueAfterFailure = false; app = XCUIApplication(); samples = []
        app.launchArguments = ["-EXRShelfSeed", "-EXRFreshState", "1", "-EXRUITestFixtures", "1"]
        app.launch()
    }
    override func tearDownWithError() throws {
        let data = try JSONSerialization.data(withJSONObject: ["test": name, "samples": samples], options: [.sortedKeys])
        let attachment = XCTAttachment(string: String(decoding: data, as: UTF8.self))
        attachment.name = "f08-reader-observations"; attachment.lifetime = .keepAlways; add(attachment)
        app?.terminate()
    }
    private func node(_ id: String) -> XCUIElement { app.descendants(matching: .any).matching(identifier: id).firstMatch }
    private func text(_ id: String) -> String {
        guard let value = try? node(id).snapshot() else { return "" }
        return value.label.isEmpty ? (value.value as? String) ?? "" : value.label
    }
    private func wait(_ condition: () -> Bool) -> Bool {
        let end = Date().addingTimeInterval(60)
        while Date() < end { if condition() { return true }; RunLoop.current.run(until: Date().addingTimeInterval(0.1)) }
        return condition()
    }
    private func tap(_ id: String) {
        if id.hasPrefix("reader."), id != "reader.tools.toggle", !node(id).isHittable, node("reader.tools.toggle").exists,
           !node("reader.tools.scroll").exists { node("reader.tools.toggle").tap() }
#if os(iOS)
        if id.hasPrefix("reader."), node("reader.tools.scroll").exists {
            for _ in 0..<8 { if node(id).isHittable { break }; node("reader.tools.scroll").swipeLeft(velocity: .slow) }
            for _ in 0..<8 { if node(id).isHittable { break }; node("reader.tools.scroll").swipeRight(velocity: .slow) }
        }
#endif
        XCTAssertTrue(wait { self.node(id).exists && self.node(id).isEnabled && self.node(id).isHittable }, "Unavailable \(id): \(app.debugDescription)")
        node(id).tap()
    }
    private func reader() -> [String: Any] {
        XCTAssertTrue(wait { self.node("reader.page").exists && !self.node("reader.busy").exists && !self.node("reader.error").exists })
        guard let value = try? node("reader.page").snapshot(), let raw = value.value as? String,
              let data = raw.data(using: .utf8), let result = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] else { XCTFail("Reader bitmap observation missing"); return [:] }
        XCTAssertEqual((result["bitmap_sha256"] as? String)?.count, 64)
        XCTAssertGreaterThan(result["sdk_frame_count"] as? Int ?? 0, 0)
        return result
    }
    private func openShelf(_ query: String) {
        XCTAssertTrue(wait { self.node("library.search").exists && !self.node("library.busy").exists })
        let field = node("library.search"); field.tap()
#if os(macOS)
        field.typeKey("a", modifierFlags: .command); field.typeText(XCUIKeyboardKey.delete.rawValue)
#else
        let previous = field.value as? String ?? ""; if !previous.isEmpty { field.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: previous.count)) }
#endif
        field.typeText(query); field.typeText(XCUIKeyboardKey.return.rawValue)
        let books = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'library.book.'"))
        XCTAssertTrue(wait { books.count == 1 && books.firstMatch.isHittable && self.text("library.status").isEmpty == false })
        books.firstMatch.tap(); _ = reader()
    }
    private func nativeMetrics() -> [XCTMetric] {
        var metrics: [XCTMetric] = [XCTClockMetric(), XCTMemoryMetric(application: app)]
        if #available(macOS 26, iOS 26, *) { metrics.append(XCTHitchMetric(application: app)) }
        return metrics
    }
    private func locate(_ query: String) {
        tap("reader.search"); tap("search.query"); let field = node("search.query")
        let previous = field.value as? String ?? ""
#if os(macOS)
        field.typeKey("a", modifierFlags: .command); field.typeText(XCUIKeyboardKey.delete.rawValue)
#else
        if !previous.isEmpty { field.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: previous.count)) }
#endif
        field.typeText(query); tap("search.find")
        let hits = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'search.hit.'"))
        XCTAssertTrue(wait { hits.count == 1 && self.text("search.status").contains("已查找完毕") })
        hits.firstMatch.tap()
        XCTAssertTrue(wait { !self.node("search.query").exists && !self.node("reader.busy").exists && self.text("reader.page").contains(query) })
        XCTAssertFalse(node("reader.error").exists)
    }
    func test11FrozenOriginalFontAndLocateMetrics() {
        openShelf("Book 0201")
        XCTAssertTrue(text("reader.page").contains("Stored native shelf book 201."))
        let options = XCTMeasureOptions(); options.iterationCount = 5
        measure(metrics: nativeMetrics(), options: options) {
            let before = reader(); tap("reader.font.increase"); let larger = reader()
            XCTAssertEqual(larger["font_size"] as? Int, (before["font_size"] as? Int ?? 0) + 2)
            XCTAssertNotEqual(larger["bitmap_sha256"] as? String, before["bitmap_sha256"] as? String)
            tap("reader.font.decrease"); let restored = reader(); locate("Offline")
            let located = reader()
            XCTAssertEqual(restored["font_size"] as? Int, before["font_size"] as? Int)
            XCTAssertGreaterThan(located["sdk_frame_count"] as? Int ?? 0, before["sdk_frame_count"] as? Int ?? 0)
            samples.append(["cohort": "frozen-2202", "before": before, "larger": larger, "restored": restored, "located": located,
                "page_turn_coverage": false, "body_scroll_coverage": false,
                "reason": "The frozen originals contain one short page. The product reader displays paged bitmaps rather than a body scroll view."])
        }
    }
    func test12LongReaderPageFontAndLocateDiagnostic() {
        XCTAssertTrue(wait { self.node("library.import.epub").exists && !self.node("library.busy").exists })
        tap("library.import.epub")
        XCTAssertTrue(wait { !self.node("library.busy").exists && self.text("library.status").contains("已导入") })
        openShelf("Sample")
        tap("reader.first"); let initial = reader()
        XCTAssertTrue(text("reader.page").contains("C00P000W00"))
        let options = XCTMeasureOptions(); options.iterationCount = 5; options.invocationOptions = [.manuallyStop]
        measure(metrics: nativeMetrics(), options: options) {
            let before = reader(); tap("reader.next"); let next = reader()
            XCTAssertNotEqual(next["location"] as? String, before["location"] as? String)
            XCTAssertNotEqual(next["bitmap_sha256"] as? String, before["bitmap_sha256"] as? String)
            tap("reader.font.increase"); let larger = reader(); tap("reader.font.decrease"); let restored = reader()
            locate("C00P040W00"); let located = reader()
            XCTAssertNotEqual(located["location"] as? String, initial["location"] as? String)
            stopMeasuring()
            samples.append(["cohort": "diagnostic-2202-plus-Sample.epub", "frozen_cohort_acceptance": false,
                "before": before, "next": next, "larger": larger, "restored": restored, "located": located])
            tap("reader.first"); _ = reader()
        }
    }
}
