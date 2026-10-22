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
        view.isEditable = true
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
        // Keep hardware-keyboard selection testable without a software keyboard covering the actions.
        view.inputView = UIView(frame: CGRect(x: 0, y: 0, width: 1, height: 1))
        view.text = text
        view.delegate = context.coordinator
        view.accessibilityIdentifier = "selection.text"
        view.accessibilityLabel = "本页文字"
        return view
    }

    func updateUIView(_ view: UITextView, context: Context) {
        let changed = context.coordinator.parent.text != text || context.coordinator.parent.revision != revision ||
            context.coordinator.parent.isEnabled != isEnabled
        if changed { context.coordinator.generation += 1 }
        context.coordinator.parent = self
        context.coordinator.updating = true
        defer { context.coordinator.updating = false }
        view.isSelectable = isEnabled
        view.isUserInteractionEnabled = isEnabled
        if changed || view.text != text {
            view.text = text
            view.selectedRange = NSRange(location: 0, length: 0)
        } else if view.selectedRange != selection {
            view.selectedRange = selection
        }
    }

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    final class Coordinator: NSObject, UITextViewDelegate {
        var parent: SelectableText
        var generation = 0
        var updating = false

        init(_ parent: SelectableText) { self.parent = parent }

        func textViewDidChangeSelection(_ textView: UITextView) {
            guard !updating else { return }
            let range = textView.selectedRange
            let expected = parent, generation = self.generation
            guard parent.selection != range else { return }
            DispatchQueue.main.async { [weak self, weak textView] in
                guard let self, let textView, expected.isEnabled, self.parent.isEnabled,
                      generation == self.generation,
                      self.parent.revision == expected.revision, self.parent.text == expected.text,
                      textView.text == expected.text else { return }
                expected.selection = range.length == 0 || hostSelectionUTF8Range(range, in: expected.text) != nil
                    ? range : NSRange(location: 0, length: 0)
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
            context.coordinator.parent.isEnabled != isEnabled
        if changed { context.coordinator.generation += 1 }
        context.coordinator.parent = self
        guard let view = scroll.documentView as? NSTextView else { return }
        context.coordinator.updating = true
        defer { context.coordinator.updating = false }
        view.isSelectable = isEnabled
        if changed || view.string != text {
            view.string = text
            view.setSelectedRange(NSRange(location: 0, length: 0))
        } else if view.selectedRange() != selection { view.setSelectedRange(selection) }
    }

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    final class Coordinator: NSObject, NSTextViewDelegate {
        var parent: SelectableText
        var generation = 0
        var updating = false

        init(_ parent: SelectableText) { self.parent = parent }

        func textViewDidChangeSelection(_ notification: Notification) {
            guard !updating, let view = notification.object as? NSTextView else { return }
            let range = view.selectedRange()
            let expected = parent, generation = self.generation
            guard parent.selection != range else { return }
            DispatchQueue.main.async { [weak self, weak view] in
                guard let self, let view, expected.isEnabled, self.parent.isEnabled,
                      generation == self.generation,
                      self.parent.revision == expected.revision, self.parent.text == expected.text,
                      view.string == expected.text else { return }
                expected.selection = range.length == 0 || hostSelectionUTF8Range(range, in: expected.text) != nil
                    ? range : NSRange(location: 0, length: 0)
            }
        }
    }
}
#endif
