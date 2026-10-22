// SPDX-License-Identifier: MIT
import Foundation
import CoreGraphics
import CryptoKit
import CEXReader

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
    private var page = 0
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

    func listBooks() throws -> [HostBookRow] {
        try library.books().map { book in
            let detail = "\(book.formatLabel) · 位置 \(book.position)"
            return HostBookRow(id: book.id, title: book.title.isEmpty ? "未命名书籍" : book.title,
                               detail: detail, isFixed: book.isFixed, position: book.position)
        }
    }

    func cancelCurrent() {
        currentCancel?.cancel()
    }

    private func begin(_ cancel: HostCancelBox) {
        currentCancel = cancel
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
        pageRange = 0..<0
        pageText = ""
    }

    func close() {
        closeDocument()
        book = nil
    }

    func importBook(url: URL, cancel: HostCancelBox) throws -> (Int64, Bool) {
        begin(cancel)
        if slowDelay > 0 { try waitCancellable(cancel, seconds: slowDelay) }
        let title = url.lastPathComponent
        let (id, created) = try library.importUnique(file: url, title: title)
        return (id, created)
    }

    func open(bookID: Int64, cancel: HostCancelBox) throws -> HostSnapshot {
        guard let target = try library.books().first(where: { $0.id == bookID }) else {
            throw HostError.invalidInput("书籍不存在")
        }
        return try open(book: target, cancel: cancel)
    }

    private func open(book target: HostBook, cancel: HostCancelBox) throws -> HostSnapshot {
        begin(cancel)
        closeDocument()
        book = target
        if target.isFixed {
            let fixed = try library.fixed(bookID: target.id, font: font)
            self.fixed = fixed
            page = min(max(0, target.position), max(0, fixed.pageCount - 1))
        } else {
            let document = try library.document(bookID: target.id)
            self.document = document
            page = 0
            try rebuildPager(width: Double(viewport.width), height: Double(viewport.height),
                             font: fontSize, cancel: cancel, restore: true)
        }
        do {
            return try renderSnapshot()
        } catch {
            if let failure = pager?.failure {
                throw HostError.invalidInput("分页失败（\(Int(viewport.width))x\(Int(viewport.height))）：\(failure)")
            }
            throw error
        }
    }

    private func rebuildPager(width: Double, height: Double, font size: Double,
                              cancel: HostCancelBox, restore: Bool) throws {
        guard let document else { return }
        begin(cancel)
        let anchor: HostAnchor?
        if restore, let saved = try? library.progress(bookID: documentID()) {
            anchor = saved.state == EXR_ANCHOR_FOUND || saved.state == EXR_ANCHOR_LEGACY ? saved.anchor : nil
        } else if !restore, pageRange.lowerBound <= pageRange.upperBound {
            anchor = try? document.makeAnchor(start: pageRange.lowerBound, end: pageRange.lowerBound)
        } else {
            anchor = nil
        }
        viewport = CGSize(width: width, height: height)
        fontSize = size
        let newPager = try HostPager(document: document, font: font, width: width, height: height,
                                     fontSize: size, box: cancel)
        pager = newPager
        if let anchor {
            if let match = try? document.resolve(anchor), let range = match.range {
                page = (try? newPager.pageIndex(for: range.lowerBound)) ?? 0
            } else {
                page = (try? newPager.pageIndex(for: anchor.start)) ?? 0
            }
        }
        if (try? newPager.pageRange(page)) == nil { page = 0 }
    }

    private func documentID() -> Int64 { book?.id ?? 0 }

    func resize(width: Double, height: Double, cancel: HostCancelBox) throws -> HostSnapshot {
        begin(cancel)
        guard fixed == nil, document != nil else { return try renderSnapshot() }
        try rebuildPager(width: width, height: height, font: fontSize, cancel: cancel, restore: false)
        return try renderSnapshot()
    }

    func changeFont(delta: Double, cancel: HostCancelBox) throws -> HostSnapshot {
        begin(cancel)
        guard fixed == nil, document != nil else { return try renderSnapshot() }
        let next = min(48, max(18, fontSize + delta))
        guard next != fontSize else { return try renderSnapshot() }
        try rebuildPager(width: Double(viewport.width), height: Double(viewport.height),
                         font: next, cancel: cancel, restore: false)
        return try renderSnapshot()
    }

    func turn(_ direction: Int, cancel: HostCancelBox) throws -> HostSnapshot {
        begin(cancel)
        guard let book else { throw HostError.invalidInput("没有打开的书") }
        if let fixed {
            let next = page + direction
            page = min(max(0, next), max(0, fixed.pageCount - 1))
        } else {
            guard pager != nil else { throw HostError.invalidInput("分页尚未就绪") }
            let next = page + direction
            if next >= 0, (try? pager?.pageRange(next)) != nil {
                page = next
            }
        }
        _ = book
        return try renderSnapshot()
    }

    func firstPage(cancel: HostCancelBox) throws -> HostSnapshot {
        begin(cancel)
        page = 0
        return try renderSnapshot()
    }

    func renderSnapshot() throws -> HostSnapshot {
        guard let book else { throw HostError.invalidInput("没有打开的书") }
        if let fixed {
            let bitmap = try fixed.render(page: page, maximumDimension: 2200)
            let text = try fixed.text(page: page).text
            pageText = text
            let total = max(1, fixed.pageCount)
            let percent = Int((Double(page + 1) / Double(total) * 100).rounded())
            let location = "第 \(page + 1) / \(total) 页"
            pageRange = 0..<0
            try persist(book: book, fixed: fixed)
            return HostSnapshot(book: book, image: makeCGImage(bitmap), location: location,
                                progress: "\(percent)% · 固定版式", pageText: text, pageIndex: page,
                                pageRange: 0..<0, pageCount: total, fontSize: Int(fontSize),
                                pageAccessibilityLabel: pageLabel(text: text, page: page + 1))
        }
        guard let document, let pager else { throw HostError.invalidInput("分页尚未就绪") }
        let range = try pager.pageRange(page)
        let bitmap = try pager.render(page)
        let text = slice(document.text, range)
        pageRange = range
        pageText = text
        let totalBytes = max(1, document.text.count)
        let percent = min(100, Int((Double(range.upperBound) / Double(totalBytes) * 100).rounded()))
        try persist(book: book, fixed: nil, document: document, range: range)
        return HostSnapshot(book: book, image: makeCGImage(bitmap),
                            location: "第 \(page + 1) 页", progress: "\(percent)%",
                            pageText: text, pageIndex: page, pageRange: range, pageCount: nil,
                            fontSize: Int(fontSize),
                            pageAccessibilityLabel: pageLabel(text: text, page: page + 1))
    }

    private func pageLabel(text: String, page: Int) -> String {
        let flat = text.replacingOccurrences(of: "\n", with: " ")
        let snippet = String(flat.prefix(60))
        return snippet.isEmpty ? "第 \(page) 页" : "第 \(page) 页：\(snippet)"
    }

    private func slice(_ data: Data, _ range: Range<Int>) -> String {
        guard range.lowerBound >= 0, range.upperBound <= data.count,
              range.lowerBound <= range.upperBound else { return "" }
        return String(decoding: data[range], as: UTF8.self)
    }

    private func persist(book: HostBook, fixed: HostFixed?) throws {
        if fixed != nil {
            try library.updatePosition(book: book, position: page)
        } else if let document {
            let anchor = try document.makeAnchor(start: pageRange.lowerBound, end: pageRange.lowerBound)
            try library.setProgress(bookID: book.id, anchor: anchor)
        }
    }

    private func persist(book: HostBook, fixed: HostFixed?, document: HostDocument, range: Range<Int>) throws {
        try library.updatePosition(book: book, position: range.lowerBound)
        let anchor = try document.makeAnchor(start: range.lowerBound, end: range.lowerBound)
        try library.setProgress(bookID: book.id, anchor: anchor)
    }

    func notes() throws -> [HostNoteRow] {
        guard let book else { return [] }
        if let fixed { return try library.fixedNotes(bookID: book.id, fixed: fixed) }
        if let document { return try library.reflowNotes(bookID: book.id, document: document) }
        return []
    }

    func addNote(start: Int, end: Int, comment: String, cancel: HostCancelBox) throws {
        begin(cancel)
        guard let book else { throw HostError.invalidInput("没有打开的书") }
        if fixed != nil {
            _ = try library.addFixedNote(bookID: book.id, page: page, start: start, end: end, text: comment)
        } else {
            _ = try library.addNote(bookID: book.id, start: start, end: end, text: comment)
        }
    }

    func updateNote(noteID: Int64, text: String, cancel: HostCancelBox) throws {
        begin(cancel)
        try library.updateNoteText(noteID: noteID, text: text)
    }

    func deleteNote(_ note: HostNoteRow, cancel: HostCancelBox) throws {
        begin(cancel)
        if note.page >= 0 {
            try library.removeFixedNote(noteID: note.id)
        } else {
            try library.removeNote(noteID: note.id)
        }
    }

    func jump(to note: HostNoteRow, cancel: HostCancelBox) throws -> HostSnapshot {
        begin(cancel)
        guard note.isResolved else { throw HostError.invalidInput("该标注无法精确恢复") }
        if let fixed {
            page = min(max(0, note.page), max(0, fixed.pageCount - 1))
            return try renderSnapshot()
        }
        guard let pager else { throw HostError.invalidInput("分页尚未就绪") }
        page = try pager.pageIndex(for: note.start)
        return try renderSnapshot()
    }

    func persistCurrent() {
        guard let book else { return }
        if let fixed {
            try? library.updatePosition(book: book, position: page)
        } else if let document, pageRange.lowerBound <= pageRange.upperBound {
            if let anchor = try? document.makeAnchor(start: pageRange.lowerBound, end: pageRange.lowerBound) {
                try? library.setProgress(bookID: book.id, anchor: anchor)
            }
        }
    }

    func stateHash() throws -> String {
        var parts: [String] = []
        for book in try library.books() {
            parts.append("b\(book.id):\(book.position)")
        }
        for note in try notes() {
            parts.append("n\(note.id):\(note.page):\(note.start):\(note.state):\(note.comment)")
        }
        let digest = SHA256.hash(data: Data(parts.joined(separator: "|").utf8))
        return String(digest.map { String(format: "%02x", $0) }.joined().prefix(8))
    }

    func writeState(to url: URL, fontSHA: String) throws {
        var payload: [String: Any] = [
            "schema": 1,
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
            if let current = self.book, current.id == book.id {
                entry["notes"] = try notes().map { note -> [String: Any] in
                    ["id": note.id, "quote": note.quote, "comment": note.comment,
                     "page": note.page, "start": note.start, "state": note.state]
                }
                entry["page"] = page
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
    private(set) var fontSHA = ""

    private let queue = DispatchQueue(label: "org.exreader.host.reader")
    private var session: HostSession?
    private var token = 0
    private var activeCancel: HostCancelBox?
    private var started = false
    private var lastViewport = CGSize.zero
    private var viewportWork: DispatchWorkItem?
    private let defaults = UserDefaults.standard
    private let testFixtures = ProcessInfo.processInfo.arguments.contains("-EXRUITestFixtures")
    private let freshState = ProcessInfo.processInfo.arguments.contains("-EXRFreshState")
    private var slowDelay: Double = 0

    var showsTestFixtures: Bool { testFixtures }

    func start() {
        guard !started else { return }
        started = true
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
        token += 1
        let box = HostCancelBox()
        activeCancel = box
        busy = true
        errorText = ""
        return (token, box)
    }

    private func finish() {
        busy = false
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
        let (myToken, box) = begin()
        statusText = "正在打开…"
        queue.async {
            do {
                guard let session = self.session else { throw HostError.invalidInput("书库未就绪") }
                let snapshot = try session.open(bookID: row.id, cancel: box)
                let notes = try session.notes()
                let hash = try session.stateHash()
                try? self.writeState(session: session)
                DispatchQueue.main.async {
                    guard myToken == self.token else { return }
                    self.apply(snapshot)
                    self.showLibrary = false
                    self.publishNotes(notes, hash: hash)
                    self.statusText = box.isCancelled ? "已取消" : "就绪"
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

    func importFile(_ url: URL) {
        let (myToken, box) = begin()
        statusText = "正在导入…"
        queue.async {
            let scoped = url.startAccessingSecurityScopedResource()
            defer { if scoped { url.stopAccessingSecurityScopedResource() } }
            do {
                guard let session = self.session else { throw HostError.invalidInput("书库未就绪") }
                let (bookID, created) = try session.importBook(url: url, cancel: box)
                let rows = try session.listBooks()
                let hash = try session.stateHash()
                try? self.writeState(session: session)
                DispatchQueue.main.async {
                    guard myToken == self.token else { return }
                    self.books = rows
                    self.showLibrary = true
                    self.stateHash = hash
                    if box.isCancelled {
                        self.statusText = "已取消"
                    } else if created {
                        let name = rows.first(where: { $0.id == bookID })?.title ?? "书籍"
                        self.statusText = "已导入 \(name)"
                    } else {
                        self.statusText = "已存在，复用书架记录"
                    }
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

    func importFixture(_ name: String, extension ext: String) {
        guard let url = Bundle.main.url(forResource: name, withExtension: ext) else {
            errorText = "缺少示例文件 \(name).\(ext)"
            return
        }
        importFile(url)
    }

    func turn(_ delta: Int) {
        let (myToken, box) = begin()
        queue.async {
            do {
                guard let session = self.session else { throw HostError.invalidInput("书库未就绪") }
                let snapshot = try session.turn(delta, cancel: box)
                let hash = try session.stateHash()
                DispatchQueue.main.async {
                    guard myToken == self.token else { return }
                    self.apply(snapshot)
                    self.stateHash = hash
                    self.statusText = box.isCancelled ? "已取消" : "就绪"
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

    func firstPage() {
        let (myToken, box) = begin()
        queue.async {
            do {
                guard let session = self.session else { throw HostError.invalidInput("书库未就绪") }
                let snapshot = try session.firstPage(cancel: box)
                let hash = try session.stateHash()
                DispatchQueue.main.async {
                    guard myToken == self.token else { return }
                    self.apply(snapshot)
                    self.stateHash = hash
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

    func changeFont(_ delta: Int) {
        let (myToken, box) = begin()
        queue.async {
            do {
                guard let session = self.session else { throw HostError.invalidInput("书库未就绪") }
                let snapshot = try session.changeFont(delta: Double(delta), cancel: box)
                let hash = try session.stateHash()
                DispatchQueue.main.async {
                    guard myToken == self.token else { return }
                    self.apply(snapshot)
                    self.stateHash = hash
                    self.statusText = snapshot.pageCount == nil ? "字号 \(snapshot.fontSize)" : "固定版式"
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

    func updateViewport(_ size: CGSize) {
        guard size.width > 80, size.height > 80 else { return }
        guard abs(size.width - lastViewport.width) > 6 || abs(size.height - lastViewport.height) > 6 else { return }
        lastViewport = size
        viewportWork?.cancel()
        let work = DispatchWorkItem { [weak self] in self?.applyViewport(size) }
        viewportWork = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.35, execute: work)
    }

    private func applyViewport(_ size: CGSize) {
        guard let current, !current.isFixed else { return }
        defaults.set(Double(size.width), forKey: "EXRViewportWidth")
        defaults.set(Double(size.height), forKey: "EXRViewportHeight")
        let (myToken, box) = begin()
        queue.async {
            do {
                guard let session = self.session else { throw HostError.invalidInput("书库未就绪") }
                let snapshot = try session.resize(width: Double(size.width), height: Double(size.height), cancel: box)
                let hash = try session.stateHash()
                DispatchQueue.main.async {
                    guard myToken == self.token else { return }
                    self.apply(snapshot)
                    self.stateHash = hash
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

    func addNote(start: Int, end: Int, comment: String) {
        let (myToken, box) = begin()
        queue.async {
            do {
                guard let session = self.session else { throw HostError.invalidInput("书库未就绪") }
                try session.addNote(start: start, end: end, comment: comment, cancel: box)
                let notes = try session.notes()
                let hash = try session.stateHash()
                try? self.writeState(session: session)
                DispatchQueue.main.async {
                    guard myToken == self.token else { return }
                    self.publishNotes(notes, hash: hash)
                    self.statusText = "已保存标注"
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

    func updateNote(_ note: HostNoteRow, text: String) {
        let (myToken, box) = begin()
        queue.async {
            do {
                guard let session = self.session else { throw HostError.invalidInput("书库未就绪") }
                try session.updateNote(noteID: note.id, text: text, cancel: box)
                let notes = try session.notes()
                let hash = try session.stateHash()
                try? self.writeState(session: session)
                DispatchQueue.main.async {
                    guard myToken == self.token else { return }
                    self.publishNotes(notes, hash: hash)
                    self.statusText = "标注已更新"
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

    func deleteNote(_ note: HostNoteRow) {
        let (myToken, box) = begin()
        queue.async {
            do {
                guard let session = self.session else { throw HostError.invalidInput("书库未就绪") }
                try session.deleteNote(note, cancel: box)
                let notes = try session.notes()
                let hash = try session.stateHash()
                try? self.writeState(session: session)
                DispatchQueue.main.async {
                    guard myToken == self.token else { return }
                    self.publishNotes(notes, hash: hash)
                    self.statusText = "标注已删除"
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

    func jump(to note: HostNoteRow) {
        let (myToken, box) = begin()
        queue.async {
            do {
                guard let session = self.session else { throw HostError.invalidInput("书库未就绪") }
                let snapshot = try session.jump(to: note, cancel: box)
                let hash = try session.stateHash()
                DispatchQueue.main.async {
                    guard myToken == self.token else { return }
                    self.apply(snapshot)
                    self.stateHash = hash
                    self.statusText = "已定位标注"
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

    func backToLibrary() {
        token += 1
        activeCancel?.cancel()
        busy = false
        showLibrary = true
        current = nil
        image = nil
        queue.async {
            self.session?.persistCurrent()
            self.session?.close()
            if let rows = try? self.session?.listBooks() {
                DispatchQueue.main.async { self.books = rows }
            }
        }
    }

    func cancelWork() {
        activeCancel?.cancel()
        statusText = "正在取消…"
    }

    func persistNow() {
        queue.async {
            self.session?.persistCurrent()
            try? self.writeState(session: self.session)
        }
    }

    func detach() {
        activeCancel?.cancel()
        queue.async {
            self.session?.persistCurrent()
        }
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
}