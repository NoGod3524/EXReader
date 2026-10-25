// SPDX-License-Identifier: MIT
import SwiftUI

struct HostReadingRecordsSheet: View {
    @ObservedObject var model: HostReaderModel
    @ObservedObject var records: HostReadingState
    @Environment(\.presentationMode) private var presentation
    @State private var editing: HostReadingRow?
    @State private var deleting: HostReadingRow?
    @State private var restoring: HostReadingVersion?
    @State private var discardRevision: String?
    init(model: HostReaderModel) {
        self.model = model; self.records = model.readingRecords
    }
    private var confirmationTitle: String {
        deleting != nil ? "删除阅读记录？" : restoring != nil ? "恢复这个保留版本？" : "放弃这项待完成请求？"
    }
    var body: some View {
        VStack(spacing: 12) {
            Text("阅读记录").font(.headline).accessibilityAddTraits(.isHeader)
                .accessibilityIdentifier("reading.title")
            HStack {
                Button("保存阅读进度") { model.saveReadingRecord(bookmark: false) }
                    .accessibilityIdentifier("reading.save-progress")
                Button("添加书签") { model.saveReadingRecord(bookmark: true) }
                    .accessibilityIdentifier("reading.add-bookmark")
            }.buttonStyle(.bordered).disabled(model.busy || records.pending != nil)
            if let pending = records.pending {
                Text("有一项待完成记录。重试会沿用原请求。").font(.caption)
                    .accessibilityIdentifier("reading.pending")
                HStack {
                    Button("重试原请求") { model.replayReadingRequest() }
                        .accessibilityIdentifier("reading.retry")
                    Button("放弃请求", role: .destructive) { discardRevision = pending.revision }
                        .accessibilityIdentifier("reading.discard")
                }.buttonStyle(.bordered).disabled(model.busy)
            }
            List {
                ForEach(Array(records.rows.enumerated()), id: \.element.id) { index, row in
                    VStack(alignment: .leading, spacing: 6) {
                        Text(row.label).font(.headline).accessibilityIdentifier("reading.kind.\(index)")
                        Text(row.detail).font(.caption).lineLimit(4).accessibilityIdentifier("reading.body.\(index)")
                        if row.safe && row.hasLocation {
                            HStack {
                                Button("跳转") { model.jumpReadingRecord(row) }
                                    .accessibilityIdentifier("reading.jump.\(index)")
                                if row.entityKind == "annotation" {
                                    Button("编辑批注") { editing = row }
                                        .accessibilityIdentifier("reading.edit.\(index)")
                                }
                                Button("删除", role: .destructive) { deleting = row }
                                    .accessibilityIdentifier("reading.delete.\(index)")
                            }.disabled(model.busy || records.pending != nil)
                        }
                        Button("保留版本") { model.showReadingHistory(row) }
                            .accessibilityIdentifier("reading.history.\(index)")
                            .disabled(model.busy || records.pending != nil)
                    }.padding(.vertical, 4)
                }
                if !records.versions.isEmpty {
                    Section("选择恢复版本") {
                        ForEach(Array(records.versions.enumerated()), id: \.element.id) { index, version in
                            Button("恢复\(version.label)") { restoring = version }
                                .accessibilityIdentifier("reading.restore.\(index)")
                        }
                    }.disabled(model.busy || records.pending != nil)
                }
            }.buttonStyle(.borderless).accessibilityIdentifier("reading.list")
            if !records.complete {
                Button("下一批") { model.loadReadingRecords(next: true) }
                    .accessibilityIdentifier("reading.next").disabled(model.busy)
            }
            Text(records.status).font(.caption).accessibilityIdentifier("reading.status")
#if EXR_APPLE_HOST_REVIEW
            if !records.nativeBoundary.isEmpty {
                Text(records.nativeBoundary).font(.caption2).accessibilityIdentifier("reading.native-boundary")
            }
#endif
            HStack {
                Button("刷新") { model.loadReadingRecords() }.accessibilityIdentifier("reading.refresh").disabled(model.busy)
                if model.busy { Button("取消") { model.cancelWork() }.accessibilityIdentifier("reading.cancel") }
                Button("关闭") { presentation.wrappedValue.dismiss() }.accessibilityIdentifier("reading.close")
            }.buttonStyle(.bordered)
        }.padding().frame(minWidth: 280, minHeight: 360)
            .onDisappear { if editing == nil { model.closeReadingRecords() } }
            .sheet(item: $editing) { HostReadingNoteEditor(model: model, row: $0) }
            .alert(confirmationTitle, isPresented: Binding(get: { deleting != nil || restoring != nil || discardRevision != nil },
                set: { if !$0 { deleting = nil; restoring = nil; discardRevision = nil } })) {
                if let row = deleting {
                    Button("删除", role: .destructive) { model.deleteReadingRecord(row); deleting = nil }
                        .accessibilityIdentifier("reading.confirm-delete")
                } else if let version = restoring {
                    Button("恢复") { model.restoreReadingVersion(version); restoring = nil }
                        .accessibilityIdentifier("reading.confirm-restore")
                } else if let revision = discardRevision {
                    Button("放弃请求", role: .destructive) { model.discardReadingRequest(expected: revision); discardRevision = nil }
                        .accessibilityIdentifier("reading.confirm-discard")
                }
                Button("取消", role: .cancel) { deleting = nil; restoring = nil; discardRevision = nil }
            } message: { Text(restoring != nil ? "先核验原书中的实际位置，再新建恢复记录。当前页面保持不变。" : "已经提交的版本会保留。") }
    }
}

private struct HostReadingNoteEditor: View {
    @ObservedObject var model: HostReaderModel
    let row: HostReadingRow
    @State private var text: String
    @Environment(\.presentationMode) private var presentation
    init(model: HostReaderModel, row: HostReadingRow) {
        self.model = model; self.row = row; _text = State(initialValue: row.body)
    }
    var body: some View {
        VStack(spacing: 12) {
            Text("编辑批注").font(.headline)
            TextEditor(text: $text).frame(minHeight: 180).accessibilityIdentifier("reading.editor")
            if text.utf8.count > 65536 { Text("批注超过长度上限").foregroundColor(.red) }
            HStack {
                Button("保存") { model.editReadingRecord(row, body: text); presentation.wrappedValue.dismiss() }
                    .accessibilityIdentifier("reading.save-note").disabled(text.utf8.count > 65536 || text.utf8.contains(0))
                Button("取消") { presentation.wrappedValue.dismiss() }.accessibilityIdentifier("reading.cancel-note")
            }.buttonStyle(.bordered)
        }.padding().frame(minWidth: 280, minHeight: 260)
    }
}
