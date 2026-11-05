// SPDX-License-Identifier: MIT
// Public value types of the Apple file-entry component.
// The component has no dependency on the reading SDK: its product is a private
// staged file plus a FileEntryRequest that the SDK owner hands to
// exr_sideload_import_file().
import Foundation

/// Hard limits. They mirror the sideload import policy and can only be lowered.
public enum FileEntryLimits {
    /// EXR_SIDELOAD_STREAM_LIMIT: EPUB, CBZ and PDF.
    public static let streamFormatBytes: UInt64 = 128 * 1024 * 1024
    /// EXR_SIDELOAD_MEMORY_LIMIT: TXT, HTML, FB2, DOCX, RTF and MOBI.
    public static let memoryFormatBytes: UInt64 = 32 * 1024 * 1024
    /// Upper bound of one staged file, whatever its extension says.
    public static let maxFileBytes: UInt64 = streamFormatBytes
    /// Files accepted by one stage(urls:) call; the rest are reported tooManyFiles.
    public static let maxBatchCount = 64
    /// Staged-but-not-yet-released bytes and requests per staging directory.
    public static let maxPendingBytes: UInt64 = 1024 * 1024 * 1024
    public static let maxPendingRequests = 256
    /// The only buffer used while copying.
    public static let copyChunkBytes = 64 * 1024
    /// Entries returned by FileEntryInbox.candidates.
    public static let maxInboxEntries = 256
}

/// Nine formats of the sideload module, selected from the file extension only.
/// The hint never replaces the SDK's own format validation.
public enum FileFormatHint: String, CaseIterable, Equatable {
    case txt, html, fb2, epub, docx, rtf, mobi, pdf, cbz

    /// Value of the matching exr_format constant (EXR_TXT == 1 ... EXR_CBZ == 9).
    public var exrFormatRawValue: Int32 {
        switch self {
        case .txt: return 1
        case .html: return 2
        case .fb2: return 3
        case .epub: return 4
        case .docx: return 5
        case .rtf: return 6
        case .mobi: return 7
        case .pdf: return 8
        case .cbz: return 9
        }
    }

    /// Import-original byte policy of this format.
    public var byteLimit: UInt64 {
        switch self {
        case .epub, .cbz, .pdf: return FileEntryLimits.streamFormatBytes
        default: return FileEntryLimits.memoryFormatBytes
        }
    }

    /// Case-insensitive extension without the dot.
    public static func from(pathExtension: String) -> FileFormatHint? {
        switch pathExtension.lowercased() {
        case "txt": return .txt
        case "html", "htm", "xhtml": return .html
        case "fb2": return .fb2
        case "epub": return .epub
        case "docx": return .docx
        case "rtf": return .rtf
        case "mobi": return .mobi
        case "pdf": return .pdf
        case "cbz": return .cbz
        default: return nil
        }
    }
}

public enum FileEntryError: Error, Equatable {
    /// The staging area was closed; nothing was copied.
    case closed
    /// Cancellation was observed; no staged file remains.
    case cancelled
    /// A blocking call was made on the main thread; nothing was read.
    case calledOnMainThread
    case notFound
    /// Permission, revoked access or an expired security scope.
    case accessDenied
    /// Directory, FIFO, device or other non-regular item.
    case notRegularFile
    /// iCloud item without local bytes. downloadRequested tells whether the
    /// system was asked to fetch it; retry later.
    case notDownloaded(downloadRequested: Bool)
    /// The file is larger than the stated byte limit; nothing was copied.
    case tooLarge(limit: UInt64)
    /// The pending staged bytes or request count would exceed their cap.
    case tooManyPending
    /// Position in a batch beyond FileEntryLimits.maxBatchCount.
    case tooManyFiles(limit: Int)
    /// The source changed size or modification time while it was copied.
    case changedDuringCopy
    /// NSFileCoordinator failed (Cocoa error code).
    case coordination(code: Int)
    /// A system call failed at `stage`.
    case io(errno: Int32, stage: String)
}

/// A committed, app-private copy of one picked file.
///
/// The staged file is immutable and exclusively owned by the staging directory
/// until FileEntryStagingArea.release(_:) is called; it is safe to read after
/// the source's security scope was released or the source was deleted.
public struct FileEntryRequest: Equatable {
    public enum Origin: String, Equatable {
        case picker, inbox, other
    }

    /// Lowercase UUID; also the basename of the staged files.
    public let id: String
    /// Absolute filesystem path (UTF-8 when handed to C) of the staged bytes.
    public let stagedPath: String
    /// Last path component of the source, byte-for-byte as received: no
    /// Unicode normalization, no extension rewrite. Use as a title proposal.
    public let displayName: String
    public let byteCount: UInt64
    /// Lowercase hex SHA-256 of the staged bytes.
    public let sha256: String
    public let format: FileFormatHint?
    public let origin: Origin
}

/// Thread-safe, one-way cancellation flag. Create one per user operation.
public final class FileEntryCancellation {
    private let lock = NSLock()
    private var flag = false
    private var handlers: [() -> Void] = []

    public init() {}

    public var isCancelled: Bool {
        lock.lock()
        defer { lock.unlock() }
        return flag
    }

    /// Idempotent. Registered handlers run once, on the calling thread.
    public func cancel() {
        lock.lock()
        let pending = flag ? [] : handlers
        flag = true
        handlers = []
        lock.unlock()
        for handler in pending { handler() }
    }

    func onCancel(_ handler: @escaping () -> Void) {
        lock.lock()
        if flag {
            lock.unlock()
            handler()
            return
        }
        handlers.append(handler)
        lock.unlock()
    }
}

/// Security-scope access. The live implementation wraps
/// startAccessingSecurityScopedResource / stopAccessingSecurityScopedResource.
public protocol FileEntryScopeAccess {
    /// Returns true when the call must be balanced with stop(_:).
    func start(_ url: URL) -> Bool
    func stop(_ url: URL)
}

public struct LiveScopeAccess: FileEntryScopeAccess {
    public init() {}
    public func start(_ url: URL) -> Bool { url.startAccessingSecurityScopedResource() }
    public func stop(_ url: URL) { url.stopAccessingSecurityScopedResource() }
}

public enum FileEntryUbiquity: Equatable {
    case notUbiquitous
    case notDownloaded
    case available
}

/// Seams for faults the system cannot produce on demand. Production code uses
/// `.live`; the native probes inject faults and count scope calls.
public struct FileEntryHooks {
    public var scope: FileEntryScopeAccess
    public var ubiquity: (URL) -> FileEntryUbiquity
    /// Called on the copying thread after each chunk with its zero-based index
    /// and the source URL. Must not call close() on the staging area.
    public var afterChunk: ((Int, URL) -> Void)?

    public init(scope: FileEntryScopeAccess = LiveScopeAccess(),
                ubiquity: @escaping (URL) -> FileEntryUbiquity = FileEntryHooks.liveUbiquity,
                afterChunk: ((Int, URL) -> Void)? = nil) {
        self.scope = scope
        self.ubiquity = ubiquity
        self.afterChunk = afterChunk
    }

    public static var live: FileEntryHooks { FileEntryHooks() }

    public static func liveUbiquity(_ url: URL) -> FileEntryUbiquity {
        // iOS before 17 and some providers expose ".Name.ext.icloud" placeholders.
        let name = url.lastPathComponent
        if name.hasPrefix(".") && name.hasSuffix(".icloud") { return .notDownloaded }
        guard let values = try? url.resourceValues(forKeys: [.isUbiquitousItemKey, .ubiquitousItemDownloadingStatusKey]),
              values.isUbiquitousItem == true else { return .notUbiquitous }
        if values.ubiquitousItemDownloadingStatus == .notDownloaded { return .notDownloaded }
        return .available
    }
}
