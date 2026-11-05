// SPDX-License-Identifier: MIT
#if EXR_APPLE_WAVE3
import Foundation
import Combine
import CEXReader
import CReaderProduct
import CReaderAppleFeatures

// Font-library calls are thread-affine, unlike a serial DispatchQueue. This
// permanent native owner services only synchronous requests from the SDK owner.
// No layout outlives HostFont; its final release returns the borrowed lease here.
final class HostFontThread {
    static let shared = HostFontThread()
    private let condition = NSCondition()
    private var jobs: [() -> Void] = []
    private init() {
        Thread.detachNewThread { [self] in
            Thread.current.name = "org.exreader.font-lease-owner"
            Thread.current.threadDictionary["EXRFontOwner"] = true
            while true {
                condition.lock()
                while jobs.isEmpty { condition.wait() }
                let job = jobs.removeFirst(); condition.unlock(); job()
            }
        }
    }
    func call<T>(_ body: @escaping () throws -> T) throws -> T {
        if Thread.current.threadDictionary["EXRFontOwner"] as? Bool == true { return try body() }
        let done = DispatchSemaphore(value: 0)
        var result: Result<T, Error>!
        condition.lock(); jobs.append { result = Result { try body() }; done.signal() }; condition.signal(); condition.unlock()
        done.wait(); return try result.get()
    }
}

private final class HostFontLibrary {
    private final class Weak { weak var value: HostFontLibrary?; init(_ value: HostFontLibrary) { self.value = value } }
    private static var libraries: [String: Weak] = [:] // Accessed only by HostFontThread.
    let handle: OpaquePointer
    static func open(_ directory: URL) throws -> HostFontLibrary {
        if let existing = libraries[directory.path]?.value { return existing }
        let value = try HostFontLibrary(directory)
        libraries[directory.path] = Weak(value); return value
    }
    private init(_ directory: URL) throws {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        var value: OpaquePointer?, error = rfl_error()
        guard rfl_open(directory.path, nil, &value, &error) == RFL_OK, let value else {
            throw HostError.invalidInput("字体库被锁定或无法打开：\(hostReadingField(error.message))")
        }
        handle = value
    }
    deinit {
        let handle = handle
        _ = try? HostFontThread.shared.call { var error = rfl_error(); precondition(rfl_close(handle, &error) == RFL_OK) }
    }
}
final class HostFontLease {
    private let library: HostFontLibrary
    private let lease: OpaquePointer
    let font: OpaquePointer
    let hash: String
    init(directory: URL, selected: URL, cancel: HostCancelBox) throws {
        let library = try HostFontLibrary.open(directory)
        var lease: OpaquePointer?, font: OpaquePointer?, error = rfl_error()
        var record = rfl_record(), created: Int32 = 0, control = rfl_control()
        control.context = Unmanaged.passUnretained(cancel).toOpaque()
        control.progress = { context, _, _, _ in
            guard let context else { return 1 }
            return Unmanaged<HostCancelBox>.fromOpaque(context).takeUnretainedValue().isCancelled ? 1 : 0
        }
        guard rfl_import_file(library.handle, selected.path, selected.lastPathComponent, &control, &record, &created, &error) == RFL_OK else {
            throw HostError.invalidInput("字体导入失败：\(hostReadingField(error.message))")
        }
        let hash = hostReadingField(record.hash)
        guard rfl_font_open(library.handle, hash, 0, &lease, &error) == RFL_OK, let borrowed = lease else {
            throw HostError.invalidInput("字体 lease 失败：\(hostReadingField(error.message))")
        }
        guard rfl_lease_font(borrowed, &font, &error) == RFL_OK, let pointer = font else {
            _ = rfl_lease_release(borrowed, &error); throw HostError.invalidInput("字体借用失败")
        }
        self.library = library; self.lease = borrowed; self.font = pointer; self.hash = hash
    }
    deinit {
        let lease = lease
        _ = try? HostFontThread.shared.call { var error = rfl_error(); precondition(rfl_lease_release(lease, &error) == RFL_OK) }
    }
}

struct HostImportPreview {
    let file: URL
    let fingerprint: String
    let bookKey: String
    let count: UInt64
    let nulls: UInt64
    let duplicates: UInt64
    let omitted: UInt64
}
final class HostFeatureState: ObservableObject {
    @Published var status = "所有操作使用已安装原生模块"
    @Published var preview: HostImportPreview?
    @Published var canBack = false
    @Published var canForward = false
    @Published var fontName = "内置字体"
    @Published var exported: URL?
    @Published var sync = "本地书库：尚无同步会话"
}
final class HostImportContext {
    let session: HostSession
    let cancel: HostCancelBox
    init(_ session: HostSession, _ cancel: HostCancelBox) { self.session = session; self.cancel = cancel }
}

final class HostJumpHistory {
    private var handle: OpaquePointer?
    private func owned() throws -> OpaquePointer {
        var error = reader_jh_error()
        if handle == nil { guard reader_jh_open(nil, &handle, &error) == READER_JH_OK else { throw HostError.invalidResult("历史无法创建") } }
        guard let handle, reader_jh_adopt_thread(handle, &error) == READER_JH_OK else { throw HostError.invalidResult("历史 owner 不可用") }
        return handle
    }
    deinit {
        if let handle { var error = reader_jh_error(); _ = reader_jh_adopt_thread(handle, &error); _ = reader_jh_close(&self.handle, &error) }
    }
    func capture(_ session: HostSession, catalog: HostCatalog, kind: reader_jh_kind) throws {
        let cancel = HostCancelBox(), handle = try owned()
        guard let book = session.book else { return }
        let identity = try catalog.readingBook(sdkID: book.id)
        let capture = try session.readingCapture(cancel: cancel)
        let encode: (OpaquePointer) throws -> Void = { history in
            try identity.key.withCString { key in
                try capture.withRaw { raw in
                    try withUnsafePointer(to: raw) { pointer in
                        var position = reader_jh_position(); position.book_key = key
                        position.parser_version = exr_version(); position.kind = kind; position.capture = pointer; position.part = capture.part
                        var result = reader_jh_result(), error = reader_jh_error()
                        let status = capture.mode == 3 ? reader_jh_commit_fixed_v3(handle, history, &position, &result, &error) :
                            reader_jh_commit(handle, history, &position, &result, &error)
                        guard status == READER_JH_OK else { throw HostError.invalidInput("当前位置无法加入历史：\(hostReadingField(error.message))") }
                    }
                }
            }
        }
        if capture.mode == 3 { try catalog.withHistory(encode) }
        else { try catalog.withLegacyEncoder(encode) }
    }
    func state() throws -> reader_jh_state {
        var value = reader_jh_state(), error = reader_jh_error()
        guard reader_jh_state_get(try owned(), &value, &error) == READER_JH_OK else { throw HostError.invalidResult("历史无法读取") }
        return value
    }
    func peek(_ direction: reader_jh_direction) throws -> reader_jh_item {
        var item = reader_jh_item(), error = reader_jh_error()
        guard reader_jh_peek(try owned(), direction, &item, &error) == READER_JH_OK else { throw HostError.invalidInput("此方向没有可返回位置") }
        return item
    }
    func complete(_ item: inout reader_jh_item) throws {
        var error = reader_jh_error()
        guard reader_jh_complete(try owned(), &item, &error) == READER_JH_OK else { throw HostError.invalidInput("历史已变化，未移动历史游标") }
    }
}

func hostFeatureImport(_ file: URL, preview: HostImportPreview?, session: HostSession,
                       catalog: HostCatalog, cancel: HostCancelBox) throws -> (HostImportPreview, String) {
    guard let book = session.book else { throw HostError.invalidInput("请先打开书籍") }
    let identity = try catalog.readingBook(sdkID: book.id)
    if let preview, preview.bookKey != identity.key { throw HostError.invalidInput("书籍已切换，请重新预览") }
    let context = HostImportContext(session, cancel)
    return try catalog.withHistory { history in
        try hostProductStrings([file.path, identity.key]) { strings in
            var options = reader_ai3_options(), stats = reader_ai3_stats(), error = reader_ai3_error()
            options.struct_size = MemoryLayout<reader_ai3_options>.size; options.revisions = history
            options.jsonl_path = strings[0]; options.target_book_key = strings[1]
            options.mode = preview == nil ? READER_AI3_PREVIEW : READER_AI3_COMMIT
            options.policy = READER_AI3_RESOLVE_REQUIRED
            options.context = Unmanaged.passUnretained(context).toOpaque()
            options.cancel = { context in
                guard let context else { return 1 }
                return Unmanaged<HostImportContext>.fromOpaque(context).takeUnretainedValue().cancel.isCancelled ? 1 : 0
            }
            options.resolve = { context, record, _ in
                guard let context, let record else { return 0 }
                let value = Unmanaged<HostImportContext>.fromOpaque(context).takeUnretainedValue()
                return (try? value.session.featureResolve(record.pointee, cancel: value.cancel)) == true ? 1 : 0
            }
            if let preview {
                withUnsafeMutableBytes(of: &options.confirm_fingerprint) { target in
                    let bytes = Array(preview.fingerprint.utf8) + [0]
                    target.copyBytes(from: bytes)
                }
            }
            let result = reader_annotation_import_raw3_run(&options, &stats, &error)
            guard result == READER_AI3_OK else {
                throw HostError.invalidInput("标注导入失败 code=\(result.rawValue)，已提交 \(stats.committed)，可从原文件重试：\(hostReadingField(error.message))")
            }
            let value = HostImportPreview(file: file, fingerprint: hostReadingField(stats.fingerprint), bookKey: identity.key,
                count: stats.head_wires, nulls: stats.null_preserved, duplicates: stats.would_duplicate, omitted: stats.omitted_history)
            return (value, preview == nil ? "预览完成，尚未写入" : "已提交 \(stats.committed)，新增 \(stats.created)，重复 \(stats.duplicates)；未补造祖先历史")
        }
    }
}

func hostFeatureOriginal(_ directory: URL, session: HostSession, cancel: HostCancelBox) throws -> URL {
    guard let book = session.book else { throw HostError.invalidInput("请先打开书籍") }
    var owner = roe_owner(), exporter: OpaquePointer?
    // This entire synchronous call is enclosed by HostReaderModel.queue. No
    // callback enters the SDK, and no other operation can run until it returns.
    owner.enter = { _ in 0 }; owner.leave = { _ in }
    guard roe_create(session.library.handle, &owner, &exporter) == ROE_OK, let opened = exporter else { throw HostError.invalidResult("原件导出 owner 失败") }
    defer { _ = roe_destroy(&exporter) }
    var selection = roe_selection(); selection.book_id = book.id
    var options = roe_options(); options.naming = ROE_HASH_NAME
    options.callbacks.context = Unmanaged.passUnretained(cancel).toOpaque()
    options.callbacks.cancelled = { context in
        guard let context else { return 1 }
        return Unmanaged<HostCancelBox>.fromOpaque(context).takeUnretainedValue().isCancelled ? 1 : 0
    }
    var receipt: UnsafeMutablePointer<roe_result>?
    let status = directory.path.withCString { path -> roe_status in
        options.directory = path; return roe_run(opened, &selection, 1, &options, &receipt)
    }
    defer { if let receipt { roe_result_free(receipt) } }
    guard let receipt else { throw HostError.invalidResult("原件导出无回执 code=\(status.rawValue)") }
    let item = withUnsafePointer(to: receipt.pointee.items) {
        $0.withMemoryRebound(to: roe_item.self, capacity: 100) { $0.pointee }
    }
    guard status == ROE_OK, item.committed != 0 else { throw HostError.invalidInput("原件未完整导出 code=\(status.rawValue)，已提交=\(item.committed)，清理待办=\(item.cleanup_pending)") }
    return URL(fileURLWithPath: hostReadingField(item.output_path))
}
#endif
