// SPDX-License-Identifier: MIT
import Foundation
import CoreGraphics
import CryptoKit
import CEXReader
import CReaderProduct
import Combine
import Darwin

// Product shelf state is independent of SDK pagination and its owner handles.
// Only three catalog pages are retained; async results carry a query generation.
final class HostShelf: ObservableObject {
    typealias Loader = (String, HostShelfKey?, Bool, Bool, @escaping (Result<[HostShelfBook], Error>) -> Void) -> Void
    @Published private(set) var rows: [HostShelfBook] = []
    @Published var query = ""
    @Published private(set) var loading = false
    @Published private(set) var error = ""
    @Published private(set) var restoreRevision = 0
    @Published private var viewportRevision = 0
    private(set) var restoreKey: String?
    private(set) var top: HostShelfKey?
    private(set) var before = false
    private(set) var after = false
    private(set) var generation = 0
    private(set) var appliedGeneration = -1
    private(set) var discarded = 0
    private(set) var maximumRows = 0
    private(set) var selected: String?
    private var loader: Loader?
    private var debounce: DispatchWorkItem?
    private var visible = Set<String>()
    private let defaults: UserDefaults
    private var appliedQuery = ""
    private var lastLayout: TimeInterval?
    private var layoutIntervals: [Double] = []
    private var viewportSize = CGSize.zero
    private let createdUptime = ProcessInfo.processInfo.systemUptime
    private var firstLayoutUptime: TimeInterval?
    private var awaitingLayoutKey: String?
    private var issuedRestoreRevision = -1
    private var probeRevision = -1
    private var probePositions: [String: CGRect] = [:]
    private var probeSize = CGSize.zero
    private var probeFlushScheduled = false
    private var lastProbeMovement: TimeInterval?
    private var pendingPage: (() -> Void)?
    private var pendingPageWork: DispatchWorkItem?
    // Even epochs precede the native scroll; odd epochs follow its issue.
    var geometryRevision: Int { restoreRevision * 2 + (issuedRestoreRevision == restoreRevision ? 1 : 0) }
    var needsScroll: Bool { awaitingLayoutKey != nil && issuedRestoreRevision != restoreRevision }
    private var pendingSave: DispatchWorkItem?
#if EXR_APPLE_SHELF_REVIEW
    private var reviewVisibleFrames: [[String: Any]] = []
    private var reviewGeometryRevision = -1

    private func recordReviewTrace(_ line: String) {
        guard let root = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first else { return }
        let folder = root.appendingPathComponent("EXReader", isDirectory: true)
        try? FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let url = folder.appendingPathComponent("shelf-layout-trace.jsonl")
        if !FileManager.default.fileExists(atPath: url.path) { FileManager.default.createFile(atPath: url.path, contents: nil) }
        guard let handle = try? FileHandle(forWritingTo: url) else { return }
        defer { try? handle.close() }
        _ = try? handle.seekToEnd()
        try? handle.write(contentsOf: Data((line + "\n").utf8))
    }
#endif

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        query = defaults.string(forKey: "EXRShelfQuery") ?? ""
        selected = defaults.string(forKey: "EXRShelfSelected")
        if let data = defaults.data(forKey: "EXRShelfTop") { top = try? JSONDecoder().decode(HostShelfKey.self, from: data) }
    }
    deinit { debounce?.cancel(); pendingSave?.cancel(); pendingPageWork?.cancel() }

    func connect(_ load: @escaping Loader) {
        guard loader == nil else { return }
        loader = load
        reset(anchor: top)
    }

    func search() {
        debounce?.cancel()
        pendingPageWork?.cancel(); pendingPage = nil
        query = String(String.UnicodeScalarView(query.precomposedStringWithCanonicalMapping.unicodeScalars.prefix(256)))
        generation += 1
        rows = []; visible = []; top = nil; awaitingLayoutKey = nil; before = false; after = false; loading = true
        defaults.removeObject(forKey: "EXRShelfTop")
        defaults.set(query, forKey: "EXRShelfQuery")
        let work = DispatchWorkItem { [weak self] in self?.reset(anchor: nil) }
        debounce = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.18, execute: work)
    }

    func refresh() {
        guard loader != nil else { return }
        save()
        reset(anchor: top)
    }

    private func reset(anchor: HostShelfKey?) {
        pendingPageWork?.cancel(); pendingPage = nil
        generation += 1; loading = false; error = ""
        rows = []; visible = []; awaitingLayoutKey = nil; before = false; after = false
        request(anchor: anchor, previous: false, inclusive: true, replacing: true)
    }

    private func request(anchor: HostShelfKey?, previous: Bool, inclusive: Bool, replacing: Bool) {
        guard !loading, let loader else { return }
        loading = true
        let token = generation, requested = query
        loader(requested, anchor, previous, inclusive) { [weak self] result in
            self?.receive(result, token: token, requested: requested, anchor: anchor, previous: previous, replacing: replacing)
        }
    }

    private func receive(_ result: Result<[HostShelfBook], Error>, token: Int, requested: String,
                         anchor: HostShelfKey?, previous: Bool, replacing: Bool, settled: Bool = false) {
        guard generation == token, query == requested else { discarded += 1; return }
        loading = false
        switch result {
            case .failure(let error): self.error = error.localizedDescription
            case .success(let page):
                guard page.count <= 50 else { self.error = "书架分页超过上限"; return }
                if !replacing && page.isEmpty {
                    if previous { self.before = false } else { self.after = false }
                    if self.awaitingLayoutKey != nil { self.restoreRevision += 1 }
                    return
                }
                if replacing && page.isEmpty && anchor != nil && !previous {
                    self.request(anchor: anchor, previous: true, inclusive: false, replacing: true)
                    return
                }
                // A prepend/eviction moves existing rows. Wait for measured
                // native movement to stop before changing those coordinates.
                if !replacing, previous || self.rows.count + page.count > 150, !settled,
                   let lastProbeMovement, ProcessInfo.processInfo.systemUptime - lastProbeMovement < 0.15 {
                    loading = true
                    pendingPage = { [weak self] in
                        self?.receive(result, token: token, requested: requested, anchor: anchor,
                                      previous: previous, replacing: replacing, settled: true)
                    }
                    schedulePendingPage()
                    return
                }
                let retainedTop = replacing ? anchor :
                    (self.rows.first(where: { $0.id == self.awaitingLayoutKey })?.key ?? self.top)
                // Appending within the cache changes no existing row position.
                // A forced scroll here races an in-flight native drag/deceleration.
                let shiftsExistingRows = replacing || previous || self.rows.count + page.count > 150
                if !replacing && self.rows.count + page.count > 150,
                   let index = self.rows.firstIndex(where: { $0.key == self.top }) {
                    if (!previous && index < 50) || (previous && index + self.visible.count > self.rows.count - 50) { return }
                }
                if replacing {
                    self.rows = page
                    self.before = anchor != nil && (!previous || page.count == 50)
                    self.after = !previous && page.count == 50
                } else if previous {
                    self.rows.insert(contentsOf: page, at: 0)
                    self.before = page.count == 50
                    if self.rows.count > 150 { self.rows.removeLast(self.rows.count - 150); self.after = true }
                } else {
                    self.rows.append(contentsOf: page)
                    self.after = page.count == 50
                    if self.rows.count > 150 { self.rows.removeFirst(self.rows.count - 150); self.before = true }
                }
                self.maximumRows = max(self.maximumRows, self.rows.count)
                self.appliedGeneration = token; self.appliedQuery = requested
                if shiftsExistingRows {
                    self.restoreKey = retainedTop.flatMap { key in self.rows.contains(where: { $0.key == key }) ? key.key : nil } ?? self.rows.first?.id
                    self.awaitingLayoutKey = self.restoreKey
                    self.restoreRevision += 1
                }
        }
    }

    private func schedulePendingPage() {
        guard pendingPage != nil else { return }
        pendingPageWork?.cancel()
        let work = DispatchWorkItem { [weak self] in
            guard let self else { return }
            let apply = self.pendingPage; self.pendingPage = nil; apply?()
        }
        pendingPageWork = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.15, execute: work)
    }

    func measureProbe(key: String?, frame: CGRect, size: CGSize, revision: Int) {
        guard revision == geometryRevision else { return }
        if probeRevision != revision {
            probeRevision = revision; probePositions = [:]; probeSize = .zero
        }
        if let key {
            if probePositions[key] != frame { lastProbeMovement = ProcessInfo.processInfo.systemUptime; schedulePendingPage() }
            probePositions[key] = frame
        } else { probeSize = size }
        guard !probeFlushScheduled else { return }
        probeFlushScheduled = true
        DispatchQueue.main.async { [weak self] in
            guard let self else { return }
            self.probeFlushScheduled = false
            guard self.probeRevision == self.geometryRevision else { return }
            self.probePositions = self.probePositions.filter { key, _ in self.rows.contains(where: { $0.id == key }) }
            // A row callback is a partial layout, not the complete visible
            // ordering. Only a single-row shelf has an unambiguous first row.
            guard self.rows.count == 1 else { return }
            self.observe(self.probePositions, size: self.probeSize, revision: self.probeRevision)
        }
    }

    func observe(_ positions: [String: CGRect], size: CGSize, revision: Int, complete: Bool = true) {
        if size.height > 0, revision == geometryRevision {
            if probeRevision == revision, positions != probePositions {
                lastProbeMovement = ProcessInfo.processInfo.systemUptime
                schedulePendingPage()
            }
            probeRevision = revision; probePositions = positions; probeSize = size
        }
#if EXR_APPLE_SHELF_REVIEW
        if complete, revision == geometryRevision {
            let frames: [[String: Any]] = size.height > 0 ? positions
                .filter { $0.value.maxY > 0 && $0.value.minY < size.height }
                .sorted { $0.value.minY < $1.value.minY }.prefix(3).map {
                    ["key": $0.key, "min_y": Double($0.value.minY), "max_y": Double($0.value.maxY)]
                } : []
            if reviewGeometryRevision != revision || !NSArray(array: reviewVisibleFrames).isEqual(to: frames) {
                objectWillChange.send()
                reviewGeometryRevision = revision
                reviewVisibleFrames = frames
            }
        }
        if let awaitingLayoutKey {
            var trace: [String: Any] = ["incoming_epoch": revision, "expected_epoch": geometryRevision,
                "issued_revision": issuedRestoreRevision, "needs_scroll": needsScroll,
                "complete_snapshot": complete,
                "frame_count": positions.count, "width": Double(size.width), "height": Double(size.height),
                "target_key": awaitingLayoutKey]
            if let frame = positions[awaitingLayoutKey] {
                trace["target_frame"] = ["min_y": Double(frame.minY), "max_y": Double(frame.maxY),
                    "width": Double(frame.width), "height": Double(frame.height)]
            }
            if let data = try? JSONSerialization.data(withJSONObject: trace, options: [.sortedKeys]),
               let value = String(data: data, encoding: .utf8) { recordReviewTrace("SHELF RAW GEOMETRY \(value)") }
        }
#endif
        guard size.height > 0, revision == geometryRevision else { return }
        if viewportSize != .zero && viewportSize != size {
            viewportSize = size; restoreViewport(); return
        }
        viewportSize = size
        guard complete else { return }
        guard awaitingLayoutKey == nil || issuedRestoreRevision == restoreRevision else { return }
        let ordered = positions.filter { $0.value.maxY > 0 && $0.value.minY < size.height }
            .sorted { $0.value.minY < $1.value.minY }
        let newVisible = Set(ordered.map(\.key))
        guard let first = ordered.first, let index = rows.firstIndex(where: { $0.id == first.key }) else { return }
        let lastIndex = ordered.last.flatMap { last in rows.firstIndex(where: { $0.id == last.key }) } ?? index
        let acknowledged = awaitingLayoutKey != nil
        if let awaitingLayoutKey {
            if first.key != awaitingLayoutKey {
                // Native List clamps an old top near the global end when a
                // taller viewport cannot align that row at the top. Confirm
                // only real visible target + terminal-row geometry.
                guard let target = positions[awaitingLayoutKey], target.maxY > 0, target.minY < size.height,
                      let last = rows.last, let tail = positions[last.id], tail.maxY > 0,
                      tail.maxY <= size.height + 1 else { return }
                if after {
                    if !loading { request(anchor: last.key, previous: false, inclusive: false, replacing: false) }
                    return
                }
                restoreKey = first.key
            }
            self.awaitingLayoutKey = nil
        }
        if firstLayoutUptime == nil, !loading, generation == appliedGeneration {
            firstLayoutUptime = ProcessInfo.processInfo.systemUptime
        }
        if acknowledged || visible != newVisible || top != rows[index].key {
            let now = ProcessInfo.processInfo.systemUptime
            if let lastLayout { layoutIntervals.append((now - lastLayout) * 1000) }
            if layoutIntervals.count > 512 { layoutIntervals.removeFirst(layoutIntervals.count - 512) }
            self.lastLayout = now
            visible = newVisible
            viewportRevision += 1
            pendingSave?.cancel()
            let token = generation, key = rows[index].key
            let work = DispatchWorkItem { [weak self] in
                guard let self, self.generation == token, self.top == key else { return }
                self.save()
            }
            pendingSave = work
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3, execute: work)
        }
        top = rows[index].key
        guard !loading, appliedGeneration == generation else { return }
        if after && lastIndex >= rows.count - 12, let last = rows.last {
            request(anchor: last.key, previous: false, inclusive: false, replacing: false)
        } else if before && index < 12, let first = rows.first {
            request(anchor: first.key, previous: true, inclusive: false, replacing: false)
        }
    }

    func restoreViewport() {
        restoreKey = awaitingLayoutKey ?? top?.key ?? restoreKey
        awaitingLayoutKey = restoreKey
        restoreRevision += 1
    }
    func didScroll(revision: Int) {
        guard revision == restoreRevision, issuedRestoreRevision != revision else { return }
        issuedRestoreRevision = revision
#if EXR_APPLE_SHELF_REVIEW
        recordReviewTrace("SHELF SCROLL ISSUED revision=\(revision) epoch=\(geometryRevision)")
#endif
        viewportRevision += 1
    }
    func choose(_ book: HostShelfBook) { selected = book.id; defaults.set(book.id, forKey: "EXRShelfSelected"); save() }
    func save() {
        // Never pair a new query with an old viewport, or clear a valid anchor
        // while a same-query refresh is temporarily between pages.
        guard appliedGeneration == generation, appliedQuery == query, awaitingLayoutKey == nil else { return }
        defaults.set(query, forKey: "EXRShelfQuery")
        let encoder = JSONEncoder()
        encoder.outputFormatting = .sortedKeys
        if let top, let bytes = try? encoder.encode(top) { defaults.set(bytes, forKey: "EXRShelfTop") }
    }

    var observation: String {
        var usage = rusage()
        getrusage(RUSAGE_SELF, &usage)
        var value: [String: Any] = ["query": query, "generation": generation, "applied_generation": appliedGeneration,
            "loading": loading, "restoring_layout": awaitingLayoutKey != nil,
            "cached_rows": rows.count, "max_cached_rows": maximumRows,
            "page_limit": 50, "cache_limit": 150, "has_before": before, "has_after": after,
            "top_key": top?.key ?? "", "selected_key": selected ?? "", "discarded": discarded,
            "keys": rows.map(\.id), "visible_keys": rows.filter { visible.contains($0.id) }.map(\.id),
            "layout_revision": viewportRevision, "process_peak_rss_bytes": usage.ru_maxrss,
            "shelf_created_to_first_visible_layout_ms": firstLayoutUptime.map { ($0 - createdUptime) * 1000 } ?? -1,
            "layout_observation_intervals_ms": layoutIntervals]
#if EXR_APPLE_SHELF_REVIEW
        value["visible_frames"] = reviewVisibleFrames
        value["observed_geometry_revision"] = reviewGeometryRevision
        value["viewport_height"] = Double(viewportSize.height)
        value["requested_restore_key"] = restoreKey ?? ""
        value["geometry_revision"] = geometryRevision
        value["issued_restore_revision"] = issuedRestoreRevision
#endif
        return (try? String(data: JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]), encoding: .utf8)) ?? "{}"
    }
}

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

private enum HostImportPublication {
    // ponytail: serialize only SDK/catalog publication and startup repair
    // across windows; independent reading/rendering keeps its owner queue.
    private static let lock = NSRecursiveLock()
    static func perform<T>(_ operation: () throws -> T) rethrows -> T {
        lock.lock()
        defer { lock.unlock() }
        return try operation()
    }
}

extension HostCatalog {
    @discardableResult
    func attach(book: HostBook, fingerprint: HostSourceFingerprint, library: HostLibrary) throws -> Int64 {
        try attach(format: fingerprint.format, sha256: fingerprint.sha256, bytes: fingerprint.bytes,
                   title: book.title, author: book.author, sdkID: book.id,
                   locationKind: library.locationKind(book: book))
    }

    func repairMissing(library: HostLibrary, books: [HostBook], cancel: HostCancelBox? = nil) throws -> [String] {
        try HostImportPublication.perform {
            let mapped = try localIDs()
            var failures: [String] = []
            // One SDK enumeration is supplied by startup. Ascending IDs ensure
            // historical duplicate sources retain the smallest ID and its real mode.
            for book in books.sorted(by: { $0.id < $1.id }) where !mapped.contains(book.id) {
                try cancel?.check()
                do {
                    let fingerprint = try library.sourceFingerprint(book: book, cancel: cancel)
                    try attach(book: book, fingerprint: fingerprint, library: library)
                } catch let error as HostError where error.isCancelled { throw error }
                catch { failures.append("\(book.id)：\(error.localizedDescription)") }
            }
            return failures
        }
    }
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

    func listBooks(_ storedBooks: [HostBook]? = nil) throws -> [HostBookRow] {
        // The public SDK enumeration is still transiently unbounded. Do not
        // retain its complete metadata array in the UI's compatibility rows.
        try (storedBooks ?? library.books()).prefix(50).map { book in
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

    func importBook(url: URL, cancel: HostCancelBox, catalog: HostCatalog? = nil) throws -> (Int64, Bool) {
        try begin(cancel)
        if slowDelay > 0 { try waitCancellable(cancel, seconds: slowDelay) }
        let title = url.lastPathComponent
        guard let catalog else { return try library.importUnique(file: url, title: title, cancel: cancel) }
        guard !title.utf8.contains(0), title.unicodeScalars.count <= 4096 else {
            throw HostError.invalidInput("书名包含空字符或超过长度上限")
        }
        let copy = try HostImportCopy(file: url,
            root: library.path.deletingLastPathComponent().appendingPathComponent("import-staging", isDirectory: true), cancel: cancel)
        return try HostImportPublication.perform {
            var published = false, created = false
            var importedID: Int64?
            do {
                let result = try library.importUnique(file: copy.url, title: title, cancel: cancel)
                let id = result.id
                importedID = id; created = result.created
#if EXR_APPLE_HOST_REVIEW
                try HostSDKReview.event?("mapping-after-sdk")
#endif
                guard let stored = try library.books().first(where: { $0.id == id }) else {
                    throw HostError.invalidResult("SDK 导入后未找到原件记录")
                }
                let actual = try library.sourceFingerprint(book: stored, cancel: cancel)
                guard actual == copy.fingerprint else { throw HostError.invalidResult("SDK 存储原件与私有导入副本不一致") }
                try cancel.commit {}
                published = true
#if EXR_APPLE_HOST_REVIEW
                try HostSDKReview.event?("mapping-before-product")
#endif
                let canonicalID = try catalog.attach(book: stored, fingerprint: actual, library: library)
                try copy.close()
                return (canonicalID, created)
            } catch {
                var failure = error
                if !published {
                    if created, let importedID {
                        do { try library.delete(bookID: importedID) }
                        catch { failure = HostError.invalidResult("导入回滚失败；书库保留记录 \(importedID)：\(error.localizedDescription)") }
                    }
                }
                do { try copy.close() }
                catch let cleanup {
                    let detail = "私有副本清理失败：\(cleanup.localizedDescription)；原错误：\(failure.localizedDescription)"
                    if published { throw HostError.importRepairPending(detail) }
                    throw HostError.invalidResult(detail)
                }
                if published { throw HostError.importRepairPending(failure.localizedDescription) }
                throw failure
            }
        }
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
        return flat.isEmpty ? "第 \(page) 页" : "第 \(page) 页：\(flat)"
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
    @Published private(set) var productIndexPending = false
    @Published var stateHash = "—"
    @Published var busy = false
    @Published private(set) var syncPreparing = false
    @Published var notes: [HostNoteRow] = []
    @Published var showLibrary = true
    @Published var frameCount = 0
    @Published private(set) var uiTestTrace = ""
#if EXR_APPLE_IMPORT_REVIEW
    @Published private(set) var importMappingProbe = ""
#endif
    private var uiTestEvents: [String] = []
    private var uiTestEventCount = 0
    private var pagePart = -1
    private var pagePath = ""
    private(set) var fontSHA = ""

    private let queue = DispatchQueue(label: "org.exreader.host.reader")
    private var session: HostSession?
    private var catalog: HostCatalog?
    private var token = 0
    private var activeCancel: HostCancelBox?
    private var syncCancel: HostCancelBox?
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
    private let defaults: UserDefaults
    private let accountProfile: HostAccountProfile?
    private let accounts: HostAccounts?
    let accountSession: HostAccountSession?
    private let testFixtures = ProcessInfo.processInfo.arguments.contains("-EXRUITestFixtures")
    private let freshState = ProcessInfo.processInfo.arguments.contains("-EXRFreshState")
    private var slowDelay: Double = 0

    init(profile: HostAccountProfile? = nil, accounts: HostAccounts? = nil) {
        self.accountProfile = profile
        self.accounts = accounts
        self.accountSession = profile.flatMap { accounts?.controller(for: $0) }
        self.defaults = profile.flatMap { UserDefaults(suiteName: "org.exreader.account." + $0.id) } ?? .standard
    }

    deinit {
        let ownedCatalog = catalog
        queue.async {
            try? ownedCatalog?.close()
        }
    }

    var showsTestFixtures: Bool { testFixtures }
    var shelfDefaults: UserDefaults { defaults }

    func closeAccountSession() {
        syncCancel?.cancel()
        accountSession?.close()
    }

    func synchronizeAccount() {
        guard !busy, !syncPreparing, let profile = accountProfile, let accounts, let accountSession,
              !accountSession.running, !accountSession.preparing else { return }
        do {
            let authorization = try accounts.authorization(for: profile)
            let cancel = HostCancelBox()
            try accountSession.beginPreparation { cancel.cancel() }
            syncCancel = cancel; syncPreparing = true
            prepareSyncPage(after: nil, profile: profile, authorization: authorization, cancel: cancel)
        } catch { errorText = describe(error) }
    }

    private func prepareSyncPage(after: String?, profile: HostAccountProfile, authorization: Data, cancel: HostCancelBox) {
        queue.async {
            do {
                try cancel.check()
                guard let session = self.session, let catalog = self.catalog else { throw HostError.invalidInput("书库尚未就绪") }
                let directory = try self.storageFolder()
                let page = try catalog.syncPage(after: after)
                try catalog.withHistory { history in
                    for book in page {
                        try session.library.exportSyncOriginal(bookID: book.sdkID,
                            expected: HostSourceFingerprint(format: book.format, sha256: book.sha256, bytes: book.bytes),
                            directory: directory.appendingPathComponent("sync-originals", isDirectory: true), cancel: cancel)
                        try catalog.bootstrapVerified(book, store: history)
                    }
                }
                try cancel.check()
                if page.count == 50 {
                    self.prepareSyncPage(after: page.last?.key, profile: profile, authorization: authorization, cancel: cancel)
                } else {
                    DispatchQueue.main.async {
                        self.syncPreparing = false; self.accountSession?.finishPreparation()
                        guard !cancel.isCancelled else { return }
                        do {
                            try self.accountSession?.start(profile: profile, directory: directory, authorization: authorization) { [weak self] in
                                self?.statusText = "本轮云盘扫描结束；阅读位置保持不变"
                            }
                        } catch { self.errorText = self.describe(error) }
                    }
                }
            } catch {
                DispatchQueue.main.async {
                    self.syncPreparing = false; self.accountSession?.finishPreparation()
                    if !cancel.isCancelled { self.errorText = self.describe(error) }
                }
            }
        }
    }

    private func traceUITest(_ event: String) {
        guard testFixtures else { return }
        uiTestEventCount += 1
        uiTestEvents.append("\(uiTestEventCount):token=\(token),busy=\(busy),started=\(started):\(event)")
        if uiTestEvents.count > 16 { uiTestEvents.removeFirst(uiTestEvents.count - 16) }
        uiTestTrace = uiTestEvents.joined(separator: " | ")
    }

    func observeUITestScene(_ phase: String) { traceUITest("scene=\(phase)") }

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
        traceUITest("startup-request")
        guard !started else { return }
        started = true
        busy = true
        traceUITest("startup-worker-scheduled")
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
                    for name in ["library.sqlite", "library.sqlite-wal", "library.sqlite-shm",
                                 "reader-catalog.db", "reader-catalog.db-wal", "reader-catalog.db-shm",
                                 "reader-catalog.db-journal"] {
                        try? FileManager.default.removeItem(at: folder.appendingPathComponent(name))
                    }
                    self.defaults.removeObject(forKey: "EXRLastBook")
                }
                guard let migration = Bundle.main.url(forResource: HostCatalog.resourceName, withExtension: "sql") else {
                    throw HostError.invalidInput("缺少原始产品书库迁移资源")
                }
#if EXR_APPLE_SHELF_REVIEW
                if ProcessInfo.processInfo.arguments.contains("-EXRShelfSeed"),
                   !FileManager.default.fileExists(atPath: folder.appendingPathComponent("library.sqlite").path) {
                    for (resource, destination) in [("ShelfSeed-library", "library.sqlite"), ("ShelfSeed-reader-catalog", "reader-catalog.db")] {
                        let ext = resource == "ShelfSeed-library" ? "sqlite" : "db"
                        guard let source = Bundle.main.url(forResource: resource, withExtension: ext) else {
                            throw HostError.invalidInput("缺少实际 SDK 原件书库")
                        }
                        try FileManager.default.copyItem(at: source, to: folder.appendingPathComponent(destination))
                    }
                    for key in ["EXRLastBook", "EXRShelfQuery", "EXRShelfTop", "EXRShelfSelected"] { self.defaults.removeObject(forKey: key) }
                }
#endif
                let catalog = try HostCatalog(path: folder.appendingPathComponent("reader-catalog.db"),
                                              migrationURL: migration, ownerQueue: self.queue)
#if EXR_APPLE_IMPORT_REVIEW
                self.configureImportMappingReview()
#endif
                let library = try HostLibrary(path: folder.appendingPathComponent("library.sqlite"))
                try HostImportCopy.discardInterrupted(in: folder.appendingPathComponent("import-staging", isDirectory: true))
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
                let (storedBooks, repairProblems) = try HostImportPublication.perform {
                    let books = try library.books()
                    return (books, try catalog.repairMissing(library: library, books: books))
                }
                let rows = try session.listBooks(storedBooks)
                self.catalog = catalog
#if EXR_APPLE_IMPORT_REVIEW
                self.refreshImportMappingProbe(catalog, folder: folder)
#endif
                let lastID = (self.defaults.object(forKey: "EXRLastBook") as? NSNumber)?.int64Value
                let lastPresent = lastID.map { id in storedBooks.contains(where: { $0.id == id }) } ?? false
                DispatchQueue.main.async {
                    self.traceUITest("startup-publish rows=\(rows.count)")
                    self.books = rows
                    self.productIndexPending = !repairProblems.isEmpty
                    self.busy = false
                    if !repairProblems.isEmpty {
                        self.errorText = "产品索引待修复：" + repairProblems.joined(separator: "；")
                        self.statusText = "书籍已保留，产品索引待修复"
                    } else if let lastID, lastPresent {
                        self.openBook(id: lastID)
                    } else {
                        self.busy = false
                    }
                    self.traceUITest("startup-finished")
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

#if EXR_APPLE_IMPORT_REVIEW
    private func configureImportMappingReview() {
        let arguments = ProcessInfo.processInfo.arguments
        let pause: (String) -> Void = { [weak self] phase in
            DispatchQueue.main.async { self?.statusText = phase }
            // The independent UI suite kills this real process while paused.
            // Ordinary hosts contain neither the observer nor this pause.
            Thread.sleep(forTimeInterval: 180)
        }
        HostSDKReview.event = arguments.contains("-EXRMappingPausePublished") ? { event in
            if event == "mapping-before-product" { pause("导入已保存，正在登记") }
        } : nil
        if arguments.contains("-EXRMappingRejectTransaction") {
            HostCatalog.afterProductBookWrite = { throw HostError.invalidResult("独立验收中的产品事务拒绝") }
        } else {
            HostCatalog.afterProductBookWrite = arguments.contains("-EXRMappingPauseTransaction") ? {
                pause("登记事务已开始")
            } : nil
        }
    }

    private func refreshImportMappingProbe(_ catalog: HostCatalog, folder: URL) {
        do {
            let books = try catalog.scalar("SELECT count(*) FROM reader_books")
            let local = try catalog.scalar("SELECT count(*) FROM reader_local_books")
            let epub = try catalog.scalar("SELECT count(*) FROM reader_local_books WHERE location_kind='epub_chapter'")
            let reflow = try catalog.scalar("SELECT count(*) FROM reader_local_books WHERE location_kind='reflow_global'")
            let fixed = try catalog.scalar("SELECT count(*) FROM reader_local_books WHERE location_kind='fixed_page'")
            let keys = try catalog.text("SELECT coalesce(group_concat(book_key,'|'),'') FROM (SELECT book_key FROM reader_books ORDER BY book_key LIMIT 16)")
            let staging = (try? FileManager.default.contentsOfDirectory(atPath: folder.appendingPathComponent("import-staging").path).count) ?? 0
            let value = "books=\(books);local=\(local);epub_chapter=\(epub);reflow_global=\(reflow);fixed_page=\(fixed);staging=\(staging);keys=\(keys)"
            DispatchQueue.main.async { self.importMappingProbe = value }
        } catch {
            DispatchQueue.main.async { self.importMappingProbe = "error=\(error.localizedDescription)" }
        }
    }
#endif

    private func storageFolder() throws -> URL {
        let base = try FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask,
                                               appropriateFor: nil, create: true)
        let root = base.appendingPathComponent("EXReader", isDirectory: true)
        return accountProfile?.directory(in: root) ?? root
    }

    private func stateFileURL() throws -> URL {
        if accountProfile != nil { return try storageFolder().appendingPathComponent("host-state.json") }
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
            if imported { self.traceUITest("import-publish source-token=\(token),status=\(status)") }
            guard token == self.token else { return }
            if case .success(let rows) = books { self.books = rows }
            if case .success(let rows) = notes { self.notes = rows }
            if case .success(let value) = hash { self.stateHash = value }
            if imported { self.showLibrary = true }
            if imported { self.traceUITest("import-committed rows=\(self.books.count)") }
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
        openBook(HostBookRow(id: id, title: "", detail: "", isFixed: false, position: 0))
    }

    func loadShelf(query: String, anchor: HostShelfKey?, before: Bool, inclusive: Bool,
                   completion: @escaping (Result<[HostShelfBook], Error>) -> Void) {
        queue.async {
            let result = Result { () throws -> [HostShelfBook] in
                guard let catalog = self.catalog else { throw HostError.invalidInput("产品书库未就绪") }
                return try catalog.shelf(query: query, anchor: anchor, before: before, inclusive: inclusive)
            }
            DispatchQueue.main.async { completion(result) }
        }
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
        traceUITest("import-request file=\(url.lastPathComponent)")
        guard !busy else { traceUITest("import-rejected-busy"); return }
        let (myToken, box) = begin()
        statusText = "正在导入…"
        traceUITest("import-accepted")
        queue.async {
            DispatchQueue.main.async { self.traceUITest("import-worker-begin source-token=\(myToken)") }
            let scoped = url.startAccessingSecurityScopedResource()
            defer { if scoped { url.stopAccessingSecurityScopedResource() } }
            do {
                guard let session = self.session, let catalog = self.catalog else { throw HostError.invalidInput("书库未就绪") }
                let (bookID, created) = try session.importBook(url: url, cancel: box, catalog: catalog)
#if EXR_APPLE_IMPORT_REVIEW
                self.refreshImportMappingProbe(catalog, folder: session.library.path.deletingLastPathComponent())
#endif
                DispatchQueue.main.async { self.traceUITest("import-sdk-return source-token=\(myToken),book=\(bookID),created=\(created)") }
                self.completeMutation(session: session, token: myToken,
                                      status: created ? "已导入 \(url.lastPathComponent)" : "已存在，复用书架记录",
                                      imported: true)
            } catch {
#if EXR_APPLE_IMPORT_REVIEW
                if let catalog = self.catalog, let session = self.session {
                    self.refreshImportMappingProbe(catalog, folder: session.library.path.deletingLastPathComponent())
                }
#endif
                if case HostError.importRepairPending = error, let session = self.session {
                    let rows = Result { try session.listBooks() }
                    self.appendLog("import retained; product repair pending: \(self.describe(error))")
                    DispatchQueue.main.async {
                        guard myToken == self.token else { return }
                        if case .success(let books) = rows { self.books = books }
                        self.productIndexPending = true
                        self.errorText = self.describe(error)
                        self.statusText = "书籍已保存，产品索引待修复"
                        self.finish()
                    }
                    return
                }
                DispatchQueue.main.async {
                    guard myToken == self.token else { return }
                    self.fail(error)
                }
            }
        }
    }

    func importFixture(_ name: String, extension ext: String) {
        traceUITest("fixture-request name=\(name).\(ext)")
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
        traceUITest("cancel-request")
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
        traceUITest("failure=\(describe(error))")
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
    func reviewCleanImportStaging(_ root: URL) throws {
        try queue.sync { try HostImportCopy.discardInterrupted(in: root) }
    }

    // Install an actual session in the command-line cloud consumer without
    // relying on application-bundle startup resources or replacing SDK calls.
    func installReviewSession(_ session: HostSession, snapshot: HostSnapshot, catalogMigration: URL) throws {
        // start() creates this directory for the real app. The headless
        // consumer must satisfy the same persistence prerequisite explicitly.
        let stateFolder = try stateFileURL().deletingLastPathComponent()
        try FileManager.default.createDirectory(at: stateFolder, withIntermediateDirectories: true)
        try queue.sync {
            self.catalog = try HostCatalog(path: session.library.path.deletingLastPathComponent()
                .appendingPathComponent("reader-catalog.db"), migrationURL: catalogMigration, ownerQueue: queue)
        }
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
