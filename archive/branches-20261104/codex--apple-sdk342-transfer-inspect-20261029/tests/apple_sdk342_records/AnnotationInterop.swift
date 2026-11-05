// SPDX-License-Identifier: MIT
// Actual Apple owner export/import probe. Run only after the independent
// 3.41-to-3.42 selector semantic proof and production policy admission.
import Foundation
import CoreGraphics
import CryptoKit
import CEXReader
import CReaderProduct

@main struct AnnotationInterop {
    static func need(_ value: Bool, _ message: String) throws {
        if !value { throw HostError.invalidResult(message) }
    }
    static func main() throws {
        let a = CommandLine.arguments, env = ProcessInfo.processInfo.environment
        guard env["GITHUB_ACTIONS"] == "true", a.count == 6 else { throw HostError.invalidInput("Actions-only probe") }
        let mode = a[1], resources = URL(fileURLWithPath: a[2]), root = URL(fileURLWithPath: a[3])
        let exchange = URL(fileURLWithPath: a[4]), report = URL(fileURLWithPath: a[5])
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        let queue = DispatchQueue(label: "apple.sdk342.annotation.owner")
        var checks: [String] = []
        try queue.sync {
            let library = try HostLibrary(path: root.appendingPathComponent("library.sqlite"))
            let catalog = try HostCatalog(path: root.appendingPathComponent("catalog.sqlite"),
                migrationURL: resources.appendingPathComponent("reader-catalog-v1.sql"), ownerQueue: queue)
            defer { try? catalog.close() }
            let font = try HostFont(data: Data(contentsOf: resources.appendingPathComponent("Reader.otf")))
            let session = HostSession(library: library, font: font, slowDelay: 0,
                viewport: CGSize(width: 480, height: 640), fontSize: 28)
            let cancel = HostCancelBox()
            let (id, _) = try session.importBook(url: resources.appendingPathComponent("AnchorSource.pdf"), cancel: cancel, catalog: catalog)
            let frame = try session.open(bookID: id, cancel: cancel)
            let book = try catalog.readingBook(sdkID: id)
            guard let range = frame.pageText.range(of: "UniqueSelectionTarget") else { throw HostError.invalidResult("Actual PDF selection missing") }
            let start = frame.pageRange.lowerBound + frame.pageText[..<range.lowerBound].utf8.count
            let capture = try session.readingCapture(start: start,
                end: start + frame.pageText[range].utf8.count, cancel: cancel)
            if mode == "produce" {
                try need(String(cString: exr_version()) == "3.41.0", "Producer is not SDK 3.41")
                let request = try HostReadingWorker.request(session: session, catalog: catalog, kind: 3,
                    operation: 0, mode: capture.mode, capture: capture, body: "", anchorVersion: 3, cancel: cancel)
                try need(request.writerVersion == 3 && request.capture?.fixed?.start != request.capture?.fixed?.end,
                    "Producer did not capture a nonempty RAW3 PDF selection")
                let submitted = try HostReadingWorker.submit(request, session: session, catalog: catalog, root: root, cancel: cancel)
                try need(submitted.created == 1 && request.parser == "3.41.0", "Producer did not commit actual 3.41 annotation")
                let wire = try catalog.withHistory { try HostReadingWorker.retained($0, revision: request.revision).0 }
                let url = try HostWave3Worker.exportAnnotations(catalog: catalog, key: book.key, directory: exchange, markdown: false, cancel: cancel)
                let bytes = try Data(contentsOf: url)
                let saved: [String: Any] = ["revision": request.revision, "book_key": book.key, "parser": request.parser,
                    "wire_sha256": SHA256.hash(data: wire).map { String(format: "%02x", $0) }.joined(),
                    "export_sha256": SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined(), "file": url.lastPathComponent]
                try JSONSerialization.data(withJSONObject: saved, options: [.sortedKeys, .prettyPrinted])
                    .write(to: exchange.appendingPathComponent("producer.json"), options: .atomic)
                checks += ["actual-341-raw3-highlight-created", "actual-341-jsonl-exported"]
            } else if mode == "consume" {
                try need(String(cString: exr_version()) == "3.42.0", "Receiver is not SDK 3.42")
                let saved = try JSONSerialization.jsonObject(with: Data(contentsOf: exchange.appendingPathComponent("producer.json"))) as! [String: String]
                try need(saved["book_key"] == book.key && saved["parser"] == "3.41.0", "Original identity or parser differs")
                let file = exchange.appendingPathComponent(saved["file"]!)
                let bytes = try Data(contentsOf: file)
                try need(SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined() == saved["export_sha256"], "Export bytes changed")
                // Bootstrap the same source identity with a local progress record;
                // it does not insert the exported annotation revision.
                let point = try session.readingCapture(cancel: cancel)
                let seed = try HostReadingWorker.request(session: session, catalog: catalog, kind: 1,
                    operation: 0, mode: point.mode, capture: point, body: "", cancel: cancel)
                _ = try HostReadingWorker.submit(seed, session: session, catalog: catalog, root: root, cancel: cancel)
                let resolver = try HostWave3AnnotationResolver(library: library, font: font, bookID: id, key: book.key, cancel: cancel)
                func apply(_ confirmation: String?) throws -> HostWave3AnnotationPreview {
                    try HostWave3Worker.annotations(catalog: catalog, key: book.key, file: file,
                        confirmation: confirmation, cancel: cancel) { try resolver.resolve($0) }
                }
                let revisions = try catalog.scalar("SELECT count(*) FROM reader_revisions")
                let outbox = try catalog.scalar("SELECT count(*) FROM reader_outbox")
                let preview = try apply(nil)
                try need(preview.found == 1 && preview.unresolved == 0 && preview.wouldCreate == 1 && preview.wouldDuplicate == 0,
                    "Original annotation did not preview as uniquely resolved new head")
                try need(catalog.scalar("SELECT count(*) FROM reader_revisions") == revisions && catalog.scalar("SELECT count(*) FROM reader_outbox") == outbox, "Preview mutated history")
                let commit = try apply(preview.fingerprint)
                try need(commit.committed == 1 && commit.receivingGraphChecked, "Original annotation commit failed")
                let after = try catalog.scalar("SELECT count(*) FROM reader_revisions")
                try need(after == revisions + 1 && catalog.scalar("SELECT count(*) FROM reader_outbox") == outbox, "Import changed unrelated history or outbox")
                let wire = try catalog.withHistory { try HostReadingWorker.retained($0, revision: saved["revision"]!).0 }
                try need(SHA256.hash(data: wire).map { String(format: "%02x", $0) }.joined() == saved["wire_sha256"], "Imported original wire changed")
                let decoded = try catalog.withHistory { try HostReadingWorker.decoded(wire, history: $0) }
                try need(decoded.book == book.key, "Imported original identity differs")
                let duplicate = try apply(nil)
                try need(duplicate.found == 1 && duplicate.unresolved == 0 && duplicate.wouldCreate == 0 && duplicate.wouldDuplicate == 1,
                    "Second preview did not identify exact duplicate")
                let repeated = try apply(duplicate.fingerprint)
                try need(repeated.committed == 1 && catalog.scalar("SELECT count(*) FROM reader_revisions") == after &&
                         catalog.scalar("SELECT count(*) FROM reader_outbox") == outbox, "Duplicate import changed history or outbox")
                guard let anchor = decoded.capture.fixed, let pageID = anchor.fields[0].map({ String(decoding: $0, as: UTF8.self) }) else {
                    throw HostError.invalidResult("Retained RAW3 fixed-page selector missing")
                }
                for (name, expected) in [("AnchorMissing.pdf", EXR_ANCHOR_MISSING), ("AnchorAmbiguous.pdf", EXR_ANCHOR_AMBIGUOUS)] {
                    let (otherID, _) = try session.importBook(url: resources.appendingPathComponent(name), cancel: cancel, catalog: catalog)
                    let fixed = try library.fixed(bookID: otherID, font: font, cancel: cancel)
                    try need(fixed.pageIDs.count == 1 && fixed.pageIDs[0] == pageID, "Altered fixture page identity differs")
                    let text = try fixed.text(page: 0, cancel: cancel)
                    let state = try anchor.withInput { try text.resolve($0, pageID: pageID, cancel: cancel).state }
                    try need(state == expected, "Public fixed anchor result differs for " + name)
                    var refused = false
                    do { _ = try HostWave3AnnotationResolver(library: library, font: font, bookID: otherID, key: book.key, cancel: cancel) }
                    catch { refused = true }
                    try need(refused, "Altered original was accepted by owner")
                }
                checks += ["original-341-jsonl-and-book-identity", "342-found-preview-read-only", "342-first-import-exact-wire",
                           "342-decode-original", "342-repeat-exact-duplicate-no-history-or-outbox",
                           "342-original-selector-missing-and-ambiguous", "owner-rejects-altered-originals"]
            } else { throw HostError.invalidInput("Unknown mode") }
        }
        let result: [String: Any] = ["accepted": true, "mode": mode, "checks": checks,
            "sdk": String(cString: exr_version()), "source_sha": env["GITHUB_SHA"] ?? "",
            "run_id": env["GITHUB_RUN_ID"] ?? "", "attempt": env["GITHUB_RUN_ATTEMPT"] ?? "",
            "physical_device": false, "android_sender": false]
        try JSONSerialization.data(withJSONObject: result, options: [.sortedKeys, .prettyPrinted]).write(to: report, options: .atomic)
        print("APPLE_ANNOTATION_INTEROP " + String(decoding: try JSONSerialization.data(withJSONObject: result, options: [.sortedKeys]), as: UTF8.self))
    }
}
