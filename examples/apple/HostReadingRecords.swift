// SPDX-License-Identifier: MIT
import Foundation
import Combine
import CEXReader
import CReaderProduct
import Darwin

func hostReadingField<T>(_ input: T) -> String {
    var value = input
    return withUnsafePointer(to: &value) {
        $0.withMemoryRebound(to: CChar.self, capacity: MemoryLayout<T>.size) { String(cString: $0) }
    }
}

struct HostReadingCapture: Codable, Equatable {
    let mode: Int
    let part: Int
    let path: String
    let page: Int
    let anchor: HostSearchAnchor?
    let fixed: HostSearchFixedAnchor?

    func validate() throws {
        let fields = mode == 3 ? fixed?.fields : anchor?.fields
        let start = mode == 3 ? fixed?.start : anchor?.start
        let end = mode == 3 ? fixed?.end : anchor?.end
        guard (1...3).contains(mode), part >= 0, page >= 0, let fields, fields.count == 4,
              let start, let end, start >= 0, end >= start,
              fields.allSatisfy({ ($0?.count ?? 0) <= 65536 }),
              path.utf8.count <= 1024, !path.utf8.contains(0), mode != 2 || !path.isEmpty else {
            throw HostError.invalidInput("阅读记录位置无效")
        }
    }

    func withRaw<T>(_ operation: (reader_rs_capture) throws -> T) throws -> T {
        try validate()
        if mode == 3, let fixed {
            return try fixed.withInput { value in
                try withUnsafePointer(to: value) { pointer in
                    var input = reader_rs_capture(); input.mode = READER_RS_FIXED_PAGE
                    input.fixed = pointer; input.page = page
                    return try operation(input)
                }
            }
        }
        guard let anchor else { throw HostError.invalidInput("阅读记录选文缺失") }
        return try anchor.withInput { value in
            try path.withCString { path in
                try withUnsafePointer(to: value) { pointer in
                    var input = reader_rs_capture()
                    input.mode = mode == 2 ? READER_RS_EPUB_CHAPTER : READER_RS_REFLOW_GLOBAL
                    input.anchor = pointer; input.part_path = mode == 2 ? path : nil
                    return try operation(input)
                }
            }
        }
    }
}

struct HostReadingRequest: Codable {
    let version: Int
    let bookID: Int64
    let bookKey: String
    let revision: String
    let bootstrap: String
    let annotation: String
    let kind: Int
    let operation: Int
    let heads: [String]
    let parser: String
    let body: String
    let capture: HostReadingCapture?
    let mode: Int
    let format: String
    let sha256: String
    let bytes: Int64
    let title: String
    let author: String
    let sort: String
    let favorite: Int32

    var entityKind: String { kind == 1 ? "progress" : "annotation" }
    var entityKey: String { kind == 1 ? bookKey : bookKey + ":" + annotation }
    static func newID() -> String { UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased() }
    static func id(_ value: String) -> Bool {
        value.utf8.count == 32 && value.utf8.allSatisfy { (48...57).contains($0) || (97...102).contains($0) }
    }
    func validate() throws {
        guard version == 1, bookID > 0, Self.id(revision), Self.id(bootstrap),
              (1...4).contains(kind), (0...2).contains(operation), (1...3).contains(mode),
              kind == 1 ? annotation.isEmpty : Self.id(annotation),
              heads.count <= 32, Set(heads).count == heads.count, heads.allSatisfy(Self.id),
              bytes > 0, bookKey == format + ":" + sha256, sha256.utf8.count == 64,
              sha256.utf8.allSatisfy({ (48...57).contains($0) || (97...102).contains($0) }),
              HostReadingWorker.acceptsParser(parser), body.utf8.count <= 65536, !body.utf8.contains(0) else {
            throw HostError.invalidInput("待完成阅读记录无效；请显式放弃后重试")
        }
        if operation != 1 && kind != 4 {
            guard let capture, capture.mode == mode else { throw HostError.invalidInput("待完成记录位置缺失") }
            try capture.validate()
        }
    }
}

// One immutable request per account. The same lock covers all windows and a
// filesystem lock covers separate host processes. Only its own ID may clear it.
enum HostReadingRequests {
    private static let lock = NSRecursiveLock()
    static func withLock<T>(_ root: URL, _ operation: (URL) throws -> T) throws -> T {
        lock.lock(); defer { lock.unlock() }
        let folder = root.appendingPathComponent("reading-requests", isDirectory: true)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true,
                                               attributes: [.posixPermissions: 0o700])
        try FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: folder.path)
        let fd = open(folder.appendingPathComponent("owner.lock").path, O_CREAT | O_RDWR | O_NOFOLLOW, 0o600)
        guard fd >= 0 else { throw HostError.invalidResult("无法锁定待完成记录") }
        defer { _ = flock(fd, LOCK_UN); close(fd) }
        guard flock(fd, LOCK_EX) == 0 else { throw HostError.invalidResult("无法锁定待完成记录") }
        return try operation(folder.appendingPathComponent("request.json"))
    }
    static func read(_ file: URL) throws -> HostReadingRequest? {
        guard FileManager.default.fileExists(atPath: file.path) else { return nil }
        let fd = open(file.path, O_RDONLY | O_NOFOLLOW)
        guard fd >= 0 else { throw HostError.invalidInput("待完成记录无法读取") }
        let handle = FileHandle(fileDescriptor: fd, closeOnDealloc: true)
        defer { try? handle.close() }
        var info = stat()
        guard fstat(fd, &info) == 0, (info.st_mode & S_IFMT) == S_IFREG,
              info.st_size > 0, info.st_size <= 2 * 1024 * 1024 else { throw HostError.invalidInput("待完成记录文件无效") }
        let bytes = try handle.readToEnd() ?? Data()
        guard bytes.count == Int(info.st_size) else { throw HostError.invalidInput("待完成记录已变化") }
        let value = try JSONDecoder().decode(HostReadingRequest.self, from: bytes)
        try value.validate(); return value
    }
    static func save(_ request: HostReadingRequest, file: URL) throws {
        guard !FileManager.default.fileExists(atPath: file.path) else { throw HostError.invalidInput("请先重试或放弃上一项待完成记录") }
        try request.validate()
        let bytes = try JSONEncoder().encode(request)
        guard bytes.count <= 2 * 1024 * 1024 else { throw HostError.invalidInput("待完成记录超过上限") }
        let temporary = file.deletingLastPathComponent().appendingPathComponent(UUID().uuidString + ".tmp")
        let fd = open(temporary.path, O_CREAT | O_EXCL | O_WRONLY | O_NOFOLLOW, 0o600)
        guard fd >= 0 else { throw HostError.invalidResult("无法保存待完成记录") }
        let handle = FileHandle(fileDescriptor: fd, closeOnDealloc: true)
        defer { try? handle.close(); try? FileManager.default.removeItem(at: temporary) }
        try handle.write(contentsOf: bytes); try handle.synchronize()
        guard rename(temporary.path, file.path) == 0 else { throw HostError.invalidResult("待完成记录发布失败") }
        try syncDirectory(file.deletingLastPathComponent())
    }
    static func clear(_ revision: String, file: URL) throws {
        guard try read(file)?.revision == revision else { throw HostError.invalidInput("待完成记录已经变化") }
        guard unlink(file.path) == 0 else { throw HostError.invalidResult("记录已保存，待完成标记尚未清除") }
        try syncDirectory(file.deletingLastPathComponent())
    }
    private static func syncDirectory(_ folder: URL) throws {
        let fd = open(folder.path, O_RDONLY | O_NOFOLLOW)
        guard fd >= 0 else { throw HostError.invalidResult("待完成记录目录无法刷新") }
        defer { close(fd) }
        guard fsync(fd) == 0 else { throw HostError.invalidResult("待完成记录目录无法刷新") }
    }
}

private final class HostReadingHeads {
    var ids: [String] = []
}
private func hostReadingHead(_ context: UnsafeMutableRawPointer?, _ input: UnsafePointer<reader_revision_head>?) -> Int32 {
    guard let context, let input else { return 1 }
    let output = Unmanaged<HostReadingHeads>.fromOpaque(context).takeUnretainedValue()
    output.ids.append(hostReadingField(input.pointee.revision_id))
    return output.ids.count > 32 ? 1 : 0
}

struct HostReadingRow: Identifiable {
    let bookID: Int64
    let bookKey: String
    let annotation: String
    let entityKind: String
    let state: Int
    let kind: Int
    let revision: String
    let mode: Int
    let revisions: Int
    let heads: Int
    let missing: Int
    let requiresRestore: Bool
    let quote: String
    let body: String
    let hasLocation: Bool
    var id: String { entityKind + ":" + annotation }
    var safe: Bool { state == 1 }
    var deleted: Bool { kind == 4 }
    var label: String { entityKind == "progress" ? "阅读进度" : !safe ? "阅读记录" : deleted ? "已删除的记录" : kind == 1 ? "书签" : kind == 2 ? "高亮" : "批注" }
    var detail: String {
        if safe { return deleted ? "可查看保留版本并显式恢复" : body.isEmpty ? quote : body }
        return "保留 \(revisions) 个版本 · \(heads) 个分支\(missing > 0 ? " · 等待关联版本" : "")"
    }
}
struct HostReadingPage {
    let rows: [HostReadingRow]
    let next: reader_av_cursor
    let complete: Bool
}
struct HostReadingVersion: Identifiable {
    let revision: String
    let wire: Data
    let label: String
    var id: String { revision }
}
struct HostReadingHistory {
    let row: HostReadingRow
    let versions: [HostReadingVersion]
    let heads: [String]
}

enum HostReadingWorker {
    // Explicit upgrade/spelling policy for the canvas-only 3.41 candidate. This only
    // admits decoding: apply/resolution still independently verify the retained
    // original, graph and exact selector. Stored wire and retry parser tags are
    // never rewritten. Android's two known spellings are explicit; there is no
    // arbitrary prefix stripping. Other versions (including downgrade) stay refused.
    static func acceptsParser(_ recorded: String) -> Bool {
        let actual = String(cString: exr_version())
        if recorded == actual { return true }
        return actual == "3.41.0" &&
            ["3.40.0", "exreader-sdk-3.40.0", "exreader-sdk-3.41.0"].contains(recorded)
    }
#if EXR_APPLE_HOST_REVIEW
    static var afterDurableSave: (() throws -> Void)?
    static var afterCommit: (() throws -> Void)?
#endif
    static func fixedCapture(_ fixed: HostFixed, page: Int, start: Int, end: Int, cancel: HostCancelBox) throws -> HostReadingCapture {
        try cancel.check()
        let text = try fixed.text(page: page, cancel: cancel), id = try fixed.pageID(page)
        var raw = exr_fixed_anchor(), error = exr_error()
        try id.withCString { try hostCheck(exr_fixed_anchor_create($0, text.handle, start, end, &raw, &error), error) }
        defer { exr_fixed_anchor_free(&raw) }
        try cancel.check()
        return HostReadingCapture(mode: 3, part: 0, path: "", page: page, anchor: nil, fixed: try HostSearchFixedAnchor(raw, maximumBytes: 65536))
    }

    static func decoded(_ wire: Data, history: OpaquePointer) throws -> (capture: HostReadingCapture, version: UInt64, book: String, body: String) {
        var record = reader_rs_record(), error = reader_rs_error()
        let status = wire.withUnsafeBytes { reader_rs_decode(history, $0.baseAddress, $0.count, &record, &error) }
        guard status == READER_RS_OK else { throw HostError.invalidInput("阅读记录格式无法读取") }
        defer { reader_rs_record_free(&record) }
        guard record.has_location != 0, acceptsParser(hostReadingField(record.parser_version)),
              record.start <= UInt64(Int.max), record.end <= UInt64(Int.max), record.part <= UInt64(Int.max), record.page <= UInt64(Int.max) else {
            throw HostError.invalidInput("保留版本没有可解析位置")
        }
        let capture: HostReadingCapture
        if record.mode == READER_RS_FIXED_PAGE {
            var raw = exr_fixed_anchor(); raw.start = Int(record.start); raw.end = Int(record.end)
            raw.page_id = record.page_id; raw.exact = record.exact; raw.prefix = record.prefix; raw.suffix = record.suffix
            raw.exact_size = record.exact_size; raw.prefix_size = record.prefix_size; raw.suffix_size = record.suffix_size
            capture = HostReadingCapture(mode: 3, part: 0, path: "", page: Int(record.page), anchor: nil, fixed: try HostSearchFixedAnchor(raw, maximumBytes: 65536))
        } else {
            var raw = exr_anchor(); raw.start = Int(record.start); raw.end = Int(record.end)
            raw.exact = record.exact; raw.prefix = record.prefix; raw.suffix = record.suffix
            // EPUB stores this SDK chapter scope in its explicit part_path;
            // record.chapter is reserved for the reflow-global wire mode.
            raw.chapter = record.mode == READER_RS_EPUB_CHAPTER ? record.part_path : record.chapter
            capture = HostReadingCapture(mode: record.mode == READER_RS_EPUB_CHAPTER ? 2 : 1, part: Int(record.part),
                path: hostString(record.part_path), page: 0, anchor: HostSearchAnchor(raw), fixed: nil)
        }
        try capture.validate()
        return (capture, record.anchor_version, hostReadingField(record.book_key), hostString(record.note_text))
    }

    static func request(session: HostSession, catalog: HostCatalog, kind: Int, operation: Int,
                        annotation: String = "", mode: Int, capture: HostReadingCapture?, body: String,
                        observedHeads: [String]? = nil, cancel: HostCancelBox) throws -> HostReadingRequest {
        try cancel.check()
        guard let sdkBook = session.book else { throw HostError.invalidInput("请先打开书籍") }
        let book = try catalog.readingBook(sdkID: sdkBook.id)
        let actual = try session.library.sourceFingerprint(book: sdkBook, cancel: cancel)
        guard actual.format == book.format, actual.sha256 == book.sha256, actual.bytes == book.bytes else { throw HostError.invalidInput("当前原件映射已变化") }
        let annotation = kind == 1 ? "" : annotation.isEmpty ? HostReadingRequest.newID() : annotation
        let heads = try observedHeads ?? catalog.withHistory { history in
            try self.heads(history, kind: kind == 1 ? "progress" : "annotation", key: kind == 1 ? book.key : book.key + ":" + annotation)
        }
        let value = HostReadingRequest(version: 1, bookID: sdkBook.id, bookKey: book.key, revision: HostReadingRequest.newID(),
            bootstrap: HostReadingRequest.newID(), annotation: annotation, kind: kind, operation: operation,
            heads: heads, parser: String(cString: exr_version()), body: body, capture: capture, mode: mode,
            format: book.format, sha256: book.sha256, bytes: book.bytes, title: book.title, author: book.author,
            sort: book.sort, favorite: book.favorite)
        try value.validate(); return value
    }

    static func heads(_ history: OpaquePointer, kind: String, key: String) throws -> [String] {
        let values = HostReadingHeads(); var graph = reader_revision_state(), error = reader_revision_error()
        let result = reader_revision_heads(history, kind, key, hostReadingHead,
            Unmanaged.passUnretained(values).toOpaque(), &graph, &error)
        guard result == READER_REV_OK, values.ids.count <= 32, values.ids.count == graph.heads,
              Set(values.ids).count == values.ids.count else { throw HostError.invalidInput("阅读记录分支过多或无法完整读取") }
        return values.ids.sorted()
    }

    static func retained(_ history: OpaquePointer, revision: String) throws -> (Data, reader_revision_info) {
        var wire: UnsafeMutablePointer<CChar>?, count = 0, info = reader_revision_info(), error = reader_revision_error()
        guard HostReadingRequest.id(revision), reader_revision_get(history, revision, &wire, &count, &info, &error) == READER_REV_OK,
              let wire, count > 0, count <= 1024 * 1024 else { throw HostError.invalidInput("保留版本无法读取") }
        defer { reader_revision_bytes_free(wire) }
        return (Data(bytes: wire, count: count), info)
    }

    static func apply(_ request: HostReadingRequest, session: HostSession, catalog: HostCatalog,
                      cancel: HostCancelBox) throws -> reader_rc_result {
        try request.validate(); try cancel.check()
        guard let book = session.book, book.id == request.bookID else { throw HostError.invalidInput("请先打开待完成记录对应的书籍") }
        let actual = try session.library.sourceFingerprint(book: book, cancel: cancel)
        guard actual.format == request.format, actual.sha256 == request.sha256, actual.bytes == request.bytes,
              try catalog.searchSourceKey(sdkID: book.id) == actual.searchKey else { throw HostError.invalidInput("阅读记录与当前原件不一致") }
        return try catalog.withHistory { history in
            var bookBytes: UInt64 = 0, bookError = reader_revision_error()
            let identity = reader_revision_book_identity(history, request.bookKey, &bookBytes, &bookError)
            if identity == READER_REV_NOT_FOUND {
                try hostProductStrings([request.bootstrap, request.bookKey, request.format, request.sha256,
                                        request.title, request.author, request.sort]) { strings in
                    var context = reader_command_context(); context.store = history; context.revision_id = strings[0]
                    var command = reader_book_command(); command.operation = READER_COMMAND_PUT
                    command.book_key = strings[1]; command.format = strings[2]; command.source_sha256 = strings[3]
                    command.title = strings[4]; command.author = strings[5]; command.sort_title = strings[6]
                    command.source_bytes = UInt64(request.bytes); command.favorite = request.favorite
                    var result = reader_command_result(), error = reader_command_error()
                    try cancel.commit {
                        guard reader_command_apply_book(&context, &command, &result, &error) == READER_COMMAND_OK else {
                            throw HostError.invalidInput("原件历史准备失败；待完成记录已保留")
                        }
                    }
                }
            } else if identity != READER_REV_OK || bookBytes != UInt64(request.bytes) {
                throw HostError.invalidInput("原件历史存在冲突，待完成记录已保留")
            }
            return try hostProductStrings([request.revision, request.parser, request.bookKey, request.annotation, request.body] + request.heads) { strings in
                let expected = Array(strings.dropFirst(5))
                return try expected.withUnsafeBufferPointer { buffer in
                    var context = reader_rc_context(); context.store = history; context.revision_id = strings[0]
                    context.parser_version = strings[1]; context.expected_heads = buffer.baseAddress; context.expected_count = buffer.count
                    var command = reader_rc_command()
                    command.kind = request.kind == 1 ? READER_RC_PROGRESS : request.kind == 2 ? READER_RC_BOOKMARK : request.kind == 3 ? READER_RC_HIGHLIGHT : READER_RC_NOTE_TEXT
                    command.operation = request.operation == 1 ? READER_RC_DELETE : request.operation == 2 ? READER_RC_RESTORE : READER_RC_PUT
                    command.book_key = strings[2]; command.annotation_id = request.kind == 1 ? nil : strings[3]
                    command.text = request.kind == 1 || request.operation == 1 ? nil : strings[4]
                    command.part = request.capture?.part ?? 0
                    func submit(_ capture: reader_rs_capture?) throws -> reader_rc_result {
                        var result = reader_rc_result(), error = reader_rc_error()
                        func commit() throws -> reader_rc_result {
                            try cancel.commit {
                                guard reader_rc_apply(&context, &command, &result, &error) == READER_RC_OK else {
                                    throw HostError.invalidInput("阅读记录未提交；保留原请求，可重试或显式放弃")
                                }
                            }
                            return result
                        }
                        if let capture {
                            return try withUnsafePointer(to: capture) { pointer in command.capture = pointer; return try commit() }
                        }
                        var deleted = reader_rs_capture()
                        deleted.mode = request.mode == 3 ? READER_RS_FIXED_PAGE : request.mode == 2 ? READER_RS_EPUB_CHAPTER : READER_RS_REFLOW_GLOBAL
                        return try withUnsafePointer(to: &deleted) { pointer in command.capture = request.operation == 1 ? pointer : nil; return try commit() }
                    }
                    if let capture = request.capture, request.kind != 4, request.operation != 1 { return try capture.withRaw { try submit($0) } }
                    return try submit(nil)
                }
            }
        }
    }

    static func submit(_ request: HostReadingRequest, session: HostSession, catalog: HostCatalog,
                       root: URL, cancel: HostCancelBox) throws -> reader_rc_result {
        try HostReadingRequests.withLock(root) { file in
            try cancel.check(); try HostReadingRequests.save(request, file: file)
#if EXR_APPLE_HOST_REVIEW
            try afterDurableSave?()
#endif
            let result = try apply(request, session: session, catalog: catalog, cancel: cancel)
#if EXR_APPLE_HOST_REVIEW
            try afterCommit?()
#endif
            try HostReadingRequests.clear(request.revision, file: file)
            return result
        }
    }
    static func replay(session: HostSession, catalog: HostCatalog, root: URL, cancel: HostCancelBox) throws -> reader_rc_result {
        try HostReadingRequests.withLock(root) { file in
            guard let request = try HostReadingRequests.read(file) else { throw HostError.invalidInput("没有待完成记录") }
            let result = try apply(request, session: session, catalog: catalog, cancel: cancel)
            try HostReadingRequests.clear(request.revision, file: file)
            return result
        }
    }
    static func discard(root: URL, expected: String) throws {
        try HostReadingRequests.withLock(root) { file in try HostReadingRequests.clear(expected, file: file) }
    }
    static func pending(root: URL) throws -> HostReadingRequest? {
        try HostReadingRequests.withLock(root) { file in try HostReadingRequests.read(file) }
    }

    static func page(catalog: HostCatalog, bookID: Int64, bookKey: String,
                     from: reader_av_cursor?, cancel: HostCancelBox) throws -> HostReadingPage {
        try catalog.withHistory { history in
            try cancel.check()
            var options = reader_av_options(); options.struct_size = MemoryLayout<reader_av_options>.size
            options.max_page_bytes = 2 * 1024 * 1024
            options.cancel_context = Unmanaged.passUnretained(cancel).toOpaque()
            options.cancel = { context in context.map { Unmanaged<HostCancelBox>.fromOpaque($0).takeUnretainedValue().isCancelled ? 1 : 0 } ?? 1 }
            var view: OpaquePointer?, error = reader_av_error()
            guard reader_av_open(history, bookKey, &options, &view, &error) == READER_AV_OK else { throw HostError.invalidResult("阅读记录列表无法打开") }
            defer { _ = reader_av_close(&view, &error) }
            var cursor = from ?? reader_av_cursor()
            if from == nil { guard reader_av_cursor_start(view, 1, &cursor, &error) == READER_AV_OK else { throw HostError.invalidResult("阅读记录分页无法开始") } }
            var page = reader_av_page()
            guard reader_av_page_get(view, &cursor, 32, &page, &error) == READER_AV_OK else {
                try cancel.check(); throw HostError.invalidResult("阅读记录分页失败，保留上一批")
            }
            defer { reader_av_page_free(&page) }
            var rows: [HostReadingRow] = []
            for index in 0..<page.count {
                try cancel.check()
                guard let items = page.items else { throw HostError.invalidResult("阅读记录页缺失") }
                let value = items[index], safe = value.state == READER_AV_STATE_SAFE
                rows.append(HostReadingRow(bookID: bookID, bookKey: bookKey, annotation: hostReadingField(value.annotation_id),
                    entityKind: "annotation", state: Int(value.state.rawValue), kind: safe ? Int(value.kind.rawValue) : 0,
                    revision: safe ? hostReadingField(value.revision_id) : "", mode: safe ? Int(value.mode.rawValue) : 0,
                    revisions: value.revisions, heads: value.heads, missing: value.missing_parents + value.foreign_parents,
                    requiresRestore: value.requires_restore != 0, quote: safe && value.content_available != 0 ? hostString(value.exact) : "",
                    body: safe && value.content_available != 0 ? hostString(value.note_text) : "", hasLocation: safe && value.has_location != 0))
            }
            try cancel.check()
            return HostReadingPage(rows: rows, next: page.next, complete: page.complete != 0)
        }
    }

    static func selectedWire(catalog: HostCatalog, row: HostReadingRow) throws -> Data {
        try catalog.withHistory { history in
            var wire: UnsafeMutablePointer<CChar>?, count = 0, info = reader_revision_info()
            var selection = reader_revision_selection(), error = reader_revision_error()
            let key = row.entityKind == "progress" ? row.bookKey : row.bookKey + ":" + row.annotation
            let status = reader_revision_selected(history, row.entityKind, key, &wire, &count, &info, &selection, &error)
            defer { reader_revision_bytes_free(wire) }
            guard row.safe, status == READER_REV_OK, selection.kind == READER_SELECTION_SAFE,
                  hostReadingField(info.revision_id) == row.revision, let wire, count > 0 else {
                throw HostError.invalidInput("阅读记录已变化，请刷新后重试")
            }
            return Data(bytes: wire, count: count)
        }
    }

    static func progress(catalog: HostCatalog, bookID: Int64, bookKey: String) throws -> HostReadingRow? {
        try catalog.withHistory { history in
            var wire: UnsafeMutablePointer<CChar>?, count = 0, info = reader_revision_info()
            var selection = reader_revision_selection(), error = reader_revision_error()
            let status = reader_revision_selected(history, "progress", bookKey, &wire, &count, &info, &selection, &error)
            defer { reader_revision_bytes_free(wire) }
            if status == READER_REV_NOT_FOUND { return nil }
            guard status == READER_REV_OK || status == READER_REV_UNSAFE else { throw HostError.invalidInput("阅读进度记录无法读取") }
            let safe = status == READER_REV_OK && selection.kind == READER_SELECTION_SAFE
            let deleted = safe && hostReadingField(info.operation) == "delete"
            let decoded: (capture: HostReadingCapture, version: UInt64, book: String, body: String)?
            if safe && !deleted, let wire { decoded = try self.decoded(Data(bytes: wire, count: count), history: history) } else { decoded = nil }
            let graph = selection.graph
            return HostReadingRow(bookID: bookID, bookKey: bookKey, annotation: "", entityKind: "progress", state: safe ? 1 : 2,
                kind: deleted ? 4 : 1, revision: safe ? hostReadingField(info.revision_id) : "", mode: decoded?.capture.mode ?? 0,
                revisions: graph.revisions, heads: graph.heads, missing: graph.missing_parents + graph.foreign_parents,
                requiresRestore: graph.requires_restore != 0, quote: "", body: "", hasLocation: decoded != nil)
        }
    }

    static func history(catalog: HostCatalog, row: HostReadingRow) throws -> HostReadingHistory {
        try catalog.withHistory { history in
            let key = row.entityKind == "progress" ? row.bookKey : row.bookKey + ":" + row.annotation
            let observed = try heads(history, kind: row.entityKind, key: key)
            var pending = observed, seen = Set<String>()
            var totalBytes = 0, output: [HostReadingVersion] = []
            while !pending.isEmpty {
                let id = pending.removeFirst()
                if !seen.insert(id).inserted { continue }
                guard seen.count <= 128 else { throw HostError.invalidInput("保留版本超过本次查看上限") }
                let (wire, info) = try retained(history, revision: id)
                totalBytes += wire.count
                guard totalBytes <= 2 * 1024 * 1024, hostReadingField(info.book_key) == row.bookKey,
                      hostReadingField(info.entity_kind) == row.entityKind, hostReadingField(info.entity_key) == key,
                      let value = try JSONSerialization.jsonObject(with: wire) as? [String: Any],
                      let parents = value["parents"] as? [String], parents.count <= 32,
                      parents.allSatisfy(HostReadingRequest.id) else { throw HostError.invalidInput("保留版本身份或容量无效") }
                pending.append(contentsOf: parents)
                if hostReadingField(info.operation) != "delete" {
                    guard output.count < 32 else { throw HostError.invalidInput("可恢复版本超过本次查看上限") }
                    output.append(HostReadingVersion(revision: id, wire: wire, label: "保留版本 \(output.count + 1)"))
                }
            }
            return HostReadingHistory(row: row, versions: output, heads: observed)
        }
    }
}

final class HostReadingState: ObservableObject {
    @Published var rows: [HostReadingRow] = []
    @Published var versions: [HostReadingVersion] = []
    @Published var status = "本书的书签与标注"
    @Published var pending: HostReadingRequest?
    @Published var running = false
    @Published var complete = false
#if EXR_APPLE_HOST_REVIEW
    @Published var nativeBoundary = ""
#endif
    var cursor: reader_av_cursor?
    var generation = 0
    var bookID: Int64?
    var restoring: HostReadingRow?
    var restoreHeads: [String] = []
    func bind(_ id: Int64?) {
        generation += 1; bookID = id; rows = []; versions = []; cursor = nil
        restoring = nil; restoreHeads = []; pending = nil; complete = false; running = false
#if EXR_APPLE_HOST_REVIEW
        nativeBoundary = ""
#endif
    }
}
