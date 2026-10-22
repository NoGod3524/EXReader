// SPDX-License-Identifier: MIT
import Foundation
import CoreGraphics
import CryptoKit
import CEXReader

@main
struct ModelReview {
    static func sha(_ path: URL) throws -> String {
        SHA256.hash(data: try Data(contentsOf: path)).map { String(format: "%02x", $0) }.joined()
    }

    static func sql(_ path: URL, _ statement: String) throws {
        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/usr/bin/sqlite3")
        task.arguments = [path.path, statement]
        task.standardOutput = FileHandle.nullDevice
        task.standardError = FileHandle.nullDevice
        try task.run()
        task.waitUntilExit()
        guard task.terminationStatus == 0 else { throw HostError.invalidResult("SQLite test setup failed") }
    }

    static func rejected(_ operation: () throws -> Void) -> Bool {
        do { try operation(); return false } catch { return true }
    }

    static func databaseRejected(_ operation: () throws -> Void) -> Bool {
        do { try operation(); return false }
        catch HostError.engine(let code, _) { return code == Int(EXR_DATABASE.rawValue) }
        catch { return false }
    }

    static func main() throws {
        guard ProcessInfo.processInfo.environment["GITHUB_ACTIONS"] == "true" else {
            throw HostError.invalidInput("Run only in GitHub Actions")
        }
        let resources = URL(fileURLWithPath: CommandLine.arguments[1])
        let out = URL(fileURLWithPath: CommandLine.arguments[2])
        try FileManager.default.createDirectory(at: out, withIntermediateDirectories: true)
        let library = try HostLibrary(path: out.appendingPathComponent("model.sqlite"))
        let font = try HostFont(data: Data(contentsOf: resources.appendingPathComponent("Reader.otf")))
        let session = HostSession(library: library, font: font, slowDelay: 0,
                                  viewport: CGSize(width: 480, height: 640), fontSize: 28)
        let (id, _) = try library.importUnique(file: resources.appendingPathComponent("Sample.epub"), title: "Model review")
        var checks: [[String: Any]] = []
        func check(_ name: String, _ operation: () throws -> Bool) {
            do { checks.append(["name": name, "passed": try operation()]) }
            catch { checks.append(["name": name, "passed": false, "error": error.localizedDescription]) }
        }
        var frame: HostSnapshot?
        check("open_real_source") {
            frame = try session.open(bookID: id, cancel: HostCancelBox())
            return frame?.pageIndex == 0 && frame?.image != nil && !(frame?.pageText.isEmpty ?? true)
        }
        check("cancelled_turn_keeps_frame_and_recovers") {
            let box = HostCancelBox(); box.cancel()
            guard rejected({ _ = try session.turn(1, cancel: box) }) else { return false }
            frame = try session.turn(1, cancel: HostCancelBox())
            return frame?.pageIndex == 1
        }
        check("precise_progress_is_atomic") {
            let saved = try library.progress(bookID: id)
            let persisted = try library.books().first(where: { $0.id == id })?.position
            return saved.anchor.start == frame?.pageRange.lowerBound &&
                   saved.anchor.start == persisted
        }
        check("resize_keeps_exact_offset") {
            let before = try library.progress(bookID: id).anchor.start
            frame = try session.resize(width: 610, height: 780, cancel: HostCancelBox())
            let after = try library.progress(bookID: id).anchor.start
            return before == after && frame!.pageRange.contains(before)
        }
        check("invalid_resize_keeps_viewport_and_frame") {
            let before = session.currentViewport
            guard rejected({ _ = try session.resize(width: .infinity, height: 640, cancel: HostCancelBox()) }) else { return false }
            let after = try session.renderSnapshot()
            return before == session.currentViewport && after.pageIndex == frame?.pageIndex && after.pageText == frame?.pageText
        }
        check("cancelled_font_change_recovers") {
            let old = frame!.fontSize
            let box = HostCancelBox(); box.cancel()
            guard rejected({ _ = try session.changeFont(delta: 2, cancel: box) }) else { return false }
            frame = try session.changeFont(delta: 2, cancel: HostCancelBox())
            return frame?.fontSize == old + 2
        }
        check("failed_save_rolls_back_page_and_numeric_progress") {
            let before = try session.renderSnapshot()
            let position = try library.progress(bookID: id).anchor.start
            try sql(library.path, "CREATE TRIGGER reject_progress BEFORE INSERT ON book_progress BEGIN SELECT RAISE(ABORT,'model-review'); END;")
            defer { try? sql(library.path, "DROP TRIGGER IF EXISTS reject_progress;") }
            let refused = databaseRejected { _ = try session.turn(1, cancel: HostCancelBox()) }
            let unchanged = try library.progress(bookID: id).anchor.start == position
            try sql(library.path, "DROP TRIGGER reject_progress;")
            let next = try session.turn(1, cancel: HostCancelBox())
            frame = next
            return refused && unchanged && next.pageIndex == before.pageIndex + 1
        }
        check("failed_save_rolls_back_font_and_viewport") {
            let before = try session.renderSnapshot()
            let viewport = session.currentViewport
            try sql(library.path, "CREATE TRIGGER reject_progress BEFORE INSERT ON book_progress BEGIN SELECT RAISE(ABORT,'model-review'); END;")
            defer { try? sql(library.path, "DROP TRIGGER IF EXISTS reject_progress;") }
            let fontRefused = databaseRejected { _ = try session.changeFont(delta: 2, cancel: HostCancelBox()) }
            let sizeRefused = databaseRejected { _ = try session.resize(width: 700, height: 900, cancel: HostCancelBox()) }
            try sql(library.path, "DROP TRIGGER reject_progress;")
            frame = try session.renderSnapshot()
            return fontRefused && sizeRefused && frame?.fontSize == before.fontSize && session.currentViewport == viewport
        }
        check("persistence_failure_is_reported") {
            try sql(library.path, "CREATE TRIGGER reject_progress BEFORE INSERT ON book_progress BEGIN SELECT RAISE(ABORT,'model-review'); END;")
            defer { try? sql(library.path, "DROP TRIGGER IF EXISTS reject_progress;") }
            let refused = databaseRejected { try session.persistCurrent() }
            try sql(library.path, "DROP TRIGGER reject_progress;")
            try session.persistCurrent()
            return refused
        }
        check("failed_open_keeps_previous_session") {
            let (broken, _) = try library.importUnique(file: resources.appendingPathComponent("Unicode.epub"), title: "Failing source")
            try sql(library.path, "UPDATE books SET source=X'00' WHERE id=\(broken);")
            let refused = rejected { _ = try session.open(bookID: broken, cancel: HostCancelBox()) }
            let restored = try session.renderSnapshot()
            return refused && restored.book.id == id && restored.pageText == frame?.pageText
        }
        check("cancelled_candidate_keeps_previous_book") {
            let candidate = session.candidate()
            let box = HostCancelBox(); box.cancel()
            let refused = rejected { _ = try candidate.open(bookID: id, cancel: box) }
            return refused && session.book?.id == id && candidate.book == nil
        }
        check("reopen_uses_exact_saved_offset") {
            let position = try library.progress(bookID: id).anchor.start
            let reopened = session.candidate()
            let restored = try reopened.open(bookID: id, cancel: HostCancelBox())
            let after = try library.progress(bookID: id).anchor.start
            return restored.pageRange.contains(position) && after == position
        }
        check("selection_context_rejects_wrong_book_page_and_text") {
            let current = try session.renderSnapshot()
            let good = HostSelectionContext(bookID: id, frameCount: 1, baseOffset: current.pageRange.lowerBound, text: current.pageText)
            let model = HostReaderModel()
            model.current = HostBookRow(id: id, title: "Reader", detail: "", isFixed: false, position: 0)
            model.pageText = current.pageText
            guard model.selectionContext != nil else { return false }
            model.updateViewport(CGSize(width: 480, height: 640))
            let pendingUnavailable = model.busy && model.selectionContext == nil
            model.cancelWork()
            return pendingUnavailable && !model.busy && model.selectionContext != nil && session.matches(good) &&
                !session.matches(HostSelectionContext(bookID: id + 100, frameCount: 1, baseOffset: good.baseOffset, text: good.text)) &&
                !session.matches(HostSelectionContext(bookID: id, frameCount: 1, baseOffset: good.baseOffset + 1, text: good.text)) &&
                !session.matches(HostSelectionContext(bookID: id, frameCount: 1, baseOffset: good.baseOffset, text: "old text"))
        }
        check("unicode_scalar_ranges_are_exact") {
            let text = "A😀é中"
            return hostSelectionUTF8Range(NSRange(location: 1, length: 1), in: text) == nil &&
                hostSelectionUTF8Range(NSRange(location: 2, length: 1), in: text) == nil &&
                hostSelectionUTF8Range(NSRange(location: 1, length: 2), in: text) == (1..<5) &&
                hostSelectionUTF8Range(NSRange(location: Int.max, length: 4), in: text) == nil
        }
        let accepted = checks.allSatisfy { $0["passed"] as? Bool == true }
        let env = ProcessInfo.processInfo.environment
        let program = URL(fileURLWithPath: CommandLine.arguments[0]).standardizedFileURL
        let sdk = URL(fileURLWithPath: CommandLine.arguments[3])
        var fixtures: [String: String] = [:]
        for name in ["Sample.epub", "Sample.pdf", "Unicode.epub", "Reader.otf"] {
            fixtures[name] = try sha(resources.appendingPathComponent(name))
        }
        var sdkHashes: [String: String] = [:]
        let enumerator = FileManager.default.enumerator(at: sdk, includingPropertiesForKeys: [.isRegularFileKey])!
        for case let file as URL in enumerator {
            if (try file.resourceValues(forKeys: [.isRegularFileKey])).isRegularFile == true {
                sdkHashes[String(file.path.dropFirst(sdk.path.count + 1))] = try sha(file)
            }
        }
        let report: [String: Any] = ["schema": 1, "source_sha": env["GITHUB_SHA"] ?? "",
            "run_id": env["GITHUB_RUN_ID"] ?? "", "attempt": env["GITHUB_RUN_ATTEMPT"] ?? "",
            "job": env["GITHUB_JOB"] ?? "",
            "accepted": accepted, "checks": checks,
            "program": ["path": program.lastPathComponent, "sha256": try sha(program)],
            "sdk_files_sha256": sdkHashes, "fixtures": fixtures]
        try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys])
            .write(to: out.appendingPathComponent("model-review.json"))
        print("Model review: \(checks.count) checks, accepted=\(accepted)")
        if !accepted { exit(1) }
    }
}
