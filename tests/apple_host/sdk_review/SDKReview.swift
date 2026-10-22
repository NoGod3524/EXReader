// SPDX-License-Identifier: MIT
// Cloud-only installed public-SDK consumer. No SwiftUI, app driver or private API.
import Foundation
import CEXReader
import SQLite3

enum ReviewFailure: Error { case contract(String) }

func require(_ condition: @autoclosure () throws -> Bool, _ message: String) throws {
    if try condition() == false { throw ReviewFailure.contract(message) }
}

func expectCancelled(_ operation: () throws -> Void) throws {
    do { try operation() }
    catch HostError.cancelled { return }
    throw ReviewFailure.contract("operation did not report cancellation")
}

func withBook(_ library: HostLibrary, _ id: Int64,
              _ operation: (inout exr_book) throws -> Void) throws {
    var list: UnsafeMutablePointer<exr_book>?
    var count = 0
    var error = exr_error()
    try hostCheck(exr_library_books(library.handle, nil, &list, &count, &error), error)
    defer { exr_books_free(list, count) }
    guard let list, let index = (0..<count).first(where: { list[$0].id == id }) else {
        throw ReviewFailure.contract("missing book")
    }
    var raw = list[index]
    try operation(&raw)
}

@main struct SDKReviewMain {
    static func main() throws {
        guard CommandLine.arguments.count == 3 else {
            throw ReviewFailure.contract("usage: sdk-review RESOURCES OUTPUT")
        }
        let resources = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
        let output = URL(fileURLWithPath: CommandLine.arguments[2], isDirectory: true)
        try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
        let library = try HostLibrary(path: output.appendingPathComponent("library.sqlite"))
        let font = try HostFont(data: Data(contentsOf: resources.appendingPathComponent("Reader.otf")))
        let textURL = output.appendingPathComponent("bridge.txt")
        let text = "SDK bridge document header unique.\n" + (0..<200).map {
            "Line \($0): this original paragraph tests paging and metadata preservation.\n"
        }.joined()
        try Data(text.utf8).write(to: textURL)
        var results: [[String: Any]] = []
        func test(_ name: String, _ operation: () throws -> Void) {
            defer { HostSDKReview.event = nil; HostSDKReview.poll = nil }
            do {
                try operation()
                results.append(["id": name, "passed": true])
            } catch {
                results.append(["id": name, "passed": false, "error": String(describing: error)])
            }
        }

        let imported = try library.importUnique(file: textURL, title: "Original")
        let stale = try library.books().first(where: { $0.id == imported.id })!
        test("position-preserves-latest-metadata") {
            try withBook(library, imported.id) { raw in
                try "Edited title".withCString { title in
                    try "Edited author".withCString { author in
                        try "review,保存".withCString { tags in
                            raw.title = UnsafeMutablePointer(mutating: title)
                            raw.author = UnsafeMutablePointer(mutating: author)
                            raw.tags = UnsafeMutablePointer(mutating: tags)
                            raw.favorite = 1
                            raw.status = 2
                            var error = exr_error()
                            try hostCheck(exr_library_update(library.handle, &raw, &error), error)
                        }
                    }
                }
            }
            try library.updatePosition(book: stale, position: 7)
            try withBook(library, imported.id) { raw in
                try require(raw.position == 7 && raw.favorite == 1 && raw.status == 2,
                            "position write reset favorite/status")
                try require(hostString(raw.title) == "Edited title" && hostString(raw.author) == "Edited author"
                            && hostString(raw.tags) == "review,保存", "position write reset latest metadata")
            }
        }

        test("import-pre-cancel-preserves-library") {
            let before = try library.books().count
            let box = HostCancelBox(); box.cancel()
            try expectCancelled { _ = try library.importUnique(file: textURL, title: "No", cancel: box) }
            try require(try library.books().count == before, "pre-cancel modified library")
        }
        test("import-oversize-rejected-before-read") {
            let file = output.appendingPathComponent("oversized.txt")
            FileManager.default.createFile(atPath: file.path, contents: nil)
            let handle = try FileHandle(forWritingTo: file)
            try handle.truncate(atOffset: 32 * 1024 * 1024 + 1)
            try handle.close()
            var reads = 0
            HostSDKReview.event = { if $0 == "import-read" { reads += 1 } }
            do { _ = try library.importUnique(file: file, title: "Oversized") }
            catch HostError.invalidInput {
                try require(reads == 0, "oversized input was read before validation")
                return
            }
            throw ReviewFailure.contract("oversized import accepted")
        }
        test("import-cancel-during-bounded-read") {
            let box = HostCancelBox()
            var read = false
            HostSDKReview.event = { phase in
                if phase == "import-read" { read = true; box.cancel() }
            }
            let before = try library.books().count
            try expectCancelled { _ = try library.importUnique(file: textURL, title: "No", cancel: box) }
            try require(read, "bounded read gate was not reached")
            try require(try library.books().count == before, "read cancellation modified library")
        }
        test("import-late-cancel-removes-new-row") {
            let file = output.appendingPathComponent("new-cancelled.txt")
            try Data("A distinct original for late cancellation.\n".utf8).write(to: file)
            let before = try library.books().count
            let box = HostCancelBox()
            var inserted = false
            HostSDKReview.event = { phase in
                if phase == "import-inserted" { inserted = true; box.cancel() }
            }
            try expectCancelled { _ = try library.importUnique(file: file, title: "No", cancel: box) }
            try require(inserted, "actual SDK insert was not reached")
            try require(try library.books().count == before, "new row survived cancellation")
        }
        test("import-late-cancel-preserves-reused-row") {
            let before = try library.books().count
            let box = HostCancelBox()
            HostSDKReview.event = { if $0 == "import-inserted" { box.cancel() } }
            try expectCancelled { _ = try library.importUnique(file: textURL, title: "No", cancel: box) }
            try require(try library.books().count == before, "duplicate cancellation deleted existing row")
            try withBook(library, imported.id) { raw in
                try require(hostString(raw.title) == "Edited title" && raw.favorite == 1,
                            "duplicate import changed existing metadata")
            }
        }
        test("import-rollback-failure-reports-retained-row") {
            let file = output.appendingPathComponent("rollback-failure.txt")
            try Data("A separate original for real SQLite writer-lock rollback.\n".utf8).write(to: file)
            var connection: OpaquePointer?
            guard sqlite3_open(library.path.path, &connection) == SQLITE_OK, let connection else {
                throw ReviewFailure.contract("cannot open independent writer")
            }
            defer { sqlite3_exec(connection, "ROLLBACK", nil, nil, nil); sqlite3_close(connection) }
            let box = HostCancelBox()
            var locked = false
            HostSDKReview.event = { phase in
                if phase == "import-inserted" {
                    try require(sqlite3_exec(connection, "BEGIN IMMEDIATE", nil, nil, nil) == SQLITE_OK,
                                "independent writer lock failed")
                    locked = true
                    box.cancel()
                }
            }
            let before = try library.books().count
            do { _ = try library.importUnique(file: file, title: "Retained", cancel: box) }
            catch HostError.invalidResult(let message) {
                try require(locked && message.contains("回滚失败") && message.contains("保留记录"),
                            "rollback failure lost retained-row detail")
                sqlite3_exec(connection, "ROLLBACK", nil, nil, nil)
                try require(try library.books().count == before + 1, "failure did not preserve the actual retained row")
                let rows = try library.books().filter { $0.title == "Retained" }
                for row in rows { try library.delete(bookID: row.id) }
                return
            }
            throw ReviewFailure.contract("rollback failure reported cancellation or success")
        }

        let document = try library.document(bookID: imported.id)
        let creation = HostCancelBox()
        let pager = try HostPager(document: document, font: font, width: 720, height: 1040,
                                  fontSize: 28, box: creation)
        _ = try pager.pageRange(0)
        test("pager-rebinds-after-creator-cancel") {
            creation.cancel()
            let range = try pager.pageRange(0, cancel: HostCancelBox())
            try require(!range.isEmpty, "fresh task retained cancelled creator token")
        }
        test("pager-current-token-controls-cache-hit") {
            let box = HostCancelBox(); box.cancel()
            try expectCancelled { _ = try pager.pageRange(0, cancel: box) }
            try require(!(try pager.pageRange(0, cancel: HostCancelBox())).isEmpty,
                        "cancelled cache access poisoned the next task")
        }
        test("pager-render-polls-current-token") {
            let box = HostCancelBox()
            var polls = 0
            HostSDKReview.poll = { active in
                if active === box { polls += 1; if polls == 2 { box.cancel() } }
            }
            try expectCancelled { _ = try pager.render(0, cancel: box) }
            try require(polls >= 2, "render did not poll supplied token inside public SDK")
        }
        test("pager-seek-propagates-real-limit") {
            let limited = try HostPager(document: document, font: font, width: 720, height: 1040,
                                        fontSize: 28, box: HostCancelBox())
            try limited.reviewCacheBudget(1)
            do { _ = try limited.pageIndex(for: 5, cancel: HostCancelBox()) }
            catch HostError.engine(let code, _) where code == Int(EXR_LIMIT.rawValue) { return }
            throw ReviewFailure.contract("seek converted actual SDK cache limit into missing page")
        }
        test("pager-seek-verifies-target-range-and-eof") {
            let target = document.text.count - 20
            let page = try pager.pageIndex(for: target, cancel: HostCancelBox())
            try require(try pager.pageRange(page).contains(target), "seek returned a page without target")
            let endPage = try pager.pageIndex(for: document.text.count)
            try require(try pager.pageRange(endPage).upperBound == document.text.count,
                        "end point did not restore final page")
            let missing = try pager.existingRange(endPage + 1)
            try require(missing == nil, "actual end of document was not classified")
        }
        test("snapshot-pager-anchor-uses-document-api") {
            let anchor = try pager.makeAnchor(start: 0, end: 3)
            let match = try pager.resolve(anchor)
            try require(match.isFound && match.range == (0..<3), "snapshot anchor called chapter-only API")
        }

        let fixedID = try library.importUnique(file: resources.appendingPathComponent("Sample.pdf"), title: "PDF").id
        let fixed = try library.fixed(bookID: fixedID, font: font)
        test("fixed-render-polls-current-token") {
            let box = HostCancelBox()
            var polls = 0
            HostSDKReview.poll = { active in
                if active === box { polls += 1; if polls == 2 { box.cancel() } }
            }
            try expectCancelled { _ = try fixed.render(page: 0, maximumDimension: 800, cancel: box) }
            try require(polls >= 2, "fixed render ignored current control")
        }
        test("fixed-text-polls-current-token") {
            let box = HostCancelBox()
            var polls = 0
            HostSDKReview.poll = { active in
                if active === box { polls += 1; if polls == 2 { box.cancel() } }
            }
            try expectCancelled { _ = try fixed.text(page: 0, cancel: box) }
            try require(polls >= 2, "fixed text ignored current control")
        }
        test("fixed-reuses-after-cancel") {
            let bitmap = try fixed.render(page: 0, maximumDimension: 800, cancel: HostCancelBox())
            let text = try fixed.text(page: 0, cancel: HostCancelBox())
            try require(!bitmap.pixels.isEmpty && !text.text.isEmpty, "fixed handle was poisoned by cancellation")
        }
        test("fixed-comment-update-keeps-reflow-note-separate") {
            let reflowID = try library.addNote(bookID: imported.id, start: 0, end: 3, text: "Keep reflow")
            let fixedNoteID = try library.addFixedNote(bookID: fixedID, page: 0, start: 0, end: 0, text: "Before")
            try require(reflowID == fixedNoteID, "fixture does not exercise colliding table IDs")
            try library.updateFixedNoteText(bookID: fixedID, noteID: fixedNoteID, text: "After 保存")
            let reflow = try library.reflowNotes(bookID: imported.id, document: document)
            let fixedRows = try library.fixedNotes(bookID: fixedID, fixed: fixed)
            try require(reflow.first(where: { $0.id == reflowID })?.comment == "Keep reflow",
                        "fixed update modified colliding reflow note")
            try require(fixedRows.first(where: { $0.id == fixedNoteID })?.comment == "After 保存",
                        "fixed comment update did not persist")
        }
        test("fixed-notes-propagates-cancellation") {
            let box = HostCancelBox(); box.cancel()
            try expectCancelled { _ = try library.fixedNotes(bookID: fixedID, fixed: fixed, cancel: box) }
        }
        test("fixed-notes-text-failure-is-propagated") {
            // The existing native fixed-library fixture has page 0 readable and
            // page 1 returning EXR_FORMAT from the real text provider.
            let fixture = output.appendingPathComponent("TextFailure.pdf")
            let id = try library.importUnique(file: fixture, title: "Text failure").id
            _ = try library.addFixedNote(bookID: id, page: 0, start: 0, end: 0, text: "Preserve error")
            let reader = try library.fixed(bookID: id, font: font)
            var connection: OpaquePointer?
            guard sqlite3_open(library.path.path, &connection) == SQLITE_OK, let connection else {
                throw ReviewFailure.contract("cannot open independent annotation writer")
            }
            defer {
                sqlite3_exec(connection, "UPDATE fixed_notes SET page=0 WHERE book_id=\(id)", nil, nil, nil)
                sqlite3_close(connection)
            }
            try require(sqlite3_exec(connection, "UPDATE fixed_notes SET page=1 WHERE book_id=\(id)", nil, nil, nil)
                        == SQLITE_OK, "cannot change real stored annotation page")
            do { _ = try library.fixedNotes(bookID: id, fixed: reader) }
            catch HostError.engine(let code, _) where code == Int(EXR_FORMAT.rawValue) { return }
            throw ReviewFailure.contract("text load failure was converted into an unresolved note")
        }
        test("publication-cancel-ordering") {
            let cancelled = HostCancelBox(); cancelled.cancel()
            var writes = 0
            try expectCancelled { try cancelled.commit { writes += 1 } }
            try require(writes == 0, "cancelled operation entered publication body")
            let completed = HostCancelBox()
            try completed.commit { writes += 1 }
            completed.cancel()
            try completed.check()
            try require(writes == 1 && !completed.isCancelled, "late cancel relabeled committed state")
            let failed = HostCancelBox()
            do { try failed.commit { throw ReviewFailure.contract("expected write failure") } }
            catch ReviewFailure.contract { }
            failed.cancel()
            try require(failed.isCancelled, "failed commit became uncancellable")
        }
        test("embedded-nul-note-is-rejected") {
            do { _ = try library.addNote(bookID: imported.id, start: 0, end: 3, text: "before\0after") }
            catch HostError.invalidInput { return }
            throw ReviewFailure.contract("NUL comment was silently truncated")
        }

        let passed = results.allSatisfy { ($0["passed"] as? Bool) == true }
        let report: [String: Any] = ["schema": 1, "suite": "apple-host-sdk-review", "passed": passed,
                                    "checks": results.count, "sdk": HOST_SDK_VERSION, "abi": HOST_ABI_VERSION,
                                    "backend": "installed public SDK; real SQLite and render/pager APIs",
                                    "review_callbacks": "observation/cancellation gates only; distributed host excludes them",
                                    "cases": results]
        let bytes = try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys])
        try bytes.write(to: output.appendingPathComponent("sdk-review.json"))
        print("Apple SDK bridge review: \(results.filter { ($0["passed"] as? Bool) == true }.count)/\(results.count)")
        if !passed { exit(1) }
    }
}
