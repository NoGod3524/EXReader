// SPDX-License-Identifier: MIT
import Foundation
import CoreGraphics
import CEXReader
import CReaderProduct
import Darwin

@main struct SearchReview {
    static func main() throws {
        let environment = ProcessInfo.processInfo.environment
        guard environment["GITHUB_ACTIONS"] == "true" else { throw HostError.invalidInput("Cloud execution only") }
        let resources = URL(fileURLWithPath: CommandLine.arguments[1])
        let output = URL(fileURLWithPath: CommandLine.arguments[2])
        try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
        let queue = DispatchQueue(label: "apple.search.review.owner")
        var checks: [[String: Any]] = []
        func check(_ name: String, _ operation: () throws -> Void) {
            var row: [String: Any] = ["id": name, "passed": false]
            do { try operation(); row["passed"] = true }
            catch { row["error"] = error.localizedDescription }
            checks.append(row)
            print("SEARCH CHECK \(row)")
        }
        func expect(_ value: Bool, _ detail: String) throws {
            if !value { throw HostError.invalidResult(detail) }
        }
        func rejects(_ operation: () throws -> Void) -> Bool {
            do { try operation(); return false } catch { return true }
        }
        try queue.sync {
            let library = try HostLibrary(path: output.appendingPathComponent("library.sqlite"))
            let catalog = try HostCatalog(path: output.appendingPathComponent("catalog.sqlite"),
                migrationURL: resources.appendingPathComponent("reader-catalog-v1.sql"), ownerQueue: queue)
            defer { try? catalog.close() }
            let font = try HostFont(data: Data(contentsOf: resources.appendingPathComponent("Reader.otf")))
            let session = HostSession(library: library, font: font, slowDelay: 0, viewport: CGSize(width: 480, height: 640), fontSize: 28)
            let source = output.appendingPathComponent("search.txt")
            let text = (0..<70).map { String(format: "Unique section %04d before needle😀 after section %04d.\n", $0, $0) }.joined()
            try Data(text.utf8).write(to: source)
            let (id, _) = try session.importBook(url: source, cancel: HostCancelBox(), catalog: catalog)
            _ = try session.open(bookID: id, cancel: HostCancelBox())
            let key = try catalog.searchSourceKey(sdkID: id)
            let baseline = try session.stateHash()
            let revisionCount = try catalog.scalar("SELECT count(*) FROM reader_revisions")
            let outboxCount = try catalog.scalar("SELECT count(*) FROM reader_outbox")
            func batch(_ resume: reader_search_cursor? = nil, query: String = "needle😀", sourceKey: String? = nil,
                       cancel: HostCancelBox = HostCancelBox(), using owner: HostLibrary? = nil) throws -> HostSearchBatch {
                try HostSearchWorker.batch(library: owner ?? library, font: font, bookID: id,
                    sourceKey: sourceKey ?? key, query: query, resume: resume, cancel: cancel)
            }
            let first = try batch()
            check("bounded-copied-unicode-batch") {
                try expect(first.hits.count == 32 && !first.complete, "First batch must have exactly 32 copied results")
                try expect(first.hits.allSatisfy { $0.quote == "needle😀" }, "Unicode capture differs")
            }
            let independent = try HostLibrary(path: library.path)
            let second = try batch(first.next, using: independent)
            let third = try batch(second.next)
            check("resume-on-independently-opened-instance") {
                try expect(independent.handle != library.handle, "Library handles were reused")
                try expect(second.hits.count == 32 && third.hits.count == 6 && third.complete, "Cursor did not advance exactly 70 results")
                let all = first.hits + second.hits + third.hits
                try expect(Set(all.map(\.id)).count == 70, "Cursor repeated a result")
            }
            check("cursor-rejects-query-and-source-change") {
                try expect(rejects { _ = try batch(first.next, query: "section") }, "Different query resumed")
                try expect(rejects { _ = try batch(first.next, sourceKey: key + ":other") }, "Different source resumed")
            }
            check("cancelled-batch-retries-previous-cursor") {
                let cancelled = HostCancelBox(); cancelled.cancel()
                try expect(rejects { _ = try batch(first.next, cancel: cancelled) }, "Cancelled scan succeeded")
#if EXR_APPLE_HOST_REVIEW
                let active = HostCancelBox(), prior = HostSDKReview.poll
                var cancelledInsideNext = false
                HostSDKReview.poll = { polled in
                    if polled === active, HostSearchWorker.reviewInsideNext {
                        cancelledInsideNext = true; polled.cancel()
                    } else { prior?(polled) }
                }
                defer { HostSDKReview.poll = prior }
                try expect(rejects { _ = try batch(first.next, cancel: active) }, "In-flight F1 scan ignored cancellation")
                try expect(cancelledInsideNext, "Cancellation did not occur inside reader_search_next")
#endif
                let retried = try batch(first.next)
                try expect(retried.hits.map(\.id) == second.hits.map(\.id), "Cancelled batch advanced")
            }
            check("no-hit-completes-without-state-write") {
                let missing = try batch(query: "NoSuchQuery_159873")
                try expect(missing.complete && missing.hits.isEmpty, "No-hit result is not complete")
                try expect(try session.stateHash() == baseline, "Scanning changed progress or notes")
                try expect(try Data(contentsOf: source) == Data(text.utf8), "Source was changed")
                try expect(try catalog.scalar("SELECT count(*) FROM reader_books") == 1, "Search wrote a product record")
                try expect(try catalog.scalar("SELECT count(*) FROM reader_revisions") == revisionCount &&
                    catalog.scalar("SELECT count(*) FROM reader_outbox") == outboxCount, "Search wrote a revision or outbox entry")
            }
            check("independent-found-navigation") {
                let (selected, snapshot) = try session.searchCandidate(second.hits[7], cancel: HostCancelBox())
                try expect(selected.library.handle != library.handle, "Selection reused the source instance")
                try expect(snapshot.pageText.contains("needle😀") && snapshot.pageRange.contains(second.hits[7].anchor.start), "Resolved match is not in the rendered page")
                try expect(selected.book?.id == id, "Selection changed books")
            }
            check("unresolved-preserves-prior-progress") {
                let hit = first.hits[0]
                var raw = exr_anchor()
                raw.start = hit.anchor.start; raw.end = hit.anchor.end
                let invalid = "missing exact selector"
                let poisoned = invalid.withCString { pointer -> HostSearchHit in
                    raw.exact = UnsafeMutablePointer(mutating: pointer)
                    return HostSearchHit(mode: hit.mode, unit: hit.unit, path: hit.path, pageID: hit.pageID,
                        pageLabel: hit.pageLabel, sourceKey: hit.sourceKey, bookID: hit.bookID,
                        anchor: HostSearchAnchor(raw), fixed: hit.fixed)
                }
                let before = try session.stateHash()
                try expect(rejects { _ = try session.searchCandidate(poisoned, cancel: HostCancelBox()) }, "Unresolved capture navigated by offset")
                try expect(try session.stateHash() == before, "Unresolved selection changed progress")
            }
            check("bounded-epub-exact-spine-route") {
                let (epubID, _) = try session.importBook(url: resources.appendingPathComponent("Bounded.epub"), cancel: HostCancelBox(), catalog: catalog)
                _ = try session.open(bookID: epubID, cancel: HostCancelBox())
                let sourceKey = try catalog.searchSourceKey(sdkID: epubID)
                let found = try HostSearchWorker.batch(library: library, font: font, bookID: epubID,
                    sourceKey: sourceKey, query: "opening", resume: nil, cancel: HostCancelBox())
                try expect(found.hits.count == 3 && found.complete, "Duplicate spine occurrence omitted")
                try expect(found.hits.map(\.unit) == [0, 1, 2], "Spine order changed")
                let (_, frame) = try session.searchCandidate(found.hits[2], cancel: HostCancelBox())
                try expect(frame.part == 2 && frame.pageText.contains("Bounded first"), "Duplicate spine guessed the first occurrence")
            }
            check("fixed-page-id-and-independent-found") {
                let (pdfID, _) = try session.importBook(url: resources.appendingPathComponent("Sample.pdf"), cancel: HostCancelBox(), catalog: catalog)
                _ = try session.open(bookID: pdfID, cancel: HostCancelBox())
                let fixed = try library.fixed(bookID: pdfID, font: font)
                let text = try fixed.text(page: 0).text
                let query = String(text.trimmingCharacters(in: .whitespacesAndNewlines).prefix(3))
                try expect(!query.isEmpty, "Fixture has no PDF text")
                let found = try HostSearchWorker.batch(library: library, font: font, bookID: pdfID,
                    sourceKey: catalog.searchSourceKey(sdkID: pdfID), query: query, resume: nil, cancel: HostCancelBox())
                try expect(!found.hits.isEmpty && found.hits[0].mode == READER_SEARCH_FIXED, "PDF hit missing")
                let (_, frame) = try session.searchCandidate(found.hits[0], cancel: HostCancelBox())
                try expect(frame.pageText.contains(query), "Resolved PDF page differs")
            }
            check("exact-full-window-and-first-zero") {
                let expected = try JSONSerialization.jsonObject(with: Data(contentsOf: resources.appendingPathComponent("search-expected.json"))) as! [String: Any]
                guard let query = expected["query"] as? String, expected["count"] as? Int == 32 else {
                    throw HostError.invalidResult("Independent 32-hit fixture contract missing")
                }
                let (bookID, _) = try session.importBook(url: resources.appendingPathComponent("Sample.epub"), cancel: HostCancelBox(), catalog: catalog)
                let identity = try catalog.searchSourceKey(sdkID: bookID)
                let first = try HostSearchWorker.batch(library: library, font: font, bookID: bookID,
                    sourceKey: identity, query: query, resume: nil, cancel: HostCancelBox())
                try expect(first.hits.count == 32 && !first.complete, "Actual source did not fill exactly one window")
                let tail = try HostSearchWorker.batch(library: library, font: font, bookID: bookID,
                    sourceKey: identity, query: query, resume: first.next, cancel: HostCancelBox())
                try expect(tail.hits.isEmpty && tail.complete, "Exactly 32 hits did not require an empty EOF read")
                let state = HostSearchState()
                state.bind(bookID: bookID, query: query)
                let (initialEpoch, _) = state.begin(restart: true)
                state.accept(first, key: identity, generation: initialEpoch)
                let ids = state.rows.map(\.id)
                let (tailEpoch, _) = state.begin(restart: false)
                state.accept(tail, key: identity, generation: tailEpoch)
                try expect(state.complete && state.rows.count == 32 && state.rows.map(\.id) == ids &&
                    state.status == "本批 32 项 · 已查找完毕", "Empty EOF read discarded the usable final window")
                let missing = try HostSearchWorker.batch(library: library, font: font, bookID: bookID,
                    sourceKey: identity, query: "NoSuchFirstHit_159873", resume: nil, cancel: HostCancelBox())
                let (emptyEpoch, _) = state.begin(restart: true)
                state.accept(missing, key: identity, generation: emptyEpoch)
                try expect(state.rows.isEmpty && state.complete && state.status == "没有匹配结果", "First zero-hit search retained old results")
            }
            check("one-dynamic-sdk-image") {
                var images: [String] = []
                for name in ["exr_document_free", "exr_anchor_free", "exr_anchor_resolve_ex", "exr_pager_anchor_resolve"] {
                    guard let symbol = dlsym(UnsafeMutableRawPointer(bitPattern: -2), name) else { throw HostError.invalidResult("Missing SDK symbol") }
                    var info = Dl_info()
                    try expect(dladdr(symbol, &info) != 0, "SDK symbol image missing")
                    images.append(String(cString: info.dli_fname))
                }
                try expect(Set(images).count == 1 && images[0].contains("libexreader"), "Search/resolver SDK image differs")
                print("SEARCH_DSO_IMAGES \(images)")
            }
        }
        let failed = checks.filter { $0["passed"] as? Bool != true }.count
        let report: [String: Any] = ["accepted": failed == 0 && checks.count == 11, "failed": failed,
            "skipped": 0, "source_sha": environment["GITHUB_SHA"] ?? "", "run_id": environment["GITHUB_RUN_ID"] ?? "",
            "attempt": environment["GITHUB_RUN_ATTEMPT"] ?? "", "checks": checks]
        try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys])
            .write(to: output.appendingPathComponent("search-review.json"))
        if failed != 0 || checks.count != 11 { throw HostError.invalidResult("Apple search checks failed") }
    }
}
