// SPDX-License-Identifier: MIT
// Read-only interpretation of original failure images, never reader acceptance.
import Foundation
import ImageIO
import Vision
import AVFoundation
import CoreMedia

guard ProcessInfo.processInfo.environment["GITHUB_ACTIONS"] == "true", CommandLine.arguments.count == 2 else {
    fatalError("Actions only; supply the exported original attachment directory")
}
let root = URL(fileURLWithPath: CommandLine.arguments[1]).standardizedFileURL
let data = try Data(contentsOf: root.appendingPathComponent("manifest.json"))
guard let groups = try JSONSerialization.jsonObject(with: data) as? [[String: Any]] else { fatalError("Invalid export manifest") }
var count = 0
let wantedCase = ProcessInfo.processInfo.environment["ORIGINAL_CASE"] ?? "testFixedCbzAndPdfRealPointRecords"
func recognize(_ image: CGImage, label: String) {
    print("ORIGINAL-FAILURE-IMAGE \(label) \(image.width)x\(image.height)")
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.recognitionLanguages = ["zh-Hans", "en-US"]
    request.usesLanguageCorrection = false
    do {
        try VNImageRequestHandler(cgImage: image, options: [:]).perform([request])
        for row in request.results ?? [] {
            if let value = row.topCandidates(1).first { print("IMAGE-TEXT \(value.confidence): \(value.string)") }
        }
    } catch { print("IMAGE-INTERPRETATION-ERROR \(error)") }
    count += 1
}
for group in groups {
    let owner = (group["testIdentifier"] as? String) ?? (group["testName"] as? String) ?? ""
    guard owner.contains(wantedCase) else { continue }
    for attachment in group["attachments"] as? [[String: Any]] ?? [] {
        guard let name = attachment["exportedFileName"] as? String else { continue }
        let url = root.appendingPathComponent(name).standardizedFileURL
        guard url.path.hasPrefix(root.path + "/") else { fatalError("Attachment path escaped export directory") }
        print("FAILED-CASE-ATTACHMENT \(name)")
        if let source = CGImageSourceCreateWithURL(url as CFURL, nil),
           let image = CGImageSourceCreateImageAtIndex(source, 0, nil) {
            recognize(image, label: name)
        } else if ["mp4", "mov", "m4v"].contains(url.pathExtension.lowercased()) {
            let asset = AVURLAsset(url: url)
            let duration = CMTimeGetSeconds(asset.duration)
            guard duration.isFinite && duration > 0 else { print("VIDEO-DURATION-UNAVAILABLE"); continue }
            let generator = AVAssetImageGenerator(asset: asset)
            generator.appliesPreferredTrackTransform = true
            let frames = root.deletingLastPathComponent().appendingPathComponent("failure-video-frames")
            try FileManager.default.createDirectory(at: frames, withIntermediateDirectories: true)
            let samples = Set([1.0,20.0,40.0,60.0,90.0,120.0,max(0,duration-1)]).sorted().filter { $0 < duration }
            print("ORIGINAL-VIDEO \(name) duration=\(duration) samples=\(samples)")
            for second in samples {
                do {
                    var actual = CMTime.zero
                    let image = try generator.copyCGImage(at: CMTime(seconds: second, preferredTimescale: 600), actualTime: &actual)
                    let output = frames.appendingPathComponent("frame-\(Int(second)).png")
                    guard let writer = CGImageDestinationCreateWithURL(output as CFURL, "public.png" as CFString, 1, nil) else { fatalError("Frame output unavailable") }
                    CGImageDestinationAddImage(writer, image, nil)
                    guard CGImageDestinationFinalize(writer) else { fatalError("Frame output failed") }
                    recognize(image, label: "\(name) requested=\(second) actual=\(CMTimeGetSeconds(actual))")
                } catch { print("VIDEO-FRAME-ERROR \(second): \(error)") }
            }
        }
    }
}
print("ORIGINAL-FAILURE-IMAGES \(count); diagnostic interpretation only; original failed run unchanged")
