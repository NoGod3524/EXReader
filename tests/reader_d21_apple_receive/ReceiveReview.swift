// SPDX-License-Identifier: MIT
import Foundation
import CReaderProduct

@main struct ReceiveReview {
    static func main() {
        do { try run() }
        catch {
            fputs("D21 native receive failed: \(error)\n", stderr)
            exit(1)
        }
    }
    static func run() throws {
        let mode = CommandLine.arguments[1], root = CommandLine.arguments[2]
        let base = URL(fileURLWithPath: CommandLine.arguments[3])
        let migration = URL(fileURLWithPath: CommandLine.arguments[4])
        let source = URL(fileURLWithPath: CommandLine.arguments[5])
        let secret = ProcessInfo.processInfo.environment["READER_ACCOUNT_TEST_PASSWORD"]!
        let authorization = Data(("Basic " + Data(("reader:" + secret).utf8).base64EncodedString()).utf8)
        let queue = DispatchQueue(label: "d21-native-owner")
        try FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
        var checks: [String] = []
        func check(_ name: String, _ condition: @autoclosure () throws -> Bool) throws {
            guard try condition() else { throw HostError.invalidResult(name) }
            checks.append(name); print("PASS " + name)
        }
        func wait(_ ready: () -> Bool) -> Bool {
            let deadline = Date().addingTimeInterval(180)
            while Date() < deadline { if ready() { return true }; RunLoop.current.run(until: Date().addingTimeInterval(0.02)) }
            return ready()
        }
        // The public session deliberately binds a product store to one exact
        // account UUID/root across processes. A test restart must honor it too.
        let profileURL = base.appendingPathComponent("profile.json")
        let profile: HostAccountProfile
        if FileManager.default.fileExists(atPath: profileURL.path) {
            profile = try JSONDecoder().decode(HostAccountProfile.self, from: Data(contentsOf: profileURL))
            try check("same_account_restart_identity", profile.root == root)
        } else {
            profile = HostAccountProfile(id: UUID().uuidString.lowercased(), root: root)
            try JSONEncoder().encode(profile).write(to: profileURL, options: .atomic)
        }
        if mode == "seed" {
            try queue.sync {
                let catalog = try HostCatalog(path: base.appendingPathComponent("reader-catalog.db"), migrationURL: migration, ownerQueue: queue)
                defer { try? catalog.close() }
                let library = try HostLibrary(path: base.appendingPathComponent("library.sqlite"))
                let imported = try library.importUnique(file: source, title: "D21 Remote Book")
                let book = try library.books().first { $0.id == imported.id }!
                let fingerprint = try library.sourceFingerprint(book: book)
                try catalog.attach(format: fingerprint.format, sha256: fingerprint.sha256, bytes: fingerprint.bytes,
                                   title: "D21 Remote Book", author: "D21", sdkID: book.id, locationKind: "reflow_global")
                let rows = try catalog.syncPage()
                try catalog.withHistory { try catalog.bootstrapVerified(rows[0], store: $0) }
                try library.exportSyncOriginal(bookID: book.id, expected: fingerprint,
                    directory: base.appendingPathComponent("sync-originals"), cancel: HostCancelBox())
            }
        } else {
            try queue.sync {
                let catalog = try HostCatalog(path: base.appendingPathComponent("reader-catalog.db"), migrationURL: migration, ownerQueue: queue)
                defer { try? catalog.close() }
                if mode == "receive" {
                    let oldSource = base.appendingPathComponent("old-local.txt")
                    try Data("Old local book remains independent of remote receiving.\n".utf8).write(to: oldSource)
                    let library = try HostLibrary(path: base.appendingPathComponent("library.sqlite"))
                    let imported = try library.importUnique(file: oldSource, title: "Old local book")
                    let book = try library.books().first { $0.id == imported.id }!
                    let fingerprint = try library.sourceFingerprint(book: book)
                    try catalog.attach(format: fingerprint.format, sha256: fingerprint.sha256, bytes: fingerprint.bytes,
                                       title: "Old local book", author: "Local", sdkID: book.id, locationKind: library.locationKind(book: book))
                }
            }
        }
        if mode == "fault" || mode == "retry" || mode == "cancel" {
            try queue.sync {
                let catalog = try HostCatalog(path: base.appendingPathComponent("reader-catalog.db"), migrationURL: migration, ownerQueue: queue)
                defer { try? catalog.close() }
                let rows = try catalog.shelf(query: "", anchor: nil)
                let selected = try catalog.receivedBook(key: rows.first { $0.title != "Old local book" }!.id)
                let cache = base.appendingPathComponent("sync").appendingPathComponent(selected.sha256 + "." + selected.format)
                if FileManager.default.fileExists(atPath: cache.path) { try FileManager.default.removeItem(at: cache) }
                var rejected = false
                let transferCancel = HostCancelBox()
                if mode == "cancel" { DispatchQueue.global().asyncAfter(deadline: .now() + 0.15) { transferCancel.cancel() } }
                do {
                    let copy = try HostReceivedOriginal.prepare(selected, directory: base, profile: profile, authorization: authorization, cancel: transferCancel)
                    try copy.close()
                } catch { rejected = true }
                try check("remote_fault_or_retry_expected_result", rejected == (mode != "retry"))
                let library = try HostLibrary(path: base.appendingPathComponent("library.sqlite"))
                try check("failed_download_preserves_existing_local_book", library.books().count == 2)
            }
            let result: [String: Any] = ["mode": mode, "checks": checks, "source_sha": ProcessInfo.processInfo.environment["GITHUB_SHA"]!]
            try JSONSerialization.data(withJSONObject: result, options: [.prettyPrinted]).write(to: base.appendingPathComponent(mode + "-result.json"))
            return
        }
        let session = HostAccountSession()
        try session.start(profile: profile, directory: base, authorization: authorization) {}
        let finished = wait { !session.running }
        try check("actual_https_sweep state=\(session.state) message=\(session.message)", finished && session.state == "本轮扫描完成")
        session.close(); try check("network_owner_closed", wait { session.state == "已关闭" })
        if mode == "conflict" {
            try queue.sync {
                let catalog = try HostCatalog(path: base.appendingPathComponent("reader-catalog.db"), migrationURL: migration, ownerQueue: queue)
                defer { try? catalog.close() }
                let page = try catalog.receivePage(after: nil, checkCancellation: HostCancelBox().check)
                try check("concurrent_remote_roots_report_conflict", page.conflicts == 1 && page.projected == 0)
                let rows = try catalog.shelf(query: "", anchor: nil)
                try check("conflict_retains_local_metadata_and_mapping", rows.count == 2 && rows.contains { $0.title == "Local title" && $0.sdkID > 0 })
                var rejected = false
                do { _ = try catalog.receivedBook(key: rows.first { $0.title == "Local title" }!.id) } catch { rejected = true }
                try check("conflict_never_selects_remote_winner", rejected)
                let library = try HostLibrary(path: base.appendingPathComponent("library.sqlite"))
                try check("conflict_retains_existing_sdk_original", library.books().count == 2)
            }
        }
        if mode == "receive" {
            try queue.sync {
                let catalog = try HostCatalog(path: base.appendingPathComponent("reader-catalog.db"), migrationURL: migration, ownerQueue: queue)
                defer { try? catalog.close() }
                let cancel = HostCancelBox()
                let received = try catalog.receivePage(after: nil, checkCancellation: cancel.check)
                try check("remote_projection", received.projected == 1 && received.conflicts == 0)
                let rows = try catalog.shelf(query: "", anchor: nil)
                try check("cloud_book_visible_without_sdk_mapping", rows.count == 2 && rows.filter { $0.sdkID == 0 }.count == 1)
                let selected = try catalog.receivedBook(key: rows.first { $0.title != "Old local book" }!.id)
                let cached = base.appendingPathComponent("sync").appendingPathComponent(selected.sha256 + "." + selected.format)
                try FileManager.default.removeItem(at: cached)
                let copy = try HostReceivedOriginal.prepare(selected, directory: base, profile: profile, authorization: authorization, cancel: cancel)
                try check("on_demand_original_identity", copy.fingerprint.sha256 == selected.sha256 && UInt64(copy.fingerprint.bytes) == selected.bytes)
                // Import through the same production HostLibrary + catalog mapping.
                let library = try HostLibrary(path: base.appendingPathComponent("library.sqlite"))
                let imported = try library.importUnique(file: copy.url, title: selected.title, cancel: cancel)
                let book = try library.books().first { $0.id == imported.id }!
                let fingerprint = try library.sourceFingerprint(book: book)
                try check("stored_original_identity", fingerprint == copy.fingerprint)
                let id = try catalog.attach(format: fingerprint.format, sha256: fingerprint.sha256, bytes: fingerprint.bytes, title: book.title, author: book.author, sdkID: book.id, locationKind: library.locationKind(book: book))
                try copy.close()
                let offlineCopy = try HostReceivedOriginal.prepare(selected, directory: base, profile: profile, authorization: nil, cancel: cancel)
                try check("verified_cache_without_credentials", offlineCopy.fingerprint == fingerprint)
                try offlineCopy.close()
                try Data("damaged cache".utf8).write(to: cached)
                var damagedRejected = false
                do { _ = try HostReceivedOriginal.prepare(selected, directory: base, profile: profile, authorization: nil, cancel: cancel) } catch { damagedRejected = true }
                try check("damaged_cache_not_trusted_offline", damagedRejected)
                let healed = try HostReceivedOriginal.prepare(selected, directory: base, profile: profile, authorization: authorization, cancel: cancel)
                try check("damaged_cache_download_retry", healed.fingerprint == fingerprint)
                try healed.close()
                let repaired = try HostReceivedOriginal.prepare(selected, directory: base, profile: profile, authorization: nil, cancel: cancel)
                try check("retry_publishes_verified_offline_cache", repaired.fingerprint == fingerprint)
                try repaired.close()
                try catalog.execute("UPDATE reader_books SET title='Local title',favorite=1 WHERE book_key='\(selected.key)'")
                let second = try catalog.receivePage(after: nil, checkCancellation: cancel.check)
                try check("duplicate_preserves_local_metadata", second.projected == 0 && catalog.text("SELECT title||favorite FROM reader_books WHERE book_key='\(selected.key)'") == "Local title1")
                let offline = try catalog.shelf(query: "", anchor: nil)
                try check("offline_mapping_retained", offline.count == 2 && offline.contains { $0.sdkID == id } && offline.contains { $0.title == "Old local book" && $0.sdkID > 0 })
                let cancelled = HostCancelBox(); cancelled.cancel()
                var rejected = false
                do { _ = try HostReceivedOriginal.prepare(selected, directory: base, profile: profile, authorization: authorization, cancel: cancelled) } catch { rejected = true }
                try check("cancel_keeps_local_book", rejected && library.books().count == 2)
                try check("repeat_has_single_sdk_copy", library.books().count == 2)
            }
        }
        let result: [String: Any] = ["mode": mode, "source_sha": ProcessInfo.processInfo.environment["GITHUB_SHA"]!,
            "run_id": ProcessInfo.processInfo.environment["GITHUB_RUN_ID"]!, "attempt": ProcessInfo.processInfo.environment["GITHUB_RUN_ATTEMPT"]!, "checks": checks]
        try JSONSerialization.data(withJSONObject: result, options: [.prettyPrinted,.sortedKeys]).write(to: base.appendingPathComponent(mode == "conflict" ? "conflict-result.json" : "result.json"))
    }
}
