// SPDX-License-Identifier: GPL-3.0-only
import Foundation
import CEXReader

@main struct SDKSmoke {
    static func main() throws {
        precondition(CommandLine.arguments.count == 2)
        let root = URL(fileURLWithPath: CommandLine.arguments[1])
        let pdf = try Data(contentsOf: root.appendingPathComponent("fixed-pages/pdf-public.pdf"))
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
        print("Swift SDK: PDF text/render/font ownership owned multilingual metadata and WAVE samples passed")
    }
}
