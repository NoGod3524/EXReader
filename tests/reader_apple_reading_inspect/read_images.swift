// SPDX-License-Identifier: MIT
// Read-only interpretation of original failure images, never reader acceptance.
import Foundation
import ImageIO
import Vision

guard ProcessInfo.processInfo.environment["GITHUB_ACTIONS"] == "true", CommandLine.arguments.count == 2 else {
    fatalError("Actions only; supply the exported original attachment directory")
}
let root = URL(fileURLWithPath: CommandLine.arguments[1]).standardizedFileURL
let data = try Data(contentsOf: root.appendingPathComponent("manifest.json"))
guard let groups = try JSONSerialization.jsonObject(with: data) as? [[String: Any]] else { fatalError("Invalid export manifest") }
var count = 0
for group in groups {
    let owner = (group["testIdentifier"] as? String) ?? (group["testName"] as? String) ?? ""
    guard owner.contains("testFixedCbzAndPdfRealPointRecords") else { continue }
    for attachment in group["attachments"] as? [[String: Any]] ?? [] {
        guard let name = attachment["exportedFileName"] as? String else { continue }
        let url = root.appendingPathComponent(name).standardizedFileURL
        guard url.path.hasPrefix(root.path + "/"),
              let source = CGImageSourceCreateWithURL(url as CFURL, nil),
              let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else { continue }
        print("ORIGINAL-FAILURE-IMAGE \(name) \(image.width)x\(image.height)")
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.recognitionLanguages = ["zh-Hans", "en-US"]
        request.usesLanguageCorrection = false
        do {
            try VNImageRequestHandler(cgImage: image).perform([request])
            for row in request.results ?? [] {
                if let value = row.topCandidates(1).first { print("IMAGE-TEXT \(value.confidence): \(value.string)") }
            }
        } catch { print("IMAGE-INTERPRETATION-ERROR \(error)") }
        count += 1
    }
}
print("ORIGINAL-FAILURE-IMAGES \(count); diagnostic interpretation only; original failed run unchanged")
