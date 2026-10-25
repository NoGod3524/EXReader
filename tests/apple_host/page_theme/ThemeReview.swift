// SPDX-License-Identifier: MIT
import Foundation
import CoreGraphics
import CryptoKit
import CEXReader
import CReaderProduct

@main
struct ThemeReview {
    static func expect(_ value: @autoclosure () throws -> Bool, _ message: String) throws {
        guard try value() else { throw HostError.invalidResult(message) }
    }
    static func bytes(_ snapshot: HostSnapshot) throws -> Data {
        guard let data = snapshot.image?.dataProvider?.data else { throw HostError.invalidResult("Missing real SDK pixels") }
        return data as Data
    }
    static func count(_ snapshot: HostSnapshot, _ rgba: UInt32) throws -> Int {
        let data = try bytes(snapshot), image = snapshot.image!
        var result = 0
        for y in 0..<image.height { for x in 0..<image.width {
            let i = y * image.bytesPerRow + x * 4
            let value = UInt32(data[i]) << 24 | UInt32(data[i+1]) << 16 | UInt32(data[i+2]) << 8 | UInt32(data[i+3])
            if value == rgba { result += 1 }
        } }
        return result
    }
    static func preserveSolidPatch(_ original: HostSnapshot, _ themed: HostSnapshot, _ rgba: UInt32) throws {
        let before = try bytes(original), after = try bytes(themed), image = original.image!
        let expected: [UInt8] = [UInt8(rgba >> 24), UInt8((rgba >> 16) & 255), UInt8((rgba >> 8) & 255), UInt8(rgba & 255)]
        // A foreground change can round antialiased edge pixels differently.
        // Compare a real solid interior, excluding those text-edge pixels.
        for y in 0..<(image.height - 8) { for x in 0..<(image.width - 8) {
            let start = y * image.bytesPerRow + x * 4
            if !before[start..<(start + 4)].elementsEqual(expected) { continue }
            var solid = true
            for row in 0..<8 { for column in 0..<8 {
                let i = (y + row) * image.bytesPerRow + (x + column) * 4
                if !before[i..<(i + 4)].elementsEqual(expected) { solid = false; break }
            }; if !solid { break } }
            if solid {
                for row in 0..<8 {
                    let i = (y + row) * image.bytesPerRow + x * 4
                    try expect(before[i..<(i + 32)] == after[i..<(i + 32)], "Authored solid interior pixels changed")
                }
                print("THEME_SOLID_PATCH", String(format: "%08x", rgba), "x=", x, "y=", y)
                return
            }
        } }
        throw HostError.invalidResult("Authored solid interior not present in real original bitmap")
    }
#if EXR_APPLE_PAGE_THEME
    static func pump(_ condition: () -> Bool) throws {
        let end = Date().addingTimeInterval(30)
        while Date() < end {
            if condition() { return }
            RunLoop.current.run(until: Date().addingTimeInterval(0.01))
        }
        throw HostError.invalidResult("Theme model did not finish its real owner candidate")
    }
    static func reviewModel(_ resources: URL, _ output: URL) throws -> [[String: Any]] {
        let library = try HostLibrary(path: output.appendingPathComponent("model-library.sqlite"))
        let font = try HostFont(data: Data(contentsOf: resources.appendingPathComponent("Reader.otf")))
        let session = HostSession(library: library, font: font, slowDelay: 0, viewport: CGSize(width: 480, height: 640), fontSize: 28)
        let (id, _) = try session.importBook(url: resources.appendingPathComponent("Theme.txt"), cancel: HostCancelBox())
        _ = try session.open(bookID: id, cancel: HostCancelBox())
        let frame = try session.turn(1, cancel: HostCancelBox()), model = HostReaderModel()
        try model.installReviewSession(session, snapshot: frame, catalogMigration: resources.appendingPathComponent("reader-catalog-v1.sql"))
        let hash = try session.stateHash(), initial = model.frameCount
        let defaults = [UserDefaults.standard.string(forKey: "EXRFontSize"), UserDefaults.standard.string(forKey: "EXRLastBook")]
        defer { HostSDKReview.event = nil; HostSDKReview.poll = nil }
        let ready = DispatchSemaphore(value: 0), release = DispatchSemaphore(value: 0)
        var held = false
        HostSDKReview.event = { event in
            guard event == "page-theme-rendered", !held else { return }
            held = true; ready.signal()
            guard release.wait(timeout: .now() + 15) == .success else { throw HostError.invalidResult("Theme review release missing") }
        }
        model.changePageTheme(.dark)
        try pump { ready.wait(timeout: .now()) == .success }
        try expect(model.busy && model.frameCount == initial && model.pageThemeChoice == .original, "Unaccepted theme published early")
        model.changePageTheme(.light)
        model.observePageThemeEnvironment(dark: true)
        model.changePageTheme(.system)
        model.observePageThemeEnvironment(dark: false)
        model.observePageThemeEnvironment(dark: true)
        release.signal()
        try pump { !model.busy && model.pageThemeChoice == .system }
        HostSDKReview.event = nil
        try expect(model.pageThemePalette == HostPagePalette.resolve(.system, systemDark: true) && model.frameCount == initial + 1,
                   "Busy notifications did not coalesce to the latest palette or stale epoch published")
        try expect(try session.stateHash() == hash && defaults == [UserDefaults.standard.string(forKey: "EXRFontSize"), UserDefaults.standard.string(forKey: "EXRLastBook")],
                   "Theme model saved old settings or SDK state")
        var checks: [[String: Any]] = [["id": "model:latest-system-notification-only", "passed": true]]
        let prior = model.pageThemeObservation, count = model.frameCount
        HostSDKReview.event = { if $0 == "page-theme-rendered" { throw HostError.invalidResult("Injected theme owner failure") } }
        model.changePageTheme(.light)
        try pump { !model.busy }
        HostSDKReview.event = nil
        try expect(model.pageThemeObservation == prior && model.frameCount == count && !model.errorText.isEmpty,
                   "Failed owner candidate replaced accepted pixels")
        model.changePageTheme(.light)
        try pump { !model.busy && model.pageThemeChoice == .light }
        try expect(model.errorText.isEmpty && model.frameCount == count + 1, "Theme retry did not recover")
        checks.append(["id": "model:failure-preserves-frame-and-retry", "passed": true])
        let accepted = model.pageThemeObservation, acceptedCount = model.frameCount
        HostSDKReview.event = { event in
            if event == "page-theme-rendered" { DispatchQueue.main.sync { model.cancelWork() } }
        }
        model.changePageTheme(.dark)
        try pump { !model.busy }
        HostSDKReview.event = nil
        try expect(model.pageThemeObservation == accepted && model.frameCount == acceptedCount, "Cancelled theme published")
        try expect(try session.stateHash() == hash, "Model cancel changed SDK progress")
        checks.append(["id": "model:cancel-preserves-accepted-frame", "passed": true])
        return checks
    }
#endif
    static func main() throws {
        let env = ProcessInfo.processInfo.environment
        guard env["GITHUB_ACTIONS"] == "true" else { throw HostError.invalidInput("Actions only") }
        let resources = URL(fileURLWithPath: CommandLine.arguments[1]), output = URL(fileURLWithPath: CommandLine.arguments[2])
        try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
        let queue = DispatchQueue(label: "org.exreader.page-theme-consumer")
        var checks: [[String: Any]] = [], originals: [String: String] = [:], metrics: [[String: Any]] = []
        try queue.sync {
            let library = try HostLibrary(path: output.appendingPathComponent("library.sqlite"))
            let catalog = try HostCatalog(path: output.appendingPathComponent("catalog.sqlite"),
                migrationURL: resources.appendingPathComponent("reader-catalog-v1.sql"), ownerQueue: queue)
            defer { try? catalog.close(); HostSDKReview.poll = nil; HostSDKReview.event = nil }
            let font = try HostFont(data: Data(contentsOf: resources.appendingPathComponent("Reader.otf")))
            var session = HostSession(library: library, font: font, slowDelay: 0, viewport: CGSize(width: 480, height: 640), fontSize: 28)
            func check(_ name: String, _ operation: () throws -> Void) rethrows {
                try operation(); checks.append(["id": name, "passed": true])
            }
            func productCounts() throws -> [Int64] {
                [try catalog.scalar("SELECT count(*) FROM reader_revisions"), try catalog.scalar("SELECT count(*) FROM reader_outbox")]
            }
            for name in ["Theme.txt", "ThemeText.epub", "ThemeAuthored.epub", "Sample.pdf", "NavigationPages.cbz"] {
                let source = resources.appendingPathComponent(name), original = try Data(contentsOf: source)
                let (id, _) = try session.importBook(url: source, cancel: HostCancelBox(), catalog: catalog)
                var frame = try session.open(bookID: id, cancel: HostCancelBox())
                if name == "Theme.txt" || name == "ThemeText.epub" { frame = try session.turn(1, cancel: HostCancelBox()) }
                let initial = try bytes(frame), capture = try session.readingCapture(cancel: HostCancelBox()), hash = try session.stateHash()
                let counts = try productCounts(), notes = try session.notes().count
                originals[name] = SHA256.hash(data: initial).map { String(format: "%02x", $0) }.joined()
                try check(name + ":original") {
                    try expect((name != "Theme.txt" && name != "ThemeText.epub") || (capture.anchor?.start ?? 0) > 0, "Nonzero fixture failed to move")
                    try initial.write(to: output.appendingPathComponent(name + ".original.rgba"))
                }
#if EXR_APPLE_PAGE_THEME
                for choice in [HostPageThemeChoice.dark, .light, .system, .original] {
                    let palette = HostPagePalette.resolve(choice, systemDark: true)
                    let (candidate, next) = try session.pageThemeCandidate(palette, cancel: HostCancelBox())
                    try check(name + ":" + (choice == .original ? "original-roundtrip" : choice.rawValue)) {
                        try expect(try candidate.readingCapture(cancel: HostCancelBox()) == capture && candidate.stateHash() == hash,
                                   "Theme changed the original capture or SDK progress/notes")
                        try expect(try productCounts() == counts && candidate.notes().count == notes, "Theme wrote product/notes")
                        try expect(next.pageRange == frame.pageRange && next.pageText == frame.pageText && next.location == frame.location,
                                   "Color-only theme changed the reading text or page")
                        if name.hasSuffix("pdf") || name.hasSuffix("cbz") || choice == .original {
                            try expect(try bytes(next) == initial, "Fixed/original bitmap changed")
                        } else {
                            let expected: UInt32 = choice == .light ? 0xffffffff : 0x101010ff
                            try expect(try bytes(next).prefix(4) == Data([UInt8(expected >> 24), UInt8((expected >> 16) & 255), UInt8((expected >> 8) & 255), UInt8(expected & 255)]), "Canvas pixel differs")
                            try expect(try count(next, palette.foreground!) > 0, "Actual text foreground missing")
                            if name == "ThemeAuthored.epub" {
                                print("THEME_AUTHORED_COUNTS original=\(try count(frame, 0x223344ff)) themed=\(try count(next, 0x223344ff))")
                                try preserveSolidPatch(frame, next, 0x223344ff)
                                try expect(try count(frame, 0xc02040ff) > 0 && count(next, 0xc02040ff) == count(frame, 0xc02040ff), "Embedded image changed")
                                try preserveSolidPatch(frame, next, 0xc02040ff)
                            }
                        }
                    }
                    metrics.append(["book": name, "choice": choice.rawValue, "width": next.image!.width, "height": next.image!.height,
                        "rgba_sha256": SHA256.hash(data: try bytes(next)).map { String(format: "%02x", $0) }.joined()])
                    session = candidate
                }
                if name == "Theme.txt" || name == "ThemeText.epub" {
                    let dark = HostPagePalette.resolve(.dark, systemDark: false)
                    let measure = HostCancelBox(); var polls = 0
                    HostSDKReview.poll = { if $0 === measure { polls += 1 } }
                    _ = try session.pageThemeCandidate(dark, cancel: measure)
                    HostSDKReview.poll = nil
                    try expect(polls > 0, "No genuine SDK cancellation polls")
                    for stop in 1...polls {
                        let box = HostCancelBox(); var n = 0
                        HostSDKReview.poll = { if $0 === box { n += 1; if n == stop { box.cancel() } } }
                        var cancelled = false
                        do { _ = try session.pageThemeCandidate(dark, cancel: box) }
                        catch let error as HostError { cancelled = error.isCancelled }
                        HostSDKReview.poll = nil
                        try expect(cancelled, "Cancellation point accepted a frame")
                        try expect(try session.stateHash() == hash && productCounts() == counts && session.readingCapture(cancel: HostCancelBox()) == capture,
                                   "Cancelled theme changed accepted session")
                    }
                    checks.append(["id": name + ":cancel-every-sdk-poll", "passed": true, "polls": polls])
                    try check(name + ":post-render-failure") {
                        HostSDKReview.event = { if $0 == "page-theme-rendered" { throw HostError.invalidResult("Injected post-render failure") } }
                        var rejected = false
                        do { _ = try session.pageThemeCandidate(dark, cancel: HostCancelBox()) } catch { rejected = true }
                        HostSDKReview.event = nil
                        try expect(rejected && session.pagePalette == .original, "Failed theme replaced old session")
                        try expect(try session.stateHash() == hash && productCounts() == counts, "Failed theme wrote state")
                        let (_, retry) = try session.pageThemeCandidate(dark, cancel: HostCancelBox())
                        try expect(try count(retry, 0x101010ff) > 0, "Retry failed to produce real dark frame")
                    }
                }
#endif
                try check(name + ":source-retained") { try expect(try Data(contentsOf: source) == original, "Source file changed") }
                session.close()
            }
        }
#if EXR_APPLE_PAGE_THEME
        checks += try reviewModel(resources, output)
#endif
        let enabled: Bool
#if EXR_APPLE_PAGE_THEME
        enabled = true
#else
        enabled = false
#endif
        let result: [String: Any] = ["accepted": true, "theme_enabled": enabled, "source_sha": env["GITHUB_SHA"] ?? "",
            "run_id": env["GITHUB_RUN_ID"] ?? "", "attempt": env["GITHUB_RUN_ATTEMPT"] ?? "", "sdk": HOST_SDK_VERSION,
            "abi": HOST_ABI_VERSION, "checks": checks, "originals": originals, "metrics": metrics,
            "complete_product": false, "old_340_migration_tested": false]
        try JSONSerialization.data(withJSONObject: result, options: [.prettyPrinted, .sortedKeys]).write(to: output.appendingPathComponent("theme-review.json"))
        print("PAGE_THEME_NATIVE_PASSED checks=\(checks.count) enabled=\(enabled)")
    }
}
