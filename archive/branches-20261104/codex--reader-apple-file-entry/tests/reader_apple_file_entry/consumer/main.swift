// SPDX-License-Identifier: MIT
// Installed-package consumer: EXRFileEntry + installed sideload module + public
// SDK, driven through the installed example ImportStagedRequest.swift.
// Usage: consumer <work-dir> <result-file>
import Foundation
import CryptoKit
import EXRFileEntry

struct Fail: Error { let message: String }

func expect(_ condition: @autoclosure () throws -> Bool, _ message: String) throws {
    if !(try condition()) { throw Fail(message: message) }
}

let arguments = CommandLine.arguments
let root = URL(fileURLWithPath: arguments[1], isDirectory: true)
let resultPath = arguments[2]
var output: [String] = []

func emit(_ line: String) {
    output.append(line)
    print(line)
    fflush(stdout)
}

func clean(_ text: String) -> String {
    let allowed = Set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_=,.:/ -")
    return String(text.filter { allowed.contains($0) }.prefix(160))
}

func run(_ id: String, _ body: () throws -> Void) {
    do {
        try body()
        emit("check \(id) pass ok")
    } catch let failure as Fail {
        emit("check \(id) fail \(clean(failure.message))")
    } catch {
        emit("check \(id) fail unexpected \(clean(String(describing: error)))")
    }
}

func sha(_ data: Data) -> String {
    return SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
}

func message(_ error: exr_error) -> String {
    var copy = error
    return withUnsafePointer(to: &copy.message) { pointer in
        pointer.withMemoryRebound(to: CChar.self, capacity: 256) { String(cString: $0) }
    }
}

func readStored(_ library: OpaquePointer, _ id: Int64) throws -> Data {
    var source = exr_source()
    var error = exr_error()
    guard exr_library_source(library, id, &source, &error) == EXR_OK, let read = source.read_at else {
        throw Fail(message: "library_source \(message(error))")
    }
    defer { source.release?(source.context) }
    var data = Data(count: Int(source.size))
    var offset = 0
    while offset < data.count {
        let want = min(65_536, data.count - offset)
        let got = data.withUnsafeMutableBytes { raw -> Int in
            read(source.context, UInt64(offset), raw.baseAddress! + offset, want)
        }
        if got != want { throw Fail(message: "short stored read at \(offset)") }
        offset += got
    }
    return data
}

func bookCount(_ library: OpaquePointer) throws -> (Int, [Int64: String]) {
    var books: UnsafeMutablePointer<exr_book>?
    var count = 0
    var error = exr_error()
    guard exr_library_books(library, nil, &books, &count, &error) == EXR_OK else { throw Fail(message: "books \(message(error))") }
    var titles: [Int64: String] = [:]
    for index in 0..<count { titles[books![index].id] = String(cString: books![index].title) }
    exr_books_free(books, count)
    return (count, titles)
}

func body() {
    let expectations = try! JSONSerialization.jsonObject(with: Data(contentsOf: root.appendingPathComponent("expectations.json"))) as! [String: Any]
    let nine = expectations["nine"] as! [[String: Any]]
    let fixtureRoot = root.appendingPathComponent("fixtures", isDirectory: true)
    let picked = root.appendingPathComponent("picked", isDirectory: true)
    let stageDirectory = root.appendingPathComponent("stage", isDirectory: true)
    let libraryPath = root.appendingPathComponent("consumer-library.sqlite").path
    try! FileManager.default.createDirectory(at: picked, withIntermediateDirectories: true)
    let area = try! FileEntryStagingArea(directory: stageDirectory)
    var library: OpaquePointer?
    var error = exr_error()
    guard exr_library_open(libraryPath, &library, &error) == EXR_OK, let handle = library else {
        emit("check library-open fail \(clean(message(error)))")
        return
    }
    var ids: [String: Int64] = [:]
    var originals: [String: Data] = [:]

    for entry in nine {
        let file = entry["file"] as! String
        let expectedSha = entry["sha256"] as! String
        let format = entry["format"] as! String
        run("format-\(format)-stage-import-readback") {
            let original = try Data(contentsOf: fixtureRoot.appendingPathComponent(file))
            try expect(sha(original) == expectedSha, "fixture digest")
            let source = picked.appendingPathComponent("\u{4E66}-" + file)
            try original.write(to: source)
            let request = try area.stage(url: source)
            try expect(request.format?.rawValue == format && request.sha256 == expectedSha, "request")
            try FileManager.default.removeItem(at: source)
            let outcome = importStagedRequest(library: handle, area: area, request: request)
            guard case .imported(let id, let created) = outcome else { throw Fail(message: "outcome \(outcome)") }
            try expect(created && id > 0, "created")
            try expect(!FileManager.default.fileExists(atPath: request.stagedPath), "staging not released")
            let stored = try readStored(handle, id)
            try expect(stored == original, "stored bytes differ (\(stored.count) vs \(original.count))")
            ids[format] = id
            originals[format] = original
        }
    }

    run("duplicate-stage-import-reuses-book-and-releases-staging") {
        guard let id = ids["epub"], let original = originals["epub"] else { throw Fail(message: "epub missing") }
        let again = picked.appendingPathComponent("again-copy.epub")
        try original.write(to: again)
        let request = try area.stage(url: again)
        let outcome = importStagedRequest(library: handle, area: area, request: request)
        guard case .imported(let second, let created) = outcome else { throw Fail(message: "outcome \(outcome)") }
        try expect(second == id && !created, "dedup id=\(second) created=\(created)")
        try expect(area.pendingRequests().isEmpty, "staging left")
    }

    run("unicode-title-and-staged-path-roundtrip") {
        guard let id = ids["epub"] else { throw Fail(message: "epub missing") }
        let (_, titles) = try bookCount(handle)
        let file = (nine.first { ($0["format"] as! String) == "epub" }!["file"] as! String)
        let expected = ((file as NSString).deletingPathExtension)
        try expect(titles[id].map { Array($0.utf8) } == Array(("\u{4E66}-" + expected).utf8), "title \(titles[id] ?? "nil")")
    }

    run("cancel-keeps-staged-request-and-retry-succeeds") {
        let source = picked.appendingPathComponent("cancel-me.txt")
        try Data("Cancel then retry. \u{4E2D}\u{6587}\u{1F600}\n".utf8).write(to: source)
        let before = try bookCount(handle).0
        let request = try area.stage(url: source)
        let token = FileEntryCancellation(); token.cancel()
        let first = importStagedRequest(library: handle, area: area, request: request, cancellation: token)
        try expect(first == .cancelled, "first outcome \(first)")
        try expect(try bookCount(handle).0 == before, "book created by cancelled import")
        try expect(area.pendingRequests().map { $0.id } == [request.id] && FileManager.default.fileExists(atPath: request.stagedPath), "request lost")
        let second = importStagedRequest(library: handle, area: area, request: request)
        guard case .imported(_, let created) = second else { throw Fail(message: "retry \(second)") }
        try expect(created && area.pendingRequests().isEmpty, "retry")
    }

    run("invalid-bytes-fail-keep-staging-and-create-no-book") {
        let source = picked.appendingPathComponent("garbage.epub")
        try Data(repeating: 0x41, count: 4096).write(to: source)
        let before = try bookCount(handle).0
        let request = try area.stage(url: source)
        let outcome = importStagedRequest(library: handle, area: area, request: request)
        guard case .failed = outcome else { throw Fail(message: "outcome \(outcome)") }
        try expect(try bookCount(handle).0 == before, "book created")
        try expect(FileManager.default.fileExists(atPath: request.stagedPath), "staging removed after failure")
        area.release(request)
    }

    run("staging-empty-after-all-imports") {
        try expect(area.pendingRequests().isEmpty && area.sweepOrphans() == 0, "pending")
        try expect(((try? FileManager.default.contentsOfDirectory(atPath: stageDirectory.path)) ?? ["x"]).isEmpty, "files left")
    }

    run("library-reopen-readback-all-nine") {
        exr_library_close(handle)
        var reopened: OpaquePointer?
        var failure = exr_error()
        guard exr_library_open(libraryPath, &reopened, &failure) == EXR_OK, let again = reopened else {
            throw Fail(message: "reopen \(message(failure))")
        }
        defer { exr_library_close(again) }
        try expect(ids.count == 9, "ids \(ids.count)")
        for (format, id) in ids {
            try expect(try readStored(again, id) == originals[format]!, "reopened bytes \(format)")
        }
    }
}

// The SDK handle is single-owner and staging refuses the main thread: run on one worker.
let finished = DispatchSemaphore(value: 0)
let worker = Thread {
    body()
    finished.signal()
}
worker.stackSize = 4 << 20
worker.start()
if finished.wait(timeout: .now() + 600) != .success {
    emit("check consumer-timeout fail worker-did-not-finish")
}
try! output.joined(separator: "\n").appending("\n").write(toFile: resultPath, atomically: true, encoding: .utf8)
let failures = output.filter { $0.contains(" fail ") }.count
print("consumer finished checks=\(output.count) failures=\(failures)")
exit(failures == 0 ? 0 : 1)
