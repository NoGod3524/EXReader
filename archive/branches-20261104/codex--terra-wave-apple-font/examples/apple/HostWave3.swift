// SPDX-License-Identifier: MIT
import Foundation
import Combine
import CEXReader
import CReaderProduct

#if EXR_APPLE_WAVE3 && EXR_APPLE_RAW3
struct HostWave3FontRow: Identifiable { let id: String; let name: String; let bytes: UInt64 }
struct HostWave3AnnotationPreview {
    let fingerprint: String
    let annotations: UInt64, heads: UInt64, found: UInt64, nullPreserved: UInt64
    let conflicts: UInt64, missingParents: UInt64, committed: UInt64, omittedHistory: UInt64
    let receivingGraphChecked: Bool
    let unresolved: UInt64, wouldCreate: UInt64, wouldDuplicate: UInt64
}
struct HostWave3ImportFailure: Error, LocalizedError {
    let preview: HostWave3AnnotationPreview
    let message: String
    let cancelled: Bool
    var errorDescription: String? { message + "；已提交 \(preview.committed) 个头，先前提交仍保留" }
}
struct HostWave3SyncSnapshot {
    let phase: String, reason: String
    let pending: Int, retried: Int, conflicts: Int
    let more: Bool
    let operations: UInt64
    let completedShards: UInt32
}
final class HostWave3State: ObservableObject {
    @Published var busy = false
    @Published var message = ""
    @Published var annotationPreview: HostWave3AnnotationPreview?
    @Published var canConfirmAnnotations = false
    @Published var fonts: [HostWave3FontRow] = []
    @Published var selectedFont: String?
#if EXR_APPLE_HOST_REVIEW
    @Published var fontObservation = "offset=0;live=0;acquired=0;released=0"
#endif
    @Published var exportURL: URL?
    @Published var canBack = false
    @Published var canForward = false
    @Published var sync: HostWave3SyncSnapshot?
}

private final class HostWave3ImportContext {
    let cancel: HostCancelBox
    let resolve: (UnsafePointer<reader_rs_record>) throws -> Bool
    var conflicts: UInt64 = 0, missing: UInt64 = 0
    init(cancel: HostCancelBox, resolve: @escaping (UnsafePointer<reader_rs_record>) throws -> Bool) {
        self.cancel = cancel; self.resolve = resolve
    }
}

// One original verification and bounded SDK snapshot per imported file. A
// hostile many-head file cannot trigger one full original hash per head.
final class HostWave3AnnotationResolver {
    private let library: HostLibrary, font: HostFont, book: HostBook, bookID: Int64, key: String, cancel: HostCancelBox
    private var document: HostDocument?, fixed: HostFixed?, publication: HostPublication?, pager: HostPager?
    private var pagerPart: Int?
    init(library: HostLibrary, font: HostFont, bookID: Int64, key: String, cancel: HostCancelBox) throws {
        guard let book = try library.books().first(where: { $0.id == bookID }) else { throw HostError.invalidInput("原件不可用") }
        let original = try library.sourceFingerprint(book: book, cancel: cancel)
        guard key == original.format + ":" + original.sha256 else { throw HostError.invalidInput("当前原件身份已变化") }
        self.library = library; self.font = font; self.book = book; self.bookID = bookID; self.key = key; self.cancel = cancel
    }
    func resolve(_ record: UnsafePointer<reader_rs_record>) throws -> Bool {
        try cancel.check()
        let value = record.pointee
        guard hostReadingField(value.book_key) == key, value.has_location != 0, value.exact != nil,
              HostReadingWorker.acceptsParser(hostReadingField(value.parser_version)),
              value.start <= UInt64(Int.max), value.end <= UInt64(Int.max), value.part <= UInt64(Int.max) else { return false }
        if value.mode == READER_RS_FIXED_PAGE && book.isFixed {
            if fixed == nil { fixed = try library.fixed(bookID: bookID, font: font, cancel: cancel) }
            let fixed = self.fixed!, pageID = hostString(value.page_id)
            let choices = fixed.pageIDs.enumerated().filter { $0.element.utf8.elementsEqual(pageID.utf8) }
            guard !pageID.isEmpty, choices.count == 1, value.page == UInt64(choices[0].offset) else { return false }
            let text = try fixed.text(page: choices[0].offset, cancel: cancel)
            var anchor = exr_fixed_anchor()
            anchor.start = Int(value.start); anchor.end = Int(value.end)
            anchor.page_id = value.page_id; anchor.exact = value.exact; anchor.prefix = value.prefix; anchor.suffix = value.suffix
            anchor.exact_size = value.exact_size; anchor.prefix_size = value.prefix_size; anchor.suffix_size = value.suffix_size
            return try text.resolve(anchor, pageID: pageID, cancel: cancel).isFound
        }
        guard !book.isFixed else { return false }
        var anchor = exr_anchor()
        anchor.start = Int(value.start); anchor.end = Int(value.end)
        anchor.exact = value.exact; anchor.prefix = value.prefix; anchor.suffix = value.suffix
        if value.mode == READER_RS_EPUB_CHAPTER, try library.isBoundedEPUB(book: book) {
            if publication == nil { publication = try HostPublication(library: library, bookID: bookID, cancel: cancel) }
            let publication = self.publication!, path = hostString(value.part_path), part: Int
            if value.anchor_version == 1 {
                let choices = publication.parts.filter { $0.reading && $0.path.utf8.elementsEqual(path.utf8) }
                guard choices.count == 1 else { return false }
                part = choices[0].index
            } else {
                part = Int(value.part); _ = try publication.route(part, path: path)
            }
            if pagerPart != part { pager = try HostPager(publication: publication, part: part, font: font, width: 600, height: 800, fontSize: 28, box: cancel); pagerPart = part }
            anchor.chapter = value.part_path
            return try self.pager!.resolveInput(anchor, cancel: cancel).isFound
        }
        guard value.mode == READER_RS_REFLOW_GLOBAL, try !library.isBoundedEPUB(book: book) else { return false }
        if document == nil { document = try library.document(bookID: bookID, cancel: cancel) }
        anchor.chapter = value.chapter
        return try self.document!.resolveInput(anchor, cancel: cancel).isFound
    }
}
// All these operations run synchronously behind the existing host SDK owner.
// No borrowed native value crosses an operation boundary.
enum HostWave3Worker {
    static func annotations(catalog: HostCatalog, key: String, file: URL, confirmation: String?,
        cancel: HostCancelBox, resolve: @escaping (UnsafePointer<reader_rs_record>) throws -> Bool) throws -> HostWave3AnnotationPreview {
        let context = HostWave3ImportContext(cancel: cancel, resolve: resolve)
        return try catalog.withHistory { history in
            try cancel.check()
            var options = reader_ai3_options(), stats = reader_ai3_stats(), error = reader_ai3_error()
            options.struct_size = MemoryLayout<reader_ai3_options>.size
            options.revisions = history; options.mode = confirmation == nil ? READER_AI3_PREVIEW : READER_AI3_COMMIT
            options.policy = READER_AI3_RESOLVE_REQUIRED
            options.context = Unmanaged.passUnretained(context).toOpaque()
            options.cancel = { raw in
                guard let raw else { return 1 }
                return Unmanaged<HostWave3ImportContext>.fromOpaque(raw).takeUnretainedValue().cancel.isCancelled ? 1 : 0
            }
            options.resolve = { raw, record, _ in
                guard let raw, let record else { return 0 }
                let context = Unmanaged<HostWave3ImportContext>.fromOpaque(raw).takeUnretainedValue()
                return (try? context.resolve(record)) == true ? 1 : 0
            }
            options.item = { raw, item in
                guard let raw, let item else { return 1 }
                let context = Unmanaged<HostWave3ImportContext>.fromOpaque(raw).takeUnretainedValue()
                if item.pointee.graph.heads > 1 { context.conflicts += 1 }
                if item.pointee.graph.missing_parents > 0 || item.pointee.graph.foreign_parents > 0 { context.missing += 1 }
                return context.cancel.isCancelled ? 1 : 0
            }
            if let confirmation {
                guard confirmation.utf8.count == 64, confirmation.utf8.allSatisfy({ (48...57).contains($0) || (97...102).contains($0) }) else {
                    throw HostError.invalidInput("请先预览并确认完整文件摘要")
                }
                withUnsafeMutableBytes(of: &options.confirm_fingerprint) { bytes in
                    for (i, value) in confirmation.utf8.enumerated() { bytes[i] = value }
                }
            }
            let status = file.path.withCString { path in key.withCString { book in
                options.jsonl_path = path; options.target_book_key = book
                return reader_annotation_import_raw3_run(&options, &stats, &error)
            } }
            let receipt = HostWave3AnnotationPreview(fingerprint: hostReadingField(stats.fingerprint), annotations: stats.annotations,
                heads: stats.head_wires, found: stats.found, nullPreserved: stats.null_preserved,
                conflicts: context.conflicts, missingParents: context.missing, committed: stats.committed, omittedHistory: stats.omitted_history,
                receivingGraphChecked: confirmation != nil && stats.committed > 0, unresolved: stats.unresolved,
                wouldCreate: stats.would_create, wouldDuplicate: stats.would_duplicate)
            guard status == READER_AI3_OK else {
                throw HostWave3ImportFailure(preview: receipt, message: status == READER_AI3_CANCELLED ? "导入已取消" : hostReadingField(error.message), cancelled: status == READER_AI3_CANCELLED)
            }
            return receipt
        }
    }

    static func exportAnnotations(catalog: HostCatalog, key: String, directory: URL, markdown: Bool, cancel: HostCancelBox) throws -> URL {
        let destination = directory.appendingPathComponent("annotations-" + UUID().uuidString.lowercased() + (markdown ? ".md" : ".jsonl"))
        return try catalog.withHistory { revisions in
            var options = reader_annotation_export_options(), stats = reader_annotation_export_stats(), error = reader_annotation_export_error()
            options.struct_size = MemoryLayout<reader_annotation_export_options>.size
            options.revisions = revisions; options.cancel_context = Unmanaged.passUnretained(cancel).toOpaque()
            options.cancel = { raw in raw.map { Unmanaged<HostCancelBox>.fromOpaque($0).takeUnretainedValue().isCancelled ? 1 : 0 } ?? 1 }
            let status = key.withCString { book in destination.path.withCString { path in
                options.book_key = book
                if markdown { options.markdown_path = path } else { options.jsonl_path = path }
                return reader_annotation_export_raw3_run(&options, &stats, &error)
            } }
            if status == READER_ANNOTATION_EXPORT_CANCELLED { throw HostError.cancelled }
            guard status == READER_ANNOTATION_EXPORT_OK, (markdown ? stats.markdown_published != 0 : stats.jsonl_published != 0) else {
                throw HostError.invalidResult(hostReadingField(error.message))
            }
            return destination
        }
    }
    static func exportOriginal(library: HostLibrary, bookID: Int64, directory: URL, cancel: HostCancelBox) throws -> URL {
        try cancel.check()
        var exporter: OpaquePointer?, owner = roe_owner()
        // The enclosing host serial queue owns every SDK operation throughout this call.
        owner.enter = { _ in 0 }; owner.leave = { _ in }
        guard roe_create(library.handle, &owner, &exporter) == ROE_OK, let active = exporter else {
            throw HostError.invalidResult("原件导出器无法创建")
        }
        defer { _ = roe_destroy(&exporter) }
        var options = roe_options(), selected = roe_selection(), result: UnsafeMutablePointer<roe_result>?
        selected.book_id = bookID; options.naming = ROE_HASH_NAME
        options.callbacks.context = Unmanaged.passUnretained(cancel).toOpaque()
        options.callbacks.cancelled = { raw in
            raw.map { Unmanaged<HostCancelBox>.fromOpaque($0).takeUnretainedValue().isCancelled ? 1 : 0 } ?? 1
        }
        let status = directory.path.withCString { path in
            options.directory = path
            return roe_run(active, &selected, 1, &options, &result)
        }
        defer { if let result { roe_result_free(result) } }
        guard let result, result.pointee.count == 1 else { throw HostError.invalidResult("原件导出缺少回执") }
        let item = withUnsafePointer(to: &result.pointee.items) { $0.withMemoryRebound(to: roe_item.self, capacity: 100) { $0.pointee } }
        if status == ROE_CANCELLED { throw HostError.cancelled }
        guard status == ROE_OK, item.committed != 0, item.durable != 0, item.cleanup_pending == 0 else {
            throw HostError.invalidResult("原件导出未完成（状态 \(status.rawValue)，清理 \(item.cleanup_pending)）；已发布副本不会回滚")
        }
        return URL(fileURLWithPath: hostReadingField(item.output_path))
    }

    static func sync(session: OpaquePointer, catalog: HostCatalog) throws -> HostWave3SyncSnapshot {
        try catalog.withHistory { revisions in
            var options = reader_sync_view_options(), snapshot: OpaquePointer?, error = reader_sync_view_error()
            options.row_limit = 100; options.detect_conflicts = 1
            guard reader_sync_view_capture(session, revisions, &options, &snapshot, &error) == READER_SYNC_VIEW_OK, let snapshot else {
                throw HostError.invalidResult(hostReadingField(error.message))
            }
            var released: OpaquePointer? = snapshot
            defer { _ = reader_sync_view_release(&released) }
            var summary = reader_sync_view_summary()
            guard reader_sync_view_summary_get(snapshot, &summary) == READER_SYNC_VIEW_OK else { throw HostError.invalidResult("同步快照不可用") }
            return HostWave3SyncSnapshot(phase: String(cString: reader_sync_view_phase_text(summary.phase)),
                reason: String(cString: reader_sync_view_reason_text(summary.reason)), pending: summary.pending_records,
                retried: summary.retried_records, conflicts: summary.conflict_records, more: summary.more_may_exist != 0,
                operations: summary.operations, completedShards: UInt32(summary.completed_shards))
        }
    }
}

// Native font handles belong to this OS thread, including lease release. The
// owner can serve import/list calls while an accepted renderer retains a lease.
private final class HostWave3FontCommands {
    let condition = NSCondition()
    var commands: [(OpaquePointer) -> Void] = []
    var stopped = false
    var opened: Result<OpaquePointer, Error>?
    let closed = DispatchSemaphore(value: 0)
}
private final class HostWave3FontWeak { weak var value: HostWave3FontOwner?; init(_ value: HostWave3FontOwner) { self.value = value } }
private final class HostWave3FontValue<T> { var result: Result<T, Error>? }
private final class HostWave3FontOwner {
    private static let lock = NSLock()
    private static var owners: [String: HostWave3FontWeak] = [:]
    private let commands = HostWave3FontCommands()
    static func shared(_ root: URL) throws -> HostWave3FontOwner {
        lock.lock(); defer { lock.unlock() }
        if let owner = owners[root.path]?.value { return owner }
        owners = owners.filter { $0.value.value != nil }
        let owner = try HostWave3FontOwner(root: root)
        owners[root.path] = HostWave3FontWeak(owner)
        return owner
    }
    private init(root: URL) throws {
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        let state = commands, ready = DispatchSemaphore(value: 0)
        Thread.detachNewThread {
            var library: OpaquePointer?, error = rfl_error()
            let status = root.path.withCString { rfl_open($0, nil, &library, &error) }
            if status != RFL_OK || library == nil {
                state.opened = .failure(HostError.invalidResult(hostReadingField(error.message)))
                ready.signal(); state.closed.signal(); return
            }
            let active = library!
            state.opened = .success(active); ready.signal()
            while true {
                state.condition.lock()
                while state.commands.isEmpty && !state.stopped { state.condition.wait() }
                if state.commands.isEmpty && state.stopped { state.condition.unlock(); break }
                let command = state.commands.removeFirst()
                state.condition.unlock(); command(active)
            }
            _ = rfl_close(active, nil); state.closed.signal()
        }
        ready.wait()
        guard let opened = commands.opened else { throw HostError.invalidResult("字体 owner 未返回") }
        _ = try opened.get()
    }
    deinit { commands.condition.lock(); commands.stopped = true; commands.condition.signal(); commands.condition.unlock(); commands.closed.wait() }
    func run<T>(_ operation: @escaping (OpaquePointer) throws -> T) throws -> T {
        let done = DispatchSemaphore(value: 0), box = HostWave3FontValue<T>()
        commands.condition.lock()
        commands.commands.append { library in
            box.result = Result { try operation(library) }; done.signal()
        }
        commands.condition.signal(); commands.condition.unlock(); done.wait()
        guard let result = box.result else { throw HostError.invalidResult("字体操作未返回") }
        return try result.get()
    }
}
final class HostWave3FontLease {
#if EXR_APPLE_HOST_REVIEW
    private static let observationLock = NSLock()
    private static var acquired = 0, released = 0
    static func observation(offset: Int) -> String {
        observationLock.lock(); defer { observationLock.unlock() }
        return "offset=\(offset);live=\(acquired - released);acquired=\(acquired);released=\(released)"
    }
#endif
    let font: OpaquePointer
    private let owner: HostWave3FontOwner
    private let lease: OpaquePointer
    private init(font: OpaquePointer, lease: OpaquePointer, owner: HostWave3FontOwner) {
        self.font = font; self.lease = lease; self.owner = owner
    }
    deinit {
        let lease = lease
        let status = try? owner.run { _ in rfl_lease_release(lease, nil) }
#if EXR_APPLE_HOST_REVIEW
        if status == RFL_OK {
            Self.observationLock.lock(); Self.released += 1; Self.observationLock.unlock()
        }
#else
        _ = status
#endif
    }
    static func acquire(root: URL, hash: String) throws -> HostWave3FontLease {
        let owner = try HostWave3FontOwner.shared(root)
        let opened: (OpaquePointer, OpaquePointer) = try owner.run { library in
            var lease: OpaquePointer?, font: OpaquePointer?, error = rfl_error()
            guard hash.withCString({ rfl_font_open(library, $0, 0, &lease, &error) }) == RFL_OK, let lease else {
                throw HostError.invalidResult(hostReadingField(error.message))
            }
            guard rfl_lease_font(lease, &font, &error) == RFL_OK, let font else {
                _ = rfl_lease_release(lease, nil); throw HostError.invalidResult(hostReadingField(error.message))
            }
            return (font, lease)
        }
#if EXR_APPLE_HOST_REVIEW
        observationLock.lock(); acquired += 1; observationLock.unlock()
#endif
        return HostWave3FontLease(font: opened.0, lease: opened.1, owner: owner)
    }
}
enum HostWave3Fonts {
    static func records(root: URL, importing file: URL? = nil, cancel: HostCancelBox) throws -> [HostWave3FontRow] {
        let owner = try HostWave3FontOwner.shared(root)
        return try owner.run { library in
            try cancel.check()
            var error = rfl_error()
            if let file {
                var record = rfl_record(), created: Int32 = 0, control = rfl_control()
                control.context = Unmanaged.passUnretained(cancel).toOpaque()
                control.progress = { raw, _, _, _ in raw.map { Unmanaged<HostCancelBox>.fromOpaque($0).takeUnretainedValue().isCancelled ? 1 : 0 } ?? 1 }
                let name = String(file.deletingPathExtension().lastPathComponent.prefix(60))
                let status = file.path.withCString { path in name.withCString { rfl_import_file(library, path, $0, &control, &record, &created, &error) } }
                if status == RFL_CANCELLED { throw HostError.cancelled }
                guard status == RFL_OK else { throw HostError.invalidResult(hostReadingField(error.message)) }
            }
            var count = 0
            guard rfl_count(library, &count, &error) == RFL_OK else { throw HostError.invalidResult(hostReadingField(error.message)) }
            var rows: [HostWave3FontRow] = []
            for index in 0..<count {
                var value = rfl_record()
                guard rfl_get(library, index, &value, &error) == RFL_OK else { throw HostError.invalidResult(hostReadingField(error.message)) }
                rows.append(HostWave3FontRow(id: hostReadingField(value.hash), name: hostReadingField(value.display_name), bytes: value.bytes))
            }
            return rows
        }
    }
}

final class HostWave3HistoryTicket {
    fileprivate var item: reader_jh_item
    var wire: Data { item.wire.map { Data(bytes: $0, count: item.wire_bytes) } ?? Data() }
    var bookKey: String { hostReadingField(item.book_key) }
    init(_ item: reader_jh_item) { self.item = item }
    deinit { reader_jh_item_release(&item) }
}
final class HostWave3History {
    private var handle: OpaquePointer?
    private func owned() throws -> OpaquePointer {
        if handle == nil { guard reader_jh_open(nil, &handle, nil) == READER_JH_OK else { throw HostError.invalidResult("阅读历史无法打开") } }
        guard let handle, reader_jh_adopt_thread(handle, nil) == READER_JH_OK else { throw HostError.invalidResult("阅读历史 owner 不可用") }
        return handle
    }
    deinit { if let handle { _ = reader_jh_adopt_thread(handle, nil) }; _ = reader_jh_close(&handle, nil) }
    func state() throws -> (Bool, Bool) {
        let active = try owned(); var state = reader_jh_state()
        guard reader_jh_state_get(active, &state, nil) == READER_JH_OK else { throw HostError.invalidResult("阅读历史状态不可用") }
        return (state.can_back != 0, state.can_forward != 0)
    }
    func commit(catalog: HostCatalog, capture: HostReadingCapture, key: String, kind: reader_jh_kind) throws {
        let active = try owned()
        func perform(_ revisions: OpaquePointer) throws {
            try capture.withRaw { raw in
                try key.withCString { book in try HOST_SDK_VERSION.withCString { parser in
                    var position = reader_jh_position(), result = reader_jh_result(), error = reader_jh_error(), raw = raw
                    position.book_key = book; position.parser_version = parser; position.kind = kind; position.part = capture.part
                    let status = withUnsafePointer(to: &raw) { pointer -> reader_jh_status in
                        position.capture = pointer
                        return capture.mode == 3 ? reader_jh_commit_fixed_v3(active, revisions, &position, &result, &error) : reader_jh_commit(active, revisions, &position, &result, &error)
                    }
                    guard status == READER_JH_OK else { throw HostError.invalidResult(hostReadingField(error.message)) }
                } }
            }
        }
        if capture.mode == 3 { try catalog.withHistory(perform) }
        else { try catalog.withLegacyHistory(perform) }
    }
    func commitWire(catalog: HostCatalog, wire: Data, kind: reader_jh_kind) throws {
        let active = try owned()
        try catalog.withHistory { revisions in
            var result = reader_jh_result(), error = reader_jh_error()
            let status = wire.withUnsafeBytes { reader_jh_commit_wire_raw_v3(active, revisions, kind, $0.baseAddress, $0.count, &result, &error) }
            guard status == READER_JH_OK else { throw HostError.invalidResult(hostReadingField(error.message)) }
        }
    }
    func peek(back: Bool) throws -> HostWave3HistoryTicket {
        let active = try owned(); var item = reader_jh_item(), error = reader_jh_error()
        guard reader_jh_peek(active, back ? READER_JH_BACK : READER_JH_FORWARD, &item, &error) == READER_JH_OK else {
            throw HostError.invalidResult(hostReadingField(error.message))
        }
        return HostWave3HistoryTicket(item)
    }
    // Call only after the parent has accepted a rendered public FOUND candidate.
    func complete(_ ticket: HostWave3HistoryTicket) throws {
        let active = try owned(); var error = reader_jh_error()
        guard reader_jh_complete(active, &ticket.item, &error) == READER_JH_OK else { throw HostError.invalidResult(hostReadingField(error.message)) }
    }
}
#endif
