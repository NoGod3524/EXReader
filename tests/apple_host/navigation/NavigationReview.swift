// SPDX-License-Identifier: MIT
import Foundation
import CoreGraphics
import CEXReader
import CReaderProduct
import Darwin

@main struct NavigationReview {
    static func main() throws {
        let environment = ProcessInfo.processInfo.environment
        guard environment["GITHUB_ACTIONS"] == "true" else { throw HostError.invalidInput("Actions only") }
        let resources = URL(fileURLWithPath: CommandLine.arguments[1]), output = URL(fileURLWithPath: CommandLine.arguments[2])
        try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
        let queue = DispatchQueue(label: "apple.navigation.review.owner")
        var checks: [[String: Any]] = []
        func expect(_ value: Bool, _ detail: String) throws { if !value { throw HostError.invalidResult(detail) } }
        func rejects(_ operation: () throws -> Void) -> Bool { do { try operation(); return false } catch { return true } }
        func check(_ name: String, _ operation: () throws -> Void) {
            var value: [String: Any] = ["id": name, "passed": false]
            do { try operation(); value["passed"] = true } catch { value["error"] = error.localizedDescription }
            checks.append(value); print("NAVIGATION CHECK \(value)"); fflush(stdout)
        }
        try queue.sync {
            let library = try HostLibrary(path: output.appendingPathComponent("library.sqlite"))
            let catalog = try HostCatalog(path: output.appendingPathComponent("catalog.sqlite"),
                migrationURL: resources.appendingPathComponent("reader-catalog-v1.sql"), ownerQueue: queue)
            defer { try? catalog.close() }
            let font = try HostFont(data: Data(contentsOf: resources.appendingPathComponent("Reader.otf")))
            let session = HostSession(library: library, font: font, slowDelay: 0, viewport: CGSize(width: 480, height: 640), fontSize: 28)
            let source = resources.appendingPathComponent("Sample.epub"), bytes = try Data(contentsOf: source)
            let expected = try JSONSerialization.jsonObject(with: Data(contentsOf: resources.appendingPathComponent("navigation-expected.json"))) as! [String: Any]
            let (id, _) = try session.importBook(url: source, cancel: HostCancelBox(), catalog: catalog)
            _ = try session.open(bookID: id, cancel: HostCancelBox())
            let key = try catalog.searchSourceKey(sdkID: id)
            let originalHash = try session.stateHash()
            let revisions = try catalog.scalar("SELECT count(*) FROM reader_revisions")
            let outbox = try catalog.scalar("SELECT count(*) FROM reader_outbox")
            func page(_ parent: UInt64 = UInt64.max, first: UInt64 = 0, cancel: HostCancelBox = HostCancelBox()) throws -> HostNavigationPage {
                try HostNavigationWorker.page(library: library, font: font, bookID: id, key: key, parent: parent, first: first, cancel: cancel)
            }
            func resolve(_ row: UInt64, part: UInt64 = UInt64.max, cfi: String = "", cancel: HostCancelBox = HostCancelBox()) throws -> HostNavigationSelection {
                try HostNavigationWorker.resolve(library: library, font: font, bookID: id, key: key,
                    row: row, explicitPart: part, cfi: cfi, cancel: cancel)
            }
            let first = try page()
            check("hierarchical-pages-32-32-6") {
                let second = try page(first: first.next), third = try page(first: second.next)
                try expect(expected["roots"] as? Int == 70 && first.total == 70 && first.rows.count == 32 && second.rows.count == 32 && third.rows.count == 6,
                    "Declared 70 roots do not page 32/32/6")
                try expect(third.next == UInt64.max && !first.pages && Set((first.rows + second.rows + third.rows).map(\.index)).count == 70,
                    "Rows repeated or authored directory mislabeled")
                let child = try page(0)
                try expect(child.rows.count == 1 && child.rows[0].index == 1 && child.rows[0].parent == 0 && child.rows[0].label == "Destination chapter", "Hierarchy changed")
            }
            check("snapshot-read-only-source-progress-product") {
                try expect(try session.stateHash() == originalHash && Data(contentsOf: source) == bytes, "Directory changed original or progress")
                try expect(try catalog.scalar("SELECT count(*) FROM reader_revisions") == revisions &&
                    catalog.scalar("SELECT count(*) FROM reader_outbox") == outbox, "Directory changed product history")
            }
            check("independent-direct-found-and-projection") {
                let selection = try resolve(1)
                let (candidate, frame) = try session.navigationCandidate(selection, acceptPart: false, cancel: HostCancelBox())
                try expect(candidate.library.handle != library.handle && frame.part == 1 && frame.pageText.contains(expected["destination_text"] as! String),
                    "Independent FOUND did not select exact chapter node")
                let target = selection.resolution.target
                let poisoned = target.path.withCString { path in target.partID.withCString { identity in target.fragment.withCString { fragment in
                    var raw = reader_navigation_target()
                    raw.kind = target.kind; raw.row = target.row; raw.part = target.part; raw.node = target.node + 1
                    raw.part_path = UnsafeMutablePointer(mutating: path); raw.part_id = UnsafeMutablePointer(mutating: identity)
                    raw.fragment = UnsafeMutablePointer(mutating: fragment)
                    return HostNavigationSelection(bookID: selection.bookID, sourceKey: selection.sourceKey, row: selection.row, cfi: "",
                        resolution: HostNavigationResolution(status: READER_NAVIGATION_OK, target: HostNavigationTarget(raw), candidates: []))
                } } }
                let before = try session.stateHash()
                try expect(rejects { _ = try session.navigationCandidate(poisoned, acceptPart: false, cancel: HostCancelBox()) }, "Wrong F2 native node escaped independent SDK verification")
                try expect(try session.stateHash() == before, "Rejected poisoned node changed progress")
            }
            check("duplicate-spine-explicit-choice") {
                let ambiguous = try resolve(3)
                try expect(ambiguous.resolution.status == READER_NAVIGATION_AMBIGUOUS && ambiguous.resolution.candidates == [0, 3], "Repeated path guessed an occurrence")
                try expect(rejects { _ = try session.navigationCandidate(ambiguous, acceptPart: false, cancel: HostCancelBox()) }, "Ambiguous selection navigated")
                let explicit = try resolve(3, part: 3)
                let (_, frame) = try session.navigationCandidate(explicit, acceptPart: false, cancel: HostCancelBox())
                try expect(frame.part == 3 && frame.pageText.contains(expected["duplicate_text"] as! String), "Explicit spine choice lost identity")
                try expect(rejects { _ = try resolve(3, part: 1) }, "Unlisted explicit part accepted")
            }
            check("part-only-requires-explicit-confirmation") {
                let missing = try resolve(2), before = try session.stateHash()
                try expect(missing.resolution.status == READER_NAVIGATION_PART_ONLY, "Missing fragment mislabeled")
                try expect(rejects { _ = try session.navigationCandidate(missing, acceptPart: false, cancel: HostCancelBox()) }, "Missing fragment implicitly navigated")
                try expect(try session.stateHash() == before, "Rejected chapter-start changed progress")
                let (_, frame) = try session.navigationCandidate(missing, acceptPart: true, cancel: HostCancelBox())
                try expect(frame.part == 1 && frame.pageText.contains("C01P000W00"), "Confirmed chapter start differs")
            }
            check("external-unsafe-and-source-mismatch-refused") {
                let before = try session.stateHash()
                try expect(rejects { _ = try resolve(4) } && rejects { _ = try resolve(5) }, "External or unsafe URI opened")
                try expect(rejects { _ = try HostNavigationWorker.page(library: library, font: font, bookID: id,
                    key: key + ":changed", parent: UInt64.max, first: 0, cancel: HostCancelBox()) }, "Unverified source accepted")
                try expect(try session.stateHash() == before, "Rejected target changed progress")
            }
            check("actual-snapshot-cancel-and-retry") {
                let active = HostCancelBox(), before = try session.stateHash()
#if EXR_APPLE_HOST_REVIEW
                let previous = HostSDKReview.poll
                var observed = false
                HostSDKReview.poll = { box in
                    if box === active && HostNavigationWorker.reviewInsideSnapshot { observed = true; box.cancel() }
                    else { previous?(box) }
                }
                defer { HostSDKReview.poll = previous }
                try expect(rejects { _ = try page(cancel: active) } && observed, "Cancellation was not inside actual F2")
#endif
                try expect(try page().rows.map(\.index) == first.rows.map(\.index), "Cancelled directory advanced paging")
                let cancelled = HostCancelBox(); cancelled.cancel()
                let selection = try resolve(1)
                try expect(rejects { _ = try session.navigationCandidate(selection, acceptPart: false, cancel: cancelled) }, "Cancelled selection committed")
                try expect(try session.stateHash() == before, "Cancellation changed progress")
            }
            let publication = try HostPublication(library: library, bookID: id, cancel: HostCancelBox())
            var rawDocument: OpaquePointer?, error = exr_error()
            try hostCheck(exr_publication_load(publication.handle, 1, &rawDocument, &error), error)
            guard let rawDocument else { throw HostError.invalidResult("CFI fixture load missing") }
            let document = HostDocument(adopting: rawDocument)
            var nodeCount = 0
            guard let nodes = exr_document_nodes(document.handle, &nodeCount),
                  let unicodeNode = (0..<nodeCount).first(where: { nodes[$0].kind == EXR_NODE_TEXT && hostString(nodes[$0].text).contains("A😀Z") }),
                  let foldedNode = (0..<nodeCount).first(where: { nodes[$0].kind == EXR_NODE_TEXT && hostString(nodes[$0].text).contains("A   B") }) else {
                throw HostError.invalidResult("Declared raw CFI nodes missing")
            }
            func cfi(_ offset: Int) throws -> String {
                let active = HostCancelBox()
                // A successful candidate commits through a second connection;
                // the old library source lease intentionally expires then.
                let current = try HostPublication(library: library, bookID: id, cancel: active)
                var loaded: OpaquePointer?
                try hostCheck(exr_publication_load(current.handle, 1, &loaded, &error), error)
                guard let loaded else { throw HostError.invalidResult("Fresh CFI fixture load missing") }
                let snapshot = HostDocument(adopting: loaded)
                var point = exr_cfi_point(), result: UnsafeMutablePointer<CChar>?, control = hostControl(active)
                point.node = unicodeNode; point.offset = offset
                try withExtendedLifetime((active, current, snapshot)) {
                    try hostCheck(exr_publication_cfi_create(current.handle, 1, snapshot.handle, &point, &control, &result, &error), error)
                }
                defer { exr_free(result) }
                return hostString(result)
            }
            check("cfi-independent-utf16-to-projection-found") {
                let input = try cfi(3), selection = try resolve(UInt64.max, cfi: input)
                let (_, frame) = try session.navigationCandidate(selection, acceptPart: false, cancel: HostCancelBox())
                try expect(frame.part == 1 && frame.pageText.contains("A😀Z"), "CFI did not map whole non-BMP scalar")
            }
            check("cfi-surrogate-and-folding-refused") {
                try expect(rejects { _ = try HostNavigationWorker.cfiProjection(document: document, node: UInt64(unicodeNode), units: 2) }, "Surrogate interior mapped")
                try expect(rejects { _ = try HostNavigationWorker.cfiProjection(document: document, node: UInt64(foldedNode), units: 1) }, "Folded raw range guessed")
                let input = try cfi(2), before = try session.stateHash()
                let selection = try resolve(UInt64.max, cfi: input)
                try expect(rejects { _ = try session.navigationCandidate(selection, acceptPart: false, cancel: HostCancelBox()) }, "Surrogate CFI committed")
                try expect(try session.stateHash() == before, "Invalid CFI changed progress")
            }
            check("pdf-cbz-pages-only-independent-id") {
                for name in ["Sample.pdf", "NavigationPages.cbz"] {
                    let (bookID, _) = try session.importBook(url: resources.appendingPathComponent(name), cancel: HostCancelBox(), catalog: catalog)
                    _ = try session.open(bookID: bookID, cancel: HostCancelBox())
                    let identity = try catalog.searchSourceKey(sdkID: bookID)
                    let list = try HostNavigationWorker.page(library: library, font: font, bookID: bookID,
                        key: identity, parent: UInt64.max, first: 0, cancel: HostCancelBox())
                    try expect(list.pages && !list.rows.isEmpty, "Fixed source advertised authored outline")
                    let chosen = try HostNavigationWorker.resolve(library: library, font: font, bookID: bookID,
                        key: identity, row: list.rows.last!.index, cancel: HostCancelBox())
                    let (_, frame) = try session.navigationCandidate(chosen, acceptPart: false, cancel: HostCancelBox())
                    try expect(frame.pageIndex == Int(chosen.resolution.target.part), "Independent fixed page descriptor differs")
                }
            }
            check("late-output-close-and-book-switch-fenced") {
                let oldBookSelection = try resolve(1), before = try session.stateHash()
                try expect(rejects { _ = try session.navigationCandidate(oldBookSelection, acceptPart: false, cancel: HostCancelBox()) }, "Old book target escaped live session identity")
                try expect(try session.stateHash() == before, "Old book target changed current book progress")
                let state = HostNavigationState(); state.bind(id)
                let (epoch, _) = state.begin(); state.cancel()
                state.accept(first, key: key, generation: epoch)
                try expect(state.page == nil && !state.running, "Close accepted old directory")
                state.bind(id); let (otherEpoch, _) = state.begin(); state.bind(id + 1)
                state.accept(first, key: key, generation: otherEpoch)
                try expect(state.page == nil && state.bookID == id + 1, "Book switch accepted old directory")
            }
            check("one-dynamic-sdk-image") {
                var images: [String] = []
                for name in ["exr_document_resolve", "exr_publication_cfi_resolve", "exr_anchor_resolve_ex", "exr_pager_anchor_resolve"] {
                    guard let symbol = dlsym(UnsafeMutableRawPointer(bitPattern: -2), name) else { throw HostError.invalidResult("SDK symbol missing") }
                    var info = Dl_info()
                    try expect(dladdr(symbol, &info) != 0, "SDK image missing")
                    images.append(String(cString: info.dli_fname))
                }
                try expect(Set(images).count == 1 && images[0].contains("libexreader"), "Navigation duplicated SDK provider")
                print("NAVIGATION_DSO_IMAGES \(images)")
            }
        }
        let failed = checks.filter { $0["passed"] as? Bool != true }.count
        let result: [String: Any] = ["accepted": failed == 0 && checks.count == 12, "failed": failed, "skipped": 0,
            "source_sha": environment["GITHUB_SHA"] ?? "", "run_id": environment["GITHUB_RUN_ID"] ?? "",
            "attempt": environment["GITHUB_RUN_ATTEMPT"] ?? "", "checks": checks]
        try JSONSerialization.data(withJSONObject: result, options: [.prettyPrinted, .sortedKeys])
            .write(to: output.appendingPathComponent("navigation-review.json"))
        print("NAVIGATION_REPORT \(result)"); fflush(stdout)
        if failed != 0 || checks.count != 12 { exit(1) }
    }
}
