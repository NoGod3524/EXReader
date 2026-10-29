// SPDX-License-Identifier: MIT
// Generated diagnostic target only. No product handle or UI state is changed.
import Foundation
import CryptoKit
import Darwin
import Synchronization

private struct PhaseEvent {
    var seq: UInt64 = 0, tick: UInt64 = 0, kind: UInt64 = 0
    var owner: UInt64 = 0, op: UInt64 = 0, parent: UInt64 = 0
    var a: Int64 = 0, b: Int64 = 0, c: Int64 = 0
    var json: [String: Any] {
        ["seq": seq, "tick": tick, "kind": kind, "owner": owner, "op": op,
         "parent": parent, "a": a, "b": b, "c": c]
    }
    var bytes: Data {
        var data = Data()
        for value in [seq, tick, kind, owner, op, parent,
                      UInt64(bitPattern: a), UInt64(bitPattern: b), UInt64(bitPattern: c)] {
            var big = value.bigEndian
            withUnsafeBytes(of: &big) { data.append(contentsOf: $0) }
        }
        return data
    }
}

@available(iOS 18.0, macOS 15.0, *)
private final class PhaseRing {
    let lock = NSLock()
    let lost = Atomic<UInt64>(0), active = Atomic<UInt64>(0), outside = Atomic<UInt64>(0)
    let cutoff = Atomic<UInt64>(0), closed = Atomic<Bool>(false), operations = Atomic<UInt64>(0)
    private let capacity: Int
    private let storage: UnsafeMutablePointer<PhaseEvent>
    private var count = 0
    private var appendTicks: UInt64 = 0, maxAppendTicks: UInt64 = 0

    init(capacity: Int = 512) {
        self.capacity = capacity
        storage = .allocate(capacity: capacity)
        storage.initialize(repeating: PhaseEvent(), count: capacity)
    }
    deinit { storage.deinitialize(count: capacity); storage.deallocate() }

    func operation() -> UInt64 {
        let value = operations.wrappingAdd(1, ordering: .sequentiallyConsistent).newValue
        if value == 0 || value > 128 { lost.wrappingAdd(1, ordering: .sequentiallyConsistent) }
        return value
    }
    func append(_ kind: UInt64, owner: UInt64 = 0, op: UInt64 = 0,
                parent: UInt64 = 0, a: Int64 = 0, b: Int64 = 0, c: Int64 = 0) {
        guard beginAdmission() else { return }
        recordAdmitted(mach_absolute_time(), kind: kind, owner: owner, op: op, parent: parent, a: a, b: b, c: c)
    }
    private func beginAdmission() -> Bool {
        active.wrappingAdd(1, ordering: .sequentiallyConsistent)
        // Admission is decided before sampling the clock. Already-closed calls
        // cannot append, even when consecutive mach ticks would compare equal.
        if closed.load(ordering: .sequentiallyConsistent) {
            outside.wrappingAdd(1, ordering: .sequentiallyConsistent)
            active.wrappingSubtract(1, ordering: .sequentiallyConsistent)
            return false
        }
        return true
    }
    private func recordAdmitted(_ tick: UInt64, kind: UInt64, owner: UInt64 = 0, op: UInt64 = 0,
                                parent: UInt64 = 0, a: Int64 = 0, b: Int64 = 0, c: Int64 = 0) {
        defer { active.wrappingSubtract(1, ordering: .sequentiallyConsistent) }
        // Exactly one try, never a spin or blocking acquisition on product work.
        guard lock.try() else { lost.wrappingAdd(1, ordering: .sequentiallyConsistent); return }
        defer { lock.unlock() }
        guard count < capacity else { lost.wrappingAdd(1, ordering: .sequentiallyConsistent); return }
        storage[count] = PhaseEvent(seq: UInt64(count), tick: tick, kind: kind,
            owner: owner, op: op, parent: parent, a: a, b: b, c: c)
        count += 1
        let elapsed = mach_absolute_time() - tick
        appendTicks &+= elapsed; maxAppendTicks = max(maxAppendTicks, elapsed)
    }
    func close() {
        if closed.load(ordering: .sequentiallyConsistent) { return }
        // Called on the one sender queue. Publish cutoff before closing admission.
        cutoff.store(mach_absolute_time(), ordering: .sequentiallyConsistent)
        closed.store(true, ordering: .sequentiallyConsistent)
    }
    func snapshot() -> ([PhaseEvent], [String: Any])? {
        let sealing = closed.load(ordering: .sequentiallyConsistent)
        if sealing && active.load(ordering: .sequentiallyConsistent) != 0 { return nil }
        guard lock.try() else { return nil }
        let values = Array(UnsafeBufferPointer(start: storage, count: count))
        let stats: [String: Any] = ["lost": lost.load(ordering: .sequentiallyConsistent),
            "operations": operations.load(ordering: .sequentiallyConsistent), "sealed": sealing,
            "cutoff": cutoff.load(ordering: .sequentiallyConsistent),
            "outside_calls": outside.load(ordering: .sequentiallyConsistent),
            "append_ticks_total": appendTicks, "append_ticks_max": maxAppendTicks]
        lock.unlock()
        return (values, stats)
    }
    static func selfChecks() -> [String: Bool] {
        let a = PhaseRing(capacity: 2)
        a.append(0); a.append(1); a.append(2)
        let one = a.snapshot()!
        let order = one.0.map(\.seq) == [0, 1] && one.0.map(\.kind) == [0, 1]
        let overflow = a.lost.load(ordering: .sequentiallyConsistent) == 1
        let b = PhaseRing(capacity: 2)
        b.lock.lock(); b.append(0); b.lock.unlock()
        let contention = b.lost.load(ordering: .sequentiallyConsistent) == 1 && b.snapshot()!.0.isEmpty
        let c = PhaseRing(capacity: 4)
        c.append(0)
        let admitted = DispatchSemaphore(value: 0), release = DispatchSemaphore(value: 0)
        let finished = DispatchSemaphore(value: 0)
        DispatchQueue(label: "org.exreader.diagnostic.cutoff-self-check").async {
            guard c.beginAdmission() else { admitted.signal(); finished.signal(); return }
            let tick = mach_absolute_time()
            admitted.signal()
            // Only this isolated self-check thread pauses. Product append uses
            // the same admission/record helpers with no barrier or wait.
            if release.wait(timeout: .now() + 2) != .success {
                c.lost.wrappingAdd(1, ordering: .sequentiallyConsistent)
            }
            c.recordAdmitted(tick, kind: 1)
            finished.signal()
        }
        let entered = admitted.wait(timeout: .now() + 2) == .success
        c.close()
        let held = c.snapshot() == nil
        release.signal()
        let ended = finished.wait(timeout: .now() + 2) == .success
        let final = c.snapshot()
        // Exercise the real closed-admission gate with an equal-cutoff record
        // that would be supplied if admitted; no clock injection in real paths.
        let equalWasAdmitted = c.beginAdmission()
        if equalWasAdmitted { c.recordAdmitted(c.cutoff.load(ordering: .sequentiallyConsistent), kind: 2) }
        c.append(3)
        let after = c.snapshot()
        return ["append_order_no_overwrite": order, "overflow_loss": overflow,
            "try_lock_loss": contention,
            "cutoff_writer_handshake": entered && ended && held && final?.0.count == 2
                && c.lost.load(ordering: .sequentiallyConsistent) == 0,
            "closed_equal_tick_refused": !equalWasAdmitted && c.outside.load(ordering: .sequentiallyConsistent) == 2,
            "sealed_prefix_stable": final?.0.map(\.bytes) == after?.0.map(\.bytes)]
    }
}

@available(iOS 18.0, macOS 15.0, *)
private final class PhaseWire: NSObject, URLSessionTaskDelegate {
    static let shared = PhaseWire()
    let ring = PhaseRing()
    private let queue = DispatchQueue(label: "org.exreader.diagnostic.phase.sender")
    private var timer: DispatchSourceTimer?
    private var session: URLSession!
    private var endpoint: URL?
    private var secret = "", nonce = "", caseName = ""
    private var metadata: [String: Any] = [:]
    private var requests = 0, outstanding = false, sealedAcknowledged = false
    private var serializationTicks: UInt64 = 0, payloadBytes: UInt64 = 0
    private var started = false

    override init() {
        super.init()
        ring.append(0)
        queue.async { self.start() }
    }
    private func hashFile(_ url: URL) throws -> String {
        let handle = try FileHandle(forReadingFrom: url); defer { try? handle.close() }
        var hash = SHA256(), total = 0
        while let data = try handle.read(upToCount: 1024 * 1024), !data.isEmpty {
            total += data.count
            if total > 256 * 1024 * 1024 { throw NSError(domain: "PhaseIdentityBound", code: 1) }
            hash.update(data: data)
        }
        return hash.finalize().map { String(format: "%02x", $0) }.joined()
    }
    private func start() {
        guard !started else { return }; started = true
        let env = ProcessInfo.processInfo.environment
        secret = env["EXR_PHASE_SECRET"] ?? ""
        nonce = env["EXR_PHASE_NONCE"] ?? ""
        caseName = env["EXR_PHASE_CASE"] ?? ""
        guard secret.count == 64, nonce.count == 32,
              let url = URL(string: env["EXR_PHASE_ENDPOINT"] ?? ""),
              url.scheme == "http", url.host == "127.0.0.1", url.port != nil,
              url.path.isEmpty || url.path == "/", url.user == nil, url.password == nil,
              url.query == nil, url.fragment == nil else { return }
        endpoint = url
        var clock = mach_timebase_info_data_t(); mach_timebase_info(&clock)
        metadata = ["schema": 1, "nonce": nonce, "case": caseName,
            "source_sha": Bundle.main.object(forInfoDictionaryKey: "EXRSourceSHA") as? String ?? "",
            "pid": ProcessInfo.processInfo.processIdentifier,
            "simulator_udid": env["SIMULATOR_UDID"] ?? "",
            "clock": ["name": "mach_absolute_time", "numer": clock.numer, "denom": clock.denom],
            "sdk_version": Bundle.main.object(forInfoDictionaryKey: "EXRSDKVersion") as? String ?? "",
            "self_checks": caseName == "test00Transport" ? PhaseRing.selfChecks() : [:]]
        do {
            metadata["executable_sha256"] = try hashFile(Bundle.main.executableURL!)
            metadata["runtime_sha256"] = try hashFile(Bundle.main.bundleURL.appendingPathComponent("Frameworks/libexreader.3.42.0.dylib"))
            metadata["fixture_sha256"] = try hashFile(Bundle.main.url(forResource: "Sample", withExtension: "epub")!)
        } catch { metadata["identity_error"] = "owned-bundle-identity-unavailable" }
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 2; config.timeoutIntervalForResource = 2
        config.waitsForConnectivity = false; config.connectionProxyDictionary = [:]
        config.httpMaximumConnectionsPerHost = 1; config.urlCache = nil; config.httpCookieStorage = nil
        session = URLSession(configuration: config, delegate: self, delegateQueue: nil)
        timer = DispatchSource.makeTimerSource(queue: queue)
        timer!.schedule(deadline: .now(), repeating: 1)
        timer!.setEventHandler { self.send() }; timer!.resume()
    }
    func urlSession(_ session: URLSession, task: URLSessionTask,
                    willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest,
                    completionHandler: @escaping (URLRequest?) -> Void) { completionHandler(nil) }

    private func mac(_ data: Data) -> String {
        HMAC<SHA256>.authenticationCode(for: data, using: SymmetricKey(data: Data(secret.utf8)))
            .map { String(format: "%02x", $0) }.joined()
    }
    private func send() {
        guard !outstanding, !sealedAcknowledged, requests < 600, let endpoint,
              let (events, stats) = ring.snapshot() else { return }
        let serializationStart = mach_absolute_time()
        var chain = Data(repeating: 0, count: 32)
        for event in events { chain = Data(SHA256.hash(data: chain + event.bytes)) }
        let head = chain.map { String(format: "%02x", $0) }.joined()
        var payload = metadata
        payload["events"] = events.map(\.json); payload["head_sha256"] = head
        payload["stats"] = stats
        payload["transport"] = ["request": requests + 1, "serialization_ticks": serializationTicks,
                                 "payload_bytes": payloadBytes]
        guard let body = try? JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys]),
              body.count <= 256 * 1024 else { ring.lost.wrappingAdd(1, ordering: .sequentiallyConsistent); return }
        serializationTicks &+= mach_absolute_time() - serializationStart
        payloadBytes &+= UInt64(body.count); requests += 1; outstanding = true
        var request = URLRequest(url: endpoint.appendingPathComponent("snapshot"))
        request.httpMethod = "POST"; request.httpBody = body
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(mac(body), forHTTPHeaderField: "X-Phase-Mac")
        session.dataTask(with: request) { data, response, error in
            self.queue.async {
                self.outstanding = false
                guard error == nil, let data, data.count <= 4096,
                      let http = response as? HTTPURLResponse, http.statusCode == 200,
                      http.value(forHTTPHeaderField: "X-Phase-Mac") == self.mac(data),
                      let answer = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
                      answer["nonce"] as? String == self.nonce,
                      answer["count"] as? Int == events.count,
                      answer["head_sha256"] as? String == head else { return }
                if answer["seal_requested"] as? Bool == true { self.ring.close() }
                if stats["sealed"] as? Bool == true && answer["sealed"] as? Bool == true {
                    self.sealedAcknowledged = true; self.timer?.cancel()
                }
            }
        }.resume()
    }
}

// All owner hooks use these nonthrowing wrappers. Unsupported atomic/runtime
// availability produces no complete preflight; it never selects a fallback.
enum OrgPhase {
    private static func identity(_ owner: AnyObject) -> UInt64 {
        UInt64(UInt(bitPattern: ObjectIdentifier(owner)))
    }
    static func boot() {
        if #available(iOS 18.0, macOS 15.0, *) { _ = PhaseWire.shared }
    }
    static func event(_ kind: UInt64, _ owner: AnyObject, op: UInt64 = 0,
                      parent: UInt64 = 0, a: Int64 = 0, b: Int64 = 0, c: Int64 = 0) {
        if #available(iOS 18.0, macOS 15.0, *) {
            PhaseWire.shared.ring.append(kind, owner: identity(owner), op: op, parent: parent, a: a, b: b, c: c)
        }
    }
    static func operation(_ owner: AnyObject, kind: Int64, parent: UInt64 = 0) -> UInt64 {
        if #available(iOS 18.0, macOS 15.0, *) {
            let op = PhaseWire.shared.ring.operation()
            event(20, owner, op: op, parent: parent, a: kind); return op
        }
        return 0
    }
    static func activation(_ model: AnyObject, _ organization: AnyObject, _ sdkID: Int64) -> UInt64 {
        let op = operation(model, kind: 100)
        event(11, model, op: op, a: sdkID, c: Int64(identity(organization)))
        return op
    }
    static func selection(_ owner: AnyObject, _ kind: Int) -> UInt64 {
        let op = operation(owner, kind: 101)
        event(42, owner, op: op, a: Int64(kind)); return op
    }
    static func panel(_ value: Bool, _ organization: AnyObject, _ model: AnyObject) -> Bool {
        event(10, organization, a: value ? 1 : 0, b: Int64(identity(model))); return value
    }
    static func result<T>(_ value: Result<T, Error>) -> Int64 {
        switch value { case .success: return 0; case .failure: return 1 }
    }
    static func files(_ folder: URL, after: Bool) {
        // Startup-only freshness observation; never called on the Verify path.
        let names = ["library.sqlite", "library.sqlite-wal", "library.sqlite-shm",
                     "reader-catalog.db", "reader-catalog.db-wal", "reader-catalog.db-shm", "reader-catalog.db-journal"]
        var mask: Int64 = 0
        for (i, name) in names.enumerated() {
            if FileManager.default.fileExists(atPath: folder.appendingPathComponent(name).path) { mask |= Int64(1 << i) }
        }
        if #available(iOS 18.0, macOS 15.0, *) { PhaseWire.shared.ring.append(after ? 3 : 2, a: mask) }
    }
}
