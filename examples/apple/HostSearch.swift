// SPDX-License-Identifier: MIT
import Foundation
import Combine
import CEXReader
import CReaderProduct

// Only copied values cross owner-queue invocations. F1 handles and captures
// are created, consumed and released on one actual OS thread within batch().
struct HostSearchAnchor: Codable, Equatable {
    let start: Int
    let end: Int
    let fields: [Data?]

    init(_ raw: exr_anchor) {
        start = raw.start; end = raw.end
        fields = [raw.exact, raw.prefix, raw.suffix, raw.chapter].map {
            $0.map { Data(String(cString: $0).utf8) }
        }
    }

    func withInput<T>(_ body: (exr_anchor) throws -> T) rethrows -> T {
        try hostSearchBuffers(fields) { pointers in
            var raw = exr_anchor()
            raw.start = start; raw.end = end
            raw.exact = pointers[0]; raw.prefix = pointers[1]
            raw.suffix = pointers[2]; raw.chapter = pointers[3]
            return try body(raw)
        }
    }
}

private func hostSearchBuffers<T>(_ values: [Data?], _ body: ([UnsafeMutablePointer<CChar>?]) throws -> T) rethrows -> T {
    let buffers: [UnsafeMutablePointer<CChar>?] = values.map { value in
        guard let value else { return nil }
        let pointer = UnsafeMutablePointer<CChar>.allocate(capacity: value.count + 1)
        value.withUnsafeBytes { bytes in
            if let source = bytes.baseAddress { UnsafeMutableRawPointer(pointer).copyMemory(from: source, byteCount: bytes.count) }
        }
        pointer[value.count] = 0
        return pointer
    }
    defer { for buffer in buffers { buffer?.deallocate() } }
    return try body(buffers)
}

struct HostSearchFixedAnchor: Codable, Equatable {
    let start: Int
    let end: Int
    let fields: [Data?]

    init(_ raw: exr_fixed_anchor) throws {
        start = raw.start; end = raw.end
        let lengths = [raw.exact_size, raw.prefix_size, raw.suffix_size]
        let pointers = [raw.exact, raw.prefix, raw.suffix]
        var values: [Data?] = [raw.page_id.map { Data(String(cString: $0).utf8) }]
        for (pointer, length) in zip(pointers, lengths) {
            guard length <= 8192, length == 0 || pointer != nil else { throw HostError.invalidResult("搜索选择器长度无效") }
            values.append(pointer.map { Data(bytes: $0, count: length) })
        }
        fields = values
    }

    func withInput<T>(_ body: (exr_fixed_anchor) throws -> T) rethrows -> T {
        try hostSearchBuffers(fields) { pointers in
            var raw = exr_fixed_anchor()
            raw.start = start; raw.end = end; raw.page_id = pointers[0]
            raw.exact = pointers[1]; raw.prefix = pointers[2]; raw.suffix = pointers[3]
            raw.exact_size = fields[1]?.count ?? 0
            raw.prefix_size = fields[2]?.count ?? 0
            raw.suffix_size = fields[3]?.count ?? 0
            return try body(raw)
        }
    }
}

struct HostSearchHit: Identifiable {
    let mode: reader_search_mode
    let unit: Int
    let path: String
    let pageID: String
    let pageLabel: String
    let sourceKey: String
    let bookID: Int64
    let anchor: HostSearchAnchor
    let fixed: HostSearchFixedAnchor
    var id: String { "\(mode.rawValue):\(unit):\(mode == READER_SEARCH_FIXED ? fixed.start : anchor.start)" }
    var quote: String {
        let value = mode == READER_SEARCH_FIXED ? fixed.fields[1] : anchor.fields[0]
        return value.map { String(decoding: $0, as: UTF8.self) } ?? ""
    }
    var detail: String {
        mode == READER_SEARCH_EPUB ? "第 \(unit + 1) 章" :
            mode == READER_SEARCH_FIXED ? (pageLabel.isEmpty ? "第 \(unit + 1) 页" : pageLabel) : "正文"
    }
}

struct HostSearchBatch {
    let hits: [HostSearchHit]
    let next: reader_search_cursor
    let complete: Bool
}

extension HostSourceFingerprint {
    var searchKey: String { "exr3.40.0:projection1:\(format):\(sha256):\(bytes)" }
}

private func hostSearchCheck(_ status: reader_search_status, _ error: reader_search_error) throws {
    if status == READER_SEARCH_OK { return }
    if status == READER_SEARCH_CANCELLED { throw HostError.cancelled }
    var copy = error
    let message = withUnsafePointer(to: &copy.message) {
        $0.withMemoryRebound(to: CChar.self, capacity: 160) { String(cString: $0) }
    }
    throw HostError.invalidResult(message.isEmpty ? "书内搜索失败" : message)
}

enum HostSearchWorker {
#if EXR_APPLE_HOST_REVIEW
    static var reviewInsideNext = false
#endif
    static func batch(library: HostLibrary, font: HostFont, bookID: Int64, sourceKey: String,
                      query: String, resume: reader_search_cursor?, cancel: HostCancelBox) throws -> HostSearchBatch {
        try cancel.check()
        guard !query.isEmpty, query.utf8.count <= 4096, !query.utf8.contains(0),
              !sourceKey.isEmpty, sourceKey.utf8.count <= 255,
              let book = try library.books().first(where: { $0.id == bookID }) else {
            throw HostError.invalidInput("查询或书籍身份无效")
        }
        var options = reader_search_options()
        options.struct_size = MemoryLayout<reader_search_options>.size
        options.control = hostControl(cancel)
        var cursor = resume ?? reader_search_cursor()
        return try sourceKey.withCString { key in
            options.source_key = key
            return try withUnsafePointer(to: &cursor) { pointer in
                options.resume = resume == nil ? nil : pointer
                return try query.withCString { queryBytes in
                    var search: OpaquePointer?, error = reader_search_error()
                    var reflow: OpaquePointer?
                    var publication: HostPublication?
                    var fixed: HostFixed?
                    defer { if let reflow { exr_document_free(reflow) } }
                    let status: reader_search_status
                    if book.isFixed {
                        fixed = try library.fixed(bookID: bookID, font: font, cancel: cancel)
                        status = reader_search_open_fixed(fixed!.handle, queryBytes, query.utf8.count, &options, &search, &error)
                    } else if try library.isBoundedEPUB(book: book) {
                        publication = try HostPublication(library: library, bookID: bookID, cancel: cancel)
                        var layout = exr_layout_config_defaults()
                        layout.control = hostControl(cancel)
                        var chapter = exr_chapter_options_defaults()
                        chapter.workspace_budget = 16 * 1024 * 1024; chapter.window_bytes = 16384
                        status = reader_search_open_epub(publication!.handle, font.handle, &layout, &chapter,
                                                        queryBytes, query.utf8.count, &options, &search, &error)
                    } else {
                        var sdkError = exr_error()
                        try hostCheck(exr_library_document(library.handle, bookID, &reflow, &sdkError), sdkError)
                        status = reader_search_open_reflow(reflow, queryBytes, query.utf8.count, &options, &search, &error)
                    }
                    try hostSearchCheck(status, error)
                    guard search != nil else { throw HostError.invalidResult("搜索句柄缺失") }
                    return try withExtendedLifetime((publication, fixed)) {
                        defer { _ = reader_search_close(&search, nil) }
                        var result = reader_search_result()
#if EXR_APPLE_HOST_REVIEW
                        reviewInsideNext = true
                        defer { reviewInsideNext = false }
#endif
                        try hostSearchCheck(reader_search_next(search, 32, &result, &error), error)
                        defer { reader_search_result_free(&result) }
                        try cancel.check()
                        guard result.count <= 32, result.count == 0 || result.hits != nil,
                              result.count != 0 || result.complete != 0 else { throw HostError.invalidResult("搜索批次无效") }
                        var hits: [HostSearchHit] = []
                        for index in 0..<result.count {
                            let raw = result.hits![index]
                            guard raw.unit <= UInt64(Int.max) else { throw HostError.invalidResult("搜索单元越界") }
                            hits.append(HostSearchHit(mode: raw.mode, unit: Int(raw.unit), path: hostString(raw.part_path),
                                pageID: hostString(raw.page_id), pageLabel: hostString(raw.page_label), sourceKey: sourceKey,
                                bookID: bookID, anchor: HostSearchAnchor(raw.anchor), fixed: try HostSearchFixedAnchor(raw.fixed)))
                        }
                        return HostSearchBatch(hits: hits, next: result.next, complete: result.complete != 0)
                    }
                }
            }
        }
    }
}

final class HostSearchState: ObservableObject {
    @Published var query = ""
    @Published private(set) var rows: [HostSearchHit] = []
    @Published private(set) var running = false
    @Published private(set) var complete = false
    @Published private(set) var status = "输入文字，在本书中查找"
    private(set) var cursor: reader_search_cursor?
    private(set) var generation = 0
    private(set) var bookID: Int64?
    private(set) var sourceKey: String?
    private var cancelBox: HostCancelBox?

    func bind(bookID: Int64, query: String) {
        cancel(); self.bookID = bookID; self.query = query
        rows = []; cursor = nil; sourceKey = nil; complete = false
        status = "输入文字，在本书中查找"
    }
    func begin(restart: Bool) -> (Int, HostCancelBox) {
        cancel()
        if restart { rows = []; cursor = nil; sourceKey = nil; complete = false }
        let box = HostCancelBox(); cancelBox = box; running = true; status = "正在查找…"
        return (generation, box)
    }
    func accept(_ batch: HostSearchBatch, key: String, generation expected: Int) {
        guard expected == generation else { return }
        // An exact full final batch needs one empty EOF read. Keep its last
        // usable window; a first empty batch still starts with no rows.
        if !batch.hits.isEmpty || cursor == nil { rows = batch.hits }
        cursor = batch.next; sourceKey = key
        complete = batch.complete; running = false; cancelBox = nil
        status = rows.isEmpty && complete ? "没有匹配结果" : "本批 \(rows.count) 项\(complete ? " · 已查找完毕" : " · 还可继续查找")"
    }
    func fail(_ error: Error, generation expected: Int) {
        guard expected == generation else { return }
        running = false; cancelBox = nil; status = error.localizedDescription
    }
    func cancel() {
        cancelBox?.cancel(); cancelBox = nil; generation += 1
        if running { status = "已取消，可从上一批继续" }
        running = false
    }
    func queryChanged() { cancel(); rows = []; cursor = nil; sourceKey = nil; complete = false; status = "输入文字，在本书中查找" }
#if EXR_APPLE_HOST_REVIEW
    func reviewCancellationReady(generation expected: Int) {
        if generation == expected && running { status = "正在查找（可取消）" }
    }
#endif
    func invalidate() { cancel(); bookID = nil; sourceKey = nil; rows = []; cursor = nil; complete = false }
}
