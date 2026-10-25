// SPDX-License-Identifier: MIT
import SwiftUI
import CReaderProduct

struct HostNavigationSheet: View {
    @ObservedObject var model: HostReaderModel
    @ObservedObject var navigation: HostNavigationState
    @Environment(\.presentationMode) private var presentation
    init(model: HostReaderModel) { self.model = model; navigation = model.navigation }

    var body: some View {
        VStack(spacing: 12) {
            HStack {
                Text("目录").font(.headline).accessibilityAddTraits(.isHeader)
                Spacer()
                Button("关闭") { navigation.cancel(); presentation.wrappedValue.dismiss() }
                    .accessibilityIdentifier("navigation.close")
            }
            Text(navigation.status).font(.caption).accessibilityIdentifier("navigation.status")
            HStack {
                if !navigation.parents.isEmpty {
                    Button("上一级") {
                        if let (parent, first) = navigation.popParent() { model.loadNavigation(parent: parent, first: first) }
                    }.accessibilityIdentifier("navigation.up")
                }
                if navigation.running {
                    Button("取消") { navigation.cancel() }.accessibilityIdentifier("navigation.cancel")
                } else if let page = navigation.page {
                    if page.first > 0 {
                        Button("上一批") { model.loadNavigation(parent: page.parent, first: page.first >= 32 ? page.first - 32 : 0) }
                            .accessibilityIdentifier("navigation.previous")
                    }
                    if page.next != UInt64.max {
                        Button("下一批") { model.loadNavigation(parent: page.parent, first: page.next) }
                            .accessibilityIdentifier("navigation.next")
                    }
                } else {
                    Button("重新读取") { model.loadNavigation() }.accessibilityIdentifier("navigation.reload")
                }
            }.buttonStyle(.bordered).disabled(model.busy && !navigation.running)
            if let selection = navigation.pending {
                if selection.resolution.status == READER_NAVIGATION_AMBIGUOUS {
                    Text("选择书脊中的具体章节").font(.caption)
                    ScrollView {
                        VStack {
                            ForEach(selection.resolution.candidates, id: \.self) { part in
                                Button("第 \(part + 1) 章") { model.selectNavigation(row: selection.row, explicitPart: part, cfi: selection.cfi) }
                                    .accessibilityIdentifier("navigation.part.\(part)")
                            }
                        }
                    }.frame(maxHeight: 120)
                } else {
                    Button("确认打开本章开头") {
                        model.selectNavigation(row: selection.row, explicitPart: selection.resolution.target.part, acceptPart: true, cfi: selection.cfi)
                    }.accessibilityIdentifier("navigation.confirm.part")
                }
                Button("保留当前页面") { navigation.cancel() }.accessibilityIdentifier("navigation.keep")
            }
            List(navigation.page?.rows ?? []) { row in
                HStack {
                    Button(row.label.isEmpty ? "未命名目录项" : row.label) { model.selectNavigation(row: row.index) }
                        .accessibilityIdentifier("navigation.row.\(row.index)")
                    Spacer()
                    if row.children > 0 {
                        Button("子目录") {
                            navigation.pushParent(); model.loadNavigation(parent: row.index)
                        }.accessibilityLabel(Text("\(row.label)的子目录"))
                            .accessibilityIdentifier("navigation.children.\(row.index)")
                    }
                }.buttonStyle(.borderless).disabled(navigation.running || model.busy)
            }.accessibilityIdentifier("navigation.rows")
        }.padding().frame(minWidth: 280, minHeight: 360)
            .onDisappear { navigation.cancel() }
            .onChange(of: navigation.committed) { _ in presentation.wrappedValue.dismiss() }
            .onChange(of: model.current?.id) { _ in navigation.invalidate(); presentation.wrappedValue.dismiss() }
    }
}
