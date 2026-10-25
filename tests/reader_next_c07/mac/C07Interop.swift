// SPDX-License-Identifier: MIT
import Foundation
import CoreGraphics
import CryptoKit
import CEXReader
import CReaderProduct
import Darwin
import MachO

final class InteropOutbox {
    var entries: [(reader_revision_info, Data)] = []
    var invalid = false
}
func interopOutbox(_ context: UnsafeMutableRawPointer?, _ row: UnsafePointer<reader_revision_outbox_row>?) -> Int32 {
    guard let context, let row else { return 1 }
    let box = Unmanaged<InteropOutbox>.fromOpaque(context).takeUnretainedValue()
    guard let wire = row.pointee.wire, row.pointee.info.bytes > 0,
          row.pointee.info.bytes <= 1024 * 1024, box.entries.count < 100 else { box.invalid = true; return 1 }
    box.entries.append((row.pointee.info, Data(bytes: wire, count: row.pointee.info.bytes)))
    return 0
}

@main struct C07Interop {
    static func synchronize(_ profile: URL, resources: URL, prepare: Bool) throws -> [String: Any] {
        let env = ProcessInfo.processInfo.environment
        guard let root = env["EXR_RAW_DAV_ROOT"], root.hasPrefix("https://"),
              let account = env["EXR_RAW_ACCOUNT"], UUID(uuidString: account) != nil,
              let authorization = env["EXR_RAW_AUTH"] else { throw HostError.invalidInput("Actual native TLS session configuration missing") }
        let owner = DispatchQueue(label: "apple.raw3.sync.preparation.owner")
        try owner.sync {
            let catalog = try HostCatalog(path: profile.appendingPathComponent("reader-catalog.db"),
                migrationURL: resources.appendingPathComponent("reader-catalog-v1.sql"), ownerQueue: owner)
            defer { try? catalog.close() }
            if prepare {
                let library = try HostLibrary(path: profile.appendingPathComponent("library.sqlite"))
                var after: String?
                repeat {
                    let books = try catalog.syncPage(after: after)
                    try catalog.withHistory { history in
                        for book in books {
                            try library.exportSyncOriginal(bookID: book.sdkID,
                                expected: HostSourceFingerprint(format: book.format, sha256: book.sha256, bytes: book.bytes),
                                directory: profile.appendingPathComponent("sync-originals"), cancel: HostCancelBox())
                            try catalog.bootstrapVerified(book, store: history)
                        }
                    }
                    after = books.count == 50 ? books.last?.key : nil
                } while after != nil
            }
        }
        let controller = HostAccountSession()
        try controller.start(profile: HostAccountProfile(id: account, root: root), directory: profile,
                             authorization: Data(authorization.utf8), completed: {})
        let deadline = Date().addingTimeInterval(240)
        while controller.running && Date() < deadline { RunLoop.current.run(until: Date().addingTimeInterval(0.02)) }
        try need(!controller.running && controller.state == "本轮扫描完成" && controller.completedSweeps == 1 &&
                 controller.completedShards == 256, "Actual HostAccountSession did not finish the raw 256-shard sweep")
        let proof: [String: Any] = ["completed_sweeps": controller.completedSweeps,
            "completed_shards": controller.completedShards, "steps": controller.steps, "actual_host_account_session": true]
        controller.close()
        let closing = Date().addingTimeInterval(45)
        while controller.state != "已关闭" && Date() < closing { RunLoop.current.run(until: Date().addingTimeInterval(0.02)) }
        try need(controller.state == "已关闭", "Actual native account worker did not close")
        return proof
    }
    static func need(_ value: Bool, _ message: String) throws {
        if !value { throw HostError.invalidResult(message) }
    }
    static func sha(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
    static func json(_ value: Any) throws -> Data { try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys, .prettyPrinted]) }
    static func object(_ data: Data) throws -> [String: Any] {
        guard let result = try JSONSerialization.jsonObject(with: data) as? [String: Any] else { throw HostError.invalidInput("Manifest object missing") }
        return result
    }
    static func path(_ name: String, in root: URL) throws -> URL {
        let parts = name.split(separator: "/", omittingEmptySubsequences: false)
        try need(!name.isEmpty && name.utf8.count <= 512 && !name.hasPrefix("/") && !name.contains("\\") && !name.contains(":"), "Unsafe bundle path")
        try need(parts.allSatisfy { !$0.isEmpty && $0 != "." && $0 != ".." }, "Unsafe bundle component")
        return root.appendingPathComponent(name)
    }
    static func outbox(_ catalog: HostCatalog) throws -> [(reader_revision_info, Data)] {
        try catalog.withHistory { history in
            let rows = InteropOutbox(); var error = reader_revision_error()
            let status = reader_revision_outbox_raw_v3(history, 100, interopOutbox, Unmanaged.passUnretained(rows).toOpaque(), &error)
            try need(status == READER_REV_OK && !rows.invalid && rows.entries.count < 100, "Complete bounded actual outbox unavailable")
            return rows.entries
        }
    }
    static func capture(_ value: HostReadingCapture, book: String, parser: String) throws -> [String: Any] {
        try value.validate()
        let fields = value.mode == 3 ? value.fixed!.fields : value.anchor!.fields
        let lower = value.mode == 3 ? value.fixed!.start : value.anchor!.start
        let upper = value.mode == 3 ? value.fixed!.end : value.anchor!.end
        let selectors = value.mode == 3 ? Array(fields.dropFirst()) : Array(fields.prefix(3))
        func string(_ value: Data?) -> Any { value.map { String(decoding: $0, as: UTF8.self) } as Any? ?? NSNull() }
        let route: [Any] = [book, parser, value.mode == 2 ? value.path : NSNull(),
                            value.mode == 3 ? string(fields[0]) : NSNull(), value.mode == 3 ? NSNull() : string(fields[3])]
        return ["numbers": [String(value.mode), String(value.mode == 3 ? value.page : value.mode == 2 ? value.part : 0), String(lower), String(upper)],
                "route": route, "selectors": selectors.map { $0?.base64EncodedString() as Any? ?? NSNull() }]
    }
    static func sdkImage() throws -> URL {
        let images = (0..<_dyld_image_count()).compactMap { _dyld_get_image_name($0).map { URL(fileURLWithPath: String(cString: $0)).resolvingSymlinksInPath() } }
            .filter { $0.lastPathComponent.hasPrefix("libexreader") && $0.pathExtension == "dylib" }
        let unique = Set(images.map { $0.path })
        try need(unique.count == 1, "Actual loaded SDK DSO is missing or duplicated")
        return URL(fileURLWithPath: unique.first!)
    }
    // The transport describes the stored public decoder, including NULL tags.
    // The host separately reconstructs EPUB chapter scope from part_path.
    static func wireCapture(_ wire: Data, history: OpaquePointer) throws -> [String: Any] {
        var record = reader_rs_record(), error = reader_rs_error()
        let status = wire.withUnsafeBytes { reader_rs_decode_raw_v3(history, $0.baseAddress, $0.count, &record, &error) }
        try need(status == READER_RS_OK && record.has_location != 0, "Actual retained decoder refused location")
        defer { reader_rs_record_free(&record) }
        func text(_ pointer: UnsafeMutablePointer<CChar>?) -> Any {
            pointer.map { String(cString: $0) } as Any? ?? NSNull()
        }
        func bytes(_ pointer: UnsafeMutablePointer<CChar>?, _ size: Int) -> Any {
            pointer.map { Data(bytes: $0, count: size).base64EncodedString() } as Any? ?? NSNull()
        }
        let mode = record.mode == READER_RS_FIXED_PAGE ? 3 : record.mode == READER_RS_EPUB_CHAPTER ? 2 : 1
        return ["numbers": [String(mode), String(mode == 3 ? record.page : mode == 2 ? record.part : 0), String(record.start), String(record.end)],
                "route": [hostReadingField(record.book_key), hostReadingField(record.parser_version), text(record.part_path), text(record.page_id), text(record.chapter)],
                "selectors": [bytes(record.exact, record.exact_size), bytes(record.prefix, record.prefix_size), bytes(record.suffix, record.suffix_size)]]
    }
    static func main() throws {
        let args = CommandLine.arguments, env = ProcessInfo.processInfo.environment
        try need(env["GITHUB_ACTIONS"] == "true" && args.count == 6, "Actions-only actual host interop")
        let requestedMode = args[1], resources = URL(fileURLWithPath: args[2]), profile = URL(fileURLWithPath: args[3])
        let networkReceive = requestedMode == "session-receive" || requestedMode == "session-reopen"
        let mode = networkReceive ? "receive" : requestedMode
        let bundle = URL(fileURLWithPath: args[4]), report = URL(fileURLWithPath: args[5])
        let version = String(cString: exr_version())
        try need(version == "3.41.0", "Actual SDK is not the explicit candidate")
        try need(READER_REVISION_ANCHOR_MAX_VERSION == 2, "Candidate changed the public default MAX2 contract")
        try FileManager.default.createDirectory(at: profile, withIntermediateDirectories: true)
        var sessionProof: [String: Any] = [:]
        if requestedMode.hasPrefix("session-") {
            sessionProof = try synchronize(profile, resources: resources, prepare: requestedMode == "session-push")
        }
        let queue = DispatchQueue(label: "actual.apple.record.interop.owner")
        var checks: [String] = [], rows: [[String: Any]] = []
        try queue.sync {
            let library = try HostLibrary(path: profile.appendingPathComponent("library.sqlite"))
            let catalog = try HostCatalog(path: profile.appendingPathComponent(mode == "legacy-replay-refusal" ? "catalog.sqlite" : "reader-catalog.db"),
                migrationURL: resources.appendingPathComponent("reader-catalog-v1.sql"), ownerQueue: queue)
            defer { try? catalog.close() }
            let font = try HostFont(data: Data(contentsOf: resources.appendingPathComponent("Reader.otf")))
            let session = HostSession(library: library, font: font, slowDelay: 0,
                                      viewport: CGSize(width: 480, height: 640), fontSize: 28)
            if mode == "legacy-replay-refusal" {
                let file = profile.appendingPathComponent("reading-requests/request.json")
                let before = try Data(contentsOf: file)
                guard let pending = try HostReadingWorker.pending(root: profile) else { throw HostError.invalidResult("Actual failed old sender request missing") }
                try need(pending.version == 1 && pending.writerVersion == 2 && pending.mode == 3,
                         "Old request lost its original fixed v2 writer")
                _ = try session.open(bookID: pending.bookID, cancel: HostCancelBox())
                let sdk = try session.stateHash(), revisions = try catalog.scalar("SELECT count(*) FROM reader_revisions"),
                    pendingOutbox = try outbox(catalog).map { sha($0.1) }
                var refused = false
                do { _ = try HostReadingWorker.replay(session: session, catalog: catalog, root: profile, cancel: HostCancelBox()) }
                catch { refused = true }
                try need(refused && Data(contentsOf: file) == before && session.stateHash() == sdk &&
                         catalog.scalar("SELECT count(*) FROM reader_revisions") == revisions && outbox(catalog).map { sha($0.1) } == pendingOutbox,
                         "Raw build upgraded or rewrote the actual failed old NUL request")
                rows.append(["request_id": pending.revision, "bootstrap": pending.bootstrap, "parents": pending.heads,
                             "pending_sha256": sha(before), "writer_version": pending.writerVersion])
                checks.append("actual-old-v1-pending-fixed-v2-NUL-remains-refused-with-identical-bytes-id-parents")
            } else if mode == "session-push" {
                try need(outbox(catalog).isEmpty, "Actual native conditional PUT/GET did not ack the complete outbox")
                checks.append("actual-native-raw-session-conditional-publish-verify-and-ack")
            } else if mode == "kill-before" || mode == "kill-after" || mode == "replay-before" || mode == "replay-after" {
                let saved = profile.appendingPathComponent("saved-request.json")
                if mode.hasPrefix("kill-") {
                    let (id, _) = try session.importBook(url: resources.appendingPathComponent("Sample.pdf"), cancel: HostCancelBox(), catalog: catalog)
                    _ = try session.open(bookID: id, cancel: HostCancelBox())
                    let capture = try session.readingCapture(cancel: HostCancelBox())
                    let request = try HostReadingWorker.request(session: session, catalog: catalog, kind: 1, operation: 0,
                        mode: capture.mode, capture: capture, body: "", cancel: HostCancelBox())
                    try need(request.version == 2 && request.anchor_version == 3, "New durable request did not freeze raw3")
                    try JSONEncoder().encode(request).write(to: saved, options: .atomic)
                    if mode == "kill-before" {
                        HostReadingWorker.afterDurableSave = {
                            try Data("before".utf8).write(to: profile.appendingPathComponent("kill-boundary.txt"), options: .atomic)
                            _ = Darwin.kill(getpid(), SIGKILL); _exit(73)
                        }
                    } else {
                        HostReadingWorker.afterCommit = {
                            try Data("after".utf8).write(to: profile.appendingPathComponent("kill-boundary.txt"), options: .atomic)
                            _ = Darwin.kill(getpid(), SIGKILL); _exit(74)
                        }
                    }
                    _ = try HostReadingWorker.submit(request, session: session, catalog: catalog, root: profile, cancel: HostCancelBox())
                    throw HostError.invalidResult("Actual raw producer did not exit at durable boundary")
                }
                let original = try JSONDecoder().decode(HostReadingRequest.self, from: Data(contentsOf: saved))
                guard let pending = try HostReadingWorker.pending(root: profile) else { throw HostError.invalidResult("Raw private request missing after real termination") }
                try need(pending.revision == original.revision && pending.heads == original.heads && pending.bootstrap == original.bootstrap &&
                         pending.anchor_version == 3 && pending.capture == original.capture, "Raw pending identity changed across real process restart")
                _ = try session.open(bookID: pending.bookID, cancel: HostCancelBox())
                let before = try session.stateHash()
                let result = try HostReadingWorker.replay(session: session, catalog: catalog, root: profile, cancel: HostCancelBox())
                try need(result.created == (mode == "replay-before" ? 1 : 0) && session.stateHash() == before &&
                         HostReadingWorker.pending(root: profile) == nil, "Raw replay lost original exact commit boundary")
                let wire = try catalog.withHistory { try HostReadingWorker.retained($0, revision: pending.revision).0 }
                let decoded = try catalog.withHistory { try HostReadingWorker.decoded(wire, history: $0) }
                try need(decoded.version == 3 && decoded.capture == original.capture, "Raw retry changed fixed selector bytes/version")
                checks.append(mode + ":actual-durable-raw3-selector-and-identity")
            } else if mode == "send" {
                try FileManager.default.createDirectory(at: bundle.appendingPathComponent("originals"), withIntermediateDirectories: true)
                try FileManager.default.createDirectory(at: bundle.appendingPathComponent("revisions"), withIntermediateDirectories: true)
                try FileManager.default.createDirectory(at: bundle.appendingPathComponent("proofs"), withIntermediateDirectories: true)
                var originals: [[String: Any]] = [], records: [[String: Any]] = []
                for (role, name) in [("txt", "Records.txt"), ("epub", "Bounded.epub"), ("pdf", "Sample.pdf"), ("cbz", "NavigationPages.cbz")] {
                    let (id, _) = try session.importBook(url: resources.appendingPathComponent(name), cancel: HostCancelBox(), catalog: catalog)
                    let snapshot = try session.open(bookID: id, cancel: HostCancelBox())
                    let actualBook = try library.books().first { $0.id == id }!
                    let fingerprint = try library.sourceFingerprint(book: actualBook)
                    let key = fingerprint.format + ":" + fingerprint.sha256
                    if role == "pdf" {
                        try need(fingerprint.bytes == 8845 && fingerprint.sha256 == "5627a430fa04cbe11d38eb2682e336ef21e147d445753ed46ed11a7d5e3167cc",
                                 "Raw actual sender used another PDF")
                    }
                    try library.exportSyncOriginal(bookID: id, expected: fingerprint,
                        directory: bundle.appendingPathComponent("originals"), cancel: HostCancelBox())
                    originals.append(["role": role, "file": "originals/" + fingerprint.sha256 + "." + fingerprint.format,
                                      "format": fingerprint.format, "book_key": key, "bytes": fingerprint.bytes, "sha256": fingerprint.sha256])
                    let point = try session.readingCapture(cancel: HostCancelBox())
                    if role == "pdf" {
                        try need(point.fixed?.start == 0 && point.fixed?.end == 0 && point.fixed?.fields[3]?.contains(0) == true,
                                 "Actual PDF zero-point suffix did not retain NUL")
                    }
                    var choices: [(Int, String, HostReadingCapture)] = [(1, "progress", point), (2, "bookmark", point)]
                    if role != "cbz" {
                        guard let first = snapshot.pageText.unicodeScalars.first else { throw HostError.invalidResult("Real range text missing: " + role) }
                        // A fixed HostSnapshot deliberately has pageRange 0..<0.
                        // The real zero-point SDK suffix supplies a bounded byte
                        // range; recapture it through the actual SDK as a range.
                        let start = role == "pdf" ? 0 : snapshot.pageRange.lowerBound
                        let end = role == "pdf" ? (point.fixed?.fields[3]?.count ?? 0) : start + String(first).utf8.count
                        choices.append((3, "highlight", try session.readingCapture(start: start, end: end, cancel: HostCancelBox())))
                    }
                    for (kind, label, location) in choices {
                        print("ACTUAL_APPLE_RECORD_BEGIN role=\(role) kind=\(label) mode=\(location.mode)")
                        fflush(stdout)
                        let request = try HostReadingWorker.request(session: session, catalog: catalog, kind: kind,
                            operation: 0, mode: location.mode, capture: location, body: kind == 1 ? "" : "Actual Apple " + label,
                            cancel: HostCancelBox())
                        let result = try HostReadingWorker.submit(request, session: session, catalog: catalog, root: profile, cancel: HostCancelBox())
                        try need(result.created == 1 && request.parser == version, "Actual Apple writer did not commit the real parser")
                        try need(request.version == 2 && request.anchor_version == (location.mode == 3 ? 3 : 2), "Actual raw request did not retain explicit writer choice")
                        let wire = try catalog.withHistory { try HostReadingWorker.retained($0, revision: request.revision).0 }
                        let decoded = try catalog.withHistory { try HostReadingWorker.decoded(wire, history: $0) }
                        let before = try session.stateHash()
                        let (recaptured, _) = try session.readingResolution(wire, catalog: catalog, cancel: HostCancelBox())
                        try need(decoded.capture == location && recaptured == location && session.stateHash() == before,
                                 "Actual raw sender wire/capture/public SDK FOUND differs or writes SDK state")
                        if role == "pdf" && kind == 3 {
                            guard let exact = location.fixed?.fields[1] else { throw HostError.invalidResult("Real PDF range exact missing") }
                            try need(!exact.isEmpty && exact.contains(0), "Real nonempty raw PDF range lost NUL")
                            let page = try HostReadingWorker.page(catalog: catalog, bookID: id, bookKey: key, from: nil, cancel: HostCancelBox())
                            guard let row = page.rows.first(where: { $0.annotation == request.annotation }) else { throw HostError.invalidResult("Actual raw typed row missing") }
                            try need(row.hasLocation && row.quoteBytes == exact && Data(row.quote.utf8) == exact, "Actual typed quote truncated NUL or lost Data")
                        }
                        let envelope = try object(wire), payload = envelope["payload"] as! [String: Any], locationJSON = payload["location"] as! [String: Any]
                        records.append(["revision_id": request.revision, "role": role, "kind": label, "mode": location.mode,
                                        "anchor_version": locationJSON["anchor_version"]!, "capture": try catalog.withHistory { try wireCapture(wire, history: $0) }])
                        checks.append("send:" + role + ":" + label)
                    }
                }
                var revisions: [[String: Any]] = []
                for (info, wire) in try outbox(catalog) {
                    let envelope = try object(wire), id = hostReadingField(info.revision_id), file = "revisions/" + id + ".json"
                    try need(sha(wire) == hostReadingField(info.sha256), "Actual retained outbox wire digest differs")
                    try wire.write(to: path(file, in: bundle))
                    revisions.append(["file": file, "id": id, "entity_kind": hostReadingField(info.entity_kind),
                                      "entity_key": hostReadingField(info.entity_key), "book_key": hostReadingField(info.book_key),
                                      "parents": envelope["parents"]!, "bytes": wire.count, "sha256": sha(wire)])
                }
                let ids = Set(revisions.map { $0["id"] as! String })
                try need(records.count == 11 && ids.count == revisions.count && revisions.contains { $0["entity_kind"] as? String == "book" }, "Actual complete history set differs")
                try need(revisions.allSatisfy { ($0["parents"] as! [String]).allSatisfy { ids.contains($0) } }, "Actual sender graph omits ancestors")
                let executable = URL(fileURLWithPath: args[0]).resolvingSymlinksInPath(), sdk = try sdkImage()
                let executableBytes = try Data(contentsOf: executable), sdkBytes = try Data(contentsOf: sdk)
                try executableBytes.write(to: bundle.appendingPathComponent("proofs/program"))
                try sdkBytes.write(to: bundle.appendingPathComponent("proofs/sdk.dylib"))
                let sender: [String: Any] = ["platform": "macos", "source_sha": env["GITHUB_SHA"]!, "run_id": env["GITHUB_RUN_ID"]!,
                    "attempt": env["GITHUB_RUN_ATTEMPT"]!, "program_sha256": sha(executableBytes), "sdk_dso_sha256": sha(sdkBytes),
                    "exr_version": version, "parser_version": version, "pid": ProcessInfo.processInfo.processIdentifier,
                    "sdk_dso_basename": sdk.lastPathComponent]
                try json(["schema": 1, "sender": sender, "originals": originals, "revisions": revisions, "reading_records": records])
                    .write(to: bundle.appendingPathComponent("manifest.json"))
                checks.append("send:complete-original-wire-and-ancestor-export")
            } else if mode == "receive" {
                let manifest = try object(Data(contentsOf: bundle.appendingPathComponent("manifest.json")))
                try need(manifest["schema"] as? Int == 1, "Unknown transport schema")
                let sender = manifest["sender"] as! [String: Any], originals = manifest["originals"] as! [[String: Any]]
                let revisions = manifest["revisions"] as! [[String: Any]], records = manifest["reading_records"] as! [[String: Any]]
                try need(originals.count == 4 && revisions.count > 11 && revisions.count <= 100 && records.count == 11, "Incomplete bounded sender set")
                let revisionIDs = Set(revisions.map { $0["id"] as! String })
                try need(revisionIDs.count == revisions.count && revisions.allSatisfy { ($0["parents"] as! [String]).allSatisfy { revisionIDs.contains($0) } }, "Transferred graph omits or duplicates actual ancestors")
                var books: [String: Int64] = [:]
                for original in originals {
                    let file: URL
                    if networkReceive {
                        file = profile.appendingPathComponent("sync/" + (original["sha256"] as! String) + "." + (original["format"] as! String))
                    } else { file = try path(original["file"] as! String, in: bundle) }
                    let data = try Data(contentsOf: file)
                    try need(data.count == original["bytes"] as! Int && sha(data) == original["sha256"] as! String, "Transferred original changed")
                    let (id, _) = try session.importBook(url: file, cancel: HostCancelBox(), catalog: catalog)
                    let actual = try library.sourceFingerprint(book: try library.books().first { $0.id == id }!)
                    try need(actual.format + ":" + actual.sha256 == original["book_key"] as! String && actual.bytes == Int64(data.count), "Actual receiving SDK original differs")
                    books[original["role"] as! String] = id
                }
                try catalog.withHistory { history in
                    for revision in revisions.reversed() {
                        let wire = try Data(contentsOf: path(revision["file"] as! String, in: bundle))
                        try need(wire.count == revision["bytes"] as! Int && sha(wire) == revision["sha256"] as! String, "Transferred wire changed")
                        if networkReceive {
                            let retained = try HostReadingWorker.retained(history, revision: revision["id"] as! String).0
                            try need(retained == wire, "Actual raw Session did not receive this exact wire; direct receive is forbidden in network phase")
                            continue
                        }
                        var info = reader_revision_info(), created: Int32 = 0, error = reader_revision_error()
                        let code = wire.withUnsafeBytes { reader_revision_receive_raw_v3(history, $0.baseAddress, $0.count, revision["sha256"] as! String, &info, &created, &error) }
                        try need(code == READER_REV_OK && hostReadingField(info.revision_id) == revision["id"] as! String, "Public receive refused original retained wire")
                    }
                }
                let retainedBefore = try outbox(catalog).map { sha($0.1) }
                for record in records {
                    let role = record["role"] as! String, id = books[role]!, revision = record["revision_id"] as! String
                    _ = try session.open(bookID: id, cancel: HostCancelBox())
                    let before = try session.stateHash()
                    let wire = try catalog.withHistory { history -> Data in
                        let retained = try HostReadingWorker.retained(history, revision: revision)
                        var graph = reader_revision_state(), error = reader_revision_error()
                        let code = reader_revision_heads_raw_v3(history, hostReadingField(retained.1.entity_kind), hostReadingField(retained.1.entity_key),
                            { _, _ in 0 }, nil, &graph, &error)
                        try need(code == READER_REV_OK && graph.missing_parents == 0 && graph.foreign_parents == 0 &&
                                 graph.projection_safe != 0 && graph.heads == 1, "Received reading graph is not a complete unique admissible head")
                        return retained.0
                    }
                    let (fresh, hit) = try session.readingResolution(wire, catalog: catalog, cancel: HostCancelBox())
                    try need(hit.bookID == id && fresh.mode == record["mode"] as! Int, "Actual receiving owner resolved another document/mode")
                    let key = originals.first { $0["role"] as? String == role }!["book_key"] as! String
                    var recaptureJSON: [String: Any] = [:], reconstructedJSON: [String: Any] = [:]
                    try catalog.withHistory { history in
                        try need(json(wireCapture(wire, history: history)) == json(record["capture"]!), "Actual retained decoded transport differs")
                        let reconstructed = try HostReadingWorker.decoded(wire, history: history).capture
                        recaptureJSON = try capture(fresh, book: key, parser: sender["parser_version"] as! String)
                        reconstructedJSON = try capture(reconstructed, book: key, parser: sender["parser_version"] as! String)
                        try need(json(recaptureJSON) == json(reconstructedJSON), "Real receiver recapture differs from actual host reconstruction")
                    }
                    try need(session.stateHash() == before && outbox(catalog).map { sha($0.1) } == retainedBefore, "Read-only receive resolution changed SDK or outbox")
                    // Transport bytes (the sender's stored decoded capture) and the host's
                    // chapter/page reconstruction are separate columns; EPUB differs by design.
                    rows.append(["role": role, "kind": record["kind"] as! String, "mode": record["mode"] as! Int,
                                 "anchor_version": record["anchor_version"] as! Int, "sender_platform": sender["platform"] as! String,
                                 "revision_id": revision, "wire_sha256": sha(wire), "found": true,
                                 "transport_capture": record["capture"]!, "recapture": recaptureJSON, "reconstruction": reconstructedJSON])
                    checks.append("receive:" + role + ":" + (record["kind"] as! String))
                }
                checks.append("receive:actual-owner-resolve-recapture-readonly")
            } else if mode == "operations" {
                let (id, _) = try session.importBook(url: resources.appendingPathComponent("Records.txt"), cancel: HostCancelBox(), catalog: catalog)
                let snapshot = try session.open(bookID: id, cancel: HostCancelBox())
                let capture = try session.readingCapture(start: snapshot.pageRange.lowerBound,
                    end: snapshot.pageRange.lowerBound + String(snapshot.pageText.prefix(8)).utf8.count, cancel: HostCancelBox())
                for version in [UInt64(1), UInt64(2)] {
                    let original = try HostReadingWorker.request(session: session, catalog: catalog, kind: 3, operation: 0,
                        mode: capture.mode, capture: capture, body: "original", anchorVersion: version, cancel: HostCancelBox())
                    _ = try HostReadingWorker.submit(original, session: session, catalog: catalog, root: profile, cancel: HostCancelBox())
                    let wire = try catalog.withHistory { try HostReadingWorker.retained($0, revision: original.revision).0 }
                    let decoded = try catalog.withHistory { try HostReadingWorker.decoded(wire, history: $0) }
                    try need(decoded.version == version && decoded.capture == capture, "Explicit old raw writer did not retain actual source version")
                    let edit = try HostReadingWorker.request(session: session, catalog: catalog, kind: 4, operation: 0,
                        annotation: original.annotation, mode: capture.mode, capture: nil, body: "edited", anchorVersion: version, cancel: HostCancelBox())
                    _ = try HostReadingWorker.submit(edit, session: session, catalog: catalog, root: profile, cancel: HostCancelBox())
                    let edited = try catalog.withHistory { try HostReadingWorker.decoded(HostReadingWorker.retained($0, revision: edit.revision).0, history: $0) }
                    try need(edited.version == version && edited.capture == capture, "NOTE_TEXT upgraded retained source")
                    let deletion = try HostReadingWorker.request(session: session, catalog: catalog, kind: 3, operation: 1,
                        annotation: original.annotation, mode: capture.mode, capture: nil, body: "", anchorVersion: version, cancel: HostCancelBox())
                    _ = try HostReadingWorker.submit(deletion, session: session, catalog: catalog, root: profile, cancel: HostCancelBox())
                    let before = try session.stateHash(), (fresh, _) = try session.readingResolution(wire, catalog: catalog, cancel: HostCancelBox())
                    let restore = try HostReadingWorker.request(session: session, catalog: catalog, kind: 3, operation: 2,
                        annotation: original.annotation, mode: capture.mode, capture: fresh, body: decoded.body,
                        observedHeads: [deletion.revision], anchorVersion: decoded.version, cancel: HostCancelBox())
                    try need(restore.version == 2 && restore.anchor_version == version, "New private restore did not persist its source writer")
                    _ = try HostReadingWorker.submit(restore, session: session, catalog: catalog, root: profile, cancel: HostCancelBox())
                    let restored = try catalog.withHistory { try HostReadingWorker.decoded(HostReadingWorker.retained($0, revision: restore.revision).0, history: $0) }
                    try need(restored.version == version && restored.capture == capture && session.stateHash() == before,
                             "Explicit restore upgraded source wire or navigated/wrote SDK state")
                    checks.append("actual-source-\(version)-NOTE_TEXT-delete-restore-keeps-version-selector-and-SDK-state")
                }
                let (pdfID, _) = try session.importBook(url: resources.appendingPathComponent("Sample.pdf"), cancel: HostCancelBox(), catalog: catalog)
                _ = try session.open(bookID: pdfID, cancel: HostCancelBox())
                let point = try session.readingCapture(cancel: HostCancelBox())
                let request = try HostReadingWorker.request(session: session, catalog: catalog, kind: 2, operation: 0,
                    mode: point.mode, capture: point, body: "real point", cancel: HostCancelBox())
                _ = try HostReadingWorker.submit(request, session: session, catalog: catalog, root: profile, cancel: HostCancelBox())
                let original = try catalog.withHistory { try HostReadingWorker.retained($0, revision: request.revision).0 }
                var null = try object(original), payload = null["payload"] as! [String: Any]
                var location = payload["location"] as! [String: Any], selector = location["selector"] as! [String: Any]
                selector["exact"] = ["base64": NSNull(), "size": 0]
                location["selector"] = selector; payload["location"] = location
                null["payload"] = payload; null["id"] = HostReadingRequest.newID(); null["parents"] = [request.revision]
                let nullable = try json(null)
                try catalog.withHistory { history in
                    var info = reader_revision_info(), created: Int32 = 0, error = reader_revision_error()
                    let result = nullable.withUnsafeBytes { reader_revision_receive_raw_v3(history, $0.baseAddress, $0.count, sha(nullable), &info, &created, &error) }
                    try need(result == READER_REV_OK && created == 1, "Explicit NULL negative was not losslessly retained")
                }
                let typed = try HostReadingWorker.page(catalog: catalog, bookID: pdfID, bookKey: request.bookKey, from: nil, cancel: HostCancelBox())
                guard let row = typed.rows.first(where: { $0.annotation == request.annotation }) else { throw HostError.invalidResult("NULL negative typed row missing") }
                try need(row.safe && !row.hasLocation && row.quote.isEmpty && row.quoteBytes == nil, "NULL exact became a usable typed location")
                let before = try session.stateHash()
                var refused = false
                do { _ = try session.readingResolution(nullable, catalog: catalog, cancel: HostCancelBox()) } catch { refused = true }
                try need(refused && session.stateHash() == before, "NULL exact navigated or changed actual SDK state")
                checks.append("explicit-NULL-negative-keeps-bytes-but-never-content-or-navigation")
            } else if mode == "null-receive" {
                // An Android-produced NULL-exact transport expression: public receive keeps the
                // bytes, but it may never become a typed location, capture, FOUND or navigation.
                let manifest = try object(Data(contentsOf: bundle.appendingPathComponent("manifest.json")))
                try need(manifest["schema"] as? Int == 1 && manifest["purpose"] as? String == "authentic-android-null-negative", "Unknown NULL transport")
                let sender = manifest["sender"] as! [String: Any]
                let original = (manifest["originals"] as! [[String: Any]])[0], revisions = manifest["revisions"] as! [[String: Any]]
                let nullID = manifest["null_revision"] as! String, annotation = manifest["annotation_id"] as! String
                try need(sender["platform"] as? String == "android" && original["role"] as? String == "pdf" && revisions.count >= 2, "Incomplete NULL transport")
                let file = try path(original["file"] as! String, in: bundle)
                let data = try Data(contentsOf: file)
                try need(data.count == original["bytes"] as! Int && sha(data) == original["sha256"] as! String, "Transferred NULL original changed")
                let (pdfID, _) = try session.importBook(url: file, cancel: HostCancelBox(), catalog: catalog)
                let actual = try library.sourceFingerprint(book: try library.books().first { $0.id == pdfID }!)
                try need(actual.format + ":" + actual.sha256 == original["book_key"] as! String && actual.bytes == Int64(data.count), "Actual receiving SDK original differs")
                var nullWire: Data?
                try catalog.withHistory { history in
                    for revision in revisions.reversed() {
                        let wire = try Data(contentsOf: path(revision["file"] as! String, in: bundle))
                        try need(wire.count == revision["bytes"] as! Int && sha(wire) == revision["sha256"] as! String, "Transferred NULL-graph wire changed")
                        var info = reader_revision_info(), created: Int32 = 0, error = reader_revision_error()
                        let code = wire.withUnsafeBytes { reader_revision_receive_raw_v3(history, $0.baseAddress, $0.count, revision["sha256"] as! String, &info, &created, &error) }
                        try need(code == READER_REV_OK && hostReadingField(info.revision_id) == revision["id"] as! String, "Public receive refused the NULL-graph wire")
                        if revision["id"] as! String == nullID { nullWire = wire }
                    }
                }
                guard let wire = nullWire else { throw HostError.invalidResult("NULL revision missing from transport") }
                let stored = try catalog.withHistory { try HostReadingWorker.retained($0, revision: nullID).0 }
                try need(stored == wire, "Actual retained NULL bytes changed")
                _ = try session.open(bookID: pdfID, cancel: HostCancelBox())
                let before = try session.stateHash(), outboxBefore = try outbox(catalog).map { sha($0.1) }
                let typed = try HostReadingWorker.page(catalog: catalog, bookID: pdfID, bookKey: original["book_key"] as! String, from: nil, cancel: HostCancelBox())
                guard let row = typed.rows.first(where: { $0.annotation == annotation }) else { throw HostError.invalidResult("Android NULL typed row missing") }
                try need(row.safe && !row.hasLocation && row.quote.isEmpty && row.quoteBytes == nil, "Android NULL exact became a usable typed location")
                var refused = false
                do { _ = try session.readingResolution(wire, catalog: catalog, cancel: HostCancelBox()) } catch { refused = true }
                try need(refused && session.stateHash() == before && outbox(catalog).map { sha($0.1) } == outboxBefore, "Android NULL exact navigated or changed actual state")
                rows.append(["role": "pdf", "kind": "null-expression", "revision_id": nullID, "wire_sha256": sha(wire), "found": false,
                             "typed_has_location": row.hasLocation, "typed_quote_nil": row.quoteBytes == nil, "navigation_refused": refused,
                             "sender_platform": sender["platform"] as! String])
                checks.append("null-receive:android-null-keeps-bytes-never-capture-found-or-navigation")
            } else { throw HostError.invalidInput("Unknown interop mode") }
        }
        let loadedSDK = try sdkImage()
        let result: [String: Any] = ["accepted": true, "source_sha": env["GITHUB_SHA"]!, "run_id": env["GITHUB_RUN_ID"]!,
            "attempt": env["GITHUB_RUN_ATTEMPT"]!, "pid": ProcessInfo.processInfo.processIdentifier, "mode": requestedMode,
            "checks": checks, "records": rows, "exr_version": version,
            "actual_native_session": sessionProof,
            "program_sha256": sha(try Data(contentsOf: URL(fileURLWithPath: args[0]).resolvingSymlinksInPath())),
            "sdk_dso_basename": loadedSDK.lastPathComponent, "sdk_dso_sha256": sha(try Data(contentsOf: loadedSDK)),
            "actual_android_host_interop_accepted": false,
            "host_ui_accepted": false, "physical_device_accepted": false]
        try json(result).write(to: report)
        print("ACTUAL_APPLE_RECORD_INTEROP " + String(decoding: try json(result), as: UTF8.self))
    }
}
