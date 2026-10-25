// SPDX-License-Identifier: MIT
import Foundation
import CoreGraphics
import CryptoKit
import CEXReader
import CReaderProduct
import Darwin

@main struct ReadingReview {
    static func main() throws {
        let environment = ProcessInfo.processInfo.environment
        guard environment["GITHUB_ACTIONS"] == "true" else { throw HostError.invalidInput("Actions only") }
        let resources = URL(fileURLWithPath: CommandLine.arguments[1]), root = URL(fileURLWithPath: CommandLine.arguments[2])
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        let queue = DispatchQueue(label: "apple.reading.review.owner")
        var checks: [[String: Any]] = []
        func expect(_ value: Bool, _ message: String) throws { if !value { throw HostError.invalidResult(message) } }
        func refuses(_ operation: () throws -> Void) -> Bool { do { try operation(); return false } catch { return true } }
        func check(_ id: String, _ operation: () throws -> Void) {
            var row: [String: Any] = ["id": id, "passed": false]
            do { try operation(); row["passed"] = true } catch { row["error"] = error.localizedDescription }
            checks.append(row); print("READING CHECK \(row)"); fflush(stdout)
        }
        if CommandLine.arguments.count > 3 {
            let mode = CommandLine.arguments[3]
            try queue.sync {
                let library = try HostLibrary(path: root.appendingPathComponent("library.sqlite"))
                let catalog = try HostCatalog(path: root.appendingPathComponent("catalog.sqlite"), migrationURL: resources.appendingPathComponent("reader-catalog-v1.sql"), ownerQueue: queue)
                defer { try? catalog.close() }
                let font = try HostFont(data: Data(contentsOf: resources.appendingPathComponent("Reader.otf")))
                let session = HostSession(library: library, font: font, slowDelay: 0, viewport: CGSize(width: 480, height: 640), fontSize: 28)
                let (book, _) = try session.importBook(url: resources.appendingPathComponent("Records.txt"), cancel: HostCancelBox(), catalog: catalog)
                _ = try session.open(bookID: book, cancel: HostCancelBox())
                if mode.hasPrefix("replay-") {
                    guard let pending = try HostReadingWorker.pending(root: root) else { throw HostError.invalidResult("Real killed process did not retain its request") }
                    let baseline = try session.stateHash()
                    let result = try HostReadingWorker.replay(session: session, catalog: catalog, root: root, cancel: HostCancelBox())
                    let stored = try catalog.withHistory { history in
                        let (wire, _) = try HostReadingWorker.retained(history, revision: pending.revision)
                        return try HostReadingWorker.decoded(wire, history: history).capture
                    }
                    try expect(stored == pending.capture && result.created == (mode == "replay-before" ? 1 : 0) &&
                               session.stateHash() == baseline && HostReadingWorker.pending(root: root) == nil,
                               "Explicit post-kill replay changed the capture, SDK state or commit count")
                    let report: [String: Any] = ["passed": true, "mode": mode, "revision": pending.revision, "created": result.created,
                        "source_sha": environment["GITHUB_SHA"] ?? "", "run_id": environment["GITHUB_RUN_ID"] ?? "", "attempt": environment["GITHUB_RUN_ATTEMPT"] ?? ""]
                    try JSONSerialization.data(withJSONObject: report, options: [.sortedKeys]).write(to: root.appendingPathComponent("child-\(mode).json"))
                    return
                }
                _ = try session.turn(1, cancel: HostCancelBox())
                let capture = try session.readingCapture(cancel: HostCancelBox())
                let request = try HostReadingWorker.request(session: session, catalog: catalog, kind: 1, operation: 0, mode: capture.mode, capture: capture, body: "", cancel: HostCancelBox())
                if mode == "kill-before" { HostReadingWorker.afterDurableSave = { _exit(73) } }
                else if mode == "kill-after" { HostReadingWorker.afterCommit = { _exit(74) } }
                else { throw HostError.invalidInput("Unknown child mode") }
                _ = try HostReadingWorker.submit(request, session: session, catalog: catalog, root: root, cancel: HostCancelBox())
                throw HostError.invalidResult("Child failed to terminate at its real commit boundary")
            }
            return
        }

        try queue.sync {
            let library = try HostLibrary(path: root.appendingPathComponent("library.sqlite"))
            let catalog = try HostCatalog(path: root.appendingPathComponent("catalog.sqlite"), migrationURL: resources.appendingPathComponent("reader-catalog-v1.sql"), ownerQueue: queue)
            defer { try? catalog.close() }
            let font = try HostFont(data: Data(contentsOf: resources.appendingPathComponent("Reader.otf")))
            var session = HostSession(library: library, font: font, slowDelay: 0, viewport: CGSize(width: 480, height: 640), fontSize: 28)
            var books: [String: Int64] = [:]
            for name in ["Records.txt", "Bounded.epub", "Sample.pdf", "NavigationPages.cbz", "UnicodePages.cbz", "Sample.epub"] {
                let (id, _) = try session.importBook(url: resources.appendingPathComponent(name), cancel: HostCancelBox(), catalog: catalog)
                books[name] = id
            }
            func open(_ name: String) throws -> HostSnapshot { try session.open(bookID: books[name]!, cancel: HostCancelBox()) }
            func request(_ kind: Int = 2, operation: Int = 0, annotation: String = "", body: String = "",
                         capture supplied: HostReadingCapture? = nil, heads: [String]? = nil) throws -> HostReadingRequest {
                let capture = try supplied ?? session.readingCapture(cancel: HostCancelBox())
                return try HostReadingWorker.request(session: session, catalog: catalog, kind: kind, operation: operation,
                    annotation: annotation, mode: capture.mode, capture: kind == 4 || operation == 1 ? nil : capture,
                    body: body, observedHeads: heads, cancel: HostCancelBox())
            }
            func submit(_ input: HostReadingRequest, cancel: HostCancelBox = HostCancelBox()) throws -> reader_rc_result {
                try HostReadingWorker.submit(input, session: session, catalog: catalog, root: root, cancel: cancel)
            }
            func wire(_ input: HostReadingRequest) throws -> Data {
                try catalog.withHistory { try HostReadingWorker.retained($0, revision: input.revision).0 }
            }
            func counts(_ input: HostReadingRequest) throws -> [Int64] {
                let graph = try catalog.withHistory { history -> reader_revision_state in
                    var graph = reader_revision_state(), error = reader_revision_error()
                    guard reader_revision_heads(history, input.entityKind, input.entityKey, nil, nil, &graph, &error) == READER_REV_OK else { throw HostError.invalidResult("Public graph read failed") }
                    return graph
                }
                return [Int64(graph.revisions), Int64(graph.heads), try catalog.scalar("SELECT count(*) FROM reader_outbox")]
            }
            func page() throws -> HostReadingPage {
                let book = try catalog.readingBook(sdkID: session.book!.id)
                return try HostReadingWorker.page(catalog: catalog, bookID: book.sdkID, bookKey: book.key, from: nil, cancel: HostCancelBox())
            }
            func row(_ id: String) throws -> HostReadingRow {
                let book = try catalog.readingBook(sdkID: session.book!.id)
                var cursor: reader_av_cursor?
                for _ in 0..<8 {
                    let value = try HostReadingWorker.page(catalog: catalog, bookID: book.sdkID, bookKey: book.key, from: cursor, cancel: HostCancelBox())
                    if let found = value.rows.first(where: { $0.annotation == id }) { return found }
                    if value.complete { break }
                    cursor = value.next
                }
                throw HostError.invalidResult("Committed annotation absent from G04")
            }
            func encode(_ input: HostReadingRequest, version: Int = 2, revision: String, parents: [String]) throws -> Data {
                guard let capture = input.capture else { throw HostError.invalidResult("Real encoder capture missing") }
                return try catalog.withHistory { history in
                    try hostProductStrings([revision, "put", input.entityKind, input.bookKey, input.annotation, input.body, input.parser] + parents) { strings in
                        let parentPointers = Array(strings.dropFirst(7))
                        return try parentPointers.withUnsafeBufferPointer { buffer in
                            var envelope = reader_rs_envelope(); envelope.revision_id = strings[0]; envelope.operation = strings[1]
                            envelope.entity_kind = strings[2]; envelope.book_key = strings[3]; envelope.annotation_id = input.kind == 1 ? nil : strings[4]
                            envelope.note_text = input.kind == 1 ? nil : strings[5]; envelope.parser_version = strings[6]
                            envelope.parents = buffer.baseAddress; envelope.parent_count = buffer.count
                            return try capture.withRaw { raw in
                                var raw = raw, output: UnsafeMutablePointer<CChar>?, count = 0, error = reader_rs_error()
                                let status = version == 1 ? reader_rs_encode(history, &envelope, &raw, &output, &count, &error) :
                                    reader_rs_encode_v2(history, &envelope, &raw, capture.part, &output, &count, &error)
                                guard status == READER_RS_OK, let output else { throw HostError.invalidResult("Public codec refused the real capture") }
                                defer { reader_rs_free(output) }
                                return Data(bytes: output, count: count)
                            }
                        }
                    }
                }
            }
            var captures: [String: HostReadingRequest] = [:]
            check("real-public-point-captures-four-formats") {
                var problems: [String] = []
                for name in ["Records.txt", "Bounded.epub", "Sample.pdf", "NavigationPages.cbz"] {
                    do {
                        _ = try open(name); let before = try session.stateHash(), input = try request(1)
                        _ = try submit(input); captures[name] = input
                        let stored = try catalog.withHistory { try HostReadingWorker.decoded(wire(input), history: $0).capture }
                        let sameSelector = stored == input.capture, sameSDK = try session.stateHash() == before
                        print("READING_CAPTURE_IDENTITY format=\(name) selector_equal=\(sameSelector) sdk_unchanged=\(sameSDK) mode=\(stored.mode) part=\(stored.part) page=\(stored.page)"); fflush(stdout)
                        if !sameSelector || !sameSDK { problems.append(name + ": selector_equal=\(sameSelector) sdk_unchanged=\(sameSDK)") }
                    } catch { problems.append(name + ": " + error.localizedDescription) }
                }
                try expect(problems.isEmpty, "Product progress changed SDK or real selector: " + problems.joined(separator: "; "))
            }
            check("cbz-real-empty-snapshot-point-independent-found") {
                _ = try open("NavigationPages.cbz")
                guard let input = captures["NavigationPages.cbz"] else { throw HostError.invalidResult("CBZ capture missing") }
                try expect(session.pageText.isEmpty && input.capture?.fixed?.fields[1] != nil, "CBZ did not expose its genuine empty text snapshot")
                let (fresh, hit) = try session.readingResolution(wire(input), catalog: catalog, cancel: HostCancelBox())
                try expect(fresh.mode == 3 && fresh.fixed?.start == 0 && fresh.fixed?.end == 0 && hit.mode == READER_SEARCH_FIXED,
                    "CBZ point did not resolve through its actual fixed text provider")
                let (candidate, frame) = try session.searchCandidate(hit, cancel: HostCancelBox())
                try expect(frame.pageIndex == hit.unit, "CBZ renderer failed its second public FOUND")
                session = candidate
                _ = try open("UnicodePages.cbz")
                let actual = try session.library.fixed(bookID: books["UnicodePages.cbz"]!, font: font, cancel: HostCancelBox())
                let ids = actual.pageIDs
                try expect(ids.count == 2 && Set(ids).count == 1 && Set(ids.map { Data($0.utf8) }).count == 2,
                           "Actual CBZ did not retain both canonically equal but byte-distinct native page IDs")
                for page in 0..<2 {
                    if page != 0 { _ = try session.turn(1, cancel: HostCancelBox()) }
                    let input = try request(), before = try session.stateHash()
                    _ = try submit(input)
                    try expect(try session.stateHash() == before, "Unicode CBZ bookmark wrote SDK state")
                    let (fresh, hit) = try session.readingResolution(wire(input), catalog: catalog, cancel: HostCancelBox())
                    try expect(fresh.page == page && fresh.fixed?.fields[0] == Data(ids[page].utf8),
                               "Canonically equal CBZ IDs were merged instead of byte-exact routed")
                    let (candidate, frame) = try session.searchCandidate(hit, cancel: HostCancelBox())
                    try expect(frame.pageIndex == page, "Actual renderer guessed a Unicode-equivalent CBZ page")
                    session = candidate
                }
            }
            _ = try open("Records.txt")
            let bookmark = try request(); _ = try submit(bookmark)
            check("bookmark-products-only-and-g04-safe") {
                let value = try row(bookmark.annotation), before = try session.stateHash()
                try expect(value.safe && value.kind == 1 && value.hasLocation && value.revision == bookmark.revision && value.heads == 1,
                           "G04 did not expose a real SAFE point bookmark")
                _ = try page()
                try expect(try session.stateHash() == before, "Reading list changed SDK state")
            }
            let frame = try open("Records.txt"), length = String(frame.pageText.prefix(16)).utf8.count
            let highlightCapture = try session.readingCapture(start: frame.pageRange.lowerBound, end: frame.pageRange.lowerBound + length, cancel: HostCancelBox())
            let highlight = try request(3, capture: highlightCapture); _ = try submit(highlight)
            check("actual-visible-selection-range-products-only") {
                let value = try row(highlight.annotation), before = try session.stateHash()
                try expect(value.safe && value.kind == 2 && !value.quote.isEmpty && value.quote == String(frame.pageText.prefix(16)), "G04 quote differs from actual native selection")
                _ = try HostReadingWorker.selectedWire(catalog: catalog, row: value)
                try expect(try session.stateHash() == before, "Selection read modified SDK notes/progress")
            }
            let edit = try request(4, annotation: highlight.annotation, body: "中文 note 😀", heads: [highlight.revision])
            _ = try submit(edit)
            check("note-edit-preserves-exact-original-selector") {
                let decoded = try catalog.withHistory { try HostReadingWorker.decoded(wire(edit), history: $0) }
                try expect(decoded.capture == highlightCapture && decoded.body == "中文 note 😀" && row(highlight.annotation).kind == 3,
                           "Note edit recaptured, rounded or changed the retained selector")
            }
            check("stale-ui-head-rejected-with-durable-request-intact") {
                let stale = try request(4, annotation: highlight.annotation, body: "stale overwrite", heads: [highlight.revision])
                let before = try counts(stale), sdk = try session.stateHash()
                try expect(refuses { _ = try submit(stale) }, "Stale observed head was silently replaced with a new head")
                try expect(try counts(stale) == before && session.stateHash() == sdk && HostReadingWorker.pending(root: root)?.revision == stale.revision,
                           "Refused request changed history, outbox, SDK or its durable identity")
                try HostReadingWorker.discard(root: root, expected: stale.revision)
            }
            check("lost-response-exact-replay-after-ack-no-requeue") {
                let input = try request(), beforeSDK = try session.stateHash()
                HostReadingWorker.afterCommit = { throw HostError.invalidResult("simulated lost response") }
                defer { HostReadingWorker.afterCommit = nil }
                try expect(refuses { _ = try submit(input) }, "Real post-commit boundary was not reached")
                HostReadingWorker.afterCommit = nil
                let stored = try wire(input), digest = SHA256.hash(data: stored).map { String(format: "%02x", $0) }.joined()
                try catalog.withHistory { history in
                    var error = reader_revision_error()
                    try expect(reader_revision_ack(history, input.revision, digest, &error) == READER_REV_OK, "Actual committed revision could not be acked")
                }
                let before = try counts(input)
                let result = try HostReadingWorker.replay(session: session, catalog: catalog, root: root, cancel: HostCancelBox())
                try expect(result.created == 0 && hostReadingField(result.annotation_id) == input.annotation && counts(input) == before &&
                           wire(input) == stored && session.stateHash() == beforeSDK && HostReadingWorker.pending(root: root) == nil,
                           "Replay duplicated identity, requeued acked data or changed capture/SDK")
            }
            check("cancel-after-private-save-retains-exact-request") {
                let input = try request(), cancel = HostCancelBox(), before = try catalog.scalar("SELECT count(*) FROM reader_revisions")
                HostReadingWorker.afterDurableSave = { cancel.cancel() }
                defer { HostReadingWorker.afterDurableSave = nil }
                try expect(refuses { _ = try submit(input, cancel: cancel) }, "Cancellation did not occur after durable save")
                HostReadingWorker.afterDurableSave = nil
                let pending = try HostReadingWorker.pending(root: root)
                try expect(pending?.revision == input.revision && pending?.capture == input.capture &&
                           catalog.scalar("SELECT count(*) FROM reader_revisions") == before, "Cancelled commit altered durable input or history")
                let result = try HostReadingWorker.replay(session: session, catalog: catalog, root: root, cancel: HostCancelBox())
                try expect(result.created == 1, "Explicit cancelled-request retry failed")
            }
            check("pending-own-id-clear-and-account-isolation") {
                let input = try request()
                HostReadingWorker.afterDurableSave = { throw HostError.invalidResult("hold private request") }
                defer { HostReadingWorker.afterDurableSave = nil }
                _ = refuses { _ = try submit(input) }; HostReadingWorker.afterDurableSave = nil
                try expect(refuses { try HostReadingWorker.discard(root: root, expected: HostReadingRequest.newID()) }, "An unrelated window cleared this request")
                try expect(try HostReadingWorker.pending(root: root.appendingPathComponent("other-account")) == nil &&
                           HostReadingWorker.pending(root: root)?.revision == input.revision, "Request leaked into another account")
                var file = stat()
                try expect(lstat(root.appendingPathComponent("reading-requests/request.json").path, &file) == 0 && file.st_mode & 0o777 == 0o600,
                           "Private durable request is not owner-only")
                try HostReadingWorker.discard(root: root, expected: input.revision)
            }
            check("delete-tombstone-and-explicit-independent-restore") {
                let current = try row(highlight.annotation), before = try session.stateHash()
                let deletion = try request(3, operation: 1, annotation: highlight.annotation, heads: [current.revision])
                _ = try submit(deletion)
                let tombstone = try row(highlight.annotation)
                try expect(tombstone.deleted && !tombstone.hasLocation && tombstone.quote.isEmpty && tombstone.body.isEmpty, "Tombstone exposed a fabricated location or body")
                let versions = try HostReadingWorker.history(catalog: catalog, row: tombstone)
                guard let version = versions.versions.first else { throw HostError.invalidResult("Retained source version missing") }
                let (capture, _) = try session.readingResolution(version.wire, catalog: catalog, cancel: HostCancelBox())
                let restoration = try request(3, operation: 2, annotation: highlight.annotation, body: "restored", capture: capture, heads: versions.heads)
                _ = try submit(restoration)
                try expect(try row(highlight.annotation).hasLocation && session.stateHash() == before,
                           "Explicit product restore navigated or cloned an SDK note")
            }
            check("independent-found-before-explicit-renderer-jump") {
                let current = try row(highlight.annotation), selected = try HostReadingWorker.selectedWire(catalog: catalog, row: current)
                let (_, hit) = try session.readingResolution(selected, catalog: catalog, cancel: HostCancelBox())
                let (candidate, actual) = try session.searchCandidate(hit, cancel: HostCancelBox())
                try expect(candidate.library.handle != session.library.handle && actual.pageText.contains(current.quote), "Real renderer did not independently FOUND the retained selection")
                session = candidate
            }
            check("g04-pagination-cancel-and-snapshot-reopen") {
                for _ in 0..<35 { _ = try submit(request()) }
                let book = try catalog.readingBook(sdkID: session.book!.id), cancel = HostCancelBox()
                let first = try HostReadingWorker.page(catalog: catalog, bookID: book.sdkID, bookKey: book.key, from: nil, cancel: HostCancelBox())
                try expect(first.rows.count == 32 && !first.complete, "Actual G04 first page did not reach the real 32-row boundary")
                cancel.cancel()
                try expect(refuses { _ = try HostReadingWorker.page(catalog: catalog, bookID: book.sdkID, bookKey: book.key, from: first.next, cancel: cancel) }, "Actual G04 entry cancellation was ignored")
                let retry = try HostReadingWorker.page(catalog: catalog, bookID: book.sdkID, bookKey: book.key, from: first.next, cancel: HostCancelBox())
                try expect(!retry.rows.isEmpty && retry.complete && Set(first.rows.map(\.id)).isDisjoint(with: Set(retry.rows.map(\.id))),
                           "Reopened thread-owned G04 view lost or duplicated the actual nonempty continuation")
            }
            check("concurrent-g04-row-only-real-graph-counts") {
                let before = try session.stateHash()
                for _ in 0..<2 {
                    let bytes = try encode(bookmark, revision: HostReadingRequest.newID(), parents: [bookmark.revision])
                    let digest = SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
                    try catalog.withHistory { history in
                        var info = reader_revision_info(), created: Int32 = 0, error = reader_revision_error()
                        let status = bytes.withUnsafeBytes { reader_revision_receive(history, $0.baseAddress, $0.count, digest, &info, &created, &error) }
                        try expect(status == READER_REV_OK && created == 1, "Actual remote fork did not enter retained history")
                    }
                }
                let value = try row(bookmark.annotation)
                try expect(!value.safe && value.heads == 2 && value.revisions == 3 && value.revision.isEmpty && value.mode == 0 &&
                           value.kind == 0 && value.quote.isEmpty && value.body.isEmpty && !value.hasLocation,
                           "Concurrent G04 row invented selected content or location")
                try expect(refuses { _ = try HostReadingWorker.selectedWire(catalog: catalog, row: value) } && session.stateHash() == before,
                           "Concurrent record navigated or wrote SDK state")
            }
            check("legacy-v1-note-edit-keeps-original-anchor-version") {
                let input = try request(3, capture: highlightCapture)
                let bytes = try encode(input, version: 1, revision: input.revision, parents: [])
                try catalog.withHistory { history in
                    var info = reader_revision_info(), created: Int32 = 0, error = reader_revision_error()
                    let status = bytes.withUnsafeBytes { reader_revision_local_reading(history, $0.baseAddress, $0.count, nil, 0, &info, &created, &error) }
                    try expect(status == READER_REV_OK && created == 1, "Real legacy capture failed to enter product history")
                }
                let edit = try request(4, annotation: input.annotation, body: "legacy body edit", heads: [input.revision])
                _ = try submit(edit)
                let value = try catalog.withHistory { try HostReadingWorker.decoded(wire(edit), history: $0) }
                try expect(value.version == 1 && value.capture == highlightCapture && value.body == "legacy body edit",
                           "Host note edit upgraded or recaptured a v1 selector")
            }
            check("legacy-repeated-epub-route-refused-without-guessing") {
                let frame = try open("Sample.epub")
                let seed = try request(1); _ = try submit(seed)
                let length = String(frame.pageText.prefix(12)).utf8.count
                let capture = try session.readingCapture(start: frame.pageRange.lowerBound, end: frame.pageRange.lowerBound + length, cancel: HostCancelBox())
                let input = try request(3, capture: capture)
                let old = try encode(input, version: 1, revision: input.revision, parents: [])
                let before = try session.stateHash()
                try expect(refuses { _ = try session.readingResolution(old, catalog: catalog, cancel: HostCancelBox()) } && session.stateHash() == before,
                           "Legacy repeated spine path guessed a part or changed SDK state")
                let current = try encode(input, revision: HostReadingRequest.newID(), parents: [])
                let (actual, _) = try session.readingResolution(current, catalog: catalog, cancel: HostCancelBox())
                try expect(actual.mode == 2 && actual.part == capture.part && actual.path == capture.path, "Actual v2 spine index did not independently FOUND")
                _ = try open("Records.txt")
            }
            check("wrong-book-replay-does-not-recapture-or-clear") {
                let input = try request()
                HostReadingWorker.afterDurableSave = { throw HostError.invalidResult("hold original request") }
                _ = refuses { _ = try submit(input) }; HostReadingWorker.afterDurableSave = nil
                _ = try open("Bounded.epub")
                try expect(refuses { _ = try HostReadingWorker.replay(session: session, catalog: catalog, root: root, cancel: HostCancelBox()) }, "Pending TXT request was applied to EPUB")
                try expect(try HostReadingWorker.pending(root: root)?.capture == input.capture, "Wrong-book retry rewrote the saved selector")
                try HostReadingWorker.discard(root: root, expected: input.revision)
                _ = try open("Records.txt")
            }
            check("one-dynamic-sdk-and-installed-g03-g04") {
                var paths: [String] = []
                for name in ["exr_anchor_create", "exr_anchor_resolve_ex", "exr_pager_anchor_create", "exr_fixed_anchor_create", "exr_fixed_anchor_resolve"] {
                    guard let pointer = dlsym(UnsafeMutableRawPointer(bitPattern: -2), name) else { throw HostError.invalidResult("Public SDK symbol missing") }
                    var image = Dl_info(); try expect(dladdr(pointer, &image) != 0, "SDK image unresolved")
                    paths.append(String(cString: image.dli_fname))
                }
                try expect(Set(paths).count == 1 && paths[0].contains("libexreader"), "Reading commands embedded another SDK")
                print("READING_DSO_IMAGES \(paths)")
            }
        }
        func child(_ mode: String) throws -> Int32 {
            let task = Process()
            task.executableURL = URL(fileURLWithPath: CommandLine.arguments[0])
            task.arguments = [resources.path, root.appendingPathComponent("killed-process").path, mode]
            try task.run(); task.waitUntilExit(); return task.terminationStatus
        }
        check("real-process-termination-after-private-save-explicit-replay") {
            try expect(try child("kill-before") == 73, "Real pre-commit process did not exit at the durable boundary")
            guard let pending = try HostReadingWorker.pending(root: root.appendingPathComponent("killed-process")) else { throw HostError.invalidResult("Killed process did not durably publish a real request") }
            try expect(try child("replay-before") == 0, "Real pre-commit process death did not replay once")
            let report = try JSONSerialization.jsonObject(with: Data(contentsOf: root.appendingPathComponent("killed-process/child-replay-before.json"))) as! [String: Any]
            try expect(report["passed"] as? Bool == true && report["revision"] as? String == pending.revision &&
                       report["created"] as? Int == 1 && report["source_sha"] as? String == environment["GITHUB_SHA"],
                       "Child replay-before report did not bind the actual killed request/source")
        }
        check("real-process-termination-after-commit-exact-replay") {
            try expect(try child("kill-after") == 74, "Real committed process did not exit before clearing its request")
            guard let pending = try HostReadingWorker.pending(root: root.appendingPathComponent("killed-process")) else { throw HostError.invalidResult("Committed process did not retain its lost-response request") }
            try expect(try child("replay-after") == 0, "Real committed process death did not replay as an exact no-op")
            let report = try JSONSerialization.jsonObject(with: Data(contentsOf: root.appendingPathComponent("killed-process/child-replay-after.json"))) as! [String: Any]
            try expect(report["passed"] as? Bool == true && report["revision"] as? String == pending.revision &&
                       report["created"] as? Int == 0 && report["source_sha"] as? String == environment["GITHUB_SHA"],
                       "Child replay-after report did not bind the actual committed request/source")
        }
        let failed = checks.filter { $0["passed"] as? Bool != true }.count
        let result: [String: Any] = ["accepted": failed == 0 && checks.count == 19, "failed": failed, "skipped": 0,
            "source_sha": environment["GITHUB_SHA"] ?? "", "run_id": environment["GITHUB_RUN_ID"] ?? "", "attempt": environment["GITHUB_RUN_ATTEMPT"] ?? "", "checks": checks]
        try JSONSerialization.data(withJSONObject: result, options: [.sortedKeys, .prettyPrinted]).write(to: root.appendingPathComponent("reading-review.json"))
        print("READING_REPORT \(result)"); fflush(stdout)
        if failed != 0 || checks.count != 19 { exit(1) }
    }
}
