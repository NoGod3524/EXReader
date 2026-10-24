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

    /// Swift prints XCUIElement.ElementType as "XCUIElementType(rawValue: 48)";
    /// the contract compares stable role names, so map the documented
    /// XCUIElementType values instead of echoing a raw description.
    static func roleName(_ type: XCUIElement.ElementType) -> String {
        switch type.rawValue {
        case 0: return "Any"
        case 1: return "Other"
        case 2: return "Application"
        case 3: return "Group"
        case 4: return "Window"
        case 5: return "Sheet"
        case 7: return "Alert"
        case 8: return "Dialog"
        case 9: return "Button"
        case 10: return "RadioButton"
        case 11: return "RadioGroup"
        case 12: return "CheckBox"
        case 13: return "DisclosureTriangle"
        case 14: return "PopUpButton"
        case 15: return "ComboBox"
        case 16: return "MenuButton"
        case 17: return "ToolbarButton"
        case 18: return "Popover"
        case 19: return "Keyboard"
        case 20: return "Key"
        case 21: return "NavigationBar"
        case 22: return "TabBar"
        case 23: return "TabGroup"
        case 24: return "Toolbar"
        case 25: return "StatusBar"
        case 26: return "Table"
        case 27: return "TableRow"
        case 28: return "TableColumn"
        case 29: return "Outline"
        case 30: return "OutlineRow"
        case 31: return "Browser"
        case 32: return "CollectionView"
        case 33: return "Slider"
        case 34: return "PageIndicator"
        case 35: return "ProgressIndicator"
        case 36: return "ActivityIndicator"
        case 37: return "SegmentedControl"
        case 38: return "Picker"
        case 39: return "PickerWheel"
        case 40: return "Switch"
        case 41: return "Toggle"
        case 42: return "Link"
        case 43: return "Image"
        case 44: return "Icon"
        case 45: return "SearchField"
        case 46: return "ScrollView"
        case 47: return "ScrollBar"
        case 48: return "StaticText"
        case 49: return "TextField"
        case 50: return "SecureTextField"
        case 51: return "DatePicker"
        case 52: return "TextView"
        case 53: return "Menu"
        case 54: return "MenuItem"
        case 55: return "MenuBar"
        case 56: return "MenuBarItem"
        case 57: return "Map"
        case 58: return "WebView"
        case 59: return "IncrementArrow"
        case 60: return "DecrementArrow"
        case 61: return "Timeline"
        case 62: return "RatingIndicator"
        case 63: return "ValueIndicator"
        case 64: return "SplitGroup"
        case 65: return "Splitter"
        case 66: return "Replacement"
        case 67: return "Matte"
        case 68: return "TouchBar"
        case 69: return "StatusItem"
        case 70: return "RemoteControl"
        case 75: return "Cell"
        default: return "rawValue:" + String(type.rawValue)
        }
    }

    /// The same raw-value printing affects XCUIApplication.State, and this Xcode
    /// only exposes a subset of its members, so classify without naming them all.
    static func appStateName(_ app: XCUIApplication) -> String {
        if app.state == .runningForeground { return "runningForeground" }
        if app.state == .notRunning { return "notRunning" }
        return "other"
    }

    /// The test runner reports the iPhone idiom even when it runs on an iPad, so
    /// the workflow pins the audited platform through TEST_RUNNER_EXR_A11Y_PLATFORM
    /// (xcodebuild strips the TEST_RUNNER_ prefix for the runner process).
    static func platformName() -> String {
#if os(macOS)
        return "macos"
#else
        if let explicit = ProcessInfo.processInfo.environment["EXR_A11Y_PLATFORM"], !explicit.isEmpty {
            return explicit
        }
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
            let role = A11yAudit.roleName(node.elementType)
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
            "app_state": A11yAudit.appStateName(app),
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
                record["hittable"] = live.exists ? live.isHittable : false
            }
            elements.append(record)
        }
        var payload: [String: Any] = [
            "kind": "state",
            "platform": platform,
            "test": test,
            "step": step,
            "app_state": A11yAudit.appStateName(app),
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

    /// Records the macOS keyboard probe. Per-control focus is not observable in
    /// this Xcode (XCUIElement has no public hasFocus attribute), so the record
    /// states what WAS measured: whether Tab + Space can drive the reader at all,
    /// plus the sampled observable states. The traversal order stays uncovered
    /// instead of being invented.
    func emitKeyboard(test: String, presses: [[String: Any]], candidates: [String],
                      step: String, distinctStates: [String], changed: Bool) {
        A11yAudit.emit("EXR_A11Y_KEYBOARD", [
            "kind": "keyboard",
            "platform": platform,
            "test": test,
            "step": step,
            "presses": presses,
            "candidates": candidates,
            "probe": "Tab 16 times with Space every 4th press; the reader's observable state is sampled after each press",
            "distinct_states": distinctStates,
            "keyboard_state_changed": changed,
            "focus_observed": false,
            "focus_unobservable_reason": "本次 Xcode 的 XCUIElement 没有 hasFocus/焦点 API，逐控件焦点顺序不可观察",
        ])
    }
}
