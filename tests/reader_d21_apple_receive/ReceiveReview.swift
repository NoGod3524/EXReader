// SPDX-License-Identifier: MIT
import Foundation
import CReaderProduct

@main struct ReceiveReview {
    static func main() throws {
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
        let profile = HostAccountProfile(id: UUID().uuidString.lowercased(), root: root)
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
                try catalog.close()
            }
        }
        let session = HostAccountSession()
        try session.start(profile: profile, directory: base, authorization: authorization) {}
        try check("actual_https_sweep", wait { !session.running } && session.state == "本轮扫描完成")
        session.close(); try check("network_owner_closed", wait { session.state == "已关闭" })
        if mode != "seed" {
            try queue.sync {
                let catalog = try HostCatalog(path: base.appendingPathComponent("reader-catalog.db"), migrationURL: migration, ownerQueue: queue)
                defer { try? catalog.close() }
                let cancel = HostCancelBox()
                let received = try catalog.receivePage(after: nil, checkCancellation: cancel.check)
                try check("remote_projection", received.projected == 1 && received.conflicts == 0)
                let rows = try catalog.shelf(query: "", anchor: nil)
                try check("cloud_book_visible_without_sdk_mapping", rows.count == 1 && rows[0].sdkID == 0)
                let selected = try catalog.receivedBook(key: rows[0].id)
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
                try catalog.execute("UPDATE reader_books SET title='Local title',favorite=1")
                let second = try catalog.receivePage(after: nil, checkCancellation: cancel.check)
                try check("duplicate_preserves_local_metadata", second.projected == 0 && catalog.text("SELECT title||favorite FROM reader_books") == "Local title1")
                let offline = try catalog.shelf(query: "", anchor: nil)
                try check("offline_mapping_retained", offline.count == 1 && offline[0].sdkID == id)
                let cancelled = HostCancelBox(); cancelled.cancel()
                var rejected = false
                do { _ = try HostReceivedOriginal.prepare(selected, directory: base, profile: profile, authorization: authorization, cancel: cancelled) } catch { rejected = true }
                try check("cancel_keeps_local_book", rejected && library.books().count == 1)
                try check("repeat_has_single_sdk_copy", library.books().count == 1)
            }
        }
        let result: [String: Any] = ["mode": mode, "source_sha": ProcessInfo.processInfo.environment["GITHUB_SHA"]!,
            "run_id": ProcessInfo.processInfo.environment["GITHUB_RUN_ID"]!, "attempt": ProcessInfo.processInfo.environment["GITHUB_RUN_ATTEMPT"]!, "checks": checks]
        try JSONSerialization.data(withJSONObject: result, options: [.prettyPrinted,.sortedKeys]).write(to: base.appendingPathComponent("result.json"))
    }
}
