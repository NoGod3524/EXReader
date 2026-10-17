// SPDX-License-Identifier: GPL-3.0-only
import Foundation
import CEXReader

public enum EXReaderError: Error {
    case engine(code: Int, message: String)
    case invalidInput
    case invalidResult
}
public struct EXReaderMetadataEntry {
    public let key: String
    public let value: String
}
private func metadataValues(_ entries: UnsafeMutablePointer<exr_metadata_entry>?, _ count: Int) throws -> [EXReaderMetadataEntry] {
    guard count > 0 else { return [] }
    guard let entries else { throw EXReaderError.invalidResult }
    return try (0..<count).map { index in
        guard let key = entries[index].key, let value = entries[index].value else { throw EXReaderError.invalidResult }
        return EXReaderMetadataEntry(key: String(cString: key), value: String(cString: value))
    }
}
public enum EXReaderMetadata {
    public static func readXMP(_ packet: Data) throws -> [EXReaderMetadataEntry] {
        var entries: UnsafeMutablePointer<exr_metadata_entry>?
        var count = 0
        var error = exr_error()
        let status = packet.withUnsafeBytes { bytes in
            exr_metadata_read_xmp(bytes.baseAddress, bytes.count, nil, &entries, &count, &error)
        }
        defer { exr_metadata_free(entries, count) }
        try check(status, error)
        return try metadataValues(entries, count)
    }
}
private func check(_ status: exr_status, _ error: exr_error) throws {
    guard status != EXR_OK else { return }
    var copy = error
    let message = withUnsafePointer(to: &copy.message) { pointer in
        pointer.withMemoryRebound(to: CChar.self, capacity: 256) { String(cString: $0) }
    }
    throw EXReaderError.engine(code: Int(status.rawValue), message: message)
}

public final class EXReaderFont {
    fileprivate let handle: OpaquePointer
    public init(data: Data, faceIndex: UInt32 = 0) throws {
        var result: OpaquePointer?
        var error = exr_error()
        let status = data.withUnsafeBytes { bytes -> exr_status in
            var input = exr_font_input()
            input.data = bytes.baseAddress
            input.size = bytes.count
            input.face_index = faceIndex
            return exr_font_create_glyphs(&input, 1, &result, &error)
        }
        try check(status, error)
        guard let result else { throw EXReaderError.invalidResult }
        handle = result
    }
    deinit { exr_font_free(handle) }
}

public struct EXReaderBitmap {
    public let width: Int
    public let height: Int
    public let stride: Int
    public let channels: Int
    public let pixels: Data
}
public struct EXReaderTextRegion {
    public let range: Range<Int> // UTF-8 bytes, not Swift String character indices.
    public let quad: [Double]
    public let flags: UInt32
}
public final class EXReaderPageText {
    private let handle: OpaquePointer
    fileprivate init(handle: OpaquePointer) { self.handle = handle }
    deinit { exr_fixed_text_free(handle) }
    public var utf8: Data {
        var size = 0
        guard let text = exr_fixed_text_string(handle, &size) else { return Data() }
        return Data(bytes: text, count: size)
    }
    public var string: String { String(decoding: utf8, as: UTF8.self) }
    public var regions: [EXReaderTextRegion] {
        var count = 0
        guard let regions = exr_fixed_text_regions(handle, &count) else { return [] }
        return (0..<count).map { index in
            let region = regions[index]
            let quad = withUnsafeBytes(of: region.quad) { Array($0.bindMemory(to: Double.self)) }
            return EXReaderTextRegion(range: region.start..<region.end, quad: quad, flags: region.flags)
        }
    }
    public func find(_ query: Data, from: Int = 0) throws -> Range<Int>? {
        guard from >= 0 else { throw EXReaderError.invalidInput }
        var start = 0, end = 0
        var error = exr_error()
        let status = query.withUnsafeBytes { bytes -> exr_status in
            let pointer = bytes.baseAddress?.assumingMemoryBound(to: CChar.self)
            return exr_fixed_text_find(handle, pointer, bytes.count, from, nil, &start, &end, &error)
        }
        try check(status, error)
        return start == -1 ? nil : start..<end // C SIZE_MAX imports as Int bit pattern -1.
    }
}

public final class EXReaderFixedDocument {
    private let handle: OpaquePointer
    private let lock = NSLock()
    public init(data: Data, fallbackFont: EXReaderFont? = nil) throws {
        var result: OpaquePointer?
        var error = exr_error()
        var options = exr_fixed_open_options()
        options.struct_size = MemoryLayout<exr_fixed_open_options>.size
        options.fallback_font = fallbackFont?.handle
        let status = data.withUnsafeBytes { bytes in
            exr_fixed_open_memory(EXR_PDF, bytes.baseAddress, bytes.count, &options, &result, &error)
        }
        try check(status, error)
        guard let result else { throw EXReaderError.invalidResult }
        handle = result
    }
    deinit { exr_fixed_free(handle) }
    public var pageCount: Int {
        var count = 0
        _ = exr_fixed_pages(handle, &count)
        return count
    }
    public func metadata() throws -> [EXReaderMetadataEntry] {
        lock.lock(); defer { lock.unlock() }
        var entries: UnsafeMutablePointer<exr_metadata_entry>?
        var count = 0
        var error = exr_error()
        let status = exr_fixed_load_metadata(handle, nil, &entries, &count, &error)
        defer { exr_metadata_free(entries, count) }
        try check(status, error)
        return try metadataValues(entries, count)
    }
    public func text(page: Int) throws -> EXReaderPageText {
        guard page >= 0 else { throw EXReaderError.invalidInput }
        lock.lock(); defer { lock.unlock() }
        var result: OpaquePointer?
        var error = exr_error()
        try check(exr_fixed_load_text(handle, page, nil, &result, &error), error)
        guard let result else { throw EXReaderError.invalidResult }
        return EXReaderPageText(handle: result)
    }
    public func render(page: Int, scale: Double = 1) throws -> EXReaderBitmap {
        guard page >= 0 else { throw EXReaderError.invalidInput }
        lock.lock(); defer { lock.unlock() }
        var bitmap = exr_bitmap()
        var error = exr_error()
        let status = exr_fixed_render(handle, page, scale, nil, &bitmap, &error)
        defer { exr_bitmap_free(&bitmap) }
        try check(status, error)
        guard let pixels = bitmap.pixels else { throw EXReaderError.invalidResult }
        return EXReaderBitmap(width: Int(bitmap.width), height: Int(bitmap.height),
                              stride: Int(bitmap.stride), channels: Int(bitmap.channels),
                              pixels: Data(bytes: pixels, count: Int(bitmap.stride) * Int(bitmap.height)))
    }
}

public struct EXReaderWaveFormat {
    public let sampleRate: UInt32
    public let channels: UInt32
    public let frames: UInt64
}
public final class EXReaderWave {
    private let handle: OpaquePointer
    private let lock = NSLock()
    public let format: EXReaderWaveFormat
    public init(file: URL) throws {
        guard file.isFileURL, !file.path.utf8.contains(0) else { throw EXReaderError.invalidInput }
        var result: OpaquePointer?
        var error = exr_error()
        let status = file.path.withCString { exr_wave_open($0, nil, &result, &error) }
        try check(status, error)
        guard let result, let info = exr_wave_format(result) else { throw EXReaderError.invalidResult }
        handle = result
        format = EXReaderWaveFormat(sampleRate: info.pointee.sample_rate,
                                   channels: info.pointee.channels, frames: info.pointee.frames)
    }
    deinit { exr_wave_free(handle) }
    public func read(firstFrame: UInt64, count: Int) throws -> [Float] {
        guard count >= 0, count <= 65536 else { throw EXReaderError.invalidInput }
        lock.lock(); defer { lock.unlock() }
        var samples = [Float](repeating: 0, count: count * Int(format.channels))
        var read = 0
        var error = exr_error()
        let status = samples.withUnsafeMutableBufferPointer {
            exr_wave_read(handle, firstFrame, count, $0.baseAddress, &read, nil, &error)
        }
        try check(status, error)
        samples.removeSubrange((read * Int(format.channels))..<samples.count)
        return samples
    }
}

public struct EXReaderPCMFormat {
    public let sampleRate: UInt32
    public let channels: UInt32
    public let channelMask: UInt32
    public let frames: UInt64? // nil until an unspecified duration is discovered.
}
/** WAV, FLAC and enabled compressed codecs through the open PCM interface. */
public final class EXReaderPCM {
    private let handle: OpaquePointer
    private let lock = NSLock()
    public init(file: URL) throws {
        guard file.isFileURL, !file.path.utf8.contains(0) else { throw EXReaderError.invalidInput }
        var result: OpaquePointer?
        var error = exr_error()
        let status = file.path.withCString { exr_pcm_open($0, nil, &result, &error) }
        try check(status, error)
        guard let result else { throw EXReaderError.invalidResult }
        handle = result
    }
    deinit { exr_pcm_free(handle) }
    public var format: EXReaderPCMFormat {
        lock.lock(); defer { lock.unlock() }
        let info = exr_pcm_format(handle)!.pointee
        return EXReaderPCMFormat(sampleRate: info.sample_rate, channels: info.channels,
                                 channelMask: info.channel_mask,
                                 frames: info.frames == UInt64.max ? nil : info.frames)
    }
    public func read(firstFrame: UInt64, count: Int) throws -> [Float] {
        guard count >= 0, count <= 65536 else { throw EXReaderError.invalidInput }
        lock.lock(); defer { lock.unlock() }
        let channels = Int(exr_pcm_format(handle)!.pointee.channels)
        var samples = [Float](repeating: 0, count: count * channels)
        var read = 0
        var error = exr_error()
        let status = samples.withUnsafeMutableBufferPointer {
            exr_pcm_read(handle, firstFrame, count, $0.baseAddress, &read, nil, &error)
        }
        try check(status, error)
        samples.removeSubrange((read * channels)..<samples.count)
        return samples
    }
}
