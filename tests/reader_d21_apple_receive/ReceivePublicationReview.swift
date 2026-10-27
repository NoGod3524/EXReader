// SPDX-License-Identifier: MIT
import Foundation

// Deterministic main-queue ordering against the real product model methods.
// The HTTPS owner/UI suites separately exercise actual projection and import.
@main struct ReceivePublicationReview {
    static func main() {
        do { try run() }
        catch { fputs("D21 receive publication failed: \(error)\n", stderr); exit(1) }
    }
    static func run() throws {
        let model = HostReaderModel()
        var checks: [String] = []
        func check(_ name: String, _ condition: @autoclosure () -> Bool) throws {
            guard condition() else { throw HostError.invalidResult(name) }
            checks.append(name); print("PASS " + name)
        }
        // Owner has already committed its page and queued a successful callback.
        let cancelled = model.beginReceivePublication()
        var delivered = false
        DispatchQueue.main.async {
            model.finishReceivePublication(cancel: cancelled, message: "已接收 1 本")
            delivered = true
        }
        model.cancelReceive()
        try check("cancel_immediately_visible", model.receiveMessage.contains("接收已取消"))
        try check("cancel_does_not_release_owner_early", model.syncPreparing)
        let cancelledRevision = model.receivedShelfRevision
        let deadline = Date().addingTimeInterval(10)
        while !delivered && Date() < deadline { RunLoop.current.run(until: Date().addingTimeInterval(0.01)) }
        try check("queued_success_delivered", delivered)
        try check("queued_success_preserves_cancel_state", model.receiveMessage.contains("接收已取消") && !model.syncPreparing)
        try check("committed_shelf_refreshed_after_cancel", model.receivedShelfRevision > cancelledRevision)
        let next = model.beginReceivePublication()
        let revision = model.receivedShelfRevision
        model.finishReceivePublication(cancel: cancelled, message: "过期成功")
        model.finishReceivePublication(cancel: cancelled, message: "过期失败")
        try check("obsolete_callbacks_do_not_clear_new_owner", model.syncPreparing && model.receiveMessage == "正在接收书架…")
        try check("obsolete_callbacks_do_not_publish_shelf", model.receivedShelfRevision == revision)
        model.finishReceivePublication(cancel: next, message: "已接收 2 本")
        try check("new_receive_publishes_normally", !model.syncPreparing && model.receiveMessage == "已接收 2 本")
        let failed = model.beginReceivePublication()
        model.finishReceivePublication(cancel: failed, message: "真实接收失败")
        try check("failure_visible_and_retryable", !model.syncPreparing && model.receiveMessage == "真实接收失败")
        let closing = model.beginReceivePublication()
        model.closeAccountSession()
        let closedMessage = model.receiveMessage, closedRevision = model.receivedShelfRevision
        model.finishReceivePublication(cancel: closing, message: "已关闭账号的迟到结果")
        try check("closed_account_callback_discarded", model.receiveMessage == closedMessage && model.receivedShelfRevision == closedRevision)
        let env = ProcessInfo.processInfo.environment
        let result: [String: Any] = ["source_sha": env["GITHUB_SHA"]!, "run_id": env["GITHUB_RUN_ID"]!,
            "attempt": env["GITHUB_RUN_ATTEMPT"]!, "accepted": true, "checks": checks]
        try JSONSerialization.data(withJSONObject: result, options: [.prettyPrinted]).write(to: URL(fileURLWithPath: CommandLine.arguments[1]))
    }
}
