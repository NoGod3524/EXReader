// SPDX-License-Identifier: MIT
import Foundation
import CReaderProduct

@main struct AccountTerminalReview {
    static func main() throws {
        let root = CommandLine.arguments[1]
        let base = URL(fileURLWithPath: CommandLine.arguments[2], isDirectory: true)
        let migration = URL(fileURLWithPath: CommandLine.arguments[3])
        let password = ProcessInfo.processInfo.environment["READER_ACCOUNT_TEST_PASSWORD"]!
        let valid = Data(("Basic " + Data(("reader:" + password).utf8).base64EncodedString()).utf8)
        let invalid = Data("Basic aW52YWxpZDppbnZhbGlk".utf8)

        func wait(_ seconds: TimeInterval = 180, _ ready: () -> Bool) -> Bool {
            let deadline = Date().addingTimeInterval(seconds)
            while Date() < deadline {
                if ready() { return true }
                RunLoop.current.run(until: Date().addingTimeInterval(0.05))
            }
            return ready()
        }
        func check(_ value: Bool, _ name: String) throws {
            guard value else { throw HostError.invalidResult(name) }
            print("PASS \(name)")
        }
        func run(_ name: String, authorization: Data, cancel: Bool,
                 expected: String, expectedState: reader_session_state, callbacks: Int) throws {
            let directory = base.appendingPathComponent(name, isDirectory: true)
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            let queue = DispatchQueue(label: "terminal-review." + name)
            try queue.sync {
                let catalog = try HostCatalog(path: directory.appendingPathComponent("reader-catalog.db"),
                                              migrationURL: migration, ownerQueue: queue)
                try catalog.close()
            }
            let profile = HostAccountProfile(id: UUID().uuidString.lowercased(), root: root)
            let session = HostAccountSession()
            var called = 0
            var terminals: [reader_session_state] = []
            try session.start(profile: profile, directory: directory, authorization: authorization,
                              terminal: { terminals.append($0) }) { called += 1 }
            if cancel { session.cancel() }
            try check(wait { !session.running && session.state == expected }, name + " terminal state")
            try check(!session.message.isEmpty, name + " terminal message")
            try check(called == callbacks, name + " completion callback")
            try check(terminals == [expectedState], name + " actual terminal callback")
            if cancel {
                try session.start(profile: profile, directory: directory, authorization: authorization,
                                  terminal: { terminals.append($0) }) { called += 1 }
                try check(wait { !session.running && session.state == "本轮扫描完成" }, "cancelled session retries")
                try check(terminals == [READER_SESSION_CANCELLED, READER_SESSION_FINISHED] && called == 1,
                          "retry delivers exactly one successful completion")
            }
            session.close()
            try check(wait(30) { session.state == "已关闭" }, name + " closes")
        }
        try run("finished", authorization: valid, cancel: false, expected: "本轮扫描完成", expectedState: READER_SESSION_FINISHED, callbacks: 1)
        try run("cancelled", authorization: valid, cancel: true, expected: "已取消", expectedState: READER_SESSION_CANCELLED, callbacks: 0)
        try run("failed", authorization: invalid, cancel: false, expected: "同步失败", expectedState: READER_SESSION_FAILED, callbacks: 0)
        let preparation = HostAccountSession()
        var cancelled = false
        try preparation.beginPreparation { cancelled = true }
        preparation.cancel()
        try check(cancelled && preparation.state == "正在取消", "preparation cancellation requested")
        preparation.preparationStopped(cancelled: true)
        try check(!preparation.preparing && preparation.state == "已取消" && !preparation.message.isEmpty,
                  "preparation cancellation settles")
        try preparation.beginPreparation { }
        preparation.preparationStopped(cancelled: false, detail: "fixture failure")
        try check(preparation.state == "同步失败" && preparation.message.contains("fixture failure"),
                  "preparation failure is visible")
    }
}
