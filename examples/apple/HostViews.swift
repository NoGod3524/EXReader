// SPDX-License-Identifier: MIT
import SwiftUI
import UniformTypeIdentifiers
#if os(iOS)
import UIKit
#else
import AppKit
#endif

private func hostReadPasteboard() -> String {
#if os(iOS)
    return UIPasteboard.general.string ?? ""
#else
    return NSPasteboard.general.string(forType: .string) ?? ""
#endif
}

private func hostPasteboard(_ value: String) {
#if os(iOS)
    UIPasteboard.general.string = value
#else
    NSPasteboard.general.clearContents()
    NSPasteboard.general.setString(value, forType: .string)
#endif
}

struct HostRootView: View {
    @StateObject private var model = HostReaderModel()
    @Environment(\.scenePhase) private var phase
    private let selfTesting = CommandLine.arguments.contains("--self-test")

    private var resignPublisher: NotificationCenter.Publisher {
#if os(iOS)
        return NotificationCenter.default.publisher(for: UIApplication.didEnterBackgroundNotification)
#else
        return NotificationCenter.default.publisher(for: NSApplication.willResignActiveNotification)
#endif
    }

    var body: some View {
        Group {
            if selfTesting {
                SelfTestScreen()
            } else if model.showLibrary || model.current == nil {
                LibraryScreen(model: model)
            } else {
                ReaderScreen(model: model)
            }
        }
        .frame(minWidth: 380, minHeight: 460)
        .onAppear {
            if !selfTesting { model.start() }
        }
        .onChange(of: phase) { value in
            if value != .active && !selfTesting { model.persistNow() }
        }
        .onReceive(resignPublisher) { _ in
            if !selfTesting { model.persistNow() }
        }
    }
}

struct LibraryScreen: View {
    @ObservedObject var model: HostReaderModel
    @State private var importing = false

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("EXReader 书架").font(.title2).bold()
                    .accessibilityIdentifier("library.title")
                Spacer()
                if model.busy {
                    Text("处理中…").font(.caption)
                        .accessibilityIdentifier("library.busy")
                    Button("取消") { model.cancelWork() }
                        .accessibilityIdentifier("library.cancel")
                }
            }
            .padding(.horizontal).padding(.top, 12)

            if model.books.isEmpty {
                Spacer()
                Text("书架为空，导入一本示例书开始。")
                    .foregroundColor(.secondary)
                    .accessibilityIdentifier("library.empty")
                Spacer()
            } else {
                ScrollView {
                    LazyVStack(spacing: 8) {
                        ForEach(Array(model.books.enumerated()), id: \.element.id) { index, book in
                            Button {
                                model.openBook(book)
                            } label: {
                                HStack {
                                    VStack(alignment: .leading, spacing: 3) {
                                        Text(book.title).font(.headline)
                                        Text(book.detail).font(.caption).foregroundColor(.secondary)
                                    }
                                    Spacer()
                                    Image(systemName: "chevron.right").foregroundColor(.secondary)
                                }
                                .padding(12)
                                .background(Color.secondary.opacity(0.08))
                                .cornerRadius(10)
                            }
                            .buttonStyle(.plain)
                            .disabled(model.busy)
                            .accessibilityIdentifier("library.book.\(index)")
                            .accessibilityLabel(Text("\(book.title)，\(book.detail)"))
                        }
                    }
                    .padding(.horizontal)
                }
                .accessibilityIdentifier("library.list")
            }

            VStack(spacing: 8) {
                HStack {
                    Button("导入 EPUB 示例") { model.importFixture("Sample", extension: "epub") }
                        .accessibilityIdentifier("library.import.epub")
                    Button("再次导入同一 EPUB") { model.importFixture("Sample", extension: "epub") }
                        .accessibilityIdentifier("library.import.epub.duplicate")
                }
                HStack {
                    Button("导入 PDF 示例") { model.importFixture("Sample", extension: "pdf") }
                        .accessibilityIdentifier("library.import.pdf")
                    Button("打开文件…") { importing = true }
                        .accessibilityIdentifier("library.import.picker")
                }
                if model.showsTestFixtures {
                    HStack {
                        Button("导入损坏文件") { model.importFixture("Broken", extension: "epub") }
                            .accessibilityIdentifier("library.import.broken")
                        Button("导入大文件") { model.importFixture("Large", extension: "epub") }
                            .accessibilityIdentifier("library.import.large")
                    }
                    Button("导入 Unicode 示例") { model.importFixture("Unicode", extension: "epub") }
                        .accessibilityIdentifier("library.import.unicode")
                    Button("导入跨章示例") { model.importFixture("Bounded", extension: "epub") }
                        .accessibilityIdentifier("library.import.bounded")
                }
            }
            .buttonStyle(.bordered)
            .disabled(model.busy)
            .padding(.vertical, 8)

            Text(model.statusText).font(.caption)
                .accessibilityIdentifier("library.status")
            if !model.errorText.isEmpty {
                Text(model.errorText).font(.caption).foregroundColor(.red)
                    .accessibilityIdentifier("library.error")
            }
        }
        .fileImporter(isPresented: $importing, allowedContentTypes: [.data], allowsMultipleSelection: false) { result in
            switch result {
            case .success(let urls):
                if let url = urls.first { model.importFile(url) }
                else { model.reportImportFailure(HostError.invalidInput("文件选择器未返回文件")) }
            case .failure(let error): model.reportImportFailure(error)
            }
        }
    }
}

struct ReaderScreen: View {
    @ObservedObject var model: HostReaderModel
    @State private var showSelection = false
    @State private var showNotes = false

    var body: some View {
        VStack(spacing: 6) {
            HStack {
                Button("书架") { model.backToLibrary() }
                    .accessibilityIdentifier("reader.back")
                Text(model.title).font(.headline).lineLimit(1)
                    .accessibilityIdentifier("reader.title")
                Spacer()
                if model.busy {
                    Text("处理中…").font(.caption)
                        .accessibilityIdentifier("reader.busy")
                    Button("取消") { model.cancelWork() }
                        .accessibilityIdentifier("reader.cancel")
                }
            }
            .padding(.horizontal).padding(.top, 8)

            GeometryReader { geometry in
                ZStack {
                    Color.white
                    if let image = model.image {
                        Image(decorative: image, scale: 1)
                            .resizable()
                            .scaledToFit()
                            .frame(width: geometry.size.width, height: geometry.size.height)
                    } else {
                        Text("渲染中…").foregroundColor(.secondary)
                    }
                }
                .accessibilityElement(children: .ignore)
                .accessibilityIdentifier("reader.page")
                .accessibilityLabel(Text(model.pageAccessibilityLabel))
                .accessibilityValue(Text(model.location))
                .onAppear { model.updateViewport(geometry.size) }
                .onChange(of: geometry.size) { value in model.updateViewport(value) }
            }
            .background(Color.white)
            .padding(.horizontal, 4)

            HStack(spacing: 12) {
                Text(model.location).font(.caption)
                    .accessibilityIdentifier("reader.location")
                Text(model.progress).font(.caption)
                    .accessibilityIdentifier("reader.progress")
                Text("#\(model.stateHash)").font(.caption2).foregroundColor(.secondary)
                    .accessibilityIdentifier("reader.state")
            }

            HStack(spacing: 10) {
                Button("首页") { model.firstPage() }
                    .accessibilityIdentifier("reader.first")
                Button("上一页") { model.turn(-1) }
                    .accessibilityIdentifier("reader.previous")
                Button("下一页") { model.turn(1) }
                    .accessibilityIdentifier("reader.next")
            }
            .buttonStyle(.bordered)
            .disabled(model.busy)

            HStack(spacing: 10) {
                Button("A-") { model.changeFont(-2) }
                    .accessibilityIdentifier("reader.font.decrease")
                Text("字号 \(model.fontSize)").font(.caption)
                    .accessibilityIdentifier("reader.font.value")
                Button("A+") { model.changeFont(2) }
                    .accessibilityIdentifier("reader.font.increase")
            }
            .buttonStyle(.bordered)
            .disabled(model.busy)

            HStack(spacing: 10) {
                Button("选文") { showSelection = true }
                    .accessibilityIdentifier("reader.select")
                Button("标注 \(model.notes.count)") { showNotes = true }
                    .accessibilityIdentifier("reader.notes")
            }
            .buttonStyle(.bordered)
            .disabled(model.busy)

            Text(model.statusText).font(.caption)
                .accessibilityIdentifier("reader.status")
            if !model.errorText.isEmpty {
                Text(model.errorText).font(.caption).foregroundColor(.red)
                    .accessibilityIdentifier("reader.error")
            }
        }
        .sheet(isPresented: $showSelection) {
            SelectionSheet(model: model)
        }
        .sheet(isPresented: $showNotes) {
            NotesSheet(model: model)
        }
        .onDisappear { model.detach() }
    }
}

struct SelectionSheet: View {
    @ObservedObject var model: HostReaderModel
    @Environment(\.presentationMode) private var presentation
    @State private var selection = NSRange(location: 0, length: 0)
    @State private var lastRange = NSRange(location: 0, length: 0)
    @State private var quote = ""
    @State private var hint = "长按或用方向键选择文字"
    @State private var clipboard = ""
    @State private var context: HostSelectionContext?

    init(model: HostReaderModel) {
        self.model = model
        _context = State(initialValue: model.selectionContext)
    }

    private var isCurrent: Bool {
        guard let context else { return false }
        return model.selectionContext == context
    }

    var body: some View {
        VStack(spacing: 10) {
            Text("选择本页文字").font(.headline)
                .accessibilityIdentifier("selection.title")
            SelectableText(text: context?.text ?? "", revision: context?.frameCount ?? -1, selection: $selection)
                .frame(minHeight: 240)
                .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.secondary.opacity(0.35)))
                .disabled(!isCurrent)
            Text(quote.isEmpty ? "尚未选择文字" : quote)
                .font(.caption).lineLimit(2)
                .accessibilityIdentifier("selection.quote")
            Text(hint).font(.caption2).foregroundColor(.secondary)
                .accessibilityIdentifier("selection.hint")
            Text(clipboard.isEmpty ? "剪贴板为空" : clipboard).font(.caption2)
                .accessibilityIdentifier("selection.clipboard")
            HStack(spacing: 12) {
                Button("全选") { selection = NSRange(location: 0, length: page.length) }
                    .accessibilityIdentifier("selection.all")
                    .disabled(!isCurrent)
                Button("复制") { copySelection() }
                    .accessibilityIdentifier("selection.copy")
                    .disabled(!isCurrent)
                Button("标注所选") { annotateSelection() }
                    .accessibilityIdentifier("selection.annotate")
                    .disabled(!isCurrent)
            }
            .buttonStyle(.bordered)
            HStack(spacing: 12) {
                Button("粘贴校验") { clipboard = hostReadPasteboard() }
                    .accessibilityIdentifier("selection.verifyPaste")
                Button("关闭") { presentation.wrappedValue.dismiss() }
                    .accessibilityIdentifier("selection.close")
            }
            .buttonStyle(.bordered)
        }
        .padding()
        .onChange(of: selection) { _ in refreshQuote() }
        .onChange(of: model.selectionContext) { _ in
            guard model.selectionContext != context else { return }
            selection = NSRange(location: 0, length: 0)
            lastRange = selection
            quote = ""
            hint = "页面已变化，请关闭后重新选择文字"
        }
        .onAppear { refreshQuote() }
    }

    private var page: NSString { (context?.text ?? "") as NSString }

    private func validated(_ range: NSRange) -> NSRange {
        guard isCurrent, let context, hostSelectionUTF8Range(range, in: context.text) != nil else {
            return NSRange(location: 0, length: 0)
        }
        return range
    }

    private func effectiveRange() -> NSRange {
        let current = validated(selection)
        if current.length > 0 { return current }
        return validated(lastRange)
    }

    private func selectedText() -> String {
        let range = effectiveRange()
        guard range.length > 0 else { return "" }
        return page.substring(with: range)
    }

    private func refreshQuote() {
        let current = validated(selection)
        if current.length > 0 { lastRange = current }
        quote = selectedText()
    }

    private func byteRange() -> (Int, Int)? {
        guard isCurrent, let context,
              let bytes = hostSelectionUTF8Range(effectiveRange(), in: context.text) else { return nil }
        return (bytes.lowerBound, bytes.upperBound)
    }

    private func copySelection() {
        let text = selectedText()
        guard !text.isEmpty else {
            hint = "请先选择文字"
            return
        }
        hostPasteboard(text)
        hint = "已复制 \(text.utf8.count) 字节"
    }

    private func annotateSelection() {
        guard let context, isCurrent, let (start, end) = byteRange(), !selectedText().isEmpty else {
            hint = "请先选择文字"
            return
        }
        model.addNote(start: context.baseOffset + start, end: context.baseOffset + end,
                      comment: "摘录：\(selectedText())", expectedContext: context)
        presentation.wrappedValue.dismiss()
    }
}

struct NotesSheet: View {
    @ObservedObject var model: HostReaderModel
    @Environment(\.presentationMode) private var presentation
    @State private var editing: HostNoteRow?
    @State private var bookID: Int64?

    init(model: HostReaderModel) {
        self.model = model
        _bookID = State(initialValue: model.current?.id)
    }

    private var isCurrent: Bool { !model.busy && bookID != nil && model.current?.id == bookID }

    var body: some View {
        VStack(spacing: 10) {
            Text("标注（\(model.notes.count)）").font(.headline)
                .accessibilityIdentifier("notes.title")
            if model.notes.isEmpty {
                Text("暂无标注").foregroundColor(.secondary)
                    .accessibilityIdentifier("notes.empty")
            }
            ScrollView {
                LazyVStack(spacing: 8) {
                    ForEach(Array(model.notes.enumerated()), id: \.element.id) { index, note in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(note.quote).font(.callout).lineLimit(2)
                                .accessibilityIdentifier("notes.quote.\(index)")
                            Text(note.comment).font(.caption)
                                .accessibilityIdentifier("notes.comment.\(index)")
                            Text("状态：\(note.state)").font(.caption2)
                                .foregroundColor(note.isResolved ? .secondary : .orange)
                                .accessibilityIdentifier("notes.state.\(index)")
                            HStack(spacing: 12) {
                                Button("定位") {
                                    guard isCurrent else { return }
                                    model.jump(to: note)
                                    presentation.wrappedValue.dismiss()
                                }
                                    .accessibilityIdentifier("notes.jump.\(index)")
                                Button("编辑") {
                                    guard isCurrent else { return }
                                    editing = note
                                }
                                .accessibilityIdentifier("notes.edit.\(index)")
                                Button("删除") { if isCurrent { model.deleteNote(note) } }
                                    .accessibilityIdentifier("notes.delete.\(index)")
                            }
                            .buttonStyle(.bordered)
                            .disabled(!isCurrent)
                        }
                        .padding(8)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color.secondary.opacity(0.08))
                        .cornerRadius(8)
                    }
                }
                .padding(.horizontal)
            }
            Text(model.statusText).font(.caption)
                .accessibilityIdentifier("notes.status")
            if !model.errorText.isEmpty {
                Text(model.errorText).font(.caption).foregroundColor(.red)
                    .accessibilityIdentifier("notes.error")
            }
            Button("关闭") { presentation.wrappedValue.dismiss() }
                .accessibilityIdentifier("notes.close")
                .buttonStyle(.bordered)
        }
        .padding()
        .onChange(of: model.current?.id) { _ in editing = nil }
        .sheet(item: $editing) { note in
            EditNoteSheet(model: model, note: note)
        }
    }
}

struct EditNoteSheet: View {
    @ObservedObject var model: HostReaderModel
    let note: HostNoteRow
    @Environment(\.presentationMode) private var presentation
    @State private var draft: String
    @State private var bookID: Int64?

    init(model: HostReaderModel, note: HostNoteRow) {
        self.model = model
        self.note = note
        _draft = State(initialValue: note.comment)
        _bookID = State(initialValue: model.current?.id)
    }

    var body: some View {
        VStack(spacing: 12) {
            Text("编辑标注").font(.headline)
                .accessibilityIdentifier("notes.edit.title")
            TextField("标注内容", text: $draft)
                .textFieldStyle(.roundedBorder)
                .accessibilityIdentifier("notes.editor")
            HStack {
                Button("保存") {
                    guard !model.busy, bookID != nil, model.current?.id == bookID else { return }
                    model.updateNote(note, text: draft)
                    presentation.wrappedValue.dismiss()
                }
                .accessibilityIdentifier("notes.save")
                .disabled(model.busy || bookID == nil || model.current?.id != bookID)
                Button("取消") { presentation.wrappedValue.dismiss() }
                    .accessibilityIdentifier("notes.cancel")
            }
            .buttonStyle(.bordered)
        }
        .padding()
        .frame(minWidth: 320)
    }
}
