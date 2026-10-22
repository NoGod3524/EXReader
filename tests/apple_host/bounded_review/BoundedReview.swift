// SPDX-License-Identifier: MIT
import Foundation
import CoreGraphics
import CEXReader
import SQLite3

@main struct BoundedReview {
    static func main() throws {
        guard ProcessInfo.processInfo.environment["GITHUB_ACTIONS"] == "true" else { throw HostError.invalidInput("cloud only") }
        let resources = URL(fileURLWithPath: CommandLine.arguments[1])
        let output = URL(fileURLWithPath: CommandLine.arguments[2])
        try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
        let library = try HostLibrary(path: output.appendingPathComponent("bounded.sqlite"))
        let font = try HostFont(data: Data(contentsOf: resources.appendingPathComponent("Reader.otf")))
        let source = resources.appendingPathComponent("Bounded.epub")
        var results: [[String: Any]] = [], measurements: [String: Any] = [:]
        func check(_ name: String, _ operation: () throws -> Bool) {
            let started = Date()
            print("bounded-case-start \(name)"); fflush(stdout)
            do { results.append(["name": name, "passed": try operation()]) }
            catch { results.append(["name": name, "passed": false, "error": String(describing: error)]) }
            results[results.count - 1]["elapsed_ms"] = Date().timeIntervalSince(started) * 1000
            print("bounded-case-end \(name) passed=\(results.last?["passed"] as? Bool == true)"); fflush(stdout)
        }
        let id = try library.importUnique(file: source, title: "Bounded.epub").id
        let book = try library.books().first(where: { $0.id == id })!
        let session = HostSession(library: library, font: font, slowDelay: 0, viewport: CGSize(width: 480, height: 640), fontSize: 28)
        check("source_import_marks_unknown_extent") { try library.isBoundedEPUB(book: book) && book.position == 0 }
        check("duplicate_preserves_storage_mode") {
            let duplicate = try library.importUnique(file: source, title: "Duplicate")
            let bounded = try library.isBoundedEPUB(book: book)
            return duplicate.id == id && !duplicate.created && bounded
        }
        check("source_import_pre_cancel_is_atomic") {
            let box = HostCancelBox(); box.cancel()
            let before = try library.books().count
            do { _ = try library.importUnique(file: source, title: "Cancelled", cancel: box); return false }
            catch HostError.cancelled { return try library.books().count == before }
        }
        check("source_import_mid_cancel_and_late_rollback") {
            let before = try library.books().count
            let cancel = HostCancelBox()
            var observed = false
            HostSDKReview.event = { if $0 == "import-read" { observed = true; cancel.cancel() } }
            defer { HostSDKReview.event = nil }
            do { _ = try library.importUnique(file: resources.appendingPathComponent("Sample.epub"), title: "Cancelled", cancel: cancel); return false }
            catch HostError.cancelled { }
            guard observed, try library.books().count == before else { return false }
            let late = HostCancelBox()
            HostSDKReview.event = { if $0 == "import-inserted" { late.cancel() } }
            do { _ = try library.importUnique(file: resources.appendingPathComponent("Sample.epub"), title: "Late cancelled", cancel: late); return false }
            catch HostError.cancelled { return try library.books().count == before }
        }
        check("publication_rebinds_stable_source_control") {
            let creator = HostCancelBox()
            let publication = try HostPublication(library: library, bookID: id, cancel: creator)
            let pager = try HostPager(publication: publication, part: 0, font: font, width: 480, height: 640, fontSize: 28, box: creator)
            creator.cancel()
            let active = HostCancelBox()
            let range = try pager.pageRange(0, cancel: active)
            let text = try pager.text(range, cancel: active)
            let bitmap = try pager.render(0, cancel: active)
            return !text.isEmpty && !bitmap.pixels.isEmpty
        }
        check("repeated_spine_path_keeps_part_identity") {
            let p = try HostPublication(library: library, bookID: id, cancel: HostCancelBox())
            return p.parts.count == 3 && p.parts[0].path == p.parts[2].path && p.parts[0].index != p.parts[2].index
        }
        check("cross_chapter_next_and_previous") {
            let first = try session.open(bookID: id, cancel: HostCancelBox())
            let second = try session.turn(1, cancel: HostCancelBox())
            let third = try session.turn(1, cancel: HostCancelBox())
            let back = try session.turn(-1, cancel: HostCancelBox())
            return first.part == 0 && second.part == 1 && third.part == 2 && back.part == 1 &&
                first.pageRange.lowerBound == second.pageRange.lowerBound && first.pageText != second.pageText
        }
        check("same_part_notes_crud_and_cross_part_jump") {
            let frame = try session.renderSnapshot()
            try session.addNote(start: frame.pageRange.lowerBound, end: frame.pageRange.upperBound, comment: "bounded note", cancel: HostCancelBox())
            guard let row = try session.notes().first else { return false }
            try session.updateNote(noteID: row.id, text: "edited bounded note", cancel: HostCancelBox())
            _ = try session.turn(1, cancel: HostCancelBox())
            guard let pending = try session.notes().first, pending.state == "待定位" else { return false }
            let jumped = try session.jump(to: pending, cancel: HostCancelBox())
            guard jumped.part == 1, try session.notes().first?.comment == "edited bounded note" else { return false }
            try session.deleteNote(row, cancel: HostCancelBox())
            return try session.notes().isEmpty
        }
        check("font_resize_reopen_restores_part_and_point") {
            _ = try session.changeFont(delta: 2, cancel: HostCancelBox())
            _ = try session.resize(width: 540, height: 720, cancel: HostCancelBox())
            try session.persistCurrent()
            let before = try library.epubProgress(bookID: id)
            session.close()
            let reopened = try session.open(bookID: id, cancel: HostCancelBox())
            let after = try library.epubProgress(bookID: id)
            return reopened.part == 1 && before?.part == after?.part && before?.path == after?.path &&
                before?.raw.selector.start == after?.raw.selector.start
        }
        check("ambiguous_restore_preserves_selector") {
            session.close()
            var location = exr_epub_location(), error = exr_error()
            location.part = 0; location.selector.start = 1; location.selector.end = 1
            try "OPS/c0.xhtml".withCString { path in try "".withCString { empty in try "chapter".withCString { suffix in
                location.path = UnsafeMutablePointer(mutating: path)
                location.selector.exact = UnsafeMutablePointer(mutating: empty)
                location.selector.prefix = UnsafeMutablePointer(mutating: empty)
                location.selector.suffix = UnsafeMutablePointer(mutating: suffix)
                try hostCheck(exr_library_epub_progress(library.handle, id, &location, &error), error)
            } } }
            let restored = try session.open(bookID: id, cancel: HostCancelBox())
            try session.persistCurrent()
            let saved = try library.epubProgress(bookID: id)
            return restored.progress.contains("未精确匹配") && saved?.raw.selector.start == 1 && hostString(saved?.raw.selector.suffix) == "chapter"
        }
        check("invalid_part_path_rejected") {
            let publication = try HostPublication(library: library, bookID: id, cancel: HostCancelBox())
            do { _ = try publication.route(1, path: "OPS/c0.xhtml"); return false }
            catch HostError.invalidInput { return true }
        }
        check("original_repeated_fixture_refuses_ambiguous_note") {
            func phase(_ name: String) { print("bounded-repeated-phase \(name)"); fflush(stdout) }
            let window = Int(ProcessInfo.processInfo.environment["H9_DIAGNOSTIC_REPEATED_WINDOW"] ?? "16384") ?? 16384
            measurements["repeated_window_bytes"] = window
            print("bounded-repeated-window \(window)"); fflush(stdout)
            let repeatedID = try library.importUnique(file: resources.appendingPathComponent("Repeated.epub"), title: "Repeated.epub").id
            phase("imported")
            let publication = try HostPublication(library: library, bookID: repeatedID, cancel: HostCancelBox())
            phase("publication-opened")
            let cancel = HostCancelBox()
            let pager = try HostPager(publication: publication, part: 0, font: font, width: 480, height: 640, fontSize: 28, box: cancel, windowBytes: window)
            phase("chapter-pager-created")
            // An interior quote with repeated context must remain ambiguous.
            let anchor = try pager.makeAnchor(start: 1024, end: 1088, cancel: cancel)
            phase("anchor-captured")
            let match = try pager.resolve(anchor, cancel: cancel)
            phase("anchor-resolved")
            let stats = pager.statistics
            measurements["repeated_windows_loaded"] = stats.windows_loaded
            measurements["repeated_windows_evicted"] = stats.windows_evicted
            return match.state == EXR_ANCHOR_AMBIGUOUS && match.range == nil
        }
        check("legacy_memory_import_keeps_global_progress") {
            let data = try Data(contentsOf: resources.appendingPathComponent("Unicode.epub"))
            var legacyID: Int64 = 0, error = exr_error()
            try data.withUnsafeBytes { bytes in try "Legacy".withCString {
                try hostCheck(exr_library_import(library.handle, EXR_EPUB, bytes.baseAddress, bytes.count, $0, &legacyID, &error), error)
            } }
            let legacy = try library.books().first(where: { $0.id == legacyID })!
            let document = try library.document(bookID: legacyID)
            let anchor = try document.makeAnchor(start: 0, end: 0)
            try library.setProgress(bookID: legacyID, anchor: anchor)
            let bounded = try library.isBoundedEPUB(book: legacy)
            let progress = try library.progress(bookID: legacyID)
            return !bounded && progress.anchor.start == 0
        }
        check("schema6_upgrade_preserves_legacy_original_progress_notes") {
            let path = output.appendingPathComponent("schema6.sqlite")
            let original = try Data(contentsOf: resources.appendingPathComponent("Unicode.epub"))
            var old: HostLibrary? = try HostLibrary(path: path)
            var legacyID: Int64 = 0, error = exr_error()
            try original.withUnsafeBytes { bytes in try "Legacy schema6".withCString {
                try hostCheck(exr_library_import(old!.handle, EXR_EPUB, bytes.baseAddress, bytes.count, $0, &legacyID, &error), error)
            } }
            do {
                let document = try old!.document(bookID: legacyID)
                let anchor = try document.makeAnchor(start: 0, end: 0)
                try old!.setProgress(bookID: legacyID, anchor: anchor)
                _ = try old!.addNote(bookID: legacyID, start: 0, end: 7, text: "schema6 original note")
            }
            old = nil
            var connection: OpaquePointer?
            guard sqlite3_open(path.path, &connection) == SQLITE_OK, let connection else { return false }
            let status = sqlite3_exec(connection, "DROP TABLE epub_notes; DROP TABLE epub_progress; DROP TABLE epub_bounded_books; PRAGMA user_version=6;", nil, nil, nil)
            sqlite3_close(connection)
            guard status == SQLITE_OK else { return false }
            let upgraded = try HostLibrary(path: path)
            let book = try upgraded.books().first!
            let document = try upgraded.document(bookID: legacyID)
            let notes = try upgraded.reflowNotes(bookID: legacyID, document: document)
            var blob: UnsafeMutableRawPointer?, size = 0
            try hostCheck(exr_library_blob(upgraded.handle, legacyID, 0, &blob, &size, &error), error)
            defer { exr_free(blob) }
            guard let blob else { return false }
            let bounded = try upgraded.isBoundedEPUB(book: book)
            let progress = try upgraded.progress(bookID: legacyID)
            return book.title == "Legacy schema6" && !bounded && progress.anchor.start == 0 && notes.count == 1 &&
                notes[0].comment == "schema6 original note" && notes[0].quote == "Unicode" && Data(bytes: blob, count: size) == original
        }
        check("long_chapter_tail_text_without_snapshot") {
            func phase(_ name: String) { print("bounded-long-phase \(name)"); fflush(stdout) }
            let start = Date()
            phase("before-import")
            let longID = try library.importUnique(file: resources.appendingPathComponent("BoundedLong.epub"), title: "BoundedLong.epub").id
            phase("imported")
            let imported = Date()
            let publication = try HostPublication(library: library, bookID: longID, cancel: HostCancelBox())
            phase("publication-opened")
            let cancel = HostCancelBox()
            let pager = try HostPager(publication: publication, part: 0, font: font, width: 480, height: 640, fontSize: 28, box: cancel)
            phase("chapter-pager-created")
            let range = try pager.pageRange(0, cancel: cancel)
            phase("first-layout")
            let bitmap = try pager.render(0, cancel: cancel)
            phase("first-paint")
            let firstPaint = Date()
            let extent = pager.extent
            let tail = try pager.text(max(0, extent - 512)..<extent, cancel: cancel)
            phase("tail-text")
            let anchor = try pager.makeAnchor(start: extent, end: extent, cancel: cancel)
            phase("tail-point-captured")
            try library.setEPUBProgress(bookID: longID, part: 0, path: publication.parts[0].path, anchor: anchor)
            phase("tail-point-stored")
            let saved = try library.epubProgress(bookID: longID)
            let match = try pager.resolveLocation(saved!, cancel: cancel)
            phase("tail-point-resolved")
            let stats = pager.statistics
            measurements.merge(["import_ms": imported.timeIntervalSince(start) * 1000,
                            "first_paint_ms": firstPaint.timeIntervalSince(imported) * 1000,
                            "projection_bytes": extent, "tail_text_bytes": tail.utf8.count,
                            "index_bytes": stats.index_bytes, "parse_workspace_bytes": stats.parse_workspace_bytes,
                            "peak_parse_workspace_bytes": stats.peak_parse_workspace_bytes,
                            "page_cache_bytes": stats.page_cache_bytes, "checkpoint_bytes": stats.checkpoint_bytes,
                            "explicit_snapshot_bytes": stats.explicit_snapshot_bytes,
                            "bitmap_bytes": bitmap.pixels.count, "swift_tail_bytes": tail.utf8.count,
                            "page_range": [range.lowerBound, range.upperBound]]) { _, new in new }
            return extent >= 49 * 1024 * 1024 && tail.utf8.count == 512 && !bitmap.pixels.isEmpty &&
                stats.explicit_snapshot_bytes == 0 && stats.peak_parse_workspace_bytes <= 16 * 1024 * 1024 &&
                match.isFound && match.range?.lowerBound == extent
        }
        let accepted = results.allSatisfy { $0["passed"] as? Bool == true }
        let report: [String: Any] = ["schema": 1, "accepted": accepted, "checks": results,
                                   "measurements": measurements, "long_chapter_scope": "first page render and tail text/point; no full page enumeration"]
        try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys]).write(to: output.appendingPathComponent("bounded-review.json"))
        print("bounded Apple checks=\(results.count) accepted=\(accepted)")
        if !accepted { exit(1) }
    }
}
