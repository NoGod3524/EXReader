// SPDX-License-Identifier: MIT
// Minimal system picker glue. It only delivers the URLs the user chose; the
// host passes them to FileEntryStagingArea.stageInBackground immediately, while
// their security scope is still valid. No copying happens on the main thread.
import Foundation
#if canImport(UniformTypeIdentifiers)
import UniformTypeIdentifiers
#endif

#if canImport(UniformTypeIdentifiers)
public enum FileEntryTypes {
    /// Content types of the nine formats. Unknown extensions fall back to
    /// .data so the picker never hides a file the SDK might accept.
    public static var openTypes: [UTType] {
        var types: [UTType] = []
        for hint in FileFormatHint.allCases {
            if let type = UTType(filenameExtension: hint.rawValue), !types.contains(type) { types.append(type) }
        }
        for type in [UTType.pdf, UTType.plainText, UTType.html, UTType.rtf, UTType.data] where !types.contains(type) {
            types.append(type)
        }
        return types
    }
}
#endif

#if os(iOS)
import UIKit
import ObjectiveC

private var pickerRetainKey: UInt8 = 0

/// UIDocumentPickerViewController wrapper. The URLs are security scoped and
/// not copies (asCopy is false), so the scope pairing is done by the staging
/// area, not here.
public final class FileEntryPicker: NSObject, UIDocumentPickerDelegate {
    private let completion: ([URL]) -> Void

    private init(completion: @escaping ([URL]) -> Void) {
        self.completion = completion
    }

    /// `completion` runs on the main thread with the chosen URLs (empty when the
    /// user cancelled). The picker retains itself until then.
    public static func present(from presenter: UIViewController, allowsMultipleSelection: Bool = true,
                               completion: @escaping ([URL]) -> Void) {
        let controller = UIDocumentPickerViewController(forOpeningContentTypes: FileEntryTypes.openTypes, asCopy: false)
        controller.allowsMultipleSelection = allowsMultipleSelection
        let delegate = FileEntryPicker(completion: completion)
        controller.delegate = delegate
        objc_setAssociatedObject(controller, &pickerRetainKey, delegate, .OBJC_ASSOCIATION_RETAIN_NONATOMIC)
        presenter.present(controller, animated: true)
    }

    public func documentPicker(_ controller: UIDocumentPickerViewController, didPickDocumentsAt urls: [URL]) {
        completion(urls)
    }

    public func documentPickerWasCancelled(_ controller: UIDocumentPickerViewController) {
        completion([])
    }
}
#elseif os(macOS)
import AppKit

public enum FileEntryPicker {
    /// Shows an NSOpenPanel as a sheet on `window` (or modeless without one).
    /// `completion` runs on the main thread; empty when cancelled.
    public static func present(from window: NSWindow?, allowsMultipleSelection: Bool = true,
                               completion: @escaping ([URL]) -> Void) {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = allowsMultipleSelection
        panel.allowedContentTypes = FileEntryTypes.openTypes
        let finish: (NSApplication.ModalResponse) -> Void = { response in
            completion(response == .OK ? panel.urls : [])
        }
        if let window = window {
            panel.beginSheetModal(for: window, completionHandler: finish)
        } else {
            panel.begin(completionHandler: finish)
        }
    }
}
#endif
