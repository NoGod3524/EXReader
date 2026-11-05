// SPDX-License-Identifier: MIT
import AppKit
import ScreenCaptureKit
import CoreMedia
import CoreVideo
import CryptoKit
import Darwin

final class Frames: NSObject, SCStreamOutput {
    let output: FileHandle
    let lock = NSLock()
    var frames = 0
    var complete = 0
    var positiveDisplayTime = 0
    init(_ url: URL) throws {
        FileManager.default.createFile(atPath: url.path, contents: nil)
        output = try FileHandle(forWritingTo: url)
    }
    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of outputType: SCStreamOutputType) {
        guard outputType == .screen, sampleBuffer.isValid,
              let groups = CMSampleBufferGetSampleAttachmentsArray(sampleBuffer, createIfNecessary: false) as? [[SCStreamFrameInfo: Any]],
              let metadata = groups.first, let status = metadata[.status] as? Int else { return }
        var value: [String: Any] = ["status": status, "display_time_ticks": metadata[.displayTime] as? UInt64 ?? 0,
            "receipt_mach_ticks": mach_absolute_time(), "sample_pts_seconds": CMTimeGetSeconds(sampleBuffer.presentationTimeStamp)]
        if status == SCFrameStatus.complete.rawValue, let pixels = sampleBuffer.imageBuffer {
            CVPixelBufferLockBaseAddress(pixels, .readOnly)
            if let base = CVPixelBufferGetBaseAddress(pixels) {
                let width = CVPixelBufferGetWidth(pixels), height = CVPixelBufferGetHeight(pixels), stride = CVPixelBufferGetBytesPerRow(pixels)
                var hash = SHA256()
                for row in 0..<height { hash.update(bufferPointer: UnsafeRawBufferPointer(start: base.advanced(by: row * stride), count: width * 4)) }
                value["pixel_sha256"] = hash.finalize().map { String(format: "%02x", $0) }.joined()
                value["width"] = width; value["height"] = height; value["stride"] = stride
            }
            CVPixelBufferUnlockBaseAddress(pixels, .readOnly)
        }
        guard let bytes = try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]) else { return }
        lock.lock(); defer { lock.unlock() }
        try? output.write(contentsOf: bytes + Data([10]))
        frames += 1
        if status == SCFrameStatus.complete.rawValue { complete += 1; if (metadata[.displayTime] as? UInt64 ?? 0) > 0 { positiveDisplayTime += 1 } }
    }
    func finish() throws -> [String: Int] {
        lock.lock(); defer { lock.unlock() }; try output.synchronize(); try output.close()
        return ["events": frames, "complete_frames": complete, "complete_frames_with_display_time": positiveDisplayTime]
    }
}

@main struct Probe {
    static func main() async {
        let args = CommandLine.arguments
        let folder = URL(fileURLWithPath: args[1], isDirectory: true)
        var report: [String: Any] = ["f08_accepted": false, "workload_budget_measured": false,
            "scope": "ScreenCaptureKit capability only; no frame percentiles or workload acceptance",
            "target_bundle": args[2], "required_title": args.count > 3 ? args[3] : "",
            "preflight_screen_capture_access": CGPreflightScreenCaptureAccess(),
            "display_pixels": [CGDisplayPixelsWide(CGMainDisplayID()), CGDisplayPixelsHigh(CGMainDisplayID())],
            "resolution_changed": false]
        do {
            guard CGPreflightScreenCaptureAccess() else { throw NSError(domain: "F08Capture", code: 1, userInfo: [NSLocalizedDescriptionKey: "ScreenCaptureKit permission is not granted on this runner"] ) }
            let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
            report["windows"] = content.windows.map { ["id": $0.windowID, "bundle": $0.owningApplication?.bundleIdentifier ?? "", "pid": $0.owningApplication?.processID ?? 0, "title": $0.title ?? "", "width": $0.frame.width, "height": $0.frame.height] as [String: Any] }
            let candidates = content.windows.filter { $0.owningApplication?.bundleIdentifier == args[2] && $0.isOnScreen && $0.frame.width > 100 && $0.frame.height > 100 && (args.count <= 3 || ($0.title ?? "").contains(args[3])) }
            guard candidates.count == 1, let window = candidates.first else { throw NSError(domain: "F08Capture", code: 2, userInfo: [NSLocalizedDescriptionKey: "Target window selection must be unique; candidates=\(candidates.count)"] ) }
            let filter = SCContentFilter(desktopIndependentWindow: window)
            let configuration = SCStreamConfiguration()
            configuration.width = Int(filter.contentRect.width * CGFloat(filter.pointPixelScale))
            configuration.height = Int(filter.contentRect.height * CGFloat(filter.pointPixelScale))
            configuration.minimumFrameInterval = CMTime(value: 1, timescale: 120)
            configuration.queueDepth = 5; configuration.showsCursor = false; configuration.capturesAudio = false
            configuration.pixelFormat = kCVPixelFormatType_32BGRA
            var timebase = mach_timebase_info_data_t(); mach_timebase_info(&timebase)
            report["mach_timebase"] = ["numer": timebase.numer, "denom": timebase.denom]
            report["window_id"] = window.windowID; report["window_pid"] = window.owningApplication?.processID
            report["capture_pixels"] = [configuration.width, configuration.height]
            let frames = try Frames(folder.appendingPathComponent("frames.jsonl"))
            let stream = SCStream(filter: filter, configuration: configuration, delegate: nil)
            let queue = DispatchQueue(label: "org.exreader.f08.capture", qos: .userInitiated)
            try stream.addStreamOutput(frames, type: .screen, sampleHandlerQueue: queue)
            try await stream.startCapture()
            try await Task.sleep(for: .seconds(8))
            try await stream.stopCapture()
            let totals = try frames.finish(); report["totals"] = totals
            report["capability_complete"] = (totals["complete_frames_with_display_time"] ?? 0) > 0
        } catch { report["capability_complete"] = false; report["error"] = String(describing: error) }
        let data = try! JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys])
        try! data.write(to: folder.appendingPathComponent("capture.json"))
        print(String(decoding: data, as: UTF8.self))
    }
}
