// SPDX-License-Identifier: MIT
import Foundation
// tools/apple_swift.py selects the installed product SQLite header/provider.
import CReaderSQLite
import CReaderProduct
import Darwin

#if EXR_APPLE_RAW3
private let hostCatalogHistoryOpen = reader_revisions_open_raw_v3
private let hostCatalogHeads = reader_revision_heads_raw_v3
private let hostCatalogIdentity = reader_revision_book_identity_raw_v3
private let hostCatalogBook = reader_command_apply_book_raw_v3
#else
private let hostCatalogHistoryOpen = reader_revisions_open
private let hostCatalogHeads = reader_revision_heads
private let hostCatalogIdentity = reader_revision_book_identity
private let hostCatalogBook = reader_command_apply_book
#endif

func hostProductStrings<T>(_ values: [String], _ body: ([UnsafePointer<CChar>?]) throws -> T) rethrows -> T {
    let buffers = values.map { strdup($0) }
    defer { for buffer in buffers { free(buffer) } }
    return try body(buffers.map { $0.map { UnsafePointer($0) } })
}

struct HostProductBook {
    let key: String
    let sdkID: Int64
    let format: String
    let sha256: String
    let bytes: Int64
    let title: String
    let author: String
    let sort: String
    let favorite: Int32
    let locationKind: String
}

struct HostShelfKey: Codable, Equatable {
    let sort: String
    let key: String
}
struct HostShelfBook: Identifiable {
    let key: HostShelfKey
    let sdkID: Int64
    let title: String
    let author: String
    let format: String
    let bytes: Int64
    var id: String { key.key }
}

enum HostCatalogValue {
    case text(String)
    case integer(Int64)
}

enum HostCatalogError: Error, LocalizedError {
    case invalid(String)
    case sqlite(Int32, String)

    var errorDescription: String? {
        switch self {
        case .invalid(let message): return message
        case .sqlite(let code, let message): return "产品书库错误 \(code)：\(message)"
        }
    }
}

/** Product metadata only; all calls belong to the existing host owner queue. */
final class HostCatalog {
    static let applicationID: Int64 = 1163416144 // EXRP; the SDK uses EXRC.
    static let schemaVersion: Int64 = 1
    static let resourceName = "reader-catalog-v1"
    private let ownerQueue: DispatchQueue
    private let path: URL
    private var handle: OpaquePointer?
#if EXR_APPLE_IMPORT_REVIEW
    static var afterProductBookWrite: (() throws -> Void)?
#endif

    convenience init(path: URL, migrationURL: URL, ownerQueue: DispatchQueue) throws {
        let attributes = try FileManager.default.attributesOfItem(atPath: migrationURL.path)
        guard let size = attributes[.size] as? NSNumber, size.intValue > 0, size.intValue <= 128 * 1024 else {
            throw HostCatalogError.invalid("产品书库迁移资源大小无效")
        }
        try self.init(path: path, migration: Data(contentsOf: migrationURL), ownerQueue: ownerQueue)
    }

    init(path: URL, migration: Data, ownerQueue: DispatchQueue) throws {
        dispatchPrecondition(condition: .onQueue(ownerQueue))
        guard !path.path.utf8.contains(0), !migration.isEmpty, migration.count <= 128 * 1024,
              let sql = String(data: migration, encoding: .utf8), !sql.utf8.contains(0),
              !sql.hasPrefix("\u{feff}") else {
            throw HostCatalogError.invalid("产品书库迁移必须为有界的 UTF-8 原始 SQL")
        }
        self.ownerQueue = ownerQueue
        self.path = path
        var opened: OpaquePointer?
        let status = sqlite3_open_v2(path.path, &opened,
                                    SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE | SQLITE_OPEN_FULLMUTEX, nil)
        guard status == SQLITE_OK, let database = opened else {
            let message = opened.map { String(cString: sqlite3_errmsg($0)) } ?? "无法打开数据库"
            if let opened { sqlite3_close_v2(opened) }
            throw HostCatalogError.sqlite(status, message)
        }
        handle = database
        do {
            try check(sqlite3_extended_result_codes(database, 1), database)
            try check(sqlite3_busy_timeout(database, 5000), database)
            try execute("PRAGMA foreign_keys=ON; PRAGMA trusted_schema=OFF;")
            let identity = try scalar("PRAGMA application_id")
            let version = try scalar("PRAGMA user_version")
            if identity != Self.applicationID || version != Self.schemaVersion {
                guard identity == 0, version == 0,
                      try scalar("SELECT count(*) FROM sqlite_master WHERE name NOT GLOB 'sqlite_*'") == 0 else {
                    throw HostCatalogError.invalid("拒绝其他应用、非空或不受支持的产品书库")
                }
                // sqlite3_exec executes the original BEGIN/COMMIT and complete
                // trigger bodies together. Never split the SQL on semicolons.
                try execute(sql)
            }
            guard try scalar("PRAGMA application_id") == Self.applicationID,
                  try scalar("PRAGMA user_version") == Self.schemaVersion,
                  try scalar("PRAGMA foreign_keys") == 1 else {
                throw HostCatalogError.invalid("产品书库迁移未建立完整身份")
            }
        } catch {
            // Keep the file and its prior contents. A foreign database is never
            // recreated or deleted; unfinished migration changes are rolled back.
            sqlite3_exec(database, "ROLLBACK", nil, nil, nil)
            sqlite3_close_v2(database)
            handle = nil
            throw error
        }
    }

    deinit {
        // Normal host teardown explicitly closes on ownerQueue. FULLMUTEX and
        // close_v2 also release a connection if its owner fails before teardown.
        if let handle { sqlite3_close_v2(handle) }
    }

    func close() throws {
        dispatchPrecondition(condition: .onQueue(ownerQueue))
        guard let database = handle else { return }
        try check(sqlite3_close(database), database)
        handle = nil
    }

    func execute(_ sql: String) throws {
        let database = try connection()
        guard !sql.utf8.contains(0) else { throw HostCatalogError.invalid("SQL 包含空字符") }
        try check(sqlite3_exec(database, sql, nil, nil, nil), database)
    }

    func scalar(_ sql: String) throws -> Int64 {
        let (database, statement) = try prepare(sql)
        defer { sqlite3_finalize(statement) }
        try check(sqlite3_step(statement), database, expected: SQLITE_ROW)
        guard sqlite3_column_type(statement, 0) == SQLITE_INTEGER else {
            throw HostCatalogError.invalid("产品书库查询未返回整数")
        }
        return sqlite3_column_int64(statement, 0)
    }

    func text(_ sql: String) throws -> String {
        let (database, statement) = try prepare(sql)
        defer { sqlite3_finalize(statement) }
        try check(sqlite3_step(statement), database, expected: SQLITE_ROW)
        guard let value = sqlite3_column_text(statement, 0) else {
            throw HostCatalogError.invalid("产品书库查询未返回文本")
        }
        return String(cString: value)
    }

    func localIDs() throws -> Set<Int64> {
        let (database, statement) = try prepare("SELECT sdk_book_id FROM reader_local_books")
        defer { sqlite3_finalize(statement) }
        var result = Set<Int64>()
        var status = sqlite3_step(statement)
        while status == SQLITE_ROW {
            guard sqlite3_column_type(statement, 0) == SQLITE_INTEGER else {
                throw HostCatalogError.invalid("产品书库本机 ID 无效")
            }
            result.insert(sqlite3_column_int64(statement, 0))
            status = sqlite3_step(statement)
        }
        try check(status, database, expected: SQLITE_DONE)
        return result
    }

    // Each scoped native history is opened, consumed and closed in the same
    // synchronous owner task. A serial DispatchQueue may reuse different OS
    // threads between tasks; native revision handles never cross that boundary.
    func withHistory<T>(_ body: (OpaquePointer) throws -> T) throws -> T {
        dispatchPrecondition(condition: .onQueue(ownerQueue))
        var store: OpaquePointer?, error = reader_revision_error()
        guard hostCatalogHistoryOpen(path.path, &store, &error) == READER_REV_OK, let opened = store else {
            throw HostCatalogError.invalid("无法打开产品修订历史")
        }
        defer { _ = reader_revisions_close(&store, &error) }
        return try body(opened)
    }

#if EXR_APPLE_WAVE3
    // Legacy position encoding validates v1/v2 through its own public profile;
    // the history component stores the resulting wire only in memory.
    func withLegacyHistory<T>(_ body: (OpaquePointer) throws -> T) throws -> T {
        dispatchPrecondition(condition: .onQueue(ownerQueue))
        var store: OpaquePointer?, error = reader_revision_error()
        guard reader_revisions_open(path.path, &store, &error) == READER_REV_OK, let opened = store else {
            throw HostCatalogError.invalid("无法打开位置验证器")
        }
        defer { _ = reader_revisions_close(&store, &error) }
        return try body(opened)
    }
#endif

    func searchSourceKey(sdkID: Int64) throws -> String {
        let (database, statement) = try prepare("SELECT b.format,b.source_sha256,b.source_bytes FROM reader_books b JOIN reader_local_books l USING(book_key) WHERE l.sdk_book_id=? AND b.deleted=0 LIMIT 2", [.integer(sdkID)])
        defer { sqlite3_finalize(statement) }
        try check(sqlite3_step(statement), database, expected: SQLITE_ROW)
        guard let format = columnText(statement, 0), let sha = columnText(statement, 1),
              sha.utf8.count == 64, sha.utf8.allSatisfy({ (48...57).contains($0) || (97...102).contains($0) }),
              sqlite3_column_type(statement, 2) == SQLITE_INTEGER, sqlite3_column_int64(statement, 2) > 0 else {
            throw HostCatalogError.invalid("搜索原件身份无效")
        }
        let value = "exr3.40.0:projection1:\(format):\(sha):\(sqlite3_column_int64(statement, 2))"
        try check(sqlite3_step(statement), database, expected: SQLITE_DONE)
        return value
    }

    func syncPage(after: String? = nil) throws -> [HostProductBook] {
        let fields = "b.book_key,l.sdk_book_id,b.format,b.source_sha256,b.source_bytes,b.title,b.author,b.sort_title,b.favorite,l.location_kind"
        var sql = "SELECT " + fields + " FROM reader_books b JOIN reader_local_books l USING(book_key) WHERE b.deleted=0"
        var values: [HostCatalogValue] = []
        if let after { sql += " AND b.book_key>?"; values.append(.text(after)) }
        sql += " ORDER BY b.book_key LIMIT 50"
        let (database, statement) = try prepare(sql, values)
        defer { sqlite3_finalize(statement) }
        var result: [HostProductBook] = [], status = sqlite3_step(statement)
        while status == SQLITE_ROW {
            guard let key = columnText(statement, 0), let format = columnText(statement, 2),
                  let sha = columnText(statement, 3), let title = columnText(statement, 5),
                  let author = columnText(statement, 6), let sort = columnText(statement, 7),
                  let mode = columnText(statement, 9), sqlite3_column_type(statement, 1) == SQLITE_INTEGER,
                  sqlite3_column_type(statement, 4) == SQLITE_INTEGER,
                  sqlite3_column_type(statement, 8) == SQLITE_INTEGER else {
                throw HostCatalogError.invalid("产品同步原件身份无效")
            }
            result.append(HostProductBook(key: key, sdkID: sqlite3_column_int64(statement, 1), format: format,
                sha256: sha, bytes: sqlite3_column_int64(statement, 4), title: title, author: author, sort: sort,
                favorite: sqlite3_column_int(statement, 8), locationKind: mode))
            status = sqlite3_step(statement)
        }
        try check(status, database, expected: SQLITE_DONE)
        return result
    }

    func readingBook(sdkID: Int64) throws -> HostProductBook {
        let (database, statement) = try prepare("SELECT b.book_key,b.format,b.source_sha256,b.source_bytes,b.title,b.author,b.sort_title,b.favorite,l.location_kind FROM reader_books b JOIN reader_local_books l USING(book_key) WHERE b.deleted=0 AND l.sdk_book_id=? LIMIT 2", [.integer(sdkID)])
        defer { sqlite3_finalize(statement) }
        try check(sqlite3_step(statement), database, expected: SQLITE_ROW)
        guard let key = columnText(statement, 0), let format = columnText(statement, 1), let sha = columnText(statement, 2),
              let title = columnText(statement, 4), let author = columnText(statement, 5), let sort = columnText(statement, 6),
              let location = columnText(statement, 8), sqlite3_column_type(statement, 3) == SQLITE_INTEGER,
              sqlite3_column_type(statement, 7) == SQLITE_INTEGER else { throw HostCatalogError.invalid("阅读记录原件映射无效") }
        let value = HostProductBook(key: key, sdkID: sdkID, format: format, sha256: sha, bytes: sqlite3_column_int64(statement, 3),
            title: title, author: author, sort: sort, favorite: sqlite3_column_int(statement, 7), locationKind: location)
        try check(sqlite3_step(statement), database, expected: SQLITE_DONE)
        return value
    }

    func bootstrapVerified(_ book: HostProductBook, store: OpaquePointer,
                           verifyOriginal: (() throws -> Void)? = nil) throws {
        var state = reader_revision_state(), error = reader_revision_error()
        let status = book.key.withCString { hostCatalogHeads(store, "book", $0, nil, nil, &state, &error) }
        guard status == READER_REV_OK else { throw HostCatalogError.invalid("无法读取书籍历史") }
        if state.revisions > 0 {
            var bytes: UInt64 = 0
            guard book.key.withCString({ hostCatalogIdentity(store, $0, &bytes, &error) }) == READER_REV_OK,
                  bytes == UInt64(book.bytes) else { throw HostCatalogError.invalid("书籍历史与已验证原件不一致") }
            return
        }
        try verifyOriginal?()
        try hostProductStrings([book.key, book.format, book.sha256, book.title, book.author, book.sort]) { strings in
            var context = reader_command_context(); context.store = store
            var command = reader_book_command(); command.operation = READER_COMMAND_PUT
            command.book_key = strings[0]; command.format = strings[1]; command.source_sha256 = strings[2]
            command.title = strings[3]; command.author = strings[4]; command.sort_title = strings[5]
            command.source_bytes = UInt64(book.bytes); command.favorite = book.favorite
            var result = reader_command_result(), failure = reader_command_error()
            guard hostCatalogBook(&context, &command, &result, &failure) == READER_COMMAND_OK else {
                throw HostCatalogError.invalid("已保留原书，产品历史提交失败")
            }
        }
    }

    func shelf(query: String, anchor: HostShelfKey?, before: Bool = false,
               inclusive: Bool = false) throws -> [HostShelfBook] {
        let normalized = query.precomposedStringWithCanonicalMapping
        guard normalized.unicodeScalars.count <= 256, !normalized.utf8.contains(0) else {
            throw HostCatalogError.invalid("搜索文字超过上限或包含空字符")
        }
        func escaped(_ value: String) -> String {
            value.replacingOccurrences(of: "\\", with: "\\\\")
                .replacingOccurrences(of: "%", with: "\\%")
                .replacingOccurrences(of: "_", with: "\\_")
        }
        let literal = escaped(normalized)
        var sql = "SELECT b.sort_title,b.book_key,coalesce(l.sdk_book_id,0),b.title,b.author,b.format,b.source_bytes FROM reader_books b LEFT JOIN reader_local_books l USING(book_key) WHERE b.deleted=0"
        var values: [HostCatalogValue] = []
        if !query.isEmpty {
            sql += " AND (b.sort_title LIKE ? ESCAPE '\\' OR b.author LIKE ? ESCAPE '\\' OR b.author LIKE ? ESCAPE '\\')"
            values += [.text("%" + literal + "%"), .text("%" + literal + "%"),
                       .text("%" + escaped(normalized.decomposedStringWithCanonicalMapping) + "%")]
        }
        if let anchor {
            sql += " AND (b.sort_title,b.book_key) " + (before ? (inclusive ? "<=" : "<") : (inclusive ? ">=" : ">")) + " (?,?)"
            values += [.text(anchor.sort), .text(anchor.key)]
        }
        sql += before ? " ORDER BY b.sort_title DESC,b.book_key DESC LIMIT 50" : " ORDER BY b.sort_title,b.book_key LIMIT 50"
        let (database, statement) = try prepare(sql, values)
        defer { sqlite3_finalize(statement) }
        var result: [HostShelfBook] = []
        var status = sqlite3_step(statement)
        while status == SQLITE_ROW {
            guard let sort = columnText(statement, 0), let key = columnText(statement, 1),
                  let title = columnText(statement, 3), let author = columnText(statement, 4),
                  let format = columnText(statement, 5), sqlite3_column_type(statement, 2) == SQLITE_INTEGER,
                  sqlite3_column_type(statement, 6) == SQLITE_INTEGER else {
                throw HostCatalogError.invalid("书架行身份无效")
            }
            result.append(HostShelfBook(key: HostShelfKey(sort: sort, key: key), sdkID: sqlite3_column_int64(statement, 2),
                title: title, author: author, format: format, bytes: sqlite3_column_int64(statement, 6)))
            status = sqlite3_step(statement)
        }
        try check(status, database, expected: SQLITE_DONE)
        return before ? Array(result.reversed()) : result
    }

    @discardableResult
    func attach(format: String, sha256: String, bytes: Int64, title: String, author: String,
                sdkID: Int64, locationKind: String) throws -> Int64 {
        let formats = ["epub", "pdf", "cbz", "txt", "html", "fb2", "docx", "rtf", "mobi"]
        guard formats.contains(format), bytes > 0, sdkID > 0, sha256.count == 64,
              sha256.utf8.allSatisfy({ (48...57).contains($0) || (97...102).contains($0) }),
              [title, author, title.precomposedStringWithCanonicalMapping].allSatisfy({
                  !$0.utf8.contains(0) && $0.unicodeScalars.count <= 4096
              }) else { throw HostCatalogError.invalid("产品书籍身份或元数据无效") }
        let key = format + ":" + sha256
        try execute("BEGIN IMMEDIATE")
        do {
            let (database, existing) = try prepare(
                "SELECT format,source_sha256,source_bytes FROM reader_books WHERE book_key=?", [.text(key)])
            defer { sqlite3_finalize(existing) }
            let status = sqlite3_step(existing)
            if status == SQLITE_ROW {
                guard columnText(existing, 0) == format, columnText(existing, 1) == sha256,
                      sqlite3_column_type(existing, 2) == SQLITE_INTEGER,
                      sqlite3_column_int64(existing, 2) == bytes else {
                    throw HostCatalogError.invalid("已存在产品书籍的原件身份不一致")
                }
            } else {
                try check(status, database, expected: SQLITE_DONE)
                try write("INSERT INTO reader_books(book_key,format,source_sha256,source_bytes,title,author,sort_title) VALUES(?,?,?,?,?,?,?)",
                          [.text(key), .text(format), .text(sha256), .integer(bytes), .text(title), .text(author),
                           .text(title.precomposedStringWithCanonicalMapping)])
            }
            // Existing metadata, deleted flags, immutable revisions and outbox
            // are deliberately untouched by a local source attachment.
            let (_, incoming) = try prepare("SELECT book_key,location_kind FROM reader_local_books WHERE sdk_book_id=?", [.integer(sdkID)])
            defer { sqlite3_finalize(incoming) }
            let incomingStatus = sqlite3_step(incoming)
            if incomingStatus == SQLITE_ROW {
                guard columnText(incoming, 0) == key, columnText(incoming, 1) == locationKind else {
                    throw HostCatalogError.invalid("本机书籍 ID 已绑定其他原件或位置模式")
                }
            } else { try check(incomingStatus, database, expected: SQLITE_DONE) }
#if EXR_APPLE_IMPORT_REVIEW
            try Self.afterProductBookWrite?()
#endif
            let (_, local) = try prepare("SELECT sdk_book_id FROM reader_local_books WHERE book_key=?", [.text(key)])
            defer { sqlite3_finalize(local) }
            let localStatus = sqlite3_step(local)
            var chosen = sdkID
            if localStatus == SQLITE_ROW {
                chosen = min(sdkID, sqlite3_column_int64(local, 0))
                if chosen == sdkID {
                    try write("UPDATE reader_local_books SET sdk_book_id=?,location_kind=? WHERE book_key=?",
                              [.integer(sdkID), .text(locationKind), .text(key)])
                }
            } else {
                try check(localStatus, database, expected: SQLITE_DONE)
                try write("INSERT INTO reader_local_books(book_key,sdk_book_id,location_kind) VALUES(?,?,?)",
                          [.text(key), .integer(sdkID), .text(locationKind)])
            }
            try execute("COMMIT")
            return chosen
        } catch {
            try? execute("ROLLBACK")
            throw error
        }
    }

    private func columnText(_ statement: OpaquePointer, _ column: Int32) -> String? {
        guard sqlite3_column_type(statement, column) == SQLITE_TEXT,
              let value = sqlite3_column_text(statement, column) else { return nil }
        return String(cString: value)
    }

    private func write(_ sql: String, _ values: [HostCatalogValue]) throws {
        let (database, statement) = try prepare(sql, values)
        defer { sqlite3_finalize(statement) }
        try check(sqlite3_step(statement), database, expected: SQLITE_DONE)
    }

    private func connection() throws -> OpaquePointer {
        dispatchPrecondition(condition: .onQueue(ownerQueue))
        guard let handle else { throw HostCatalogError.invalid("产品书库已关闭") }
        return handle
    }

    private func prepare(_ sql: String, _ values: [HostCatalogValue] = []) throws -> (OpaquePointer, OpaquePointer) {
        let database = try connection()
        guard !sql.utf8.contains(0) else { throw HostCatalogError.invalid("SQL 包含空字符") }
        var statement: OpaquePointer?
        let status = sqlite3_prepare_v2(database, sql, -1, &statement, nil)
        guard status == SQLITE_OK, let prepared = statement else {
            if let statement { sqlite3_finalize(statement) }
            throw HostCatalogError.sqlite(status, String(cString: sqlite3_errmsg(database)))
        }
        do {
            for (index, value) in values.enumerated() {
                let status: Int32
                switch value {
                case .integer(let number): status = sqlite3_bind_int64(prepared, Int32(index + 1), number)
                case .text(let text):
                    guard !text.utf8.contains(0) else { throw HostCatalogError.invalid("产品书库参数包含空字符") }
                    status = text.withCString {
                        sqlite3_bind_text(prepared, Int32(index + 1), $0, -1,
                                          unsafeBitCast(-1, to: sqlite3_destructor_type.self))
                    }
                }
                try check(status, database)
            }
        } catch { sqlite3_finalize(prepared); throw error }
        return (database, prepared)
    }

    private func check(_ status: Int32, _ database: OpaquePointer, expected: Int32 = SQLITE_OK) throws {
        guard status == expected else {
            throw HostCatalogError.sqlite(status, String(cString: sqlite3_errmsg(database)))
        }
    }
}

// Explicit receive adapter. History is authoritative; SDK IDs are device-local.
// Only first publication creates metadata: a later cloud scan never overwrites
// a locally edited title, favorite, location, or the active reader's progress.
struct HostReceivedBook {
    let key: String, revision: String, title: String, format: String, sha256: String
    let bytes: UInt64
}
struct HostReceivePage {
    var last: String?
    var count = 0, projected = 0, conflicts = 0, retained = 0
}
private struct HostReceiveEntity {
    let key: String
    let info: reader_revision_info
    let selection: reader_revision_selection
}
private final class HostReceiveEntities { var rows: [HostReceiveEntity] = [] }
private func hostReceiveCString<T>(_ value: T) -> String {
    var value = value
    return withUnsafeBytes(of: &value) { String(cString: $0.baseAddress!.assumingMemoryBound(to: CChar.self)) }
}
#if EXR_APPLE_RAW3
private let hostReceiveEntities = reader_revision_entities_page_raw_v3
private let hostReceiveSelected = reader_revision_selected_raw_v3
private let hostReceiveTitle = reader_revision_book_title_raw_v3
private let hostReceiveProject = reader_revision_project_raw_v3
#else
private let hostReceiveEntities = reader_revision_entities_page
private let hostReceiveSelected = reader_revision_selected
private let hostReceiveTitle = reader_revision_book_title
private let hostReceiveProject = reader_revision_project
#endif
extension HostCatalog {
    func receivePage(after: String?, checkCancellation: () throws -> Void) throws -> HostReceivePage {
        try withHistory { history in
            let copied = HostReceiveEntities()
            let context = Unmanaged.passUnretained(copied).toOpaque()
            let visit: reader_revision_entity_fn = { context, pointer in
                guard let context, let pointer, let key = pointer.pointee.entity_key else { return 1 }
                Unmanaged<HostReceiveEntities>.fromOpaque(context).takeUnretainedValue().rows.append(
                    HostReceiveEntity(key: String(cString: key), info: pointer.pointee.info, selection: pointer.pointee.selection))
                return 0
            }
            let status = hostProductStrings([after ?? ""]) { strings in
                hostReceiveEntities(history, "book", after == nil ? nil : strings[0], 1, 50, visit, context, nil)
            }
            guard status == READER_REV_OK else { throw HostCatalogError.invalid("无法读取接收历史；请重试同步") }
            var result = HostReceivePage()
            for row in copied.rows {
                try checkCancellation()
                result.count += 1; result.last = row.key
                guard row.selection.kind == READER_SELECTION_SAFE else { result.conflicts += 1; continue }
                if row.selection.graph.deleted != 0 { result.retained += 1; continue }
                let (_, statement) = try prepare("SELECT 1 FROM reader_books WHERE book_key=?", [.text(row.key)])
                let exists = sqlite3_step(statement)
                sqlite3_finalize(statement)
                guard exists == SQLITE_ROW || exists == SQLITE_DONE else { throw HostCatalogError.invalid("无法检查本地元数据") }
                if exists == SQLITE_ROW { result.retained += 1; continue }
                let revision = hostReceiveCString(row.info.revision_id)
                var title: UnsafeMutablePointer<CChar>?
                guard hostReceiveTitle(history, revision, &title, nil) == READER_REV_OK, let title else {
                    throw HostCatalogError.invalid("接收书籍缺少可验证标题")
                }
                let sort = String(cString: title).precomposedStringWithCanonicalMapping
                reader_revision_bytes_free(title)
                let projected = hostReceiveProject(history, "book", row.key, revision, sort, nil, nil)
                if projected == READER_REV_UNSAFE || projected == READER_REV_MISSING_PARENT { result.conflicts += 1; continue }
                guard projected == READER_REV_OK else { throw HostCatalogError.invalid("接收投影未完成；保留历史供重试") }
                result.projected += 1
            }
            return result
        }
    }

    func receivedBook(key: String) throws -> HostReceivedBook {
        try withHistory { history in
            var wire: UnsafeMutablePointer<CChar>?, size = 0
            var info = reader_revision_info(), selection = reader_revision_selection()
            let result = hostReceiveSelected(history, "book", key, &wire, &size, &info, &selection, nil)
            defer { reader_revision_bytes_free(wire) }
            guard result == READER_REV_OK, selection.kind == READER_SELECTION_SAFE, selection.graph.deleted == 0 else {
                throw HostCatalogError.invalid("此书存在冲突、删除或未完整历史；请同步后处理，未替换本地书籍")
            }
            let parts = key.split(separator: ":", omittingEmptySubsequences: false)
            guard parts.count == 2, ["epub", "pdf", "cbz", "txt", "html", "fb2", "docx", "rtf", "mobi"].contains(String(parts[0])),
                  parts[1].count == 64, parts[1].utf8.allSatisfy({ (48...57).contains($0) || (97...102).contains($0) }),
                  hostReceiveCString(info.book_key) == key, info.source_bytes > 0,
                  info.source_bytes <= (parts[0] == "epub" ? 128 : 32) * 1024 * 1024 else {
                throw HostCatalogError.invalid("接收原件身份或大小超出已安装导入预算")
            }
            var title: UnsafeMutablePointer<CChar>?
            let revision = hostReceiveCString(info.revision_id)
            guard hostReceiveTitle(history, revision, &title, nil) == READER_REV_OK, let title else {
                throw HostCatalogError.invalid("接收书名不可用")
            }
            defer { reader_revision_bytes_free(title) }
            return HostReceivedBook(key: key, revision: revision, title: String(cString: title),
                                    format: String(parts[0]), sha256: String(parts[1]), bytes: info.source_bytes)
        }
    }
}
