// SPDX-License-Identifier: MIT
// Installed-package example: the SDK owner turns one FileEntryRequest into a
// library book through the public sideload module. Compile with
// -import-objc-header SdkBridge.h, -I <sdk>/include -I <sideload>/include,
// -I <file-entry>/lib/swift and link libEXRFileEntry, libexr_sideload and the SDK.
import Foundation
import EXRFileEntry

public enum SdkImportOutcome: Equatable {
    case imported(bookID: Int64, created: Bool)
    case cancelled
    case failed(status: UInt32, message: String)
}

/// Imports the staged bytes of `request`; call it on the thread that owns
/// `library` (the SDK handle is not thread-safe) and keep that thread off the
/// main thread for large books. The SDK reads the staged file; the source URL
/// and its security scope are not involved any more.
///
/// - `format` defaults to the request's extension hint; pass the user's choice
///   when the hint is nil.
/// - Cancellation is polled by the SDK between 64 KiB chunks; a result the SDK
///   already committed is returned as `.imported`, never as `.cancelled`.
/// - The staged request is released only after `.imported`. On `.cancelled` or
///   `.failed` it stays staged so the import can be retried or discarded.
public func importStagedRequest(library: OpaquePointer, area: FileEntryStagingArea,
                                request: FileEntryRequest, format: FileFormatHint? = nil,
                                cancellation: FileEntryCancellation = FileEntryCancellation()) -> SdkImportOutcome {
    guard let hint = format ?? request.format else {
        return .failed(status: EXR_UNSUPPORTED.rawValue, message: "unknown format")
    }
    let exrFormat = exr_format(rawValue: UInt32(hint.exrFormatRawValue))
    var options = exr_sideload_options()
    options.struct_size = MemoryLayout<exr_sideload_options>.size
    options.control.context = Unmanaged.passUnretained(cancellation).toOpaque()
    options.control.cancelled = { context in
        guard let context = context else { return 0 }
        return Unmanaged<FileEntryCancellation>.fromOpaque(context).takeUnretainedValue().isCancelled ? 1 : 0
    }
    var result = exr_sideload_result()
    result.struct_size = MemoryLayout<exr_sideload_result>.size
    var error = exr_error()
    let title = (request.displayName as NSString).deletingPathExtension
    let status = request.stagedPath.withCString { path in
        title.withCString { text in
            exr_sideload_import_file(library, exrFormat, path, text, &options, &result, &error)
        }
    }
    if status == EXR_OK {
        area.release(request)
        return .imported(bookID: result.book_id, created: result.created != 0)
    }
    if status == EXR_CANCELLED { return .cancelled }
    let message = withUnsafePointer(to: &error.message) { pointer in
        pointer.withMemoryRebound(to: CChar.self, capacity: 256) { String(cString: $0) }
    }
    return .failed(status: status.rawValue, message: message)
}
