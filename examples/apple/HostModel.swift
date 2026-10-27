// SPDX-License-Identifier: MIT
import Foundation
import CoreGraphics
import CryptoKit
import CEXReader
import CReaderProduct
import Combine
import Darwin

#if EXR_APPLE_PAGE_THEME
enum HostPageThemeChoice: String, CaseIterable {
    case original, light, dark, system
    var title: String {
        switch self { case .original: return "原书"; case .light: return "浅色"; case .dark: return "深色"; case .system: return "跟随系统" }
    }
}

struct HostPagePalette: Equatable {
    let foreground: UInt32?
    let background: UInt32?
    static let original = HostPagePalette(foreground: nil, background: nil)
    static func resolve(_ choice: HostPageThemeChoice, systemDark: Bool) -> HostPagePalette {
        if choice == .original { return .original }
        let dark = choice == .dark || (choice == .system && systemDark)
        return HostPagePalette(foreground: dark ? 0xe6e6e6ff : 0x1a1a1aff,
                               background: dark ? 0x101010ff : 0xffffffff)
    }
    var userCSS: String? { foreground.map { String(format: "*{color:#%08x !important;}", $0) } }
}
#endif

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
    private var restoreRetryWork: DispatchWorkItem?
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
    deinit { debounce?.cancel(); pendingSave?.cancel(); pendingPageWork?.cancel(); restoreRetryWork?.cancel() }

    func connect(_ load: @escaping Loader) {
        guard loader == nil else { return }
        loader = load
        reset(anchor: top)
    }

    func search() {
        debounce?.cancel()
        pendingPageWork?.cancel(); pendingPage = nil
        restoreRetryWork?.cancel()
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
        restoreRetryWork?.cancel()
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

    private func scheduleRestoreRetry() {
        guard let target = awaitingLayoutKey, issuedRestoreRevision == restoreRevision else { return }
        restoreRetryWork?.cancel()
        let token = generation, revision = restoreRevision
        let work = DispatchWorkItem { [weak self] in
            guard let self, self.generation == token, self.restoreRevision == revision,
                  self.awaitingLayoutKey == target, !self.loading else { return }
            if let movement = self.lastProbeMovement, ProcessInfo.processInfo.systemUptime - movement < 0.15 {
                self.scheduleRestoreRetry(); return
            }
            // An early native scroll can be superseded by the content-size
            // update. Reissue it after motion stops; only real layout can ack.
            self.restoreRevision += 1
        }
        restoreRetryWork = work
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
            // An already-aligned native scroll can emit no changed whole
            // preference. Its new probes still measure actual geometry. A
            // partial set cannot establish the first visible row: require
            // every current row and the viewport from this same epoch.
            guard self.rows.count == 1 || self.awaitingLayoutKey != nil else { return }
            guard !self.rows.isEmpty, self.probeSize.width > 0, self.probeSize.height > 0,
                  self.rows.allSatisfy({ self.probePositions[$0.id] != nil }) else { return }
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
        let ordered = positions.filter { $0.value.maxY > 0 && $0.value.minY < size.height }
            .sorted { $0.value.minY < $1.value.minY }
        if let target = awaitingLayoutKey, issuedRestoreRevision != restoreRevision {
            // Rebuilding identical filtered content can leave the native list
            // already aligned without emitting a changed aggregate preference.
            // Full current geometry can prove that no scroll is needed.
            guard !loading, generation == appliedGeneration, query == appliedQuery,
                  size.width > 0, !rows.isEmpty,
                  rows.allSatisfy({ positions[$0.id] != nil }),
                  ordered.first?.key == target, let frame = positions[target],
                  frame.width > 0, frame.height > 0, abs(frame.minY) <= 1 else { return }
        }
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
                      tail.maxY <= size.height + 1 else { scheduleRestoreRetry(); return }
                if after {
                    if !loading { request(anchor: last.key, previous: false, inclusive: false, replacing: false) }
                    return
                }
                restoreKey = first.key
            }
            restoreRetryWork?.cancel()
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
#if EXR_APPLE_PAGE_THEME
    private(set) var pagePalette = HostPagePalette.original

    func configurePagePalette(_ palette: HostPagePalette) {
        precondition(book == nil, "Only unopened candidates may be configured")
        pagePalette = palette
    }

    func pageThemeCandidate(_ palette: HostPagePalette, cancel: HostCancelBox) throws -> (HostSession, HostSnapshot) {
        try cancel.check()
        guard let book else { throw HostError.invalidInput("请先打开书籍") }
        let result = candidate()
        result.book = book; result.document = document; result.publication = publication; result.fixed = fixed
        result.part = part; result.page = page; result.readingOffset = readingOffset
        result.preserveUnresolvedProgress = preserveUnresolvedProgress
        result.pagePalette = palette
        try result.begin(cancel)
        if fixed == nil {
            try result.rebuildPager(width: Double(viewport.width), height: Double(viewport.height), font: fontSize, cancel: cancel)
        }
        let snapshot = try result.renderSnapshot(persistProgress: false)
#if EXR_APPLE_HOST_REVIEW
        try HostSDKReview.event?("page-theme-rendered")
#endif
        try cancel.check()
        return (result, snapshot)
    }
#endif

    init(library: HostLibrary, font: HostFont, slowDelay: Double, viewport: CGSize, fontSize: Double) {
        self.library = library
        self.font = font
        self.slowDelay = slowDelay
        self.viewport = viewport
        self.fontSize = min(48, max(18, fontSize))
    }

    var currentViewport: CGSize { viewport }

#if EXR_APPLE_WAVE3
    func historyResolver(bookID: Int64, cancel: HostCancelBox) throws -> HostSession {
        try cancel.check()
        guard let target = try library.books().first(where: { $0.id == bookID }) else { throw HostError.invalidInput("历史原件不可用") }
        let result = candidate()
        result.book = target
        return result
    }

    // Keep the accepted session alive until the replacement font has rendered.
    func fontCandidate(_ replacement: HostFont, cancel: HostCancelBox) throws -> (HostSession, HostSnapshot) {
        try cancel.check()
        guard let book else { throw HostError.invalidInput("请先打开书籍") }
        let result = HostSession(library: library, font: replacement, slowDelay: slowDelay,
                                 viewport: viewport, fontSize: fontSize)
        result.book = book; result.document = document; result.publication = publication
        result.part = part; result.page = page; result.readingOffset = readingOffset
        result.preserveUnresolvedProgress = preserveUnresolvedProgress
#if EXR_APPLE_PAGE_THEME
        result.pagePalette = pagePalette
#endif
        try result.begin(cancel)
        if fixed != nil {
            result.fixed = try library.fixed(bookID: book.id, font: replacement, cancel: cancel)
        } else {
            try result.rebuildPager(width: Double(viewport.width), height: Double(viewport.height), font: fontSize, cancel: cancel)
        }
        let snapshot = try result.renderSnapshot(persistProgress: false)
        try cancel.check()
        return (result, snapshot)
    }
#endif

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
        let result = HostSession(library: library, font: font, slowDelay: slowDelay,
                                 viewport: viewport, fontSize: fontSize)
#if EXR_APPLE_PAGE_THEME
        result.pagePalette = pagePalette
#endif
        return result
    }

    // The old reader is untouched until a fresh SDK instance has FOUND the
    // copied selector. Opening for resolution does not restore or write progress.
    func searchCandidate(_ hit: HostSearchHit, cancel: HostCancelBox) throws -> (HostSession, HostSnapshot) {
        try cancel.check()
        guard book?.id == hit.bookID else { throw HostError.invalidInput("书籍已切换，请重新查找") }
        let independent = try HostLibrary(path: library.path)
        guard let target = try independent.books().first(where: { $0.id == hit.bookID }),
              try independent.sourceFingerprint(book: target, cancel: cancel).searchKey == hit.sourceKey else {
            throw HostError.invalidInput("原件身份已变化，请重新查找")
        }
        let result = HostSession(library: independent, font: font, slowDelay: slowDelay,
                                 viewport: viewport, fontSize: fontSize)
#if EXR_APPLE_PAGE_THEME
        result.pagePalette = pagePalette
#endif
        try result.begin(cancel)
        result.book = target
        let match: HostAnchorMatch
        if target.isFixed, hit.mode == READER_SEARCH_FIXED {
            let fixed = try independent.fixed(bookID: target.id, font: font, cancel: cancel)
            let pages = fixed.pageIDs.enumerated().filter { $0.element.utf8.elementsEqual(hit.pageID.utf8) }
            guard pages.count == 1, !hit.pageID.isEmpty else { throw HostError.invalidInput("页面目标缺失或不唯一") }
            let selectedPage = pages[0].offset
            let text = try fixed.text(page: selectedPage, cancel: cancel)
            match = try hit.fixed.withInput { try text.resolve($0, pageID: hit.pageID, cancel: cancel) }
            result.fixed = fixed; result.page = selectedPage
        } else if hit.mode == READER_SEARCH_EPUB, try independent.isBoundedEPUB(book: target) {
            let publication = try HostPublication(library: independent, bookID: target.id, cancel: cancel)
            _ = try publication.route(hit.unit, path: hit.path)
            result.publication = publication; result.part = hit.unit
            try result.rebuildPager(width: Double(viewport.width), height: Double(viewport.height), font: fontSize, cancel: cancel)
            guard let pager = result.pager else { throw HostError.invalidResult("章节分页不可用") }
            match = try hit.anchor.withInput { try pager.resolveInput($0, cancel: cancel) }
        } else if hit.mode == READER_SEARCH_REFLOW, !target.isFixed, try !independent.isBoundedEPUB(book: target) {
            let document = try independent.document(bookID: target.id, cancel: cancel)
            result.document = document
            match = try hit.anchor.withInput { try document.resolveInput($0, cancel: cancel) }
        } else { throw HostError.invalidInput("搜索模式与书籍不一致") }
        guard match.isFound, let range = match.range else { throw HostError.invalidInput("选文未精确匹配；保留当前页面") }
        try cancel.check()
        if result.fixed == nil {
            result.readingOffset = range.lowerBound
            if result.pager == nil {
                try result.rebuildPager(width: Double(viewport.width), height: Double(viewport.height), font: fontSize, cancel: cancel)
            } else { result.page = try result.pager!.pageIndex(for: range.lowerBound, cancel: cancel) }
        }
        return (result, try result.renderSnapshot())
    }

    func navigationCandidate(_ selection: HostNavigationSelection, acceptPart: Bool,
                             cancel: HostCancelBox) throws -> (HostSession, HostSnapshot) {
        try cancel.check()
        guard book?.id == selection.bookID,
              selection.resolution.status == READER_NAVIGATION_OK ||
                (acceptPart && selection.resolution.status == READER_NAVIGATION_PART_ONLY) else {
            throw HostError.invalidInput("目录目标尚未确认")
        }
        let independent = try HostLibrary(path: library.path)
        guard let targetBook = try independent.books().first(where: { $0.id == selection.bookID }),
              try independent.sourceFingerprint(book: targetBook, cancel: cancel).searchKey == selection.sourceKey else {
            throw HostError.invalidInput("原件身份已变化，请重新打开目录")
        }
        let result = HostSession(library: independent, font: font, slowDelay: slowDelay, viewport: viewport, fontSize: fontSize)
#if EXR_APPLE_PAGE_THEME
        result.pagePalette = pagePalette
#endif
        try result.begin(cancel); result.book = targetBook
        let target = selection.resolution.target
        if targetBook.isFixed {
            let fixed = try independent.fixed(bookID: targetBook.id, font: font, cancel: cancel)
            guard target.kind == READER_NAVIGATION_RESULT_PAGE.rawValue, target.row == selection.row,
                  target.part == selection.row, target.part < UInt64(fixed.pageCount), !target.partID.isEmpty,
                  fixed.pageIDs.filter({ $0.utf8.elementsEqual(target.partID.utf8) }).count == 1,
                  fixed.pageIDs[Int(target.part)].utf8.elementsEqual(target.partID.utf8) else { throw HostError.invalidInput("独立页面身份不一致") }
            result.fixed = fixed; result.page = Int(target.part)
        } else {
            let publication: HostPublication?
            let document: HostDocument?
            if try independent.isBoundedEPUB(book: targetBook) {
                publication = try HostPublication(library: independent, bookID: targetBook.id, cancel: cancel); document = nil
            } else { publication = nil; document = try independent.document(bookID: targetBook.id, cancel: cancel) }
            let (proof, offset) = try HostNavigationWorker.verify(selection, publication: publication, document: document, cancel: cancel)
            let anchor = try proof.makeAnchor(start: offset, end: offset, cancel: cancel)
            result.publication = publication; result.document = document
            result.part = publication == nil ? -1 : Int(target.part); result.readingOffset = offset
            try result.rebuildPager(width: Double(viewport.width), height: Double(viewport.height), font: fontSize, cancel: cancel)
            guard let pager = result.pager else { throw HostError.invalidResult("目录目标分页不可用") }
            try pager.verifyProjection(proof.text, cancel: cancel)
            let match = try pager.resolve(anchor, cancel: cancel)
            guard match.isFound, match.range?.lowerBound == offset else {
                throw HostError.invalidInput("目录目标未精确匹配，保留当前页面")
            }
            result.page = try pager.pageIndex(for: offset, cancel: cancel)
        }
        try cancel.check()
        return (result, try result.renderSnapshot())
    }

    func readingCapture(start: Int? = nil, end: Int? = nil, cancel: HostCancelBox) throws -> HostReadingCapture {
        try cancel.check()
        guard book != nil else { throw HostError.invalidInput("请先打开书籍") }
        let lower = start ?? (fixed == nil ? readingOffset : 0), upper = end ?? lower
        guard lower >= 0, upper >= lower else { throw HostError.invalidInput("阅读记录选文无效") }
        if let fixed { return try HostReadingWorker.fixedCapture(fixed, page: page, start: lower, end: upper, cancel: cancel) }
        guard let pager else { throw HostError.invalidInput("阅读记录分页尚未就绪") }
        let selector = try pager.makeAnchor(start: lower, end: upper, cancel: cancel)
        return HostReadingCapture(mode: publication == nil ? 1 : 2, part: max(0, part), path: currentPath, page: 0,
            anchor: HostSearchAnchor(selector.raw), fixed: nil)
    }

    // Read/restore resolution never renders or writes SDK progress. Only the
    // explicit jump caller subsequently commits an actual renderer candidate.
    func readingResolution(_ wire: Data, catalog: HostCatalog, cancel: HostCancelBox) throws -> (HostReadingCapture, HostSearchHit) {
        try cancel.check()
#if EXR_APPLE_RAW3_REVIEW && EXR_APPLE_HOST_REVIEW
        let reviewStateBefore = try stateHash()
#endif
        guard let book else { throw HostError.invalidInput("请先打开书籍") }
        let decoded = try catalog.withHistory { try HostReadingWorker.decoded(wire, history: $0) }
        let independent = try HostLibrary(path: library.path)
        guard let verifiedBook = try independent.books().first(where: { $0.id == book.id }) else { throw HostError.invalidInput("原件已不可用") }
        let original = try independent.sourceFingerprint(book: verifiedBook, cancel: cancel)
        guard decoded.book == original.format + ":" + original.sha256,
              try catalog.searchSourceKey(sdkID: book.id) == original.searchKey else { throw HostError.invalidInput("阅读记录不是当前原件") }
        let input = decoded.capture, fresh: HostReadingCapture, unit: Int
        let match: HostAnchorMatch
        if verifiedBook.isFixed, input.mode == 3, let anchor = input.fixed {
            let fixed = try independent.fixed(bookID: book.id, font: font, cancel: cancel)
            let id = anchor.fields[0].map { String(decoding: $0, as: UTF8.self) } ?? ""
            let choices = fixed.pageIDs.enumerated().filter { $0.element.utf8.elementsEqual(id.utf8) }
            guard !id.isEmpty, choices.count == 1 else { throw HostError.invalidInput("固定页位置缺失或不唯一") }
            unit = choices[0].offset
            let text = try fixed.text(page: unit, cancel: cancel)
            match = try anchor.withInput { try text.resolve($0, pageID: id, cancel: cancel) }
            guard match.isFound, let range = match.range else { throw HostError.invalidInput("记录位置未精确匹配，保留当前页面") }
            fresh = try HostReadingWorker.fixedCapture(fixed, page: unit, start: range.lowerBound, end: range.upperBound, cancel: cancel)
        } else if input.mode == 2, !verifiedBook.isFixed, try independent.isBoundedEPUB(book: verifiedBook), let anchor = input.anchor {
            let publication = try HostPublication(library: independent, bookID: book.id, cancel: cancel)
            if decoded.version == 1 {
                let choices = publication.parts.filter { $0.path.utf8.elementsEqual(input.path.utf8) && $0.reading }
                guard choices.count == 1 else { throw HostError.invalidInput("旧版章节位置不唯一，保留记录") }
                unit = choices[0].index
            } else { unit = input.part; _ = try publication.route(unit, path: input.path) }
            let pager = try HostPager(publication: publication, part: unit, font: font, width: Double(viewport.width),
                height: Double(viewport.height), fontSize: fontSize, box: cancel)
            match = try anchor.withInput { try pager.resolveInput($0, cancel: cancel) }
            guard match.isFound, let range = match.range else { throw HostError.invalidInput("记录章节未精确匹配，保留当前页面") }
            let actual = try pager.makeAnchor(start: range.lowerBound, end: range.upperBound, cancel: cancel)
            fresh = HostReadingCapture(mode: 2, part: unit, path: input.path, page: 0, anchor: HostSearchAnchor(actual.raw), fixed: nil)
        } else if input.mode == 1, !verifiedBook.isFixed, try !independent.isBoundedEPUB(book: verifiedBook), let anchor = input.anchor {
            unit = 0
            let document = try independent.document(bookID: book.id, cancel: cancel)
            match = try anchor.withInput { try document.resolveInput($0, cancel: cancel) }
            guard match.isFound, let range = match.range else { throw HostError.invalidInput("记录正文未精确匹配，保留当前页面") }
            let actual = try document.makeAnchor(start: range.lowerBound, end: range.upperBound, cancel: cancel)
            fresh = HostReadingCapture(mode: 1, part: 0, path: "", page: 0, anchor: HostSearchAnchor(actual.raw), fixed: nil)
        } else { throw HostError.invalidInput("记录坐标模式与实际阅读模式不一致") }
        try cancel.check()
        let hit = HostSearchHit(mode: input.mode == 3 ? READER_SEARCH_FIXED : input.mode == 2 ? READER_SEARCH_EPUB : READER_SEARCH_REFLOW,
            unit: unit, path: input.path, pageID: input.fixed?.fields[0].map { String(decoding: $0, as: UTF8.self) } ?? "",
            pageLabel: "", sourceKey: original.searchKey, bookID: book.id,
            anchor: input.anchor ?? HostSearchAnchor(exr_anchor()), fixed: try input.fixed ?? HostSearchFixedAnchor(exr_fixed_anchor()))
#if EXR_APPLE_RAW3_REVIEW && EXR_APPLE_HOST_REVIEW
        try HostRaw3Review.resolution(wire: wire, original: input, fresh: fresh, session: self, before: reviewStateBefore)
#endif
        return (fresh, hit)
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
        let userCSS: String?
#if EXR_APPLE_PAGE_THEME
        userCSS = pagePalette.userCSS
#else
        userCSS = nil
#endif
        if let publication {
            newPager = try HostPager(publication: publication, part: part, font: font, width: width, height: height,
                                    fontSize: size, box: cancel, userCSS: userCSS)
        } else if let document {
            newPager = try HostPager(document: document, font: font, width: width, height: height,
                                    fontSize: size, box: cancel, userCSS: userCSS)
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

    func renderSnapshot(userMove: Bool = false, persistProgress: Bool = true) throws -> HostSnapshot {
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
            if persistProgress {
                try cancel.commit {
                    try library.updatePosition(book: book, position: page)
                    pageText = text
                    pageRange = 0..<0
                }
            } else {
                try cancel.check()
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
#if EXR_APPLE_PAGE_THEME
        let bitmap = try pager.render(page, background: pagePalette.background, cancel: cancel)
#else
        let bitmap = try pager.render(page, cancel: cancel)
#endif
        guard let image = makeCGImage(bitmap) else { throw HostError.invalidResult("页面图像无法创建") }
        // Rendering consumes the borrowed layout first; this query may evict its
        // chapter projection window and returns only an owned current-page copy.
        let text = try pager.text(range, cancel: cancel)
        let totalBytes = max(1, pager.extent)
        let percent = min(100, Int((Double(range.upperBound) / Double(totalBytes) * 100).rounded()))
        if persistProgress {
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
        } else {
            try cancel.check()
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

#if EXR_APPLE_WAVE3
private final class HostWave3AccessScope {
    let url: URL
    private let started: Bool
    init(_ url: URL) { self.url = url; started = url.startAccessingSecurityScopedResource() }
    deinit { if started { url.stopAccessingSecurityScopedResource() } }
}
#endif

final class HostReaderModel: ObservableObject {
#if EXR_APPLE_WAVE3
    let wave3 = HostWave3State()
    private let wave3History = HostWave3History()
    private var wave3PreviewFile: URL?
    private var wave3PreviewBook: Int64?
    private var wave3PreviewFingerprint: String?
    private var wave3PreviewAccess: HostWave3AccessScope?
    private var wave3OutputAccess: HostWave3AccessScope?
#endif
    let search = HostSearchState()
    let navigation = HostNavigationState()
    let readingRecords = HostReadingState()
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
#if EXR_APPLE_PAGE_THEME
    @Published private(set) var pageThemeChoice = HostPageThemeChoice.original
    @Published private(set) var pageThemePalette = HostPagePalette.original
    private var requestedPageTheme = HostPageThemeChoice.original
    private var pageSystemDark = false
    private var pageThemeEpoch = 0
    private var pendingPageTheme = false

#if EXR_APPLE_HOST_REVIEW
    // Observe the actual accepted SDK bitmap; no alternate drawing path.
    var pageThemeObservation: String {
        guard let image, let data = image.dataProvider?.data else { return "unrendered" }
        let bytes = data as Data
        let hash = SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
        let corner = bytes.prefix(4).map { String(format: "%02x", $0) }.joined()
        return "\(pageThemeChoice.rawValue)|\(corner)|\(hash)|\(pageBaseOffset)|\(location)"
    }

    func requestPageThemeSystemReview(dark: Bool) {
        guard testFixtures else { return }
        do {
            let path = try stateFileURL().deletingLastPathComponent().appendingPathComponent("page-theme-system-request.json")
            try JSONSerialization.data(withJSONObject: ["source_sha": Bundle.main.object(forInfoDictionaryKey: "EXRSourceSHA") as? String ?? "",
                "requested_appearance": dark ? "dark" : "light", "choice": pageThemeChoice.rawValue]).write(to: path, options: .atomic)
        } catch { errorText = describe(error) }
    }
#endif

    func observePageThemeEnvironment(dark: Bool) {
        guard dark != pageSystemDark else { return }
        pageSystemDark = dark
        if requestedPageTheme == .system { changePageTheme(.system) }
    }

    func changePageTheme(_ choice: HostPageThemeChoice) {
        requestedPageTheme = choice
        pageThemeEpoch += 1
        pendingPageTheme = true
        applyPendingPageTheme()
    }

    private func applyPendingPageTheme() {
        guard pendingPageTheme, !busy else { return }
        let choice = requestedPageTheme, epoch = pageThemeEpoch
        let palette = HostPagePalette.resolve(choice, systemDark: pageSystemDark)
        pendingPageTheme = false
        guard let bookID = current?.id else {
            pageThemeChoice = choice; pageThemePalette = palette; return
        }
        guard choice != pageThemeChoice || palette != pageThemePalette else { return }
        let (myToken, box) = begin()
        queue.async {
            do {
                guard let session = self.session else { throw HostError.invalidInput("书库未就绪") }
                try self.requireBook(bookID, session: session, cancel: box)
                let (candidate, snapshot) = try session.pageThemeCandidate(palette, cancel: box)
                try box.check()
                let accepted = DispatchQueue.main.sync { () -> Bool in
                    guard myToken == self.token else { return false }
                    guard epoch == self.pageThemeEpoch else { self.finish(); return false }
                    self.apply(snapshot, persist: false)
                    self.pageThemeChoice = choice; self.pageThemePalette = palette
                    self.statusText = "阅读主题已更新"
                    self.finish()
                    return true
                }
                if accepted { self.session = candidate }
            } catch {
                DispatchQueue.main.async {
                    guard myToken == self.token else { return }
                    if epoch == self.pageThemeEpoch { self.requestedPageTheme = self.pageThemeChoice }
                    self.fail(error)
                }
            }
        }
    }
#endif
    @Published var statusText = "就绪"
    @Published var errorText = ""
    @Published private(set) var productIndexPending = false
    @Published var stateHash = "—"
    @Published var busy = false
    @Published private(set) var libraryReady = false
    @Published private(set) var syncPreparing = false
    @Published var notes: [HostNoteRow] = []
    @Published var showLibrary = true
    @Published var frameCount = 0
    @Published private(set) var uiTestTrace = ""
#if EXR_APPLE_HOST_REVIEW
    @Published private(set) var reviewInitializationHeld = false
    private var reviewInitializationReleased = false
    private var reviewRejectedBeforeInitialization = 0
    var reviewInitializationHoldEnabled: Bool { CommandLine.arguments.contains("-EXRHoldInitializationBeforeStart") }
    var reviewInitializationObservation: String {
        let value: [String: Any] = ["held": reviewInitializationHeld, "library_ready": libraryReady,
            "started": started, "busy": busy, "token": token, "rejected_unready": reviewRejectedBeforeInitialization,
            "retained_ui_books": books.count]
        return (try? String(data: JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]), encoding: .utf8)) ?? "{}"
    }
    func reviewTryImportBeforeInitialization() { importFixture("Sample", extension: "epub") }
    func reviewReleaseInitialization() {
        reviewInitializationReleased = true; reviewInitializationHeld = false; start()
    }
    @Published private var uiTestCancellationReadyToken: Int?
    var uiTestCancellationReady: Bool { busy && uiTestCancellationReadyToken == token }
    @Published private(set) var reviewFastImportObservation = "{}"
    private var reviewFastImportArmed = false
    private var reviewFastImportCompleted = false
    private var reviewFastImportBusyChanges = 0
    var reviewFastImportEnabled: Bool { CommandLine.arguments.contains("-EXRFastImportOneMainTurn") }
    var reviewFastImportReady: Bool { libraryReady && !busy && books.isEmpty }

    func observeReviewLibraryBusy(_ value: Bool) {
        guard reviewFastImportEnabled else { return }
        if reviewFastImportArmed { reviewFastImportBusyChanges += 1 }
        updateReviewFastImport()
    }

    private func updateReviewFastImport() {
        let value: [String: Any] = ["ready": reviewFastImportReady, "completed": reviewFastImportCompleted,
            "busy": busy, "observed_busy_changes": reviewFastImportBusyChanges,
            "sdk_books": books.count, "same_main_turn": reviewFastImportCompleted]
        reviewFastImportObservation = (try? String(data: JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]), encoding: .utf8)) ?? "{}"
    }

    // Complete the real owner import and its production publication inside one
    // button action, so SwiftUI cannot observe an intermediate busy=true frame.
    func reviewImportFixtureInOneMainTurn() {
        guard reviewFastImportEnabled, reviewFastImportReady else { return }
        precondition(Thread.isMainThread)
        reviewFastImportArmed = true; reviewFastImportCompleted = false; reviewFastImportBusyChanges = 0
        let (myToken, cancel) = begin()
        do {
            guard let file = Bundle.main.url(forResource: "Sample", withExtension: "epub") else { throw HostError.invalidInput("缺少实际 EPUB 夹具") }
            let publish: () -> Void = try queue.sync {
                guard let session = self.session, let catalog = self.catalog else { throw HostError.invalidInput("书库未就绪") }
                let (_, created) = try session.importBook(url: file, cancel: cancel, catalog: catalog)
                guard created else { throw HostError.invalidResult("快速导入回归必须创建真实新书") }
                return self.mutationPublication(session: session, token: myToken, status: "已导入 Sample.epub", imported: true)
            }
            publish()
            reviewFastImportCompleted = !busy && books.count == 1
            updateReviewFastImport()
        } catch { fail(error); updateReviewFastImport() }
    }
#endif
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
#if EXR_APPLE_WAVE3
    var wave3Actions: HostWave3Actions {
        var actions = HostWave3Actions(refresh: refreshWave3, previewAnnotations: previewWave3Annotations,
            confirmAnnotations: confirmWave3Annotations, discardPreview: discardWave3Preview,
            importFont: importWave3Font, selectFont: selectWave3Font,
            exportAnnotations: exportWave3Annotations, exportOriginal: exportWave3Original,
            back: { self.jumpWave3History(back: true) }, forward: { self.jumpWave3History(back: false) },
            cancel: cancelWork)
#if EXR_APPLE_HOST_REVIEW
        actions.reviewAnnotations = prepareWave3Fixture
#endif
        return actions
    }

    private func performWave3(_ work: @escaping (HostSession, HostCatalog, URL, HostCancelBox) throws -> (() -> Void)) {
        guard !busy, current != nil else { return }
        let (epoch, cancel) = begin()
        wave3.busy = true; wave3.message = "处理中…"
        queue.async {
            do {
                guard let session = self.session, let catalog = self.catalog else { throw HostError.invalidInput("书库未就绪") }
                let publish = try work(session, catalog, self.storageFolder(), cancel)
                DispatchQueue.main.async {
                    guard epoch == self.token else { return }
                    publish(); self.wave3.busy = false; self.finish()
                }
            } catch {
                DispatchQueue.main.async {
                    guard epoch == self.token else { return }
                    if let partial = error as? HostWave3ImportFailure {
                        self.wave3.annotationPreview = partial.preview
                        self.wave3.canConfirmAnnotations = false
                    }
                    self.wave3.busy = false; self.wave3.message = self.describe(error)
                    if let partial = error as? HostWave3ImportFailure, partial.cancelled {
                        self.statusText = "已取消"; self.finish()
                    } else { self.fail(error) }
                }
            }
        }
    }

    func refreshWave3() {
        performWave3 { _, catalog, root, cancel in
            let fonts = try HostWave3Fonts.records(root: root.appendingPathComponent("fonts"), cancel: cancel)
            let history = try self.wave3History.state()
            var sync = try self.accountSession?.wave3SyncSnapshot(catalog: catalog)
#if EXR_APPLE_HOST_REVIEW
            if sync == nil && self.testFixtures { sync = try HostWave3Review.idleSync(catalog: catalog, root: root) }
#endif
            return {
                self.wave3.fonts = fonts; self.wave3.canBack = history.0; self.wave3.canForward = history.1
                self.wave3.sync = sync; self.wave3.message = "详情已刷新"
            }
        }
    }

    func discardWave3Preview() {
        guard !busy else { return }
        wave3PreviewFile = nil; wave3PreviewBook = nil; wave3PreviewFingerprint = nil
        wave3PreviewAccess = nil; wave3.canConfirmAnnotations = false
        wave3.annotationPreview = nil; wave3.message = "已放弃预览，未导入标注"
    }

    func previewWave3Annotations(_ file: URL) { importWave3Annotations(file, confirmation: nil) }
    func confirmWave3Annotations() {
        guard let file = wave3PreviewFile, wave3PreviewBook == current?.id,
              let fingerprint = wave3PreviewFingerprint else { return }
        importWave3Annotations(file, confirmation: fingerprint)
    }
    private func importWave3Annotations(_ file: URL, confirmation: String?) {
        guard !busy else { return }
        if confirmation == nil {
            wave3PreviewFile = nil; wave3PreviewBook = nil; wave3PreviewFingerprint = nil
            wave3PreviewAccess = nil; wave3.annotationPreview = nil; wave3.canConfirmAnnotations = false
        }
        performWave3 { session, catalog, _, cancel in
            guard let book = session.book else { throw HostError.invalidInput("请先打开书籍") }
            let access = HostWave3AccessScope(file)
            let key = try catalog.readingBook(sdkID: book.id).key
            let resolver = try HostWave3AnnotationResolver(library: session.library, font: session.font,
                                                         bookID: book.id, key: key, cancel: cancel)
            let preview = try HostWave3Worker.annotations(catalog: catalog, key: key, file: file,
                confirmation: confirmation, cancel: cancel) { record in
                    try resolver.resolve(record)
                }
            return {
                self.wave3.annotationPreview = preview
                self.wave3PreviewFile = confirmation == nil ? file : nil
                self.wave3PreviewBook = confirmation == nil ? book.id : nil
                self.wave3PreviewFingerprint = confirmation == nil ? preview.fingerprint : nil
                self.wave3PreviewAccess = confirmation == nil ? access : nil
                self.wave3.canConfirmAnnotations = confirmation == nil && preview.unresolved == 0
                self.wave3.message = confirmation == nil ? "预览完成，请确认后导入" : "标注已导入：\(preview.committed)"
            }
        }
    }

#if EXR_APPLE_HOST_REVIEW
    func prepareWave3Fixture(_ nullSelector: Bool) {
        guard testFixtures else { return }
        performWave3 { session, catalog, root, cancel in
            let bookID = session.book?.id
            let file = try HostWave3Review.portableFixture(session: session, catalog: catalog, root: root,
                                                         nullSelector: nullSelector, cancel: cancel)
            return {
                DispatchQueue.main.async {
                    guard self.current?.id == bookID, !self.busy else { return }
                    self.previewWave3Annotations(file)
                }
            }
        }
    }
#endif

    func importWave3Font(_ file: URL) {
        performWave3 { _, _, root, cancel in
            let scoped = file.startAccessingSecurityScopedResource()
            defer { if scoped { file.stopAccessingSecurityScopedResource() } }
            let rows = try HostWave3Fonts.records(root: root.appendingPathComponent("fonts"), importing: file, cancel: cancel)
            return { self.wave3.fonts = rows; self.wave3.message = "字体已导入，相同内容自动去重" }
        }
    }

    func selectWave3Font(_ hash: String?) {
        guard !busy, current != nil else { return }
        let (epoch, cancel) = begin(); wave3.busy = true; wave3.message = "处理中…"
        queue.async {
            do {
                guard let session = self.session else { throw HostError.invalidInput("书库未就绪") }
                let font: HostFont
                let sha: String
                if let hash {
                    let lease = try HostWave3FontLease.acquire(root: self.storageFolder().appendingPathComponent("fonts"), hash: hash)
                    font = HostFont(borrowed: lease.font, lifetime: lease); sha = hash
                } else {
                    guard let file = Bundle.main.url(forResource: "Reader", withExtension: "otf") else { throw HostError.invalidInput("缺少默认字体") }
                    let data = try Data(contentsOf: file); font = try HostFont(data: data)
                    sha = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
                }
                let (candidate, frame) = try session.fontCandidate(font, cancel: cancel)
                let previousSHA = self.fontSHA
                self.fontSHA = sha
                if self.completeFrame(frame, session: candidate, token: epoch, status: "字体已应用", recordHistory: false,
                    publishAccepted: {
                        self.defaults.set(hash, forKey: "EXRImportedFont")
                        self.wave3.selectedFont = hash; self.wave3.message = "字体已应用"
                    }) {
                    self.session = candidate
                } else { self.fontSHA = previousSHA }
            } catch {
                DispatchQueue.main.async {
                    guard epoch == self.token else { return }
                    self.wave3.busy = false; self.wave3.message = self.describe(error); self.fail(error)
                }
            }
        }
    }

    func exportWave3Original(_ directory: URL) {
        performWave3 { session, _, _, cancel in
            guard let book = session.book else { throw HostError.invalidInput("请先打开书籍") }
            let access = HostWave3AccessScope(directory)
            let output = try HostWave3Worker.exportOriginal(library: session.library, bookID: book.id, directory: directory, cancel: cancel)
            return { self.wave3OutputAccess = access; self.wave3.exportURL = output; self.wave3.message = "原件已导出，可分享副本" }
        }
    }

    func exportWave3Annotations(_ directory: URL, markdown: Bool) {
        performWave3 { session, catalog, _, cancel in
            guard let book = session.book else { throw HostError.invalidInput("请先打开书籍") }
            let access = HostWave3AccessScope(directory)
            let key = try catalog.readingBook(sdkID: book.id).key
            let output = try HostWave3Worker.exportAnnotations(catalog: catalog, key: key, directory: directory, markdown: markdown, cancel: cancel)
            return { self.wave3OutputAccess = access; self.wave3.exportURL = output; self.wave3.message = "标注已导出，可分享副本" }
        }
    }

    func jumpWave3History(back: Bool) {
        guard !busy, current != nil else { return }
        let (epoch, cancel) = begin(); wave3.busy = true; wave3.message = "处理中…"
        queue.async {
            do {
                guard let session = self.session, let catalog = self.catalog else { throw HostError.invalidInput("书库未就绪") }
                let ticket = try self.wave3History.peek(back: back)
                let identity = try catalog.withHistory { try HostReadingWorker.decoded(ticket.wire, history: $0).book }
                guard identity == ticket.bookKey else { throw HostError.invalidInput("历史原件身份不一致") }
                let resolver: HostSession
                if let book = session.book, try catalog.readingBook(sdkID: book.id).key == identity { resolver = session }
                else {
                    guard let book = try session.library.books().first(where: { (try? catalog.readingBook(sdkID: $0.id).key) == identity }) else { throw HostError.invalidInput("历史原件不可用") }
                    resolver = try session.historyResolver(bookID: book.id, cancel: cancel)
                }
                let (_, hit) = try resolver.readingResolution(ticket.wire, catalog: catalog, cancel: cancel)
                let (candidate, frame) = try resolver.searchCandidate(hit, cancel: cancel)
                if self.completeFrame(frame, session: candidate, token: epoch, status: back ? "已返回历史位置" : "已前进历史位置", recordHistory: false, finishWork: false) {
                    self.session = candidate
                    try self.wave3History.complete(ticket)
                    let state = try self.wave3History.state()
                    DispatchQueue.main.async {
                        guard epoch == self.token else { return }
                        self.wave3.canBack = state.0; self.wave3.canForward = state.1
                        self.wave3.message = "已精确定位历史位置"; self.finish()
                    }
                }
            } catch {
                DispatchQueue.main.async {
                    guard epoch == self.token else { return }
                    self.wave3.busy = false; self.wave3.message = self.describe(error); self.fail(error)
                }
            }
        }
    }
#endif
    var shelfDefaults: UserDefaults { defaults }

    func closeAccountSession() {
        activeCancel?.cancel()
        readingRecords.bind(nil)
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
                            try self.accountSession?.start(profile: profile, directory: directory, authorization: authorization, terminal: { [weak self] state in
                                if state == READER_SESSION_CANCELLED { self?.statusText = "同步已取消" }
                                else if state == READER_SESSION_FAILED { self?.statusText = "同步失败，请重试" }
                            }) { [weak self] in
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
#if EXR_APPLE_HOST_REVIEW
        if reviewInitializationHoldEnabled && !reviewInitializationReleased {
            reviewInitializationHeld = true
            return
        }
#endif
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
#if EXR_APPLE_WAVE3
                    self.defaults.removeObject(forKey: "EXRImportedFont")
#endif
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
                var font = try HostFont(data: fontData)
                self.fontSHA = SHA256.hash(data: fontData).map { String(format: "%02x", $0) }.joined()
#if EXR_APPLE_WAVE3
                if let selected = self.defaults.string(forKey: "EXRImportedFont") {
                    do {
                        let lease = try HostWave3FontLease.acquire(root: folder.appendingPathComponent("fonts"), hash: selected)
                        font = HostFont(borrowed: lease.font, lifetime: lease)
                        self.fontSHA = selected
                        DispatchQueue.main.async { self.wave3.selectedFont = selected }
                    } catch {
                        DispatchQueue.main.async { self.wave3.message = "导入字体不可用，已使用内置字体：\(self.describe(error))" }
                    }
                }
#endif
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
                    // Both owner dependencies and the initial SDK read exist
                    // before any import control or backend entry is admitted.
                    self.libraryReady = true
                    self.busy = false
                    if !repairProblems.isEmpty {
                        self.errorText = "产品索引待修复：" + repairProblems.joined(separator: "；")
                        self.statusText = "书籍已保留，产品索引待修复"
                    } else if let lastID, lastPresent {
                        self.errorText = ""; self.statusText = "就绪"
                        self.openBook(id: lastID)
                    } else {
                        self.errorText = ""; self.statusText = "就绪"
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

    private func begin(preserveNavigation: Bool = false) -> (Int, HostCancelBox) {
        search.cancel()
        if !preserveNavigation { navigation.cancel() }
        activeCancel?.cancel()
        token += 1
        let box = HostCancelBox()
        activeCancel = box
        busy = true
        errorText = ""
        return (token, box)
    }

    private func finish() {
#if EXR_APPLE_WAVE3
        wave3.busy = false
#endif
        activeCancel = nil
        if let request = pendingViewport {
            pendingViewport = nil
            if request.bookID == current?.id, request.token == token, current?.isFixed == false {
                applyViewport(request, finishingPrevious: true)
                return
            }
        }
        busy = false
#if EXR_APPLE_PAGE_THEME
        applyPendingPageTheme()
#endif
    }

    private func requireBook(_ id: Int64, session: HostSession, cancel: HostCancelBox) throws {
        try cancel.check()
        guard session.book?.id == id else { throw HostError.invalidInput("书籍已切换，请重试操作") }
    }

    @discardableResult
    private func completeFrame(_ snapshot: HostSnapshot, session: HostSession, token: Int,
                               status: String, opening: Bool = false, historyKind: Int = 1,
                               recordHistory: Bool = true, finishWork: Bool = true,
                               publishAccepted: (() -> Void)? = nil) -> Bool {
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
        let accepted = DispatchQueue.main.sync {
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
            publishAccepted?()
            if finishWork { self.finish() }
            return true
        }
#if EXR_APPLE_WAVE3
        if accepted && recordHistory {
            do {
                guard let catalog else { throw HostError.invalidInput("产品书库未就绪") }
                let capture = try session.readingCapture(cancel: HostCancelBox())
                let key = try catalog.readingBook(sdkID: snapshot.book.id).key
                try wave3History.commit(catalog: catalog, capture: capture, key: key,
                                        kind: historyKind == 2 ? READER_JH_SEARCH : historyKind == 3 ? READER_JH_TOC : READER_JH_PAGE)
                let state = try wave3History.state()
                DispatchQueue.main.async { self.wave3.canBack = state.0; self.wave3.canForward = state.1 }
            } catch {
                DispatchQueue.main.async { self.wave3.message = "页面已更新，历史未记录：\(self.describe(error))" }
            }
        }
#endif
        return accepted
    }

    private func completeMutation(session: HostSession, token: Int, status: String, imported: Bool = false) {
        let publish = mutationPublication(session: session, token: token, status: status, imported: imported)
        DispatchQueue.main.async { publish() }
    }

    private func mutationPublication(session: HostSession, token: Int, status: String, imported: Bool) -> () -> Void {
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
        return {
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

    private func apply(_ snapshot: HostSnapshot, persist: Bool = true) {
#if EXR_APPLE_WAVE3
        if current?.id != snapshot.book.id {
            wave3PreviewFile = nil; wave3PreviewBook = nil; wave3PreviewFingerprint = nil
            wave3PreviewAccess = nil; wave3.canConfirmAnnotations = false
            wave3.annotationPreview = nil
        }
#endif
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
        frameCount += 1
        if persist {
            defaults.set(snapshot.fontSize, forKey: "EXRFontSize")
            defaults.set(snapshot.book.id, forKey: "EXRLastBook")
        }
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

    func prepareReadingRecords() {
        guard let current, !busy else { return }
        readingRecords.bind(current.id)
        loadReadingRecords()
    }

    private func performReading(_ status: String, cursor: reader_av_cursor? = nil,
                                _ action: @escaping (HostSession, HostCatalog, URL, HostCancelBox) throws -> HostReadingHistory?) {
        guard !busy, let bookID = current?.id, readingRecords.bookID == bookID else { return }
        let generation = readingRecords.generation, (myToken, box) = begin()
        readingRecords.running = true; readingRecords.status = "处理中…"
        queue.async {
            do {
                guard let session = self.session, let catalog = self.catalog else { throw HostError.invalidInput("书库尚未就绪") }
                try self.requireBook(bookID, session: session, cancel: box)
                let root = try self.storageFolder()
#if EXR_APPLE_HOST_REVIEW
                let beforeSave = HostReadingWorker.afterDurableSave, beforeCommit = HostReadingWorker.afterCommit
                func holdAtNativeBoundary(_ boundary: String) throws {
#if EXR_APPLE_RAW3_REVIEW
                    try HostRaw3Review.audit(session: session, catalog: catalog, root: root, event: boundary)
#endif
                    DispatchQueue.main.async { self.readingRecords.nativeBoundary = boundary }
                    while !box.isCancelled { Thread.sleep(forTimeInterval: 0.05) }
                    throw HostError.cancelled
                }
                if ProcessInfo.processInfo.arguments.contains("-EXRKillReadingAfterSave") {
                    HostReadingWorker.afterDurableSave = { try holdAtNativeBoundary("private-save") }
                }
                if ProcessInfo.processInfo.arguments.contains("-EXRKillReadingAfterCommit") {
                    HostReadingWorker.afterCommit = { try holdAtNativeBoundary("post-commit") }
                }
                defer { HostReadingWorker.afterDurableSave = beforeSave; HostReadingWorker.afterCommit = beforeCommit }
#endif
                let history = try action(session, catalog, root, box)
                let book = try catalog.readingBook(sdkID: bookID)
                let page = try HostReadingWorker.page(catalog: catalog, bookID: bookID, bookKey: book.key, from: cursor, cancel: box)
                let progress = try HostReadingWorker.progress(catalog: catalog, bookID: bookID, bookKey: book.key)
                let pending = try HostReadingWorker.pending(root: root)
#if EXR_APPLE_RAW3_REVIEW && EXR_APPLE_HOST_REVIEW
                try HostRaw3Review.audit(session: session, catalog: catalog, root: root, event: status)
#endif
                DispatchQueue.main.async {
                    guard myToken == self.token else { return }
                    if generation == self.readingRecords.generation && self.readingRecords.bookID == bookID {
                        if cursor == nil || !page.rows.isEmpty {
                            self.readingRecords.rows = (cursor == nil ? progress.map { [$0] } ?? [] : []) + page.rows
                        }
                        self.readingRecords.cursor = page.next; self.readingRecords.complete = page.complete
                        self.readingRecords.pending = pending; self.readingRecords.status = status
                        self.readingRecords.running = false
                        self.readingRecords.versions = history?.versions ?? []
                        self.readingRecords.restoring = history?.row
                        self.readingRecords.restoreHeads = history?.heads ?? []
                        self.statusText = status
                    }
                    self.finish()
                }
            } catch {
                let pending = try? HostReadingWorker.pending(root: self.storageFolder())
#if EXR_APPLE_RAW3_REVIEW && EXR_APPLE_HOST_REVIEW
                if let session = self.session, let catalog = self.catalog, let root = try? self.storageFolder() {
                    try? HostRaw3Review.audit(session: session, catalog: catalog, root: root, event: "action-failed")
                }
#endif
                DispatchQueue.main.async {
                    guard myToken == self.token else { return }
                    if generation == self.readingRecords.generation {
                        self.readingRecords.running = false; self.readingRecords.status = self.describe(error)
                        self.readingRecords.pending = pending
                        self.errorText = self.describe(error)
                    }
                    self.finish()
                }
            }
        }
    }

    func loadReadingRecords(next: Bool = false) {
        if next && readingRecords.complete { return }
        let cursor = next ? readingRecords.cursor : nil
        performReading("本书的书签与标注", cursor: cursor) { _, _, _, _ in nil }
    }

    func saveReadingRecord(bookmark: Bool) {
        performReading(bookmark ? "已添加书签" : "已保存阅读进度") { session, catalog, root, cancel in
            let capture = try session.readingCapture(cancel: cancel)
            let request = try HostReadingWorker.request(session: session, catalog: catalog, kind: bookmark ? 2 : 1,
                operation: 0, mode: capture.mode, capture: capture, body: "", cancel: cancel)
            _ = try HostReadingWorker.submit(request, session: session, catalog: catalog, root: root, cancel: cancel)
            return nil
        }
    }

    func highlightReadingRecord(start: Int, end: Int, context: HostSelectionContext) {
        guard !busy, context == selectionContext, start >= context.baseOffset, end > start,
              end - context.baseOffset <= context.text.utf8.count else { errorText = "选文已失效，请重新选择"; return }
        if readingRecords.bookID != context.bookID { readingRecords.bind(context.bookID) }
        performReading("已保存高亮到阅读记录") { session, catalog, root, cancel in
            guard session.matches(context) else { throw HostError.invalidInput("选文页面已变化") }
            let capture = try session.readingCapture(start: start, end: end, cancel: cancel)
            let request = try HostReadingWorker.request(session: session, catalog: catalog, kind: 3, operation: 0,
                mode: capture.mode, capture: capture, body: "", cancel: cancel)
            _ = try HostReadingWorker.submit(request, session: session, catalog: catalog, root: root, cancel: cancel)
            return nil
        }
    }

    func editReadingRecord(_ row: HostReadingRow, body: String) {
        guard row.safe, row.hasLocation, row.entityKind == "annotation", body.utf8.count <= 65536 else { return }
        performReading("批注已保存") { session, catalog, root, cancel in
#if EXR_APPLE_RAW3
            let retained = try HostReadingWorker.selectedWire(catalog: catalog, row: row)
            let sourceVersion = try catalog.withHistory { try HostReadingWorker.decoded(retained, history: $0).version }
            let request = try HostReadingWorker.request(session: session, catalog: catalog, kind: 4, operation: 0,
                annotation: row.annotation, mode: row.mode, capture: nil, body: body, observedHeads: [row.revision],
                anchorVersion: sourceVersion, cancel: cancel)
#else
            _ = try HostReadingWorker.selectedWire(catalog: catalog, row: row)
            let request = try HostReadingWorker.request(session: session, catalog: catalog, kind: 4, operation: 0,
                annotation: row.annotation, mode: row.mode, capture: nil, body: body, observedHeads: [row.revision], cancel: cancel)
#endif
            _ = try HostReadingWorker.submit(request, session: session, catalog: catalog, root: root, cancel: cancel)
            return nil
        }
    }

    func deleteReadingRecord(_ row: HostReadingRow) {
        guard row.safe, row.hasLocation else { return }
        performReading("阅读记录已删除，保留历史版本") { session, catalog, root, cancel in
            _ = try HostReadingWorker.selectedWire(catalog: catalog, row: row)
            let request = try HostReadingWorker.request(session: session, catalog: catalog, kind: row.entityKind == "progress" ? 1 : 2,
                operation: 1, annotation: row.annotation, mode: row.mode, capture: nil, body: "", observedHeads: [row.revision], cancel: cancel)
            _ = try HostReadingWorker.submit(request, session: session, catalog: catalog, root: root, cancel: cancel)
            return nil
        }
    }

    func showReadingHistory(_ row: HostReadingRow) {
        performReading("请选择要恢复的保留版本") { _, catalog, _, _ in try HostReadingWorker.history(catalog: catalog, row: row) }
    }

    func restoreReadingVersion(_ version: HostReadingVersion) {
        guard let row = readingRecords.restoring, readingRecords.versions.contains(where: { $0.id == version.id }) else { return }
        let heads = readingRecords.restoreHeads
        performReading("已恢复阅读记录，当前页面保持不变") { session, catalog, root, cancel in
            let (capture, _) = try session.readingResolution(version.wire, catalog: catalog, cancel: cancel)
            let source = try catalog.withHistory { try HostReadingWorker.decoded(version.wire, history: $0) }
            let isPoint = capture.mode == 3 ? capture.fixed!.start == capture.fixed!.end : capture.anchor!.start == capture.anchor!.end
#if EXR_APPLE_RAW3
            let request = try HostReadingWorker.request(session: session, catalog: catalog,
                kind: row.entityKind == "progress" ? 1 : isPoint ? 2 : 3, operation: 2, annotation: row.annotation,
                mode: capture.mode, capture: capture, body: source.body, observedHeads: heads,
                anchorVersion: source.version, cancel: cancel)
#else
            let request = try HostReadingWorker.request(session: session, catalog: catalog,
                kind: row.entityKind == "progress" ? 1 : isPoint ? 2 : 3, operation: 2, annotation: row.annotation,
                mode: capture.mode, capture: capture, body: source.body, observedHeads: heads, cancel: cancel)
#endif
            _ = try HostReadingWorker.submit(request, session: session, catalog: catalog, root: root, cancel: cancel)
            return nil
        }
    }

    func replayReadingRequest() {
        performReading("待完成阅读记录已确认保存") { session, catalog, root, cancel in
            _ = try HostReadingWorker.replay(session: session, catalog: catalog, root: root, cancel: cancel); return nil
        }
    }
    func discardReadingRequest(expected: String) {
        performReading("已放弃这项待完成请求") { _, _, root, _ in
            try HostReadingWorker.discard(root: root, expected: expected); return nil
        }
    }
    func closeReadingRecords() {
        if readingRecords.running { activeCancel?.cancel() }
        readingRecords.bind(nil)
    }
    func jumpReadingRecord(_ row: HostReadingRow) {
        guard !busy, row.safe, row.hasLocation, row.bookID == current?.id else { return }
        let (myToken, box) = begin()
        queue.async {
            do {
                guard let session = self.session, let catalog = self.catalog else { throw HostError.invalidInput("书库尚未就绪") }
                try self.requireBook(row.bookID, session: session, cancel: box)
                let wire = try HostReadingWorker.selectedWire(catalog: catalog, row: row)
                let (_, hit) = try session.readingResolution(wire, catalog: catalog, cancel: box)
                let (candidate, frame) = try session.searchCandidate(hit, cancel: box)
                if self.completeFrame(frame, session: candidate, token: myToken, status: "已精确定位阅读记录") {
                    self.session = candidate
                }
            } catch {
                DispatchQueue.main.async { guard myToken == self.token else { return }; self.readingRecords.status = self.describe(error); self.finish() }
            }
        }
    }

    func prepareSearch() {
        guard let current, !busy else { return }
        let key = "EXRSearchQuery.\(current.id)"
        search.bind(bookID: current.id, query: defaults.string(forKey: key) ?? "")
    }

    func prepareNavigation() {
        guard let current, !busy else { return }
        navigation.bind(current.id); loadNavigation()
    }

    func loadNavigation(parent: UInt64 = UInt64.max, first: UInt64 = 0) {
        guard !busy, let bookID = current?.id, navigation.bookID == bookID else { return }
        let boundKey = navigation.key
        let (epoch, box) = navigation.begin()
        queue.async {
            do {
                guard let session = self.session, session.book?.id == bookID, let catalog = self.catalog else {
                    throw HostError.invalidInput("书籍已切换")
                }
                let key = try catalog.searchSourceKey(sdkID: bookID)
                guard boundKey == nil || boundKey == key else { throw HostError.invalidInput("原件身份已变化，请重新打开目录") }
#if EXR_APPLE_HOST_REVIEW
                let previous = HostSDKReview.poll
                let hold = CommandLine.arguments.contains("-EXRHoldNavigationCancellation")
                if hold {
                    HostSDKReview.poll = { polled in
                        guard polled === box, HostNavigationWorker.reviewInsideSnapshot else { previous?(polled); return }
                        DispatchQueue.main.async { self.navigation.reviewCancellationReady(generation: epoch) }
                        while !polled.isCancelled { Thread.sleep(forTimeInterval: 0.05) }
                    }
                }
                defer { if hold { HostSDKReview.poll = previous } }
#endif
                let page = try HostNavigationWorker.page(library: session.library, font: session.font, bookID: bookID,
                    key: key, parent: parent, first: first, cancel: box)
                DispatchQueue.main.async {
                    guard self.current?.id == bookID else { return }
                    self.navigation.accept(page, key: key, generation: epoch)
                }
            } catch { DispatchQueue.main.async { self.navigation.fail(error, generation: epoch) } }
        }
    }

    func selectNavigation(row: UInt64, explicitPart: UInt64 = UInt64.max, acceptPart: Bool = false, cfi: String = "") {
        guard !busy, !navigation.running, let bookID = current?.id, navigation.bookID == bookID,
              let key = navigation.key, cfi.isEmpty || (cfi.utf8.count <= 4096 && !cfi.utf8.contains(0)) else { return }
        let (myToken, box) = begin(preserveNavigation: true)
        let (epoch, _) = navigation.begin(box: box)
        statusText = "正在核对目录目标…"
        queue.async {
            do {
                guard let session = self.session, let catalog = self.catalog, session.book?.id == bookID,
                      try catalog.searchSourceKey(sdkID: bookID) == key else { throw HostError.invalidInput("书籍身份已变化") }
                let selection = try HostNavigationWorker.resolve(library: session.library, font: session.font,
                    bookID: bookID, key: key, row: row, explicitPart: explicitPart, cfi: cfi, cancel: box)
                if selection.resolution.status == READER_NAVIGATION_AMBIGUOUS ||
                    (selection.resolution.status == READER_NAVIGATION_PART_ONLY && !acceptPart) {
                    DispatchQueue.main.async {
                        guard myToken == self.token else { return }
                        self.navigation.propose(selection, generation: epoch); self.finish()
                    }
                    return
                }
                let (candidate, snapshot) = try session.navigationCandidate(selection, acceptPart: acceptPart, cancel: box)
                if self.completeFrame(snapshot, session: candidate, token: myToken, status: "已精确定位目录目标", historyKind: 3) {
                    self.session = candidate
                    DispatchQueue.main.async { self.navigation.didCommit(generation: epoch) }
                }
            } catch {
                DispatchQueue.main.async {
                    guard myToken == self.token else { return }
                    self.navigation.fail(error, generation: epoch); self.fail(error)
                }
            }
        }
    }

    func findInBook(restart: Bool = true) {
        guard !busy, let bookID = current?.id, search.bookID == bookID,
              !search.running, restart || !search.complete else { return }
        let query = search.query
        guard !query.isEmpty, query.utf8.count <= 4096, !query.utf8.contains(0) else { return }
        defaults.set(query, forKey: "EXRSearchQuery.\(bookID)")
        let resume = restart ? nil : search.cursor
        let boundSource = restart ? nil : search.sourceKey
        let (epoch, box) = search.begin(restart: restart)
        queue.async {
            do {
                guard let session = self.session, let catalog = self.catalog,
                      session.book?.id == bookID else { throw HostError.invalidInput("书籍已切换") }
                let key = try catalog.searchSourceKey(sdkID: bookID)
                guard boundSource == nil || boundSource == key else { throw HostError.invalidInput("原件身份已变化，请重新查找") }
#if EXR_APPLE_HOST_REVIEW
                let priorPoll = HostSDKReview.poll
                let hold = CommandLine.arguments.contains("-EXRHoldSearchCancellation")
                if hold {
                    HostSDKReview.poll = { polled in
                        guard polled === box, HostSearchWorker.reviewInsideNext else { priorPoll?(polled); return }
                        DispatchQueue.main.async { self.search.reviewCancellationReady(generation: epoch) }
                        while !polled.isCancelled { Thread.sleep(forTimeInterval: 0.05) }
                    }
                }
                defer { if hold { HostSDKReview.poll = priorPoll } }
#endif
                let batch = try HostSearchWorker.batch(library: session.library, font: session.font,
                    bookID: bookID, sourceKey: key, query: query, resume: resume, cancel: box)
                DispatchQueue.main.async {
                    guard self.current?.id == bookID else { return }
                    self.search.accept(batch, key: key, generation: epoch)
                }
            } catch {
                DispatchQueue.main.async { self.search.fail(error, generation: epoch) }
            }
        }
    }

    func selectSearchHit(_ hit: HostSearchHit) {
        guard !busy, !search.running, current?.id == hit.bookID, search.bookID == hit.bookID,
              search.sourceKey == hit.sourceKey, search.rows.contains(where: { $0.id == hit.id }) else { return }
        let (myToken, box) = begin()
        statusText = "正在精确定位…"
        queue.async {
            do {
                guard let session = self.session, let catalog = self.catalog,
                      try catalog.searchSourceKey(sdkID: hit.bookID) == hit.sourceKey else {
                    throw HostError.invalidInput("原件身份已变化")
                }
                let (candidate, snapshot) = try session.searchCandidate(hit, cancel: box)
                if self.completeFrame(snapshot, session: candidate, token: myToken, status: "已精确定位选文", historyKind: 2) {
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
#if EXR_APPLE_PAGE_THEME
        let palette = pageThemePalette
#endif
        search.invalidate()
        navigation.invalidate()
        readingRecords.bind(nil)
        let (myToken, box) = begin()
        statusText = "正在打开…"
        queue.async {
            do {
                guard let session = self.session else { throw HostError.invalidInput("书库未就绪") }
                let candidate = session.candidate()
#if EXR_APPLE_PAGE_THEME
                candidate.configurePagePalette(palette)
#endif
                let snapshot = try candidate.open(bookID: row.id, cancel: box)
#if EXR_APPLE_WAVE3 && EXR_APPLE_RAW3
                // Establish original identity when opening the verified local
                // book, before any later read-only annotation preview.
                guard let catalog = self.catalog else { throw HostError.invalidInput("产品书库未就绪") }
                let book = try catalog.readingBook(sdkID: row.id)
                try catalog.withHistory { history in
                    try catalog.bootstrapVerified(book, store: history) {
                        try candidate.library.exportSyncOriginal(bookID: book.sdkID,
                            expected: HostSourceFingerprint(format: book.format, sha256: book.sha256, bytes: book.bytes),
                            directory: self.storageFolder().appendingPathComponent("sync-originals", isDirectory: true), cancel: box)
                        try box.check()
                    }
                }
#endif
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
        guard libraryReady else {
            traceUITest("import-rejected-unready")
#if EXR_APPLE_HOST_REVIEW
            reviewRejectedBeforeInitialization += 1
#endif
            errorText = "书库未就绪"
            statusText = "书库正在初始化，请稍候"
            return
        }
        guard !busy else { traceUITest("import-rejected-busy"); return }
        let (myToken, box) = begin()
        statusText = "正在导入…"
        traceUITest("import-accepted")
        queue.async {
            DispatchQueue.main.async { self.traceUITest("import-worker-begin source-token=\(myToken)") }
            let scoped = url.startAccessingSecurityScopedResource()
            defer { if scoped { url.stopAccessingSecurityScopedResource() } }
#if EXR_APPLE_HOST_REVIEW
            let priorPoll = HostSDKReview.poll
            let latch = CommandLine.arguments.contains("-EXRHoldSDKImportCancellation") && url.lastPathComponent == "Large.epub"
            if latch {
                var announced = false
                HostSDKReview.poll = { [weak self] polled in
                    guard polled === box else { priorPoll?(polled); return }
                    if !announced {
                        announced = true
                        DispatchQueue.main.async { [weak self] in
                            guard let self, self.token == myToken else { return }
                            self.uiTestCancellationReadyToken = myToken
                        }
                    }
                    // Hold at the real SDK cancellation callback, not a timed
                    // guess about how quickly the remote UI driver can tap.
                    while !polled.isCancelled { Thread.sleep(forTimeInterval: 0.05) }
                }
            }
            defer {
                if latch {
                    HostSDKReview.poll = priorPoll
                    DispatchQueue.main.async { [weak self] in
                        guard let self, self.uiTestCancellationReadyToken == myToken else { return }
                        self.uiTestCancellationReadyToken = nil
                    }
                }
            }
#endif
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
        search.invalidate()
        navigation.invalidate()
        readingRecords.bind(nil)
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
        search.cancel()
        navigation.cancel()
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
        libraryReady = true
        busy = false
    }
#endif
}
