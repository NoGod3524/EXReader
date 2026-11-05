// SPDX-License-Identifier: MIT
import Foundation
import CoreGraphics
import CryptoKit
import CEXReader
import CReaderProduct
import Darwin

@main struct RecordCompatibility {
    struct Saved: Codable {
        let filename: String
        let request: HostReadingRequest
        let wire: Data
    }
    static func need(_ condition: Bool, _ message: String) throws {
        if !condition { throw HostError.invalidResult(message) }
    }
    // Public G03 fixture with the exact Android formatter spelling. This is
    // deliberately identified as a protocol fixture, not an Android UI run.
    static func submitFixture(_ request: HostReadingRequest, catalog: HostCatalog) throws -> reader_rc_result {
        try catalog.withHistory { history in
            try hostProductStrings([request.revision, request.parser, request.bookKey, request.annotation, request.body] + request.heads) { strings in
                let expected = Array(strings.dropFirst(5))
                return try expected.withUnsafeBufferPointer { buffer in
                    var context = reader_rc_context(); context.store = history
                    context.revision_id = strings[0]; context.parser_version = strings[1]
                    context.expected_heads = buffer.baseAddress; context.expected_count = buffer.count
                    var command = reader_rc_command()
                    command.kind = request.kind == 1 ? READER_RC_PROGRESS : READER_RC_BOOKMARK
                    command.operation = READER_RC_PUT; command.book_key = strings[2]
                    command.annotation_id = request.kind == 1 ? nil : strings[3]
                    command.text = request.kind == 1 ? nil : strings[4]; command.part = request.capture!.part
                    return try request.capture!.withRaw { capture in
                        try withUnsafePointer(to: capture) { pointer in
                            command.capture = pointer
                            var result = reader_rc_result(), error = reader_rc_error()
                            try need(reader_rc_apply(&context, &command, &result, &error) == READER_RC_OK,
                                     "Public G03 tag fixture was refused")
                            return result
                        }
                    }
                }
            }
        }
    }
    static func main() throws {
        let args = CommandLine.arguments, env = ProcessInfo.processInfo.environment
        guard env["GITHUB_ACTIONS"] == "true", args.count == 6 else { throw HostError.invalidInput("Actions-only compatibility probe") }
        let mode = args[1], resources = URL(fileURLWithPath: args[2]), root = URL(fileURLWithPath: args[3])
        let report = URL(fileURLWithPath: args[4]), expected = args[5]
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        let queue = DispatchQueue(label: "apple.record.compatibility.owner")
        var checks: [String] = [], wires: [[String: Any]] = []
        try queue.sync {
            let library = try HostLibrary(path: root.appendingPathComponent("library.sqlite"))
            let catalog = try HostCatalog(path: root.appendingPathComponent("catalog.sqlite"),
                migrationURL: resources.appendingPathComponent("reader-catalog-v1.sql"), ownerQueue: queue)
            defer { try? catalog.close() }
            let font = try HostFont(data: Data(contentsOf: resources.appendingPathComponent("Reader.otf")))
            let session = HostSession(library: library, font: font, slowDelay: 0,
                viewport: CGSize(width: 480, height: 640), fontSize: 28)
            let manifest = root.appendingPathComponent("saved-records.json")
            if mode == "produce" || mode == "produce-prefixed" {
                var saved: [Saved] = []
                for name in ["Records.txt", "Bounded.epub", "Sample.pdf", "NavigationPages.cbz"] {
                    let (id, _) = try session.importBook(url: resources.appendingPathComponent(name), cancel: HostCancelBox(), catalog: catalog)
                    _ = try session.open(bookID: id, cancel: HostCancelBox())
                    let capture = try session.readingCapture(cancel: HostCancelBox())
                    if mode == "produce-prefixed" {
                        let seed = try HostReadingWorker.request(session: session, catalog: catalog, kind: 1,
                            operation: 0, mode: capture.mode, capture: capture, body: "", cancel: HostCancelBox())
                        _ = try HostReadingWorker.submit(seed, session: session, catalog: catalog, root: root, cancel: HostCancelBox())
                    }
                    for kind in [1, 2] {
                        var request = try HostReadingWorker.request(session: session, catalog: catalog, kind: kind,
                            operation: 0, mode: capture.mode, capture: capture, body: "", cancel: HostCancelBox())
                        let result: reader_rc_result
                        if mode == "produce-prefixed" {
                            try need(expected == "exreader-sdk-" + String(cString: exr_version()), "Fixture tag is not the real runtime's Android spelling")
                            var object = try JSONSerialization.jsonObject(with: JSONEncoder().encode(request)) as! [String: Any]
                            object["parser"] = expected
                            request = try JSONDecoder().decode(HostReadingRequest.self, from: JSONSerialization.data(withJSONObject: object))
                            result = try Self.submitFixture(request, catalog: catalog)
                        } else {
                            result = try HostReadingWorker.submit(request, session: session, catalog: catalog, root: root, cancel: HostCancelBox())
                        }
                        try need(result.created == 1 && request.parser == expected, "Producer did not commit actual host request/parser")
                        let wire = try catalog.withHistory { try HostReadingWorker.retained($0, revision: request.revision).0 }
                        saved.append(Saved(filename: name, request: request, wire: wire))
                        checks.append("produce:\(name):\(kind)")
                    }
                }
                try JSONEncoder().encode(saved).write(to: manifest, options: .atomic)
            } else if mode == "consume" || mode == "refuse" {
                let saved = try JSONDecoder().decode([Saved].self, from: Data(contentsOf: manifest))
                try need(saved.count == 8, "Retained host record set differs")
                let revisions = try catalog.scalar("SELECT count(*) FROM reader_revisions")
                let outbox = try catalog.scalar("SELECT count(*) FROM reader_outbox")
                for value in saved {
                    _ = try session.open(bookID: value.request.bookID, cancel: HostCancelBox())
                    let before = try session.stateHash()
                    let wire = try catalog.withHistory { try HostReadingWorker.retained($0, revision: value.request.revision).0 }
                    try need(wire == value.wire && value.request.parser == expected, "Retained wire or genuine producer parser changed")
                    if mode == "refuse" {
                        var refused = false
                        do { _ = try session.readingResolution(wire, catalog: catalog, cancel: HostCancelBox()) } catch { refused = true }
                        try need(refused, "Original owner unexpectedly accepted a different parser")
                    } else {
                        let (capture, hit) = try session.readingResolution(wire, catalog: catalog, cancel: HostCancelBox())
                        try need(capture == value.request.capture && hit.bookID == value.request.bookID,
                            "Live host resolution/recapture differs from the real old capture")
                        let decoded = try catalog.withHistory { try HostReadingWorker.decoded(wire, history: $0) }
                        try need(decoded.book == value.request.bookKey && decoded.capture == capture, "Decoded original identity differs")
                        let unknown = Data(String(decoding: wire, as: UTF8.self)
                            .replacingOccurrences(of: "\"parser_version\":\"" + expected + "\"", with: "\"parser_version\":\"3.43.0\"").utf8)
                        try need(unknown != wire, "Unknown parser negative did not change its input")
                        var unknownRefused = false
                        do { _ = try session.readingResolution(unknown, catalog: catalog, cancel: HostCancelBox()) } catch { unknownRefused = true }
                        try need(unknownRefused, "Unknown parser navigated a retained record")
                        var object = try JSONSerialization.jsonObject(with: JSONEncoder().encode(value.request)) as! [String: Any]
                        object["parser"] = "3.43.0"
                        let unknownRequest = try JSONDecoder().decode(HostReadingRequest.self, from: JSONSerialization.data(withJSONObject: object))
                        unknownRefused = false
                        do { try unknownRequest.validate() } catch { unknownRefused = true }
                        try need(unknownRefused, "Unknown pending request parser was admitted")
                        if value.filename == "Records.txt" {
                            let other = saved.first { $0.filename == "Bounded.epub" }!
                            _ = try session.open(bookID: other.request.bookID, cancel: HostCancelBox())
                            var refused = false
                            do { _ = try session.readingResolution(wire, catalog: catalog, cancel: HostCancelBox()) } catch { refused = true }
                            try need(refused, "Wrong original accepted an old record")
                            _ = try session.open(bookID: value.request.bookID, cancel: HostCancelBox())
                        }
                    }
                    try need(session.stateHash() == before, "Read-only old record resolution wrote SDK state")
                    let retained = try catalog.withHistory { try HostReadingWorker.retained($0, revision: value.request.revision).0 }
                    try need(retained == value.wire, "Host rewrote retained wire")
                    checks.append("\(mode):\(value.filename):\(value.request.kind)")
                    wires.append(["revision": value.request.revision, "parser": value.request.parser,
                        "sha256": SHA256.hash(data: wire).map { String(format: "%02x", $0) }.joined(),
                        "bytes": wire.count, "book": value.request.bookKey])
                }
                try need(catalog.scalar("SELECT count(*) FROM reader_revisions") == revisions &&
                         catalog.scalar("SELECT count(*) FROM reader_outbox") == outbox, "Read-only resolution changed history/outbox")
                checks.append("history-outbox-and-wire-retained")
            } else if mode == "kill-before" || mode == "kill-after" {
                let (id, _) = try session.importBook(url: resources.appendingPathComponent("Records.txt"), cancel: HostCancelBox(), catalog: catalog)
                _ = try session.open(bookID: id, cancel: HostCancelBox())
                _ = try session.turn(1, cancel: HostCancelBox())
                let capture = try session.readingCapture(cancel: HostCancelBox())
                let request = try HostReadingWorker.request(session: session, catalog: catalog, kind: 1, operation: 0,
                    mode: capture.mode, capture: capture, body: "", cancel: HostCancelBox())
                try JSONEncoder().encode(request).write(to: root.appendingPathComponent("original-request.json"), options: .atomic)
                if mode == "kill-before" { HostReadingWorker.afterDurableSave = { _exit(73) } }
                else { HostReadingWorker.afterCommit = { _exit(74) } }
                _ = try HostReadingWorker.submit(request, session: session, catalog: catalog, root: root, cancel: HostCancelBox())
                throw HostError.invalidResult("Producer did not terminate at real boundary")
            } else if mode == "replay-before" || mode == "replay-after" {
                let original = try JSONDecoder().decode(HostReadingRequest.self, from: Data(contentsOf: root.appendingPathComponent("original-request.json")))
                _ = try session.open(bookID: original.bookID, cancel: HostCancelBox())
                guard let pending = try HostReadingWorker.pending(root: root) else { throw HostError.invalidResult("Original private request missing") }
                try need(pending.parser == expected && pending.revision == original.revision && pending.capture == original.capture,
                    "Upgrade rewrote original pending identity")
                let before = try session.stateHash()
                let result = try HostReadingWorker.replay(session: session, catalog: catalog, root: root, cancel: HostCancelBox())
                try need(result.created == (mode == "replay-before" ? 1 : 0) && HostReadingWorker.pending(root: root) == nil && session.stateHash() == before,
                    "Cross-version explicit replay lost original commit boundary")
                let wire = try catalog.withHistory { try HostReadingWorker.retained($0, revision: pending.revision).0 }
                let decoded = try catalog.withHistory { try HostReadingWorker.decoded(wire, history: $0) }
                let object = try JSONSerialization.jsonObject(with: wire) as! [String: Any]
                let location = (object["payload"] as! [String: Any])["location"] as! [String: Any]
                try need(decoded.capture == original.capture && location["parser_version"] as? String == expected,
                    "Replay changed original selector/parser wire")
                checks.append(mode + ":original-revision-selector-parser-and-created")
            } else { throw HostError.invalidInput("Unknown compatibility mode") }
        }
        let result: [String: Any] = ["accepted": true, "mode": mode, "checks": checks, "records": wires,
            "sdk": String(cString: exr_version()), "producer_parser": expected, "pid": ProcessInfo.processInfo.processIdentifier,
            "public_android_spelling_fixture": mode == "produce-prefixed",
            "source_sha": env["GITHUB_SHA"] ?? "", "run_id": env["GITHUB_RUN_ID"] ?? "", "attempt": env["GITHUB_RUN_ATTEMPT"] ?? "",
            "host_ui_accepted": false, "physical_device_accepted": false]
        try JSONSerialization.data(withJSONObject: result, options: [.sortedKeys, .prettyPrinted]).write(to: report, options: .atomic)
        print("APPLE_RECORD_COMPATIBILITY " + String(decoding: try JSONSerialization.data(withJSONObject: result, options: [.sortedKeys]), as: UTF8.self))
    }
}
