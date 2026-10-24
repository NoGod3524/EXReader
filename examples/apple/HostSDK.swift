// SPDX-License-Identifier: MIT
// Local host bridge over the public C SDK (EXReader 3.40).
// The shared Swift binding stays read-only; this file adds library, anchor and
// fixed-page access that the reference host needs.
import Foundation
import CryptoKit
import CEXReader
import Darwin

enum HostError: Error, LocalizedError {
    case engine(code: Int, message: String)
    case cancelled
    case endOfDocument
    case invalidInput(String)
    case invalidResult(String)
    case importRepairPending(String)

    var errorDescription: String? {
        switch self {
        case .engine(_, let message): return message.isEmpty ? "引擎错误" : message
        case .cancelled: return "操作已取消"
        case .endOfDocument: return "已到文档末尾"
        case .invalidInput(let detail): return detail
        case .invalidResult(let detail): return detail
        case .importRepairPending(let detail): return "书籍已保存，产品索引待修复；重启后重试：\(detail)"
        }
    }

    var isCancelled: Bool {
        if case .cancelled = self { return true }
        return false
    }
}

@inline(__always) func hostCheck(_ status: exr_status, _ error: exr_error) throws {
    guard status != EXR_OK else { return }
    var copy = error
    let message = withUnsafePointer(to: &copy.message) { pointer in
        pointer.withMemoryRebound(to: CChar.self, capacity: 256) { String(cString: $0) }
    }
    if status == EXR_CANCELLED { throw HostError.cancelled }
    throw HostError.engine(code: Int(status.rawValue), message: message)
}

func hostString(_ pointer: UnsafePointer<CChar>?) -> String {
    guard let pointer else { return "" }
    return String(cString: pointer)
}

func hostString(_ pointer: UnsafeMutablePointer<CChar>?) -> String {
    guard let pointer else { return "" }
    return String(cString: pointer)
}

struct HostBitmap {
    let width: Int
    let height: Int
    let stride: Int
    let channels: Int
    let pixels: Data
}

final class HostCancelBox {
    private let lock = NSLock()
    private var cancelled = false
    private var committed = false
    private var committing = false
    func cancel() {
        lock.lock()
        if !committing && !committed { cancelled = true }
        lock.unlock()
    }
    var isCancelled: Bool {
        lock.lock()
        defer { lock.unlock() }
        return cancelled
    }

    func check() throws {
        if isCancelled { throw HostError.cancelled }
    }

    // Entering publication is the cancellation boundary. SQLite may wait for a
    // writer, so the UI's cancel/check must never wait for the publication body.
    func commit<T>(_ operation: () throws -> T) throws -> T {
        lock.lock()
        if cancelled { lock.unlock(); throw HostError.cancelled }
        if committing { lock.unlock(); throw HostError.invalidResult("操作正在提交，不能重入") }
        committing = true
        lock.unlock()
        do {
            let value = try operation()
            lock.lock()
            committing = false
            committed = true
            lock.unlock()
            return value
        } catch {
            lock.lock()
            committing = false
            lock.unlock()
            throw error
        }
    }
}

private func hostCancelledCallback(_ context: UnsafeMutableRawPointer?) -> Int32 {
    guard let context else { return 0 }
    let box = Unmanaged<HostCancelBox>.fromOpaque(context).takeUnretainedValue()
#if EXR_APPLE_HOST_REVIEW
    HostSDKReview.poll?(box)
#endif
    return box.isCancelled ? 1 : 0
}

private func hostProgressCallback(_ context: UnsafeMutableRawPointer?, _ stage: exr_stage,
                                  _ completed: UInt64, _ total: UInt64) {
}

func hostControl(_ box: HostCancelBox) -> exr_control {
    var control = exr_control()
    control.context = Unmanaged.passUnretained(box).toOpaque()
    control.cancelled = hostCancelledCallback
    control.progress = hostProgressCallback
    return control
}

#if EXR_APPLE_HOST_REVIEW
// Cloud-only observation gates: the ordinary host contains no review callbacks.
enum HostSDKReview {
    static var event: ((String) throws -> Void)?
    static var poll: ((HostCancelBox) -> Void)?
}
#endif

final class HostFont {
    let handle: OpaquePointer
    init(data: Data) throws {
        var font: OpaquePointer?
        var error = exr_error()
        var input = exr_font_input()
        let status = data.withUnsafeBytes { bytes -> exr_status in
            input.data = bytes.baseAddress
            input.size = bytes.count
            input.face_index = 0
            return exr_font_create_glyphs(&input, 1, &font, &error)
        }
        try hostCheck(status, error)
        guard let font else { throw HostError.invalidResult("字体无法创建") }
        handle = font
    }
    deinit { exr_font_free(handle) }
}

final class HostAnchor {
    var raw: exr_anchor
    init(adopting value: exr_anchor) {
        raw = value
    }
    deinit {
        exr_anchor_free(&raw)
    }
    var start: Int { raw.start }
    var end: Int { raw.end }
    var quote: String { hostString(raw.exact) }
    var hasQuote: Bool { raw.exact != nil }
    var isPoint: Bool { raw.start == raw.end }
}

// This owner is stable for the entire publication lifetime; each serial worker
// operation replaces only its active token, never a borrowed callback context.
private final class HostSourceControl {
    var active: HostCancelBox
    init(_ active: HostCancelBox) { self.active = active }
}
private func hostSourceCancelled(_ context: UnsafeMutableRawPointer?) -> Int32 {
    guard let context else { return 0 }
    return Unmanaged<HostSourceControl>.fromOpaque(context).takeUnretainedValue().active.isCancelled ? 1 : 0
}

struct HostPart { let index: Int; let path: String; let reading: Bool }
final class HostPublication {
    let handle: OpaquePointer
    let parts: [HostPart]
    private let library: HostLibrary
    private let controlOwner: HostSourceControl
    init(library: HostLibrary, bookID: Int64, cancel: HostCancelBox) throws {
        self.library = library
        let owner = HostSourceControl(cancel)
        controlOwner = owner
        var source = exr_source(), error = exr_error()
        try hostCheck(exr_library_source(library.handle, bookID, &source, &error), error)
        source.control.context = Unmanaged.passUnretained(owner).toOpaque()
        source.control.cancelled = hostSourceCancelled
        var result: OpaquePointer?
        let status = exr_publication_open_source(&source, &result, &error)
        if status != EXR_OK {
            source.release?(source.context)
            try hostCheck(status, error)
        }
        guard let result else {
            source.release?(source.context)
            throw HostError.invalidResult("EPUB 目录为空")
        }
        if cancel.isCancelled { exr_publication_free(result); throw HostError.cancelled }
        handle = result
        var count = 0
        if let rows = exr_publication_parts(result, &count) {
            parts = (0..<count).map { HostPart(index: $0, path: hostString(rows[$0].path), reading: rows[$0].in_reading_order != 0) }
        } else { parts = [] }
    }
    deinit { exr_publication_free(handle) }
    func bind(_ cancel: HostCancelBox) throws { try cancel.check(); controlOwner.active = cancel }
    func route(_ part: Int, path: String? = nil) throws -> HostPart {
        guard parts.indices.contains(part), parts[part].reading,
              path == nil || path == parts[part].path else { throw HostError.invalidInput("EPUB 章节路由无效") }
        return parts[part]
    }
}

final class HostEPUBLocation {
    private(set) var raw: exr_epub_location
    init(adopting raw: exr_epub_location) { self.raw = raw }
    deinit { exr_epub_location_free(&raw) }
    var part: Int { raw.part }
    var path: String { hostString(raw.path) }
}

private final class HostFileSource {
    let file: FileHandle
    let cancel: HostCancelBox
    var failure: Error?
    init(file: FileHandle, cancel: HostCancelBox) { self.file = file; self.cancel = cancel }
}
private func hostFileRead(_ context: UnsafeMutableRawPointer?, _ offset: UInt64,
                          _ buffer: UnsafeMutableRawPointer?, _ size: Int) -> Int {
    guard let context, let buffer else { return 0 }
    let owner = Unmanaged<HostFileSource>.fromOpaque(context).takeUnretainedValue()
    do {
        try owner.cancel.check()
        try owner.file.seek(toOffset: offset)
        let bytes = try owner.file.read(upToCount: min(size, 64 * 1024)) ?? Data()
        bytes.copyBytes(to: buffer.assumingMemoryBound(to: UInt8.self), count: bytes.count)
#if EXR_APPLE_HOST_REVIEW
        try HostSDKReview.event?("import-read")
#endif
        return bytes.count
    } catch { if owner.failure == nil { owner.failure = error }; return 0 }
}

private final class HostPageText {
    var data = Data()
    static let limit = 2 * 1024 * 1024
}
private func hostPageTextSink(_ context: UnsafeMutableRawPointer?, _ bytes: UnsafePointer<CChar>?,
                              _ size: Int, _ error: UnsafeMutablePointer<exr_error>?) -> exr_status {
    guard let context, let bytes else { return EXR_ARGUMENT }
    let owner = Unmanaged<HostPageText>.fromOpaque(context).takeUnretainedValue()
    guard size <= HostPageText.limit - owner.data.count else { return EXR_LIMIT }
    owner.data.append(UnsafeRawPointer(bytes).assumingMemoryBound(to: UInt8.self), count: size)
    return EXR_OK
}

struct HostAnchorMatch {
    let state: exr_anchor_state
    let range: Range<Int>?
    var label: String {
        switch state {
        case EXR_ANCHOR_FOUND: return "精确"
        case EXR_ANCHOR_AMBIGUOUS: return "歧义"
        case EXR_ANCHOR_LEGACY: return "旧式"
        default: return "未找到"
        }
    }
    var isFound: Bool { state == EXR_ANCHOR_FOUND }
}

final class HostDocument {
    let handle: OpaquePointer
    let text: Data
    let title: String

    init(library: HostLibrary, bookID: Int64, cancel: HostCancelBox? = nil) throws {
        try cancel?.check()
        var document: OpaquePointer?
        var error = exr_error()
        try hostCheck(exr_library_document(library.handle, bookID, &document, &error), error)
        guard let document else { throw HostError.invalidResult("书籍无法打开") }
        if cancel?.isCancelled == true {
            exr_document_free(document)
            throw HostError.cancelled
        }
        handle = document
        var size = 0
        if let pointer = exr_document_text(document, &size), size > 0 {
            text = Data(bytes: pointer, count: size)
        } else {
            text = Data()
        }
        title = hostString(exr_document_title(document))
    }

    deinit { exr_document_free(handle) }

    func resolve(_ anchor: HostAnchor, cancel: HostCancelBox? = nil) throws -> HostAnchorMatch {
        let active = cancel ?? HostCancelBox()
        try active.check()
        var match = exr_anchor_match()
        var error = exr_error()
        var control = hostControl(active)
        try hostCheck(exr_anchor_resolve_ex(handle, &anchor.raw, &control, &match, &error), error)
        try active.check()
        let range: Range<Int>? = match.state == EXR_ANCHOR_FOUND ? Int(match.start)..<Int(match.end) : nil
        return HostAnchorMatch(state: match.state, range: range)
    }

    func makeAnchor(start: Int, end: Int, cancel: HostCancelBox? = nil) throws -> HostAnchor {
        try cancel?.check()
        guard start >= 0, end >= start else { throw HostError.invalidInput("文字位置无效") }
        var anchor = exr_anchor()
        var error = exr_error()
        try hostCheck(exr_anchor_create(handle, start, end, &anchor, &error), error)
        if cancel?.isCancelled == true { exr_anchor_free(&anchor); throw HostError.cancelled }
        return HostAnchor(adopting: anchor)
    }
}

final class HostPager {
    private let pager: OpaquePointer
    private(set) var failure: String?
    private let document: HostDocument?
    private let publication: HostPublication?
    private let font: HostFont
    private var box: HostCancelBox

    init(document: HostDocument, font: HostFont, width: Double, height: Double,
         fontSize: Double, box: HostCancelBox) throws {
        self.document = document
        publication = nil
        self.font = font
        self.box = box
        let safeWidth = max(320.0, width)
        let safeHeight = max(480.0, height)
        var config = exr_layout_config_defaults()
        config.page.width = Float(safeWidth)
        config.page.height = Float(safeHeight)
        config.page.margin = 36
        config.page.font_size = Float(fontSize)
        config.document_css = 1
        config.embedded_fonts = 1
        try box.check()
        config.control = hostControl(box)
        var result: OpaquePointer?
        var error = exr_error()
        try hostCheck(exr_pager_create(document.handle, font.handle, &config, &result, &error), error)
        guard let result else { throw HostError.invalidResult("分页器无法创建") }
        if box.isCancelled {
            exr_pager_free(result)
            throw HostError.cancelled
        }
        pager = result
    }

    init(publication: HostPublication, part: Int, font: HostFont, width: Double, height: Double,
         fontSize: Double, box: HostCancelBox, windowBytes: Int = 16384) throws {
        document = nil; self.publication = publication; self.font = font; self.box = box
        _ = try publication.route(part)
        try publication.bind(box)
        var config = exr_layout_config_defaults()
        config.page.width = Float(max(320, width)); config.page.height = Float(max(480, height))
        config.page.margin = 36; config.page.font_size = Float(fontSize)
        config.document_css = 1; config.embedded_fonts = 1; config.control = hostControl(box)
        var options = exr_chapter_options_defaults()
        options.workspace_budget = 16 * 1024 * 1024; options.window_bytes = windowBytes
        var result: OpaquePointer?, error = exr_error()
        try hostCheck(exr_publication_pager_create(publication.handle, part, font.handle, &config, &options, &result, &error), error)
        guard let result else { throw HostError.invalidResult("有界章节无法创建") }
        if box.isCancelled { exr_pager_free(result); throw HostError.cancelled }
        do {
            try hostCheck(exr_pager_set_cache(result, 2, 8 * 1024 * 1024, &error), error)
            try hostCheck(exr_pager_set_checkpoints(result, 4, 2 * 1024 * 1024, 16, &error), error)
        } catch { exr_pager_free(result); throw error }
        pager = result
    }

    var extent: Int { document?.text.count ?? Int(exr_pager_chapter_statistics(pager).projection_bytes) }
    var statistics: exr_chapter_stats { exr_pager_chapter_statistics(pager) }

    func text(_ range: Range<Int>, cancel: HostCancelBox) throws -> String {
        if let document { return String(decoding: document.text[range], as: UTF8.self) }
        try bind(cancel)
        let owner = HostPageText()
        var error = exr_error(), control = hostControl(cancel)
        try hostCheck(exr_pager_read_text(pager, range.lowerBound, range.upperBound, hostPageTextSink,
                                        Unmanaged.passUnretained(owner).toOpaque(), &control, &error), error)
        try cancel.check()
        return String(decoding: owner.data, as: UTF8.self)
    }

    deinit { exr_pager_free(pager) }

    func cancel() { box.cancel() }

    private func bind(_ cancel: HostCancelBox?) throws {
        let active = cancel ?? HostCancelBox()
        try active.check()
        try publication?.bind(active)
        var control = hostControl(active)
        var error = exr_error()
        try hostCheck(exr_pager_set_control(pager, &control, &error), error)
        box = active // The pager borrows its callback context until the next bind/free.
        failure = nil
    }

    func pageRange(_ index: Int, cancel: HostCancelBox? = nil) throws -> Range<Int> {
        guard index >= 0 else { throw HostError.invalidInput("页码无效") }
        try bind(cancel)
        var layout: OpaquePointer?
        var error = exr_error()
        let status = exr_pager_get(pager, index, &layout, &error)
        try box.check() // Cache hits do not necessarily poll the SDK control.
        if status == EXR_ARGUMENT {
            do { try hostCheck(status, error) }
            catch HostError.engine(_, let message) where message == "Page index is outside the document" {
                throw HostError.endOfDocument
            }
        }
        record(status, error)
        try hostCheck(status, error)
        guard let layout else { throw HostError.invalidResult("页面不存在") }
        var count = 0
        guard let pages = exr_layout_pages(layout, &count), count > 0 else {
            throw HostError.invalidResult("页面布局为空")
        }
        return Int(pages[0].start)..<Int(pages[0].end)
    }

    func render(_ index: Int, cancel: HostCancelBox? = nil) throws -> HostBitmap {
        guard index >= 0 else { throw HostError.invalidInput("页码无效") }
        try bind(cancel)
        var layout: OpaquePointer?
        var error = exr_error()
        try hostCheck(exr_pager_get(pager, index, &layout, &error), error)
        guard let layout else { throw HostError.invalidResult("页面不存在") }
        var bitmap = exr_bitmap()
        defer { exr_bitmap_free(&bitmap) }
        var control = hostControl(box)
        try hostCheck(exr_render_page_ex(layout, exr_layout_font(layout), 0, 4, &control, &bitmap, &error), error)
        try box.check()
        guard let pixels = bitmap.pixels, bitmap.width > 0, bitmap.height > 0 else {
            throw HostError.invalidResult("页面渲染失败")
        }
        let stride = Int(bitmap.stride), height = Int(bitmap.height)
        return HostBitmap(width: Int(bitmap.width), height: height, stride: stride,
                          channels: Int(bitmap.channels),
                          pixels: Data(bytes: pixels, count: stride * height))
    }

    func makeAnchor(start: Int, end: Int, cancel: HostCancelBox? = nil) throws -> HostAnchor {
        try bind(cancel)
        // Snapshot pagers retain document selectors; bounded pagers use only
        // their chapter query entry points.
        if let document { return try document.makeAnchor(start: start, end: end, cancel: box) }
        var anchor = exr_anchor(), error = exr_error(), control = hostControl(box)
        try hostCheck(exr_pager_anchor_create(pager, start, end, &control, &anchor, &error), error)
        if box.isCancelled { exr_anchor_free(&anchor); throw HostError.cancelled }
        return HostAnchor(adopting: anchor)
    }

    func resolve(_ anchor: HostAnchor, cancel: HostCancelBox? = nil) throws -> HostAnchorMatch {
        try bind(cancel)
        if let document { return try document.resolve(anchor, cancel: box) }
        return try withExtendedLifetime(anchor) { try resolveRaw(anchor.raw) }
    }

    func resolveLocation(_ location: HostEPUBLocation, cancel: HostCancelBox) throws -> HostAnchorMatch {
        try bind(cancel)
        return try withExtendedLifetime(location) { try resolveRaw(location.raw.selector) }
    }
    private func resolveRaw(_ raw: exr_anchor) throws -> HostAnchorMatch {
        var anchor = raw, match = exr_anchor_match(), error = exr_error(), control = hostControl(box)
        try hostCheck(exr_pager_anchor_resolve(pager, &anchor, &control, &match, &error), error)
        try box.check()
        return HostAnchorMatch(state: match.state, range: match.state == EXR_ANCHOR_FOUND ? match.start..<match.end : nil)
    }

    func pageIndex(for offset: Int, cancel: HostCancelBox? = nil) throws -> Int {
        let textCount = extent
        guard offset >= 0, offset <= textCount else {
            throw HostError.invalidInput("文字位置越界")
        }
        let active = cancel ?? HostCancelBox()
        try active.check()
        let first = try pageRange(0, cancel: active)
        if first.contains(offset) || (offset == textCount && first.upperBound == offset) { return 0 }
        var low = 0
        var high = 1
        while high < 262144 {
            guard let range = try existingRange(high, cancel: active) else { break }
            if range.upperBound > offset || (offset == textCount && range.upperBound == offset) { break }
            low = high
            high *= 2
        }
        while low < high {
            let middle = (low + high) / 2
            if let range = try existingRange(middle, cancel: active),
               range.upperBound < offset || (range.upperBound == offset && offset != textCount) {
                low = middle + 1
            } else {
                high = middle
            }
        }
        let range = try pageRange(low, cancel: active)
        guard range.contains(offset) || (offset == textCount && range.upperBound == offset) else {
            throw HostError.invalidResult("未找到包含文字位置的页面")
        }
        return low
    }

    private func record(_ status: exr_status, _ error: exr_error) {
        guard status != EXR_OK, failure == nil else { return }
        var copy = error
        failure = withUnsafePointer(to: &copy.message) { pointer in
            pointer.withMemoryRebound(to: CChar.self, capacity: 256) { String(cString: $0) }
        }
    }

    func existingRange(_ index: Int, cancel: HostCancelBox? = nil) throws -> Range<Int>? {
        do {
            return try pageRange(index, cancel: cancel)
        } catch HostError.endOfDocument {
            return nil
        }
    }

#if EXR_APPLE_HOST_REVIEW
    func reviewCacheBudget(_ bytes: Int) throws {
        var error = exr_error()
        try hostCheck(exr_pager_set_cache(pager, 1, bytes, &error), error)
    }
#endif
}

struct HostFixedGeometry {
    let width: Double
    let height: Double
}

final class HostFixed {
    let handle: OpaquePointer
    private let font: HostFont
    private(set) var pageIDs: [String] = []
    private(set) var geometries: [HostFixedGeometry] = []

    init(library: HostLibrary, bookID: Int64, font: HostFont, cancel: HostCancelBox? = nil) throws {
        self.font = font
        let active = cancel ?? HostCancelBox()
        try active.check()
        var options = exr_fixed_open_options()
        options.struct_size = MemoryLayout<exr_fixed_open_options>.size
        options.fallback_font = font.handle
        options.control = hostControl(active)
        var result: OpaquePointer?
        var error = exr_error()
        try hostCheck(exr_library_fixed(library.handle, bookID, &options, &result, &error), error)
        guard let result else { throw HostError.invalidResult("固定版面无法打开") }
        if active.isCancelled { exr_fixed_free(result); throw HostError.cancelled }
        handle = result
        var count = 0
        guard let pages = exr_fixed_pages(result, &count) else { return }
        pageIDs = (0..<count).map { hostString(pages[$0].id) }
        geometries = (0..<count).map { index in
            let bounds = pages[index].geometry.bounds
            let unit = pages[index].geometry.unit_scale
            return HostFixedGeometry(width: (bounds.2 - bounds.0) * unit,
                                     height: (bounds.3 - bounds.1) * unit)
        }
    }

    deinit { exr_fixed_free(handle) }

    var pageCount: Int { pageIDs.count }

    func pageID(_ page: Int) throws -> String {
        guard page >= 0, page < pageIDs.count else { throw HostError.invalidInput("页码越界") }
        return pageIDs[page]
    }

    func text(page: Int, cancel: HostCancelBox? = nil) throws -> HostFixedPageText {
        try HostFixedPageText(fixed: self, page: page, cancel: cancel)
    }

    func render(page: Int, maximumDimension: Int, cancel: HostCancelBox? = nil) throws -> HostBitmap {
        guard page >= 0, page < geometries.count else { throw HostError.invalidInput("页码越界") }
        guard maximumDimension > 0, maximumDimension <= 4096 else {
            throw HostError.invalidInput("固定页面尺寸须在 1...4096 像素内")
        }
        let active = cancel ?? HostCancelBox()
        try active.check()
        let geometry = geometries[page]
        let longest = max(geometry.width, geometry.height)
        let scale = longest > 0 ? min(1.0, Double(maximumDimension) / longest) : 1.0
        var bitmap = exr_bitmap()
        var error = exr_error()
        defer { exr_bitmap_free(&bitmap) }
        var options = exr_fixed_render_options()
        options.channels = 4
        options.background = 0xffffffff
        options.control = hostControl(active)
        try hostCheck(exr_fixed_render(handle, page, scale, &options, &bitmap, &error), error)
        try active.check()
        guard let pixels = bitmap.pixels, bitmap.width > 0, bitmap.height > 0 else {
            throw HostError.invalidResult("固定页面渲染失败")
        }
        let stride = Int(bitmap.stride), height = Int(bitmap.height)
        return HostBitmap(width: Int(bitmap.width), height: height, stride: stride,
                          channels: Int(bitmap.channels),
                          pixels: Data(bytes: pixels, count: stride * height))
    }
}

final class HostFixedPageText {
    let handle: OpaquePointer
    let text: String

    init(fixed: HostFixed, page: Int, cancel: HostCancelBox? = nil) throws {
        let active = cancel ?? HostCancelBox()
        try active.check()
        var text: OpaquePointer?
        var error = exr_error()
        var control = hostControl(active)
        try hostCheck(exr_fixed_load_text(fixed.handle, page, &control, &text, &error), error)
        guard let text else { throw HostError.invalidResult("页面文字无法读取") }
        if active.isCancelled { exr_fixed_text_free(text); throw HostError.cancelled }
        handle = text
        var size = 0
        if let pointer = exr_fixed_text_string(text, &size), size > 0 {
            self.text = String(decoding: UnsafeRawBufferPointer(start: pointer, count: size), as: UTF8.self)
        } else {
            self.text = ""
        }
    }

    deinit { exr_fixed_text_free(handle) }

    func resolve(_ anchor: exr_fixed_anchor, pageID: String, cancel: HostCancelBox? = nil) throws -> HostAnchorMatch {
        let active = cancel ?? HostCancelBox()
        try active.check()
        var match = exr_anchor_match()
        var copy = anchor
        var error = exr_error()
        var control = hostControl(active)
        try pageID.withCString { pointer in
            try hostCheck(exr_fixed_anchor_resolve(pointer, handle, &copy, &control, &match, &error), error)
        }
        try active.check()
        let range: Range<Int>? = match.state == EXR_ANCHOR_FOUND ? Int(match.start)..<Int(match.end) : nil
        return HostAnchorMatch(state: match.state, range: range)
    }
}

struct HostBook {
    let id: Int64
    let format: Int32
    let title: String
    let author: String
    let position: Int
    var isFixed: Bool { format == Int32(EXR_PDF.rawValue) || format == Int32(EXR_CBZ.rawValue) }
    var formatLabel: String {
        switch format {
        case Int32(EXR_PDF.rawValue): return "PDF"
        case Int32(EXR_CBZ.rawValue): return "CBZ"
        case Int32(EXR_EPUB.rawValue): return "EPUB"
        case Int32(EXR_TXT.rawValue): return "TXT"
        case Int32(EXR_HTML.rawValue): return "HTML"
        case Int32(EXR_FB2.rawValue): return "FB2"
        case Int32(EXR_DOCX.rawValue): return "DOCX"
        case Int32(EXR_RTF.rawValue): return "RTF"
        case Int32(EXR_MOBI.rawValue): return "MOBI"
        default: return "文档"
        }
    }
}

struct HostSourceFingerprint: Equatable {
    let format: String
    let sha256: String
    let bytes: Int64
}

// A single bounded read of the external URL creates the stable, host-owned
// input used by every later SDK open (including PDF's path-based import).
final class HostImportCopy {
    let url: URL
    let fingerprint: HostSourceFingerprint
    private let folder: URL
    private var closed = false
    private static let leaseLock = NSLock()
    private static var activeFolders = Set<String>()

    private static func leaseKey(_ url: URL) -> String {
        url.standardizedFileURL.resolvingSymlinksInPath().path
    }

    static func discardInterrupted(in root: URL) throws {
        leaseLock.lock()
        defer { leaseLock.unlock() }
        guard FileManager.default.fileExists(atPath: root.path) else { return }
        for item in try FileManager.default.contentsOfDirectory(at: root, includingPropertiesForKeys: nil) {
            if !activeFolders.contains(leaseKey(item)) { try FileManager.default.removeItem(at: item) }
        }
    }

    init(file: URL, root: URL, cancel: HostCancelBox) throws {
        try cancel.check()
        guard let format = HostLibrary.format(forExtension: file.pathExtension) else {
            throw HostError.invalidInput("不支持的格式：\(file.pathExtension)")
        }
        let maximum = format == EXR_EPUB ? 128 * 1024 * 1024 : 32 * 1024 * 1024
        let privateFolder = root.appendingPathComponent(UUID().uuidString, isDirectory: true)
        let privateURL = privateFolder.appendingPathComponent("source." + file.pathExtension.lowercased())
        folder = privateFolder
        url = privateURL
        Self.leaseLock.lock()
        Self.activeFolders.insert(Self.leaseKey(privateFolder))
        Self.leaseLock.unlock()
        do {
            try FileManager.default.createDirectory(at: privateFolder, withIntermediateDirectories: true,
                                                    attributes: [.posixPermissions: 0o700])
            let input = try FileHandle(forReadingFrom: file)
            defer { try? input.close() }
            let advertised = try input.seekToEnd()
            guard advertised > 0, advertised <= UInt64(maximum) else {
                throw HostError.invalidInput(format == EXR_EPUB ? "EPUB 文件为空或超过 128 MiB" : "文件为空或超过 32 MiB")
            }
            try input.seek(toOffset: 0)
            guard FileManager.default.createFile(atPath: privateURL.path, contents: nil,
                                                  attributes: [.posixPermissions: 0o600]) else {
                throw HostError.invalidInput("无法创建私有导入副本")
            }
            let output = try FileHandle(forWritingTo: privateURL)
            defer { try? output.close() }
            var hash = SHA256(), total = 0
            while true {
                try cancel.check()
                let chunk = try input.read(upToCount: min(64 * 1024, maximum - total + 1)) ?? Data()
                if chunk.isEmpty { break }
                guard chunk.count <= maximum - total else { throw HostError.invalidInput("导入时文件超过格式上限") }
                try output.write(contentsOf: chunk)
                hash.update(data: chunk)
                total += chunk.count
#if EXR_APPLE_HOST_REVIEW
                try HostSDKReview.event?("private-copy-read")
#endif
            }
            guard total > 0, UInt64(total) == advertised else { throw HostError.invalidInput("导入时外部文件长度改变") }
            try output.close()
            try cancel.check()
            fingerprint = HostSourceFingerprint(format: format == EXR_HTML ? "html" : file.pathExtension.lowercased(),
                sha256: hash.finalize().map { String(format: "%02x", $0) }.joined(), bytes: Int64(total))
#if EXR_APPLE_HOST_REVIEW
            try HostSDKReview.event?("private-copy-complete")
#endif
        } catch {
            Self.leaseLock.lock()
            defer {
                Self.activeFolders.remove(Self.leaseKey(privateFolder))
                Self.leaseLock.unlock()
            }
            do {
                if FileManager.default.fileExists(atPath: privateFolder.path) { try FileManager.default.removeItem(at: privateFolder) }
            } catch let cleanup {
                throw HostError.invalidResult("导入未提交，私有副本清理失败：\(cleanup.localizedDescription)；原错误：\(error.localizedDescription)")
            }
            throw error
        }
    }

    func close() throws {
        Self.leaseLock.lock()
        defer { Self.leaseLock.unlock() }
        if closed { return }
        if FileManager.default.fileExists(atPath: folder.path) { try FileManager.default.removeItem(at: folder) }
        Self.activeFolders.remove(Self.leaseKey(folder))
        closed = true
    }

    deinit {
        try? close()
        // Once the owner dies a failed remove becomes interrupted work, so
        // another model's next startup can retry it without retaining a lease.
        Self.leaseLock.lock()
        Self.activeFolders.remove(Self.leaseKey(folder))
        Self.leaseLock.unlock()
    }
}

struct HostNoteRow: Identifiable {
    let id: Int64
    let bookID: Int64
    let quote: String
    let comment: String
    let page: Int
    let start: Int
    let end: Int
    let state: String
    var location: HostEPUBLocation? = nil
    var isResolved: Bool { state == "精确" }
    var storage: String { location != nil ? "epub" : (page >= 0 ? "fixed" : "global") }
}

final class HostLibrary {
    let handle: OpaquePointer
    let path: URL

    init(path: URL) throws {
        self.path = path
        var library: OpaquePointer?
        var error = exr_error()
        try path.path.withCString { pointer in
            try hostCheck(exr_library_open(pointer, &library, &error), error)
        }
        guard let library else { throw HostError.invalidResult("书库无法打开") }
        handle = library
    }

    deinit { exr_library_close(handle) }

    static func format(forExtension ext: String) -> exr_format? {
        switch ext.lowercased() {
        case "epub": return EXR_EPUB
        case "pdf": return EXR_PDF
        case "cbz": return EXR_CBZ
        case "txt": return EXR_TXT
        case "html", "xhtml": return EXR_HTML
        case "fb2": return EXR_FB2
        case "docx": return EXR_DOCX
        case "rtf": return EXR_RTF
        case "mobi": return EXR_MOBI
        default: return nil
        }
    }

    func importUnique(file: URL, title: String, cancel: HostCancelBox? = nil) throws -> (id: Int64, created: Bool) {
        try cancel?.check()
        guard let format = HostLibrary.format(forExtension: file.pathExtension) else {
            throw HostError.invalidInput("不支持的格式：\(file.pathExtension)")
        }
        guard !title.utf8.contains(0) else { throw HostError.invalidInput("标题包含空字符") }
        let maximum = 32 * 1024 * 1024
        let input = try FileHandle(forReadingFrom: file)
        defer { try? input.close() }
        let size = try input.seekToEnd()
        if format == EXR_EPUB {
            guard size > 0, size <= 128 * 1024 * 1024 else { throw HostError.invalidInput("EPUB 文件为空或超过 128 MiB") }
            let active = cancel ?? HostCancelBox()
            let owner = HostFileSource(file: input, cancel: active)
            var source = exr_source(), id: Int64 = 0, created: Int32 = 0, error = exr_error()
            source.size = size; source.context = Unmanaged.passUnretained(owner).toOpaque()
            source.read_at = hostFileRead; source.control = hostControl(active)
            let status = withExtendedLifetime(owner) {
                title.withCString { exr_library_import_source_unique(handle, format, &source, $0, &id, &created, &error) }
            }
            if status != EXR_OK {
                if active.isCancelled { throw HostError.cancelled }
                if let failure = owner.failure { throw failure }
                try hostCheck(status, error)
            }
            do {
#if EXR_APPLE_HOST_REVIEW
                try HostSDKReview.event?("import-inserted")
#endif
                try active.check()
            } catch {
                if created != 0 {
                    do { try delete(bookID: id) }
                    catch { throw HostError.invalidResult("导入回滚失败；书库保留记录 \(id)：\(error.localizedDescription)") }
                }
                throw error
            }
            return (id, created != 0)
        }
        guard size > 0, size <= UInt64(maximum) else {
            throw HostError.invalidInput("文件为空或超过 32 MiB")
        }
        try input.seek(toOffset: 0)
        var data = Data()
        data.reserveCapacity(Int(size))
        while true {
            try cancel?.check()
            // One extra byte detects growth after the size check without reading
            // an unbounded file or trusting the original size as a stable identity.
            let chunk = try input.read(upToCount: min(64 * 1024, maximum - data.count + 1)) ?? Data()
            if chunk.isEmpty { break }
            guard chunk.count <= maximum - data.count else {
                throw HostError.invalidInput("文件超过 32 MiB")
            }
            data.append(chunk)
#if EXR_APPLE_HOST_REVIEW
            try HostSDKReview.event?("import-read")
#endif
        }
        guard !data.isEmpty else { throw HostError.invalidInput("文件为空") }
        try cancel?.check()
        var id: Int64 = 0
        var created: Int32 = 0
        var error = exr_error()
        try data.withUnsafeBytes { bytes in
            try title.withCString { name in
                try hostCheck(exr_library_import_unique(handle, format, bytes.baseAddress,
                                                        bytes.count, name, &id, &created, &error),
                              error)
            }
        }
        do {
#if EXR_APPLE_HOST_REVIEW
            try HostSDKReview.event?("import-inserted")
#endif
            try cancel?.check()
        } catch {
            // The public snapshot import has no control argument. Cancellation
            // during it is honored immediately on return; never delete a reused row.
            if created != 0 {
                do { try delete(bookID: id) }
                catch {
                    throw HostError.invalidResult("导入回滚失败；书库保留记录 \(id)：\(error.localizedDescription)")
                }
            }
            throw error
        }
        return (id, created != 0)
    }

    func books() throws -> [HostBook] {
        var list: UnsafeMutablePointer<exr_book>?
        var count = 0
        var error = exr_error()
        try hostCheck(exr_library_books(handle, nil, &list, &count, &error), error)
        defer { exr_books_free(list, count) }
        guard let list, count > 0 else { return [] }
        return (0..<count).map { index in
            let book = list[index]
            return HostBook(id: book.id, format: Int32(book.format.rawValue),
                            title: hostString(book.title), author: hostString(book.author),
                            position: Int(book.position))
        }
    }

    func sourceFingerprint(book: HostBook, cancel: HostCancelBox? = nil) throws -> HostSourceFingerprint {
        try cancel?.check()
        let format = book.formatLabel.lowercased()
        guard ["epub", "pdf", "cbz", "txt", "html", "fb2", "docx", "rtf", "mobi"].contains(format) else {
            throw HostError.invalidInput("产品书库不支持该原件格式")
        }
        var source = exr_source(), error = exr_error()
        try hostCheck(exr_library_source(handle, book.id, &source, &error), error)
        defer {
            source.release?(source.context)
#if EXR_APPLE_HOST_REVIEW
            try? HostSDKReview.event?("mapping-source-released")
#endif
        }
        guard source.size > 0, source.size <= UInt64(Int64.max), let read = source.read_at else {
            throw HostError.invalidResult("存储原件来源无效")
        }
        var buffer = [UInt8](repeating: 0, count: 64 * 1024), offset: UInt64 = 0
        var hash = SHA256()
        while offset < source.size {
            try cancel?.check()
            let request = Int(min(UInt64(buffer.count), source.size - offset))
            let received = buffer.withUnsafeMutableBytes { read(source.context, offset, $0.baseAddress, request) }
            guard received > 0, received <= request else { throw HostError.invalidResult("存储原件读取不完整") }
            hash.update(data: Data(buffer.prefix(received)))
            offset += UInt64(received)
#if EXR_APPLE_HOST_REVIEW
            try HostSDKReview.event?("mapping-source-read")
#endif
        }
        try cancel?.check()
        return HostSourceFingerprint(format: format,
            sha256: hash.finalize().map { String(format: "%02x", $0) }.joined(), bytes: Int64(offset))
    }

    // One bounded public source lease; no source or SDK handle enters the network worker.
    func exportSyncOriginal(_ book: HostProductBook, directory: URL, cancel: HostCancelBox) throws {
        guard book.bytes > 0, book.bytes <= 128 * 1024 * 1024,
              book.sha256.utf8.count == 64, book.sha256.utf8.allSatisfy({ (48...57).contains($0) || (97...102).contains($0) }),
              ["epub", "pdf", "cbz", "txt", "html", "fb2", "docx", "rtf", "mobi"].contains(book.format),
              book.key == book.format + ":" + book.sha256 else { throw HostError.invalidInput("同步原件身份无效") }
        try cancel.check()
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true,
                                                attributes: [.posixPermissions: 0o700])
        let attributes = try directory.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
        guard attributes.isDirectory == true, attributes.isSymbolicLink != true else { throw HostError.invalidInput("同步目录无效") }
        let temporary = directory.appendingPathComponent("." + UUID().uuidString + ".part")
        let descriptor = Darwin.open(temporary.path, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0o600)
        guard descriptor >= 0 else { throw HostError.invalidResult("无法创建同步原件副本") }
        let output = FileHandle(fileDescriptor: descriptor, closeOnDealloc: true)
        defer { try? output.close(); try? FileManager.default.removeItem(at: temporary) }
        var source = exr_source(), error = exr_error()
        try hostCheck(exr_library_source(handle, book.sdkID, &source, &error), error)
        defer { source.release?(source.context) }
        guard source.size == UInt64(book.bytes), let read = source.read_at else { throw HostError.invalidResult("SDK 原件长度与产品身份不一致") }
        var buffer = [UInt8](repeating: 0, count: 64 * 1024), offset: UInt64 = 0, hash = SHA256()
        while offset < source.size {
            try cancel.check()
            let request = Int(min(UInt64(buffer.count), source.size - offset))
            let received = buffer.withUnsafeMutableBytes { read(source.context, offset, $0.baseAddress, request) }
            guard received > 0, received <= request else { throw HostError.invalidResult("SDK 原件读取不完整") }
            let chunk = Data(buffer.prefix(received)); hash.update(data: chunk); try output.write(contentsOf: chunk)
            offset += UInt64(received)
        }
        guard hash.finalize().map({ String(format: "%02x", $0) }).joined() == book.sha256 else { throw HostError.invalidResult("SDK 原件摘要与产品身份不一致") }
        try output.synchronize(); try output.close(); try cancel.check()
        let destination = directory.appendingPathComponent(book.sha256 + "." + book.format)
        if FileManager.default.fileExists(atPath: destination.path) {
            let existingDescriptor = Darwin.open(destination.path, O_RDONLY | O_NOFOLLOW | O_CLOEXEC)
            guard existingDescriptor >= 0 else { throw HostError.invalidResult("已有同步副本无效") }
            let existing = FileHandle(fileDescriptor: existingDescriptor, closeOnDealloc: true)
            defer { try? existing.close() }
            var status = stat()
            guard fstat(existingDescriptor, &status) == 0, (Int32(status.st_mode) & S_IFMT) == S_IFREG,
                  status.st_size == book.bytes else { throw HostError.invalidResult("已有同步副本长度无效") }
            var total = 0, digest = SHA256()
            while Int64(total) < book.bytes {
                try cancel.check()
                let chunk = try existing.read(upToCount: Int(min(Int64(64 * 1024), book.bytes - Int64(total)))) ?? Data()
                guard !chunk.isEmpty else { throw HostError.invalidResult("已有同步副本读取不完整") }
                digest.update(data: chunk); total += chunk.count
            }
            guard digest.finalize().map({ String(format: "%02x", $0) }).joined() == book.sha256 else { throw HostError.invalidResult("已有同步副本摘要无效") }
        } else { try FileManager.default.moveItem(at: temporary, to: destination) }
    }

    func locationKind(book: HostBook) throws -> String {
        if book.isFixed { return "fixed_page" }
        return try isBoundedEPUB(book: book) ? "epub_chapter" : "reflow_global"
    }

    func delete(bookID: Int64) throws {
        var error = exr_error()
        try hostCheck(exr_library_delete(handle, bookID, &error), error)
    }

    func document(bookID: Int64, cancel: HostCancelBox? = nil) throws -> HostDocument {
        try HostDocument(library: self, bookID: bookID, cancel: cancel)
    }

    func isBoundedEPUB(book: HostBook) throws -> Bool {
        guard book.format == Int32(EXR_EPUB.rawValue) else { return false }
        var info = exr_library_epub_info(), error = exr_error()
        info.struct_size = MemoryLayout<exr_library_epub_info>.size
        try hostCheck(exr_library_epub_info_get(handle, book.id, &info, &error), error)
        return info.bounded_storage != 0
    }
    func epubProgress(bookID: Int64) throws -> HostEPUBLocation? {
        var location = exr_epub_location(), present: Int32 = 0, error = exr_error()
        try hostCheck(exr_library_epub_progress_get(handle, bookID, &location, &present, &error), error)
        guard present != 0 else { exr_epub_location_free(&location); return nil }
        return HostEPUBLocation(adopting: location)
    }
    func setEPUBProgress(bookID: Int64, part: Int, path: String, anchor: HostAnchor) throws {
        var location = exr_epub_location(), error = exr_error()
        location.part = part; location.selector = anchor.raw
        try withExtendedLifetime(anchor) {
            try path.withCString {
                location.path = UnsafeMutablePointer(mutating: $0)
                try hostCheck(exr_library_epub_progress(handle, bookID, &location, &error), error)
            }
        }
    }
    func addEPUBNote(bookID: Int64, part: Int, path: String, anchor: HostAnchor, text: String) throws {
        guard !text.utf8.contains(0) else { throw HostError.invalidInput("标注包含空字符") }
        var note = exr_epub_note(), result: Int64 = 0, error = exr_error()
        note.book_id = bookID; note.location.part = part; note.location.selector = anchor.raw
        try withExtendedLifetime(anchor) {
            try path.withCString { route in try text.withCString { comment in
                note.location.path = UnsafeMutablePointer(mutating: route); note.text = UnsafeMutablePointer(mutating: comment)
                try hostCheck(exr_library_epub_note(handle, &note, &result, &error), error)
            } }
        }
    }
    func updateEPUBNote(bookID: Int64, noteID: Int64, text: String) throws {
        guard !text.utf8.contains(0) else { throw HostError.invalidInput("标注包含空字符") }
        var note = exr_epub_note(), result: Int64 = 0, error = exr_error()
        note.id = noteID; note.book_id = bookID // exact=NULL is comment-only.
        try text.withCString {
            note.text = UnsafeMutablePointer(mutating: $0)
            try hostCheck(exr_library_epub_note(handle, &note, &result, &error), error)
        }
    }
    func removeEPUBNote(noteID: Int64) throws {
        var error = exr_error(); try hostCheck(exr_library_remove_epub_note(handle, noteID, &error), error)
    }
    func epubNotes(bookID: Int64, part: Int, pager: HostPager, cancel: HostCancelBox) throws -> [HostNoteRow] {
        var list: UnsafeMutablePointer<exr_epub_note>?, count = 0, error = exr_error()
        try hostCheck(exr_library_epub_notes(handle, bookID, &list, &count, &error), error)
        defer { exr_epub_notes_free(list, count) }
        guard let list else { return [] }
        var rows: [HostNoteRow] = []
        for i in 0..<count {
            try cancel.check()
            // Transfer this nested location into one owner, then clear the array
            // slot so notes_free cannot free the strings a second time.
            let location = HostEPUBLocation(adopting: list[i].location)
            list[i].location = exr_epub_location()
            let match: HostAnchorMatch?
            if location.part == part { match = try pager.resolveLocation(location, cancel: cancel) }
            else { match = nil }
            rows.append(HostNoteRow(id: list[i].id, bookID: list[i].book_id,
                                    quote: hostString(location.raw.selector.exact), comment: hostString(list[i].text),
                                    page: -1, start: match?.range?.lowerBound ?? Int.max,
                                    end: match?.range?.upperBound ?? Int.max,
                                    state: match?.label ?? "待定位", location: location))
        }
        return rows
    }

    func fixed(bookID: Int64, font: HostFont, cancel: HostCancelBox? = nil) throws -> HostFixed {
        try HostFixed(library: self, bookID: bookID, font: font, cancel: cancel)
    }

    func setProgress(bookID: Int64, anchor: HostAnchor) throws {
        var error = exr_error()
        try hostCheck(exr_library_progress(handle, bookID, &anchor.raw, &error), error)
    }

    func progress(bookID: Int64) throws -> (anchor: HostAnchor, state: exr_anchor_state) {
        var anchor = exr_anchor()
        var state = EXR_ANCHOR_MISSING
        var error = exr_error()
        try hostCheck(exr_library_progress_get(handle, bookID, &anchor, &state, &error), error)
        return (HostAnchor(adopting: anchor), state)
    }

    func updatePosition(book: HostBook, position: Int) throws {
        guard position >= 0 else { throw HostError.invalidInput("阅读位置无效") }
        var list: UnsafeMutablePointer<exr_book>?
        var count = 0
        var error = exr_error()
        try hostCheck(exr_library_books(handle, nil, &list, &count, &error), error)
        defer { exr_books_free(list, count) }
        guard let list, let index = (0..<count).first(where: { list[$0].id == book.id }) else {
            throw HostError.invalidInput("书籍不存在")
        }
        // Query-owned strings stay alive through update. The session's HostBook
        // is only an identity: its cached metadata must not overwrite newer edits.
        var raw = list[index]
        raw.position = position
        try hostCheck(exr_library_update(handle, &raw, &error), error)
    }

    func addNote(bookID: Int64, start: Int, end: Int, text: String) throws -> Int64 {
        guard start >= 0, end >= start, !text.isEmpty, !text.utf8.contains(0) else {
            throw HostError.invalidInput("标注范围或内容无效")
        }
        var note = exr_note()
        note.book_id = bookID
        note.start = start
        note.end = end
        var noteID: Int64 = 0
        var error = exr_error()
        try text.withCString { pointer in
            note.text = UnsafeMutablePointer(mutating: pointer)
            try hostCheck(exr_library_note(handle, &note, &noteID, &error), error)
        }
        return noteID
    }

    func updateNoteText(noteID: Int64, text: String) throws {
        guard !text.utf8.contains(0) else { throw HostError.invalidInput("标注包含空字符") }
        var error = exr_error()
        try text.withCString { pointer in
            try hostCheck(exr_library_note_text(handle, noteID, pointer, &error), error)
        }
    }

    func removeNote(noteID: Int64) throws {
        var error = exr_error()
        try hostCheck(exr_library_remove_note(handle, noteID, &error), error)
    }

    func reflowNotes(bookID: Int64, document: HostDocument, cancel: HostCancelBox? = nil) throws -> [HostNoteRow] {
        let active = cancel ?? HostCancelBox()
        try active.check()
        var list: UnsafeMutablePointer<exr_note>?
        var count = 0
        var error = exr_error()
        try hostCheck(exr_library_notes(handle, bookID, &list, &count, &error), error)
        defer { exr_notes_free(list, count) }
        guard let list, count > 0 else { return [] }
        var rows: [HostNoteRow] = []
        for index in 0..<count {
            let note = list[index]
            var match = exr_anchor_match()
            var anchor = note.anchor
            var resolveError = exr_error()
            var control = hostControl(active)
            try hostCheck(exr_anchor_resolve_ex(document.handle, &anchor, &control, &match, &resolveError), resolveError)
            try active.check()
            let state: String
            if match.state == EXR_ANCHOR_FOUND {
                state = "精确"
            } else if match.state == EXR_ANCHOR_AMBIGUOUS {
                state = "歧义"
            } else if match.state == EXR_ANCHOR_LEGACY {
                state = "旧式"
            } else {
                state = "未找到"
            }
            let resolvedStart = match.state == EXR_ANCHOR_FOUND ? Int(match.start) : Int.max
            rows.append(HostNoteRow(id: note.id, bookID: note.book_id, quote: hostString(note.anchor.exact),
                                    comment: hostString(note.text), page: -1,
                                    start: resolvedStart, end: Int(match.end), state: state))
        }
        return rows
    }

    func addFixedNote(bookID: Int64, page: Int, start: Int, end: Int, text: String,
                      cancel: HostCancelBox? = nil) throws -> Int64 {
        guard page >= 0, start >= 0, end >= start, !text.isEmpty, !text.utf8.contains(0) else {
            throw HostError.invalidInput("标注范围或内容无效")
        }
        let active = cancel ?? HostCancelBox()
        try active.check()
        var note = exr_fixed_note()
        note.book_id = bookID
        note.page = page
        note.start = start
        note.end = end
        var noteID: Int64 = 0
        var error = exr_error()
        var control = hostControl(active)
        try text.withCString { pointer in
            note.text = UnsafeMutablePointer(mutating: pointer)
            try hostCheck(exr_library_fixed_note(handle, &note, &control, &noteID, &error), error)
        }
        return noteID
    }

    func removeFixedNote(noteID: Int64) throws {
        var error = exr_error()
        try hostCheck(exr_library_remove_fixed_note(handle, noteID, &error), error)
    }

    func updateFixedNoteText(bookID: Int64, noteID: Int64, text: String,
                             cancel: HostCancelBox? = nil) throws {
        guard !text.utf8.contains(0) else { throw HostError.invalidInput("标注包含空字符") }
        let active = cancel ?? HostCancelBox()
        try active.check()
        var list: UnsafeMutablePointer<exr_fixed_note>?
        var count = 0
        var error = exr_error()
        try hostCheck(exr_library_fixed_notes(handle, bookID, &list, &count, &error), error)
        defer { exr_fixed_notes_free(list, count) }
        guard let list, let index = (0..<count).first(where: { list[$0].id == noteID }) else {
            throw HostError.invalidInput("标注不存在或不属于当前书籍")
        }
        var note = list[index]
        var id: Int64 = 0
        var control = hostControl(active)
        try text.withCString { pointer in
            note.text = UnsafeMutablePointer(mutating: pointer)
            try hostCheck(exr_library_fixed_note(handle, &note, &control, &id, &error), error)
        }
    }

    func fixedNotes(bookID: Int64, fixed: HostFixed, cancel: HostCancelBox? = nil) throws -> [HostNoteRow] {
        try cancel?.check()
        var list: UnsafeMutablePointer<exr_fixed_note>?
        var count = 0
        var error = exr_error()
        try hostCheck(exr_library_fixed_notes(handle, bookID, &list, &count, &error), error)
        defer { exr_fixed_notes_free(list, count) }
        guard let list, count > 0 else { return [] }
        var rows: [HostNoteRow] = []
        for index in 0..<count {
            let note = list[index]
            var state = "未找到"
            var start = Int.max
            var end = 0
            let text = try fixed.text(page: Int(note.page), cancel: cancel)
            let pageID = try fixed.pageID(Int(note.page))
            let match = try text.resolve(note.anchor, pageID: pageID, cancel: cancel)
            state = match.label
            if let range = match.range {
                start = range.lowerBound
                end = range.upperBound
            }
            rows.append(HostNoteRow(id: note.id, bookID: note.book_id, quote: hostString(note.anchor.exact),
                                    comment: hostString(note.text), page: Int(note.page),
                                    start: start, end: end, state: state))
        }
        return rows
    }

    func backup(to url: URL) throws {
        var error = exr_error()
        try url.path.withCString { pointer in
            try hostCheck(exr_library_backup(handle, pointer, &error), error)
        }
    }
}

let HOST_SDK_VERSION: String = String(cString: exr_version())
let HOST_ABI_VERSION: UInt32 = exr_abi_version()
