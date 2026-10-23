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
            groups.append(name); print("SHELF PASS \(name)")
        }
        try queue.sync {
            let library = try HostLibrary(path: output.appendingPathComponent("ShelfSeed-library.sqlite"))
            let catalog = try HostCatalog(path: output.appendingPathComponent("ShelfSeed-reader-catalog.db"),
                migrationURL: resources.appendingPathComponent("reader-catalog-v1.sql"), ownerQueue: queue)
            let input = output.appendingPathComponent("seed.txt")
            for index in 0..<2202 {
                let title = index < 130 ? "Tie title" : index == 200 ? "100%_ literal" : String(format: "Book %04d", index)
                let bytes = Data("Stored native shelf book \(index). Offline reading uses these exact original bytes.\n".utf8)
                try bytes.write(to: input)
                _ = try library.importUnique(file: input, title: title)
            }
            let books = try library.books()
            try check("2202_real_public_sdk_originals", books.count == 2202)
            for (index, book) in books.enumerated() {
                let fingerprint = try library.sourceFingerprint(book: book)
                try catalog.attach(format: fingerprint.format, sha256: fingerprint.sha256, bytes: fingerprint.bytes,
                    title: book.title, author: index == 400 ? "Unique Shelf Author" : "", sdkID: book.id,
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
            try check("literal_percent_underscore_and_bound_parameters", catalog.shelf(query: "100%_", anchor: nil).count == 1)
            try check("title_ascii_case_search", catalog.shelf(query: "bOoK 0201", anchor: nil).count == 1)
            try check("independent_author_search", catalog.shelf(query: "Unique Shelf Author", anchor: nil).count == 1)
            try check("empty_search_result", catalog.shelf(query: "not a shelf title", anchor: nil).isEmpty)
            let middle = try catalog.shelf(query: "", anchor: nil)[30]
            try check("inclusive_restore_keeps_exact_top_key", catalog.shelf(query: "", anchor: middle.key, inclusive: true).first?.id == middle.id)
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
