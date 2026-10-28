// SPDX-License-Identifier: MIT
import Foundation
import CReaderSQLite

@main
struct CatalogReopenCheck {
    static func execute(_ db: OpaquePointer, _ sql: String) throws {
        guard sqlite3_exec(db, sql, nil, nil, nil) == SQLITE_OK else {
            throw NSError(domain: "CatalogReopenCheck", code: Int(sqlite3_errcode(db)),
                          userInfo: [NSLocalizedDescriptionKey: String(cString: sqlite3_errmsg(db))])
        }
    }

    static func main() throws {
        guard ProcessInfo.processInfo.environment["GITHUB_ACTIONS"] == "true" else {
            throw NSError(domain: "CatalogReopenCheck", code: 1)
        }
        let queue = DispatchQueue(label: "catalog-reopen-check")
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("catalog-reopen-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let migrations = try (1...3).map { index -> String in
            let file = ["001_catalog.sql", "002_originals.sql", "003_original_staging.sql"][index - 1]
            return try String(contentsOfFile: "apps/reader/store/" + file, encoding: .utf8)
        }
        let migration = Data(migrations[0].utf8)
        try queue.sync {
            for version in [2, 3] {
                let path = root.appendingPathComponent("catalog-\(version).db")
                var connection: OpaquePointer?
                guard sqlite3_open(path.path, &connection) == SQLITE_OK, let db = connection else {
                    throw NSError(domain: "CatalogReopenCheck", code: 2)
                }
                do {
                    for sql in migrations.prefix(version) { try execute(db, sql) }
                    try execute(db, "INSERT INTO reader_shelves(shelf_id,name) VALUES('00000000000000000000000000000001','Retained shelf')")
                    sqlite3_close_v2(db)
                } catch {
                    sqlite3_close_v2(db)
                    throw error
                }
                let catalog = try HostCatalog(path: path, migration: migration, ownerQueue: queue)
                guard try catalog.scalar("PRAGMA user_version") == Int64(version),
                      try catalog.text("SELECT name FROM reader_shelves") == "Retained shelf" else {
                    throw NSError(domain: "CatalogReopenCheck", code: 3)
                }
                try catalog.close()
                guard sqlite3_open(path.path, &connection) == SQLITE_OK, let future = connection else {
                    throw NSError(domain: "CatalogReopenCheck", code: 4)
                }
                try execute(future, "PRAGMA user_version=4")
                sqlite3_close_v2(future)
                do {
                    let unexpected = try HostCatalog(path: path, migration: migration, ownerQueue: queue)
                    try unexpected.close()
                    throw NSError(domain: "CatalogReopenCheck", code: 5)
                } catch let error as HostCatalogError {
                    guard case .invalid = error else { throw error }
                }
            }
        }
        print("Product schema 2 and 3 reopen preserved data; future schema rejected")
    }
}
