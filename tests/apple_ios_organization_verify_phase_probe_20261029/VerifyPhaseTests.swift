    // SPDX-License-Identifier: MIT
    // Class-body fragment. Frozen helpers/old cases are copied but not selected.
    private var phaseTapArmed = false
    private var phaseWaitStarted: UInt64 = 0, phaseWaitReturned: UInt64 = 0
    private var phaseTapStarted: UInt64 = 0, phaseTapReturned: UInt64 = 0
    private var phaseTapCalls = 0, phaseLost = 0
    private var phaseStarted: UInt64 = 0
    private var phaseAssertionReturned = false
    private var phaseLastLabel = ""
    private var phasePredicates: [[String: Any]] = []
    private var phaseNonce = "", phaseSecret = "", phaseCase = "", phaseEndpoint = ""
    private var phaseTransportProblems: [String] = []
    private var phaseClock: [String: Any] {
        var value = mach_timebase_info_data_t(); mach_timebase_info(&value)
        return ["name": "mach_absolute_time", "numer": value.numer, "denom": value.denom]
    }
    private func phaseConfigureLaunch() {
        let env = ProcessInfo.processInfo.environment
        phaseStarted = mach_absolute_time()
        phaseNonce = env["EXR_PHASE_NONCE"] ?? ""
        phaseSecret = env["EXR_PHASE_SECRET"] ?? ""
        phaseCase = env["EXR_PHASE_CASE"] ?? ""
        phaseEndpoint = env["EXR_PHASE_ENDPOINT"] ?? ""
        for key in ["EXR_PHASE_NONCE", "EXR_PHASE_SECRET", "EXR_PHASE_CASE", "EXR_PHASE_ENDPOINT"] {
            app.launchEnvironment[key] = env[key] ?? ""
        }
    }
    private func phaseNativeTap(_ element: XCUIElement) {
        phaseTapCalls += 1
        phaseTapStarted = mach_absolute_time()
        element.tap() // sole original native call; no network or extra AX query
        phaseTapReturned = mach_absolute_time()
    }
    private func phaseLabel(_ value: String) -> String {
        phaseLastLabel = value
        return value // unchanged full value goes to the original contains()
    }
    private func phaseWaitResult(_ value: Bool) -> Bool {
        phaseWaitReturned = mach_absolute_time()
        return value // observe return before XCTAssertTrue can stop a failed case
    }
    private func phasePredicate(_ original: () -> Bool) -> Bool {
        let begin = mach_absolute_time()
        phaseLastLabel = ""
        let result = original() // exactly one original predicate evaluation
        let end = mach_absolute_time()
        if phasePredicates.count < 512 {
            let prefix = Array(phaseLastLabel.utf8.prefix(129))
            phasePredicates.append(["begin": begin, "end": end, "result": result,
                "message": String(decoding: prefix.prefix(128), as: UTF8.self), "message_truncated": prefix.count > 128])
        } else { phaseLost += 1 }
        return result
    }

    private final class PhaseNoRedirect: NSObject, URLSessionTaskDelegate {
        func urlSession(_ session: URLSession, task: URLSessionTask,
                        willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest,
                        completionHandler: @escaping (URLRequest?) -> Void) { completionHandler(nil) }
    }
    // Used only by preflight and post-outcome teardown, never by the prefix loop.
    private func phaseRequest(_ path: String, _ value: [String: Any], timeout: TimeInterval = 2) -> [String: Any]? {
        guard phaseSecret.count == 64, phaseNonce.count == 32,
              let base = URL(string: phaseEndpoint), base.scheme == "http", base.host == "127.0.0.1",
              base.port != nil, base.user == nil, base.password == nil,
              base.query == nil, base.fragment == nil, base.path.isEmpty || base.path == "/",
              let body = try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]), body.count <= 256 * 1024 else { return nil }
        let key = SymmetricKey(data: Data(phaseSecret.utf8))
        let auth = HMAC<SHA256>.authenticationCode(for: body, using: key).map { String(format: "%02x", $0) }.joined()
        var request = URLRequest(url: base.appendingPathComponent(path))
        request.httpMethod = "POST"; request.httpBody = body; request.timeoutInterval = timeout
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(auth, forHTTPHeaderField: "X-Phase-Mac")
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = timeout; config.timeoutIntervalForResource = timeout
        config.waitsForConnectivity = false; config.connectionProxyDictionary = [:]
        config.urlCache = nil; config.httpCookieStorage = nil
        let session = URLSession(configuration: config, delegate: PhaseNoRedirect(), delegateQueue: nil)
        let semaphore = DispatchSemaphore(value: 0)
        // Callback storage is protected and never read while an incomplete callback writes.
        let box = PhaseResponseBox()
        let task = session.dataTask(with: request) { data, response, error in
            defer { semaphore.signal() }
            guard error == nil, let data, data.count <= 4096,
                  let http = response as? HTTPURLResponse, http.statusCode == 200 else { return }
            let expected = HMAC<SHA256>.authenticationCode(for: data, using: key).map { String(format: "%02x", $0) }.joined()
            guard http.value(forHTTPHeaderField: "X-Phase-Mac") == expected,
                  let answer = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
                  answer["nonce"] as? String == self.phaseNonce else { return }
            box.lock.lock(); box.value = answer; box.lock.unlock()
        }
        task.resume()
        let completed = semaphore.wait(timeout: .now() + timeout) == .success
        if !completed { task.cancel() }
        session.invalidateAndCancel()
        guard completed else { return nil }
        box.lock.lock(); defer { box.lock.unlock() }
        return box.value
    }
    private final class PhaseResponseBox {
        let lock = NSLock()
        var value: [String: Any]?
    }
    private func phaseReceipt() -> [String: Any] {
        ["schema": 1, "trial": phaseCase, "test": name, "nonce": phaseNonce,
         "source_sha": ProcessInfo.processInfo.environment["EXR_PHASE_SOURCE"] ?? "",
         "simulator_udid": ProcessInfo.processInfo.environment["SIMULATOR_UDID"] ?? "",
         "clock": phaseClock, "started": phaseStarted, "finished": mach_absolute_time(),
         "native_tap_calls": phaseTapCalls, "native_tap_started": phaseTapStarted,
         "native_tap_returned": phaseTapReturned, "original_wait_started": phaseWaitStarted,
         "original_wait_returned": phaseWaitReturned, "original_assertion_returned": phaseAssertionReturned,
         "predicates": phasePredicates, "lost": phaseLost, "observations": observations,
         "product_accepted": false, "formal_credit": 0]
    }
    private func phaseFinish() {
        if phaseNonce.isEmpty { return }
        let start = ProcessInfo.processInfo.systemUptime
        let deadline = start + 10
        var receipt = phaseReceipt()
        let requested = phaseRequest("seal", ["nonce": phaseNonce, "ui": receipt]) != nil
        var sealed = false
        if requested {
            while ProcessInfo.processInfo.systemUptime < deadline {
                let remaining = deadline - ProcessInfo.processInfo.systemUptime
                if remaining <= 0 { break }
                if let answer = phaseRequest("status", ["nonce": phaseNonce], timeout: min(2, remaining)),
                   answer["sealed"] as? Bool == true { sealed = true; break }
                if ProcessInfo.processInfo.systemUptime >= deadline { break }
                Thread.sleep(forTimeInterval: min(0.1, deadline - ProcessInfo.processInfo.systemUptime))
            }
        }
        receipt["seal_request_accepted"] = requested; receipt["seal_observed"] = sealed
        receipt["capture_finalization_seconds"] = ProcessInfo.processInfo.systemUptime - start
        receipt["capture_problems"] = phaseTransportProblems
        // A missing capture seal does not rewrite the original assertion outcome.
        // The independent collector rejects capture completeness instead.
        if let bytes = try? JSONSerialization.data(withJSONObject: receipt, options: [.sortedKeys]) {
            let attachment = XCTAttachment(data: bytes, uniformTypeIdentifier: "public.json")
            attachment.name = "verify-phase-ui-receipt-\(phaseCase).json"
            attachment.lifetime = .keepAlways; add(attachment)
        }
    }
    private func phaseTag() {
        let kind = "tag"
/* ORIGINAL_TAG_PREFIX */
        phaseAssertionReturned = true
    }
    func test00Transport() {
        launch(fresh: true)
        // Only this isolated preflight may wait for a transport beacon.
        let deadline = ProcessInfo.processInfo.systemUptime + 15
        var ready = false
        while ProcessInfo.processInfo.systemUptime < deadline {
            let remaining = deadline - ProcessInfo.processInfo.systemUptime
            if remaining <= 0 { break }
            if let answer = phaseRequest("status", ["nonce": phaseNonce], timeout: min(2, remaining)),
               answer["ready"] as? Bool == true { ready = true; break }
            if ProcessInfo.processInfo.systemUptime >= deadline { break }
            Thread.sleep(forTimeInterval: min(0.1, deadline - ProcessInfo.processInfo.systemUptime))
        }
        XCTAssertTrue(ready, "isolated app event transport preflight incomplete")
    }
    func test01TagPrefix() { phaseTag() }
    func test02TagPrefix() { phaseTag() }
    func test03TagPrefix() { phaseTag() }
