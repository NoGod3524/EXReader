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
public struct EXReaderAudioChapter {
    public let id, title: String
    public let parent: Int?
    public let startMilliseconds: UInt64
    public let endMilliseconds: UInt64?
}
public struct EXReaderAudioBookMetadata {
    public let entries: [EXReaderMetadataEntry]
    public let chapters: [EXReaderAudioChapter]
    public let durationMilliseconds: UInt64?
    public let cover: Data?
    public let coverMediaType: String?
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
    public static func readM4B(file: URL) throws -> EXReaderAudioBookMetadata {
        guard file.isFileURL, !file.path.utf8.contains(0) else { throw EXReaderError.invalidInput }
        var result: OpaquePointer?
        var error = exr_error()
        let status = file.path.withCString { exr_m4b_inspect($0, nil, &result, &error) }
        try check(status, error)
        guard let result else { throw EXReaderError.invalidResult }
        defer { exr_m4b_inspection_free(result) }
        var count = 0, chapterCount = 0, coverSize = 0
        let values = exr_m4b_inspection_metadata(result, &count)
        let nativeChapters = exr_m4b_inspection_chapters(result, &chapterCount)
        let entries = (0..<count).map {
            EXReaderMetadataEntry(key: String(cString: values![$0].key), value: String(cString: values![$0].value))
        }
        let chapters = (0..<chapterCount).map { index -> EXReaderAudioChapter in
            let c = nativeChapters![index]
            return EXReaderAudioChapter(id: String(cString: c.id), title: String(cString: c.title),
                                        parent: c.parent == -1 ? nil : c.parent, startMilliseconds: c.start_ms,
                                        endMilliseconds: c.end_ms == UInt64.max ? nil : c.end_ms)
        }
        var mediaType: UnsafePointer<CChar>?
        let cover = exr_m4b_inspection_cover(result, &coverSize, &mediaType)
        let duration = exr_m4b_inspection_duration(result)
        return EXReaderAudioBookMetadata(entries: entries, chapters: chapters,
                                         durationMilliseconds: duration == UInt64.max ? nil : duration,
                                         cover: cover.map { Data(bytes: $0, count: coverSize) },
                                         coverMediaType: mediaType.map { String(cString: $0) })
    }
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
    fileprivate let gate = NSLock()
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
public struct EXReaderFontSource {
    public let data: Data
    public let faceIndex: UInt32
    public let axes: [exr_font_axis]
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

public enum EXReaderFixedFormat { case pdf, cbz }

public final class EXReaderFixedDocument {
    private let handle: OpaquePointer
    private let lock = NSLock()
    private let fallbackFont: EXReaderFont?
    public struct PdfSecurity {
        public let encrypted,ownerAuthenticated,metadataEncrypted: Bool
        public let revision,keyBits,permissions: UInt32
    }
    public let pdfSecurity: PdfSecurity?
    /// Password bytes: PDFDocEncoding for R2-4; UTF-8 for R5-6. Used only while opening.
    public init(data: Data, fallbackFont: EXReaderFont? = nil, format: EXReaderFixedFormat = .pdf, password: Data? = nil) throws {
        var result: OpaquePointer?
        var error = exr_error()
        var options = exr_fixed_open_options()
        options.struct_size = MemoryLayout<exr_fixed_open_options>.size
        options.fallback_font = fallbackFont?.handle
        var security = exr_pdf_security_info()
        security.struct_size = MemoryLayout<exr_pdf_security_info>.size
        fallbackFont?.gate.lock(); defer { fallbackFont?.gate.unlock() }
        let status = (password ?? Data()).withUnsafeBytes { secret in
            options.pdf_password = secret.baseAddress
            options.pdf_password_size = secret.count
            return withUnsafeMutablePointer(to: &security) { info in
                options.pdf_security = format == .pdf ? info : nil
                return data.withUnsafeBytes { bytes in
                    exr_fixed_open_memory(format == .pdf ? EXR_PDF : EXR_CBZ, bytes.baseAddress, bytes.count, &options, &result, &error)
                }
            }
        }
        try check(status, error)
        guard let result else { throw EXReaderError.invalidResult }
        handle = result
        self.fallbackFont = fallbackFont
        pdfSecurity = format == .pdf ? PdfSecurity(encrypted: security.encrypted != 0, ownerAuthenticated: security.owner_authenticated != 0,
            metadataEncrypted: security.metadata_encrypted != 0, revision: security.revision, keyBits: security.key_bits, permissions: security.permissions) : nil
    }
    deinit {
        fallbackFont?.gate.lock(); defer { fallbackFont?.gate.unlock() }
        exr_fixed_free(handle)
    }
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
        fallbackFont?.gate.lock(); defer { fallbackFont?.gate.unlock() }
        var result: OpaquePointer?
        var error = exr_error()
        try check(exr_fixed_load_text(handle, page, nil, &result, &error), error)
        guard let result else { throw EXReaderError.invalidResult }
        return EXReaderPageText(handle: result)
    }
    public func render(page: Int, scale: Double = 1) throws -> EXReaderBitmap {
        guard page >= 0 else { throw EXReaderError.invalidInput }
        lock.lock(); defer { lock.unlock() }
        fallbackFont?.gate.lock(); defer { fallbackFont?.gate.unlock() }
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

/** Independent UTF-8 snapshots. Absent node indices import as -1 (C SIZE_MAX). */
public struct EXReaderNode {
    public let kind: exr_node_kind
    public let parent, firstChild, nextSibling, chapter: Int
    public let start, end: Int
    public let name, text: String?
    public let attributes: [EXReaderMetadataEntry]
}
public struct EXReaderPart {
    public let id, path, title: String?
    public let inReadingOrder: Bool
}
public struct EXReaderLayoutConfig {
    public var page = exr_layout_defaults()
    public var userCSS: String? = nil
    public var documentCSS = true
    public var embeddedFonts = true
    public var direction = EXR_DIRECTION_AUTO
    public init() {}
}
private func optionalString(_ value: UnsafePointer<CChar>?) -> String? {
    value.map { String(cString: $0) }
}
public final class EXReaderDocument {
    fileprivate let handle: OpaquePointer
    fileprivate let gate: NSLock
    fileprivate init(handle: OpaquePointer, gate: NSLock) { self.handle = handle; self.gate = gate }
    public convenience init(data: Data, format: exr_format) throws {
        var result: OpaquePointer?
        var error = exr_error()
        let status = data.withUnsafeBytes {
            exr_document_open_memory(format, $0.baseAddress, $0.count, &result, &error)
        }
        try check(status, error)
        guard let result else { throw EXReaderError.invalidResult }
        self.init(handle: result, gate: NSLock())
    }
    public convenience init(file: URL) throws {
        guard file.isFileURL, !file.path.utf8.contains(0) else { throw EXReaderError.invalidInput }
        var result: OpaquePointer?
        var error = exr_error()
        let status = file.path.withCString { exr_document_open($0, &result, &error) }
        try check(status, error)
        guard let result else { throw EXReaderError.invalidResult }
        self.init(handle: result, gate: NSLock())
    }
    deinit { gate.lock(); defer { gate.unlock() }; exr_document_free(handle) }
    public var title: String? {
        gate.lock(); defer { gate.unlock() }
        return optionalString(exr_document_title(handle))
    }
    public var utf8: Data {
        gate.lock(); defer { gate.unlock() }
        var size = 0
        guard let text = exr_document_text(handle, &size) else { return Data() }
        return Data(bytes: text, count: size)
    }
    public var nodes: [EXReaderNode] {
        gate.lock(); defer { gate.unlock() }
        var count = 0
        guard let nodes = exr_document_nodes(handle, &count) else { return [] }
        return (0..<count).map { index in
            let n = nodes[index]
            let attributes: [EXReaderMetadataEntry] = (0..<n.attribute_count).map {
                EXReaderMetadataEntry(key: String(cString: n.attributes![$0].name), value: String(cString: n.attributes![$0].value))
            }
            return EXReaderNode(kind: n.kind, parent: n.parent, firstChild: n.first_child,
                                nextSibling: n.next_sibling, chapter: n.chapter, start: n.start, end: n.end,
                                name: optionalString(n.name), text: optionalString(n.text), attributes: attributes)
        }
    }
    public func pager(font: EXReaderFont, config: EXReaderLayoutConfig = EXReaderLayoutConfig()) throws -> EXReaderPager {
        try EXReaderPager(document: self, font: font, config: config)
    }
}
/** EPUB manifest/spine first; load() decodes only the requested part. */
public final class EXReaderPublication {
    private let handle: OpaquePointer
    private let gate = NSLock()
    public init(file: URL) throws {
        guard file.isFileURL, !file.path.utf8.contains(0) else { throw EXReaderError.invalidInput }
        var result: OpaquePointer?
        var error = exr_error()
        let status = file.path.withCString { exr_publication_open($0, &result, &error) }
        try check(status, error)
        guard let result else { throw EXReaderError.invalidResult }
        handle = result
    }
    public init(data: Data, format: exr_format = EXR_EPUB) throws {
        var result: OpaquePointer?
        var error = exr_error()
        let status = data.withUnsafeBytes {
            exr_publication_open_memory(format, $0.baseAddress, $0.count, &result, &error)
        }
        try check(status, error)
        guard let result else { throw EXReaderError.invalidResult }
        handle = result
    }
    deinit { gate.lock(); defer { gate.unlock() }; exr_publication_free(handle) }
    public var title: String? {
        gate.lock(); defer { gate.unlock() }
        return optionalString(exr_publication_title(handle))
    }
    public var parts: [EXReaderPart] {
        gate.lock(); defer { gate.unlock() }
        var count = 0
        guard let parts = exr_publication_parts(handle, &count) else { return [] }
        return (0..<count).map {
            EXReaderPart(id: optionalString(parts[$0].id), path: optionalString(parts[$0].path),
                         title: optionalString(parts[$0].title), inReadingOrder: parts[$0].in_reading_order != 0)
        }
    }
    public func load(part: Int) throws -> EXReaderDocument {
        guard part >= 0 else { throw EXReaderError.invalidInput }
        gate.lock(); defer { gate.unlock() }
        var result: OpaquePointer?
        var error = exr_error()
        let status = exr_publication_load(handle, part, &result, &error)
        try check(status, error)
        guard let result else { throw EXReaderError.invalidResult }
        return EXReaderDocument(handle: result, gate: gate)
    }
}
/// Host-owned UTF-8 patterns; dictionary data and its license are supplied separately.
public struct EXReaderHyphenDictionary {
    public var language: String
    public var patterns: Data
    public var leftMinimum, rightMinimum: UInt32
    public init(language: String, patterns: Data, leftMinimum: UInt32 = 2, rightMinimum: UInt32 = 2) {
        self.language = language; self.patterns = patterns
        self.leftMinimum = leftMinimum; self.rightMinimum = rightMinimum
    }
}
public final class EXReaderPager {
    private var handle: OpaquePointer?
    fileprivate let document: EXReaderDocument
    fileprivate let font: EXReaderFont
    fileprivate init(document: EXReaderDocument, font: EXReaderFont, config: EXReaderLayoutConfig) throws {
        guard !(config.userCSS?.utf8.contains(0) ?? false) else { throw EXReaderError.invalidInput }
        self.document = document; self.font = font
        document.gate.lock(); defer { document.gate.unlock() }
        font.gate.lock(); defer { font.gate.unlock() }
        var native = exr_layout_config_defaults()
        native.page = config.page; native.document_css = config.documentCSS ? 1 : 0
        native.embedded_fonts = config.embeddedFonts ? 1 : 0; native.direction = config.direction
        var result: OpaquePointer?
        var error = exr_error()
        let status: exr_status
        if let css = config.userCSS {
            status = css.withCString {
                native.user_css = $0
                return exr_pager_create(document.handle, font.handle, &native, &result, &error)
            }
        } else {
            status = exr_pager_create(document.handle, font.handle, &native, &result, &error)
        }
        try check(status, error)
        guard let result else { throw EXReaderError.invalidResult }
        handle = result
    }
    deinit {
        document.gate.lock(); defer { document.gate.unlock() }
        font.gate.lock(); defer { font.gate.unlock() }
        exr_pager_free(handle)
    }
    /// Before next(); empty dictionaries disable hyphenation. CSS hyphens:auto is required.
    /// Each pager owns independent compiled data. byteBudget=0 uses 32 MiB (maximum 128 MiB).
    public func setHyphenation(_ dictionaries: [EXReaderHyphenDictionary], byteBudget: Int = 0) throws {
        guard dictionaries.count <= 64, byteBudget >= 0, byteBudget <= 128 * 1024 * 1024 else { throw EXReaderError.invalidInput }
        var total = 0
        for d in dictionaries {
            guard !d.language.utf8.contains(0), d.language.utf8.count <= 255,
                  d.leftMinimum <= 64, d.rightMinimum <= 64, d.patterns.count <= 8 * 1024 * 1024 else { throw EXReaderError.invalidInput }
            total += d.patterns.count
        }
        guard total <= 32 * 1024 * 1024 else { throw EXReaderError.invalidInput }
        let languages = dictionaries.map { Data($0.language.utf8CString.map { UInt8(bitPattern: $0) }) as NSData }
        let patterns = dictionaries.map { $0.patterns as NSData }
        var inputs = dictionaries.indices.map { i -> exr_hyphen_pattern_input in
            var value = exr_hyphen_pattern_input()
            value.struct_size = MemoryLayout<exr_hyphen_pattern_input>.size
            value.language = languages[i].bytes.assumingMemoryBound(to: CChar.self)
            value.patterns = patterns[i].bytes; value.size = patterns[i].length
            value.left_min = dictionaries[i].leftMinimum; value.right_min = dictionaries[i].rightMinimum
            return value
        }
        document.gate.lock(); defer { document.gate.unlock() }
        font.gate.lock(); defer { font.gate.unlock() }
        guard let handle else { throw EXReaderError.invalidInput }
        var result: OpaquePointer?
        defer { exr_hyphenator_free(result) }
        var error = exr_error()
        let status: exr_status = withExtendedLifetime((languages, patterns)) {
            inputs.withUnsafeMutableBufferPointer {
                $0.isEmpty ? EXR_OK : exr_hyphenator_create_patterns($0.baseAddress, $0.count, byteBudget, nil, &result, &error)
            }
        }
        try check(status, error)
        try check(exr_pager_set_hyphenator(handle, result, &error), error)
    }
    /** nil at EOF. An engine error invalidates this pager; construct another to retry. */
    public func next() throws -> EXReaderReflowPage? {
        document.gate.lock(); defer { document.gate.unlock() }
        font.gate.lock(); defer { font.gate.unlock() }
        guard let handle else { throw EXReaderError.invalidInput }
        var result: OpaquePointer?
        var error = exr_error()
        let status = exr_pager_next(handle, &result, &error)
        if status != EXR_OK { exr_pager_free(handle); self.handle = nil; try check(status, error) }
        return result.map { EXReaderReflowPage(handle: $0, document: document, font: font) }
    }
}
/** One owned page, independent of the pager. Record arrays contain no borrowed pointers. */
public final class EXReaderReflowPage {
    private let handle: OpaquePointer
    private let document: EXReaderDocument
    private let font: EXReaderFont
    fileprivate init(handle: OpaquePointer, document: EXReaderDocument, font: EXReaderFont) {
        self.handle = handle; self.document = document; self.font = font
    }
    deinit {
        document.gate.lock(); defer { document.gate.unlock() }
        font.gate.lock(); defer { font.gate.unlock() }
        exr_layout_free(handle)
    }
    public var content: exr_page {
        document.gate.lock(); defer { document.gate.unlock() }
        return exr_layout_pages(handle, nil)!.pointee
    }
    public var writingMode: exr_writing_mode {
        document.gate.lock(); defer { document.gate.unlock() }
        return exr_layout_writing_mode(handle)
    }
    public var glyphs: [exr_glyph] {
        document.gate.lock(); defer { document.gate.unlock() }
        var count = 0
        guard let data = exr_layout_glyphs(handle, &count) else { return [] }
        return Array(UnsafeBufferPointer(start: data, count: count))
    }
    public var lines: [exr_line] {
        document.gate.lock(); defer { document.gate.unlock() }
        var count = 0
        guard let data = exr_layout_lines(handle, &count) else { return [] }
        return Array(UnsafeBufferPointer(start: data, count: count))
    }
    public var boxes: [exr_box] {
        document.gate.lock(); defer { document.gate.unlock() }
        var count = 0
        guard let data = exr_layout_boxes(handle, &count) else { return [] }
        return Array(UnsafeBufferPointer(start: data, count: count))
    }
    /** Effective font bytes and instance coordinates, including embedded book fonts. */
    public func fontSource(index: Int) throws -> EXReaderFontSource {
        guard index >= 0 else { throw EXReaderError.invalidInput }
        document.gate.lock(); defer { document.gate.unlock() }
        font.gate.lock(); defer { font.gate.unlock() }
        var input = exr_font_input()
        var axes: UnsafeMutablePointer<exr_font_axis>?
        var count = 0
        var error = exr_error()
        let effective = exr_layout_font(handle)
        var status = exr_font_source(effective, index, &input, &error)
        try check(status, error)
        status = exr_font_axes(effective, index, &axes, &count, &error)
        defer { exr_free(axes) }
        try check(status, error)
        guard let data = input.data else { throw EXReaderError.invalidResult }
        return EXReaderFontSource(data: Data(bytes: data, count: input.size), faceIndex: input.face_index,
                                  axes: axes.map { Array(UnsafeBufferPointer(start: $0, count: count)) } ?? [])
    }
    public func image(resource: Int) throws -> EXReaderBitmap? {
        guard resource >= 0 else { throw EXReaderError.invalidInput }
        document.gate.lock(); defer { document.gate.unlock() }
        guard let image = exr_layout_image(handle, resource), let pixels = image.pointee.pixels else { return nil }
        let b = image.pointee
        return EXReaderBitmap(width: Int(b.width), height: Int(b.height), stride: Int(b.stride), channels: Int(b.channels),
                              pixels: Data(bytes: pixels, count: Int(b.stride) * Int(b.height)))
    }
    /** UTF-8 byte offset in the part document; nil for an empty page. */
    public func hitTest(x: Float, y: Float) -> Int? {
        document.gate.lock(); defer { document.gate.unlock() }
        let offset = exr_layout_hit_test(handle, 0, x, y)
        return offset == -1 ? nil : offset
    }
    public func render() throws -> EXReaderBitmap {
        document.gate.lock(); defer { document.gate.unlock() }
        font.gate.lock(); defer { font.gate.unlock() }
        var bitmap = exr_bitmap()
        var error = exr_error()
        let status = exr_render_page_color(handle, exr_layout_font(handle), 0, &bitmap, &error)
        defer { exr_bitmap_free(&bitmap) }
        try check(status, error)
        guard let pixels = bitmap.pixels else { throw EXReaderError.invalidResult }
        return EXReaderBitmap(width: Int(bitmap.width), height: Int(bitmap.height),
                              stride: Int(bitmap.stride), channels: Int(bitmap.channels),
                              pixels: Data(bytes: pixels, count: Int(bitmap.stride) * Int(bitmap.height)))
    }
}
