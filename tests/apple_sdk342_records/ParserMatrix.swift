// SPDX-License-Identifier: MIT
// Prepared for the future production-policy acceptance run; not executed yet.
import Foundation
import CEXReader

@main struct ParserMatrix {
    static func main() throws {
        guard ProcessInfo.processInfo.environment["GITHUB_ACTIONS"] == "true" else { throw HostError.invalidInput("Actions only") }
        let actual = String(cString: exr_version())
        guard actual == "3.41.0" || actual == "3.42.0" else { throw HostError.invalidInput("Unexpected installed SDK") }
        let old = ["3.40.0", "exreader-sdk-3.40.0", "3.41.0", "exreader-sdk-3.41.0"]
        let current = ["3.42.0", "exreader-sdk-3.42.0"]
        let invalid = ["", "3.40.1", "exreader-sdk-3.40.1", "3.41.1", "3.42.1", "3.43.0",
                       "exreader-sdk-3.43.0", "exreader-sdk-exreader-sdk-3.41.0", "exreader-3.41.0",
                       "3.42", "3.42.0 ", " 3.42.0", "3.42.0\u{0}", "v3.42.0"]
        for value in old {
            guard HostReadingWorker.acceptsParser(value) else { throw HostError.invalidResult("Known prior tag rejected: \(value)") }
        }
        for value in current {
            guard HostReadingWorker.acceptsParser(value) == (actual == "3.42.0") else {
                throw HostError.invalidResult("Current/future tag policy differs: \(value)")
            }
        }
        for value in invalid {
            guard !HostReadingWorker.acceptsParser(value) else { throw HostError.invalidResult("Unregistered parser accepted: \(value)") }
        }
        print("APPLE_PARSER_MATRIX sdk=\(actual) known=\(old.count + current.count) invalid=\(invalid.count)")
    }
}
