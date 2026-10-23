// SPDX-License-Identifier: MIT
import Foundation
import CoreGraphics
import CryptoKit
import CEXReader

@main
struct MappingReview {
    static func expect(_ value: Bool, _ message: String) throws {
        if !value { throw HostError.invalidResult(message) }
    }
    static func digest(_ data: Data) -> String {
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }
    static func rejected(_ operation: () throws -> Void) -> Bool {
        do { try operation(); return false } catch { return true }
    }
    static func cancelled(_ operation: () throws -> Void) -> Bool {
        do { try operation(); return false }
        catch HostError.cancelled { return true }
        catch { return false }
    }
    static func legacy(_ library: HostLibrary, file: URL, bounded: Bool) throws -> Int64 {
        var id: Int64 = 0, error = exr_error()
        if bounded {
            try file.path.withCString { path in
                try hostCheck(exr_library_import_file(library.handle, EXR_EPUB, path, "historical bounded", &id, &error), error)
            }
        } else {
            let bytes = try Data(contentsOf: file)
            try bytes.withUnsafeBytes {
                try hostCheck(exr_library_import(library.handle, EXR_EPUB, $0.baseAddress, $0.count,
                                                  "historical snapshot", &id, &error), error)
            }
        }
        return id
    }

    static func main() throws {
        let environment = ProcessInfo.processInfo.environment
        guard environment["GITHUB_ACTIONS"] == "true" else { throw HostError.invalidInput("Cloud execution only") }
        let resources = URL(fileURLWithPath: CommandLine.arguments[1])
        let output = URL(fileURLWithPath: CommandLine.arguments[2])
        try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
        let queue = DispatchQueue(label: "org.exreader.host.mapping-review")
        var checks: [[String: Any]] = []
        queue.sync {
            var observations: [String: Any] = [:]
            func check(_ name: String, _ operation: () throws -> Void) {
                observations = [:]
                var row: [String: Any] = ["id": name, "passed": false]
                do { try operation(); row["passed"] = true }
                catch { row["error"] = error.localizedDescription }
                HostSDKReview.event = nil
                row["observations"] = observations
                checks.append(row)
                if let data = try? JSONSerialization.data(withJSONObject: ["mapping_check": row], options: [.sortedKeys]) {
                    FileHandle.standardOutput.write(data); FileHandle.standardOutput.write(Data([10]))
                }
            }
            struct Context {
                let folder: URL
                let library: HostLibrary
                let catalog: HostCatalog
                let session: HostSession
                var staging: URL { folder.appendingPathComponent("import-staging") }
            }
            func context(_ name: String) throws -> Context {
                let folder = output.appendingPathComponent(name)
                try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
                let library = try HostLibrary(path: folder.appendingPathComponent("library.sqlite"))
                let catalog = try HostCatalog(path: folder.appendingPathComponent("reader-catalog.db"),
                    migrationURL: resources.appendingPathComponent("reader-catalog-v1.sql"), ownerQueue: queue)
                let font = try HostFont(data: Data(contentsOf: resources.appendingPathComponent("Reader.otf")))
                return Context(folder: folder, library: library, catalog: catalog,
                    session: HostSession(library: library, font: font, slowDelay: 0,
                                         viewport: CGSize(width: 480, height: 640), fontSize: 28))
            }
            func file(_ context: Context, name: String = "source.txt", data: Data = Data("Stable original reading text.".utf8)) throws -> URL {
                let path = context.folder.appendingPathComponent(name)
                try data.write(to: path)
                return path
            }
            func emptyStaging(_ context: Context) throws {
                let count = (try? FileManager.default.contentsOfDirectory(atPath: context.staging.path).count) ?? 0
                try expect(count == 0, "Private copy leaked after completion or failure")
            }
            func mapped(_ context: Context, _ path: URL, cancel: HostCancelBox = HostCancelBox()) throws -> (Int64, Bool) {
                try context.session.importBook(url: path, cancel: cancel, catalog: context.catalog)
            }

            check("maps-public-sources-and-three-location-modes") {
                let c = try context("modes"); defer { try? c.catalog.close() }
                for path in [resources.appendingPathComponent("Sample.epub"), resources.appendingPathComponent("Sample.pdf"), try file(c)] {
                    let (id, created) = try mapped(c, path)
                    try expect(created, "Fresh fixture reused an unrelated book")
                    let book = try c.library.books().first { $0.id == id }!
                    let identity = try c.library.sourceFingerprint(book: book)
                    let bytes = try Data(contentsOf: path)
                    try expect(identity.sha256 == digest(bytes) && identity.bytes == bytes.count, "Stored original SHA/length differs")
                    try expect(try c.catalog.text("SELECT book_key FROM reader_local_books WHERE sdk_book_id=\(id)") == identity.format + ":" + digest(bytes), "Global identity differs")
                }
                for kind in ["epub_chapter", "reflow_global", "fixed_page"] {
                    try expect(try c.catalog.scalar("SELECT count(*) FROM reader_local_books WHERE location_kind='\(kind)'") == 1, "Actual location mode missing")
                }
                try emptyStaging(c)
            }

            for boundedFirst in [false, true] {
                check(boundedFirst ? "historical-duplicates-select-oldest-bounded-mode" : "historical-duplicates-select-oldest-snapshot-mode") {
                    let c = try context(boundedFirst ? "bounded-first" : "snapshot-first"); defer { try? c.catalog.close() }
                    let path = resources.appendingPathComponent("Sample.epub")
                    let oldest = try legacy(c.library, file: path, bounded: boundedFirst)
                    let newer = try legacy(c.library, file: path, bounded: !boundedFirst)
                    let books = try c.library.books()
                    let high = books.first { $0.id == newer }!
                    let highIdentity = try c.library.sourceFingerprint(book: high)
                    try c.catalog.attach(book: high, fingerprint: highIdentity, library: c.library)
                    let failures = try c.catalog.repairMissing(library: c.library, books: Array(books.reversed()))
                    try expect(failures.isEmpty, "Historical repair failed")
                    try expect(try c.catalog.scalar("SELECT sdk_book_id FROM reader_local_books") == oldest, "Did not select minimum SDK ID")
                    try expect(try c.catalog.text("SELECT location_kind FROM reader_local_books") == (boundedFirst ? "epub_chapter" : "reflow_global"), "Selected the other duplicate's mode")
                    try expect(try c.library.books().count == 2 && c.catalog.scalar("SELECT count(*) FROM reader_books") == 1, "Historical SDK duplicate was deleted")
                    observations = ["oldest_sdk_id": oldest, "newer_sdk_id": newer, "oldest_bounded": boundedFirst]
                }
            }

            check("retains-metadata-deletion-revisions-and-outbox") {
                let c = try context("metadata"); defer { try? c.catalog.close() }
                let path = try file(c)
                _ = try mapped(c, path)
                let revision = String(repeating: "a", count: 32), hash = digest(Data("{}".utf8))
                try c.catalog.execute("UPDATE reader_books SET title='User title',author='User author',sort_title='custom sort',favorite=1,deleted=1; INSERT INTO reader_revisions VALUES('\(revision)','book',(SELECT book_key FROM reader_books),'delete','{}','\(hash)'); INSERT INTO reader_outbox(revision_id,attempts,last_error) VALUES('\(revision)',3,'retained');")
                let before = try c.catalog.text("SELECT title||'|'||author||'|'||sort_title||'|'||favorite||'|'||deleted FROM reader_books")
                let (_, created) = try mapped(c, path)
                try expect(!created, "Repeated source created a new SDK row")
                try expect(try c.catalog.text("SELECT title||'|'||author||'|'||sort_title||'|'||favorite||'|'||deleted FROM reader_books") == before, "Import replaced user metadata or restored deletion")
                try expect(try c.catalog.scalar("SELECT count(*) FROM reader_tombstones") == 1 && c.catalog.scalar("SELECT attempts FROM reader_outbox") == 3, "Import changed revision/outbox history")
                try expect(try c.catalog.text("SELECT last_error FROM reader_outbox") == "retained", "Import rewrote outbox state")
            }

            check("normalizes-sort-title-only-and-binds-unicode") {
                let c = try context("unicode"); defer { try? c.catalog.close() }
                let title = "Cafe\u{301} ' 阅读😀.txt"
                let path = try file(c, name: title)
                let (id, _) = try mapped(c, path)
                let storedTitle = try c.library.books().first { $0.id == id }!.title
                try expect(try Array(c.catalog.text("SELECT title FROM reader_books").utf8) == Array(storedTitle.utf8), "Display title bytes changed")
                try expect(try Array(c.catalog.text("SELECT sort_title FROM reader_books").utf8) == Array(storedTitle.precomposedStringWithCanonicalMapping.utf8), "Sort title is not NFC")
            }

            check("same-original-different-format-has-separate-global-key") {
                let c = try context("format-key"); defer { try? c.catalog.close() }
                let bytes = Data("<html><body><p>The same original bytes.</p></body></html>".utf8)
                _ = try mapped(c, file(c, name: "same.txt", data: bytes))
                _ = try mapped(c, file(c, name: "same.html", data: bytes))
                try expect(try c.catalog.scalar("SELECT count(*) FROM reader_books") == 2, "Format was omitted from global key")
                try expect(try c.catalog.scalar("SELECT count(DISTINCT source_sha256) FROM reader_books") == 1, "Exact original bytes changed")
            }

            check("pre-cancel-creates-neither-copy-nor-book") {
                let c = try context("pre-cancel"); defer { try? c.catalog.close() }
                let path = try file(c), box = HostCancelBox(); box.cancel()
                try expect(cancelled { _ = try mapped(c, path, cancel: box) }, "Pre-cancel was not honored")
                try expect(try c.library.books().isEmpty && c.catalog.localIDs().isEmpty, "Pre-cancel changed storage")
                try emptyStaging(c)
            }

            check("bounded-copy-cancel-cleans-private-copy") {
                let c = try context("copy-cancel"); defer { try? c.catalog.close() }
                let path = try file(c, data: Data(repeating: 65, count: 200_000)), box = HostCancelBox()
                HostSDKReview.event = { if $0 == "private-copy-read" { box.cancel() } }
                try expect(cancelled { _ = try mapped(c, path, cancel: box) }, "Copy cancellation was not honored")
                try expect(try c.library.books().isEmpty && c.catalog.localIDs().isEmpty, "Copy cancellation inserted storage")
                try emptyStaging(c)
            }

            for reused in [false, true] {
                check(reused ? "prepublication-cancel-preserves-reused-sdk-row" : "prepublication-cancel-compensates-created-sdk-row") {
                    let c = try context(reused ? "cancel-reused" : "cancel-created"); defer { try? c.catalog.close() }
                    let path = try file(c)
                    if reused { _ = try mapped(c, path) }
                    let box = HostCancelBox()
                    HostSDKReview.event = { if $0 == "mapping-after-sdk" { box.cancel() } }
                    try expect(cancelled { _ = try mapped(c, path, cancel: box) }, "Prepublication cancellation was ignored")
                    try expect(try c.library.books().count == (reused ? 1 : 0) && c.catalog.localIDs().count == (reused ? 1 : 0), "Created-only compensation changed a reused row")
                    try emptyStaging(c)
                }
            }

            check("source-hashes-in-64k-chunks-and-releases-on-cancel") {
                let c = try context("source-release"); defer { try? c.catalog.close() }
                let bytes = Data(repeating: 65, count: 200_000), path = try file(c, data: bytes)
                let (id, _) = try mapped(c, path), book = try c.library.books().first { $0.id == id }!
                var reads = 0, releases = 0
                HostSDKReview.event = { if $0 == "mapping-source-read" { reads += 1 }; if $0 == "mapping-source-released" { releases += 1 } }
                let identity = try c.library.sourceFingerprint(book: book)
                try expect(reads == 4 && releases == 1 && identity.sha256 == digest(bytes) && identity.bytes == 200_000, "Public source chunk/hash/release differs")
                let box = HostCancelBox(); reads = 0; releases = 0
                HostSDKReview.event = { if $0 == "mapping-source-read" { reads += 1; box.cancel() }; if $0 == "mapping-source-released" { releases += 1 } }
                try expect(cancelled { _ = try c.library.sourceFingerprint(book: book, cancel: box) }, "Source cancellation was ignored")
                try expect(reads == 1 && releases == 1 && c.library.books().count == 1, "Cancelled source leaked ownership or deleted book")
                observations = ["chunk_limit": 65536, "cancelled_reads": reads, "cancelled_releases": releases]
            }

            check("product-transaction-failure-keeps-sdk-and-repairs") {
                let c = try context("transaction"); defer { try? c.catalog.close() }
                let path = try file(c)
                try c.catalog.execute("CREATE TRIGGER reject_local BEFORE INSERT ON reader_local_books BEGIN SELECT RAISE(ABORT,'mapping test refusal'); END;")
                do { _ = try mapped(c, path); throw HostError.invalidResult("Product failure was accepted") }
                catch HostError.invalidResult(let message) { try expect(message.contains("产品索引待修复"), "Product failure did not report retained SDK source") }
                try expect(try c.library.books().count == 1 && c.catalog.scalar("SELECT count(*) FROM reader_books") == 0 && c.catalog.localIDs().isEmpty, "Product transaction was partial or deleted SDK source")
                try emptyStaging(c)
                try c.catalog.execute("DROP TRIGGER reject_local")
                try expect(try c.catalog.repairMissing(library: c.library, books: c.library.books()).isEmpty && c.catalog.localIDs().count == 1, "Startup-style repair failed")
                try expect(try c.library.books().count == 1, "Repair reimported the source")
            }

            check("external-pdf-change-cannot-change-private-import") {
                let c = try context("private-pdf"); defer { try? c.catalog.close() }
                let original = try Data(contentsOf: resources.appendingPathComponent("Sample.pdf"))
                let path = try file(c, name: "external.pdf", data: original)
                HostSDKReview.event = { if $0 == "private-copy-complete" { try Data("External file replaced after copy".utf8).write(to: path) } }
                let (id, _) = try mapped(c, path)
                let book = try c.library.books().first { $0.id == id }!
                try expect(try c.library.sourceFingerprint(book: book).sha256 == digest(original), "PDF imported a later external open")
                try expect(try Data(contentsOf: path) != original, "External mutation fixture did not run")
                try emptyStaging(c)
            }

            check("copy-detects-changing-length-and-cleans-up") {
                let c = try context("copy-growth"); defer { try? c.catalog.close() }
                let path = try file(c, data: Data(repeating: 65, count: 70_000))
                var changed = false
                HostSDKReview.event = { event in
                    if event == "private-copy-read" && !changed {
                        changed = true
                        let handle = try FileHandle(forWritingTo: path); defer { try? handle.close() }
                        try handle.seekToEnd(); try handle.write(contentsOf: Data([66]))
                    }
                }
                try expect(rejected { _ = try mapped(c, path) } && changed, "Changing external length was accepted")
                try expect(try c.library.books().isEmpty && c.catalog.localIDs().isEmpty, "Changing length inserted a book")
                try emptyStaging(c)
            }

            check("format-limits-reject-before-private-read") {
                let c = try context("size-limits"); defer { try? c.catalog.close() }
                var reads = 0
                HostSDKReview.event = { if $0 == "private-copy-read" { reads += 1 } }
                for (name, limit) in [("too-large.txt", 32 * 1024 * 1024), ("too-large.epub", 128 * 1024 * 1024)] {
                    let path = try file(c, name: name)
                    let handle = try FileHandle(forWritingTo: path)
                    try handle.truncate(atOffset: UInt64(limit + 1)); try handle.close()
                    try expect(rejected { _ = try mapped(c, path) }, "Format limit was widened")
                }
                try expect(reads == 0 && c.library.books().isEmpty, "Oversize source was read or imported")
                try emptyStaging(c)
            }
        }
        let passed = checks.count == 15 && checks.allSatisfy { $0["passed"] as? Bool == true }
        let report: [String: Any] = ["schema": 1, "accepted": passed, "checks": checks,
            "passed": checks.filter { $0["passed"] as? Bool == true }.count,
            "failed": checks.filter { $0["passed"] as? Bool != true }.count, "skipped": 0,
            "source_sha": environment["GITHUB_SHA"] ?? "", "run_id": environment["GITHUB_RUN_ID"] ?? "",
            "attempt": environment["GITHUB_RUN_ATTEMPT"] ?? "", "sdk": HOST_SDK_VERSION, "abi": HOST_ABI_VERSION,
            "scope": "actual macOS public-SDK product import mapping; separate UI process-recovery evidence required",
            "physical_device_execution": false, "problems": passed ? [] : ["Import mapping checks failed"]]
        try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys])
            .write(to: output.appendingPathComponent("mapping-review.json"))
        print("mapping-review checks=\(checks.count) accepted=\(passed)")
        if !passed { exit(1) }
    }
}
