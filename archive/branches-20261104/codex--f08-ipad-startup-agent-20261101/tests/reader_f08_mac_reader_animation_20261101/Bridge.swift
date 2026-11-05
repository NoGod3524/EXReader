// Diagnostic-only generated host source. No UI publication, renderer hooks, timer or invalidation.
#if os(macOS)
import AppKit
import CoreFoundation
import CryptoKit
import os.signpost

private let f08ReaderDarwinCallback: CFNotificationCallback = { _, observer, name, _, _ in
    guard let observer, let name else { return }
    Unmanaged<F08ReaderAnimationBridge>.fromOpaque(observer).takeUnretainedValue().receive(name.rawValue as String)
}

final class F08ReaderAnimationBridge {
    private static var installed: F08ReaderAnimationBridge?
    private let center = CFNotificationCenterGetDarwinNotifyCenter()
    private let log = OSLog(subsystem: "org.exreader.f08", category: "NativeUI")
    private let nonce: String
    private let caseID: Int
    private var boundWindow: NSWindow?
    private var identity: [String: Any] = [:]
    private var errors: [String] = []
    private var events: [[String: Any]] = []
    private var seen: Set<String> = []
    private var tokens: [NSObjectProtocol] = []
    private var starts = 0
    private var ends = 0
    private var active = false
    private var flushed = false
    private var names: [String: (Int, String)] = [:]
    private let temporaryRoot: URL
    private let directory: URL
    private var output: URL { directory.appendingPathComponent("app-bridge.json") }
    private var readyOutput: URL { directory.appendingPathComponent("bridge-ready.json") }
    private func now() -> UInt64 { DispatchTime.now().uptimeNanoseconds }

    static func installIfEnabled() {
        let args = ProcessInfo.processInfo.arguments
        guard args.contains("-EXRF08ReaderAnimation") else { return }
        func argument(_ key: String) -> String? {
            guard let i = args.firstIndex(of: key), i + 1 < args.count else { return nil }
            return args[i + 1]
        }
        guard Thread.isMainThread, installed == nil,
              let nonce = argument("-EXRF08AnimationNonce"), nonce.range(of: "^[0-9a-f]{32}$", options: .regularExpression) != nil,
              let rawCase = argument("-EXRF08AnimationCase"), let caseID = Int(rawCase), [11, 12].contains(caseID) else {
            fputs("F08 diagnostic bridge opt-in invalid\n", stderr); return
        }
        let bridge = F08ReaderAnimationBridge(nonce: nonce, caseID: caseID)
        installed = bridge
        for name in [NSWindow.didBecomeKeyNotification, NSWindow.didBecomeMainNotification] {
            bridge.tokens.append(NotificationCenter.default.addObserver(forName: name, object: nil, queue: nil) { [weak bridge] note in
                guard let bridge, let window = note.object as? NSWindow else { return }
                bridge.bind(window)
            })
        }
        if let window = NSApp?.keyWindow { bridge.bind(window) }
    }

    private init(nonce: String, caseID: Int) {
        self.nonce = nonce; self.caseID = caseID
        temporaryRoot = FileManager.default.temporaryDirectory.resolvingSymlinksInPath().standardizedFileURL
        directory = temporaryRoot.appendingPathComponent("F08ReaderAnimation-" + nonce, isDirectory: true)
    }
    private func sha(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
    private func write(_ value: [String: Any], to url: URL) throws {
        let data = try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])
        try data.write(to: url, options: .atomic)
    }
    private func fail(_ message: String) {
        errors.append(message)
        fputs("F08_BRIDGE_FAIL \(message)\n", stderr)
        try? write(["schema": 1, "kind": "reader-animation-app-log", "clock": "DispatchTime.uptimeNanoseconds",
                    "identity": identity, "events": events, "errors": errors, "complete_log": false,
                    "temporary_root": temporaryRoot.path, "app_log_path": output.path], to: output)
    }
    private func bind(_ window: NSWindow) {
        guard Thread.isMainThread else { fail("window binding off main thread"); return }
        guard boundWindow == nil, window.isVisible, window.windowNumber > 0, window.level == .normal,
              !window.isSheet, let executable = Bundle.main.executableURL?.resolvingSymlinksInPath(),
              let source = Bundle.main.object(forInfoDictionaryKey: "EXRSourceSHA") as? String,
              source.range(of: "^[0-9a-f]{40}$", options: .regularExpression) != nil else { return }
        do {
            let bytes = try Data(contentsOf: executable)
            identity = ["nonce": nonce, "pid": ProcessInfo.processInfo.processIdentifier,
                        "window_number": window.windowNumber, "case_id": caseID, "source_sha": source,
                        "executable_url": executable.path, "executable_sha256": sha(bytes)]
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: false)
            try FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: directory.path)
            boundWindow = window
            for iteration in 0..<6 {
                for phase in ["b", "e"] { register(request(iteration: String(iteration), phase: phase), iteration: iteration, phase: phase) }
            }
            register(request(iteration: "all", phase: "flush"), iteration: -1, phase: "flush")
            try write(["schema": 1, "kind": "reader-animation-bridge-ready", "clock": "DispatchTime.uptimeNanoseconds",
                       "identity": identity, "registered_names": names.keys.sorted(), "registered_ns": now(),
                       "temporary_root": temporaryRoot.path, "app_log_path": output.path, "errors": errors], to: readyOutput)
        } catch { fail("bridge bind/write: \(error)") }
    }
    private func request(iteration: String, phase: String) -> String {
        return "org.exreader.f08.a.\(nonce).\(ProcessInfo.processInfo.processIdentifier).\(boundWindow?.windowNumber ?? -1).\(caseID).\(iteration).\(phase)"
    }
    private func register(_ name: String, iteration: Int, phase: String) {
        names[name] = (iteration, phase)
        CFNotificationCenterAddObserver(center, Unmanaged.passUnretained(self).toOpaque(), f08ReaderDarwinCallback,
                                        name as CFString, nil, .deliverImmediately)
    }
    fileprivate func receive(_ name: String) {
        let received = now()
        guard Thread.isMainThread else { fail("notification not main thread"); return }
        guard let (iteration, phase) = names[name] else { fail("unknown exact request name"); return }
        guard !seen.contains(name), !flushed else { fail("duplicate or post-flush request: " + name); return }
        seen.insert(name)
        guard let window = boundWindow, window.isVisible, window.windowNumber == identity["window_number"] as? Int,
              ProcessInfo.processInfo.processIdentifier == identity["pid"] as? Int32,
              Bundle.main.object(forInfoDictionaryKey: "EXRSourceSHA") as? String == identity["source_sha"] as? String else {
            fail("actual PID/Window/source no longer bound"); return
        }
        if phase == "flush" {
            guard !active, starts == 6, ends == 6, events.count == 12 else { fail("flush before six closed iterations"); return }
            flushed = true
            // Close every request observer on the same main thread before freezing the final log.
            // No callback remains registered that may mutate the sealed snapshot after its ACK.
            CFNotificationCenterRemoveEveryObserver(center, Unmanaged.passUnretained(self).toOpaque())
            let closed = now()
            let value: [String: Any] = ["schema": 1, "kind": "reader-animation-app-log", "clock": "DispatchTime.uptimeNanoseconds",
                "identity": identity, "events": events, "errors": errors, "complete_log": errors.isEmpty,
                "temporary_root": temporaryRoot.path, "app_log_path": output.path,
                "flush_request_name": name, "flush_received_ns": received, "callbacks_closed": true, "callbacks_closed_ns": closed, "flush_prepare_ns": now()]
            do {
                try write(value, to: output)
                CFNotificationCenterPostNotification(center, CFNotificationName(rawValue: (name + ".ack") as CFString), nil, nil, false)
            } catch { fail("flush write failed: \(error)") }
            return
        }
        guard (phase == "b" && !active && starts == iteration && ends == iteration) ||
              (phase == "e" && active && starts == iteration + 1 && ends == iteration) else {
            fail("request phase/iteration out of order: " + name); return
        }
        let before = now()
        if phase == "b" {
            // Same native custom-animation API and format as the authenticated original Shelf14 helper.
            os_signpost(.animationBegin, log: log, name: "ReaderWorkloadFrames", signpostID: .exclusive)
            starts += 1; active = true
        } else {
            os_signpost(.end, log: log, name: "ReaderWorkloadFrames", signpostID: .exclusive)
            ends += 1; active = false
        }
        let after = now()
        var event: [String: Any] = ["sequence": events.count + 1, "phase": phase == "b" ? "begin" : "end",
            "case_id": caseID, "iteration": iteration, "request_name": name, "ack_name": name + ".ack",
            "actual_pid": ProcessInfo.processInfo.processIdentifier, "actual_window_number": window.windowNumber,
            "actual_source_sha": Bundle.main.object(forInfoDictionaryKey: "EXRSourceSHA") as? String ?? "",
            "main_thread": Thread.isMainThread, "window_visible": window.isVisible,
            "signpost_type": phase == "b" ? "animationBegin" : "end", "starts": starts, "ends": ends, "active": active,
            "request_received_ns": received, "signpost_before_ns": before, "signpost_after_ns": after]
        event["ack_post_before_ns"] = now()
        CFNotificationCenterPostNotification(center, CFNotificationName(rawValue: (name + ".ack") as CFString), nil, nil, false)
        event["ack_post_after_ns"] = now()
        events.append(event)
    }
}
#endif
