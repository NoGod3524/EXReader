// SPDX-License-Identifier: MIT
import Foundation
import SQLite3

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
    private var handle: OpaquePointer?

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

    private func connection() throws -> OpaquePointer {
        dispatchPrecondition(condition: .onQueue(ownerQueue))
        guard let handle else { throw HostCatalogError.invalid("产品书库已关闭") }
        return handle
    }

    private func prepare(_ sql: String) throws -> (OpaquePointer, OpaquePointer) {
        let database = try connection()
        guard !sql.utf8.contains(0) else { throw HostCatalogError.invalid("SQL 包含空字符") }
        var statement: OpaquePointer?
        let status = sqlite3_prepare_v2(database, sql, -1, &statement, nil)
        guard status == SQLITE_OK, let prepared = statement else {
            if let statement { sqlite3_finalize(statement) }
            throw HostCatalogError.sqlite(status, String(cString: sqlite3_errmsg(database)))
        }
        return (database, prepared)
    }

    private func check(_ status: Int32, _ database: OpaquePointer, expected: Int32 = SQLITE_OK) throws {
        guard status == expected else {
            throw HostCatalogError.sqlite(status, String(cString: sqlite3_errmsg(database)))
        }
    }
}
