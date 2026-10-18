// SPDX-License-Identifier: GPL-3.0-only
import Foundation
import CEXReader

@main struct SDKSmoke {
    static func main() throws {
        precondition(CommandLine.arguments.count == 2)
        let root = URL(fileURLWithPath: CommandLine.arguments[1])
        let audiobook = try EXReaderMetadata.readM4B(file: root.appendingPathComponent("audio/metadata.m4b"))
        precondition(audiobook.durationMilliseconds == 200 && audiobook.chapters.count == 2 && audiobook.chapters[0].parent == nil)
        precondition(audiobook.chapters[0].startMilliseconds == 0 && audiobook.chapters[1].startMilliseconds == 100 && audiobook.chapters[1].endMilliseconds == 200)
        precondition(audiobook.entries[0].value == "Book 中文😀" && audiobook.entries[1].value == "作者" && audiobook.cover?.isEmpty == false && audiobook.coverMediaType == "image/jpeg")
        let pdf = try Data(contentsOf: root.appendingPathComponent("fixed-pages/pdf-public.pdf"))
        let encrypted = try Data(contentsOf: root.appendingPathComponent("fixed-pages/encrypted-r6.pdf"))
        do { _ = try EXReaderFixedDocument(data: encrypted); preconditionFailure("password must be required") }
        catch EXReaderError.engine(let code, _) { precondition(code == 10) }
        let protectedPdf = try EXReaderFixedDocument(data: encrypted, password: Data("reader".utf8))
        precondition(protectedPdf.pageCount == 2 && protectedPdf.pdfSecurity?.encrypted == true && protectedPdf.pdfSecurity?.revision == 6 && protectedPdf.pdfSecurity?.keyBits == 256)
        precondition(protectedPdf.pdfSecurity?.ownerAuthenticated == false && protectedPdf.pdfSecurity?.permissions == 0xfffff0c4)
        let protectedText = try protectedPdf.text(page: 0)
        precondition(protectedText.string == "Secret text")
        do { _ = try protectedPdf.text(page: 1); preconditionFailure("invalid page must fail") }
        catch EXReaderError.engine(let code, _) { precondition(code == 5) }
        let retriedText = try protectedPdf.text(page: 0)
        precondition(retriedText.string == "Secret text")
        let comic = try EXReaderFixedDocument(data: Data(contentsOf: root.appendingPathComponent("fixed-pages/comic.cbz")), format: .cbz)
        precondition(comic.pageCount == 4)
        let comicMetadata = try comic.metadata()
        precondition(comicMetadata.first?.value == "SDK Comic")
        let comicText = try comic.text(page: 0)
        precondition(comicText.string.isEmpty)
        let comicPage = try comic.render(page: 0, scale: 1)
        precondition(comicPage.width == 2 && comicPage.height == 2)
        let document = try EXReaderFixedDocument(data: pdf)
        precondition(document.pageCount == 5)
        let emptyMetadata = try document.metadata()
        precondition(emptyMetadata.isEmpty)
        let text = try document.text(page: 0)
        precondition(text.string == "A" && text.regions.count == 1)
        let match = try text.find(Data("A".utf8))
        precondition(match == 0..<1)
        let miss = try text.find(Data("Z".utf8))
        precondition(miss == nil)
        let semanticDocument = try EXReaderFixedDocument(data: Data(contentsOf: root.appendingPathComponent("fixed-pages/pdf-public-text.pdf")))
        let semanticText = try semanticDocument.text(page: 0)
        precondition(semanticText.utf8.count == 14 && semanticText.string.utf8.count == 14 && semanticText.regions.count == 8)
        let nulMatch = try semanticText.find(Data([0]))
        precondition(nulMatch == 6..<7)
        do {
            _ = try text.find(Data())
            preconditionFailure("empty query should fail")
        } catch EXReaderError.engine(let code, _) {
            precondition(code == Int(EXR_ARGUMENT.rawValue))
        }
        let bitmap = try document.render(page: 0)
        precondition(bitmap.width == 12 && bitmap.height == 12 && bitmap.channels == 4 && bitmap.pixels.count == 576)
        do {
            _ = try document.render(page: 3)
            preconditionFailure("bad embedded font should fail")
        } catch EXReaderError.engine(let code, _) {
            precondition(code == Int(EXR_FORMAT.rawValue))
        }
        let retainedFontDocument: EXReaderFixedDocument
        let glyphOnlyFont = try EXReaderFont(data: Data(contentsOf: root.appendingPathComponent("fonts/glyph-only.ttf")))
        let glyphOnlyDocument = try EXReaderFixedDocument(data: pdf, fallbackFont: glyphOnlyFont)
        precondition(glyphOnlyDocument.pageCount == 5)
        do {
            let font = try EXReaderFont(data: Data(contentsOf: root.appendingPathComponent("fonts/collection.ttc")), faceIndex: 1)
            retainedFontDocument = try EXReaderFixedDocument(data: pdf, fallbackFont: font)
        }
        let fallbackBitmap = try retainedFontDocument.render(page: 1)
        precondition(fallbackBitmap.width == 12)
        let head = "<r:RDF xmlns:r='http://www.w3.org/1999/02/22-rdf-syntax-ns#'><r:Description xmlns:dc='http://purl.org/dc/elements/1.1/'>"
        let xmpTail = "</r:Description></r:RDF>"
        var packet = Data((head + "<dc:title>中文😀</dc:title><dc:creator><r:Seq><r:li>Alice</r:li><r:li>Bob</r:li></r:Seq></dc:creator>" + xmpTail).utf8)
        let metadata = try EXReaderMetadata.readXMP(packet)
        packet.resetBytes(in: 0..<packet.count)
        precondition(metadata.count == 3 && metadata[0].key == "http://purl.org/dc/terms/title" && metadata[0].value == "中文😀" && metadata[1].value == "Alice" && metadata[2].value == "Bob")
        let many = head + String(repeating: "<dc:subject>词😀</dc:subject>", count: 4096) + xmpTail
        let manyMetadata = try EXReaderMetadata.readXMP(Data(many.utf8))
        precondition(manyMetadata.count == 4096)
        do {
            _ = try EXReaderMetadata.readXMP(Data("<bad/>".utf8))
            preconditionFailure("bad XMP should fail")
        } catch EXReaderError.engine(let code, _) {
            precondition(code == Int(EXR_FORMAT.rawValue))
        }
        let wave = try EXReaderWave(file: root.appendingPathComponent("audio/pcm.wav"))
        precondition(wave.format.sampleRate == 16000 && wave.format.channels == 1 && wave.format.frames == 3200)
        let samples = try wave.read(firstFrame: 0, count: 1024)
        precondition(samples.count == 1024 && samples.map { abs($0) }.max() == 0.5)
        let tail = try wave.read(firstFrame: 3199, count: 1024)
        precondition(tail.count == 1)
        let pcm = try EXReaderPCM(file: root.appendingPathComponent("audio/pcm.wav"))
        precondition(pcm.format.sampleRate == 16000 && pcm.format.channels == 1 && pcm.format.frames == 3200)
        let decoded = try pcm.read(firstFrame: 0, count: 1024)
        precondition(decoded == samples)
        let pcmTail = try pcm.read(firstFrame: 3199, count: 1024)
        let pcmEnd = try pcm.read(firstFrame: 3200, count: 1)
        precondition(pcmTail.count == 1 && pcmEnd.isEmpty)
        var config = EXReaderLayoutConfig()
        config.page.width = 220; config.page.height = 180; config.page.margin = 10
        config.page.font_size = 14; config.page.paragraph_spacing = 4
        config.userCSS = "p {background-color:#ff0000}"
        let retainedPage: EXReaderReflowPage
        let savedNodes: [EXReaderNode]
        do {
            let html = "<html><head><title>书😀</title></head><body><p id='hello' style='background-color:#ff0000'>A 中文😀</p>"
                + String(repeating: "<p>A paragraph with several words.</p>", count: 100) + "</body></html>"
            let book = try EXReaderDocument(data: Data(html.utf8), format: EXR_HTML)
            precondition(book.title != nil && String(decoding: book.utf8, as: UTF8.self).contains("中文😀"))
            savedNodes = book.nodes
            precondition(!savedNodes.isEmpty && savedNodes[0].parent == -1)
            let font = try EXReaderFont(data: Data(contentsOf: root.appendingPathComponent("fonts/primary.ttf")))
            let pager = try book.pager(font: font, config: config)
            guard let first = try pager.next(), let second = try pager.next() else { preconditionFailure("missing pages") }
            retainedPage = first
            precondition(second.content.start == first.content.end && !first.glyphs.isEmpty && !first.lines.isEmpty && !first.boxes.isEmpty)
            let glyph = first.glyphs[0]
            precondition(first.hitTest(x: glyph.x, y: glyph.baseline) != nil)
            var pages = 2
            while let _ = try pager.next() { pages += 1 }
            let end = try pager.next()
            precondition(pages > 2 && end == nil)
        }
        let pageBitmap = try retainedPage.render()
        let sourceFont = try retainedPage.fontSource(index: 0)
        let missingImage = try retainedPage.image(resource: 99999)
        precondition(!sourceFont.data.isEmpty && sourceFont.faceIndex == 0 && sourceFont.axes.isEmpty && missingImage == nil)
        precondition(pageBitmap.width == 220 && pageBitmap.height == 180 && pageBitmap.channels == 4 && !savedNodes.isEmpty)
        let retainedChapter: EXReaderDocument
        do {
            let publication = try EXReaderPublication(file: root.appendingPathComponent("books/layout.epub"))
            precondition(!publication.parts.isEmpty && publication.parts[0].path != nil)
            retainedChapter = try publication.load(part: 0)
        }
        precondition(!retainedChapter.utf8.isEmpty && !retainedChapter.nodes.isEmpty)
        precondition(retainedChapter.nodes.contains { $0.attributes.contains { $0.key == "id" && $0.value == "intro" } })
        do {
            _ = try EXReaderDocument(data: Data(), format: EXR_TXT)
            preconditionFailure("empty document should fail")
        } catch EXReaderError.engine(let code, _) {
            precondition(code == Int(EXR_ARGUMENT.rawValue))
        }
        var floatConfig = EXReaderLayoutConfig()
        floatConfig.page.width = 240; floatConfig.page.height = 240; floatConfig.page.margin = 20
        floatConfig.page.font_size = 14; floatConfig.page.line_height = 20 / 14; floatConfig.page.paragraph_spacing = 0
        do {
            let floats = try EXReaderPublication(file: root.appendingPathComponent("books/float-both.epub"))
            let chapter = try floats.load(part: 0)
            let font = try EXReaderFont(data: Data(contentsOf: root.appendingPathComponent("fonts/primary.ttf")))
            let pager = try chapter.pager(font: font, config: floatConfig)
            guard let page = try pager.next() else { preconditionFailure("missing float page") }
            precondition(!page.glyphs.isEmpty && abs(page.glyphs[0].clip_left - 80) < 0.01 && abs(page.glyphs[0].clip_right - 160) < 0.01)
            let images = page.boxes.filter { $0.kind == EXR_BOX_IMAGE }
            precondition(images.count == 2)
            for box in images {
                guard let image = try page.image(resource: Int(box.resource)) else { preconditionFailure("missing image") }
                precondition(image.width == 80 && image.height == 60)
            }
            let bitmap = try page.render()
            let pixel = 30 * bitmap.stride + 30 * 4
            precondition(bitmap.pixels[pixel] == 0 && bitmap.pixels[pixel + 1] == 128 && bitmap.pixels[pixel + 2] == 255)
        }
        do {
            let floats = try EXReaderPublication(file: root.appendingPathComponent("books/float-long-main.epub"))
            let chapter = try floats.load(part: 0)
            let font = try EXReaderFont(data: Data(contentsOf: root.appendingPathComponent("fonts/primary.ttf")))
            let pager = try chapter.pager(font: font, config: floatConfig)
            var pages = 0, letters = 0
            while let page = try pager.next() {
                letters += page.glyphs.filter { $0.codepoint == 65 }.count
                let bitmap = try page.render()
                precondition(bitmap.width == 240 && bitmap.height == 240)
                pages += 1
            }
            precondition(pages > 20 && letters == 7500)
        }
        do {
            let publication = try EXReaderPublication(file: root.appendingPathComponent("books/float-bfc-stream.epub"))
            let chapter = try publication.load(part: 0)
            let font = try EXReaderFont(data: Data(contentsOf: root.appendingPathComponent("fonts/primary.ttf")))
            let pager = try chapter.pager(font: font, config: floatConfig)
            guard let table = chapter.nodes.firstIndex(where: { $0.attributes.contains { $0.key == "id" && $0.value == "ordinary" } }) else { preconditionFailure("missing table") }
            var pages = 0, letters = 0, fragments = 0
            while let page = try pager.next() {
                letters += page.glyphs.filter { $0.codepoint == 65 }.count
                for box in page.boxes where box.node == table && (box.flags & 2) == 0 {
                    precondition(abs(box.x - 100) < 0.01 && abs(box.width - 100) < 0.01)
                    fragments += 1
                }
                let bitmap = try page.render()
                precondition(bitmap.width == 240)
                pages += 1
            }
            precondition(pages > 20 && fragments > 20 && letters == 3350)
        }
        do {
            let publication = try EXReaderPublication(file: root.appendingPathComponent("books/hyphen-long.epub"))
            let chapter = try publication.load(part: 0)
            let font = try EXReaderFont(data: Data(contentsOf: root.appendingPathComponent("fonts/primary.ttf")))
            var config = EXReaderLayoutConfig()
            config.page.width = 55; config.page.height = 100; config.page.margin = 10; config.page.font_size = 14
            config.userCSS = "html,body,p {margin:0;padding:0;font-size:14px;line-height:20px}"
            let pager = try chapter.pager(font: font, config: config)
            try pager.setHyphenation([
                EXReaderHyphenDictionary(language: "en", patterns: Data("aa1aaaa aaaa1aa".utf8), leftMinimum: 1, rightMinimum: 1),
                EXReaderHyphenDictionary(language: "fr", patterns: Data("bb1bbbb".utf8))])
            do {
                try pager.setHyphenation([EXReaderHyphenDictionary(language: "en", patterns: Data("\\patterns{a1b}".utf8))])
                preconditionFailure("invalid patterns accepted")
            } catch EXReaderError.engine(let code, _) { precondition(code == 11) }
            guard let page = try pager.next() else { preconditionFailure("missing hyphenated page") }
            let inserted = page.glyphs.filter { ($0.flags & 2048) != 0 }
            precondition(!inserted.isEmpty && inserted.allSatisfy { $0.start == $0.end })
            let bitmap = try page.render(); precondition(bitmap.width == 55)
            do { try pager.setHyphenation([]); preconditionFailure("dictionary changed after paging") }
            catch EXReaderError.engine(let code, _) { precondition(code == 1) }
        }
        do {
            let publication = try EXReaderPublication(file: root.appendingPathComponent("books/hyphen-canonical.epub"))
            let chapter = try publication.load(part: 0)
            let font = try EXReaderFont(data: Data(contentsOf: root.appendingPathComponent("fonts/primary.ttf")))
            var config = EXReaderLayoutConfig()
            config.page.width = 55; config.page.height = 100; config.page.margin = 10; config.page.font_size = 14
            config.userCSS = "html,body,p {margin:0;padding:0;font-size:14px;line-height:20px}"
            let pager = try chapter.pager(font: font, config: config)
            try pager.setHyphenation([EXReaderHyphenDictionary(language: "fr", patterns: Data("é1té".utf8), leftMinimum: 1, rightMinimum: 1)])
            guard let page = try pager.next() else { preconditionFailure("missing canonical-word page") }
            let inserted = page.glyphs.filter { ($0.flags & 2048) != 0 }
            precondition(!inserted.isEmpty && inserted.allSatisfy { $0.start == $0.end && $0.start % 8 == 3 })
            let bitmap = try page.render(); precondition(bitmap.width == 55)
        }
        do {
            let publication = try EXReaderPublication(file: root.appendingPathComponent("books/hyphen-compound.epub"))
            let chapter = try publication.load(part: 0)
            let font = try EXReaderFont(data: Data(contentsOf: root.appendingPathComponent("fonts/primary.ttf")))
            var config = EXReaderLayoutConfig()
            config.page.width = 80; config.page.height = 100; config.page.margin = 10; config.page.font_size = 14
            config.userCSS = "html,body,p {margin:0;padding:0;font-size:14px;line-height:20px}"
            let pager = try chapter.pager(font: font, config: config)
            try pager.setHyphenation([EXReaderHyphenDictionary(language: "xx", patterns: Data("aaaa1aaaa\n.aa1aa.\nNEXTLEVEL\n.a1a.".utf8), leftMinimum: 1, rightMinimum: 1)])
            guard let page = try pager.next() else { preconditionFailure("missing compound page") }
            let inserted = page.glyphs.filter { ($0.flags & 2048) != 0 }
            precondition(inserted.contains { $0.start == 5 } && inserted.allSatisfy { $0.start == $0.end && (1...7).contains($0.start % 9) })
            let bitmap = try page.render(); precondition(bitmap.width == 80)
        }
        print("Swift SDK: PDF/audio/metadata, floats, table BFCs, dictionary hyphenation and reflow lifetime passed")
    }
}
