    // SPDX-License-Identifier: MIT
    // Class-body fragment appended to a byte-checked generated copy of the
    // frozen suite. The original file is never edited or selected for execution.
    private static var probeOrder: [String] = []
    private static var probeGroups: Set<String> = []
    private var probeActivation = false
    private var probeDeadline: TimeInterval?
    private var probeRecord: [String: Any] = [:]
    private var probeTrace: [[String: Any]] = []
    private func mono() -> TimeInterval { ProcessInfo.processInfo.systemUptime }
    private func exactButton(_ id: String) -> XCUIElementQuery {
        app.buttons.matching(NSPredicate(format: "identifier == %@", id))
    }
    private func bounds(_ element: XCUIElement) -> [String: Double] {
        let r = element.frame
        return ["x": Double(r.origin.x), "y": Double(r.origin.y),
                "width": Double(r.size.width), "height": Double(r.size.height)]
    }
    private func state(_ phase: String, detailed: Bool) -> [String: Any] {
        let begin = mono()
        probeRecord["inflight_observation"] = phase
        probeRecord["observation_started"] = begin
        let target = exactButton("organization.verify-original")
        let targetCount = target.count
        let keyboards = app.keyboards
        let keyboardCount = keyboards.count
        let returns = keyboards.buttons.matching(NSPredicate(format: "identifier == %@", "Return"))
        let returnCount = returns.count
        var value: [String: Any] = ["phase": phase, "started": begin,
            "target_count": targetCount, "keyboard_count": keyboardCount, "return_count": returnCount,
            "message": label("organization.message"), "membership": label("organization.membership"),
            "selected_group": label("organization.selected"),
            "name": app.textFields.matching(identifier: "organization.name").firstMatch.value as? String ?? "",
            "ordinal": app.textFields.matching(identifier: "organization.ordinal").firstMatch.value as? String ?? ""]
        if targetCount == 1 {
            let button = target.firstMatch
            value["target_id"] = button.identifier; value["target_role"] = "Button"
            value["target_frame"] = bounds(button)
            value["target_enabled"] = button.isEnabled; value["target_hittable"] = button.isHittable
        }
        if keyboardCount == 1 { value["keyboard_frame"] = bounds(keyboards.firstMatch) }
        if returnCount == 1 {
            value["return_enabled"] = returns.firstMatch.isEnabled
            value["return_hittable"] = returns.firstMatch.isHittable
            value["return_id"] = returns.firstMatch.identifier
        }
        for id in ["organization.create", "organization.add"] {
            let query = exactButton(id)
            value[id + ".count"] = query.count
            if query.count == 1 { value[id + ".enabled"] = query.firstMatch.isEnabled }
        }
        for kind in ["group", "book"] {
            let query = exactButton(observations[kind + "_id"] ?? "")
            let count = query.count
            value[kind + "_count"] = count
            value[kind + "_id"] = count == 1 ? query.firstMatch.identifier : ""
        }
        if detailed {
            let tree = XCTAttachment(string: app.debugDescription)
            tree.name = "activation-probe-\(phase)-tree-\(name)"; tree.lifetime = .keepAlways; add(tree)
            let screen = XCTAttachment(screenshot: app.screenshot())
            screen.name = "activation-probe-\(phase)-screen-\(name)"; screen.lifetime = .keepAlways; add(screen)
        }
        value["finished"] = mono(); value["duration"] = mono() - begin
        probeTrace.append(value)
        probeRecord["inflight_observation"] = ""
        return value
    }
    private func probeNativeTap(_ element: XCUIElement) {
        // Called only by the frozen tap helper's one native-call hook.
        let count = probeRecord["native_tap_calls"] as? Int ?? 0
        probeRecord["native_tap_calls"] = count + 1
        XCTAssertEqual(count, 0, "more than one verification activation")
        probeRecord["native_tap_started"] = mono()
        element.tap()
        let returned = mono()  // The deadline is set BEFORE any post-tap query/capture.
        probeDeadline = returned + 60
        probeRecord["native_tap_returned"] = returned
        probeRecord["deadline"] = returned + 60
    }
    private func emitProbeReceipt() {
        if probeRecord.isEmpty { return }
        probeRecord["finished"] = mono()
        probeRecord["trace"] = probeTrace
        probeRecord["test"] = name
        probeRecord["observed_order"] = Self.probeOrder
        if probeRecord["outcome"] as? String == "running" { probeRecord["outcome"] = "native_failure_or_exception" }
        do {
            let data = try JSONSerialization.data(withJSONObject: probeRecord, options: [.prettyPrinted, .sortedKeys])
            let receipt = XCTAttachment(data: data, uniformTypeIdentifier: "public.json")
            receipt.name = "activation-probe-receipt-\(name).json"; receipt.lifetime = .keepAlways; add(receipt)
        } catch { XCTFail("Could not preserve diagnostic receipt: \(error)") }
    }
    private func proveFresh() {
        app.terminate()
        XCTAssertTrue(wait(15) { self.app.state == .notRunning }, "previous app did not terminate")
        probeRecord["previous_app_stopped"] = true
        launch(fresh: true)
        XCTAssertEqual(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "library.book.")).count, 0)
        probeRecord["initial_books"] = 0
        tap("library.organization")
        var counts: [String: Int] = [:]
        for kind in ["shelf", "tag", "series"] {
            tap("organization.kind." + kind)
            for showRemoved in [false, true] {
                removed(showRemoved)
                let count = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "organization.group.")).count
                XCTAssertEqual(count, 0, "fresh state has groups")
                counts[kind + (showRemoved ? ".removed" : ".active")] = count
                XCTAssertFalse(node("organization.retry").exists, "fresh state has pending work")
                XCTAssertFalse(node("organization.staged").exists, "fresh state has staged work")
            }
            removed(false)
        }
        probeRecord["initial_groups"] = counts
        tap("organization.close")
        probeRecord["initial_state_empty"] = true
    }
    private func runProbe(_ trial: String, arm: String) {
        probeRecord = ["schema": 1, "trial": trial, "arm": arm, "started": mono(),
            "product_accepted": false, "formal_credit": 0, "outcome": "running",
            "freshness_proved": false, "native_tap_calls": 0, "return_tap_calls": 0]
        Self.probeOrder.append(trial)
        proveFresh()
        tap("library.import.epub")
        XCTAssertTrue(wait(90) { !self.node("library.busy").exists && self.node("library.book.0").exists })
        XCTAssertEqual(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "library.book.")).count, 1)
        tap("library.organization"); tap("organization.kind.tag")
        let groupID = create("Mobile tag")
        XCTAssertTrue(Self.probeGroups.insert(groupID).inserted, "group ID reused across fresh trials")
        observations["group_id"] = groupID
        let books = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "organization.book."))
        XCTAssertEqual(books.count, 1, "exactly one imported fixture required")
        let bookID = books.firstMatch.identifier
        XCTAssertEqual(bookID, "organization.book.epub:0c54c6c969cb720875557d8f877d0733cc65dd1e80d74d098fb18ba65bf42bdb")
        observations["book_id"] = bookID
        chooseBook(bookID)
        XCTAssertTrue(wait { self.label("organization.message") == "书籍需要验证原件后建立历史。" })
        XCTAssertEqual(label("organization.membership"), "not member")
        probeRecord["freshness_proved"] = true
        probeRecord["group_id"] = groupID; probeRecord["book_id"] = bookID
        probeRecord["prebootstrap_proved"] = true
        let before = state("pre-intervention", detailed: true)
        XCTAssertEqual(before["group_count"] as? Int, 1)
        XCTAssertEqual(before["book_count"] as? Int, 1)
        XCTAssertEqual(before["group_id"] as? String, groupID)
        XCTAssertEqual(before["book_id"] as? String, bookID)
        probeRecord["keyboard_applicable"] = (before["keyboard_count"] as? Int == 1)
        probeRecord["return_action_started"] = mono()
        if arm == "return" {
            guard before["keyboard_count"] as? Int == 1 else {
                probeRecord["outcome"] = "inapplicable_keyboard"
                _ = state("post-intervention", detailed: true)
                XCTFail("Return comparison inapplicable: no unique keyboard"); return
            }
            guard before["return_count"] as? Int == 1,
                  before["return_id"] as? String == "Return",
                  before["return_enabled"] as? Bool == true,
                  before["return_hittable"] as? Bool == true else {
                probeRecord["outcome"] = "unsupported_return"
                _ = state("post-intervention", detailed: true)
                XCTFail("Return comparison lacks unique enabled/hittable native Return"); return
            }
            probeRecord["return_tap_calls"] = 1
            app.keyboards.buttons.matching(NSPredicate(format: "identifier == %@", "Return")).firstMatch.tap()
        }
        probeRecord["return_action_finished"] = mono()
        let after = state("post-intervention", detailed: true)
        XCTAssertEqual(after["group_count"] as? Int, 1)
        XCTAssertEqual(after["book_count"] as? Int, 1)
        for key in ["group_id", "book_id", "selected_group", "name", "ordinal"] {
            XCTAssertEqual(before[key] as? String, after[key] as? String, "Return changed \(key)")
        }
        if arm == "return" && (after["keyboard_count"] as? Int) != 0 {
            probeRecord["outcome"] = "return_did_not_dismiss"
            XCTFail("Native Return did not dismiss keyboard"); return
        }
        XCTAssertEqual(after["target_count"] as? Int, 1, "verification target ambiguous")
        probeActivation = true
        tap("organization.verify-original")
        probeActivation = false
        guard let deadline = probeDeadline else { XCTFail("native activation deadline missing"); return }
        var sample = state("post-verify", detailed: true)
        var complete = false
        var observedAt: TimeInterval?
        while true {
            let now = mono()
            if now > deadline { break }
            if (sample["message"] as? String ?? "").contains("原件验证完成") {
                complete = true; observedAt = now; break
            }
            RunLoop.current.run(until: Date().addingTimeInterval(0.2))
            if mono() >= deadline { break }
            if probeTrace.count >= 512 { XCTFail("bounded trace limit exceeded"); return }
            sample = state("poll", detailed: false)
        }
        probeRecord["completion_observed"] = complete
        probeRecord["completion_observed_at"] = observedAt ?? mono()
        probeRecord["outcome"] = complete ? "verification_completed" : "completion_window_failed"
        XCTAssertTrue(complete, "original verification completion missing within unchanged60-second window")
    }
    func test01Control() { runProbe("test01Control", arm: "control") }
    func test02Return() { runProbe("test02Return", arm: "return") }
    func test03Control() { runProbe("test03Control", arm: "control") }
    func test04Return() { runProbe("test04Return", arm: "return") }
    func test05Control() { runProbe("test05Control", arm: "control") }
    func test06Return() { runProbe("test06Return", arm: "return") }
