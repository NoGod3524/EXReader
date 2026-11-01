// Supplementary diagnostic. Original cases11/12 are compiled and executed separately without body changes.
import XCTest
import AppKit
import CoreGraphics
import CoreFoundation
import Darwin
import CryptoKit

private let f08DiagnosticSource = "__F08_DIAG_SOURCE__"
private let f08ExpectedExecutable = "__F08_APP_EXE__"
private func f08Now() -> UInt64 { DispatchTime.now().uptimeNanoseconds }
private func f08SHA(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
private func f08Rect(_ r: CGRect) -> [String: Double] { ["x": r.minX, "y": r.minY, "width": r.width, "height": r.height] }
private func f08Error(_ text: String) -> NSError { NSError(domain: "F08ReaderAnimation", code: 1, userInfo: [NSLocalizedDescriptionKey: text]) }
private func f08FreshSharedDirectory(_ directory: URL, nonce: String) throws {
    guard directory.path.hasPrefix("/"), directory.standardizedFileURL.path == directory.path,
          directory.resolvingSymlinksInPath().path == directory.path,
          directory.lastPathComponent == "F08ReaderAnimation-" + nonce else { throw f08Error("Noncanonical nonce directory") }
    // mkdir is atomic: a pre-existing directory, file or symlink must fail, including EEXIST.
    guard mkdir(directory.path, mode_t(0o700)) == 0 else { throw f08Error("Fresh nonce directory creation failed, errno=\(errno)") }
    var component = URL(fileURLWithPath: "/", isDirectory: true)
    for part in directory.pathComponents.dropFirst() {
        component.appendPathComponent(part, isDirectory: true)
        let attributes = try FileManager.default.attributesOfItem(atPath: component.path)
        guard attributes[.type] as? FileAttributeType == .typeDirectory else { throw f08Error("Nonce directory contains symlink/non-directory") }
    }
    let attributes = try FileManager.default.attributesOfItem(atPath: directory.path)
    guard (attributes[.ownerAccountID] as? NSNumber)?.uint32Value == getuid(),
          (attributes[.posixPermissions] as? NSNumber)?.intValue == 0o700 else { throw f08Error("Nonce directory UID/mode0700 mismatch") }
}
private func f08Attach(_ test: XCTestCase, _ name: String, _ value: [String: Any]) {
    guard let data = try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]) else { XCTFail("JSON attachment failed: " + name); return }
    let a = XCTAttachment(string: String(decoding: data, as: UTF8.self)); a.name = name; a.lifetime = .keepAlways; test.add(a)
}

func F08PrepareReaderWindow(_ test: XCTestCase, _ app: XCUIApplication) -> Bool {
    var events: [[String: Any]] = []
    func record(_ phase: String) { events.append(["phase": phase, "clock_ns": f08Now(), "ax_window_count": app.windows.count,
        "declared_launch_arguments": app.launchArguments, "meaning": "Reader setup outside measure; never launch09 or TTI."] ) }
    defer { f08Attach(test, "f08-reader-window-preparation", ["kind": "reader-window-preparation", "test": test.name, "events": events]) }
    record("after-original-launch")
    if app.windows.count == 0 {
        let file = app.menuBars.menuBarItems["File"]
        guard file.exists && file.isEnabled else { record("file-menu-unavailable"); return false }
        file.click()
        let item = app.menuBars.menuItems["New Window"].firstMatch
        guard item.exists && item.isEnabled else { record("new-window-unavailable"); return false }
        record("before-standard-new-window-command"); item.click(); record("after-standard-new-window-command")
    }
    let exists = app.windows.firstMatch.waitForExistence(timeout: 30)
    record(exists ? "window-prepared" : "window-missing")
    guard exists else { return false }
    do {
        let target = try f08Target(app, hashExecutable: true)
        events.append(["phase": "owned-runtime-bound", "clock_ns": f08Now(), "actual_identity": [
            "pid": Int(target.pid), "window_number": target.window, "source_sha": target.source,
            "executable_url": target.executable, "executable_sha256": target.executableSHA],
            "native_window_frame_points": f08Rect(target.frame), "ax_window_frame_points": f08Rect(target.ax.frame)])
        return true
    } catch { events.append(["phase": "runtime-binding-failed", "error": String(describing: error), "clock_ns": f08Now()]); return false }
}

private struct F08Target {
    let pid: pid_t
    let window: Int
    let frame: CGRect
    let ax: XCUIElement
    let executable: String
    let source: String
    let executableSHA: String
}
private func f08Target(_ app: XCUIApplication, hashExecutable: Bool) throws -> F08Target {
    let applications = NSRunningApplication.runningApplications(withBundleIdentifier: "org.exreader.host").filter {
        !$0.isTerminated && $0.executableURL?.resolvingSymlinksInPath().path == f08ExpectedExecutable
    }
    guard applications.count == 1, let application = applications.first,
          let executable = application.executableURL?.resolvingSymlinksInPath(), let bundle = application.bundleURL,
          let infoData = try? Data(contentsOf: bundle.appendingPathComponent("Contents/Info.plist")),
          let info = try? PropertyListSerialization.propertyList(from: infoData, format: nil) as? [String: Any],
          info["EXRSourceSHA"] as? String == f08DiagnosticSource else { throw f08Error("Owned executable/PID/source binding missing or ambiguous") }
    let windows = (CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]] ?? []).filter {
        ($0[kCGWindowOwnerPID as String] as? NSNumber)?.int32Value == application.processIdentifier &&
        ($0[kCGWindowLayer as String] as? NSNumber)?.intValue == 0 &&
        ($0[kCGWindowIsOnscreen as String] as? Bool) == true
    }
    guard windows.count == 1, let row = windows.first, let number = row[kCGWindowNumber as String] as? Int,
          let bounds = row[kCGWindowBounds as String] as? NSDictionary, let frame = CGRect(dictionaryRepresentation: bounds as CFDictionary) else {
        throw f08Error("Exactly one on-screen owned native normal Window required")
    }
    let axes = app.windows.allElementsBoundByIndex.filter { $0.exists && $0.frame == frame }
    guard axes.count == 1 else { throw f08Error("AX/native Window exact geometry binding missing or ambiguous") }
    let digest = hashExecutable ? f08SHA(try Data(contentsOf: executable)) : ""
    return F08Target(pid: application.processIdentifier, window: number, frame: frame, ax: axes[0], executable: executable.path,
                     source: f08DiagnosticSource, executableSHA: digest)
}

private let f08AckCallback: CFNotificationCallback = { _, observer, name, _, _ in
    guard let observer, let name else { return }
    Unmanaged<F08Ack>.fromOpaque(observer).takeUnretainedValue().receive(name.rawValue as String)
}
private final class F08Ack {
    private let center = CFNotificationCenterGetDarwinNotifyCenter()
    private let name: String
    private(set) var count = 0
    private var received: UInt64 = 0
    private(set) var offMain = false
    init(_ name: String) { self.name = name }
    deinit { CFNotificationCenterRemoveObserver(center, Unmanaged.passUnretained(self).toOpaque(), CFNotificationName(rawValue: name as CFString), nil) }
    func receive(_ actual: String) {
        if actual != name || !Thread.isMainThread { offMain = true }
        count += 1; received = f08Now()
    }
    func send(_ request: String) throws -> [String: Any] {
        CFNotificationCenterAddObserver(center, Unmanaged.passUnretained(self).toOpaque(), f08AckCallback, name as CFString, nil, .deliverImmediately)
        let registered = f08Now()
        let before = f08Now()
        CFNotificationCenterPostNotification(center, CFNotificationName(rawValue: request as CFString), nil, nil, false)
        let after = f08Now(); let deadline = f08Now() + 5_000_000_000
        while count == 0 && f08Now() < deadline { RunLoop.current.run(until: Date().addingTimeInterval(0.01)) }
        guard count == 1, !offMain else { throw f08Error("ACK missing, duplicate or off-main: \(name), count=\(count)") }
        return ["request_name": request, "ack_name": name, "ack_registered_ns": registered,
                "request_post_before_ns": before, "request_post_after_ns": after, "ack_received_ns": received, "ack_receipt_count": count]
    }
}

final class F08ReaderAnimationUITests: XCTestCase {
    private var app: XCUIApplication!
    private var samples: [[String: Any]] = []
    private var iterations: [[String: Any]] = []
    private var currentItem: [String: Any]?
    private var errors: [String] = []
    private var identity: [String: Any] = [:]
    private var ready: [String: Any] = [:]
    private var flush: [String: Any] = [:]
    private var nonce = ""
    private var caseID = 0
    private var protocolMode: String { name.contains("ActionOnlyNativeFrames") ? "action_only" : "capture" }
    private var actualTestIdentifier: String {
        let methods = ["test16FrozenFontLocateNativeFrames", "test17SampleNextFontLocateNativeFrames",
                       "test18FrozenFontLocateActionOnlyNativeFrames", "test19SampleNextFontLocateActionOnlyNativeFrames"]
        return "F08ReaderAnimationUITests/" + (methods.first(where: { name.contains($0) }) ?? "unknown") + "()"
    }
    private var temporaryRoot = ""
    private var sharedDirectory = ""
    private var appLogPath = ""
    private var appLogSHA = ""
    private var currentInputs: [[String: Any]] = []
    private var acknowledgements: [String: F08Ack] = [:]

    override func setUpWithError() throws {
        continueAfterFailure = false
        caseID = (name.contains("test16FrozenFontLocateNativeFrames") || name.contains("test18FrozenFontLocateActionOnlyNativeFrames")) ? 11 : 12
        nonce = UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased()
        // Independently obtain the current UID's public Darwin temporary root; do not trust a path supplied by the app.
        let required = confstr(_CS_DARWIN_USER_TEMP_DIR, nil, 0)
        guard required > 1 else { throw f08Error("Darwin UID temporary root unavailable") }
        var buffer = [CChar](repeating: 0, count: required)
        guard confstr(_CS_DARWIN_USER_TEMP_DIR, &buffer, required) == required else { throw f08Error("Darwin UID temporary root changed") }
        temporaryRoot = URL(fileURLWithPath: String(cString: buffer), isDirectory: true).resolvingSymlinksInPath().standardizedFileURL.path
        let directory = URL(fileURLWithPath: temporaryRoot, isDirectory: true).appendingPathComponent("F08ReaderAnimation-" + nonce, isDirectory: true)
        try f08FreshSharedDirectory(directory, nonce: nonce)
        sharedDirectory = directory.path; appLogPath = directory.appendingPathComponent("app-bridge.json").path
        app = XCUIApplication(); samples = []; iterations = []; errors = []
        app.launchArguments = ["-EXRShelfSeed", "-EXRFreshState", "1", "-EXRUITestFixtures", "1",
            "-EXRF08ReaderAnimation", "-EXRF08AnimationNonce", nonce, "-EXRF08AnimationCase", String(caseID),
            "-EXRF08AnimationDirectory", sharedDirectory]
        app.launch()
        guard F08PrepareReaderWindow(self, app) else { throw f08Error("Real Window preparation failed") }
        let target = try f08Target(app, hashExecutable: true)
        identity = ["nonce": nonce, "pid": Int(target.pid), "window_number": target.window, "case_id": caseID,
                    "source_sha": target.source, "executable_url": target.executable, "executable_sha256": target.executableSHA]
        let path = directory.appendingPathComponent("bridge-ready.json")
        let deadline = f08Now() + 15_000_000_000
        while !FileManager.default.fileExists(atPath: path.path) && f08Now() < deadline { RunLoop.current.run(until: Date().addingTimeInterval(0.05)) }
        let data = try Data(contentsOf: path)
        guard let value = try JSONSerialization.jsonObject(with: data) as? [String: Any], value["schema"] as? Int == 1,
              let actual = value["identity"] as? NSDictionary, actual.isEqual(to: identity),
              value["temporary_root"] as? String == temporaryRoot,
              value["app_log_path"] as? String == directory.appendingPathComponent("app-bridge.json").path,
              value["errors"] as? [String] == [] else { throw f08Error("App-main bridge-ready identity/root mismatch") }
        ready = value; appLogPath = directory.appendingPathComponent("app-bridge.json").path
    }
    override func tearDownWithError() throws {
        if var partial = currentItem {
            partial["partial"] = true; iterations.append(partial); currentItem = nil
            errors.append("XCTest interrupted the current iteration; only its observed prefix is retained")
        }
        if !identity.isEmpty {
            do { flush = try control("all", "flush") }
            catch { errors.append("flush: \(error)") }
            do {
                let bytes = try Data(contentsOf: URL(fileURLWithPath: appLogPath)); appLogSHA = f08SHA(bytes)
                let attachment = XCTAttachment(string: String(decoding: bytes, as: UTF8.self))
                attachment.name = "f08-reader-animation-app-log"; attachment.lifetime = .keepAlways; add(attachment)
                guard let parsed = try JSONSerialization.jsonObject(with: bytes) as? [String: Any],
                      parsed["kind"] as? String == "reader-animation-app-log" else { throw f08Error("App log malformed") }
            } catch { errors.append("export: \(error)") }
        }
        for i in iterations.indices {
            for phase in ["begin", "end"] {
                guard var control = iterations[i][phase] as? [String: Any], let name = control["request_name"] as? String,
                      let actual = acknowledgements[name] else { continue }
                control["ack_receipt_count"] = actual.count; iterations[i][phase] = control
                if actual.offMain { errors.append("ACK off main thread: " + name) }
            }
        }
        if let name = flush["request_name"] as? String, let actual = acknowledgements[name] { flush["ack_receipt_count"] = actual.count }
        f08Attach(self, "f08-reader-animation-protocol", ["schema": 1, "kind": "reader-animation-protocol", "clock": "DispatchTime.uptimeNanoseconds",
            "identity": identity, "test": name, "mode": protocolMode, "actual_test_identifier": actualTestIdentifier,
            "iterations": iterations, "errors": errors, "flush": flush,
            "bridge_ready": ready, "temporary_root": temporaryRoot, "shared_directory": sharedDirectory, "app_log_path": appLogPath, "app_log_sha256": appLogSHA,
            "samples": samples, "f08_accepted": false,
            "meaning": "Darwin ACK only marks app-main signpost emission. Capture cases prove visible ROI separately; action-only intervals contain no PNG capture. Neither is a GPU fence."])
        app?.terminate()
        if !errors.isEmpty { throw f08Error(errors.joined(separator: "; ")) }
    }
    private func control(_ iteration: String, _ phase: String) throws -> [String: Any] {
        guard let pid = identity["pid"] as? Int, let window = identity["window_number"] as? Int else { throw f08Error("Unbound request identity") }
        let name = "org.exreader.f08.a.\(nonce).\(pid).\(window).\(caseID).\(iteration).\(phase)"
        guard acknowledgements[name] == nil else { throw f08Error("Duplicate request") }
        let ack = F08Ack(name + ".ack"); acknowledgements[name] = ack
        return try ack.send(name)
    }
    private func performAction(_ id: String, body: () -> Void) -> [String: Any] {
        currentInputs = []; let started = f08Now(); let inputStarted = f08Now(); body(); let inputFinished = f08Now()
        currentInputs.append(["id": id, "started_ns": inputStarted, "finished_ns": inputFinished,
                              "scope": "Original public action sequence with its original readiness assertions; conservative call bounds, not physical input latency"])
        return ["id": id, "started_ns": started, "finished_ns": f08Now(), "inputs": currentInputs]
    }
    private func capture(_ phase: String, iteration: Int, wholeWindow: Bool = false) throws -> [String: Any] {
        let started = f08Now(); let target = try f08Target(app, hashExecutable: false)
        guard target.pid == (identity["pid"] as? Int).map({ pid_t($0) }), target.window == identity["window_number"] as? Int else { throw f08Error("Capture target identity changed") }
        let page = node("reader.page"); let pageFrame = page.frame
        let screenshot = wholeWindow ? target.ax.screenshot() : page.screenshot()
        let png = screenshot.pngRepresentation
        guard let pixels = NSBitmapImageRep(data: png) else { throw f08Error("Public screenshot PNG decode failed") }
        let afterTarget = try f08Target(app, hashExecutable: false)
        guard afterTarget.pid == target.pid, afterTarget.window == target.window, afterTarget.frame == target.frame, page.frame == pageFrame else { throw f08Error("Window/reader geometry changed during capture") }
        let name = "f08-\(nonce)-\(caseID)-\(iteration)-\(wholeWindow ? "window-located" : phase)"
        let attachment = XCTAttachment(data: png, uniformTypeIdentifier: "public.png"); attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
        return ["phase": phase, "started_ns": started, "finished_ns": f08Now(), "png_sha256": f08SHA(png), "attachment_name": name,
            "pixel_width": pixels.pixelsWide, "pixel_height": pixels.pixelsHigh, "actual_pid": Int(target.pid),
            "actual_window_number": target.window, "window_visible": true, "window_frame_points": f08Rect(target.frame),
            "ax_window_frame_points": f08Rect(target.ax.frame), "reader_frame_points": f08Rect(pageFrame),
            "scale_x": Double(pixels.pixelsWide) / Double(wholeWindow ? target.frame.width : pageFrame.width),
            "scale_y": Double(pixels.pixelsHigh) / Double(wholeWindow ? target.frame.height : pageFrame.height), "crop_bottom_points": 2]
    }
    private func metrics() -> [XCTMetric] {
        var values: [XCTMetric] = [XCTClockMetric(), XCTMemoryMetric(application: app)]
#if compiler(>=6.2)
        if #available(macOS 26, *) { values.append(XCTHitchMetric(application: app)) }
#endif
        values.append(XCTOSSignpostMetric(subsystem: "org.exreader.f08", category: "NativeUI", name: "ReaderWorkloadFrames"))
        f08Attach(self, "f08-reader-animation-metric-configuration", ["runtime": ProcessInfo.processInfo.operatingSystemVersionString,
            "configured_native_metric_types": values.map { String(describing: type(of: $0)) },
            "signpost": ["subsystem": "org.exreader.f08", "category": "NativeUI", "name": "ReaderWorkloadFrames"],
            "f08_accepted": false, "mode": protocolMode, "actual_test_identifier": actualTestIdentifier,
            "ratio_scope": protocolMode == "capture" ? "IPC/capture-expanded diagnostic, never frozen original budget" : "Original actions/assertions and ACK boundaries; no PNG or added idle. Raw native ratio retained without subtracting IPC."])
        return values
    }

/*F08_COMMON_HELPERS*/

    func test16FrozenFontLocateNativeFrames() {
        openShelf("Book 0201")
        XCTAssertTrue(text("reader.page").contains("Stored native shelf book 201."))
        let options = XCTMeasureOptions(); options.iterationCount = 5; options.invocationOptions = [.manuallyStart, .manuallyStop]
        var ordinal = 0
        measure(metrics: metrics(), options: options) {
            let i = ordinal; ordinal += 1
            var item: [String: Any] = ["index": i, "warmup": i == 0, "native_measurement_index": i == 0 ? NSNull() as Any : (i - 1) as Any, "errors": []]
            var stopped = false
            item["start_before_ns"] = f08Now(); self.currentItem = item; self.startMeasuring(); item["start_after_ns"] = f08Now(); self.currentItem = item
            do {
                item["begin"] = try self.control(String(i), "b"); self.currentItem = item
                let before = self.reader(); var shots = [try self.capture("before", iteration: i)]; var actions: [[String: Any]] = []; item["screenshots"] = shots; item["actions"] = actions; self.currentItem = item
                var larger: [String: Any] = [:], restored: [String: Any] = [:], located: [String: Any] = [:]
                actions.append(self.performAction("font_increase") {
                    self.tap("reader.font.increase"); larger = self.reader()
                    XCTAssertEqual(larger["font_size"] as? Int, (before["font_size"] as? Int ?? 0) + 2)
                    XCTAssertNotEqual(larger["bitmap_sha256"] as? String, before["bitmap_sha256"] as? String)
                }); shots.append(try self.capture("larger", iteration: i)); item["actions"] = actions; item["screenshots"] = shots; self.currentItem = item
                actions.append(self.performAction("font_decrease") { self.tap("reader.font.decrease"); restored = self.reader() })
                shots.append(try self.capture("restored", iteration: i)); item["actions"] = actions; item["screenshots"] = shots; self.currentItem = item
                actions.append(self.performAction("locate:Offline") {
                    self.locate("Offline"); located = self.reader()
                    XCTAssertEqual(restored["font_size"] as? Int, before["font_size"] as? Int)
                    XCTAssertGreaterThan(located["sdk_frame_count"] as? Int ?? 0, before["sdk_frame_count"] as? Int ?? 0)
                }); shots.append(try self.capture("located", iteration: i)); item["actions"] = actions; item["screenshots"] = shots; self.currentItem = item
                item["window_screenshot"] = try self.capture("located", iteration: i, wholeWindow: true); self.currentItem = item
                item["end"] = try self.control(String(i), "e"); self.currentItem = item
                item["stop_before_ns"] = f08Now(); self.stopMeasuring(); item["stop_after_ns"] = f08Now(); stopped = true
                self.samples.append(["cohort": "frozen-2202", "before": before, "larger": larger, "restored": restored, "located": located,
                    "page_turn_coverage": false, "body_scroll_coverage": false,
                    "reason": "The frozen originals contain one short page. The product reader displays paged bitmaps rather than a body scroll view."])
            } catch { item["errors"] = [String(describing: error)]; self.errors.append("iteration \(i): \(error)") }
            if !stopped { item["stop_before_ns"] = f08Now(); self.stopMeasuring(); item["stop_after_ns"] = f08Now() }
            self.iterations.append(item); self.currentItem = nil
            XCTAssertTrue((item["errors"] as? [String] ?? ["missing"]).isEmpty, "Supplementary native frame iteration failed")
        }
        XCTAssertEqual(ordinal, 6, "Original five measured iterations plus the XCTest warmup are required")
    }
    func test17SampleNextFontLocateNativeFrames() {
        XCTAssertTrue(wait { self.node("library.import.epub").exists && !self.node("library.busy").exists })
        tap("library.import.epub")
        XCTAssertTrue(wait { !self.node("library.busy").exists && self.text("library.status").contains("已导入") })
        openShelf("Sample")
        tap("reader.first"); let initial = reader()
        XCTAssertTrue(text("reader.page").contains("C00P000W00"))
        let options = XCTMeasureOptions(); options.iterationCount = 5; options.invocationOptions = [.manuallyStart, .manuallyStop]
        var ordinal = 0
        measure(metrics: metrics(), options: options) {
            let i = ordinal; ordinal += 1
            var item: [String: Any] = ["index": i, "warmup": i == 0, "native_measurement_index": i == 0 ? NSNull() as Any : (i - 1) as Any, "errors": []]
            var stopped = false
            item["start_before_ns"] = f08Now(); self.currentItem = item; self.startMeasuring(); item["start_after_ns"] = f08Now(); self.currentItem = item
            do {
                item["begin"] = try self.control(String(i), "b"); self.currentItem = item
                let before = self.reader(); var shots = [try self.capture("before", iteration: i)]; var actions: [[String: Any]] = []; item["screenshots"] = shots; item["actions"] = actions; self.currentItem = item
                var next: [String: Any] = [:], larger: [String: Any] = [:], restored: [String: Any] = [:], located: [String: Any] = [:]
                actions.append(self.performAction("page_next") {
                    self.tap("reader.next"); next = self.reader()
                    XCTAssertNotEqual(next["location"] as? String, before["location"] as? String)
                    XCTAssertNotEqual(next["bitmap_sha256"] as? String, before["bitmap_sha256"] as? String)
                }); shots.append(try self.capture("next", iteration: i)); item["actions"] = actions; item["screenshots"] = shots; self.currentItem = item
                actions.append(self.performAction("font_increase") { self.tap("reader.font.increase"); larger = self.reader() })
                shots.append(try self.capture("larger", iteration: i)); item["actions"] = actions; item["screenshots"] = shots; self.currentItem = item
                actions.append(self.performAction("font_decrease") { self.tap("reader.font.decrease"); restored = self.reader() })
                shots.append(try self.capture("restored", iteration: i)); item["actions"] = actions; item["screenshots"] = shots; self.currentItem = item
                actions.append(self.performAction("locate:C00P040W00") {
                    self.locate("C00P040W00"); located = self.reader()
                    XCTAssertNotEqual(located["location"] as? String, initial["location"] as? String)
                }); shots.append(try self.capture("located", iteration: i)); item["actions"] = actions; item["screenshots"] = shots; self.currentItem = item
                item["window_screenshot"] = try self.capture("located", iteration: i, wholeWindow: true); self.currentItem = item
                item["end"] = try self.control(String(i), "e"); self.currentItem = item
                item["stop_before_ns"] = f08Now(); self.stopMeasuring(); item["stop_after_ns"] = f08Now(); stopped = true
                self.samples.append(["cohort": "diagnostic-2202-plus-Sample.epub", "frozen_cohort_acceptance": false,
                    "before": before, "next": next, "larger": larger, "restored": restored, "located": located])
            } catch { item["errors"] = [String(describing: error)]; self.errors.append("iteration \(i): \(error)") }
            if !stopped { item["stop_before_ns"] = f08Now(); self.stopMeasuring(); item["stop_after_ns"] = f08Now() }
            self.iterations.append(item); self.currentItem = nil
            XCTAssertTrue((item["errors"] as? [String] ?? ["missing"]).isEmpty, "Supplementary native frame iteration failed")
            // Exact original reset position: after stopMeasuring, never part of the native interval.
            self.tap("reader.first"); _ = self.reader()
        }
        XCTAssertEqual(ordinal, 6, "Original five measured iterations plus the XCTest warmup are required")
    }

    // Same reader actions/assertions; separate cases16/17 retain their visual captures.
    func test18FrozenFontLocateActionOnlyNativeFrames() {
        openShelf("Book 0201")
        XCTAssertTrue(text("reader.page").contains("Stored native shelf book 201."))
        let options = XCTMeasureOptions(); options.iterationCount = 5; options.invocationOptions = [.manuallyStart, .manuallyStop]
        var ordinal = 0
        measure(metrics: metrics(), options: options) {
            let i = ordinal; ordinal += 1
            var item: [String: Any] = ["index": i, "warmup": i == 0, "native_measurement_index": i == 0 ? NSNull() as Any : (i - 1) as Any, "errors": []]
            var stopped = false
            item["start_before_ns"] = f08Now(); self.currentItem = item; self.startMeasuring(); item["start_after_ns"] = f08Now(); self.currentItem = item
            do {
                item["begin"] = try self.control(String(i), "b"); self.currentItem = item
                let before = self.reader(); var actions: [[String: Any]] = []; item["screenshots"] = [[String: Any]](); item["actions"] = actions; self.currentItem = item
                var larger: [String: Any] = [:], restored: [String: Any] = [:], located: [String: Any] = [:]
                actions.append(self.performAction("font_increase") {
                    self.tap("reader.font.increase"); larger = self.reader()
                    XCTAssertEqual(larger["font_size"] as? Int, (before["font_size"] as? Int ?? 0) + 2)
                    XCTAssertNotEqual(larger["bitmap_sha256"] as? String, before["bitmap_sha256"] as? String)
                }); item["actions"] = actions; self.currentItem = item
                actions.append(self.performAction("font_decrease") { self.tap("reader.font.decrease"); restored = self.reader() })
                item["actions"] = actions; self.currentItem = item
                actions.append(self.performAction("locate:Offline") {
                    self.locate("Offline"); located = self.reader()
                    XCTAssertEqual(restored["font_size"] as? Int, before["font_size"] as? Int)
                    XCTAssertGreaterThan(located["sdk_frame_count"] as? Int ?? 0, before["sdk_frame_count"] as? Int ?? 0)
                }); item["actions"] = actions; self.currentItem = item
                item["end"] = try self.control(String(i), "e"); self.currentItem = item
                item["stop_before_ns"] = f08Now(); self.stopMeasuring(); item["stop_after_ns"] = f08Now(); stopped = true
                self.samples.append(["cohort": "frozen-2202", "before": before, "larger": larger, "restored": restored, "located": located,
                    "page_turn_coverage": false, "body_scroll_coverage": false,
                    "reason": "The frozen originals contain one short page. The product reader displays paged bitmaps rather than a body scroll view."])
            } catch { item["errors"] = [String(describing: error)]; self.errors.append("iteration \(i): \(error)") }
            if !stopped { item["stop_before_ns"] = f08Now(); self.stopMeasuring(); item["stop_after_ns"] = f08Now() }
            self.iterations.append(item); self.currentItem = nil
            XCTAssertTrue((item["errors"] as? [String] ?? ["missing"]).isEmpty, "Supplementary native frame iteration failed")
        }
        XCTAssertEqual(ordinal, 6, "Original five measured iterations plus the XCTest warmup are required")
    }
    func test19SampleNextFontLocateActionOnlyNativeFrames() {
        XCTAssertTrue(wait { self.node("library.import.epub").exists && !self.node("library.busy").exists })
        tap("library.import.epub")
        XCTAssertTrue(wait { !self.node("library.busy").exists && self.text("library.status").contains("已导入") })
        openShelf("Sample")
        tap("reader.first"); let initial = reader()
        XCTAssertTrue(text("reader.page").contains("C00P000W00"))
        let options = XCTMeasureOptions(); options.iterationCount = 5; options.invocationOptions = [.manuallyStart, .manuallyStop]
        var ordinal = 0
        measure(metrics: metrics(), options: options) {
            let i = ordinal; ordinal += 1
            var item: [String: Any] = ["index": i, "warmup": i == 0, "native_measurement_index": i == 0 ? NSNull() as Any : (i - 1) as Any, "errors": []]
            var stopped = false
            item["start_before_ns"] = f08Now(); self.currentItem = item; self.startMeasuring(); item["start_after_ns"] = f08Now(); self.currentItem = item
            do {
                item["begin"] = try self.control(String(i), "b"); self.currentItem = item
                let before = self.reader(); var actions: [[String: Any]] = []; item["screenshots"] = [[String: Any]](); item["actions"] = actions; self.currentItem = item
                var next: [String: Any] = [:], larger: [String: Any] = [:], restored: [String: Any] = [:], located: [String: Any] = [:]
                actions.append(self.performAction("page_next") {
                    self.tap("reader.next"); next = self.reader()
                    XCTAssertNotEqual(next["location"] as? String, before["location"] as? String)
                    XCTAssertNotEqual(next["bitmap_sha256"] as? String, before["bitmap_sha256"] as? String)
                }); item["actions"] = actions; self.currentItem = item
                actions.append(self.performAction("font_increase") { self.tap("reader.font.increase"); larger = self.reader() })
                item["actions"] = actions; self.currentItem = item
                actions.append(self.performAction("font_decrease") { self.tap("reader.font.decrease"); restored = self.reader() })
                item["actions"] = actions; self.currentItem = item
                actions.append(self.performAction("locate:C00P040W00") {
                    self.locate("C00P040W00"); located = self.reader()
                    XCTAssertNotEqual(located["location"] as? String, initial["location"] as? String)
                }); item["actions"] = actions; self.currentItem = item
                item["end"] = try self.control(String(i), "e"); self.currentItem = item
                item["stop_before_ns"] = f08Now(); self.stopMeasuring(); item["stop_after_ns"] = f08Now(); stopped = true
                self.samples.append(["cohort": "diagnostic-2202-plus-Sample.epub", "frozen_cohort_acceptance": false,
                    "before": before, "next": next, "larger": larger, "restored": restored, "located": located])
            } catch { item["errors"] = [String(describing: error)]; self.errors.append("iteration \(i): \(error)") }
            if !stopped { item["stop_before_ns"] = f08Now(); self.stopMeasuring(); item["stop_after_ns"] = f08Now() }
            self.iterations.append(item); self.currentItem = nil
            XCTAssertTrue((item["errors"] as? [String] ?? ["missing"]).isEmpty, "Supplementary native frame iteration failed")
            // Exact original reset position: after stopMeasuring, never part of the native interval.
            self.tap("reader.first"); _ = self.reader()
        }
        XCTAssertEqual(ordinal, 6, "Original five measured iterations plus the XCTest warmup are required")
    }
}
