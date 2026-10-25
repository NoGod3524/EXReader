// SPDX-License-Identifier: MIT
#if EXR_APPLE_RAW3_REVIEW && EXR_APPLE_HOST_REVIEW
import Foundation
import CryptoKit
import CEXReader
import CReaderProduct
import MachO

// Test observations only. Callers stay on the actual host owner queue. This
// observer reads existing handles and files; it never opens an SDK connection,
// submits a revision, changes a selector, or runs an extra resolver.
enum HostRaw3Review {
    static func digest(_ value: Data) -> String {
        SHA256.hash(data: value).map { String(format: "%02x", $0) }.joined()
    }
    static var caseName: String {
        let values = CommandLine.arguments
        if let index = values.firstIndex(of: "-EXRRaw3Case"), index + 1 < values.count { return values[index + 1] }
        return "unlabelled"
    }
    static func encoded<T: Encodable>(_ value: T) throws -> Any {
        try JSONSerialization.jsonObject(with: JSONEncoder().encode(value))
    }
    static func emit(_ payload: [String: Any], root: URL) throws {
        let directory = root.appendingPathComponent("raw3-review", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        var value = payload
        value["case"] = caseName
        value["source_sha"] = Bundle.main.object(forInfoDictionaryKey: "EXRSourceSHA") as? String ?? ""
        value["sdk_version"] = String(cString: exr_version())
        value["pid"] = ProcessInfo.processInfo.processIdentifier
#if EXR_APPLE_RAW3
        value["raw_enabled"] = true
#else
        value["raw_enabled"] = false
#endif
        let images = (0..<_dyld_image_count()).compactMap { _dyld_get_image_name($0).map { URL(fileURLWithPath: String(cString: $0)) } }
            .filter { $0.lastPathComponent.hasPrefix("libexreader") && $0.pathExtension == "dylib" }
        value["sdk_images"] = try images.map { ["name": $0.lastPathComponent, "sha256": digest(try Data(contentsOf: $0))] }
        let data = try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys, .prettyPrinted])
        try data.write(to: directory.appendingPathComponent(UUID().uuidString + ".json"), options: .atomic)
    }
    static func audit(session: HostSession, catalog: HostCatalog, root: URL, event: String,
                      submission: HostReadingRequest? = nil, created: Int32? = nil) throws {
        let before = try session.stateHash()
        let count = try catalog.scalar("SELECT count(*) FROM reader_revisions")
        let ids: [String]
        if count == 0 { ids = [] }
        else { ids = try catalog.text("SELECT group_concat(revision_id, ',') FROM (SELECT revision_id FROM reader_revisions ORDER BY revision_id)").split(separator: ",").map(String.init) }
        var rows: [[String: Any]] = []
        try catalog.withHistory { history in
            for id in ids {
                let (wire, info) = try HostReadingWorker.retained(history, revision: id)
                var value: [String: Any] = ["id": id, "wire_base64": wire.base64EncodedString(), "bytes": wire.count,
                    "sha256": digest(wire), "entity_kind": hostReadingField(info.entity_kind)]
                let json = try JSONSerialization.jsonObject(with: wire) as! [String: Any]
                if ["annotation", "progress"].contains(hostReadingField(info.entity_kind)), json["payload"] is [String: Any] {
                    let decoded = try HostReadingWorker.decoded(wire, history: history)
                    value["anchor_version"] = decoded.version
                    value["capture"] = try encoded(decoded.capture)
                }
                rows.append(value)
            }
        }
        var typed: [[String: Any]] = []
        var original: [String: Any] = [:]
        if let book = session.book {
            let fingerprint = try session.library.sourceFingerprint(book: book)
            original = ["book_id": book.id, "format": fingerprint.format, "sha256": fingerprint.sha256, "bytes": fingerprint.bytes]
            let product = try catalog.readingBook(sdkID: book.id)
            let page = try HostReadingWorker.page(catalog: catalog, bookID: book.id, bookKey: product.key, from: nil, cancel: HostCancelBox())
            let progress = try HostReadingWorker.progress(catalog: catalog, bookID: book.id, bookKey: product.key)
            for row in (progress.map { [$0] } ?? []) + page.rows {
                typed.append(["revision": row.revision, "safe": row.safe, "has_location": row.hasLocation,
                    "kind": row.kind, "quote_utf8_base64": Data(row.quote.utf8).base64EncodedString(),
                    "quote_bytes_base64": row.quoteBytes?.base64EncodedString() as Any? ?? NSNull()])
            }
        }
        let pending = root.appendingPathComponent("reading-requests/request.json")
        let pendingBytes: Data?
        if FileManager.default.fileExists(atPath: pending.path) { pendingBytes = try Data(contentsOf: pending) }
        else { pendingBytes = nil }
        var value: [String: Any] = ["event": event, "revisions": rows, "typed_rows": typed, "original": original,
            "sdk_state_before": before, "sdk_state_after": try session.stateHash(),
            "pending_base64": pendingBytes?.base64EncodedString() as Any? ?? NSNull()]
        if let submission { value["submission"] = try encoded(submission) }
        if let created { value["created"] = created }
        try emit(value, root: root)
    }
    static func resolution(wire: Data, original: HostReadingCapture, fresh: HostReadingCapture,
                           session: HostSession, before: String) throws {
        try emit(["event": "actual-public-resolution", "wire_sha256": digest(wire), "wire_base64": wire.base64EncodedString(),
            "original": try encoded(original), "fresh": try encoded(fresh), "found": true,
            "sdk_state_before": before, "sdk_state_after": try session.stateHash()], root: session.library.path.deletingLastPathComponent())
    }
}
#endif
