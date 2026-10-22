// SPDX-License-Identifier: MIT
// Local host bridge over the public C SDK (EXReader 3.40).
// The shared Swift binding stays read-only; this file adds library, anchor and
// fixed-page access that the reference host needs.
import Foundation
import CEXReader

enum HostError: Error, LocalizedError {
    case engine(code: Int, message: String)
    case cancelled
    case invalidInput(String)
    case invalidResult(String)

    var errorDescription: String? {
        switch self {
        case .engine(_, let message): return message.isEmpty ? "引擎错误" : message
        case .cancelled: return "操作已取消"
        case .invalidInput(let detail): return detail
        case .invalidResult(let detail): return detail
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
    func cancel() {
        lock.lock()
        cancelled = true
        lock.unlock()
    }
    var isCancelled: Bool {
        lock.lock()
        defer { lock.unlock() }
        return cancelled
    }
}

private func hostCancelledCallback(_ context: UnsafeMutableRawPointer?) -> Int32 {
    guard let context else { return 0 }
    let box = Unmanaged<HostCancelBox>.fromOpaque(context).takeUnretainedValue()
    return box.isCancelled ? 1 : 0
}

private func hostProgressCallback(_ context: UnsafeMutableRawPointer?, _ stage: exr_stage,
                                  _ completed: UInt64, _ total: UInt64) {
}

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

    init(library: HostLibrary, bookID: Int64) throws {
        var document: OpaquePointer?
        var error = exr_error()
        try hostCheck(exr_library_document(library.handle, bookID, &document, &error), error)
        guard let document else { throw HostError.invalidResult("书籍无法打开") }
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

    func resolve(_ anchor: HostAnchor) throws -> HostAnchorMatch {
        var match = exr_anchor_match()
        var error = exr_error()
        try hostCheck(exr_anchor_resolve(handle, &anchor.raw, &match, &error), error)
        let range: Range<Int>? = match.state == EXR_ANCHOR_FOUND ? Int(match.start)..<Int(match.end) : nil
        return HostAnchorMatch(state: match.state, range: range)
    }
}

final class HostPager {
    private let pager: OpaquePointer
    private let document: HostDocument
    private let font: HostFont
    private let box: HostCancelBox

    init(document: HostDocument, font: HostFont, width: Double, height: Double,
         fontSize: Double, box: HostCancelBox) throws {
        self.document = document
        self.font = font
        self.box = box
        var config = exr_layout_config_defaults()
        config.page.width = Float(width)
        config.page.height = Float(height)
        config.page.margin = 36
        config.page.font_size = Float(fontSize)
        config.document_css = 1
        config.embedded_fonts = 1
        var control = exr_control()
        control.context = Unmanaged.passUnretained(box).toOpaque()
        control.cancelled = hostCancelledCallback
        control.progress = hostProgressCallback
        config.control = control
        var result: OpaquePointer?
        var error = exr_error()
        try hostCheck(exr_pager_create(document.handle, font.handle, &config, &result, &error), error)
        guard let result else { throw HostError.invalidResult("分页器无法创建") }
        pager = result
    }

    deinit { exr_pager_free(pager) }

    func cancel() { box.cancel() }

    func pageRange(_ index: Int) throws -> Range<Int> {
        guard index >= 0 else { throw HostError.invalidInput("页码无效") }
        var layout: OpaquePointer?
        var error = exr_error()
        try hostCheck(exr_pager_get(pager, index, &layout, &error), error)
        guard let layout else { throw HostError.invalidResult("页面不存在") }
        var count = 0
        guard let pages = exr_layout_pages(layout, &count), count > 0 else {
            throw HostError.invalidResult("页面布局为空")
        }
        return Int(pages[0].start)..<Int(pages[0].end)
    }

    func render(_ index: Int) throws -> HostBitmap {
        var layout: OpaquePointer?
        var error = exr_error()
        try hostCheck(exr_pager_get(pager, index, &layout, &error), error)
        guard let layout else { throw HostError.invalidResult("页面不存在") }
        var bitmap = exr_bitmap()
        defer { exr_bitmap_free(&bitmap) }
        try hostCheck(exr_render_page_color(layout, exr_layout_font(layout), 0, &bitmap, &error), error)
        guard let pixels = bitmap.pixels, bitmap.width > 0, bitmap.height > 0 else {
            throw HostError.invalidResult("页面渲染失败")
        }
        let stride = Int(bitmap.stride), height = Int(bitmap.height)
        return HostBitmap(width: Int(bitmap.width), height: height, stride: stride,
                          channels: Int(bitmap.channels),
                          pixels: Data(bytes: pixels, count: stride * height))
    }

    func makeAnchor(start: Int, end: Int) throws -> HostAnchor {
        var anchor = exr_anchor()
        var error = exr_error()
        try hostCheck(exr_pager_anchor_create(pager, start, end, nil, &anchor, &error), error)
        return HostAnchor(adopting: anchor)
    }

    func resolve(_ anchor: HostAnchor) throws -> HostAnchorMatch {
        var match = exr_anchor_match()
        var error = exr_error()
        try hostCheck(exr_pager_anchor_resolve(pager, &anchor.raw, nil, &match, &error), error)
        let range: Range<Int>? = match.state == EXR_ANCHOR_FOUND ? Int(match.start)..<Int(match.end) : nil
        return HostAnchorMatch(state: match.state, range: range)
    }

    func pageIndex(for offset: Int) throws -> Int {
        guard offset > 0 else { return 0 }
        var low = 0
        var high = 1
        while high < 262144 {
            guard let range = try existingRange(high) else { break }
            if range.upperBound > offset { break }
            low = high
            high *= 2
        }
        while low < high {
            let middle = (low + high) / 2
            if let range = try existingRange(middle), range.upperBound <= offset {
                low = middle + 1
            } else {
                high = middle
            }
        }
        return low
    }

    private func existingRange(_ index: Int) throws -> Range<Int>? {
        do {
            return try pageRange(index)
        } catch HostError.cancelled {
            throw HostError.cancelled
        } catch {
            return nil
        }
    }
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

    init(library: HostLibrary, bookID: Int64, font: HostFont) throws {
        self.font = font
        var options = exr_fixed_open_options()
        options.struct_size = MemoryLayout<exr_fixed_open_options>.size
        options.fallback_font = font.handle
        var result: OpaquePointer?
        var error = exr_error()
        try hostCheck(exr_library_fixed(library.handle, bookID, &options, &result, &error), error)
        guard let result else { throw HostError.invalidResult("固定版面无法打开") }
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

    func text(page: Int) throws -> HostFixedPageText {
        try HostFixedPageText(fixed: self, page: page)
    }

    func render(page: Int, maximumDimension: Int) throws -> HostBitmap {
        guard page >= 0, page < geometries.count else { throw HostError.invalidInput("页码越界") }
        let geometry = geometries[page]
        let longest = max(geometry.width, geometry.height)
        let scale = longest > 0 ? min(1.0, Double(maximumDimension) / longest) : 1.0
        var bitmap = exr_bitmap()
        var error = exr_error()
        defer { exr_bitmap_free(&bitmap) }
        try hostCheck(exr_fixed_render(handle, page, scale, nil, &bitmap, &error), error)
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

    init(fixed: HostFixed, page: Int) throws {
        var text: OpaquePointer?
        var error = exr_error()
        try hostCheck(exr_fixed_load_text(fixed.handle, page, nil, &text, &error), error)
        guard let text else { throw HostError.invalidResult("页面文字无法读取") }
        handle = text
        var size = 0
        if let pointer = exr_fixed_text_string(text, &size), size > 0 {
            self.text = String(decoding: UnsafeRawBufferPointer(start: pointer, count: size), as: UTF8.self)
        } else {
            self.text = ""
        }
    }

    deinit { exr_fixed_text_free(handle) }

    func resolve(_ anchor: exr_fixed_anchor, pageID: String) throws -> HostAnchorMatch {
        var match = exr_anchor_match()
        var copy = anchor
        var error = exr_error()
        try pageID.withCString { pointer in
            try hostCheck(exr_fixed_anchor_resolve(pointer, handle, &copy, nil, &match, &error), error)
        }
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

struct HostNoteRow: Identifiable {
    let id: Int64
    let quote: String
    let comment: String
    let page: Int
    let start: Int
    let end: Int
    let state: String
    var isResolved: Bool { state == "精确" }
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

    func importUnique(file: URL, title: String) throws -> (id: Int64, created: Bool) {
        guard let format = HostLibrary.format(forExtension: file.pathExtension) else {
            throw HostError.invalidInput("不支持的格式：\(file.pathExtension)")
        }
        let data = try Data(contentsOf: file)
        guard !data.isEmpty, data.count <= 32 * 1024 * 1024 else {
            throw HostError.invalidInput("文件为空或超过 32 MiB")
        }
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

    func delete(bookID: Int64) throws {
        var error = exr_error()
        try hostCheck(exr_library_delete(handle, bookID, &error), error)
    }

    func document(bookID: Int64) throws -> HostDocument {
        try HostDocument(library: self, bookID: bookID)
    }

    func fixed(bookID: Int64, font: HostFont) throws -> HostFixed {
        try HostFixed(library: self, bookID: bookID, font: font)
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
        var raw = exr_book()
        raw.id = book.id
        raw.position = position
        raw.favorite = 0
        raw.status = 0
        var error = exr_error()
        try book.title.withCString { title in
            try book.author.withCString { author in
                try "".withCString { tags in
                    raw.title = UnsafeMutablePointer(mutating: title)
                    raw.author = UnsafeMutablePointer(mutating: author)
                    raw.tags = UnsafeMutablePointer(mutating: tags)
                    try hostCheck(exr_library_update(handle, &raw, &error), error)
                }
            }
        }
    }

    func addNote(bookID: Int64, start: Int, end: Int, text: String) throws -> Int64 {
        guard end >= start, !text.isEmpty else { throw HostError.invalidInput("标注内容为空") }
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
        var error = exr_error()
        try text.withCString { pointer in
            try hostCheck(exr_library_note_text(handle, noteID, pointer, &error), error)
        }
    }

    func removeNote(noteID: Int64) throws {
        var error = exr_error()
        try hostCheck(exr_library_remove_note(handle, noteID, &error), error)
    }

    func reflowNotes(bookID: Int64, document: HostDocument) throws -> [HostNoteRow] {
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
            let status = exr_anchor_resolve(document.handle, &anchor, &match, &resolveError)
            let state: String
            if status != EXR_OK {
                state = "未找到"
            } else if match.state == EXR_ANCHOR_FOUND {
                state = "精确"
            } else if match.state == EXR_ANCHOR_AMBIGUOUS {
                state = "歧义"
            } else if match.state == EXR_ANCHOR_LEGACY {
                state = "旧式"
            } else {
                state = "未找到"
            }
            let resolvedStart = match.state == EXR_ANCHOR_FOUND ? Int(match.start) : Int.max
            rows.append(HostNoteRow(id: note.id, quote: hostString(note.anchor.exact),
                                    comment: hostString(note.text), page: -1,
                                    start: resolvedStart, end: Int(match.end), state: state))
        }
        return rows
    }

    func addFixedNote(bookID: Int64, page: Int, start: Int, end: Int, text: String) throws -> Int64 {
        guard end >= start, !text.isEmpty else { throw HostError.invalidInput("标注内容为空") }
        var note = exr_fixed_note()
        note.book_id = bookID
        note.page = page
        note.start = start
        note.end = end
        var noteID: Int64 = 0
        var error = exr_error()
        try text.withCString { pointer in
            note.text = UnsafeMutablePointer(mutating: pointer)
            try hostCheck(exr_library_fixed_note(handle, &note, nil, &noteID, &error), error)
        }
        return noteID
    }

    func removeFixedNote(noteID: Int64) throws {
        var error = exr_error()
        try hostCheck(exr_library_remove_fixed_note(handle, noteID, &error), error)
    }

    func fixedNotes(bookID: Int64, fixed: HostFixed) throws -> [HostNoteRow] {
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
            if let text = try? fixed.text(page: Int(note.page)) {
                let pageID = (try? fixed.pageID(Int(note.page))) ?? ""
                if let match = try? text.resolve(note.anchor, pageID: pageID) {
                    state = match.label
                    if let range = match.range {
                        start = range.lowerBound
                        end = range.upperBound
                    }
                }
            }
            rows.append(HostNoteRow(id: note.id, quote: hostString(note.anchor.exact),
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