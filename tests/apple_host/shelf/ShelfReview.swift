// SPDX-License-Identifier: MIT
import Foundation
import CryptoKit

@main struct ShelfReview {
    static func main() throws {
        let resources = URL(fileURLWithPath: CommandLine.arguments[1])
        let output = URL(fileURLWithPath: CommandLine.arguments[2])
        try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
        let queue = DispatchQueue(label: "shelf.seed.owner")
        var expected: [String] = []
        var groups: [String] = []
        func check(_ name: String, _ condition: @autoclosure () throws -> Bool) throws {
            guard try condition() else { throw NSError(domain: "ShelfReview", code: 1, userInfo: [NSLocalizedDescriptionKey: name]) }
            groups.append(name)
            FileHandle.standardOutput.write(Data("SHELF PASS \(name)\n".utf8))
        }
        try queue.sync {
            let library = try HostLibrary(path: output.appendingPathComponent("ShelfSeed-library.sqlite"))
            let catalog = try HostCatalog(path: output.appendingPathComponent("ShelfSeed-reader-catalog.db"),
                migrationURL: resources.appendingPathComponent("reader-catalog-v1.sql"), ownerQueue: queue)
            let input = output.appendingPathComponent("seed.txt")
            for index in 0..<2202 {
                let title = index < 130 ? "Tie title" : index == 200 ? "100%_ literal" :
                    index == 203 ? "Cafe\u{301} Unicode" : String(format: "Book %04d", index)
                let bytes = Data("Stored native shelf book \(index). Offline reading uses these exact original bytes.\n".utf8)
                try bytes.write(to: input)
                _ = try library.importUnique(file: input, title: title)
            }
            let books = try library.books()
            try check("2202_real_public_sdk_originals", books.count == 2202)
            for (index, book) in books.enumerated() {
                let fingerprint = try library.sourceFingerprint(book: book)
                let author = book.title == "Cafe\u{301} Unicode" ? "Re\u{301}ne\u{301} Unique" : index == 400 ? "Unique Shelf Author" : ""
                try catalog.attach(format: fingerprint.format, sha256: fingerprint.sha256, bytes: fingerprint.bytes,
                    title: book.title, author: author, sdkID: book.id,
                    locationKind: library.locationKind(book: book))
            }
            var anchor: HostShelfKey?
            var forward: [String] = []
            repeat {
                let page = try catalog.shelf(query: "", anchor: anchor)
                guard page.count <= 50 else { throw HostError.invalidResult("page exceeded 50") }
                forward += page.map(\.id)
                anchor = page.last?.key
                if page.count < 50 { break }
            } while true
            expected = forward
            try check("forward_keyset_visits_every_original_once", Set(forward).count == 2202 && forward.count == 2202)
            var backward: [String] = []
            anchor = nil
            repeat {
                let page = try catalog.shelf(query: "", anchor: anchor, before: true)
                backward.insert(contentsOf: page.map(\.id), at: 0)
                anchor = page.first?.key
                if page.count < 50 { break }
            } while true
            try check("reverse_keyset_is_exact_inverse", backward == forward)
            var ties: [String] = []; anchor = nil
            repeat {
                let page = try catalog.shelf(query: "Tie title", anchor: anchor)
                ties += page.map(\.id); anchor = page.last?.key
                if page.count < 50 { break }
            } while true
            try check("same_title_uses_130_stable_source_keys", ties.count == 130 && Set(ties).count == 130 && ties == ties.sorted())
            try check("literal_percent_underscore_and_bound_parameters", try catalog.shelf(query: "100%_", anchor: nil).count == 1)
            try check("title_ascii_case_search", try catalog.shelf(query: "bOoK 0201", anchor: nil).count == 1)
            try check("independent_author_search", try catalog.shelf(query: "Unique Shelf Author", anchor: nil).count == 1)
            try check("empty_search_result", try catalog.shelf(query: "not a shelf title", anchor: nil).isEmpty)
            let canonicalTitle = try catalog.shelf(query: "Café Unicode", anchor: nil)
            let canonicalAuthor = try catalog.shelf(query: "Réné Unique", anchor: nil)
            FileHandle.standardOutput.write(Data("SHELF canonical title=\(canonicalTitle.count) author=\(canonicalAuthor.count)\n".utf8))
            try check("canonical_title_and_author_search_preserves_display_bytes", canonicalTitle.count == 1 &&
                canonicalAuthor.count == 1 && Array(canonicalTitle[0].title.utf8) == Array("Cafe\u{301} Unicode".utf8) &&
                Array(canonicalAuthor[0].author.utf8) == Array("Re\u{301}ne\u{301} Unique".utf8))
            let middle = try catalog.shelf(query: "", anchor: nil)[30]
            try check("inclusive_restore_keeps_exact_top_key", try catalog.shelf(query: "", anchor: middle.key, inclusive: true).first?.id == middle.id)
            try catalog.close()
            try FileManager.default.removeItem(at: input)
        }
        // Deterministic old-result rejection exercises the production state machine.
        let defaults = UserDefaults(suiteName: "EXR.ShelfReview.\(UUID().uuidString)")!
        var responses: [(Result<[HostShelfBook], Error>) -> Void] = []
        let shelf = HostShelf(defaults: defaults)
        shelf.connect { _, _, _, _, completion in responses.append(completion) }
        shelf.query = "new query"; shelf.search()
        responses[0](.success([]))
        try check("old_generation_cannot_replace_new_query", shelf.discarded == 1 && shelf.query == "new query" && shelf.rows.isEmpty)
        let catalog = try queue.sync { try HostCatalog(path: output.appendingPathComponent("ShelfSeed-reader-catalog.db"),
            migrationURL: resources.appendingPathComponent("reader-catalog-v1.sql"), ownerQueue: queue) }
        let pageDefaults = UserDefaults(suiteName: "EXR.ShelfPages.\(UUID().uuidString)")!
        let paged = HostShelf(defaults: pageDefaults)
        var deferred = false
        var pending: (() -> Void)?
        paged.connect { query, anchor, before, inclusive, done in
            let result = Result { try queue.sync { try catalog.shelf(query: query, anchor: anchor, before: before, inclusive: inclusive) } }
            if deferred { pending = { done(result) } } else { done(result) }
        }
        var appendKeepsNativeOffset = true
        func settlePage() {
            let deadline = Date().addingTimeInterval(1)
            while paged.loading && Date() < deadline {
                RunLoop.current.run(until: Date().addingTimeInterval(0.01))
            }
        }
        func layout(_ id: String) {
            paged.didScroll(revision: paged.restoreRevision)
            let priorKeys = paged.rows.map(\.id), priorEpoch = paged.geometryRevision
            paged.observe([id: CGRect(x: 0, y: 0, width: 100, height: 40)], size: CGSize(width: 100, height: 100), revision: paged.geometryRevision)
            settlePage()
            if paged.rows.count > priorKeys.count && Array(paged.rows.prefix(priorKeys.count).map(\.id)) == priorKeys {
                appendKeepsNativeOffset = appendKeepsNativeOffset && paged.geometryRevision == priorEpoch && !paged.needsScroll
            }
        }
        func acknowledge() {
            for _ in 0..<4 {
                if let key = paged.restoreKey { layout(key) }
                if !paged.observation.contains("\"restoring_layout\":true") { break }
            }
        }
        acknowledge()
        var visited = Set(paged.rows.map(\.id)), turns = 0
        while paged.after {
            guard let last = paged.rows.last, turns < 100 else { throw HostError.invalidResult("forward state did not advance") }
            layout(last.id); acknowledge(); visited.formUnion(paged.rows.map(\.id)); turns += 1
        }
        var reverse = Set(paged.rows.map(\.id)); turns = 0
        while paged.before {
            guard let first = paged.rows.first, turns < 100 else { throw HostError.invalidResult("reverse state did not advance") }
            layout(first.id); acknowledge(); reverse.formUnion(paged.rows.map(\.id)); turns += 1
        }
        try check("production_state_bounds_both_real_traversals", visited.count == 2202 && reverse.count == 2202 &&
            paged.rows.count <= 150 && paged.maximumRows == 150 && appendKeepsNativeOffset)
        let chosen = paged.rows[25]
        layout(chosen.id); paged.save()
        let saved = pageDefaults.data(forKey: "EXRShelfTop")
        FileHandle.standardOutput.write(Data("SHELF before refresh saved=\(saved != nil) chosen=\(chosen.id) state=\(paged.observation)\n".utf8))
        deferred = true; paged.refresh(); paged.save()
        FileHandle.standardOutput.write(Data("SHELF during refresh saved_unchanged=\(pageDefaults.data(forKey: "EXRShelfTop") == saved) state=\(paged.observation)\n".utf8))
        try check("refresh_interruption_retains_saved_top_key", paged.loading && paged.rows.isEmpty &&
            saved != nil && pageDefaults.data(forKey: "EXRShelfTop") == saved)
        deferred = false; pending?(); pending = nil
        let restoredFrame = [chosen.id: CGRect(x: 0, y: 0, width: 100, height: 40)]
        let preScrollEpoch = paged.geometryRevision
        paged.observe(restoredFrame, size: CGSize(width: 100, height: 100), revision: preScrollEpoch)
        let preScrollRejected = paged.observation.contains("\"restoring_layout\":true")
        paged.didScroll(revision: paged.restoreRevision)
        paged.observe(restoredFrame, size: CGSize(width: 100, height: 100), revision: preScrollEpoch)
        let sameKeyOldEpochRejected = paged.observation.contains("\"restoring_layout\":true")
        let priorTop = paged.top
        paged.observe(restoredFrame, size: CGSize(width: 100, height: 100), revision: paged.geometryRevision, complete: false)
        let partialSnapshotRejected = paged.top == priorTop && paged.observation.contains("\"restoring_layout\":true")
        if let wrong = paged.rows.dropFirst().first { layout(wrong.id) }
        let stillRestoring = paged.observation.contains("\"restoring_layout\":true")
        let retryDeadline = Date().addingTimeInterval(1)
        while !paged.needsScroll && Date() < retryDeadline { RunLoop.current.run(until: Date().addingTimeInterval(0.01)) }
        let requestsRealRetry = paged.needsScroll && paged.restoreKey == chosen.id
        paged.didScroll(revision: paged.restoreRevision)
        let beforePrependEpoch = paged.geometryRevision
        paged.observe(restoredFrame, size: CGSize(width: 100, height: 100), revision: beforePrependEpoch)
        settlePage()
        let prepended = paged.geometryRevision != beforePrependEpoch && paged.rows.first?.id != chosen.id
        paged.observe(restoredFrame, size: CGSize(width: 100, height: 100), revision: beforePrependEpoch)
        let oldPrependFrameRejected = paged.observation.contains("\"restoring_layout\":true")
        acknowledge()
        let probes = HostShelf(defaults: UserDefaults(suiteName: "EXR.ShelfProbes.\(UUID().uuidString)")!)
        probes.connect { query, anchor, before, inclusive, done in
            done(Result { try queue.sync { try catalog.shelf(query: query, anchor: anchor, before: before, inclusive: inclusive) } })
        }
        let measuredRows = probes.rows
        let oldProbeEpoch = probes.geometryRevision
        probes.didScroll(revision: probes.restoreRevision)
        let measuredEpoch = probes.geometryRevision
        probes.measureProbe(key: nil, frame: .zero, size: CGSize(width: 100, height: 100), revision: measuredEpoch)
        for (index, row) in measuredRows.dropLast().enumerated() {
            probes.measureProbe(key: row.id, frame: CGRect(x: 0, y: CGFloat(index * 40), width: 100, height: 40),
                size: CGSize(width: 100, height: 40), revision: measuredEpoch)
        }
        RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        let incompleteProbesRejected = probes.top == nil && probes.observation.contains("\"restoring_layout\":true")
        let lastMeasured = measuredRows.last!
        let lastMeasuredFrame = CGRect(x: 0, y: CGFloat((measuredRows.count - 1) * 40), width: 100, height: 40)
        probes.measureProbe(key: lastMeasured.id, frame: lastMeasuredFrame, size: CGSize(width: 100, height: 40), revision: oldProbeEpoch)
        RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        let staleLastProbeRejected = probes.top == nil && probes.observation.contains("\"restoring_layout\":true")
        probes.measureProbe(key: lastMeasured.id, frame: lastMeasuredFrame, size: CGSize(width: 100, height: 40), revision: measuredEpoch)
        let probeDeadline = Date().addingTimeInterval(1)
        while probes.observation.contains("\"restoring_layout\":true") && Date() < probeDeadline {
            RunLoop.current.run(until: Date().addingTimeInterval(0.01))
        }
        let completeCurrentProbesAcknowledge = probes.top == measuredRows.first?.key &&
            !probes.observation.contains("\"restoring_layout\":true")
        try check("layout_acknowledges_exact_restored_source", preScrollRejected && sameKeyOldEpochRejected && partialSnapshotRejected && requestsRealRetry &&
            stillRestoring && prepended && oldPrependFrameRejected && incompleteProbesRejected && staleLastProbeRejected &&
            completeCurrentProbesAcknowledge && paged.top == chosen.key &&
            !paged.observation.contains("\"restoring_layout\":true"))
        let terminal = try queue.sync { try catalog.shelf(query: "", anchor: nil, before: true) }
        let tailDefaults = UserDefaults(suiteName: "EXR.ShelfTail.\(UUID().uuidString)")!
        let terminalTarget = terminal[terminal.count - 2]
        tailDefaults.set(try JSONEncoder().encode(terminalTarget.key), forKey: "EXRShelfTop")
        let tail = HostShelf(defaults: tailDefaults)
        tail.connect { query, anchor, before, inclusive, done in
            done(Result { try queue.sync { try catalog.shelf(query: query, anchor: anchor, before: before, inclusive: inclusive) } })
        }
        tail.didScroll(revision: tail.restoreRevision)
        tail.observe([terminalTarget.id: CGRect(x: 0, y: 0, width: 100, height: 40)], size: CGSize(width: 100, height: 400), revision: tail.geometryRevision)
        let tailDeadline = Date().addingTimeInterval(1)
        while tail.loading && Date() < tailDeadline {
            RunLoop.current.run(until: Date().addingTimeInterval(0.01))
        }
        var clamped: [String: CGRect] = [:]
        for (index, row) in tail.rows.suffix(10).enumerated() {
            clamped[row.id] = CGRect(x: 0, y: CGFloat(index * 40), width: 100, height: 40)
        }
        tail.didScroll(revision: tail.restoreRevision)
        tail.observe(clamped, size: CGSize(width: 100, height: 400), revision: tail.geometryRevision)
        try check("terminal_viewport_clamp_keeps_real_visible_top", !tail.after && tail.top == tail.rows[tail.rows.count - 10].key &&
            !tail.observation.contains("\"restoring_layout\":true"))
        let tall = HostShelf(defaults: UserDefaults(suiteName: "EXR.ShelfTall.\(UUID().uuidString)")!)
        tall.connect { query, anchor, before, inclusive, done in
            done(Result { try queue.sync { try catalog.shelf(query: query, anchor: anchor, before: before, inclusive: inclusive) } })
        }
        func tallLayout() {
            tall.didScroll(revision: tall.restoreRevision)
            var positions: [String: CGRect] = [:]
            for (index, row) in tall.rows.prefix(60).enumerated() {
                positions[row.id] = CGRect(x: 0, y: CGFloat(index * 40), width: 100, height: 40)
            }
            tall.observe(positions, size: CGSize(width: 100, height: 2400), revision: tall.geometryRevision)
        }
        tallLayout(); tallLayout()
        try check("tall_native_viewport_prefetches_without_initial_scroll_range", tall.rows.count == 100 &&
            tall.top == tall.rows.first?.key && !tall.observation.contains("\"restoring_layout\":true"))
        try queue.sync { try catalog.close() }
        let manifest: [String: Any] = ["source_sha": ProcessInfo.processInfo.environment["GITHUB_SHA"]!,
            "run_id": ProcessInfo.processInfo.environment["GITHUB_RUN_ID"]!,
            "attempt": ProcessInfo.processInfo.environment["GITHUB_RUN_ATTEMPT"]!,
            "accepted": true, "books": 2202, "source_keys": expected, "checks": groups,
            "seeded_via": "actual public macOS SDK imports; portable stored originals", "failed": 0, "skipped": 0]
        try JSONSerialization.data(withJSONObject: manifest, options: [.prettyPrinted, .sortedKeys])
            .write(to: output.appendingPathComponent("shelf-seed.json"))
        print("Shelf native accepted=true checks=\(groups.count) originals=2202")
    }
}
