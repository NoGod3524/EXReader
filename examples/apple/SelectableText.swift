// SPDX-License-Identifier: MIT
import SwiftUI

#if os(iOS)
import UIKit

struct SelectableText: UIViewRepresentable {
    let text: String
    @Binding var selection: NSRange

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
        context.coordinator.parent = self
        if view.text != text {
            view.text = text
            view.selectedRange = NSRange(location: 0, length: 0)
        }
    }

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    final class Coordinator: NSObject, UITextViewDelegate {
        var parent: SelectableText

        init(_ parent: SelectableText) { self.parent = parent }

        func textViewDidChangeSelection(_ textView: UITextView) {
            let range = textView.selectedRange
            guard parent.selection != range else { return }
            DispatchQueue.main.async { self.parent.selection = range }
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
    @Binding var selection: NSRange

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
        context.coordinator.parent = self
        guard let view = scroll.documentView as? NSTextView else { return }
        if view.string != text { view.string = text }
    }

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    final class Coordinator: NSObject, NSTextViewDelegate {
        var parent: SelectableText

        init(_ parent: SelectableText) { self.parent = parent }

        func textViewDidChangeSelection(_ notification: Notification) {
            guard let view = notification.object as? NSTextView else { return }
            let range = view.selectedRange()
            guard parent.selection != range else { return }
            DispatchQueue.main.async { self.parent.selection = range }
        }
    }
}
#endif
