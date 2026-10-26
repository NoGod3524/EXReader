// SPDX-License-Identifier: MIT
#if EXR_APPLE_WAVE3
import SwiftUI
import UniformTypeIdentifiers
#if os(macOS)
import AppKit
#else
import UIKit
#endif

struct HostFeatureSheet: View {
    @ObservedObject var model: HostReaderModel
    @ObservedObject var state: HostFeatureState
    @Environment(\.presentationMode) private var presentation
    @State private var picking = false
    @State private var selection = "annotations"
    @State private var sharing = false
    private func pick(_ kind: String) { selection = kind; picking = true }
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("阅读工具").font(.headline)
                Spacer()
                Button("关闭") { if model.busy { model.cancelWork() }; model.dismissFeaturePreview(); presentation.wrappedValue.dismiss() }
                    .accessibilityIdentifier("features.close")
            }
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Text(state.status).accessibilityIdentifier("features.status").fixedSize(horizontal: false, vertical: true)
                    GroupBox("标注预览与确认") {
                        VStack(alignment: .leading, spacing: 8) {
                            Button("选择标注 JSONL") { pick("annotations") }.accessibilityIdentifier("features.annotations.pick")
#if EXR_APPLE_HOST_REVIEW
                            if model.showsTestFixtures {
                                Button("预览实际导出标注") { model.reviewFeatureAnnotationRoundtrip() }.accessibilityIdentifier("features.annotations.roundtrip")
                            }
#endif
                            if let preview = state.preview {
                                Text("\(preview.count) 个版本；NULL 保留 \(preview.nulls)；重复 \(preview.duplicates)；省略祖先 \(preview.omitted)")
                                    .accessibilityIdentifier("features.annotations.preview")
                                Text("预览未写入。确认只接收原始 heads；NULL 不可跳转，冲突不自动合并。").font(.caption)
                                Button("确认导入") { model.confirmFeatureAnnotations() }.accessibilityIdentifier("features.annotations.confirm")
                                Button("取消预览") { model.dismissFeaturePreview() }.accessibilityIdentifier("features.annotations.cancel")
                            }
                        }.frame(maxWidth: .infinity, alignment: .leading)
                    }
                    GroupBox("字体") {
                        VStack(alignment: .leading, spacing: 8) {
                            Text(state.fontName).accessibilityIdentifier("features.font.name")
                            Button("选择本地字体") { pick("font") }.accessibilityIdentifier("features.font.pick")
                            Button("恢复内置字体") { model.chooseFeatureFont(nil) }.accessibilityIdentifier("features.font.reset")
                            Text("字体仅借用原生 lease；排版成功才替换，失败保留旧页面。").font(.caption)
#if EXR_APPLE_HOST_REVIEW
                            if model.showsTestFixtures {
                                Button("使用测试包字体") { model.chooseFeatureFont(Bundle.main.url(forResource: "Reader", withExtension: "otf")) }
                                    .accessibilityIdentifier("features.font.fixture")
                                Button("拒绝无效字体") { model.chooseFeatureFont(Bundle.main.url(forResource: "Sample", withExtension: "pdf")) }
                                    .accessibilityIdentifier("features.font.invalid")
                            }
#endif
                        }.frame(maxWidth: .infinity, alignment: .leading)
                    }
                    GroupBox("原件导出与分享") {
                        VStack(alignment: .leading, spacing: 8) {
                            Button("选择导出目录") { pick("directory") }.accessibilityIdentifier("features.original.directory")
                            Button("准备原件分享") { model.exportFeatureOriginal(nil) }.accessibilityIdentifier("features.original.prepare")
#if EXR_APPLE_HOST_REVIEW
                            if model.showsTestFixtures {
                                Button("验证锁定目录") { model.reviewFeatureExportFailure(locked: true) }.accessibilityIdentifier("features.original.locked")
                                Button("验证目标冲突") { model.reviewFeatureExportFailure(locked: false) }.accessibilityIdentifier("features.original.conflict")
                            }
#endif
                            if let url = state.exported {
                                Text(url.lastPathComponent).accessibilityIdentifier("features.original.file")
#if os(iOS)
                                Button("分享原件") { sharing = true }.accessibilityIdentifier("features.original.share")
#else
                                HostOriginalShare(url: url).frame(height: 32)
#endif
                            }
                        }.frame(maxWidth: .infinity, alignment: .leading)
                    }
                    GroupBox("跳转历史") {
                        HStack {
                            Button("后退") { model.returnFeatureHistory(forward: false) }.disabled(!state.canBack).accessibilityIdentifier("features.history.back")
                            Button("前进") { model.returnFeatureHistory(forward: true) }.disabled(!state.canForward).accessibilityIdentifier("features.history.forward")
                        }.frame(maxWidth: .infinity, alignment: .leading)
                    }
                    GroupBox("只读同步状态") {
                        VStack(alignment: .leading, spacing: 8) {
                            Text(state.sync).fixedSize(horizontal: false, vertical: true).accessibilityIdentifier("features.sync.snapshot")
#if EXR_APPLE_HOST_REVIEW
                            if model.showsTestFixtures {
                                Button("读取实际 idle 快照") { model.reviewFeatureSyncSnapshot() }.accessibilityIdentifier("features.sync.idle")
                            }
#endif
                            Button("刷新状态") { model.refreshFeatureSync() }.accessibilityIdentifier("features.sync.refresh")
                        }.frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
            }.disabled(model.busy)
            if model.busy { Button("取消当前操作") { model.cancelWork() }.accessibilityIdentifier("features.cancel") }
        }.padding().frame(minWidth: 280, idealWidth: 560, minHeight: 340)
        .fileImporter(isPresented: $picking, allowedContentTypes: selection == "directory" ? [.folder] : [.data], allowsMultipleSelection: false) { result in
            switch result {
            case .success(let urls):
                guard let url = urls.first else { return }
                if selection == "annotations" { model.previewFeatureAnnotations(url) }
                else if selection == "font" { model.chooseFeatureFont(url) }
                else { model.exportFeatureOriginal(url) }
            case .failure(let error):
                let error = error as NSError
                state.status = error.code == NSUserCancelledError ? "已取消选择；原内容不变" : "选择失败：\(error.localizedDescription)"
            }
        }
#if os(iOS)
        .sheet(isPresented: $sharing) { if let url = state.exported { HostOriginalShare(url: url) } }
#endif
    }
}
#if os(iOS)
struct HostOriginalShare: UIViewControllerRepresentable {
    let url: URL
    func makeUIViewController(context: Context) -> UIActivityViewController { UIActivityViewController(activityItems: [url], applicationActivities: nil) }
    func updateUIViewController(_ controller: UIActivityViewController, context: Context) {}
}
#else
struct HostOriginalShare: NSViewRepresentable {
    let url: URL
    final class Coordinator: NSObject {
        var url: URL
        init(_ url: URL) { self.url = url }
        @objc func share(_ sender: NSButton) { NSSharingServicePicker(items: [url]).show(relativeTo: sender.bounds, of: sender, preferredEdge: .minY) }
    }
    func makeCoordinator() -> Coordinator { Coordinator(url) }
    func makeNSView(context: Context) -> NSButton {
        let button = NSButton(title: "分享原件", target: context.coordinator, action: #selector(Coordinator.share(_:)))
        button.setAccessibilityIdentifier("features.original.share"); return button
    }
    func updateNSView(_ view: NSButton, context: Context) { context.coordinator.url = url }
}
#endif
#endif
