// SPDX-License-Identifier: MIT
import Foundation
import CReaderProduct

@main struct AccountReview {
    static func main() throws {
        let root = CommandLine.arguments[1], folder = URL(fileURLWithPath: CommandLine.arguments[2])
        let migration = URL(fileURLWithPath: CommandLine.arguments[3])
        guard let password = ProcessInfo.processInfo.environment["READER_ACCOUNT_TEST_PASSWORD"] else {
            throw HostError.invalidInput("missing fixture authorization")
        }
        var checks: [String] = []
        func check(_ name: String, _ condition: @autoclosure () throws -> Bool) throws {
            guard try condition() else { throw HostError.invalidResult(name) }
            checks.append(name)
        }
        func wait(_ seconds: TimeInterval = 90, _ ready: () -> Bool) -> Bool {
            let end = Date().addingTimeInterval(seconds)
            while Date() < end {
                if ready() { return true }
                RunLoop.current.run(until: Date().addingTimeInterval(0.02))
            }
            return ready()
        }
        let accounts = HostAccounts(folder: folder)
        try accounts.create(root: root, username: "reader", password: password, remember: true)
        guard let profile = accounts.current else { throw HostError.invalidResult("profile missing") }
        defer {
            var store: OpaquePointer?
            if exr_credentials_open("org.exreader.host.webdav", &store) == EXR_CRED_OK, let store {
                _ = profile.id.withCString { exr_credentials_delete(store, $0) }
                exr_credentials_close(store)
            }
        }
        try check("stable_lowercase_profile_uuid", UUID(uuidString: profile.id)?.uuidString.lowercased() == profile.id)
        let auth = Data(("Basic " + Data(("reader:" + password).utf8).base64EncodedString()).utf8)
        try check("actual_keychain_roundtrip_after_profile_reopen", HostAccounts(folder: folder).authorization(for: profile) == auth)
        let metadata = try Data(contentsOf: folder.appendingPathComponent("accounts.json"))
        try check("metadata_contains_no_authorization", metadata.range(of: Data(password.utf8)) == nil && metadata.range(of: auth) == nil)
        let before = accounts.profiles
        do { try accounts.create(root: "http://localhost/", username: "reader", password: password, remember: true) }
        catch {}
        try check("insecure_root_rejected_without_profile_write", accounts.profiles == before && Data(contentsOf: folder.appendingPathComponent("accounts.json")) == metadata)
        try accounts.updateCredentials(profile, username: "reader", password: password, remember: false)
        var missing = false
        do { _ = try HostAccounts(folder: folder).authorization(for: profile) } catch { missing = true }
        try check("session_only_authorization_not_restored_from_disk", missing && accounts.authorization(for: profile) == auth)
        try accounts.updateCredentials(profile, username: "reader", password: password, remember: true)
        let directory = profile.directory(in: folder)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let other = HostAccountProfile(id: UUID().uuidString.lowercased(), root: root)
        try check("account_directories_are_isolated", directory != other.directory(in: folder))
        let queue = DispatchQueue(label: "account-review.owner")
        let original = Data("Actual Apple account original. Exact retained bytes.\n".utf8)
        var bookKey = ""
        try queue.sync {
            let catalog = try HostCatalog(path: directory.appendingPathComponent("reader-catalog.db"), migrationURL: migration, ownerQueue: queue)
            defer { try? catalog.close() }
            let library = try HostLibrary(path: directory.appendingPathComponent("library.sqlite"))
            let input = directory.appendingPathComponent("original.txt"); try original.write(to: input)
            let imported = try library.importUnique(file: input, title: "Account original")
            guard let book = try library.books().first(where: { $0.id == imported.id }) else { throw HostError.invalidResult("SDK book missing") }
            let fingerprint = try library.sourceFingerprint(book: book)
            try catalog.attach(format: fingerprint.format, sha256: fingerprint.sha256, bytes: fingerprint.bytes,
                               title: "Remote title preserved", author: "Account author", sdkID: book.id, locationKind: "reflow_global")
            let page = try catalog.syncPage()
            try check("bounded_product_sync_page", page.count == 1 && page.count <= 50 && page[0].sdkID == book.id)
            let target = directory.appendingPathComponent("sync-originals", isDirectory: true)
            let expected = HostSourceFingerprint(format: page[0].format, sha256: page[0].sha256, bytes: page[0].bytes)
            try library.exportSyncOriginal(bookID: page[0].sdkID, expected: expected, directory: target, cancel: HostCancelBox())
            let output = target.appendingPathComponent(page[0].sha256 + ".txt")
            try check("exact_public_sdk_original_export", Data(contentsOf: output) == original)
            try library.exportSyncOriginal(bookID: page[0].sdkID, expected: expected, directory: target, cancel: HostCancelBox())
            try check("existing_immutable_original_is_verified_and_reused", Data(contentsOf: output) == original)
            let cancelled = HostCancelBox(); cancelled.cancel(); var refused = false
            do { try library.exportSyncOriginal(bookID: page[0].sdkID, expected: expected, directory: target, cancel: cancelled) } catch { refused = true }
            try check("cancelled_preparation_preserves_the_valid_original", refused && Data(contentsOf: output) == original)
            try catalog.withHistory { try catalog.bootstrapVerified(page[0], store: $0) }
            try catalog.withHistory { try catalog.bootstrapVerified(page[0], store: $0) }
            try check("verified_bootstrap_is_idempotent_history_and_outbox", catalog.scalar("SELECT count(*) FROM reader_revisions") == 1 && catalog.scalar("SELECT count(*) FROM reader_outbox") == 1)
            try check("bootstrap_preserves_product_title_author", catalog.text("SELECT title||'|'||author FROM reader_books") == "Remote title preserved|Account author")
            bookKey = page[0].key
        }
        let session = accounts.controller(for: profile)
        try check("all_windows_share_one_account_controller", session === accounts.controller(for: profile))
        var preparationCancelled = false, overlappingPreparationRefused = false
        try session.beginPreparation { preparationCancelled = true }
        do { try session.beginPreparation {} } catch { overlappingPreparationRefused = true }
        session.close(); session.finishPreparation()
        try check("account_change_cancels_unstarted_preparation", preparationCancelled && overlappingPreparationRefused && !session.preparing)
        var ticks = 0, callbacks = 0
        let timer = Timer.scheduledTimer(withTimeInterval: 0.01, repeats: true) { _ in ticks += 1 }
        defer { timer.invalidate(); session.close() }
        try session.start(profile: profile, directory: directory, authorization: accounts.authorization(for: profile)) { callbacks += 1 }
        try check("native_account_sweep_completes", wait { !session.running && session.completedSweeps == 1 })
        try check("actual_256_shard_account_scan", session.completedShards == 256 && session.steps >= 256 && callbacks == 1)
        try check("main_runloop_active_during_native_https", ticks >= 10)
        session.close()
        try check("closed_before_native_controller_release", wait(10) { session.state == "已关闭" })
        try queue.sync {
            let catalog = try HostCatalog(path: directory.appendingPathComponent("reader-catalog.db"), migrationURL: migration, ownerQueue: queue)
            defer { try? catalog.close() }
            try check("verified_remote_ack_retains_history", catalog.scalar("SELECT count(*) FROM reader_revisions") == 1 && catalog.scalar("SELECT count(*) FROM reader_outbox") == 0)
        }
        let report: [String: Any] = ["accepted": true, "source_sha": ProcessInfo.processInfo.environment["GITHUB_SHA"]!,
            "run_id": ProcessInfo.processInfo.environment["GITHUB_RUN_ID"]!, "attempt": ProcessInfo.processInfo.environment["GITHUB_RUN_ATTEMPT"]!,
            "checks": checks, "main_thread_ticks": ticks, "sweeps": session.completedSweeps, "shards": session.completedShards,
            "book_key": bookKey, "host_account_ui_accepted": false, "physical_device_execution": false]
        try JSONSerialization.data(withJSONObject: report, options: [.sortedKeys, .prettyPrinted])
            .write(to: folder.appendingPathComponent("account.json"))
        print("Native Apple account checks=\(checks.count) accepted=true")
    }
}
