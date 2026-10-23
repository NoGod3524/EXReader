// SPDX-License-Identifier: MIT
import SwiftUI

// Native ranges use UTF-16; the SDK uses UTF-8 byte offsets. A surrogate pair
// must remain intact on both ends, otherwise NSString would replace half of it.
func hostSelectionUTF8Range(_ range: NSRange, in text: String) -> Range<Int>? {
    let units = Array(text.utf16)
    guard range.location != NSNotFound, range.location >= 0, range.length > 0,
          range.location <= units.count, range.length <= units.count - range.location else { return nil }
    let end = range.location + range.length
    func splitsPair(_ offset: Int) -> Bool {
        offset > 0 && offset < units.count && (0xD800...0xDBFF).contains(units[offset - 1]) &&
            (0xDC00...0xDFFF).contains(units[offset])
    }
    guard !splitsPair(range.location), !splitsPair(end) else { return nil }
    let page = text as NSString
    let start = page.substring(to: range.location).utf8.count
    return start..<(start + page.substring(with: range).utf8.count)
}

#if os(iOS)
import UIKit

struct SelectableText: UIViewRepresentable {
    let text: String
    let revision: Int
    @Binding var selection: NSRange
    @Environment(\.isEnabled) private var isEnabled

    init(text: String, revision: Int, selection: Binding<NSRange>) {
        self.text = text
        self.revision = revision
        _selection = selection
    }

    func makeUIView(context: Context) -> UITextView {
        let view = UITextView()
        view.isEditable = false
        view.isSelectable = true
        view.isScrollEnabled = true
        view.alwaysBounceVertical = true
        view.autocorrectionType = .no
        view.autocapitalizationType = .none
        view.spellCheckingType = .no
        view.smartQuotesType = .no
        view.smartDashesType = .no
        view.font = UIFont.preferredFont(forTextStyle: .body)
        view.textContainerInset = UIEdgeInsets(top: 10, left: 10, bottom: 10, right: 10)
        view.text = text
        view.delegate = context.coordinator
        view.accessibilityIdentifier = "selection.text"
        view.accessibilityLabel = "本页文字"
        return view
    }

    func updateUIView(_ view: UITextView, context: Context) {
        let changed = context.coordinator.parent.text != text || context.coordinator.parent.revision != revision ||
            context.coordinator.enabled != isEnabled
        if changed { context.coordinator.generation += 1 }
        let requested = context.coordinator.requestedSelection != selection
        let nativeEcho = context.coordinator.publishedSelection == selection
        if nativeEcho || changed { context.coordinator.publishedSelection = nil }
        context.coordinator.requestedSelection = selection
        context.coordinator.parent = self
        context.coordinator.enabled = isEnabled
        context.coordinator.updating = true
        defer { context.coordinator.updating = false }
        if view.isSelectable != isEnabled { view.isSelectable = isEnabled }
        if view.isUserInteractionEnabled != isEnabled { view.isUserInteractionEnabled = isEnabled }
        if changed || view.text != text {
            view.text = text
            view.selectedRange = NSRange(location: 0, length: 0)
        } else if requested && !nativeEcho && view.selectedRange != selection {
            // A native gesture can change selectedRange before its deferred
            // Binding callback. Unrelated redraws must not restore the old range.
            context.coordinator.selectionEvent += 1
            view.selectedRange = selection
        }
    }

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    final class Coordinator: NSObject, UITextViewDelegate {
        var parent: SelectableText
        var generation = 0
        var updating = false
        var enabled: Bool
        var requestedSelection: NSRange
        var publishedSelection: NSRange?
        var selectionEvent = 0

        init(_ parent: SelectableText) {
            self.parent = parent
            enabled = parent.isEnabled
            requestedSelection = parent.selection
        }

        func textViewDidChangeSelection(_ textView: UITextView) {
            guard !updating else { return }
            let range = textView.selectedRange
            let expected = parent, generation = self.generation
            selectionEvent += 1
            let event = selectionEvent
            guard parent.selection != range else { return }
            DispatchQueue.main.async { [weak self, weak textView] in
                guard let self, let textView, self.enabled, event == self.selectionEvent,
                      generation == self.generation,
                      self.parent.revision == expected.revision, self.parent.text == expected.text,
                      textView.text == expected.text, textView.selectedRange == range else { return }
                let valid = range.length == 0 || hostSelectionUTF8Range(range, in: expected.text) != nil
                self.publishedSelection = valid ? range : nil
                expected.selection = valid ? range : NSRange(location: 0, length: 0)
            }
        }

        func textView(_ textView: UITextView, shouldChangeTextIn range: NSRange,
                      replacementText text: String) -> Bool {
            false
        }
    }
}
#else
import AppKit

struct SelectableText: NSViewRepresentable {
    let text: String
    let revision: Int
    @Binding var selection: NSRange
    @Environment(\.isEnabled) private var isEnabled

    init(text: String, revision: Int, selection: Binding<NSRange>) {
        self.text = text
        self.revision = revision
        _selection = selection
    }

    func makeNSView(context: Context) -> NSScrollView {
        let scroll = NSTextView.scrollableTextView()
        guard let view = scroll.documentView as? NSTextView else { return scroll }
        view.isEditable = false
        view.isSelectable = true
        view.isRichText = false
        view.drawsBackground = true
        view.font = NSFont.systemFont(ofSize: 15)
        view.textContainerInset = NSSize(width: 10, height: 10)
        view.string = text
        view.delegate = context.coordinator
        view.setAccessibilityIdentifier("selection.text")
        view.setAccessibilityLabel("本页文字")
        return scroll
    }

    func updateNSView(_ scroll: NSScrollView, context: Context) {
        let changed = context.coordinator.parent.text != text || context.coordinator.parent.revision != revision ||
            context.coordinator.enabled != isEnabled
        if changed { context.coordinator.generation += 1 }
        let requested = context.coordinator.requestedSelection != selection
        let nativeEcho = context.coordinator.publishedSelection == selection
        if nativeEcho || changed { context.coordinator.publishedSelection = nil }
        context.coordinator.requestedSelection = selection
        context.coordinator.parent = self
        context.coordinator.enabled = isEnabled
        guard let view = scroll.documentView as? NSTextView else { return }
        context.coordinator.updating = true
        defer { context.coordinator.updating = false }
        if view.isSelectable != isEnabled { view.isSelectable = isEnabled }
        if changed || view.string != text {
            view.string = text
            view.setSelectedRange(NSRange(location: 0, length: 0))
        } else if requested && !nativeEcho && view.selectedRange() != selection {
            context.coordinator.selectionEvent += 1
            view.setSelectedRange(selection)
        }
    }

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    final class Coordinator: NSObject, NSTextViewDelegate {
        var parent: SelectableText
        var generation = 0
        var updating = false
        var enabled: Bool
        var requestedSelection: NSRange
        var publishedSelection: NSRange?
        var selectionEvent = 0

        init(_ parent: SelectableText) {
            self.parent = parent
            enabled = parent.isEnabled
            requestedSelection = parent.selection
        }

        func textViewDidChangeSelection(_ notification: Notification) {
            guard !updating, let view = notification.object as? NSTextView else { return }
            let range = view.selectedRange()
            let expected = parent, generation = self.generation
            selectionEvent += 1
            let event = selectionEvent
            guard parent.selection != range else { return }
            DispatchQueue.main.async { [weak self, weak view] in
                guard let self, let view, self.enabled, event == self.selectionEvent,
                      generation == self.generation,
                      self.parent.revision == expected.revision, self.parent.text == expected.text,
                      view.string == expected.text, view.selectedRange() == range else { return }
                let valid = range.length == 0 || hostSelectionUTF8Range(range, in: expected.text) != nil
                self.publishedSelection = valid ? range : nil
                expected.selection = valid ? range : NSRange(location: 0, length: 0)
            }
        }
    }
}
#endif
