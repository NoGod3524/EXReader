// SPDX-License-Identifier: MIT
import Foundation
import Combine
import CEXReader
import CReaderProduct

struct HostNavigationRow: Identifiable {
    let index: UInt64
    let parent: UInt64
    let children: UInt32
    let label: String
    let href: String
    var id: UInt64 { index }
}

struct HostNavigationPage {
    let rows: [HostNavigationRow]
    let parent: UInt64
    let first: UInt64
    let next: UInt64
    let total: UInt64
    let pages: Bool
}

struct HostNavigationTarget {
    let kind: UInt32
    let row: UInt64
    let part: UInt64
    let path: String
    let partID: String
    let fragment: String
    let node: UInt64
    let cfi: String
    let cfiNode: UInt64
    let cfiOffset: UInt64
    let cfiSide: UInt32
    init(_ raw: reader_navigation_target) {
        kind = raw.kind; row = raw.row; part = raw.part
        path = hostString(raw.part_path); partID = hostString(raw.part_id)
        fragment = hostString(raw.fragment); node = raw.node
        cfi = hostString(raw.cfi); cfiNode = raw.cfi_node; cfiOffset = raw.cfi_offset; cfiSide = raw.cfi_side
    }
}

struct HostNavigationResolution {
    let status: reader_navigation_status
    let target: HostNavigationTarget
    let candidates: [UInt64]
}

struct HostNavigationSelection {
    let bookID: Int64
    let sourceKey: String
    let row: UInt64
    let cfi: String
    let resolution: HostNavigationResolution
}

private func hostNavigationCheck(_ status: reader_navigation_status, _ error: reader_navigation_error) throws {
    if status == READER_NAVIGATION_OK { return }
    if status == READER_NAVIGATION_CANCELLED { throw HostError.cancelled }
    var copy = error
    let message = withUnsafePointer(to: &copy.message) {
        $0.withMemoryRebound(to: CChar.self, capacity: 160) { String(cString: $0) }
    }
    throw HostError.invalidResult(message.isEmpty ? "目录目标不可用，保留当前页面" : message)
}

// Dispatch queues can change OS threads. Each invocation opens, uses and closes
// its F2 snapshot on one thread; only owned values cross invocations.
enum HostNavigationWorker {
#if EXR_APPLE_HOST_REVIEW
    static var reviewInsideSnapshot = false
#endif
    private static func withSnapshot<T>(library: HostLibrary, font: HostFont, bookID: Int64,
        key: String, cancel: HostCancelBox,
        _ body: (OpaquePointer, HostPublication?, HostDocument?, HostFixed?) throws -> T) throws -> T {
        try cancel.check()
        guard let book = try library.books().first(where: { $0.id == bookID }),
              try library.sourceFingerprint(book: book, cancel: cancel).searchKey == key else {
            throw HostError.invalidInput("原件身份已变化，请重新打开目录")
        }
        var publication: HostPublication?, document: HostDocument?, fixed: HostFixed?
        if book.isFixed { fixed = try library.fixed(bookID: bookID, font: font, cancel: cancel) }
        else if try library.isBoundedEPUB(book: book) { publication = try HostPublication(library: library, bookID: bookID, cancel: cancel) }
        else { document = try library.document(bookID: bookID, cancel: cancel) }
        return try withExtendedLifetime((publication, document, fixed)) {
            try key.withCString { keyPointer in
                var options = reader_navigation_options(), snapshot: OpaquePointer?, error = reader_navigation_error()
                options.struct_size = MemoryLayout<reader_navigation_options>.size
                options.control = hostControl(cancel); options.source_key = keyPointer
#if EXR_APPLE_HOST_REVIEW
                reviewInsideSnapshot = true
                defer { reviewInsideSnapshot = false }
#endif
                let status: reader_navigation_status
                if let publication { status = reader_navigation_open_publication(publication.handle, &options, &snapshot, &error) }
                else if let fixed { status = reader_navigation_open_pages(fixed.handle, &options, &snapshot, &error) }
                else { status = reader_navigation_open_document(document!.handle, &options, &snapshot, &error) }
                try hostNavigationCheck(status, error)
                guard let handle = snapshot else { throw HostError.invalidResult("目录快照缺失") }
                defer { _ = reader_navigation_close(&snapshot, nil) }
                return try body(handle, publication, document, fixed)
            }
        }
    }

    static func page(library: HostLibrary, font: HostFont, bookID: Int64, key: String,
                     parent: UInt64, first: UInt64, cancel: HostCancelBox) throws -> HostNavigationPage {
        try withSnapshot(library: library, font: font, bookID: bookID, key: key, cancel: cancel) { snapshot, _, _, _ in
            var info = reader_navigation_info(), page = reader_navigation_page(), error = reader_navigation_error()
            try hostNavigationCheck(reader_navigation_info_get(snapshot, &info, &error), error)
            try hostNavigationCheck(reader_navigation_children(snapshot, parent, first, 32, &page, &error), error)
            defer { reader_navigation_page_free(&page) }
            try cancel.check()
            guard page.count <= 32, page.count == 0 || page.rows != nil,
                  info.kind != READER_NAVIGATION_PAGES || info.author_outline == 0 else {
                throw HostError.invalidResult("目录页无效")
            }
            let rows = (0..<page.count).map { index -> HostNavigationRow in
                let raw = page.rows![index]
                return HostNavigationRow(index: raw.index, parent: raw.parent, children: raw.child_count,
                                         label: hostString(raw.label), href: hostString(raw.href))
            }
            return HostNavigationPage(rows: rows, parent: parent, first: first, next: page.next,
                                      total: page.total, pages: info.kind == READER_NAVIGATION_PAGES)
        }
    }

    static func resolve(library: HostLibrary, font: HostFont, bookID: Int64, key: String,
                        row: UInt64, explicitPart: UInt64 = UInt64.max, cfi: String = "",
                        cancel: HostCancelBox) throws -> HostNavigationSelection {
        try withSnapshot(library: library, font: font, bookID: bookID, key: key, cancel: cancel) { snapshot, publication, document, fixed in
            try key.withCString { keyPointer in
                var options = reader_navigation_resolve_options(), target = reader_navigation_target(), error = reader_navigation_error()
                options.struct_size = MemoryLayout<reader_navigation_resolve_options>.size
                options.control = hostControl(cancel); options.source_key = keyPointer; options.explicit_part = explicitPart
                var inputCFI = cfi, checkLocalPart = false
                if inputCFI.isEmpty {
                    var page = reader_navigation_page()
                    try hostNavigationCheck(reader_navigation_rows(snapshot, row, 1, &page, &error), error)
                    defer { reader_navigation_page_free(&page) }
                    guard page.count == 1, let rows = page.rows, rows[0].index == row else { throw HostError.invalidInput("目录项已变化") }
                    let href = hostString(rows[0].href)
                    if href.hasPrefix("epubcfi(") { inputCFI = href }
                    else if let hash = href.firstIndex(of: "#") {
                        let fragment = String(href[href.index(after: hash)...])
                        if fragment.hasPrefix("epubcfi(") {
                            inputCFI = fragment; checkLocalPart = hash != href.startIndex
                        }
                    }
                }
                var localPart: HostNavigationTarget?
                if checkLocalPart {
                    guard let publication else { throw HostError.invalidInput("本书的目录位置无法精确解析") }
                    var local = reader_navigation_target()
                    let status = reader_navigation_resolve_publication(snapshot, row, publication.handle, &options, &local, &error)
                    defer { reader_navigation_target_free(&local) }
                    if status == READER_NAVIGATION_AMBIGUOUS {
                        let candidates = local.candidates.map { Array(UnsafeBufferPointer(start: $0, count: local.candidate_count)) } ?? []
                        return HostNavigationSelection(bookID: bookID, sourceKey: key, row: row, cfi: "",
                            resolution: HostNavigationResolution(status: status, target: HostNavigationTarget(local), candidates: candidates))
                    }
                    if status != READER_NAVIGATION_PART_ONLY { try hostNavigationCheck(status, error) }
                    localPart = HostNavigationTarget(local)
                }
                let status: reader_navigation_status
                if !inputCFI.isEmpty {
                    guard let publication else { throw HostError.invalidInput("本书不提供 EPUB CFI") }
                    status = inputCFI.withCString { reader_navigation_resolve_cfi(snapshot, publication.handle, $0, &options, &target, &error) }
                } else if let publication { status = reader_navigation_resolve_publication(snapshot, row, publication.handle, &options, &target, &error) }
                else if let fixed { status = reader_navigation_resolve_page(snapshot, row, fixed.handle, &options, &target, &error) }
                else { status = reader_navigation_resolve_document(snapshot, row, document!.handle, &options, &target, &error) }
                defer { reader_navigation_target_free(&target) }
                if status != READER_NAVIGATION_PART_ONLY && status != READER_NAVIGATION_AMBIGUOUS {
                    try hostNavigationCheck(status, error)
                }
                if let localPart {
                    guard target.part == localPart.part, hostString(target.part_path) == localPart.path,
                          hostString(target.part_id) == localPart.partID else { throw HostError.invalidInput("目录链接与原生位置不一致") }
                }
                try cancel.check()
                let candidates = target.candidates.map { Array(UnsafeBufferPointer(start: $0, count: target.candidate_count)) } ?? []
                return HostNavigationSelection(bookID: bookID, sourceKey: key, row: row, cfi: inputCFI,
                    resolution: HostNavigationResolution(status: status, target: HostNavigationTarget(target), candidates: candidates))
            }
        }
    }

    // Raw TEXT must equal its entire normalized projection. UTF-16 scalar
    // boundaries are counted explicitly; folding and surrogate interiors refuse.
    static func cfiProjection(document: HostDocument, node index: UInt64, units: UInt64) throws -> Int {
        var count = 0
        guard let nodes = exr_document_nodes(document.handle, &count), index < UInt64(count) else { throw HostError.invalidInput("CFI 节点不存在") }
        let node = nodes[Int(index)]
        guard node.start >= 0, node.start <= node.end, node.end <= document.text.count else { throw HostError.invalidInput("CFI 节点未投影") }
        if node.kind != EXR_NODE_TEXT {
            if units == UInt64.max { return node.start }
            guard units <= UInt64(count) else { throw HostError.invalidInput("CFI 子节点越界") }
            var child = node.first_child
            for _ in 0..<units {
                guard child >= 0, child < count else { throw HostError.invalidInput("CFI 子节点越界") }
                child = nodes[child].next_sibling
            }
            if child == -1 { return node.end }
            guard child >= 0, child < count, nodes[child].start >= 0, nodes[child].start <= document.text.count else { throw HostError.invalidInput("CFI 子节点未投影") }
            return nodes[child].start
        }
        guard let rawPointer = node.text, units != UInt64.max else { throw HostError.invalidInput("CFI 文字偏移无效") }
        let raw = Data(String(cString: rawPointer).utf8)
        guard raw == document.text[node.start..<node.end], let text = String(data: raw, encoding: .utf8) else {
            throw HostError.invalidInput("CFI 文字折叠无法唯一映射")
        }
        var seen: UInt64 = 0, bytes = 0
        for scalar in text.unicodeScalars {
            if seen == units { return node.start + bytes }
            let width: UInt64 = scalar.value > 0xffff ? 2 : 1
            guard seen + width <= units else { throw HostError.invalidInput("CFI 位于代理项中间") }
            seen += width; bytes += String(scalar).utf8.count
        }
        guard seen == units else { throw HostError.invalidInput("CFI 文字偏移越界") }
        return node.start + bytes
    }

    // A second independently opened SDK input calls the SDK directly. F2 is
    // deliberately absent here: repeating its resolution would prove nothing.
    static func verify(_ selection: HostNavigationSelection, publication: HostPublication?,
                       document: HostDocument?, cancel: HostCancelBox) throws -> (HostDocument, Int) {
        let target = selection.resolution.target
        guard target.part <= UInt64(Int.max) else { throw HostError.invalidInput("目录章节越界") }
        let part = Int(target.part)
        var loaded: HostDocument, chapter = part
        if let publication {
            _ = try publication.route(part, path: target.path)
            var count = 0
            guard let parts = exr_publication_parts(publication.handle, &count), part < count,
                  hostString(parts[part].id) == target.partID else { throw HostError.invalidInput("章节身份不匹配") }
            var handle: OpaquePointer?, error = exr_error()
            if !selection.cfi.isEmpty {
                guard target.kind == READER_NAVIGATION_RESULT_CFI.rawValue && target.cfi == selection.cfi else {
                    throw HostError.invalidInput("CFI 目标不匹配")
                }
                var resolvedPart = -1, point = exr_cfi_point(), control = hostControl(cancel)
                let status = selection.cfi.withCString {
                    exr_publication_cfi_resolve(publication.handle, $0, &control, &resolvedPart, &handle, &point, &error)
                }
                try hostCheck(status, error)
                guard let handle else { throw HostError.invalidResult("CFI 独立文档缺失") }
                loaded = HostDocument(adopting: handle)
                guard resolvedPart == part, point.node >= 0, UInt64(point.node) == target.cfiNode,
                      (point.offset == -1 ? UInt64.max : UInt64(point.offset)) == target.cfiOffset,
                      point.side == target.cfiSide else { throw HostError.invalidInput("CFI 独立解析不一致") }
                try cancel.check()
                return (loaded, try cfiProjection(document: loaded, node: target.cfiNode, units: target.cfiOffset))
            }
            guard target.kind == READER_NAVIGATION_RESULT_SPINE.rawValue, target.row == selection.row else { throw HostError.invalidInput("章节目标类型不匹配") }
            try hostCheck(exr_publication_load(publication.handle, part, &handle, &error), error)
            guard let handle else { throw HostError.invalidResult("独立章节文档缺失") }
            loaded = HostDocument(adopting: handle); chapter = 0
        } else {
            guard let document, target.kind == READER_NAVIGATION_RESULT_CHAPTER.rawValue,
                  target.row == selection.row else { throw HostError.invalidInput("目录目标类型不匹配") }
            loaded = document
        }
        try cancel.check()
        var chapterCount = 0
        guard let chapters = exr_document_chapters(loaded.handle, &chapterCount), chapter >= 0, chapter < chapterCount,
              publication != nil || (hostString(chapters[chapter].path) == target.path && hostString(chapters[chapter].id) == target.partID) else {
            throw HostError.invalidInput("独立章节目录不匹配")
        }
        var nodeCount = 0
        guard let nodes = exr_document_nodes(loaded.handle, &nodeCount) else { throw HostError.invalidInput("章节节点缺失") }
        var node = -1
        if !target.fragment.isEmpty {
            var resource = -1, error = exr_error()
            try ("#" + target.fragment).withCString { uri in
                try hostCheck(exr_document_resolve(loaded.handle, chapter, uri, &resource, &node, &error), error)
            }
            guard (node == -1 ? UInt64.max : UInt64(node)) == target.node,
                  (selection.resolution.status == READER_NAVIGATION_PART_ONLY) == (node == -1) else {
                throw HostError.invalidInput("独立片段解析不一致")
            }
        } else if target.node != UInt64.max { throw HostError.invalidInput("目录节点不一致") }
        let chosen = node == -1 ? chapters[chapter].root : node
        guard chosen >= 0, chosen < nodeCount else { throw HostError.invalidInput("目录节点未投影") }
        let offset = nodes[chosen].start
        guard offset >= 0, offset <= loaded.text.count,
              offset == loaded.text.count || (loaded.text[offset] & 0xc0) != 0x80 else { throw HostError.invalidInput("目录目标不是文字边界") }
        return (loaded, offset)
    }
}

final class HostNavigationState: ObservableObject {
    @Published private(set) var page: HostNavigationPage?
    @Published private(set) var running = false
    @Published private(set) var status = "正在读取目录…"
    @Published private(set) var pending: HostNavigationSelection?
    @Published private(set) var committed = 0
    private(set) var bookID: Int64?
    private(set) var key: String?
    private(set) var generation = 0
    private(set) var parents: [(UInt64, UInt64)] = []
    private var cancelBox: HostCancelBox?
    func bind(_ bookID: Int64) {
        invalidate(); self.bookID = bookID; status = "正在读取目录…"
    }
    func begin(box: HostCancelBox = HostCancelBox()) -> (Int, HostCancelBox) {
        cancel(); cancelBox = box; running = true
        pending = nil; status = "正在读取目录…"; return (generation, box)
    }
    func accept(_ page: HostNavigationPage, key: String, generation expected: Int) {
        guard generation == expected else { return }
        self.page = page; self.key = key; running = false; cancelBox = nil
        status = page.pages ? "按页入口 · 非作者目录" : page.total == 0 ? "本书没有作者目录" : "本页 \(page.rows.count) 项 · 共 \(page.total) 项"
    }
    func propose(_ selection: HostNavigationSelection, generation expected: Int) {
        guard generation == expected else { return }
        pending = selection; running = false; cancelBox = nil
        status = selection.resolution.status == READER_NAVIGATION_AMBIGUOUS ? "章节路径重复，请选择具体位置" : "片段不存在，是否打开本章开头？"
    }
    func didCommit(generation expected: Int) {
        guard generation == expected else { return }
        running = false; cancelBox = nil; pending = nil; committed += 1; status = "已精确定位目录目标"
    }
    func fail(_ error: Error, generation expected: Int) {
        guard generation == expected else { return }
        running = false; cancelBox = nil; pending = nil; status = error.localizedDescription
    }
    func cancel() {
        cancelBox?.cancel(); cancelBox = nil; generation += 1; pending = nil
        if running { status = "已取消，保留当前页面" }
        running = false
    }
    func pushParent() { if let page { parents.append((page.parent, page.first)) } }
    func popParent() -> (UInt64, UInt64)? { parents.popLast() }
    func invalidate() { cancel(); bookID = nil; key = nil; page = nil; parents = [] }
#if EXR_APPLE_HOST_REVIEW
    func reviewCancellationReady(generation expected: Int) {
        if generation == expected && running { status = "正在读取目录（可取消）" }
    }
#endif
}
