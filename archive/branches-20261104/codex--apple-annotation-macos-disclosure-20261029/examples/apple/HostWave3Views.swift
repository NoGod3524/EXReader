// SPDX-License-Identifier: MIT
import SwiftUI
import UniformTypeIdentifiers
import Darwin
#if os(iOS)
import UIKit
#else
import AppKit
#endif

#if EXR_APPLE_WAVE3 && EXR_APPLE_RAW3
// The sheet only presents owner snapshots. Every module operation goes back to
// HostReaderModel's serialized owner; opening this view never starts a sync.
struct HostWave3Actions {
    let refresh: () -> Void
    let previewAnnotations: (URL) -> Void
    let confirmAnnotations: () -> Void
    let discardPreview: () -> Void
    let importFont: (URL) -> Void
    let selectFont: (String?) -> Void
    let exportAnnotations: (URL, Bool) -> Void
    let exportOriginal: (URL) -> Void
    let back: () -> Void
    let forward: () -> Void
    let cancel: () -> Void
#if EXR_APPLE_HOST_REVIEW
    var reviewAnnotations: ((Bool) -> Void)? = nil
    var reviewSnapshot: (() -> Void)? = nil
#endif
}

struct HostWave3Sheet: View {
    @ObservedObject var state: HostWave3State
    let ownerBusy: Bool
    let actions: HostWave3Actions
    @Environment(\.presentationMode) private var presentation
    @State private var choosing = false
    @State private var choice = Choice.annotations
    @State private var pickerError = ""
    @State private var selectedInput = ""
#if EXR_APPLE_HOST_REVIEW
    @State private var previewExportWhenReady = false
    @State private var previousExportURL: URL?
    @State private var reviewOriginalDirectory: URL?
    @State private var lockedReviewDirectory: URL?
    @State private var reviewPickerFile: URL?
    @State private var reviewPickerDirectory: URL?
    @State private var reviewExportCheck = ""
#endif

    private enum Choice {
        case annotations, font, original, jsonl, markdown
        var directory: Bool {
            switch self { case .original, .jsonl, .markdown: return true; default: return false }
        }
    }

    var body: some View {
        VStack(spacing: 12) {
            HStack(alignment: .firstTextBaseline) {
                Text("阅读详情").font(.headline).accessibilityAddTraits(.isHeader)
                    .accessibilityIdentifier("features.title")
                Spacer()
                Button("关闭") { presentation.wrappedValue.dismiss() }
                    .accessibilityIdentifier("features.close")
            }
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    originalSection
                    annotationSection
                    fontSection
                    historySection
                    syncSection
#if EXR_APPLE_HOST_REVIEW
                    if UserDefaults.standard.bool(forKey: "EXRUITestFixtures") { reviewSection }
#endif
                }.frame(maxWidth: .infinity, alignment: .leading)
            }.accessibilityIdentifier("features.scroll")
            if !pickerError.isEmpty {
                Text(pickerError).font(.caption).foregroundColor(.red)
                    .accessibilityIdentifier("features.picker.error")
            }
            Text(state.message).font(.caption).frame(maxWidth: .infinity, alignment: .leading)
                .accessibilityIdentifier("features.status")
            if let url = state.exportURL {
                HostWave3ShareButton(url: url).disabled(state.busy)
            }
            HStack {
                Button("刷新详情", action: actions.refresh).disabled(state.busy || ownerBusy)
                    .accessibilityIdentifier("features.refresh")
                Spacer()
                if state.busy {
                    ProgressView().controlSize(.small)
                    Button("取消", action: actions.cancel).accessibilityIdentifier("features.cancel")
                }
            }.buttonStyle(.bordered)
        }
        .padding().frame(minWidth: 280, minHeight: 360)
#if os(macOS)
        .frame(idealWidth: 500, idealHeight: 620)
#endif
#if EXR_APPLE_HOST_REVIEW
        .onChange(of: state.busy) { busy in
            if !busy, let directory = lockedReviewDirectory {
                try? FileManager.default.setAttributes([.posixPermissions: NSNumber(value: 0o700)], ofItemAtPath: directory.path)
                lockedReviewDirectory = nil
            }
            if !busy && previewExportWhenReady {
                previewExportWhenReady = false
                if let url = state.exportURL, url != previousExportURL {
                    selectedInput = url.lastPathComponent
                    actions.previewAnnotations(url)
                }
            }
        }
#endif
        .fileImporter(isPresented: $choosing,
                      allowedContentTypes: choice.directory ? [.folder] : [.data],
                      allowsMultipleSelection: false) { result in
            switch result {
            case .success(let urls):
                guard let url = urls.first else { return }
                pickerError = ""
                switch choice {
                case .annotations: selectedInput = url.lastPathComponent; actions.previewAnnotations(url)
                case .font: actions.importFont(url)
                case .original: actions.exportOriginal(url)
                case .jsonl:
#if EXR_APPLE_HOST_REVIEW
                    reviewPickerDirectory = url
#endif
                    actions.exportAnnotations(url, false)
                case .markdown: actions.exportAnnotations(url, true)
                }
            case .failure(let error):
                if (error as NSError).code != NSUserCancelledError { pickerError = error.localizedDescription }
            }
        }
    }

    private func choose(_ value: Choice) {
        choice = value; pickerError = ""; choosing = true
    }

    private var annotationSection: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 8) {
                action("选择标注文件并预览", id: "features.annotations.import") { choose(.annotations) }
                if let preview = state.annotationPreview {
                    if !selectedInput.isEmpty { Text(selectedInput).font(.caption).lineLimit(2) }
                    Text("\(preview.annotations) 项标注，\(preview.heads) 个保留头；已定位 \(preview.found)")
                        .font(.caption).accessibilityIdentifier("features.preview.summary")
                    Text("NULL 选择器：\(preview.nullPreserved)；保留原值，不可跳转")
                        .font(.caption).accessibilityIdentifier("features.preview.null")
                    if preview.receivingGraphChecked {
                        Text("冲突：\(preview.conflicts)")
                            .font(.caption).accessibilityIdentifier("features.preview.conflicts")
                        Text("缺少父版本：\(preview.missingParents)")
                            .font(.caption).accessibilityIdentifier("features.preview.missing-parents")
                    } else {
                        Text("接收图在确认后读取，冲突与父版本会原样保留。")
                            .font(.caption).accessibilityIdentifier("features.preview.conflicts")
                    }
                    Text("未能定位：\(preview.unresolved)；预计新增 \(preview.wouldCreate)，重复 \(preview.wouldDuplicate)")
                        .font(.caption).accessibilityIdentifier("features.preview.unresolved")
                    Text("原文件省略的历史版本：\(preview.omittedHistory)")
                        .font(.caption).accessibilityIdentifier("features.preview.omitted")
                    if preview.committed > 0 {
                        Text("本次已提交 \(preview.committed) 个头；取消后已提交内容仍保留。")
                            .font(.caption).accessibilityIdentifier("features.preview.committed")
                    }
                    action("确认导入这份预览", id: "features.preview.confirm", disabled: !state.canConfirmAnnotations || preview.fingerprint.isEmpty || preview.unresolved > 0,
                           perform: actions.confirmAnnotations)
                    action("放弃预览", id: "features.preview.discard", perform: actions.discardPreview)
                }
                DisclosureGroup("导出标注") {
                    VStack(alignment: .leading, spacing: 8) {
                        action("导出可导入的 JSONL", id: "features.annotations.export-jsonl") { choose(.jsonl) }
                        action("导出 Markdown", id: "features.annotations.export-markdown") { choose(.markdown) }
                        Text("仅包含保留头；冲突会保留，不自动选择版本。")
                            .font(.caption).foregroundColor(.secondary)
                    }.padding(.top, 8)
                }.accessibilityIdentifier("features.annotations.export-options")
            }.frame(maxWidth: .infinity, alignment: .leading)
        } label: { Text("标注导入与导出") }
    }

    private var fontSection: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 8) {
                action("导入字体文件", id: "features.font.import") { choose(.font) }
                Text(state.selectedFont == nil ? "当前：内置字体" : "当前：已选导入字体")
                    .font(.caption).accessibilityIdentifier("features.font.selected")
                action("使用内置字体", id: "features.font.default") { actions.selectFont(nil) }
                ForEach(state.fonts) { font in
                    action(font.name + (font.id == state.selectedFont ? "（已选）" : ""), id: "features.font.\(font.id)") {
                        actions.selectFont(font.id)
                    }
                    .accessibilityValue(font.id == state.selectedFont ? "已选" : "")
                }
                Text("字体在当前书籍重新排版成功后切换。固定版式保留原书字体。")
                    .font(.caption).foregroundColor(.secondary)
            }.frame(maxWidth: .infinity, alignment: .leading)
        } label: { Text("阅读字体") }
    }

    private var originalSection: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 8) {
                action("导出当前书籍原件", id: "features.original.export") { choose(.original) }
                Text("选择保存文件夹；已有同名文件不会被替换。")
                    .font(.caption).foregroundColor(.secondary)
                if let url = state.exportURL {
                    Text(url.lastPathComponent).font(.caption).lineLimit(2)
                        .accessibilityIdentifier("features.export.filename")
                }
            }.frame(maxWidth: .infinity, alignment: .leading)
        } label: { Text("导出与分享") }
    }

    private var historySection: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 8) {
                action("返回上次阅读位置", id: "features.history.back", disabled: !state.canBack, perform: actions.back)
                action("前进到下一阅读位置", id: "features.history.forward", disabled: !state.canForward, perform: actions.forward)
                Text("只有实际定位成功才改变当前页面和历史位置。")
                    .font(.caption).foregroundColor(.secondary)
            }.frame(maxWidth: .infinity, alignment: .leading)
        } label: { Text("位置历史") }
    }

    private var syncSection: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 8) {
                if let sync = state.sync {
                    Text(sync.phase).accessibilityIdentifier("features.sync.phase")
                    Text(sync.reason).font(.caption).accessibilityIdentifier("features.sync.reason")
                    Text("待处理 \(sync.pending)，重试 \(sync.retried)")
                        .font(.caption).accessibilityIdentifier("features.sync.pending")
                    Text("冲突 \(sync.conflicts)").font(.caption).accessibilityIdentifier("features.sync.conflicts")
                    Text("本轮已读分片 \(sync.completedShards)/256；操作观察次数 \(sync.operations)")
                        .font(.caption).accessibilityIdentifier("features.sync.operations")
                    if sync.more {
                        Text("当前只显示一页，后面可能还有待处理记录。")
                            .font(.caption).accessibilityIdentifier("features.sync.more")
                    }
                } else {
                    Text("本地书库未连接同步会话").font(.caption).accessibilityIdentifier("features.sync.phase")
                }
                Text("只读快照。完成一轮分片扫描不代表整个书库已经同步。")
                    .font(.caption).foregroundColor(.secondary)
            }.frame(maxWidth: .infinity, alignment: .leading)
        } label: { Text("同步详情") }
    }

#if EXR_APPLE_HOST_REVIEW
    private var reviewSection: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 8) {
                action("导入随包字体", id: "features.font.fixture") {
                    if let url = Bundle.main.url(forResource: "Reader", withExtension: "otf") { actions.importFont(url) }
                }
                action("尝试将书籍导入为字体", id: "features.font.invalid") {
                    if let url = Bundle.main.url(forResource: "Sample", withExtension: "epub") { actions.importFont(url) }
                }
                action("导出原件到临时文件夹", id: "features.original.prepare") {
                    if let directory = reviewDirectory() {
                        reviewOriginalDirectory = directory
                        actions.exportOriginal(directory)
                    }
                }
                action("核对原件同名冲突", id: "features.original.conflict") {
                    guard let directory = reviewOriginalDirectory, let file = state.exportURL,
                          file.deletingLastPathComponent() == directory else { return }
                    do {
                        try Data("wave3-conflict-sentinel".utf8).write(to: file)
                        actions.exportOriginal(directory)
                    } catch { pickerError = error.localizedDescription }
                }
                action("核对只读文件夹", id: "features.original.locked") {
                    if let directory = reviewDirectory() {
                        do {
                            try FileManager.default.setAttributes([.posixPermissions: NSNumber(value: 0o500)], ofItemAtPath: directory.path)
                            lockedReviewDirectory = directory
                            actions.exportOriginal(directory)
                        } catch { pickerError = error.localizedDescription }
                    }
                }
                action("预览真实 NULL 标注文件", id: "features.annotations.null") {
                    selectedInput = "NULL 标注文件"
                    actions.reviewAnnotations?(true)
                }
                action("预览真实并发标注文件", id: "features.annotations.conflict") {
                    selectedInput = "并发标注文件"
                    actions.reviewAnnotations?(false)
                }
                action("预览无效标注文件", id: "features.annotations.invalid") {
                    if let directory = reviewDirectory() {
                        let file = directory.appendingPathComponent("invalid.jsonl")
                        do {
                            try Data("{invalid json\n".utf8).write(to: file)
                            selectedInput = file.lastPathComponent
                            actions.previewAnnotations(file)
                        } catch { pickerError = error.localizedDescription }
                    }
                }
                action("读取修订快照", id: "features.annotations.snapshot") { actions.reviewSnapshot?() }
                Text(state.reviewRevisionIdentity).accessibilityIdentifier("features.annotations.identity")
                action("准备系统选择器文件", id: "features.annotations.prepare-picker") {
                    guard let source = state.exportURL else { return }
                    do {
                        guard let documents = reviewPickerDirectory else {
                            throw HostError.invalidInput("请先通过系统选择器导出 JSONL")
                        }
                        let accessing = documents.startAccessingSecurityScopedResource()
                        defer { if accessing { documents.stopAccessingSecurityScopedResource() } }
                        let file = documents.appendingPathComponent("EXReader-annotations.jsonl")
                        let invalid = documents.appendingPathComponent("EXReader-invalid.jsonl")
                        try Data(contentsOf: source).write(to: file, options: .atomic)
                        try Data("{invalid json\n".utf8).write(to: invalid, options: .atomic)
                        reviewPickerFile = file
                    } catch { pickerError = error.localizedDescription }
                }
                if let file = reviewPickerFile {
                    Text(file.path).accessibilityIdentifier("features.annotations.picker-path")
                }
                action("导出 Markdown 到临时文件夹", id: "features.annotations.markdown-fixture") {
                    if let directory = reviewDirectory() { actions.exportAnnotations(directory, true) }
                }
                action("核对导出文件", id: "features.annotations.check-exports") {
                    guard let jsonl = reviewPickerFile, let markdown = state.exportURL else { return }
                    do { try HostWave3Review.checkExports(jsonl: jsonl, markdown: markdown); reviewExportCheck = "导出内容一致" }
                    catch { reviewExportCheck = "导出内容错误：\(error.localizedDescription)" }
                }
                Text(reviewExportCheck).accessibilityIdentifier("features.annotations.export-check")
                action("导出后预览同一标注文件", id: "features.annotations.roundtrip") {
                    if let directory = reviewDirectory() {
                        previousExportURL = state.exportURL
                        previewExportWhenReady = true
                        actions.exportAnnotations(directory, false)
                    }
                }
            }.frame(maxWidth: .infinity, alignment: .leading)
        } label: { Text("验收操作") }
    }

    private func reviewDirectory() -> URL? {
        guard let resolved = realpath(FileManager.default.temporaryDirectory.path, nil) else {
            pickerError = "无法解析临时文件夹"
            return nil
        }
        defer { free(resolved) }
        let directory = URL(fileURLWithPath: String(cString: resolved), isDirectory: true)
            .appendingPathComponent("wave3-review-" + UUID().uuidString, isDirectory: true)
        do {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            return directory
        } catch { pickerError = error.localizedDescription; return nil }
    }
#endif

    private func action(_ title: String, id: String, disabled: Bool = false,
                        perform: @escaping () -> Void) -> some View {
        Button(action: perform) {
            Text(title).frame(maxWidth: .infinity, minHeight: 44, alignment: .leading).contentShape(Rectangle())
        }.buttonStyle(.borderless).disabled(state.busy || ownerBusy || disabled).accessibilityIdentifier(id)
    }
}

private struct HostWave3ShareButton: View {
    let url: URL
#if os(iOS)
    @State private var sharing = false
    var body: some View {
        Button("分享导出文件") { sharing = true }
            .frame(minHeight: 44).accessibilityIdentifier("features.share")
            .sheet(isPresented: $sharing) { HostWave3Activity(url: url) }
    }
#else
    var body: some View {
        HostWave3SharingPicker(url: url).frame(height: 32)
            .accessibilityIdentifier("features.share")
    }
#endif
}

#if os(iOS)
private struct HostWave3Activity: UIViewControllerRepresentable {
    let url: URL
    func makeUIViewController(context: Context) -> UIActivityViewController {
        let controller = UIActivityViewController(activityItems: [url], applicationActivities: nil)
        controller.view.accessibilityIdentifier = "features.share.native"
        if let popover = controller.popoverPresentationController {
            popover.sourceView = controller.view
            popover.sourceRect = CGRect(x: controller.view.bounds.midX, y: controller.view.bounds.midY, width: 1, height: 1)
        }
        return controller
    }
    func updateUIViewController(_ controller: UIActivityViewController, context: Context) {}
}
#else
private struct HostWave3SharingPicker: NSViewRepresentable {
    let url: URL
    func makeCoordinator() -> Coordinator { Coordinator(url: url) }
    func makeNSView(context: Context) -> NSButton {
        let button = NSButton(title: "分享导出文件", target: context.coordinator, action: #selector(Coordinator.share(_:)))
        button.setAccessibilityIdentifier("features.share")
        return button
    }
    func updateNSView(_ button: NSButton, context: Context) { context.coordinator.url = url }
    final class Coordinator: NSObject {
        var url: URL
        private var picker: NSSharingServicePicker?
        init(url: URL) { self.url = url }
        @objc func share(_ sender: NSButton) {
            let picker = NSSharingServicePicker(items: [url])
            self.picker = picker
            picker.show(relativeTo: sender.bounds, of: sender, preferredEdge: .minY)
        }
    }
}
#endif
#endif


