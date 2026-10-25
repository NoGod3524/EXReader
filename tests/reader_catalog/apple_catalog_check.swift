// SPDX-License-Identifier: MIT
import Foundation
import CryptoKit
import CReaderSQLite

private struct CatalogCheckFailure: Error {
    let message: String
}

@main
struct AppleCatalogCheck {
    static func require(_ value: @autoclosure () throws -> Bool, _ message: String) throws {
        guard try value() else { throw CatalogCheckFailure(message: message) }
    }

    static func rejected(_ operation: () throws -> Void) throws {
        do { try operation() } catch { return }
        throw CatalogCheckFailure(message: "Invalid operation was accepted")
    }

    static func raw(_ path: URL, _ operation: (OpaquePointer) throws -> Void) throws {
        var database: OpaquePointer?
        let status = sqlite3_open_v2(path.path, &database,
                                    SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE | SQLITE_OPEN_FULLMUTEX, nil)
        guard status == SQLITE_OK, let db = database else {
            if let database { sqlite3_close_v2(database) }
            throw CatalogCheckFailure(message: "Raw SQLite setup failed")
        }
        defer { sqlite3_close_v2(db) }
        try operation(db)
    }

    static func rawExec(_ database: OpaquePointer, _ sql: String) throws {
        guard sqlite3_exec(database, sql, nil, nil, nil) == SQLITE_OK else {
            throw CatalogCheckFailure(message: "Raw SQLite statement failed")
        }
    }

    static func rawText(_ database: OpaquePointer, _ sql: String) throws -> String {
        var statement: OpaquePointer?
        guard sqlite3_prepare_v2(database, sql, -1, &statement, nil) == SQLITE_OK, let prepared = statement else {
            if let statement { sqlite3_finalize(statement) }
            throw CatalogCheckFailure(message: "Raw SQLite query failed")
        }
        defer { sqlite3_finalize(prepared) }
        guard sqlite3_step(prepared) == SQLITE_ROW, let text = sqlite3_column_text(prepared, 0) else {
            throw CatalogCheckFailure(message: "Raw SQLite query returned no value")
        }
        return String(cString: text)
    }

    static func id(_ number: Int) -> String { String(format: "%032x", number) }

    static func main() throws {
        let env = ProcessInfo.processInfo.environment
        guard env["GITHUB_ACTIONS"] == "true", CommandLine.arguments.count == 3 else {
            throw CatalogCheckFailure(message: "Run in GitHub Actions with original migration and output JSON")
        }
        let migrationURL = URL(fileURLWithPath: CommandLine.arguments[1])
        let output = URL(fileURLWithPath: CommandLine.arguments[2])
        let source = try Data(contentsOf: migrationURL)
        let sourceHash = SHA256.hash(data: source).map { String(format: "%02x", $0) }.joined()
        let temporary = FileManager.default.temporaryDirectory.appendingPathComponent("apple-catalog-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: temporary, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporary) }
        let queue = DispatchQueue(label: "org.exreader.host.catalog-check")
        var checks: [[String: Any]] = []
        queue.sync {
            func check(_ name: String, _ operation: () throws -> Void) {
                let started = DispatchTime.now().uptimeNanoseconds
                var result: [String: Any] = ["id": name, "passed": false]
                do { try operation(); result["passed"] = true }
                catch { result["error"] = String(describing: error) }
                result["elapsed_ms"] = Double(DispatchTime.now().uptimeNanoseconds - started) / 1_000_000
                checks.append(result)
                print("catalog-check \(name) passed=\(result["passed"] as? Bool == true)")
            }
            func file(_ name: String) -> URL { temporary.appendingPathComponent(name + ".db") }
            func open(_ name: String) throws -> HostCatalog {
                try HostCatalog(path: file(name), migrationURL: migrationURL, ownerQueue: queue)
            }

            check("createsAndReopensCatalog") {
                let catalog = try open("reopen")
                try require(catalog.scalar("PRAGMA application_id") == HostCatalog.applicationID, "Wrong product identity")
                try require(catalog.scalar("PRAGMA user_version") == 1, "Wrong product version")
                try require(catalog.scalar("PRAGMA foreign_keys") == 1, "Foreign keys disabled")
                try require(catalog.scalar("SELECT count(*) FROM sqlite_master WHERE type='table'") == 10, "Wrong product table set")
                try catalog.execute("INSERT INTO reader_shelves(shelf_id,name) VALUES('\(id(1))','Original shelf')")
                try catalog.close()
                let reopened = try open("reopen")
                defer { try? reopened.close() }
                try require(reopened.text("SELECT name FROM reader_shelves") == "Original shelf", "Reopen lost data or reran migration")
                try require(reopened.scalar("PRAGMA foreign_keys") == 1, "Reopen disabled foreign keys")
                try require(reopened.text("PRAGMA integrity_check") == "ok", "Catalog integrity failed")
            }

            check("rejectsForeignDatabasesWithoutChangingData") {
                let identities: [(Int64, Int64)] = [(1163416131, 7), (999, 1), (0, 0), (0, 0), (HostCatalog.applicationID, 2), (0, 2)]
                for (index, identity) in identities.enumerated() {
                    let path = file("foreign-\(index)")
                    let table = index == 3 ? "sqliteXbooks" : "retained"
                    var before: [String] = []
                    try raw(path) { db in
                        try rawExec(db, "CREATE TABLE \(table)(value TEXT NOT NULL);INSERT INTO \(table) VALUES('kept original');PRAGMA application_id=\(identity.0);PRAGMA user_version=\(identity.1);")
                        before = try [rawText(db, "PRAGMA application_id"), rawText(db, "PRAGMA user_version"),
                                      rawText(db, "SELECT name||':'||sql FROM sqlite_master WHERE type='table'"),
                                      rawText(db, "SELECT value FROM \(table)")]
                    }
                    try rejected {
                        let refused = try HostCatalog(path: path, migration: source, ownerQueue: queue)
                        try refused.close()
                    }
                    try raw(path) { db in
                        let after = try [rawText(db, "PRAGMA application_id"), rawText(db, "PRAGMA user_version"),
                                         rawText(db, "SELECT name||':'||sql FROM sqlite_master WHERE type='table'"),
                                         rawText(db, "SELECT value FROM \(table)")]
                        try require(after == before, "Rejected database changed its identity/schema/data")
                        try require(rawText(db, "SELECT count(*) FROM sqlite_master WHERE type='table'") == "1", "Foreign database gained tables")
                        try require(rawText(db, "PRAGMA integrity_check") == "ok", "Foreign database was damaged")
                    }
                }
            }

            check("keepsCompleteShelfTriggers") {
                let catalog = try open("shelves")
                defer { try? catalog.close() }
                for number in 1...8 {
                    let parent = number == 1 ? "NULL" : "'\(id(number - 1))'"
                    try catalog.execute("INSERT INTO reader_shelves(shelf_id,parent_id,name) VALUES('\(id(number))',\(parent),'Shelf \(number)')")
                }
                try rejected { try catalog.execute("INSERT INTO reader_shelves(shelf_id,parent_id,name) VALUES('\(id(9))','\(id(8))','Too deep')") }
                try rejected { try catalog.execute("UPDATE reader_shelves SET parent_id='\(id(8))' WHERE shelf_id='\(id(1))'") }
                try rejected { try catalog.execute("UPDATE reader_shelves SET parent_id=shelf_id WHERE shelf_id='\(id(1))'") }
                try catalog.execute("INSERT INTO reader_shelves(shelf_id,name) VALUES('\(id(20))','Branch'); INSERT INTO reader_shelves(shelf_id,parent_id,name) VALUES('\(id(21))','\(id(20))','Child')")
                try rejected { try catalog.execute("UPDATE reader_shelves SET parent_id='\(id(7))' WHERE shelf_id='\(id(20))'") }
                try catalog.execute("UPDATE reader_shelves SET parent_id='\(id(6))' WHERE shelf_id='\(id(20))'")
                try require(catalog.text("SELECT parent_id FROM reader_shelves WHERE shelf_id='\(id(20))'") == id(6), "Legal subtree move failed")
                try rejected { try catalog.execute("UPDATE reader_shelves SET parent_id='\(id(999))' WHERE shelf_id='\(id(21))'") }
                try require(catalog.scalar("SELECT count(*) FROM reader_shelves") == 10, "Rejected shelf mutations changed rows")
            }

            check("retainsImmutableRevisionsAndTombstones") {
                let catalog = try open("revisions")
                defer { try? catalog.close() }
                let digest = String(repeating: "0", count: 64)
                let insert = "INSERT INTO reader_revisions VALUES('\(id(1))','book','epub:\(digest)','delete','{}','\(digest)')"
                try catalog.execute(insert)
                try catalog.execute("INSERT INTO reader_outbox(revision_id) VALUES('\(id(1))')")
                try rejected { try catalog.execute(insert) }
                try rejected { try catalog.execute(insert.replacingOccurrences(of: "INSERT INTO", with: "INSERT OR REPLACE INTO")) }
                try rejected { try catalog.execute("UPDATE reader_revisions SET body_json='{\"changed\":true}'") }
                try rejected { try catalog.execute("DELETE FROM reader_revisions") }
                try catalog.execute("DELETE FROM reader_outbox")
                try require(catalog.scalar("SELECT count(*) FROM reader_outbox") == 0, "Outbox acknowledgement failed")
                try require(catalog.text("SELECT revision_id FROM reader_tombstones") == id(1), "Delete history was lost")
                try catalog.close()
                let reopened = try open("revisions")
                defer { try? reopened.close() }
                try require(reopened.text("SELECT body_json FROM reader_tombstones") == "{}", "Reopen lost immutable tombstone bytes")
            }

            check("rollsBackInterruptedMigrationAndAllowsRetry") {
                guard var sql = String(data: source, encoding: .utf8), let commit = sql.range(of: "COMMIT;", options: .backwards) else {
                    throw CatalogCheckFailure(message: "Original migration has no commit")
                }
                sql.insert(contentsOf: "CREATE TABLE reader_failure_probe(value INTEGER); INSERT INTO missing_catalog_table VALUES(1);\n", at: commit.lowerBound)
                let path = file("interrupted")
                try rejected {
                    let refused = try HostCatalog(path: path, migration: Data(sql.utf8), ownerQueue: queue)
                    try refused.close()
                }
                try raw(path) { db in
                    try require(rawText(db, "PRAGMA application_id") == "0", "Failed migration committed identity")
                    try require(rawText(db, "PRAGMA user_version") == "0", "Failed migration committed version")
                    try require(rawText(db, "SELECT count(*) FROM sqlite_master WHERE name NOT GLOB 'sqlite_*'") == "0", "Failed migration leaked schema")
                    try require(rawText(db, "PRAGMA integrity_check") == "ok", "Rollback damaged database")
                }
                let retried = try open("interrupted")
                defer { try? retried.close() }
                try require(retried.scalar("SELECT count(*) FROM sqlite_master WHERE type='table'") == 10, "Retry did not apply original migration")
            }

            check("rejectsInvalidMigrationInput") {
                let invalid = [Data(), Data(repeating: 32, count: 128 * 1024 + 1),
                               Data([0xc3, 0x28]), Data([0xef, 0xbb, 0xbf]) + source,
                               Data("SELECT '\0';".utf8)]
                for (index, bytes) in invalid.enumerated() {
                    let path = file("invalid-\(index)")
                    try rejected {
                        let refused = try HostCatalog(path: path, migration: bytes, ownerQueue: queue)
                        try refused.close()
                    }
                    try require(!FileManager.default.fileExists(atPath: path.path), "Invalid migration opened a database")
                }
                let missing = file("missing-resource")
                try rejected {
                    let refused = try HostCatalog(path: missing, migrationURL: temporary.appendingPathComponent("absent.sql"), ownerQueue: queue)
                    try refused.close()
                }
                try require(!FileManager.default.fileExists(atPath: missing.path), "Missing resource opened database")
            }

            check("usesBoundedBusyTimeout") {
                let catalog = try open("busy")
                defer { try? catalog.close() }
                try require(catalog.scalar("PRAGMA busy_timeout") == 5000, "Unbounded or changed busy timeout")
                try require(catalog.scalar("PRAGMA trusted_schema") == 0, "Trusted schema unexpectedly enabled")
                try raw(file("busy")) { locker in
                    try rawExec(locker, "BEGIN IMMEDIATE")
                    defer { try? rawExec(locker, "ROLLBACK") }
                    do {
                        try catalog.execute("INSERT INTO reader_tags(tag_id,name) VALUES('\(id(1))','Busy')")
                        throw CatalogCheckFailure(message: "Write bypassed an existing SQLite writer")
                    } catch HostCatalogError.sqlite(let code, _) {
                        try require(code & 255 == SQLITE_BUSY, "Contention returned an unexpected database error")
                    }
                }
                try require(catalog.scalar("SELECT count(*) FROM reader_tags") == 0, "Rejected busy write changed data")
            }

            check("closesExplicitlyAndRejectsReuse") {
                let catalog = try open("close")
                try catalog.close()
                try catalog.close()
                try rejected { _ = try catalog.scalar("PRAGMA user_version") }
                try rejected { try catalog.execute("CREATE TABLE after_close(value TEXT)") }
                let reopened = try open("close")
                defer { try? reopened.close() }
                try require(reopened.scalar("PRAGMA user_version") == 1, "Explicit close lost committed schema")
            }
        }
        let accepted = checks.count == 8 && checks.allSatisfy { $0["passed"] as? Bool == true }
        let report: [String: Any] = ["schema": 1, "accepted": accepted,
            "scope": "Apple product catalog adapter only", "source_sha": env["GITHUB_SHA"] ?? "",
            "run_id": env["GITHUB_RUN_ID"] ?? "", "attempt": env["GITHUB_RUN_ATTEMPT"] ?? "",
            "schema_sha256": sourceHash, "schema_bytes": source.count, "checks": checks,
            "passed": checks.filter { $0["passed"] as? Bool == true }.count,
            "failed": checks.filter { $0["passed"] as? Bool != true }.count, "skipped": 0,
            "physical_device_execution": false, "problems": accepted ? [] : ["Catalog checks failed"]]
        try FileManager.default.createDirectory(at: output.deletingLastPathComponent(), withIntermediateDirectories: true)
        try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys]).write(to: output)
        print("Apple catalog: \(checks.count) checks, accepted=\(accepted)")
        if !accepted { exit(1) }
    }
}
