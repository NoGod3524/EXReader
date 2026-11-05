// SPDX-License-Identifier: MIT
// Native probe of the installed EXRFileEntry module (macOS and iOS simulator).
// Usage: probe <work-dir> <result-file>
// <work-dir>/expectations.json carries independently computed fixture digests.
// Output: "check <id> pass|fail <detail>" lines, one per named check.
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

// MARK: helpers

typealias Staged = Result<FileEntryRequest, FileEntryError>

final class Counter {
    private let lock = NSLock()
    private var value = 0
    func bump() { lock.lock(); value += 1; lock.unlock() }
    var count: Int { lock.lock(); defer { lock.unlock() }; return value }
}

final class CountingScope: FileEntryScopeAccess {
    let starts = Counter(), stops = Counter()
    let grant: Bool
    init(grant: Bool = true) { self.grant = grant }
    func start(_ url: URL) -> Bool { starts.bump(); return grant }
    func stop(_ url: URL) { stops.bump() }
}

func offMain<T>(_ body: @escaping () -> T) -> T {
    var out: T?
    let done = DispatchSemaphore(value: 0)
    DispatchQueue.global().async {
        out = body()
        done.signal()
    }
    done.wait()
    return out!
}

func stage(_ area: FileEntryStagingArea, _ url: URL, origin: FileEntryRequest.Origin = .picker,
           cancel: FileEntryCancellation = FileEntryCancellation()) -> Staged {
    return offMain {
        do { return .success(try area.stage(url: url, origin: origin, cancellation: cancel)) }
        catch let error as FileEntryError { return .failure(error) }
        catch { return .failure(.io(errno: -1, stage: "unknown")) }
    }
}

func stageAll(_ area: FileEntryStagingArea, _ urls: [URL], cancel: FileEntryCancellation = FileEntryCancellation()) -> [Staged] {
    return offMain { area.stage(urls: urls, cancellation: cancel) }
}

func succeeded(_ result: Staged) throws -> FileEntryRequest {
    switch result {
    case .success(let request): return request
    case .failure(let error): throw Fail(message: "expected success got \(error)")
    }
}

func failed(_ result: Staged) throws -> FileEntryError {
    switch result {
    case .success: throw Fail(message: "expected failure got success")
    case .failure(let error): return error
    }
}

func pattern(_ count: Int, seed: UInt64) -> [UInt8] {
    var x = seed
    var out: [UInt8] = []
    out.reserveCapacity(count)
    for _ in 0..<count {
        x ^= x << 13
        x ^= x >> 7
        x ^= x << 17
        out.append(UInt8(truncatingIfNeeded: x >> 24))
    }
    return out
}

func put(_ url: URL, _ bytes: [UInt8]) {
    try! Data(bytes).write(to: url)
}

func sparse(_ url: URL, size: UInt64) {
    let descriptor = open(url.path, O_WRONLY | O_CREAT, 0o600)
    precondition(descriptor >= 0 && ftruncate(descriptor, off_t(size)) == 0)
    close(descriptor)
}

func rawNames(_ directory: URL) -> [[UInt8]] {
    guard let dir = opendir(directory.path) else { return [] }
    defer { closedir(dir) }
    var names: [[UInt8]] = []
    while let entry = readdir(dir) {
        let length = Int(entry.pointee.d_namlen)
        let bytes = withUnsafePointer(to: &entry.pointee.d_name) { pointer in
            pointer.withMemoryRebound(to: UInt8.self, capacity: length) {
                Array(UnsafeBufferPointer(start: $0, count: length))
            }
        }
        if bytes != [0x2e] && bytes != [0x2e, 0x2e] { names.append(bytes) }
    }
    return names
}

func entries(_ directory: URL) -> [String] {
    return ((try? FileManager.default.contentsOfDirectory(atPath: directory.path)) ?? []).sorted()
}

func sha(_ data: Data) -> String {
    return SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
}

func bytes(_ path: String) -> Data {
    return (try? Data(contentsOf: URL(fileURLWithPath: path))) ?? Data()
}

var scratchCounter = 0
func scratch() -> (src: URL, stage: URL) {
    scratchCounter += 1
    let base = root.appendingPathComponent("work/case-\(scratchCounter)", isDirectory: true)
    let src = base.appendingPathComponent("src", isDirectory: true)
    let staging = base.appendingPathComponent("stage", isDirectory: true)
    try! FileManager.default.createDirectory(at: src, withIntermediateDirectories: true)
    return (src, staging)
}

func makeArea(_ directory: URL, maxFile: UInt64 = FileEntryLimits.maxFileBytes,
              maxBytes: UInt64 = FileEntryLimits.maxPendingBytes,
              maxRequests: Int = FileEntryLimits.maxPendingRequests,
              requestDownload: Bool = true, hooks: FileEntryHooks = .live) -> FileEntryStagingArea {
    return try! FileEntryStagingArea(directory: directory, maxFileBytes: maxFile, maxPendingBytes: maxBytes,
                                     maxPendingRequests: maxRequests, requestDownload: requestDownload, hooks: hooks)
}

let expectations = try! JSONSerialization.jsonObject(with: Data(contentsOf: root.appendingPathComponent("expectations.json"))) as! [String: Any]
let fixtures = expectations["fixtures"] as! [String: [String: Any]]
let fixtureRoot = root.appendingPathComponent("fixtures", isDirectory: true)
let chunk = FileEntryLimits.copyChunkBytes

// MARK: checks

run("contract-limits-and-nine-format-hints") {
    try expect(FileEntryLimits.streamFormatBytes == 134_217_728, "stream")
    try expect(FileEntryLimits.memoryFormatBytes == 33_554_432, "memory")
    try expect(FileEntryLimits.maxBatchCount == 64 && FileEntryLimits.copyChunkBytes == 65_536, "counts")
    try expect(FileFormatHint.allCases.count == 9, "nine")
    try expect(Set(FileFormatHint.allCases.map { $0.exrFormatRawValue }) == Set(Int32(1)...Int32(9)), "raw values")
    let table: [(String, Int32)] = [("txt", 1), ("html", 2), ("htm", 2), ("fb2", 3), ("epub", 4), ("docx", 5),
                                    ("rtf", 6), ("mobi", 7), ("pdf", 8), ("cbz", 9), ("EPUB", 4), ("PdF", 8)]
    for (ext, raw) in table {
        try expect(FileFormatHint.from(pathExtension: ext)?.exrFormatRawValue == raw, "ext \(ext)")
    }
    try expect(FileFormatHint.from(pathExtension: "xyz") == nil && FileFormatHint.from(pathExtension: "") == nil, "unknown")
    for hint in FileFormatHint.allCases {
        let stream = hint == .epub || hint == .cbz || hint == .pdf
        try expect(hint.byteLimit == (stream ? FileEntryLimits.streamFormatBytes : FileEntryLimits.memoryFormatBytes), "limit \(hint)")
    }
}

run("stage-exact-bytes-multichunk-with-independent-sha") {
    let dirs = scratch()
    let name = "multi-chunk.epub"
    let meta = fixtures[name]!
    let source = fixtureRoot.appendingPathComponent(name)
    let original = try Data(contentsOf: source)
    let area = makeArea(dirs.stage)
    let request = try succeeded(stage(area, source))
    try expect(original.count == meta["size"] as! Int && original.count > 3 * chunk, "fixture size")
    try expect(request.byteCount == UInt64(original.count), "byteCount")
    try expect(request.sha256 == meta["sha256"] as! String, "sha256 differs from Python digest")
    try expect(bytes(request.stagedPath) == original, "bytes differ")
    try expect(request.displayName == name && request.format == .epub && request.origin == .picker, "metadata")
    try expect(!request.stagedPath.contains("multi-chunk"), "staged name leaks display name")
    try expect(area.pendingRequests().count == 1, "pending")
}

run("empty-and-one-byte-files-staged-exactly") {
    let dirs = scratch()
    let area = makeArea(dirs.stage)
    let empty = dirs.src.appendingPathComponent("empty.txt"), one = dirs.src.appendingPathComponent("one.txt")
    put(empty, []); put(one, [0x00])
    let first = try succeeded(stage(area, empty)), second = try succeeded(stage(area, one))
    try expect(first.byteCount == 0 && bytes(first.stagedPath).isEmpty, "empty")
    try expect(first.sha256 == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "empty sha")
    try expect(second.byteCount == 1 && bytes(second.stagedPath) == Data([0]), "one byte nul")
}

run("unicode-names-preserved-scalar-exact-nfc-and-nfd") {
    let dirs = scratch()
    let area = makeArea(dirs.stage)
    let names = ["caf\u{E9} \u{4E66}\u{7C4D}\u{1F600}.epub", "cafe\u{301} \u{4E66}\u{7C4D}\u{1F600}.epub"]
    for (index, name) in names.enumerated() {
        let folder = dirs.src.appendingPathComponent("d\(index)", isDirectory: true)
        try! FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let url = folder.appendingPathComponent(name)
        put(url, pattern(100, seed: UInt64(index + 1)))
        // Oracle: the raw bytes the file system reports for the entry.
        let onDisk = rawNames(folder)
        try expect(onDisk.count == 1, "listing")
        let request = try succeeded(stage(area, url))
        try expect(Array(request.displayName.utf8) == onDisk[0], "bytes differ from disk name \(Array(request.displayName.unicodeScalars).map { String($0.value, radix: 16) })")
        try expect(request.displayName.hasSuffix(".epub") && request.displayName.unicodeScalars.contains(UnicodeScalar(0x1F600)!), "content lost")
    }
    let reopened = makeArea(dirs.stage).pendingRequests()
    try expect(reopened.count == 2, "reopened count")
    let live = Set(area.pendingRequests().map { Array($0.displayName.unicodeScalars) })
    try expect(Set(reopened.map { Array($0.displayName.unicodeScalars) }) == live, "manifest changed scalars")
}

run("staging-stable-after-scope-release-and-source-removal") {
    let dirs = scratch()
    let scope = CountingScope()
    let area = makeArea(dirs.stage, hooks: FileEntryHooks(scope: scope))
    let source = dirs.src.appendingPathComponent("book.pdf")
    let original = pattern(chunk * 2 + 5, seed: 7)
    put(source, original)
    let request = try succeeded(stage(area, source))
    try expect(scope.starts.count == 1 && scope.stops.count == 1, "scope calls \(scope.starts.count)/\(scope.stops.count)")
    try! FileManager.default.removeItem(at: source)
    try expect(bytes(request.stagedPath) == Data(original), "staged bytes changed after source removal")
    try expect(bytes(request.stagedPath).count == Int(request.byteCount) && sha(bytes(request.stagedPath)) == request.sha256, "digest")
}

run("scope-stopped-once-on-every-failure-path") {
    let dirs = scratch()
    let scope = CountingScope()
    var fire: ((URL) -> Void)?
    let hooks = FileEntryHooks(scope: scope, afterChunk: { index, url in if index == 0 { fire?(url) } })
    let area = makeArea(dirs.stage, maxFile: 200_000, hooks: hooks)
    var attempts = 0
    let big = dirs.src.appendingPathComponent("big.epub"); put(big, pattern(chunk * 3, seed: 3))
    let huge = dirs.src.appendingPathComponent("huge.epub"); sparse(huge, size: 200_001)
    let folder = dirs.src.appendingPathComponent("folder.epub", isDirectory: true)
    try! FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    let cases: [(URL, FileEntryError, (() -> Void)?)] = [
        (dirs.src.appendingPathComponent("missing.epub"), .notFound, nil),
        (folder, .notRegularFile, nil),
        (huge, .tooLarge(limit: 200_000), nil),
        (big, .changedDuringCopy, { truncate(big.path, 10) }),
    ]
    for (url, expected, action) in cases {
        if let act = action { fire = { _ in act() } } else { fire = nil }
        attempts += 1
        let error = try failed(stage(area, url))
        try expect(error == expected, "expected \(expected) got \(error)")
        try expect(scope.starts.count == attempts && scope.stops.count == attempts, "unbalanced after \(expected)")
    }
    let token = FileEntryCancellation()
    put(big, pattern(chunk * 3, seed: 3))
    fire = { _ in token.cancel() }
    attempts += 1
    try expect(try failed(stage(area, big, cancel: token)) == .cancelled, "cancel")
    try expect(scope.starts.count == attempts && scope.stops.count == attempts, "unbalanced after cancel")
    try expect(entries(dirs.stage).isEmpty, "residue \(entries(dirs.stage))")
}

run("scope-not-granted-means-no-stop-and-plain-url-still-read") {
    let dirs = scratch()
    let scope = CountingScope(grant: false)
    let area = makeArea(dirs.stage, hooks: FileEntryHooks(scope: scope))
    let source = dirs.src.appendingPathComponent("plain.txt"); put(source, pattern(1000, seed: 9))
    let request = try succeeded(stage(area, source))
    try expect(scope.starts.count == 1 && scope.stops.count == 0, "stop without start grant")
    try expect(bytes(request.stagedPath) == (try Data(contentsOf: source)), "bytes")
}

run("read-only-source-staged-and-source-left-untouched") {
    let dirs = scratch()
    let area = makeArea(dirs.stage)
    let source = dirs.src.appendingPathComponent("ro.epub"); put(source, pattern(chunk + 3, seed: 11))
    chmod(source.path, 0o444)
    var before = stat(); stat(source.path, &before)
    let original = try Data(contentsOf: source)
    let request = try succeeded(stage(area, source))
    var after = stat(); stat(source.path, &after)
    try expect(bytes(request.stagedPath) == original, "bytes")
    try expect(after.st_mode == before.st_mode && after.st_mtimespec.tv_sec == before.st_mtimespec.tv_sec
        && after.st_mtimespec.tv_nsec == before.st_mtimespec.tv_nsec && after.st_size == before.st_size, "source metadata changed")
    try expect((try Data(contentsOf: source)) == original, "source bytes changed")
    chmod(source.path, 0o644)
}

run("unreadable-source-reports-access-denied-no-residue") {
    let dirs = scratch()
    let area = makeArea(dirs.stage)
    let source = dirs.src.appendingPathComponent("locked.epub"); put(source, pattern(100, seed: 13))
    try expect(geteuid() != 0, "running as root")
    chmod(source.path, 0o000)
    defer { chmod(source.path, 0o644) }
    let error = try failed(stage(area, source))
    try expect(error == .accessDenied || error == .coordination(code: NSFileReadNoPermissionError), "got \(error)")
    try expect(entries(dirs.stage).isEmpty, "residue")
}

run("missing-and-moved-sources-report-not-found") {
    let dirs = scratch()
    let area = makeArea(dirs.stage)
    let original = dirs.src.appendingPathComponent("moved.epub"), moved = dirs.src.appendingPathComponent("moved-away.epub")
    let content = pattern(chunk + 9, seed: 17)
    put(original, content)
    try! FileManager.default.moveItem(at: original, to: moved)
    try expect(try failed(stage(area, original)) == .notFound, "old url")
    try expect(try failed(stage(area, dirs.src.appendingPathComponent("never.epub"))) == .notFound, "never existed")
    let request = try succeeded(stage(area, moved))
    try expect(bytes(request.stagedPath) == Data(content), "new url bytes")
    try expect(entries(dirs.stage).count == 2, "only the committed pair remains")
}

run("moved-during-copy-completes-from-open-descriptor") {
    let dirs = scratch()
    let source = dirs.src.appendingPathComponent("rename.epub"), target = dirs.src.appendingPathComponent("renamed.epub")
    let content = pattern(chunk * 4 + 1, seed: 19)
    put(source, content)
    var moved = false
    let hooks = FileEntryHooks(afterChunk: { index, _ in
        if index == 0 && !moved { moved = true; rename(source.path, target.path) }
    })
    let area = makeArea(dirs.stage, hooks: hooks)
    let request = try succeeded(stage(area, source))
    try expect(moved && !FileManager.default.fileExists(atPath: source.path), "hook did not move")
    try expect(bytes(request.stagedPath) == Data(content), "bytes differ")
}

run("truncated-during-copy-rejected-without-residue-and-reservation-released") {
    let dirs = scratch()
    let size = chunk * 2 + 1
    let source = dirs.src.appendingPathComponent("shrink.epub")
    put(source, pattern(size, seed: 23))
    var fired = false
    let hooks = FileEntryHooks(afterChunk: { index, _ in
        if index == 0 && !fired { fired = true; truncate(source.path, 10) }
    })
    let area = makeArea(dirs.stage, maxBytes: UInt64(size), hooks: hooks)
    try expect(try failed(stage(area, source)) == .changedDuringCopy, "truncate")
    try expect(entries(dirs.stage).isEmpty && area.pendingRequests().isEmpty, "residue \(entries(dirs.stage))")
    let intact = dirs.src.appendingPathComponent("intact.epub"); put(intact, pattern(size, seed: 24))
    _ = try succeeded(stage(area, intact))
}

run("grown-during-copy-rejected-without-residue") {
    let dirs = scratch()
    let source = dirs.src.appendingPathComponent("grow.epub")
    put(source, pattern(chunk * 2, seed: 29))
    var fired = false
    let hooks = FileEntryHooks(afterChunk: { index, _ in
        if index == 0 && !fired {
            fired = true
            let handle = FileHandle(forWritingAtPath: source.path)!
            handle.seekToEndOfFile(); handle.write(Data([1, 2, 3])); handle.closeFile()
        }
    })
    let area = makeArea(dirs.stage, hooks: hooks)
    try expect(try failed(stage(area, source)) == .changedDuringCopy, "grow")
    try expect(entries(dirs.stage).isEmpty, "residue")
}

run("cancel-before-start-opens-nothing") {
    let dirs = scratch()
    let scope = CountingScope()
    let area = makeArea(dirs.stage, hooks: FileEntryHooks(scope: scope))
    let source = dirs.src.appendingPathComponent("early.epub"); put(source, pattern(50, seed: 31))
    let token = FileEntryCancellation(); token.cancel(); token.cancel()
    try expect(token.isCancelled, "flag")
    try expect(try failed(stage(area, source, cancel: token)) == .cancelled, "cancelled")
    try expect(scope.starts.count == 0 && entries(dirs.stage).isEmpty, "work was done")
}

run("cancel-mid-copy-leaves-no-residue-and-reopens-clean") {
    let dirs = scratch()
    let source = dirs.src.appendingPathComponent("mid.epub"); put(source, pattern(chunk * 4, seed: 37))
    let token = FileEntryCancellation()
    let hooks = FileEntryHooks(afterChunk: { index, _ in if index == 1 { token.cancel() } })
    let area = makeArea(dirs.stage, hooks: hooks)
    try expect(try failed(stage(area, source, cancel: token)) == .cancelled, "cancelled")
    try expect(entries(dirs.stage).isEmpty, "residue \(entries(dirs.stage))")
    let reopened = makeArea(dirs.stage)
    try expect(reopened.pendingRequests().isEmpty && reopened.sweepOrphans() == 0, "reopen")
    try expect(bytes(source.path).count == chunk * 4, "source touched")
}

run("batch-partial-failure-keeps-good-files-and-typed-errors") {
    let dirs = scratch()
    let area = makeArea(dirs.stage)
    let good1 = dirs.src.appendingPathComponent("one.epub"), good2 = dirs.src.appendingPathComponent("two.pdf")
    let folder = dirs.src.appendingPathComponent("dir.epub", isDirectory: true)
    put(good1, pattern(chunk + 1, seed: 41)); put(good2, pattern(77, seed: 43))
    try! FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    let results = stageAll(area, [good1, dirs.src.appendingPathComponent("gone.epub"), folder, good2])
    try expect(results.count == 4, "count")
    let first = try succeeded(results[0]), last = try succeeded(results[3])
    try expect(try failed(results[1]) == .notFound && (try failed(results[2])) == .notRegularFile, "typed errors")
    try expect(bytes(first.stagedPath) == (try Data(contentsOf: good1)) && bytes(last.stagedPath) == (try Data(contentsOf: good2)), "bytes")
    try expect(entries(dirs.stage).count == 4 && area.pendingRequests().count == 2, "staging \(entries(dirs.stage))")
}

run("batch-cancel-marks-remaining-cancelled-without-opening") {
    let dirs = scratch()
    let scope = CountingScope()
    let token = FileEntryCancellation()
    let hooks = FileEntryHooks(scope: scope, afterChunk: { _, url in if url.lastPathComponent == "b.epub" { token.cancel() } })
    let area = makeArea(dirs.stage, hooks: hooks)
    var urls: [URL] = []
    for name in ["a.epub", "b.epub", "c.epub", "d.epub"] {
        let url = dirs.src.appendingPathComponent(name); put(url, pattern(500, seed: 47)); urls.append(url)
    }
    let results = stageAll(area, urls, cancel: token)
    _ = try succeeded(results[0])
    for index in 1...3 { try expect(try failed(results[index]) == .cancelled, "result \(index)") }
    try expect(scope.starts.count == 2, "opened \(scope.starts.count)")
    try expect(area.pendingRequests().count == 1 && entries(dirs.stage).count == 2, "staging")
}

run("batch-count-cap-reports-too-many-files") {
    let dirs = scratch()
    let area = makeArea(dirs.stage)
    var urls: [URL] = []
    for index in 0..<66 {
        let url = dirs.src.appendingPathComponent(String(format: "f%02d.txt", index)); put(url, [UInt8(index)]); urls.append(url)
    }
    let results = stageAll(area, urls)
    for index in 0..<64 { _ = try succeeded(results[index]) }
    for index in 64..<66 { try expect(try failed(results[index]) == .tooManyFiles(limit: 64), "tail \(index)") }
    try expect(area.pendingRequests().count == 64, "pending")
}

run("size-limits-follow-import-policy-and-fail-before-copy") {
    let dirs = scratch()
    let area = makeArea(dirs.stage)
    try expect(makeArea(scratch().stage, maxFile: UInt64.max).maxFileBytes == FileEntryLimits.maxFileBytes, "limit raised")
    let text = dirs.src.appendingPathComponent("big.txt"); sparse(text, size: 33_554_433)
    let epub = dirs.src.appendingPathComponent("big.epub"); sparse(epub, size: 134_217_729)
    let unknown = dirs.src.appendingPathComponent("big.bin"); sparse(unknown, size: 134_217_729)
    try expect(try failed(stage(area, text)) == .tooLarge(limit: 33_554_432), "txt")
    try expect(try failed(stage(area, epub)) == .tooLarge(limit: 134_217_728), "epub")
    try expect(try failed(stage(area, unknown)) == .tooLarge(limit: 134_217_728), "unknown")
    try expect(entries(dirs.stage).isEmpty, "residue")
    let boundary = dirs.src.appendingPathComponent("edge.txt"); put(boundary, pattern(33_554_432, seed: 53))
    let request = try succeeded(stage(area, boundary))
    try expect(request.byteCount == 33_554_432 && request.sha256 == sha(try Data(contentsOf: boundary)), "boundary copy")
    area.release(request)
    let lowered = makeArea(scratch().stage, maxFile: 102_400)
    let exact = dirs.src.appendingPathComponent("exact.epub"), over = dirs.src.appendingPathComponent("over.epub")
    put(exact, pattern(102_400, seed: 59)); put(over, pattern(102_401, seed: 61))
    _ = try succeeded(stage(lowered, exact))
    try expect(try failed(stage(lowered, over)) == .tooLarge(limit: 102_400), "lowered")
}

run("pending-caps-enforced-and-double-release-does-not-underflow") {
    let dirs = scratch()
    let area = makeArea(dirs.stage, maxBytes: 10_000, maxRequests: 2)
    func file(_ name: String, _ size: Int) -> URL {
        let url = dirs.src.appendingPathComponent(name); put(url, pattern(size, seed: UInt64(size))); return url
    }
    let a = try succeeded(stage(area, file("a.txt", 6000)))
    try expect(try failed(stage(area, file("b-too-big.txt", 6000))) == .tooManyPending, "bytes cap")
    let b = try succeeded(stage(area, file("b.txt", 3000)))
    try expect(try failed(stage(area, file("c-count.txt", 1))) == .tooManyPending, "request cap")
    area.release(a); area.release(a)
    try expect(try failed(stage(area, file("c.txt", 8000))) == .tooManyPending, "double release freed bytes twice")
    _ = try succeeded(stage(area, file("d.txt", 6000)))
    area.release(b)
    try expect(entries(dirs.stage).count == 2, "files \(entries(dirs.stage))")
}

run("non-regular-sources-rejected-without-blocking-and-symlink-followed") {
    let dirs = scratch()
    let area = makeArea(dirs.stage)
    let fifo = dirs.src.appendingPathComponent("pipe.epub")
    try expect(mkfifo(fifo.path, 0o600) == 0, "mkfifo")
    try expect(try failed(stage(area, fifo)) == .notRegularFile, "fifo")
    let real = dirs.src.appendingPathComponent("real.epub"), link = dirs.src.appendingPathComponent("link.epub")
    put(real, pattern(900, seed: 67))
    try expect(symlink(real.path, link.path) == 0, "symlink")
    let request = try succeeded(stage(area, link))
    try expect(bytes(request.stagedPath) == (try Data(contentsOf: real)), "symlink bytes")
}

run("icloud-not-downloaded-reported-before-any-copy") {
    let dirs = scratch()
    let scope = CountingScope()
    let source = dirs.src.appendingPathComponent("cloud.epub"); put(source, pattern(100, seed: 71))
    let hooks = FileEntryHooks(scope: scope, ubiquity: { _ in .notDownloaded })
    let area = makeArea(dirs.stage, hooks: hooks)
    guard case .notDownloaded = try failed(stage(area, source)) else { throw Fail(message: "not reported") }
    let quiet = makeArea(scratch().stage, requestDownload: false, hooks: hooks)
    try expect(try failed(stage(quiet, source)) == .notDownloaded(downloadRequested: false), "no request")
    try expect(entries(dirs.stage).isEmpty && scope.starts.count == 2 && scope.stops.count == 2, "work or scope \(scope.starts.count)/\(scope.stops.count)")
    try expect(FileEntryHooks.liveUbiquity(URL(fileURLWithPath: "/tmp/.Book.epub.icloud")) == .notDownloaded, "placeholder")
    try expect(FileEntryHooks.liveUbiquity(source) == .notUbiquitous, "local file")
}

run("coordinated-read-waits-for-active-writer") {
    let dirs = scratch()
    let source = dirs.src.appendingPathComponent("coordinated.txt"); put(source, Array("old-content".utf8))
    let area = makeArea(dirs.stage)
    let started = DispatchSemaphore(value: 0), finished = DispatchSemaphore(value: 0)
    DispatchQueue.global().async {
        let writer = NSFileCoordinator(filePresenter: nil)
        var coordinationError: NSError?
        writer.coordinate(writingItemAt: source, options: [], error: &coordinationError) { writable in
            started.signal()
            Thread.sleep(forTimeInterval: 0.8)
            try? Data("new-content".utf8).write(to: writable)
        }
        finished.signal()
    }
    started.wait()
    let begin = Date()
    let request = try succeeded(stage(area, source))
    let waited = Date().timeIntervalSince(begin)
    finished.wait()
    try expect(bytes(request.stagedPath) == Data("new-content".utf8), "read before writer finished")
    try expect(waited >= 0.3, "did not wait waited=\(waited)")
}

run("main-thread-call-refused-before-any-io") {
    let dirs = scratch()
    let scope = CountingScope()
    let area = makeArea(dirs.stage, hooks: FileEntryHooks(scope: scope))
    let source = dirs.src.appendingPathComponent("main.epub"); put(source, pattern(10, seed: 73))
    try expect(Thread.isMainThread, "probe not on main thread")
    do {
        _ = try area.stage(url: source)
        throw Fail(message: "main thread call succeeded")
    } catch let error as FileEntryError {
        try expect(error == .calledOnMainThread, "got \(error)")
    }
    try expect(scope.starts.count == 0 && entries(dirs.stage).isEmpty, "work was done")
}

run("background-stage-completes-off-main-thread-in-order") {
    let dirs = scratch()
    let area = makeArea(dirs.stage)
    var urls: [URL] = []
    for index in 0..<3 {
        let url = dirs.src.appendingPathComponent("bg\(index).epub"); put(url, pattern(300 + index, seed: UInt64(80 + index))); urls.append(url)
    }
    let done = DispatchSemaphore(value: 0)
    var onMain = true
    var results: [Staged] = []
    area.stageInBackground(urls: urls + [dirs.src.appendingPathComponent("absent.epub")]) { batch in
        onMain = Thread.isMainThread
        results = batch
        done.signal()
    }
    try expect(done.wait(timeout: .now() + 60) == .success, "timeout")
    try expect(!onMain && results.count == 4, "thread or count")
    for index in 0..<3 { try expect(try succeeded(results[index]).displayName == "bg\(index).epub", "order \(index)") }
    try expect(try failed(results[3]) == .notFound, "tail")
}

run("close-cancels-running-copy-then-refuses-new-work") {
    let dirs = scratch()
    let source = dirs.src.appendingPathComponent("long.epub"); put(source, pattern(chunk * 64, seed: 89))
    let hooks = FileEntryHooks(afterChunk: { _, _ in Thread.sleep(forTimeInterval: 0.03) })
    let area = makeArea(dirs.stage, hooks: hooks)
    let flag = Counter()
    var outcome: Staged?
    let ended = DispatchSemaphore(value: 0)
    DispatchQueue.global().async {
        outcome = stage(area, source)
        flag.bump()
        ended.signal()
    }
    Thread.sleep(forTimeInterval: 0.25)
    area.close()
    try expect(ended.wait(timeout: .now() + 30) == .success, "worker did not finish")
    try expect(try failed(outcome!) == .cancelled, "not cancelled")
    try expect(entries(dirs.stage).isEmpty, "residue")
    try expect(try failed(stage(area, source)) == .closed, "stage after close")
    area.close()
    let done = DispatchSemaphore(value: 0)
    var late: [Staged] = []
    area.stageInBackground(urls: [source]) { late = $0; done.signal() }
    try expect(done.wait(timeout: .now() + 30) == .success && late.count == 1, "background")
    try expect(try failed(late[0]) == .closed, "background after close")
}

run("concurrent-staging-keeps-accounting-exact") {
    let dirs = scratch()
    let area = makeArea(dirs.stage, maxRequests: 20)
    let group = DispatchGroup()
    let lock = NSLock()
    var successes = 0
    for worker in 0..<4 {
        group.enter()
        DispatchQueue.global().async {
            for item in 0..<5 {
                let url = dirs.src.appendingPathComponent("w\(worker)-\(item).epub")
                put(url, pattern(2000, seed: UInt64(worker * 10 + item + 1)))
                if (try? area.stage(url: url)) != nil { lock.lock(); successes += 1; lock.unlock() }
            }
            group.leave()
        }
    }
    try expect(group.wait(timeout: .now() + 120) == .success, "timeout")
    try expect(successes == 20 && area.pendingRequests().count == 20, "successes=\(successes)")
    let extra = dirs.src.appendingPathComponent("extra.epub"); put(extra, [1])
    try expect(try failed(stage(area, extra)) == .tooManyPending, "21st")
}

run("reopen-recovers-committed-requests-and-recounts-caps") {
    let dirs = scratch()
    let first = makeArea(dirs.stage)
    var staged: [FileEntryRequest] = []
    let origins: [FileEntryRequest.Origin] = [.picker, .inbox, .other]
    for index in 0..<3 {
        let url = dirs.src.appendingPathComponent("r\(index).epub"); put(url, pattern(1000 + index * chunk, seed: UInt64(100 + index)))
        staged.append(try succeeded(stage(first, url, origin: origins[index])))
    }
    let reopened = makeArea(dirs.stage, maxRequests: 3)
    let sortById: (FileEntryRequest, FileEntryRequest) -> Bool = { $0.id < $1.id }
    try expect(reopened.pendingRequests(verifyContents: true).sorted(by: sortById) == staged.sorted(by: sortById), "requests differ")
    let extra = dirs.src.appendingPathComponent("extra.epub"); put(extra, [1])
    try expect(try failed(stage(reopened, extra)) == .tooManyPending, "caps not recounted")
}

run("orphans-swept-and-foreign-files-kept") {
    let dirs = scratch()
    let area = makeArea(dirs.stage)
    let source = dirs.src.appendingPathComponent("keep.epub"); put(source, pattern(64, seed: 107))
    let kept = try succeeded(stage(area, source))
    let ids = [UUID().uuidString.lowercased(), UUID().uuidString.lowercased(), UUID().uuidString.lowercased()]
    put(dirs.stage.appendingPathComponent(".tmp-\(ids[0]).data"), [1, 2, 3])
    put(dirs.stage.appendingPathComponent("\(ids[1]).data"), [4, 5, 6])
    try! Data("{\"version\":1}".utf8).write(to: dirs.stage.appendingPathComponent("\(ids[2]).json"))
    for foreign in ["keep.txt", "notes.json", ".tmp-foo.data"] { put(dirs.stage.appendingPathComponent(foreign), [9]) }
    try expect(area.sweepOrphans() == 3, "removed count")
    let expected = Set([kept.id + ".data", kept.id + ".json", "keep.txt", "notes.json", ".tmp-foo.data"])
    try expect(Set(entries(dirs.stage)) == expected, "left \(entries(dirs.stage))")
    try expect(area.pendingRequests().count == 1, "committed lost")
}

run("tampered-or-shortened-staging-detected-on-reopen") {
    let dirs = scratch()
    let area = makeArea(dirs.stage)
    var requests: [FileEntryRequest] = []
    for index in 0..<3 {
        let url = dirs.src.appendingPathComponent("t\(index).epub"); put(url, pattern(2000, seed: UInt64(120 + index)))
        requests.append(try succeeded(stage(area, url)))
    }
    var flipped = bytes(requests[0].stagedPath); flipped[5] ^= 0xFF
    try flipped.write(to: URL(fileURLWithPath: requests[0].stagedPath))
    truncate(requests[1].stagedPath, 10)
    let reopened = makeArea(dirs.stage)
    try expect(Set(reopened.pendingRequests().map { $0.id }) == Set([requests[0].id, requests[2].id]), "size check")
    try expect(reopened.pendingRequests(verifyContents: true).map { $0.id } == [requests[2].id], "digest check")
}

run("release-removes-only-its-own-staged-pair-and-is-idempotent") {
    let dirs = scratch()
    let one = makeArea(dirs.stage), other = makeArea(scratch().stage)
    let source = dirs.src.appendingPathComponent("rel.epub"); put(source, pattern(50, seed: 131))
    let kept = try succeeded(stage(one, source))
    other.release(kept)
    try expect(FileManager.default.fileExists(atPath: kept.stagedPath), "foreign area deleted it")
    one.release(kept); one.release(kept)
    try expect(entries(dirs.stage).isEmpty && one.pendingRequests().isEmpty, "not removed")
    try expect(FileManager.default.fileExists(atPath: source.path), "source removed")
}

run("staging-directory-private-and-excluded-from-backup") {
    let dirs = scratch()
    let area = makeArea(dirs.stage)
    let source = dirs.src.appendingPathComponent("perm.epub"); put(source, pattern(10, seed: 137))
    let request = try succeeded(stage(area, source))
    var info = stat()
    try expect(stat(dirs.stage.path, &info) == 0 && (info.st_mode & 0o777) == 0o700, "dir mode")
    for name in entries(dirs.stage) {
        try expect(stat(dirs.stage.appendingPathComponent(name).path, &info) == 0 && (info.st_mode & 0o777) == 0o600, "file mode \(name)")
    }
    let values = try dirs.stage.resourceValues(forKeys: [.isExcludedFromBackupKey])
    try expect(values.isExcludedFromBackup == true, "backup flag")
    try expect(request.stagedPath.hasPrefix(dirs.stage.path), "path")
}

run("inbox-candidates-filter-sort-cap-and-explicit-removal") {
    let dirs = scratch()
    let documents = dirs.src.appendingPathComponent("Documents", isDirectory: true)
    let inbox = documents.appendingPathComponent("Inbox", isDirectory: true)
    let sub = inbox.appendingPathComponent("sub", isDirectory: true)
    for folder in [documents, inbox, sub, documents.appendingPathComponent("folder.epub", isDirectory: true)] {
        try! FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    }
    for (name, folder) in [("library.sqlite", documents), ("b.epub", documents), ("a.epub", documents), (".hidden.pdf", documents),
                           ("notes.xyz", documents), ("z.PDF", inbox), ("c.txt", inbox), ("d.epub", sub)] {
        put(folder.appendingPathComponent(name), pattern(40, seed: 141))
    }
    symlink(documents.appendingPathComponent("a.epub").path, documents.appendingPathComponent("link.epub").path)
    let names = FileEntryInbox.candidates(documentsDirectory: documents).map { $0.lastPathComponent }
    try expect(names == ["a.epub", "b.epub", "c.txt", "z.PDF"], "candidates \(names)")
    // Staging an Inbox file never removes it.
    let area = makeArea(dirs.stage)
    let request = try succeeded(stage(area, inbox.appendingPathComponent("c.txt"), origin: .inbox))
    try expect(request.origin == .inbox && FileManager.default.fileExists(atPath: inbox.appendingPathComponent("c.txt").path), "inbox file")
    try FileEntryInbox.removeOriginal(inbox.appendingPathComponent("c.txt"), documentsDirectory: documents)
    try expect(!FileManager.default.fileExists(atPath: inbox.appendingPathComponent("c.txt").path), "not removed")
    func refused(_ url: URL, _ expected: FileEntryInbox.RemovalError) throws {
        do {
            try FileEntryInbox.removeOriginal(url, documentsDirectory: documents)
            throw Fail(message: "removed \(url.lastPathComponent)")
        } catch let error as FileEntryInbox.RemovalError {
            try expect(error == expected, "error \(error) for \(url.lastPathComponent)")
        }
    }
    try refused(sub.appendingPathComponent("d.epub"), .notInbox)
    try refused(dirs.src.appendingPathComponent("outside.epub"), .notInbox)
    try refused(documents.appendingPathComponent("folder.epub"), .notRegularFile)
    try refused(documents.appendingPathComponent("link.epub"), .notRegularFile)
    try expect(FileManager.default.fileExists(atPath: documents.appendingPathComponent("a.epub").path), "target removed via link")
    let crowded = dirs.src.appendingPathComponent("Crowded", isDirectory: true)
    try! FileManager.default.createDirectory(at: crowded, withIntermediateDirectories: true)
    for index in 0..<(FileEntryLimits.maxInboxEntries + 4) { put(crowded.appendingPathComponent(String(format: "n%03d.txt", index)), [1]) }
    try expect(FileEntryInbox.candidates(documentsDirectory: crowded).count == FileEntryLimits.maxInboxEntries, "cap")
}

try! output.joined(separator: "\n").appending("\n").write(toFile: resultPath, atomically: true, encoding: .utf8)
let failures = output.filter { $0.contains(" fail ") }.count
print("probe finished checks=\(output.count) failures=\(failures)")
exit(failures == 0 ? 0 : 1)
