// SPDX-License-Identifier: MIT
// G16 Apple accessibility audit instrumentation.
//
// This file only observes the shipped host: it dumps the accessibility tree,
// geometry, state exposure and text-size metrics of each audited step. Nothing
// here changes HostModel/HostViews/HostCatalog/HostSDK. The cloud gate compares
// every record against tests/reader_a11y_apple/a11y_contract.json.
import XCTest
#if os(iOS)
import UIKit
#else
import AppKit
#endif

enum A11yAudit {
    /// Element types that carry a control affordance. They are the only nodes
    /// for which hit testing and (on macOS) keyboard focus are queried, because
    /// a lazy XCUITest query per static text would dominate the audit budget.
    static let interactiveRoles: Set<String> = [
        "Button", "Link", "TextField", "TextView", "Cell", "SegmentedControl",
        "Slider", "Toggle", "SearchField", "PickerWheel",
    ]

    static func platformName() -> String {
#if os(macOS)
        return "macos"
#else
        return UIDevice.current.userInterfaceIdiom == .pad ? "ipad" : "iphone"
#endif
    }

    static func frameJSON(_ rect: CGRect) -> [String: Double] {
        return ["x": Double(rect.origin.x), "y": Double(rect.origin.y),
                "width": Double(rect.size.width), "height": Double(rect.size.height)]
    }

    static func emit(_ tag: String, _ payload: [String: Any]) {
        guard JSONSerialization.isValidJSONObject(payload),
              let data = try? JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys]),
              let text = String(data: data, encoding: .utf8) else {
            print(tag + " {\"invalid\":true}")
            return
        }
        print(tag + " " + text)
    }

    /// The test bundle runs in its own process, but that process is a normal app
    /// on the same device, so its preferred text-style sizes follow the same
    /// content size category the host app resolves. Recording the point sizes
    /// makes the Dynamic Type fixture auditable instead of assumed.
    static func textMetrics() -> [String: Double] {
#if os(iOS)
        return ["caption1_pt": Double(UIFont.preferredFont(forTextStyle: .caption1).pointSize),
                "body_pt": Double(UIFont.preferredFont(forTextStyle: .body).pointSize),
                "headline_pt": Double(UIFont.preferredFont(forTextStyle: .headline).pointSize)]
#else
        return ["caption1_pt": Double(NSFont.preferredFont(forTextStyle: .caption1).pointSize),
                "body_pt": Double(NSFont.preferredFont(forTextStyle: .body).pointSize),
                "headline_pt": Double(NSFont.preferredFont(forTextStyle: .headline).pointSize)]
#endif
    }

    static func orientation() -> String {
#if os(iOS)
        switch XCUIDevice.shared.orientation {
        case .portrait: return "portrait"
        case .portraitUpsideDown: return "portraitUpsideDown"
        case .landscapeLeft: return "landscapeLeft"
        case .landscapeRight: return "landscapeRight"
        default: return "unknown"
        }
#else
        return "macos-window"
#endif
    }
}

/// Collects one record per audited step and prints it with a stable tag so the
/// Actions collector can bind each record to this run and attempt.
final class A11yAuditRecorder {
    let platform = A11yAudit.platformName()
    private(set) var captured: [String] = []
    private(set) var failures: [String] = []

    struct Node {
        let role: String
        let identifier: String
        let label: String
        let value: String
        let frame: CGRect
        let enabled: Bool
        let order: Int
        let path: String
    }

    static func flatten(_ root: XCUIElementSnapshot) -> (nodes: [Node], window: CGRect) {
        var nodes: [Node] = []
        var window = root.frame
        var sawWindow = false
        var index = 0
        func visit(_ node: XCUIElementSnapshot, _ ancestors: [String]) {
            let role = String(describing: node.elementType)
            let identifier = node.identifier
            if !sawWindow, node.elementType == .window, !node.frame.isEmpty {
                window = node.frame
                sawWindow = true
            }
            let token = identifier.isEmpty ? role : role + "[" + identifier + "]"
            let path = (ancestors + [token]).joined(separator: ">")
            let value = (node.value as? String) ?? ""
            // Keep the record bounded: identified nodes are always kept, plus
            // anonymous controls and anonymous static text so reading order and
            // unnamed-control counts stay observable.
            let keep = !identifier.isEmpty
                || A11yAudit.interactiveRoles.contains(role)
                || (role == "StaticText" && !node.label.isEmpty)
            if keep && nodes.count < 240 {
                nodes.append(Node(role: role, identifier: identifier, label: node.label,
                                  value: value, frame: node.frame, enabled: node.isEnabled,
                                  order: index, path: path))
                index += 1
            }
            let next = ancestors.count < 10 ? ancestors + [token] : ancestors
            for child in node.children { visit(child, next) }
        }
        visit(root, [])
        return (nodes, window)
    }

    func environment(_ app: XCUIApplication) -> [String: Any] {
        var facts: [String: Any] = [
            "kind": "environment",
            "platform": platform,
            "os": ProcessInfo.processInfo.operatingSystemVersionString,
            "app_state": String(describing: app.state),
            "launch_arguments": app.launchArguments,
            "metrics": A11yAudit.textMetrics(),
            "orientation": A11yAudit.orientation(),
        ]
#if os(iOS)
        facts["device"] = UIDevice.current.model
        facts["idiom"] = String(describing: UIDevice.current.userInterfaceIdiom)
        facts["screen_scale"] = Double(UIScreen.main.scale)
        facts["screen_points"] = [Double(UIScreen.main.bounds.width), Double(UIScreen.main.bounds.height)]
#else
        facts["device"] = "mac"
#endif
        return facts
    }

    func emitEnvironment(_ app: XCUIApplication) {
        A11yAudit.emit("EXR_A11Y_ENV", environment(app))
    }

    /// Capture one audited step. Returns false when the accessibility tree is
    /// unavailable, which the caller turns into an audit precondition failure.
    @discardableResult
    func capture(_ app: XCUIApplication, test: String, step: String,
                 screenshot: String? = nil, detail: [String: Any] = [:],
                 attach: ((XCTAttachment) -> Void)? = nil) -> Bool {
        guard let snapshot = try? app.snapshot() else {
            failures.append("snapshot-unavailable:" + step)
            A11yAudit.emit("EXR_A11Y_ERROR", ["platform": platform, "test": test, "step": step,
                                              "error": "snapshot-unavailable"])
            return false
        }
        let flat = Self.flatten(snapshot)
        var elements: [[String: Any]] = []
        var anonymousControls = 0
        for node in flat.nodes {
            if node.identifier.isEmpty {
                if A11yAudit.interactiveRoles.contains(node.role) { anonymousControls += 1 }
                continue
            }
            var record: [String: Any] = [
                "id": node.identifier,
                "role": node.role,
                "label": node.label,
                "value": String(node.value.prefix(400)),
                "frame": A11yAudit.frameJSON(node.frame),
                "enabled": node.enabled,
                "order": node.order,
                "path": node.path,
            ]
            if A11yAudit.interactiveRoles.contains(node.role) {
                let live = app.descendants(matching: .any).matching(identifier: node.identifier).firstMatch
                let present = live.exists
                record["hittable"] = present ? live.isHittable : false
#if os(macOS)
                record["focus"] = present ? live.hasFocus : false
#endif
            }
            elements.append(record)
        }
        var payload: [String: Any] = [
            "kind": "state",
            "platform": platform,
            "test": test,
            "step": step,
            "app_state": String(describing: app.state),
            "orientation": A11yAudit.orientation(),
            "window": A11yAudit.frameJSON(flat.window),
            "metrics": A11yAudit.textMetrics(),
            "launch_arguments": app.launchArguments,
            "anonymous_controls": anonymousControls,
            "element_count": elements.count,
            "screenshot": screenshot ?? "",
            "elements": elements,
        ]
        if !detail.isEmpty { payload["detail"] = detail }
        A11yAudit.emit("EXR_A11Y_STATE", payload)

        if let screenshot, let attach {
            let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
            attachment.name = screenshot
            attachment.lifetime = .keepAlways
            attach(attachment)
        }
        if let attach,
           let data = try? JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys, .prettyPrinted]),
           let text = String(data: data, encoding: .utf8) {
            let attachment = XCTAttachment(string: text)
            attachment.name = "a11y-state-" + step + ".json"
            attachment.lifetime = .keepAlways
            attach(attachment)
        }
        captured.append(step)
        return true
    }

    /// Records the macOS keyboard traversal path. The sequence is emitted as its
    /// own record type so a platform without keyboard coverage simply has none.
    func emitKeyboard(test: String, presses: [[String: Any]], candidates: [String], step: String) {
        var focused: [String] = []
        for press in presses {
            if let ids = press["focused"] as? [String] { focused.append(contentsOf: ids) }
        }
        let reachable = Array(Set(focused)).sorted()
        A11yAudit.emit("EXR_A11Y_KEYBOARD", [
            "kind": "keyboard",
            "platform": platform,
            "test": test,
            "step": step,
            "presses": presses,
            "candidates": candidates,
            "focused_union": reachable,
            "focus_observed": !reachable.isEmpty,
        ])
    }
}
