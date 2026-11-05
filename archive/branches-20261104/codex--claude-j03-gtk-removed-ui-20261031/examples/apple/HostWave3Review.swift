// SPDX-License-Identifier: MIT
#if EXR_APPLE_WAVE3 && EXR_APPLE_RAW3 && EXR_APPLE_HOST_REVIEW
import Foundation
import CryptoKit
import CEXReader
import CReaderProduct
import CReaderSQLite

// Fixture preparation runs only in the Actions-launched review application.
// It uses a separate product snapshot; production import still consumes the
// resulting portable file with the same preview/confirm and FOUND policy.
enum HostWave3Review {
    // Hash every retained revision and outbox value in deterministic order.
    // Read on the host owner queue so the two observations surround import.
    static func revisionIdentity(root: URL) throws -> String {
        var db: OpaquePointer?
        guard sqlite3_open_v2(root.appendingPathComponent("reader-catalog.db").path, &db,
                              SQLITE_OPEN_READONLY | SQLITE_OPEN_FULLMUTEX, nil) == SQLITE_OK, let db else {
            if let db { sqlite3_close_v2(db) }
            throw HostError.invalidResult("无法读取修订快照")
        }
        defer { sqlite3_close_v2(db) }
        var digest = SHA256()
        for sql in ["SELECT revision_id,entity_kind,entity_key,operation,body_json,body_sha256 FROM reader_revisions ORDER BY revision_id",
                    "SELECT queue_id,revision_id,attempts,last_error FROM reader_outbox ORDER BY queue_id"] {
            var statement: OpaquePointer?
            guard sqlite3_prepare_v2(db, sql, -1, &statement, nil) == SQLITE_OK, let statement else {
                throw HostError.invalidResult("无法准备修订快照")
            }
            defer { sqlite3_finalize(statement) }
            digest.update(data: Data(sql.utf8))
            var result = sqlite3_step(statement)
            while result == SQLITE_ROW {
                for column in 0..<sqlite3_column_count(statement) {
                    let count = Int(sqlite3_column_bytes(statement, column))
                    digest.update(data: Data("\(sqlite3_column_type(statement, column)):\(count):".utf8))
                    if count > 0, let bytes = sqlite3_column_blob(statement, column) {
                        digest.update(data: Data(bytes: bytes, count: count))
                    }
                }
                result = sqlite3_step(statement)
            }
            guard result == SQLITE_DONE else { throw HostError.invalidResult("无法完成修订快照") }
        }
        return digest.finalize().map { String(format: "%02x", $0) }.joined()
    }

    static func checkExports(jsonl: URL, markdown: URL) throws {
        let data = try Data(contentsOf: jsonl)
        guard let text = String(data: data, encoding: .utf8), text.hasSuffix("\n") else {
            throw HostError.invalidResult("JSONL 不是完整 UTF-8")
        }
        let lines = text.split(separator: "\n").map(String.init)
        let objects = try lines.map { line -> [String: Any] in
            guard let object = try JSONSerialization.jsonObject(with: Data(line.utf8)) as? [String: Any] else {
                throw HostError.invalidResult("JSONL 行不是对象")
            }
            return object
        }
        guard objects.count == 3, objects[0]["type"] as? String == "header",
              objects[0]["format"] as? String == "exreader-annotation-export-raw3",
              objects[0]["format_version"] as? Int == 1,
              let sourceBytes = objects[0]["source_bytes"] as? Int, sourceBytes > 0,
              let key = objects[0]["book_key"] as? String, !key.isEmpty,
              objects[1]["type"] as? String == "annotation",
              let annotation = objects[1]["annotation_id"] as? String, !annotation.isEmpty,
              let heads = objects[1]["heads"] as? [[String: Any]], heads.count == 1,
              let revision = heads[0]["revision_id"] as? String,
              let wire = heads[0]["wire"] as? String,
              let sha = heads[0]["sha256"] as? String,
              let bytes = heads[0]["bytes"] as? Int,
              bytes == wire.utf8.count,
              SHA256.hash(data: Data(wire.utf8)).map({ String(format: "%02x", $0) }).joined() == sha,
              objects[2]["type"] as? String == "footer", objects[2]["complete"] as? Bool == true,
              objects[2]["annotations"] as? Int == 1, objects[2]["head_wires"] as? Int == 1 else {
            throw HostError.invalidResult("JSONL 内容或修订摘要不匹配")
        }
        let markdownText = try String(contentsOf: markdown, encoding: .utf8)
        guard markdownText.contains("书籍标识：`\(key)`"), markdownText.contains("标注标识：`\(annotation)`"),
              markdownText.contains("修订 `\(revision)`"), markdownText.contains("共 1 条标注实体") else {
            throw HostError.invalidResult("Markdown 与 JSONL 修订不一致")
        }
    }

    static func portableFixture(session: HostSession, catalog: HostCatalog, root: URL,
                                nullSelector: Bool, cancel: HostCancelBox) throws -> URL {
        guard let book = session.book, book.isFixed else { throw HostError.invalidInput("请先打开 Sample.pdf 再准备固定页 NULL／冲突文件") }
        let folder = root.appendingPathComponent("wave3-fixtures/" + UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        let source = root.appendingPathComponent("reader-catalog.db"), target = folder.appendingPathComponent("source.db")
        var from: OpaquePointer?, to: OpaquePointer?
        guard sqlite3_open_v2(source.path, &from, SQLITE_OPEN_READONLY | SQLITE_OPEN_FULLMUTEX, nil) == SQLITE_OK, let from else {
            throw HostError.invalidResult("夹具产品快照来源无法打开")
        }
        defer { sqlite3_close_v2(from) }
        guard sqlite3_open_v2(target.path, &to, SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE | SQLITE_OPEN_FULLMUTEX, nil) == SQLITE_OK, let to else {
            throw HostError.invalidResult("夹具产品快照无法创建")
        }
        defer { sqlite3_close_v2(to) }
        guard let backup = sqlite3_backup_init(to, "main", from, "main") else { throw HostError.invalidResult("夹具产品快照无法初始化") }
        let copied = sqlite3_backup_step(backup, -1), finished = sqlite3_backup_finish(backup)
        guard copied == SQLITE_DONE, finished == SQLITE_OK else { throw HostError.invalidResult("夹具产品快照未完成") }
        var revisions: OpaquePointer?, revisionError = reader_revision_error()
        guard reader_revisions_open_raw_v3(target.path, &revisions, &revisionError) == READER_REV_OK, let revisions else {
            throw HostError.invalidResult(hostReadingField(revisionError.message))
        }
        var closed: OpaquePointer? = revisions
        defer { _ = reader_revisions_close(&closed, nil) }
        let productBook = try catalog.readingBook(sdkID: book.id), key = productBook.key
        var identityBytes: UInt64 = 0
        let identity = reader_revision_book_identity_raw_v3(revisions, key, &identityBytes, &revisionError)
        if identity == READER_REV_NOT_FOUND {
            try hostProductStrings([HostReadingRequest.newID(), key, productBook.format, productBook.sha256,
                                    productBook.title, productBook.author, productBook.sort]) { strings in
                var context = reader_command_context(), command = reader_book_command(), result = reader_command_result(), error = reader_command_error()
                context.store = revisions; context.revision_id = strings[0]
                command.operation = READER_COMMAND_PUT; command.book_key = strings[1]; command.format = strings[2]
                command.source_sha256 = strings[3]; command.source_bytes = UInt64(productBook.bytes)
                command.title = strings[4]; command.author = strings[5]; command.sort_title = strings[6]; command.favorite = productBook.favorite
                guard reader_command_apply_book_raw_v3(&context, &command, &result, &error) == READER_COMMAND_OK else {
                    throw HostError.invalidResult("固定页夹具原件身份无法准备")
                }
            }
        } else if identity != READER_REV_OK { throw HostError.invalidResult(hostReadingField(revisionError.message)) }
        let capture = try session.readingCapture(cancel: cancel)
        let annotation = HostReadingRequest.newID()
        for index in 0..<(nullSelector ? 1 : 2) {
            try cancel.check()
            try hostProductStrings([HostReadingRequest.newID(), "put", "annotation", key, annotation,
                                    nullSelector ? "typed NULL fixture" : "concurrent fixture \(index)", HOST_SDK_VERSION]) { strings in
                var envelope = reader_rs_envelope()
                envelope.revision_id = strings[0]; envelope.operation = strings[1]; envelope.entity_kind = strings[2]
                envelope.book_key = strings[3]; envelope.annotation_id = strings[4]
                envelope.note_text = strings[5]; envelope.parser_version = strings[6]
                try capture.withRaw { raw in
                    guard let fixed = raw.fixed else { throw HostError.invalidResult("固定页夹具没有公开 SDK 选择器") }
                    var fixedCopy = fixed.pointee
                    if nullSelector { fixedCopy.exact = nil; fixedCopy.exact_size = 0; fixedCopy.end = fixedCopy.start }
                    var rawCopy = raw, wire: UnsafeMutablePointer<CChar>?, bytes = 0, error = reader_rs_error()
                    let encoded = withUnsafePointer(to: &fixedCopy) { input -> reader_rs_status in
                        rawCopy.fixed = input
                        return reader_rs_encode_fixed_v3(revisions, &envelope, &rawCopy, &wire, &bytes, &error)
                    }
                    defer { if let wire { reader_rs_free(wire) } }
                    guard encoded == READER_RS_OK, let wire else { throw HostError.invalidResult(hostReadingField(error.message)) }
                    var info = reader_revision_info(), created: Int32 = 0
                    let digest = SHA256.hash(data: Data(bytes: wire, count: bytes)).map { String(format: "%02x", $0) }.joined()
                    let received = digest.withCString { reader_revision_receive_raw_v3(revisions, wire, bytes, $0, &info, &created, &revisionError) }
                    guard received == READER_REV_OK,
                          created == 1 else { throw HostError.invalidResult(hostReadingField(revisionError.message)) }
                }
            }
        }
        let output = folder.appendingPathComponent(nullSelector ? "typed-null.jsonl" : "concurrent.jsonl")
        var options = reader_annotation_export_options(), stats = reader_annotation_export_stats(), error = reader_annotation_export_error()
        options.struct_size = MemoryLayout<reader_annotation_export_options>.size; options.revisions = revisions
        let status = key.withCString { key in output.path.withCString { path in
            options.book_key = key; options.jsonl_path = path
            return reader_annotation_export_raw3_run(&options, &stats, &error)
        } }
        guard status == READER_ANNOTATION_EXPORT_OK, stats.jsonl_published != 0 else { throw HostError.invalidResult(hostReadingField(error.message)) }
        return output
    }

    static func idleSync(catalog: HostCatalog, root: URL) throws -> HostWave3SyncSnapshot {
        let folder = root.appendingPathComponent("wave3-idle-session", isDirectory: true)
        let originals = folder.appendingPathComponent("originals", isDirectory: true)
        try FileManager.default.createDirectory(at: originals, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        // Use a separate copied product snapshot to avoid binding a real account
        // catalog to this local no-network review session.
        let product = folder.appendingPathComponent("idle.db")
        let fresh = !FileManager.default.fileExists(atPath: product.path)
        var database: OpaquePointer?
        guard sqlite3_open_v2(product.path, &database, SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE, nil) == SQLITE_OK, let database else {
            throw HostError.invalidResult("只读同步夹具无法创建")
        }
        // Initialize exactly the bundled product migration before session create.
        guard let migration = Bundle.main.url(forResource: HostCatalog.resourceName, withExtension: "sql") else {
            sqlite3_close_v2(database); throw HostError.invalidInput("缺少产品迁移")
        }
        if fresh {
            let sql = try String(contentsOf: migration, encoding: .utf8)
            guard sqlite3_exec(database, sql, nil, nil, nil) == SQLITE_OK else { sqlite3_close_v2(database); throw HostError.invalidResult("同步夹具迁移失败") }
        }
        sqlite3_close_v2(database)
        var session: OpaquePointer?
        let status = try hostProductStrings([product.path, folder.path, originals.path, "b5b364b0-8059-41d1-b411-13a9f7d8c945", "https://127.0.0.1:1/"]) { values -> reader_session_status in
            var config = reader_session_config()
            config.product_path = values[0]; config.private_directory = values[1]; config.original_directory = values[2]
            config.account_id = values[3]; config.dav.root_url = values[4]
            return reader_session_create_raw_v3(&config, &session)
        }
        guard status == READER_SESSION_OK, let active = session else { throw HostError.invalidResult("空闲原生同步会话无法创建") }
        defer {
            _ = reader_session_request_close(active)
            var snapshot = reader_session_snapshot()
            while reader_session_observe(active, &snapshot) == READER_SESSION_OK && snapshot.state != READER_SESSION_CLOSED { Thread.sleep(forTimeInterval: 0.001) }
            _ = reader_session_destroy(&session)
        }
        // No start call: the only module operation is immutable capture.
        return try HostWave3Worker.sync(session: active, catalog: catalog)
    }
}
#endif
