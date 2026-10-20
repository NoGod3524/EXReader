// SPDX-License-Identifier: MIT
import SwiftUI
import Foundation
import CryptoKit
import UniformTypeIdentifiers
import CEXReader

private struct BookEntry: Codable, Identifiable {
    let id: String
    let title: String
}
private struct ReaderFrame {
    let bitmap: EXReaderBitmap
    let text: String
    let title: String
    let part: Int
    let page: Int
    let sourceOffset: Int
}
private final class ReaderSession {
    let storage: URL
    let defaults: UserDefaults
    let font: EXReaderFont
    var publication: EXReaderPublication?
    var document: EXReaderDocument?
    var fixed: EXReaderFixedDocument?
    var pager: EXReaderPager?
    var entry: BookEntry?
    var part = 0
    var page = 0
    var fontSize: Float = 28
    var lastPages: [Int: Int] = [:]
    var lastFrame: ReaderFrame?
    var library: [BookEntry] = []
    var config: EXReaderLayoutConfig {
        var result = EXReaderLayoutConfig()
        result.page.width = 720; result.page.height = 1040
        result.page.margin = 36; result.page.font_size = fontSize
        return result
    }
    init(storage: URL, defaults: UserDefaults = .standard) throws {
        self.storage = storage; self.defaults = defaults
        try FileManager.default.createDirectory(at: storage, withIntermediateDirectories: true)
        let fontURL = Bundle.main.url(forResource: "Reader", withExtension: "otf")!
        font = try EXReaderFont(data: Data(contentsOf: fontURL))
        if let data = try? Data(contentsOf: storage.appendingPathComponent("library.json")) {
            library = try JSONDecoder().decode([BookEntry].self, from: data)
        }
    }
    func importBook(_ url: URL) throws -> ReaderFrame {
        let scoped = url.startAccessingSecurityScopedResource()
        defer { if scoped { url.stopAccessingSecurityScopedResource() } }
        let size = try url.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0
        guard size > 0, size <= 32 * 1024 * 1024 else { throw EXReaderError.invalidInput }
        let data = try Data(contentsOf: url)
        guard data.count <= 32 * 1024 * 1024 else { throw EXReaderError.invalidInput }
        let ext = url.pathExtension.lowercased()
        guard ["epub", "pdf", "cbz", "txt", "fb2", "html", "rtf", "docx", "mobi", "azw3"].contains(ext) else {
            throw EXReaderError.invalidInput
        }
        let id = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() + "." + ext
        let target = storage.appendingPathComponent(id)
        if !FileManager.default.fileExists(atPath: target.path) { try data.write(to: target, options: .atomic) }
        let book = BookEntry(id: id, title: url.deletingPathExtension().lastPathComponent)
        let frame = try open(book)
        if !library.contains(where: { $0.id == id }) {
            let updated = library + [book]
            try JSONEncoder().encode(updated).write(to: storage.appendingPathComponent("library.json"), options: .atomic)
            library = updated
        }
        return frame
    }
    func open(_ book: BookEntry) throws -> ReaderFrame {
        save()
        let previous = (fixed, publication, document, pager, entry, part, page, lastPages, lastFrame, fontSize)
        var committed = false
        defer {
            if !committed {
                (fixed, publication, document, pager, entry, part, page, lastPages, lastFrame, fontSize) = previous
            }
        }
        let url = storage.appendingPathComponent(book.id)
        let ext = url.pathExtension
        let newFixed: EXReaderFixedDocument?
        let newPublication: EXReaderPublication?
        let newDocument: EXReaderDocument?
        if ext == "pdf" || ext == "cbz" {
            newFixed = try EXReaderFixedDocument(data: Data(contentsOf: url), fallbackFont: font,
                                                format: ext == "pdf" ? .pdf : .cbz)
            newPublication = nil; newDocument = nil
        } else if ext == "epub" {
            newPublication = try EXReaderPublication(file: url)
            newFixed = nil; newDocument = nil
        } else {
            newDocument = try EXReaderDocument(file: url)
            newFixed = nil; newPublication = nil
        }
        fixed = newFixed; publication = newPublication; document = newDocument
        pager = nil; entry = book; lastPages = [:]
        part = defaults.integer(forKey: book.id + ".part")
        page = defaults.integer(forKey: book.id + ".page")
        fontSize = defaults.object(forKey: book.id + ".fontSize") == nil ? 28 : defaults.float(forKey: book.id + ".fontSize")
        if let publication {
            part = min(max(0, part), max(0, publication.parts.count - 1))
            document = try publication.load(part: part)
        } else { part = 0 }
        if let document { pager = try document.pager(font: font, config: config) }
        do {
            let frame = try render()
            committed = true
            return frame
        }
        catch EXReaderError.engine(let code, _) where code == 1 {
            page = 0
            let frame = try render()
            committed = true
            return frame
        }
    }
    func save() {
        guard let entry else { return }
        defaults.set(part, forKey: entry.id + ".part")
        defaults.set(page, forKey: entry.id + ".page")
        defaults.set(fontSize, forKey: entry.id + ".fontSize")
    }
    func render() throws -> ReaderFrame {
        guard let entry else { throw EXReaderError.invalidInput }
        let bitmap: EXReaderBitmap
        let text: String
        var offset = 0
        if let fixed {
            guard page >= 0, page < fixed.pageCount else { throw EXReaderError.invalidInput }
            // The sample has a bounded display surface; exports can use another scale.
            bitmap = try fixed.render(page: page, maximumDimension: 1440)
            text = (try? fixed.text(page: page).string) ?? ""
        } else {
            guard let document, let pager else { throw EXReaderError.invalidInput }
            let result = try pager.get(page: page)
            bitmap = result.bitmap
            let bytes = document.utf8
            guard result.sourceRange.lowerBound >= 0, result.sourceRange.upperBound <= bytes.count else {
                throw EXReaderError.invalidResult
            }
            text = String(decoding: bytes.subdata(in: result.sourceRange), as: UTF8.self)
            offset = result.sourceRange.lowerBound
        }
        let frame = ReaderFrame(bitmap: bitmap, text: text, title: entry.title, part: part, page: page, sourceOffset: offset)
        lastFrame = frame; save()
        return frame
    }
    func turn(_ direction: Int) throws -> ReaderFrame {
        guard entry != nil else { throw EXReaderError.invalidInput }
        if let fixed {
            let index = page + direction
            guard index >= 0, index < fixed.pageCount else { return try render() }
            page = index
            return try render()
        }
        guard let publication else {
            let before = page
            page = max(0, page + direction)
            do { return try render() }
            catch EXReaderError.engine(let code, _) where code == 1 { page = before; return try render() }
        }
        let before = page
        if direction > 0 {
            page += 1
            do { return try render() }
            catch EXReaderError.engine(let code, _) where code == 1 {
                lastPages[part] = before
                if part + 1 >= publication.parts.count { page = before; return try render() }
                part += 1; page = 0
            }
        } else if page > 0 { page -= 1; return try render() }
        else if part > 0 { part -= 1; page = lastPages[part] ?? 0 }
        else { return try render() }
        document = try publication.load(part: part)
        pager = try document!.pager(font: font, config: config)
        return try render()
    }
    func resizeFont(_ delta: Float) throws -> ReaderFrame {
        guard fixed == nil, let document else { return try render() }
        let offset = lastFrame?.sourceOffset ?? 0
        fontSize = min(48, max(18, fontSize + delta))
        pager = try document.pager(font: font, config: config)
        page = 0
        while page < 20000 {
            let frame = try pager!.get(page: page)
            if frame.sourceRange.upperBound > offset || frame.sourceRange.contains(offset) { break }
            page += 1
        }
        do { return try render() }
        catch EXReaderError.engine(let code, _) where code == 1 { page = 0; return try render() }
    }
    func annotate(_ text: String) throws {
        guard let entry, !text.isEmpty else { throw EXReaderError.invalidInput }
        let record = ["book": entry.id, "part": String(part), "page": String(page), "text": text]
        var notes = [[String: String]]()
        let file = storage.appendingPathComponent("notes.json")
        if let data = try? Data(contentsOf: file) { notes = try JSONDecoder().decode([[String: String]].self, from: data) }
        notes.append(record)
        try JSONEncoder().encode(notes).write(to: file, options: .atomic)
    }
}

private func cgImage(_ b: EXReaderBitmap) throws -> CGImage {
    guard b.channels == 4, b.width > 0, b.height > 0,
          b.stride >= b.width * 4, b.pixels.count == b.stride * b.height,
          let provider = CGDataProvider(data: b.pixels as CFData),
          let image = CGImage(width: b.width, height: b.height, bitsPerComponent: 8, bitsPerPixel: 32,
              bytesPerRow: b.stride, space: CGColorSpaceCreateDeviceRGB(),
              bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.last.rawValue),
              provider: provider, decode: nil, shouldInterpolate: true, intent: .defaultIntent) else {
        throw EXReaderError.invalidResult
    }
    return image
}

private final class ReaderModel: ObservableObject {
    @Published var image: CGImage?
    @Published var text = ""
    @Published var title = "EXReader"
    @Published var location = ""
    @Published var status = ""
    @Published var busy = false
    @Published var library: [BookEntry] = []
    private let worker = DispatchQueue(label: "org.exreader.host.reader")
    private var session: ReaderSession?
    private let selfTesting = CommandLine.arguments.contains("--self-test")
    init() {
        worker.async {
            do {
                let folder = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
                    .appendingPathComponent(self.selfTesting ? "EXReaderHostTests" : "EXReaderHost")
                let defaults = self.selfTesting ? UserDefaults(suiteName: "org.exreader.host.selftest." + UUID().uuidString)! : .standard
                self.session = try ReaderSession(storage: folder, defaults: defaults)
                if self.selfTesting { try self.runSelfTest(); return }
                let session = self.session!
                let frame: ReaderFrame
                if let book = session.library.last { frame = try session.open(book) }
                else { frame = try session.importBook(Bundle.main.url(forResource: "Sample", withExtension: "epub")!) }
                self.publish(frame)
            } catch { self.failed(error) }
        }
    }
    private func publish(_ frame: ReaderFrame) {
        do {
            let image = try cgImage(frame.bitmap)
            let books = session?.library ?? []
            DispatchQueue.main.async {
                self.image = image; self.text = frame.text; self.title = frame.title
                self.location = "第 \(frame.part + 1) 部分 · 第 \(frame.page + 1) 页"
                self.library = books; self.status = ""; self.busy = false
            }
        } catch { failed(error) }
    }
    private func failed(_ error: Error) {
        DispatchQueue.main.async {
            self.status = "无法完成操作，请检查文件或换一本书。"; self.busy = false
        }
        if selfTesting { writeTestReport(["passed": false, "error": String(describing: error)]) }
    }
    private func perform(_ action: @escaping (ReaderSession) throws -> ReaderFrame) {
        busy = true
        worker.async {
            do {
                guard let session = self.session else { throw EXReaderError.invalidInput }
                self.publish(try action(session))
            } catch { self.failed(error) }
        }
    }
    func open(_ url: URL) { perform { try $0.importBook(url) } }
    func choose(_ book: BookEntry) { perform { try $0.open(book) } }
    func turn(_ direction: Int) { perform { try $0.turn(direction) } }
    func resize(_ delta: Float) { perform { try $0.resizeFont(delta) } }
    func save() { worker.async { self.session?.save() } }
    func annotate() {
        let selection = text
        worker.async {
            do {
                try self.session?.annotate(selection)
                DispatchQueue.main.async { self.status = "已保存本页摘录" }
            } catch { self.failed(error) }
        }
    }
    private func writeTestReport(_ values: [String: Any]) {
        var result = values
        result["schema"] = 1
        result["engine_version"] = String(cString: exr_version())
        result["source_sha"] = Bundle.main.object(forInfoDictionaryKey: "EXRSourceSHA") as? String ?? ""
        #if os(iOS)
        result["platform"] = "iOS"
        #else
        result["platform"] = "macOS"
        #endif
        let override = ProcessInfo.processInfo.environment["EXR_SELFTEST_OUTPUT"]
        let target = override.map { URL(fileURLWithPath: $0) } ??
            FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
                .appendingPathComponent("exreader-host-selftest.json")
        let directory = target.deletingLastPathComponent()
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        if let data = try? JSONSerialization.data(withJSONObject: result, options: [.prettyPrinted, .sortedKeys]) {
            try? data.write(to: target, options: .atomic)
        }
    }
    private func runSelfTest() throws {
        guard let s = session else { throw EXReaderError.invalidInput }
        var checks = [String]()
        func check(_ value: Bool, _ name: String) throws {
            guard value else { throw EXReaderError.invalidResult }
            checks.append(name)
        }
        let epub = Bundle.main.url(forResource: "Sample", withExtension: "epub")!
        let pdf = Bundle.main.url(forResource: "Sample", withExtension: "pdf")!
        let first = try s.importBook(epub)
        try check(first.bitmap.width == 720, "epub_width")
        try check(first.bitmap.height == 1040, "epub_height")
        try check(!first.bitmap.pixels.isEmpty, "epub_pixels")
        try check(!first.text.isEmpty, "epub_text")
        try check(s.library.contains(where: { $0.id == s.entry!.id }), "library_insert")
        _ = try s.importBook(epub)
        try check(s.library.filter { $0.id == s.entry!.id }.count == 1, "library_deduplicate")
        let a = try s.turn(1)
        try check(a.page > first.page || a.part > first.part, "next_page")
        let b = try s.turn(-1)
        try check(b.bitmap.pixels == first.bitmap.pixels, "previous_page_pixels")
        try check(b.text == first.text, "previous_page_text")
        _ = try s.resizeFont(2)
        try check(s.fontSize == 30, "font_increase")
        _ = try s.resizeFont(-2)
        try check(s.fontSize == 28, "font_decrease")
        let book = s.entry!
        _ = try s.turn(1); s.save()
        let savedPart = s.part, savedPage = s.page
        _ = try s.open(book)
        try check(s.part == savedPart && s.page == savedPage, "resume_position")
        try s.annotate(try s.render().text)
        try check(FileManager.default.fileExists(atPath: s.storage.appendingPathComponent("notes.json").path), "excerpt_saved")
        let fixed = try s.importBook(pdf)
        try check(fixed.bitmap.width > 0 && fixed.bitmap.height > 0, "pdf_dimensions")
        try check(fixed.bitmap.channels == 4, "pdf_channels")
        try check(!fixed.bitmap.pixels.isEmpty, "pdf_pixels")
        try check(!fixed.text.isEmpty, "pdf_text")
        _ = try cgImage(fixed.bitmap)
        try check(true, "image_bridge")
        _ = try s.open(book)
        try check(s.entry?.id == book.id, "switch_book")
        let restored = try ReaderSession(storage: s.storage, defaults: s.defaults)
        try check(restored.library.count == s.library.count, "library_reopen")
        let last = try restored.open(book)
        try check(last.part == savedPart && last.page == savedPage, "resume_after_session_reopen")
        publish(last)
        writeTestReport(["passed": true, "checks": checks, "check_count": checks.count])
    }
}

private struct ReaderView: View {
    @StateObject var model = ReaderModel()
    @State private var importing = false
    @State private var selecting = false
    @Environment(\.scenePhase) var phase
    var body: some View {
        VStack(spacing: 0) {
            Text(model.title).font(.headline).lineLimit(1).padding(.top)
            VStack(spacing: 8) {
                if !model.library.isEmpty {
                    Menu("书架") {
                        ForEach(model.library) { book in Button(book.title) { model.choose(book) } }
                    }.accessibilityIdentifier("library")
                }
                GeometryReader { geometry in
                    if let image = model.image {
                        Image(decorative: image, scale: 1).resizable().scaledToFit()
                            .frame(width: geometry.size.width, height: geometry.size.height)
                            .accessibilityLabel(model.text)
                            .accessibilityIdentifier("page")
                    } else { ProgressView().frame(width: geometry.size.width, height: geometry.size.height) }
                }.background(Color.white)
                Text(model.location).font(.caption)
                HStack {
                    Button("上一页") { model.turn(-1) }.accessibilityIdentifier("previous")
                    Button("下一页") { model.turn(1) }.accessibilityIdentifier("next")
                    Button("小字") { model.resize(-2) }
                    Button("大字") { model.resize(2) }
                }
                HStack {
                    Button("选文") { selecting = true }
                    Button("摘录本页") { model.annotate() }
                    Button("打开文件") { importing = true }.accessibilityIdentifier("open")
                }
                if model.busy { ProgressView() }
                if !model.status.isEmpty { Text(model.status).font(.caption).accessibilityIdentifier("status") }
            }.padding().disabled(model.busy)
        }
        .fileImporter(isPresented: $importing, allowedContentTypes: [.data], allowsMultipleSelection: false) { result in
            if case .success(let urls) = result, let url = urls.first { model.open(url) }
        }
        .sheet(isPresented: $selecting) {
            VStack {
                ScrollView { Text(model.text).textSelection(.enabled).padding() }
                Button("完成") { selecting = false }.padding()
            }
        }
        .onChange(of: phase) { value in if value != .active { model.save() } }
    }
}

@main struct EXReaderHostApp: App {
    var body: some Scene {
        WindowGroup { ReaderView() }
    }
}
