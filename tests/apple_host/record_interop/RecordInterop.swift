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

@main struct RecordInterop {
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
            let status = reader_revision_outbox(history, 100, interopOutbox, Unmanaged.passUnretained(rows).toOpaque(), &error)
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
    static func main() throws {
        let args = CommandLine.arguments, env = ProcessInfo.processInfo.environment
        try need(env["GITHUB_ACTIONS"] == "true" && args.count == 6, "Actions-only actual host interop")
        let mode = args[1], resources = URL(fileURLWithPath: args[2]), profile = URL(fileURLWithPath: args[3])
        let bundle = URL(fileURLWithPath: args[4]), report = URL(fileURLWithPath: args[5])
        let version = String(cString: exr_version())
        try need(version == "3.41.0", "Actual SDK is not the explicit candidate")
        try FileManager.default.createDirectory(at: profile, withIntermediateDirectories: true)
        let queue = DispatchQueue(label: "actual.apple.record.interop.owner")
        var checks: [String] = [], rows: [[String: Any]] = []
        try queue.sync {
            let library = try HostLibrary(path: profile.appendingPathComponent("library.sqlite"))
            let catalog = try HostCatalog(path: profile.appendingPathComponent("catalog.sqlite"),
                migrationURL: resources.appendingPathComponent("reader-catalog-v1.sql"), ownerQueue: queue)
            defer { try? catalog.close() }
            let font = try HostFont(data: Data(contentsOf: resources.appendingPathComponent("Reader.otf")))
            let session = HostSession(library: library, font: font, slowDelay: 0,
                                      viewport: CGSize(width: 480, height: 640), fontSize: 28)
            if mode == "send" {
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
                    try library.exportSyncOriginal(bookID: id, expected: fingerprint,
                        directory: bundle.appendingPathComponent("originals"), cancel: HostCancelBox())
                    originals.append(["role": role, "file": "originals/" + fingerprint.sha256 + "." + fingerprint.format,
                                      "format": fingerprint.format, "book_key": key, "bytes": fingerprint.bytes, "sha256": fingerprint.sha256])
                    let point = try session.readingCapture(cancel: HostCancelBox())
                    var choices: [(Int, String, HostReadingCapture)] = [(1, "progress", point), (2, "bookmark", point)]
                    if role != "cbz" {
                        guard let first = snapshot.pageText.unicodeScalars.first else { throw HostError.invalidResult("Real range text missing: " + role) }
                        let start = snapshot.pageRange.lowerBound, end = start + String(first).utf8.count
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
                        let wire = try catalog.withHistory { try HostReadingWorker.retained($0, revision: request.revision).0 }
                        let envelope = try object(wire), payload = envelope["payload"] as! [String: Any], locationJSON = payload["location"] as! [String: Any]
                        records.append(["revision_id": request.revision, "role": role, "kind": label, "mode": location.mode,
                                        "anchor_version": locationJSON["anchor_version"]!, "capture": try capture(location, book: key, parser: request.parser)])
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
                    let file = try path(original["file"] as! String, in: bundle), data = try Data(contentsOf: file)
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
                        var info = reader_revision_info(), created: Int32 = 0, error = reader_revision_error()
                        let code = wire.withUnsafeBytes { reader_revision_receive(history, $0.baseAddress, $0.count, revision["sha256"] as! String, &info, &created, &error) }
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
                        let code = reader_revision_heads(history, hostReadingField(retained.1.entity_kind), hostReadingField(retained.1.entity_key),
                            { _, _ in 0 }, nil, &graph, &error)
                        try need(code == READER_REV_OK && graph.missing_parents == 0 && graph.foreign_parents == 0 &&
                                 graph.projection_safe != 0 && graph.heads == 1, "Received reading graph is not a complete unique admissible head")
                        return retained.0
                    }
                    let (fresh, hit) = try session.readingResolution(wire, catalog: catalog, cancel: HostCancelBox())
                    try need(hit.bookID == id && fresh.mode == record["mode"] as! Int, "Actual receiving owner resolved another document/mode")
                    try need(json(capture(fresh, book: originals.first { $0["role"] as? String == role }!["book_key"] as! String,
                                          parser: sender["parser_version"] as! String)) == json(record["capture"]!), "Real receiver recapture differs")
                    try need(session.stateHash() == before && outbox(catalog).map { sha($0.1) } == retainedBefore, "Read-only receive resolution changed SDK or outbox")
                    rows.append(["role": role, "revision_id": revision, "wire_sha256": sha(wire), "found": true])
                    checks.append("receive:" + role + ":" + (record["kind"] as! String))
                }
                checks.append("receive:actual-owner-resolve-recapture-readonly")
            } else { throw HostError.invalidInput("Unknown interop mode") }
        }
        let result: [String: Any] = ["accepted": true, "source_sha": env["GITHUB_SHA"]!, "run_id": env["GITHUB_RUN_ID"]!,
            "attempt": env["GITHUB_RUN_ATTEMPT"]!, "pid": ProcessInfo.processInfo.processIdentifier, "mode": mode,
            "checks": checks, "records": rows, "exr_version": version, "actual_android_host_interop_accepted": false,
            "host_ui_accepted": false, "physical_device_accepted": false]
        try json(result).write(to: report)
        print("ACTUAL_APPLE_RECORD_INTEROP " + String(decoding: try json(result), as: UTF8.self))
    }
}
