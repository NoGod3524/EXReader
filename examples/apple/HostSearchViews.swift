// SPDX-License-Identifier: MIT
import SwiftUI

struct HostSearchSheet: View {
    @ObservedObject var model: HostReaderModel
    @ObservedObject var search: HostSearchState
    @Environment(\.presentationMode) private var presentation
    @FocusState private var queryFocused: Bool

    init(model: HostReaderModel) { self.model = model; self.search = model.search }

    var body: some View {
        VStack(spacing: 12) {
            HStack {
                Text("书内查找").font(.headline).accessibilityAddTraits(.isHeader)
                Spacer()
                Button("关闭") { search.cancel(); presentation.wrappedValue.dismiss() }
                    .accessibilityIdentifier("search.close")
            }
            TextField("查找文字（区分大小写）", text: $search.query)
                .textFieldStyle(.roundedBorder).accessibilityIdentifier("search.query")
                .focused($queryFocused)
                .onSubmit { queryFocused = false; model.findInBook() }
                .onChange(of: search.query) { _ in search.queryChanged() }
            HStack {
                Button("查找") { queryFocused = false; model.findInBook() }
                    .disabled(model.busy || search.running || search.query.isEmpty || search.query.utf8.count > 4096)
                    .accessibilityIdentifier("search.find")
                if search.running {
                    Button("取消") { search.cancel() }.accessibilityIdentifier("search.cancel")
                } else if search.cursor != nil && !search.complete {
                    Button("下一批") { model.findInBook(restart: false) }
                        .disabled(model.busy).accessibilityIdentifier("search.next")
                }
            }.buttonStyle(.bordered)
            Text(search.status).font(.caption).accessibilityIdentifier("search.status")
            List(search.rows) { hit in
                Button {
                    model.selectSearchHit(hit)
                    presentation.wrappedValue.dismiss()
                } label: {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(hit.quote).lineLimit(3)
                        Text(hit.detail).font(.caption).foregroundColor(.secondary)
                    }
                }.disabled(search.running || model.busy)
                    .accessibilityIdentifier("search.hit.\(hit.id)")
            }.accessibilityIdentifier("search.results")
        }
        .padding().frame(minWidth: 280, minHeight: 320)
        .onDisappear { search.cancel() }
        .onChange(of: model.current?.id) { _ in search.invalidate(); presentation.wrappedValue.dismiss() }
    }
}
