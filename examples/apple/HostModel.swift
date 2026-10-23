// SPDX-License-Identifier: MIT
import Foundation
import CoreGraphics
import CryptoKit
import CEXReader
import Combine

struct HostSelectionContext: Equatable {
    let bookID: Int64
    let frameCount: Int
    let baseOffset: Int
    let text: String
    var part: Int = -1
    var path: String = ""
}

#if EXR_APPLE_HOST_REVIEW
// The cloud consumer uses this boundary to change real SQLite schema before a
// real public-SDK query; the shipped application contains no review callbacks.
enum HostModelReviewGate {
    static var beforeFrameNotes: ((HostSession) throws -> Void)?
}
#endif

struct HostBookRow: Identifiable, Equatable {
    let id: Int64
    let title: String
    let detail: String
    let isFixed: Bool
    let position: Int
}

struct HostSnapshot {
    let book: HostBook
    let image: CGImage?
    let location: String
    let progress: String
    let pageText: String
    let pageIndex: Int
    let pageRange: Range<Int>
    let pageCount: Int?
    let fontSize: Int
    let pageAccessibilityLabel: String
    var part: Int = -1
    var path: String = ""
}

private func makeCGImage(_ bitmap: HostBitmap) -> CGImage? {
    guard bitmap.channels == 4, bitmap.width > 0, bitmap.height > 0,
          bitmap.stride >= bitmap.width * 4,
          bitmap.pixels.count >= bitmap.stride * bitmap.height,
          let provider = CGDataProvider(data: bitmap.pixels as CFData) else { return nil }
    return CGImage(width: bitmap.width, height: bitmap.height, bitsPerComponent: 8, bitsPerPixel: 32,
                   bytesPerRow: bitmap.stride, space: CGColorSpaceCreateDeviceRGB(),
                   bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.last.rawValue),
                   provider: provider, decode: nil, shouldInterpolate: true, intent: .defaultIntent)
}

final class HostSession {
    let library: HostLibrary
    let font: HostFont
    let slowDelay: Double
    private(set) var book: HostBook?
    private var document: HostDocument?
    private var pager: HostPager?
    private var fixed: HostFixed?
    private var publication: HostPublication?
    private var part = -1
    private var preserveUnresolvedProgress = false
    private var page = 0
    private var readingOffset = 0
    private var fontSize = 28.0
    private var viewport = CGSize(width: 720, height: 1040)
    private(set) var pageText = ""
    private var pageRange: Range<Int> = 0..<0
    private var currentCancel: HostCancelBox?

    init(library: HostLibrary, font: HostFont, slowDelay: Double, viewport: CGSize, fontSize: Double) {
        self.library = library
        self.font = font
        self.slowDelay = slowDelay
        self.viewport = viewport
        self.fontSize = min(48, max(18, fontSize))
    }

    var currentViewport: CGSize { viewport }

    func matches(_ context: HostSelectionContext) -> Bool {
        book?.id == context.bookID && pageText == context.text && pageRange.lowerBound == context.baseOffset &&
            part == context.part && currentPath == context.path
    }
    private var currentPath: String { publication?.parts.first(where: { $0.index == part })?.path ?? "" }

    func listBooks() throws -> [HostBookRow] {
        try library.books().map { book in
            let detail: String
            if try library.isBoundedEPUB(book: book) {
                if let saved = try library.epubProgress(bookID: book.id) { detail = "EPUB · 第 \(saved.part + 1) 章" }
                else { detail = "EPUB · 有界章节阅读" }
            } else { detail = "\(book.formatLabel) · 位置 \(book.position)" }
            return HostBookRow(id: book.id, title: book.title.isEmpty ? "未命名书籍" : book.title,
                               detail: detail, isFixed: book.isFixed, position: book.position)
        }
    }

    func cancelCurrent() {
        currentCancel?.cancel()
    }

    private func begin(_ cancel: HostCancelBox) throws {
        try cancel.check()
        currentCancel = cancel
    }

    func candidate() -> HostSession {
        HostSession(library: library, font: font, slowDelay: slowDelay,
                    viewport: viewport, fontSize: fontSize)
    }

    // Keep the last usable frame/session if parsing, seeking, rendering or saving fails.
    private func changing(_ cancel: HostCancelBox, _ operation: () throws -> HostSnapshot) throws -> HostSnapshot {
        let old = (book, document, pager, fixed, page, readingOffset, fontSize, viewport, pageText, pageRange, currentCancel,
                   publication, part, preserveUnresolvedProgress)
        try begin(cancel)
        do {
            if slowDelay > 0 { try waitCancellable(cancel, seconds: slowDelay) }
            return try operation()
        }
        catch {
            (book, document, pager, fixed, page, readingOffset, fontSize, viewport, pageText, pageRange, currentCancel,
             publication, part, preserveUnresolvedProgress) = old
            throw error
        }
    }

    private func waitCancellable(_ cancel: HostCancelBox, seconds: Double) throws {
        let steps = max(1, Int(seconds / 0.05))
        for _ in 0..<steps {
            if cancel.isCancelled { throw HostError.cancelled }
            Thread.sleep(forTimeInterval: 0.05)
        }
        if cancel.isCancelled { throw HostError.cancelled }
    }

    private func closeDocument() {
        pager = nil
        document = nil
        fixed = nil
        publication = nil
        part = -1
        preserveUnresolvedProgress = false
        pageRange = 0..<0
        pageText = ""
    }

    func close() {
        closeDocument()
        book = nil
    }

    func importBook(url: URL, cancel: HostCancelBox) throws -> (Int64, Bool) {
        try begin(cancel)
        if slowDelay > 0 { try waitCancellable(cancel, seconds: slowDelay) }
        let title = url.lastPathComponent
        let (id, created) = try library.importUnique(file: url, title: title, cancel: cancel)
        return (id, created)
    }

    func open(bookID: Int64, cancel: HostCancelBox) throws -> HostSnapshot {
        try cancel.check()
        guard let target = try library.books().first(where: { $0.id == bookID }) else {
            throw HostError.invalidInput("书籍不存在")
        }
        return try changing(cancel) { try open(book: target, cancel: cancel) }
    }

    private func open(book target: HostBook, cancel: HostCancelBox) throws -> HostSnapshot {
        try begin(cancel)
        closeDocument()
        book = target
        if target.isFixed {
            let fixed = try library.fixed(bookID: target.id, font: font, cancel: cancel)
            self.fixed = fixed
            page = min(max(0, target.position), max(0, fixed.pageCount - 1))
        } else if try library.isBoundedEPUB(book: target) {
            let source = try HostPublication(library: library, bookID: target.id, cancel: cancel)
            self.publication = source
            guard let first = source.parts.first(where: { $0.reading }) else { throw HostError.invalidResult("EPUB 没有阅读章节") }
            let saved = try library.epubProgress(bookID: target.id)
            part = saved?.part ?? first.index
            _ = try source.route(part, path: saved?.path)
            readingOffset = 0; page = 0
            try rebuildPager(width: Double(viewport.width), height: Double(viewport.height), font: fontSize, cancel: cancel)
            if let saved, let pager {
                let match = try pager.resolveLocation(saved, cancel: cancel)
                if let range = match.range { readingOffset = range.lowerBound; page = try pager.pageIndex(for: readingOffset, cancel: cancel) }
                else { preserveUnresolvedProgress = true }
            }
        } else {
            let document = try library.document(bookID: target.id, cancel: cancel)
            self.document = document
            page = 0
            readingOffset = target.position
            let saved = try library.progress(bookID: target.id)
            if saved.state == EXR_ANCHOR_FOUND || saved.state == EXR_ANCHOR_LEGACY {
                readingOffset = saved.anchor.start
            }
            try rebuildPager(width: Double(viewport.width), height: Double(viewport.height),
                             font: fontSize, cancel: cancel)
        }
        return try renderSnapshot()
    }

    private func rebuildPager(width: Double, height: Double, font size: Double,
                              cancel: HostCancelBox) throws {
        guard document != nil || publication != nil else { return }
        try begin(cancel)
        guard width.isFinite, height.isFinite, size.isFinite else {
            throw HostError.invalidInput("页面尺寸或字号无效")
        }
        let offset = readingOffset
        viewport = CGSize(width: width, height: height)
        fontSize = size
        let newPager: HostPager
        if let publication {
            newPager = try HostPager(publication: publication, part: part, font: font, width: width, height: height,
                                    fontSize: size, box: cancel)
        } else if let document {
            newPager = try HostPager(document: document, font: font, width: width, height: height,
                                    fontSize: size, box: cancel)
        } else { throw HostError.invalidResult("阅读器不可用") }
        pager = newPager
        page = try newPager.pageIndex(for: offset, cancel: cancel)
        _ = try newPager.pageRange(page, cancel: cancel)
    }

    func resize(width: Double, height: Double, cancel: HostCancelBox) throws -> HostSnapshot {
        try changing(cancel) {
            if fixed == nil, document != nil || publication != nil {
                try rebuildPager(width: width, height: height, font: fontSize, cancel: cancel)
            }
            return try renderSnapshot()
        }
    }

    func changeFont(delta: Double, cancel: HostCancelBox) throws -> HostSnapshot {
        try changing(cancel) {
            guard delta.isFinite else { throw HostError.invalidInput("字号无效") }
            if fixed == nil, document != nil || publication != nil {
                let next = min(48, max(18, fontSize + delta))
                if next != fontSize {
                    try rebuildPager(width: Double(viewport.width), height: Double(viewport.height),
                                     font: next, cancel: cancel)
                }
            }
            return try renderSnapshot()
        }
    }

    func turn(_ direction: Int, cancel: HostCancelBox) throws -> HostSnapshot {
        try changing(cancel) {
            guard book != nil else { throw HostError.invalidInput("没有打开的书") }
            guard direction == -1 || direction == 1 else { throw HostError.invalidInput("翻页方向无效") }
            if let fixed {
                page = min(max(0, page + direction), max(0, fixed.pageCount - 1))
            } else {
                guard let pager else { throw HostError.invalidInput("分页尚未就绪") }
                let next = page + direction
                if next >= 0, try pager.existingRange(next, cancel: cancel) != nil { page = next }
                else if let publication {
                    let route = direction > 0 ? publication.parts.first(where: { $0.reading && $0.index > part }) :
                        publication.parts.last(where: { $0.reading && $0.index < part })
                    if let route {
                        part = route.index; readingOffset = 0
                        try rebuildPager(width: Double(viewport.width), height: Double(viewport.height), font: fontSize, cancel: cancel)
                        if direction < 0, let previous = self.pager { page = try previous.pageIndex(for: previous.extent, cancel: cancel) }
                    }
                }
            }
            return try renderSnapshot(userMove: true)
        }
    }

    func firstPage(cancel: HostCancelBox) throws -> HostSnapshot {
        try changing(cancel) {
            if let publication, let first = publication.parts.first(where: { $0.reading }), first.index != part {
                part = first.index; readingOffset = 0
                try rebuildPager(width: Double(viewport.width), height: Double(viewport.height), font: fontSize, cancel: cancel)
            }
            page = 0
            return try renderSnapshot(userMove: true)
        }
    }

    func renderSnapshot(userMove: Bool = false) throws -> HostSnapshot {
        guard let book else { throw HostError.invalidInput("没有打开的书") }
        let cancel = currentCancel ?? HostCancelBox()
        try cancel.check()
        if let fixed {
            let bitmap = try fixed.render(page: page, maximumDimension: 2200, cancel: cancel)
            let text = try fixed.text(page: page, cancel: cancel).text
            guard let image = makeCGImage(bitmap) else { throw HostError.invalidResult("页面图像无法创建") }
            let total = max(1, fixed.pageCount)
            let percent = Int((Double(page + 1) / Double(total) * 100).rounded())
            let location = "第 \(page + 1) / \(total) 页"
            try cancel.commit {
                try library.updatePosition(book: book, position: page)
                pageText = text
                pageRange = 0..<0
            }
            return HostSnapshot(book: book, image: image, location: location,
                                progress: "\(percent)% · 固定版式", pageText: text, pageIndex: page,
                                pageRange: 0..<0, pageCount: total, fontSize: Int(fontSize),
                                pageAccessibilityLabel: pageLabel(text: text, page: page + 1))
        }
        guard let pager else { throw HostError.invalidInput("分页尚未就绪") }
        let range = try pager.pageRange(page, cancel: cancel)
        let nextOffset = userMove ? range.lowerBound : readingOffset
        let bitmap = try pager.render(page, cancel: cancel)
        guard let image = makeCGImage(bitmap) else { throw HostError.invalidResult("页面图像无法创建") }
        // Rendering consumes the borrowed layout first; this query may evict its
        // chapter projection window and returns only an owned current-page copy.
        let text = try pager.text(range, cancel: cancel)
        let totalBytes = max(1, pager.extent)
        let percent = min(100, Int((Double(range.upperBound) / Double(totalBytes) * 100).rounded()))
        let anchor = try pager.makeAnchor(start: nextOffset, end: nextOffset, cancel: cancel)
        try cancel.commit {
            // This SDK call updates numeric position and selector in one transaction.
            if publication != nil {
                if userMove { preserveUnresolvedProgress = false }
                if !preserveUnresolvedProgress { try library.setEPUBProgress(bookID: book.id, part: part, path: currentPath, anchor: anchor) }
            } else { try library.setProgress(bookID: book.id, anchor: anchor) }
            readingOffset = nextOffset
            pageRange = range
            pageText = text
        }
        return HostSnapshot(book: book, image: image,
                            location: publication == nil ? "第 \(page + 1) 页" : "第 \(part + 1) 章 · 第 \(page + 1) 页",
                            progress: publication == nil ? "\(percent)%" : (preserveUnresolvedProgress ? "保存位置未精确匹配；从章首浏览" : "本章 \(percent)% · 有界 EPUB"),
                            pageText: text, pageIndex: page, pageRange: range, pageCount: nil,
                            fontSize: Int(fontSize),
                            pageAccessibilityLabel: pageLabel(text: text, page: page + 1), part: part, path: currentPath)
    }

    private func pageLabel(text: String, page: Int) -> String {
        let flat = text.replacingOccurrences(of: "\n", with: " ")
        let snippet = String(flat.prefix(60))
        return snippet.isEmpty ? "第 \(page) 页" : "第 \(page) 页：\(snippet)"
    }

    func notes() throws -> [HostNoteRow] {
        guard let book else { return [] }
        if let fixed { return try library.fixedNotes(bookID: book.id, fixed: fixed) }
        if publication != nil, let pager { return try library.epubNotes(bookID: book.id, part: part, pager: pager, cancel: currentCancel ?? HostCancelBox()) }
        if let document { return try library.reflowNotes(bookID: book.id, document: document) }
        return []
    }

    func addNote(start: Int, end: Int, comment: String, cancel: HostCancelBox) throws {
        try begin(cancel)
        guard let book else { throw HostError.invalidInput("没有打开的书") }
        guard start >= 0, end > start else { throw HostError.invalidInput("选文范围无效") }
        try cancel.commit {
            if fixed != nil {
                _ = try library.addFixedNote(bookID: book.id, page: page, start: start, end: end, text: comment)
            } else if publication != nil, let pager {
                let anchor = try pager.makeAnchor(start: start, end: end, cancel: cancel)
                try library.addEPUBNote(bookID: book.id, part: part, path: currentPath, anchor: anchor, text: comment)
            } else {
                _ = try library.addNote(bookID: book.id, start: start, end: end, text: comment)
            }
        }
    }

    func updateNote(noteID: Int64, text: String, cancel: HostCancelBox) throws {
        try begin(cancel)
        guard let book else { throw HostError.invalidInput("没有打开的书") }
        guard try notes().contains(where: { $0.id == noteID }) else { throw HostError.invalidInput("标注已不属于当前书籍") }
        try cancel.commit {
            if fixed != nil { try library.updateFixedNoteText(bookID: book.id, noteID: noteID, text: text) }
            else if publication != nil { try library.updateEPUBNote(bookID: book.id, noteID: noteID, text: text) }
            else { try library.updateNoteText(noteID: noteID, text: text) }
        }
    }

    func deleteNote(_ note: HostNoteRow, cancel: HostCancelBox) throws {
        try begin(cancel)
        guard note.bookID == book?.id else { throw HostError.invalidInput("标注已不属于当前书籍") }
        guard let stored = try notes().first(where: { $0.id == note.id && $0.page == note.page && $0.storage == note.storage }) else {
            throw HostError.invalidInput("标注已不属于当前书籍")
        }
        try cancel.commit {
            if stored.location != nil { try library.removeEPUBNote(noteID: stored.id) }
            else if stored.page >= 0 { try library.removeFixedNote(noteID: stored.id) }
            else { try library.removeNote(noteID: stored.id) }
        }
    }

    func jump(to note: HostNoteRow, cancel: HostCancelBox) throws -> HostSnapshot {
        try changing(cancel) {
            guard note.bookID == book?.id else { throw HostError.invalidInput("标注已不属于当前书籍") }
            guard let stored = try notes().first(where: { $0.id == note.id && $0.page == note.page && $0.storage == note.storage }),
                  stored.isResolved || (stored.location != nil && stored.state == "待定位") else {
                throw HostError.invalidInput("该标注无法精确恢复")
            }
            if let location = stored.location, let publication {
                _ = try publication.route(location.part, path: location.path)
                if location.part != part {
                    part = location.part; readingOffset = 0
                    try rebuildPager(width: Double(viewport.width), height: Double(viewport.height), font: fontSize, cancel: cancel)
                }
                guard let pager, let range = try pager.resolveLocation(location, cancel: cancel).range else {
                    throw HostError.invalidInput("该标注无法精确恢复")
                }
                readingOffset = range.lowerBound; page = try pager.pageIndex(for: readingOffset, cancel: cancel)
                preserveUnresolvedProgress = false
            } else if let fixed {
                guard stored.page >= 0, stored.page < fixed.pageCount else { throw HostError.invalidInput("标注页码无效") }
                page = stored.page
            } else {
                guard let pager else { throw HostError.invalidInput("分页尚未就绪") }
                page = try pager.pageIndex(for: stored.start, cancel: cancel)
                readingOffset = stored.start
            }
            return try renderSnapshot()
        }
    }

    func persistCurrent() throws {
        guard let book else { return }
        if let fixed {
            try library.updatePosition(book: book, position: page)
        } else if publication != nil, let pager {
            if !preserveUnresolvedProgress {
                let anchor = try pager.makeAnchor(start: readingOffset, end: readingOffset)
                try library.setEPUBProgress(bookID: book.id, part: part, path: currentPath, anchor: anchor)
            }
        } else if let document {
            let anchor = try document.makeAnchor(start: readingOffset, end: readingOffset)
            try library.setProgress(bookID: book.id, anchor: anchor)
        }
    }

    func stateHash() throws -> String {
        var parts: [String] = []
        for book in try library.books() {
            parts.append("b\(book.id):\(book.position)")
            if try library.isBoundedEPUB(book: book), let saved = try library.epubProgress(bookID: book.id) {
                parts.append("p\(book.id):\(saved.part):\(saved.path):\(saved.raw.selector.start)")
            }
        }
        if publication != nil, let book { parts.append("f\(book.id):\(part):\(currentPath):\(readingOffset)") }
        for note in try notes() {
            parts.append("n\(note.storage):\(note.id):\(note.location?.part ?? -1):\(note.location?.path ?? ""):\(note.page):\(note.start):\(note.state):\(note.comment)")
        }
        let digest = SHA256.hash(data: Data(parts.joined(separator: "|").utf8))
        return String(digest.map { String(format: "%02x", $0) }.joined().prefix(8))
    }

    func writeState(to url: URL, fontSHA: String) throws {
        var payload: [String: Any] = [
            "schema": 2,
            "sdk_version": HOST_SDK_VERSION,
            "abi_version": Int(HOST_ABI_VERSION),
            "font_sha256": fontSHA,
            "state_hash": try stateHash(),
            "books": []
        ]
        var booksPayload: [[String: Any]] = []
        for book in try library.books() {
            var entry: [String: Any] = ["id": book.id, "title": book.title,
                                        "format": book.formatLabel, "position": book.position]
            let bounded = try library.isBoundedEPUB(book: book)
            entry["storage"] = bounded ? "epub" : (book.isFixed ? "fixed" : "global")
            if bounded, let saved = try library.epubProgress(bookID: book.id) {
                entry["epub_progress"] = ["part": saved.part, "path": saved.path,
                                          "start": saved.raw.selector.start, "end": saved.raw.selector.end,
                                          "exact": hostString(saved.raw.selector.exact),
                                          "prefix": hostString(saved.raw.selector.prefix), "suffix": hostString(saved.raw.selector.suffix)]
            }
            if let current = self.book, current.id == book.id {
                entry["notes"] = try notes().map { note -> [String: Any] in
                    ["id": note.id, "quote": note.quote, "comment": note.comment,
                     "page": note.page, "start": note.start, "end": note.end, "state": note.state,
                     "storage": note.storage, "part": note.location?.part ?? -1, "path": note.location?.path ?? "",
                     "selector_start": note.location?.raw.selector.start ?? note.start,
                     "selector_end": note.location?.raw.selector.end ?? note.end]
                }
                entry["page"] = page
                entry["part"] = part
                entry["path"] = currentPath
                entry["reading_offset"] = readingOffset
                entry["unresolved_progress"] = preserveUnresolvedProgress
                if publication != nil, let pager {
                    let stats = pager.statistics
                    entry["bounded_memory"] = ["index_bytes": stats.index_bytes, "parse_workspace_bytes": stats.parse_workspace_bytes,
                                                "peak_parse_workspace_bytes": stats.peak_parse_workspace_bytes,
                                                "page_cache_bytes": stats.page_cache_bytes, "checkpoint_bytes": stats.checkpoint_bytes,
                                                "projection_bytes": stats.projection_bytes, "explicit_snapshot_bytes": stats.explicit_snapshot_bytes,
                                                "swift_page_text_bytes": pageText.utf8.count]
                }
                entry["page_text_sha256"] = SHA256.hash(data: Data(pageText.utf8)).map {
                    String(format: "%02x", $0)
                }.joined()
            }
            booksPayload.append(entry)
        }
        payload["books"] = booksPayload
        let data = try JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys])
        try data.write(to: url, options: .atomic)
    }
}

final class HostReaderModel: ObservableObject {
    @Published var books: [HostBookRow] = []
    @Published var current: HostBookRow?
    @Published var image: CGImage?
    @Published var title = "EXReader"
    @Published var location = "—"
    @Published var progress = "0%"
    @Published var pageText = ""
    @Published var pageBaseOffset = 0
    @Published var pageAccessibilityLabel = ""
    @Published var fontSize = 28
    @Published var statusText = "就绪"
    @Published var errorText = ""
    @Published var stateHash = "—"
    @Published var busy = false
    @Published var notes: [HostNoteRow] = []
    @Published var showLibrary = true
    @Published var frameCount = 0
    private var pagePart = -1
    private var pagePath = ""
    private(set) var fontSHA = ""

    private let queue = DispatchQueue(label: "org.exreader.host.reader")
    private var session: HostSession?
    private var token = 0
    private var activeCancel: HostCancelBox?
    private var started = false
    private var lastViewport = CGSize.zero
    private var viewportWork: DispatchWorkItem?
    private struct ViewportRequest {
        let size: CGSize
        let bookID: Int64
        let token: Int
    }
    private var pendingViewport: ViewportRequest?
    private var viewportWaiting = false
    private var viewportGeneration = 0
    private let defaults = UserDefaults.standard
    private let testFixtures = ProcessInfo.processInfo.arguments.contains("-EXRUITestFixtures")
    private let freshState = ProcessInfo.processInfo.arguments.contains("-EXRFreshState")
    private var slowDelay: Double = 0

    var showsTestFixtures: Bool { testFixtures }

    var selectionContext: HostSelectionContext? {
        guard let current, !busy else { return nil }
        return HostSelectionContext(bookID: current.id, frameCount: frameCount,
                                    baseOffset: pageBaseOffset, text: pageText, part: pagePart, path: pagePath)
    }

    func reportImportFailure(_ error: Error) {
        guard !busy else { return }
        let failure = error as NSError
        guard failure.domain != NSCocoaErrorDomain || failure.code != NSUserCancelledError else { return }
        errorText = describe(error)
        statusText = "导入失败"
    }

    func start() {
        guard !started else { return }
        started = true
        busy = true
        if let index = ProcessInfo.processInfo.arguments.firstIndex(of: "-EXRHostDelayMs"),
           index + 1 < ProcessInfo.processInfo.arguments.count,
           let value = Double(ProcessInfo.processInfo.arguments[index + 1]) {
            slowDelay = max(0, min(10, value / 1000))
        }
        let fresh = freshState
        queue.async {
            do {
                let folder = try self.storageFolder()
                try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
                if fresh {
                    for name in ["library.sqlite", "library.sqlite-wal", "library.sqlite-shm"] {
                        try? FileManager.default.removeItem(at: folder.appendingPathComponent(name))
                    }
                    self.defaults.removeObject(forKey: "EXRLastBook")
                }
                let library = try HostLibrary(path: folder.appendingPathComponent("library.sqlite"))
                let fontURL = Bundle.main.url(forResource: "Reader", withExtension: "otf")
                guard let fontURL else { throw HostError.invalidInput("缺少 Reader.otf") }
                let fontData = try Data(contentsOf: fontURL)
                let font = try HostFont(data: fontData)
                self.fontSHA = SHA256.hash(data: fontData).map { String(format: "%02x", $0) }.joined()
                let savedWidth = self.defaults.double(forKey: "EXRViewportWidth")
                let savedHeight = self.defaults.double(forKey: "EXRViewportHeight")
                let viewport = savedWidth > 200 && savedHeight > 200
                    ? CGSize(width: max(320, savedWidth), height: max(480, savedHeight))
                    : CGSize(width: 720, height: 1040)
                let savedFont = self.defaults.double(forKey: "EXRFontSize")
                let session = HostSession(library: library, font: font, slowDelay: self.slowDelay,
                                          viewport: viewport,
                                          fontSize: savedFont > 0 ? savedFont : 28)
                self.session = session
                let rows = try session.listBooks()
                let lastID = (self.defaults.object(forKey: "EXRLastBook") as? NSNumber)?.int64Value
                DispatchQueue.main.async {
                    self.books = rows
                    self.busy = false
                    if let lastID, rows.contains(where: { $0.id == lastID }) {
                        self.openBook(id: lastID)
                    } else {
                        self.busy = false
                    }
                }
            } catch {
                self.appendLog("startup failed: \(self.describe(error))")
                DispatchQueue.main.async {
                    self.errorText = self.describe(error)
                    self.statusText = "初始化失败"
                    self.busy = false
                }
            }
        }
    }

    private func storageFolder() throws -> URL {
        let base = try FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask,
                                               appropriateFor: nil, create: true)
        return base.appendingPathComponent("EXReader", isDirectory: true)
    }

    private func stateFileURL() throws -> URL {
#if os(iOS)
        let folder = try FileManager.default.url(for: .documentDirectory, in: .userDomainMask,
                                                 appropriateFor: nil, create: true)
        return folder.appendingPathComponent("host-state.json")
#else
        return try storageFolder().appendingPathComponent("host-state.json")
#endif
    }

    private func describe(_ error: Error) -> String {
        if let host = error as? HostError { return host.errorDescription ?? "操作失败" }
        return error.localizedDescription
    }

    private func begin() -> (Int, HostCancelBox) {
        activeCancel?.cancel()
        token += 1
        let box = HostCancelBox()
        activeCancel = box
        busy = true
        errorText = ""
        return (token, box)
    }

    private func finish() {
        activeCancel = nil
        if let request = pendingViewport {
            pendingViewport = nil
            if request.bookID == current?.id, request.token == token, current?.isFixed == false {
                applyViewport(request, finishingPrevious: true)
                return
            }
        }
        busy = false
    }

    private func requireBook(_ id: Int64, session: HostSession, cancel: HostCancelBox) throws {
        try cancel.check()
        guard session.book?.id == id else { throw HostError.invalidInput("书籍已切换，请重试操作") }
    }

    @discardableResult
    private func completeFrame(_ snapshot: HostSnapshot, session: HostSession, token: Int,
                               status: String, opening: Bool = false) -> Bool {
        let notes = Result {
#if EXR_APPLE_HOST_REVIEW
            try HostModelReviewGate.beforeFrameNotes?(session)
#endif
            return try session.notes()
        }
        let hash = Result { try session.stateHash() }
        let viewport = session.currentViewport
        var warnings: [String] = []
        if case .failure(let error) = notes { warnings.append("标注刷新失败：\(describe(error))") }
        if case .failure(let error) = hash { warnings.append("状态刷新失败：\(describe(error))") }
        do { try writeState(session: session) }
        catch { warnings.append("状态记录失败：\(describe(error))") }
        let warning = warnings.joined(separator: "；")
        return DispatchQueue.main.sync {
            guard token == self.token else { return false }
            if self.current?.id != snapshot.book.id {
                self.notes = []
                self.stateHash = "—"
                // A discarded request from the old book must not suppress the
                // new reader's first geometry observation at the same size.
                self.lastViewport = .zero
            }
            self.apply(snapshot)
            if opening { self.showLibrary = false }
            if case .success(let rows) = notes { self.notes = rows }
            if case .success(let value) = hash { self.stateHash = value }
            self.defaults.set(Double(viewport.width), forKey: "EXRViewportWidth")
            self.defaults.set(Double(viewport.height), forKey: "EXRViewportHeight")
            self.statusText = warning.isEmpty ? status : "页面已更新，状态刷新失败"
            self.errorText = warning
            self.finish()
            return true
        }
    }

    private func completeMutation(session: HostSession, token: Int, status: String, imported: Bool = false) {
        let books = Result { try session.listBooks() }
        let notes = Result { try session.notes() }
        let hash = Result { try session.stateHash() }
        var warnings: [String] = []
        if case .failure(let error) = books { warnings.append("书架刷新失败：\(describe(error))") }
        if case .failure(let error) = notes { warnings.append("标注刷新失败：\(describe(error))") }
        if case .failure(let error) = hash { warnings.append("状态刷新失败：\(describe(error))") }
        do { try writeState(session: session) }
        catch { warnings.append("状态记录失败：\(describe(error))") }
        let warning = warnings.joined(separator: "；")
        DispatchQueue.main.async {
            guard token == self.token else { return }
            if case .success(let rows) = books { self.books = rows }
            if case .success(let rows) = notes { self.notes = rows }
            if case .success(let value) = hash { self.stateHash = value }
            if imported { self.showLibrary = true }
            self.statusText = warning.isEmpty ? status : "\(status)，刷新失败"
            self.errorText = warning
            self.finish()
        }
    }

    private func apply(_ snapshot: HostSnapshot) {
        current = HostBookRow(id: snapshot.book.id, title: snapshot.book.title,
                              detail: "\(snapshot.book.formatLabel) · 位置 \(snapshot.book.position)",
                              isFixed: snapshot.book.isFixed, position: snapshot.book.position)
        image = snapshot.image
        title = snapshot.book.title
        location = snapshot.location
        progress = snapshot.progress
        pageText = snapshot.pageText
        pageBaseOffset = snapshot.pageRange.lowerBound
        pagePart = snapshot.part
        pagePath = snapshot.path
        pageAccessibilityLabel = snapshot.pageAccessibilityLabel
        fontSize = snapshot.fontSize
        defaults.set(snapshot.fontSize, forKey: "EXRFontSize")
        frameCount += 1
        defaults.set(snapshot.book.id, forKey: "EXRLastBook")
    }

    private func publishNotes(_ rows: [HostNoteRow], hash: String) {
        notes = rows
        stateHash = hash
    }

    func refreshState() {
        guard !busy else { return }
        let (myToken, _) = begin()
        queue.async {
            do {
                guard let session = self.session else { throw HostError.invalidInput("书库未就绪") }
                let rows = try session.listBooks()
                let notes = try session.notes()
                let hash = try session.stateHash()
                DispatchQueue.main.async {
                    guard myToken == self.token else { return }
                    self.books = rows
                    self.publishNotes(notes, hash: hash)
                    self.finish()
                }
            } catch {
                DispatchQueue.main.async {
                    guard myToken == self.token else { return }
                    self.errorText = self.describe(error)
                    self.finish()
                }
            }
        }
    }

    func openBook(id: Int64) {
        guard let row = books.first(where: { $0.id == id }) else { return }
        openBook(row)
    }

    func openBook(_ row: HostBookRow) {
        guard !busy else { return }
        let (myToken, box) = begin()
        statusText = "正在打开…"
        queue.async {
            do {
                guard let session = self.session else { throw HostError.invalidInput("书库未就绪") }
                let candidate = session.candidate()
                let snapshot = try candidate.open(bookID: row.id, cancel: box)
                if self.completeFrame(snapshot, session: candidate, token: myToken, status: "就绪", opening: true) {
                    // Only the accepted candidate replaces SDK handles, on their serial owner queue.
                    self.session = candidate
                }
            } catch {
                DispatchQueue.main.async {
                    guard myToken == self.token else { return }
                    self.fail(error)
                }
            }
        }
    }

    func importFile(_ url: URL) {
        guard !busy else { return }
        let (myToken, box) = begin()
        statusText = "正在导入…"
        queue.async {
            let scoped = url.startAccessingSecurityScopedResource()
            defer { if scoped { url.stopAccessingSecurityScopedResource() } }
            do {
                guard let session = self.session else { throw HostError.invalidInput("书库未就绪") }
                let (bookID, created) = try session.importBook(url: url, cancel: box)
                do { try box.commit {} }
                catch {
                    if created { try session.library.delete(bookID: bookID) }
                    throw error
                }
                self.completeMutation(session: session, token: myToken,
                                      status: created ? "已导入 \(url.lastPathComponent)" : "已存在，复用书架记录",
                                      imported: true)
            } catch {
                DispatchQueue.main.async {
                    guard myToken == self.token else { return }
                    self.fail(error)
                }
            }
        }
    }

    func importFixture(_ name: String, extension ext: String) {
        guard let url = Bundle.main.url(forResource: name, withExtension: ext) else {
            errorText = "缺少示例文件 \(name).\(ext)"
            return
        }
        importFile(url)
    }

    func turn(_ delta: Int) {
        guard !busy, let bookID = current?.id else { return }
        let (myToken, box) = begin()
        queue.async {
            do {
                guard let session = self.session else { throw HostError.invalidInput("书库未就绪") }
                try self.requireBook(bookID, session: session, cancel: box)
                let snapshot = try session.turn(delta, cancel: box)
                self.completeFrame(snapshot, session: session, token: myToken, status: "就绪")
            } catch {
                DispatchQueue.main.async {
                    guard myToken == self.token else { return }
                    self.fail(error)
                }
            }
        }
    }

    func firstPage() {
        guard !busy, let bookID = current?.id else { return }
        let (myToken, box) = begin()
        queue.async {
            do {
                guard let session = self.session else { throw HostError.invalidInput("书库未就绪") }
                try self.requireBook(bookID, session: session, cancel: box)
                let snapshot = try session.firstPage(cancel: box)
                self.completeFrame(snapshot, session: session, token: myToken, status: "就绪")
            } catch {
                DispatchQueue.main.async {
                    guard myToken == self.token else { return }
                    self.fail(error)
                }
            }
        }
    }

    func changeFont(_ delta: Int) {
        guard !busy, let bookID = current?.id else { return }
        let (myToken, box) = begin()
        queue.async {
            do {
                guard let session = self.session else { throw HostError.invalidInput("书库未就绪") }
                try self.requireBook(bookID, session: session, cancel: box)
                let snapshot = try session.changeFont(delta: Double(delta), cancel: box)
                self.completeFrame(snapshot, session: session, token: myToken,
                                   status: snapshot.pageCount == nil ? "字号 \(snapshot.fontSize)" : "固定版式")
            } catch {
                DispatchQueue.main.async {
                    guard myToken == self.token else { return }
                    self.fail(error)
                }
            }
        }
    }

    func updateViewport(_ size: CGSize) {
        guard let current, !current.isFixed else { return }
        guard size.width > 80, size.height > 80 else { return }
        guard abs(size.width - lastViewport.width) > 6 || abs(size.height - lastViewport.height) > 6 else { return }
        lastViewport = size
        viewportWork?.cancel()
        viewportGeneration += 1
        let generation = viewportGeneration
        let request = ViewportRequest(size: size, bookID: current.id, token: token)
        // The finishing worker will hand this request directly to the next
        // worker. Do not publish an idle, selectable frame between the two.
        if busy && !viewportWaiting {
            pendingViewport = request
            return
        }
        // The debounced interval is part of the resize operation: exposing a
        // selectable frame here would invalidate it as soon as the timer fires.
        if !busy {
            viewportWaiting = true
            busy = true
            statusText = "正在调整页面…"
        }
        let work = DispatchWorkItem { [weak self] in
            guard let self, self.viewportGeneration == generation, self.viewportWaiting else { return }
            self.viewportWaiting = false
            guard request.bookID == self.current?.id, request.token == self.token else {
                self.finish()
                return
            }
            self.applyViewport(request, finishingPrevious: true)
        }
        viewportWork = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.35, execute: work)
    }

    private func applyViewport(_ request: ViewportRequest, finishingPrevious: Bool = false) {
        guard let current, !current.isFixed else { return }
        guard current.id == request.bookID, token == request.token else { return }
        guard !busy || finishingPrevious else { pendingViewport = request; return }
        let bookID = current.id
        let size = request.size
        let (myToken, box) = begin()
        queue.async {
            do {
                guard let session = self.session else { throw HostError.invalidInput("书库未就绪") }
                try self.requireBook(bookID, session: session, cancel: box)
                let snapshot = try session.resize(width: Double(size.width), height: Double(size.height), cancel: box)
                self.completeFrame(snapshot, session: session, token: myToken, status: "就绪")
            } catch {
                DispatchQueue.main.async {
                    guard myToken == self.token else { return }
                    self.fail(error)
                }
            }
        }
    }

    func addNote(start: Int, end: Int, comment: String, expectedContext: HostSelectionContext? = nil) {
        guard !busy, let context = expectedContext ?? selectionContext, context == selectionContext,
              start >= context.baseOffset, end > start,
              end - context.baseOffset <= context.text.utf8.count else {
            errorText = "选文已失效，请重新选择"
            return
        }
        let (myToken, box) = begin()
        queue.async {
            do {
                guard let session = self.session else { throw HostError.invalidInput("书库未就绪") }
                try self.requireBook(context.bookID, session: session, cancel: box)
                guard session.matches(context) else { throw HostError.invalidInput("选文页面已变化，请重新选择") }
                try session.addNote(start: start, end: end, comment: comment, cancel: box)
                self.completeMutation(session: session, token: myToken, status: "已保存标注")
            } catch {
                DispatchQueue.main.async {
                    guard myToken == self.token else { return }
                    self.fail(error)
                }
            }
        }
    }

    func updateNote(_ note: HostNoteRow, text: String) {
        guard !busy, let bookID = current?.id, note.bookID == bookID else { return }
        let (myToken, box) = begin()
        queue.async {
            do {
                guard let session = self.session else { throw HostError.invalidInput("书库未就绪") }
                try self.requireBook(bookID, session: session, cancel: box)
                try session.updateNote(noteID: note.id, text: text, cancel: box)
                self.completeMutation(session: session, token: myToken, status: "标注已更新")
            } catch {
                DispatchQueue.main.async {
                    guard myToken == self.token else { return }
                    self.fail(error)
                }
            }
        }
    }

    func deleteNote(_ note: HostNoteRow) {
        guard !busy, let bookID = current?.id, note.bookID == bookID else { return }
        let (myToken, box) = begin()
        queue.async {
            do {
                guard let session = self.session else { throw HostError.invalidInput("书库未就绪") }
                try self.requireBook(bookID, session: session, cancel: box)
                try session.deleteNote(note, cancel: box)
                self.completeMutation(session: session, token: myToken, status: "标注已删除")
            } catch {
                DispatchQueue.main.async {
                    guard myToken == self.token else { return }
                    self.fail(error)
                }
            }
        }
    }

    func jump(to note: HostNoteRow) {
        guard !busy, let bookID = current?.id, note.bookID == bookID else { return }
        let (myToken, box) = begin()
        queue.async {
            do {
                guard let session = self.session else { throw HostError.invalidInput("书库未就绪") }
                try self.requireBook(bookID, session: session, cancel: box)
                let snapshot = try session.jump(to: note, cancel: box)
                self.completeFrame(snapshot, session: session, token: myToken, status: "已定位标注")
            } catch {
                DispatchQueue.main.async {
                    guard myToken == self.token else { return }
                    self.fail(error)
                }
            }
        }
    }

    func backToLibrary() {
        token += 1
        let myToken = token
        activeCancel?.cancel()
        viewportWork?.cancel()
        viewportGeneration += 1
        viewportWaiting = false
        pendingViewport = nil
        busy = true
        statusText = "正在保存…"
        queue.async {
            do {
                try self.session?.persistCurrent()
                let rows = try self.session?.listBooks() ?? []
                try self.writeState(session: self.session)
                self.session?.close()
                DispatchQueue.main.async {
                    guard myToken == self.token else { return }
                    self.books = rows
                    self.showLibrary = true
                    self.current = nil
                    self.image = nil
                    self.pageText = ""
                    self.notes = []
                    self.defaults.removeObject(forKey: "EXRLastBook")
                    self.errorText = ""
                    self.statusText = "就绪"
                    self.finish()
                }
            } catch {
                DispatchQueue.main.async {
                    guard myToken == self.token else { return }
                    self.fail(error)
                }
            }
        }
    }

    func cancelWork() {
        viewportWork?.cancel()
        viewportGeneration += 1
        pendingViewport = nil
        if viewportWaiting {
            viewportWaiting = false
            statusText = "已取消"
            finish()
            return
        }
        activeCancel?.cancel()
        statusText = "正在取消…"
    }

    func persistNow() {
        let myToken = token
        queue.async {
            do {
                try self.session?.persistCurrent()
                try self.writeState(session: self.session)
            } catch {
                self.appendLog("persistence failed: \(self.describe(error))")
                DispatchQueue.main.async {
                    guard myToken == self.token else { return }
                    self.errorText = "保存失败：\(self.describe(error))"
                    self.statusText = "保存失败，请重试"
                }
            }
        }
    }

    func detach() {
        activeCancel?.cancel()
        persistNow()
    }

    private func appendLog(_ text: String) {
        guard let base = try? stateFileURL().deletingLastPathComponent() else { return }
        let url = base.appendingPathComponent("host-log.txt")
        let line = "\(Date().timeIntervalSince1970) \(text)\n"
        if let handle = try? FileHandle(forWritingTo: url) {
            handle.seekToEndOfFile()
            handle.write(Data(line.utf8))
            try? handle.close()
        } else {
            try? Data(line.utf8).write(to: url)
        }
    }

    private func fail(_ error: Error) {
        appendLog("operation failed: \(describe(error))")
        if let host = error as? HostError, host.isCancelled {
            statusText = "已取消"
            finish()
            return
        }
        errorText = describe(error)
        statusText = "操作失败"
        finish()
    }

    private func writeState(session: HostSession?) throws {
        guard let session else { return }
        try session.writeState(to: try stateFileURL(), fontSHA: fontSHA)
    }

#if EXR_APPLE_HOST_REVIEW
    // Install an actual session in the command-line cloud consumer without
    // relying on application-bundle startup resources or replacing SDK calls.
    func installReviewSession(_ session: HostSession, snapshot: HostSnapshot) throws {
        // start() creates this directory for the real app. The headless
        // consumer must satisfy the same persistence prerequisite explicitly.
        let stateFolder = try stateFileURL().deletingLastPathComponent()
        try FileManager.default.createDirectory(at: stateFolder, withIntermediateDirectories: true)
        self.session = session
        books = try session.listBooks()
        apply(snapshot)
        notes = try session.notes()
        stateHash = try session.stateHash()
        showLibrary = false
        busy = false
    }
#endif
}
