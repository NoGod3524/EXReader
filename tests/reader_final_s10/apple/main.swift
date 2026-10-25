// SPDX-License-Identifier: MIT
// S10 computer-transfer driver for the iOS Simulator.
//
// This is not a product application. It bundles the UNCHANGED Apple host owner
// (HostReaderModel/HostSession/HostLibrary/HostCatalog from examples/apple) and
// only drives the existing import entry: a file that the computer placed in the
// Files-shared Documents container is imported through
// HostReaderModel.importFile(url:) - including its security-scoped access - and
// the stored original is then read back through HostLibrary.sourceFingerprint.
import Foundation
import CryptoKit

func s10sha(_ data: Data) -> String {
    return SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
}

func s10write(_ object: [String: Any], _ url: URL) {
    if let data = try? JSONSerialization.data(withJSONObject: object, options: [.prettyPrinted, .sortedKeys]) {
        try? data.write(to: url)
    }
}

func s10pump(seconds: Double, _ condition: () -> Bool) -> Bool {
    let deadline = Date().addingTimeInterval(seconds)
    while Date() < deadline {
        if condition() { return true }
        RunLoop.main.run(until: Date().addingTimeInterval(0.05))
    }
    return condition()
}

let environment = ProcessInfo.processInfo.environment
let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
let reportURL = documents.appendingPathComponent("s10-report.json")
var report: [String: Any] = [
    "schema": 1,
    "package": "S10",
    "role": "apple",
    "platform": "ios-simulator",
    "source_sha": environment["GITHUB_SHA"] ?? "",
    "run_id": environment["GITHUB_RUN_ID"] ?? "",
    "attempt": environment["GITHUB_RUN_ATTEMPT"] ?? "",
]

func finish(_ accepted: Bool, _ code: Int32) -> Never {
    report["accepted"] = accepted
    s10write(report, reportURL)
    exit(code)
}

var inboxName = ""
let arguments = ProcessInfo.processInfo.arguments
if let index = arguments.firstIndex(of: "-S10Inbox"), index + 1 < arguments.count {
    inboxName = arguments[index + 1]
}
if inboxName.isEmpty {
    report["error"] = "missing -S10Inbox <file name>"
    finish(false, 2)
}

let inboxURL = documents.appendingPathComponent("Inbox").appendingPathComponent(inboxName)
let fileSharing = Bundle.main.object(forInfoDictionaryKey: "UIFileSharingEnabled") as? Bool ?? false
let openInPlace = Bundle.main.object(forInfoDictionaryKey: "LSSupportsOpeningDocumentsInPlace") as? Bool ?? false
guard let delivered = try? Data(contentsOf: inboxURL) else {
    report["error"] = "delivered file is missing at " + inboxURL.path
    finish(false, 3)
}
let deliveredSHA = s10sha(delivered)
report["delivery"] = [
    "method": "file placed by the computer in the app Documents container (the Files app sharing location)",
    "name": inboxName,
    "path": inboxURL.path,
    "documents": documents.path,
    "bytes": delivered.count,
    "sha256": deliveredSHA,
    "info_plist_file_sharing": fileSharing,
    "info_plist_open_in_place": openInPlace,
]

let model = HostReaderModel()
model.start()
let ready = s10pump(seconds: 180) { model.libraryReady && !model.busy }
report["baseline"] = [
    "library_ready": model.libraryReady,
    "busy": model.busy,
    "books": model.books.count,
    "status": model.statusText,
    "error": model.errorText,
]
if !ready {
    report["error"] = "the existing owner library did not become ready"
    finish(false, 4)
}

model.importFile(inboxURL)
let imported = s10pump(seconds: 300) { !model.busy && (model.books.count > 0 || !model.errorText.isEmpty) }
report["owner"] = [
    "entry": "HostReaderModel.importFile(url:) with startAccessingSecurityScopedResource",
    "finished": imported,
    "books": model.books.count,
    "status": model.statusText,
    "error": model.errorText,
]

var stored: [String: Any] = [:]
if let support = try? FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask,
                                              appropriateFor: nil, create: true) {
    let libraryURL = support.appendingPathComponent("EXReader").appendingPathComponent("library.sqlite")
    stored["library"] = libraryURL.path
    if let library = try? HostLibrary(path: libraryURL), let books = try? library.books() {
        stored["books"] = books.count
        if let match = books.first(where: { $0.formatLabel.lowercased() == "epub" }) ?? books.first {
            stored["book_id"] = match.id
            stored["title"] = match.title
            if let fingerprint = try? library.sourceFingerprint(book: match) {
                stored["format"] = fingerprint.format
                stored["sha256"] = fingerprint.sha256
                stored["bytes"] = fingerprint.bytes
            }
        }
    } else {
        stored["error"] = "library enumeration failed"
    }
}

var checks: [[String: Any]] = []
func addCheck(_ identifier: String, _ passed: Bool, _ detail: String) {
    checks.append(["id": identifier, "passed": passed, "detail": detail])
}
addCheck("delivery.files-sharing-declared", fileSharing && openInPlace,
         "UIFileSharingEnabled=" + String(fileSharing) + " LSSupportsOpeningDocumentsInPlace=" + String(openInPlace))
addCheck("delivery.file-present-in-documents", delivered.count > 0, "bytes=" + String(delivered.count))
addCheck("owner.import-finished", imported, "finished=" + String(imported))
addCheck("owner.no-owner-error", model.errorText.isEmpty, model.errorText)
addCheck("sdk.stored-source-matches-fixture",
         (stored["sha256"] as? String ?? "") == deliveredSHA, stored["sha256"] as? String ?? "no stored source")
let problems = checks.filter { ($0["passed"] as? Bool) != true }
    .map { ($0["id"] as? String ?? "") + ": " + ($0["detail"] as? String ?? "") }
report["checks"] = checks
report["stored_source"] = stored
report["problems"] = problems
report["physical_device_execution"] = false
finish(problems.isEmpty, problems.isEmpty ? 0 : 5)
