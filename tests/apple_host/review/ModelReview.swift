// SPDX-License-Identifier: MIT
import Foundation
import CoreGraphics
import CryptoKit
import CEXReader
import Combine

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

    static func pump(_ timeout: TimeInterval = 10, until condition: () -> Bool) throws {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if condition() { return }
            RunLoop.current.run(until: Date().addingTimeInterval(0.01))
        }
        throw HostError.invalidResult("Model worker did not reach the expected observable state")
    }

    static func settle(_ seconds: TimeInterval) {
        let deadline = Date().addingTimeInterval(seconds)
        while Date() < deadline {
            RunLoop.current.run(until: Date().addingTimeInterval(0.01))
        }
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
        // Preserve the original snapshot/global-coordinate regression contract.
        // Bounded sessions have a separate suite; these numeric rollback tests
        // must continue asserting real book_progress writes, not zero placeholders.
        let legacy = try Data(contentsOf: resources.appendingPathComponent("Sample.epub"))
        var id: Int64 = 0, error = exr_error()
        try legacy.withUnsafeBytes { bytes in
            try "Model review".withCString { title in
                try hostCheck(exr_library_import(library.handle, EXR_EPUB, bytes.baseAddress, bytes.count, title, &id, &error), error)
            }
        }
        var checks: [[String: Any]] = []
        var observations: [String: Any] = [:]
        func check(_ name: String, _ operation: () throws -> Bool) {
            observations = [:]
            var result: [String: Any] = ["name": name]
            do { result["passed"] = try operation() }
            catch { result["passed"] = false; result["error"] = error.localizedDescription }
            if !observations.isEmpty { result["observations"] = observations }
            checks.append(result)
            if let data = try? JSONSerialization.data(withJSONObject: ["model_check": result], options: [.sortedKeys]) {
                FileHandle.standardOutput.write(data)
                FileHandle.standardOutput.write(Data([10]))
            }
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
        check("cross_book_notes_query_failure_clears_previous_book") {
            let original = try session.renderSnapshot()
            if try session.notes().isEmpty {
                _ = try library.addNote(bookID: id, start: original.pageRange.lowerBound,
                                        end: original.pageRange.lowerBound + 24, text: "Original book annotation")
            }
            let otherFile = out.appendingPathComponent("other-review.txt")
            try Data("A different book with its own unique source text and no annotations.".utf8).write(to: otherFile)
            let (otherID, _) = try library.importUnique(file: otherFile, title: "Other review book")
            let model = HostReaderModel()
            try model.installReviewSession(session, snapshot: original)
            guard !model.notes.isEmpty, model.notes.allSatisfy({ $0.bookID == id }) else { return false }
            let oldRequest = CGSize(width: 570, height: 750)
            model.updateViewport(oldRequest)
            model.cancelWork()
            guard !model.busy else { return false }
            var hidden = false, realSDKRejected = false
            defer {
                HostModelReviewGate.beforeFrameNotes = nil
                if hidden { try? sql(library.path, "ALTER TABLE notes_review_hidden RENAME TO notes;") }
            }
            HostModelReviewGate.beforeFrameNotes = { candidate in
                guard candidate.book?.id == otherID, !hidden else { return }
                try sql(library.path, "ALTER TABLE notes RENAME TO notes_review_hidden;")
                hidden = true
                realSDKRejected = databaseRejected { _ = try candidate.notes() }
            }
            model.openBook(id: otherID)
            try pump { !model.busy }
            let cleared = model.current?.id == otherID && model.notes.isEmpty && model.stateHash == "—" &&
                model.errorText.contains("标注刷新失败") && model.image != nil
            HostModelReviewGate.beforeFrameNotes = nil
            try sql(library.path, "ALTER TABLE notes_review_hidden RENAME TO notes;")
            hidden = false
            model.refreshState()
            try pump { !model.busy }
            let recovered = model.current?.id == otherID && model.notes.isEmpty &&
                model.stateHash != "—" && model.errorText.isEmpty
            let acceptedFrame = model.frameCount
            model.updateViewport(oldRequest)
            let freshRequestAccepted = model.busy && model.selectionContext == nil
            try pump { !model.busy }
            observations = ["real_sdk_query_rejected": realSDKRejected, "new_book_cleared": cleared,
                            "refresh_recovered": recovered, "fresh_viewport_request_accepted": freshRequestAccepted,
                            "accepted_frame_before_resize": acceptedFrame, "accepted_frame_after_resize": model.frameCount,
                            "current_book_id": model.current?.id ?? -1, "expected_book_id": otherID,
                            "visible_notes": model.notes.count, "error_after_resize": model.errorText]
            return realSDKRejected && cleared && recovered && freshRequestAccepted &&
                model.frameCount == acceptedFrame + 1 && model.current?.id == otherID && model.notes.isEmpty
        }
        check("same_book_notes_query_failure_preserves_list_and_recovers") {
            let original = try session.renderSnapshot()
            let model = HostReaderModel()
            try model.installReviewSession(session, snapshot: original)
            let noteIDs = model.notes.map(\.id)
            guard !noteIDs.isEmpty else { return false }
            var hidden = false, realSDKRejected = false
            defer {
                HostModelReviewGate.beforeFrameNotes = nil
                if hidden { try? sql(library.path, "ALTER TABLE notes_review_hidden RENAME TO notes;") }
            }
            HostModelReviewGate.beforeFrameNotes = { candidate in
                guard !hidden else { return }
                try sql(library.path, "ALTER TABLE notes RENAME TO notes_review_hidden;")
                hidden = true
                realSDKRejected = databaseRejected { _ = try candidate.notes() }
            }
            model.turn(1)
            try pump { !model.busy }
            let retained = model.current?.id == id && model.notes.map(\.id) == noteIDs &&
                model.errorText.contains("标注刷新失败") && model.frameCount == 2
            let errorDuringFailure = model.errorText
            HostModelReviewGate.beforeFrameNotes = nil
            try sql(library.path, "ALTER TABLE notes_review_hidden RENAME TO notes;")
            hidden = false
            model.refreshState()
            try pump { !model.busy }
            observations = ["real_sdk_query_rejected": realSDKRejected, "old_list_retained": retained,
                            "expected_note_ids": noteIDs, "recovered_note_ids": model.notes.map(\.id),
                            "error_during_failure": errorDuringFailure, "error_after_recovery": model.errorText]
            return realSDKRejected && retained && model.notes.map(\.id) == noteIDs && model.errorText.isEmpty
        }
        check("pending_viewport_handoff_has_no_idle_frame") {
            let original = try session.renderSnapshot()
            let model = HostReaderModel()
            try model.installReviewSession(session, snapshot: original)
            let initialFrame = model.frameCount
            let size = CGSize(width: 530, height: 710)
            var intermediateIdle = false, actualRefreshes = 0
            let observation = model.$busy.sink { value in
                if !value && model.frameCount == initialFrame + 1 { intermediateIdle = true }
            }
            defer { observation.cancel(); HostModelReviewGate.beforeFrameNotes = nil }
            HostModelReviewGate.beforeFrameNotes = { _ in
                actualRefreshes += 1
                if actualRefreshes == 1 {
                    DispatchQueue.main.sync { model.updateViewport(size) }
                }
            }
            model.turn(1)
            try pump { !model.busy && model.frameCount >= initialFrame + 2 }
            observations = ["intermediate_idle_published": intermediateIdle, "actual_refreshes": actualRefreshes,
                            "initial_frame": initialFrame, "final_frame": model.frameCount,
                            "actual_viewport_width": session.currentViewport.width,
                            "actual_viewport_height": session.currentViewport.height,
                            "selection_context_available": model.selectionContext != nil, "error_after_resize": model.errorText]
            return !intermediateIdle && actualRefreshes == 2 && model.frameCount == initialFrame + 2 &&
                session.currentViewport == size && model.selectionContext != nil && model.errorText.isEmpty
        }
        check("cancel_pending_viewport_keeps_frame_and_recovers") {
            let original = try session.renderSnapshot()
            let model = HostReaderModel()
            try model.installReviewSession(session, snapshot: original)
            let initialFrame = model.frameCount, viewport = session.currentViewport
            var actualPoll = false
            defer { HostSDKReview.poll = nil }
            HostSDKReview.poll = { _ in
                guard !actualPoll else { return }
                actualPoll = true
                DispatchQueue.main.sync {
                    model.updateViewport(CGSize(width: 660, height: 820))
                    model.cancelWork()
                }
            }
            model.turn(1)
            try pump { !model.busy }
            HostSDKReview.poll = nil
            settle(0.6) // A discarded debounce must not start another resize.
            try pump { !model.busy }
            let unchanged = actualPoll && model.frameCount == initialFrame && model.pageText == original.pageText &&
                session.currentViewport == viewport && model.statusText == "已取消"
            let cancelledFrame = model.frameCount, cancelledStatus = model.statusText
            model.turn(1)
            try pump { !model.busy }
            observations = ["actual_sdk_cancel_poll": actualPoll, "cancelled_frame_unchanged": unchanged,
                            "initial_frame": initialFrame, "frame_after_cancel": cancelledFrame,
                            "status_after_cancel": cancelledStatus, "frame_after_recovery": model.frameCount,
                            "error_after_recovery": model.errorText]
            return unchanged && model.frameCount == initialFrame + 1 && model.errorText.isEmpty
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
