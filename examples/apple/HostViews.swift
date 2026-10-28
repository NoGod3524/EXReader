// SPDX-License-Identifier: MIT
import SwiftUI
import UniformTypeIdentifiers
#if os(iOS)
import UIKit
#else
import AppKit
#endif

@ViewBuilder private func hostActionLabel(_ title: String) -> some View {
#if os(iOS)
    Text(title).frame(minWidth: 44, minHeight: 44).contentShape(Rectangle())
#else
    Text(title)
#endif
}

@ViewBuilder private func hostHeaderActionLabel(_ title: String, symbol: String, compact: Bool) -> some View {
    if compact {
        Image(systemName: symbol).font(.system(size: 20)).frame(width: 44, height: 44).contentShape(Rectangle())
    } else { hostActionLabel(title) }
}

private func hostAnnounce(_ text: String) {
    guard !text.isEmpty else { return }
#if os(iOS)
    UIAccessibility.post(notification: .announcement, argument: text)
#else
    NSAccessibility.post(element: NSApplication.shared, notification: .announcementRequested,
                         userInfo: [.announcement: text, .priority: NSAccessibilityPriorityLevel.medium.rawValue])
#endif
}

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
    @StateObject private var model: HostReaderModel
    @Environment(\.scenePhase) private var phase
#if EXR_APPLE_PAGE_THEME
    @Environment(\.colorScheme) private var pageThemeScheme
#endif
    private let selfTesting = CommandLine.arguments.contains("--self-test")

    init(profile: HostAccountProfile? = nil, accounts: HostAccounts? = nil) {
        _model = StateObject(wrappedValue: HostReaderModel(profile: profile, accounts: accounts))
    }

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
        .preference(key: HostReadingRouteKey.self, value: !selfTesting && !model.showLibrary && model.current != nil)
#if EXR_APPLE_HOST_REVIEW
        .overlay(alignment: .topTrailing) {
            if model.reviewInitializationHoldEnabled {
                VStack {
                    Text(model.reviewInitializationObservation).font(.system(size: 2)).lineLimit(1)
                        .accessibilityIdentifier("initialization.state")
                    if model.reviewInitializationHeld {
                        Button("尝试初始化前导入") { model.reviewTryImportBeforeInitialization() }
                            .accessibilityIdentifier("initialization.try-import")
                        Button("继续实际初始化") { model.reviewReleaseInitialization() }
                            .accessibilityIdentifier("initialization.release")
                    }
                }.padding(4)
            }
        }
#endif
#if os(macOS)
        .frame(minWidth: 380, minHeight: 460)
#endif
        .onAppear {
#if EXR_APPLE_PAGE_THEME
            if !selfTesting { model.observePageThemeEnvironment(dark: pageThemeScheme == .dark) }
#endif
            if !selfTesting { model.observeUITestScene(String(describing: phase)); model.start() }
        }
#if EXR_APPLE_PAGE_THEME
        .onChange(of: pageThemeScheme) { value in
            if !selfTesting { model.observePageThemeEnvironment(dark: value == .dark) }
        }
#endif
        .onChange(of: phase) { value in
            if !selfTesting { model.observeUITestScene(String(describing: value)) }
            if value != .active && !selfTesting { model.persistNow(); model.closeAccountSession() }
        }
        .onReceive(resignPublisher) { _ in
            if !selfTesting { model.persistNow(); model.closeAccountSession() }
        }
        .onDisappear {
            if !selfTesting { model.persistNow(); model.closeAccountSession() }
        }
    }
}

private struct ShelfGeometry: Equatable {
    var frames: [String: CGRect] = [:]
    var size: CGSize = .zero
    var revision = 0
}
private struct ShelfGeometryKey: PreferenceKey {
    static var defaultValue = ShelfGeometry()
    static func reduce(value: inout ShelfGeometry, nextValue: () -> ShelfGeometry) {
        let next = nextValue()
        guard next.revision >= value.revision else { return }
        if next.revision > value.revision { value = next; return }
        value.frames.merge(next.frames) { _, newer in newer }
        if next.size.height > 0 { value.size = next.size }
    }
}

private struct ShelfGeometryProbe: View {
    @ObservedObject var shelf: HostShelf
    var rowKey: String? = nil

    private func measure(_ geometry: GeometryProxy, revision: Int) {
        let frame = geometry.frame(in: .named("catalog-shelf")), size = geometry.size
        DispatchQueue.main.async {
            shelf.measureProbe(key: rowKey, frame: frame, size: size, revision: revision)
        }
    }

    var body: some View {
        let revision = shelf.geometryRevision
        GeometryReader { geometry in
            Color.clear.preference(key: ShelfGeometryKey.self, value: rowKey.map {
                ShelfGeometry(frames: [$0: geometry.frame(in: .named("catalog-shelf"))], revision: revision)
            } ?? ShelfGeometry(size: geometry.size, revision: revision))
            // A scroll to an already aligned single row changes no rectangle.
            // Its new native probe still reports the actual post-issue epoch.
            .onAppear { measure(geometry, revision: revision) }
            .onChange(of: revision) { value in measure(geometry, revision: value) }
        }
    }
}

#if EXR_APPLE_SHELF_REVIEW
private struct ShelfObservationView: View {
    let value: String
    let searchFocused: Bool
    var body: some View {
        // macOS XCTest truncates one static-text value to 512 UTF-16 units.
        let scalars = Array(value.unicodeScalars)
        let parts = stride(from: 0, to: scalars.count, by: 200).map { start in
            String(String.UnicodeScalarView(scalars[start..<min(start + 200, scalars.count)]))
        }
        ZStack {
            Text(searchFocused ? "focused" : "unfocused").accessibilityIdentifier("library.search.focus")
            Text(String(parts.count)).accessibilityIdentifier("library.shelf.count")
            ForEach(parts.indices, id: \.self) { index in
                Text(parts[index]).accessibilityIdentifier("library.shelf.part.\(index)")
            }
        }
        .font(.caption2).lineLimit(1).frame(height: 1).clipped()
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("library.shelf.state")
    }
}
#endif

struct LibraryScreen: View {
    @ObservedObject var model: HostReaderModel
    @State private var importing = false
    @State private var organizing = false
    @StateObject private var shelf: HostShelf
    @FocusState private var searchFocused: Bool
    @Environment(\.scenePhase) private var phase
#if os(iOS)
    @Environment(\.verticalSizeClass) private var verticalSizeClass
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
#endif

    private var compactLibrary: Bool {
#if os(iOS)
        return verticalSizeClass == .compact || dynamicTypeSize.isAccessibilitySize
#else
        return false
#endif
    }

    init(model: HostReaderModel) {
        self.model = model
        _shelf = StateObject(wrappedValue: HostShelf(defaults: model.shelfDefaults))
    }

    private func restoreShelf(_ proxy: ScrollViewProxy, revision: Int) {
        DispatchQueue.main.async {
            guard shelf.restoreRevision == revision, shelf.needsScroll, let key = shelf.restoreKey else { return }
            proxy.scrollTo(key, anchor: .top)
            shelf.didScroll(revision: revision)
        }
    }

    private var importControls: some View {
        VStack(spacing: 8) {
            if model.showsTestFixtures {
                HStack {
                    Button("导入 EPUB 示例") { model.importFixture("Sample", extension: "epub") }
                        .accessibilityIdentifier("library.import.epub")
                    Button("再次导入同一 EPUB") { model.importFixture("Sample", extension: "epub") }
                        .accessibilityIdentifier("library.import.epub.duplicate")
                }
            }
            HStack {
                if model.showsTestFixtures {
                    Button("导入 PDF 示例") { model.importFixture("Sample", extension: "pdf") }
                        .accessibilityIdentifier("library.import.pdf")
                }
                if !compactLibrary {
                    Button("打开文件…") { importing = true }
                        .accessibilityIdentifier("library.import.picker")
                }
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
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("EXReader 书架").font(compactLibrary ? .caption : .title2).bold().lineLimit(1)
                    .accessibilityIdentifier("library.title")
                    .accessibilityAddTraits(.isHeader)
#if EXR_APPLE_HOST_REVIEW
                    .accessibilityValue(Text(model.uiTestTrace))
#endif
                Spacer()
                if compactLibrary {
                    if let account = model.accountSession {
                        HostSyncControls(session: account, preparing: model.syncPreparing, compact: true) { model.synchronizeAccount() }
                    }
                    Button { importing = true } label: { hostHeaderActionLabel("打开文件", symbol: "plus", compact: true) }
                        .accessibilityLabel(Text("打开文件"))
                        .accessibilityIdentifier("library.import.picker").disabled(model.busy)
                }
                if model.busy {
                    Text("处理中…").font(.caption)
                        .accessibilityIdentifier("library.busy")
#if EXR_APPLE_HOST_REVIEW
                    if model.uiTestCancellationReady {
                        Text("等待取消").font(.caption2).lineLimit(1).accessibilityIdentifier("library.cancel.ready")
                    }
#endif
                    Button { model.cancelWork() } label: { hostHeaderActionLabel("取消", symbol: "xmark", compact: compactLibrary) }
                        .accessibilityLabel(Text("取消"))
                        .accessibilityIdentifier("library.cancel")
                }
            }
            .padding(.horizontal).padding(.top, 12)

            HStack {
                TextField("搜索书名或作者", text: $shelf.query)
                    .textFieldStyle(.roundedBorder)
                    .focused($searchFocused).submitLabel(.search)
                    .onSubmit { searchFocused = false }
                    .accessibilityIdentifier("library.search")
                    .onChange(of: shelf.query) { _ in shelf.search() }
                    .disabled(model.productIndexPending)
                Button("刷新") { shelf.refresh() }
                    .disabled(model.busy || model.productIndexPending)
                    .accessibilityIdentifier("library.refresh")
                Button("整理") { organizing = true }
                    .disabled(model.busy || model.productIndexPending || model.organizationURL == nil)
                    .accessibilityIdentifier("library.organization")
            }.padding(.horizontal).padding(.vertical, 6)

            if (model.productIndexPending || (shelf.rows.isEmpty && !model.errorText.isEmpty)) && !model.books.isEmpty {
                // Retained SDK imports remain reachable while product repair is pending.
                List(model.books) { book in
                    Button(book.title) { model.openBook(book) }
                        .disabled(model.busy)
                        .accessibilityIdentifier("library.book.\(book.id - 1)")
                }.accessibilityIdentifier("library.list")
            } else if shelf.rows.isEmpty && !shelf.loading {
                Spacer()
                Text(shelf.query.isEmpty ? "书架为空，打开文件即可导入。" : "未找到匹配书籍")
                    .foregroundColor(.secondary)
                    .accessibilityIdentifier("library.empty")
                Spacer()
            } else {
                ScrollViewReader { proxy in
                    ScrollView {
                      VStack(spacing: 0) {
                        ForEach(shelf.rows) { book in
                            Button {
                                shelf.choose(book)
                                model.openShelfBook(book)
                            } label: {
                                HStack {
                                    VStack(alignment: .leading, spacing: 3) {
                                        Text(book.title).font(.headline)
                                        Text([book.author, book.format.uppercased(), "\(book.bytes) B"].filter { !$0.isEmpty }.joined(separator: " · "))
                                            .font(.caption).foregroundColor(.secondary)
                                    }
                                    Spacer()
                                    Image(systemName: book.sdkID > 0 ? "chevron.right" : "icloud.and.arrow.down").foregroundColor(.secondary)
                                }
                                .padding(12)
                                .background(Color.secondary.opacity(shelf.selected == book.id ? 0.18 : 0.08))
                                .cornerRadius(10)
                            }
                            .buttonStyle(.plain)
                            .disabled(model.busy)
                            .accessibilityIdentifier(book.sdkID > 0 ? "library.book.\(book.sdkID - 1)" : "library.cloud.\(book.id)")
                            .accessibilityLabel(Text("\(book.title)，\(book.author)，\(book.format.uppercased())"))
                            .id(book.id)
                            .padding(.horizontal, 8)
                            .background(ShelfGeometryProbe(shelf: shelf, rowKey: book.id).id(shelf.geometryRevision))
                        }
                      }
                    }
                    .accessibilityIdentifier("library.list")
                    .coordinateSpace(name: "catalog-shelf")
                    .background(ShelfGeometryProbe(shelf: shelf).id(shelf.geometryRevision))
                    .onPreferenceChange(ShelfGeometryKey.self) { geometry in
                        let complete = shelf.rows.allSatisfy { geometry.frames[$0.id] != nil }
                        shelf.observe(geometry.frames, size: geometry.size, revision: geometry.revision, complete: complete)
                    }
                    // A restore request must issue its native command even
                    // when the aggregate geometry preference stays unchanged.
                    // Only later real geometry can acknowledge that command.
                    .onAppear { restoreShelf(proxy, revision: shelf.restoreRevision) }
                    // Published delivers every request, including a request
                    // made while ScrollViewReader keeps its content identity.
                    // Its value is assigned after delivery; issue on main's
                    // next turn and reject any superseded revision there.
                    .onReceive(shelf.$restoreRevision) { revision in restoreShelf(proxy, revision: revision) }
                }
            }

#if EXR_APPLE_SHELF_REVIEW
            ShelfObservationView(value: shelf.observation, searchFocused: searchFocused)
#endif
            if model.productIndexPending {
                Text("产品索引待修复；暂时最多显示最近 50 本本地书籍，重启后重试。")
                    .font(.caption).foregroundColor(.secondary)
                    .accessibilityIdentifier("library.shelf.pending")
            }
            if !shelf.error.isEmpty {
                Text(shelf.error).font(.caption).foregroundColor(.red).accessibilityIdentifier("library.shelf.error")
            }
            if let account = model.accountSession, !compactLibrary {
                HostSyncControls(session: account, preparing: model.syncPreparing) { model.synchronizeAccount() }
            }

            if let account = model.accountSession {
                if !model.receiveMessage.isEmpty {
                    Text(model.receiveMessage).font(.caption).accessibilityIdentifier("account.receive.state")
                }
                if model.syncPreparing && !account.preparing {
                    Button("取消接收准备") { model.cancelReceive() }.accessibilityIdentifier("account.receive.cancel")
                }
            }

            if model.showsTestFixtures || !compactLibrary {
                if compactLibrary {
                    ScrollView { importControls }.frame(maxHeight: 160)
                } else {
                    importControls
                }
            }

            Text(model.statusText).font(.caption)
                .accessibilityIdentifier("library.status")
#if EXR_APPLE_IMPORT_REVIEW
            if model.showsTestFixtures {
                Button("导入文本示例") { model.importFixture("Mapping", extension: "txt") }
                    .accessibilityIdentifier("library.import.mapping-text")
                Text(model.importMappingProbe).font(.caption2).lineLimit(2)
                    .accessibilityLabel(model.importMappingProbe)
                    .accessibilityIdentifier("library.import.mapping-state")
            }
#endif
#if EXR_APPLE_READING_REVIEW
            if model.showsTestFixtures {
                HStack {
                    Button("导入阅读文本示例") { model.importFixture("Records", extension: "txt") }
                        .accessibilityIdentifier("library.import.records-text")
                    Button("导入漫画示例") { model.importFixture("UnicodePages", extension: "cbz") }
                        .accessibilityIdentifier("library.import.records-cbz")
                }
            }
#endif
#if EXR_APPLE_RAW3_REVIEW && EXR_APPLE_HOST_REVIEW
            if model.showsTestFixtures {
                Button("导入原始选择器 PDF 示例") { model.importFixture("RawSelectorNUL", extension: "pdf") }
                    .accessibilityIdentifier("library.import.raw3-pdf")
                Button("导入保留记录原文示例") { model.importFixture("RetainedMacRecords", extension: "txt") }
                    .accessibilityIdentifier("library.import.raw3-mac-text")
            }
#endif
#if EXR_APPLE_HOST_REVIEW
            if model.reviewFastImportEnabled {
                Button("单回合真实快速导入") { model.reviewImportFixtureInOneMainTurn() }
                    .disabled(!model.reviewFastImportReady)
                    .accessibilityIdentifier("library.fast-import-run")
                Text(model.reviewFastImportObservation).font(.system(size: 2)).lineLimit(1)
                    .accessibilityIdentifier("library.fast-import-state")
            }
#endif
            if !model.errorText.isEmpty {
                Text(model.errorText).font(.caption).foregroundColor(.red)
                    .accessibilityIdentifier("library.error")
            }
        }
        .disabled(!model.libraryReady)
        .onAppear {
            shelf.connect(model.loadShelf)
#if EXR_APPLE_HOST_REVIEW
            model.observeReviewLibraryBusy(model.busy)
#endif
        }
        .onDisappear { shelf.save() }
        // Book publication is a commit signal even when a fast busy cycle is
        // coalesced into one SwiftUI frame.
        .onReceive(model.$books) { _ in shelf.refresh() }
        .onReceive(model.$receivedShelfRevision) { _ in shelf.refresh() }
        .onChange(of: model.busy) { value in
#if EXR_APPLE_HOST_REVIEW
            model.observeReviewLibraryBusy(value)
#endif
            if !value { shelf.refresh(); hostAnnounce(model.statusText) }
        }
        .onChange(of: phase) { value in
            if value == .active { shelf.restoreViewport() } else { shelf.save() }
        }
        .sheet(isPresented: $organizing) {
            if let url = model.organizationURL {
                HostOrganizationPanel(model: model, productURL: url, books: shelf.rows)
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

private struct HostOrganizationPanel: View {
    @ObservedObject var model: HostReaderModel
    @StateObject private var organization: HostOrganization
    let books: [HostShelfBook]
    @Environment(\.dismiss) private var dismiss
    @State private var kind = 0
    @State private var parent: String?
    @State private var parentStack: [String] = []
    @State private var removed = false
    @State private var selectedGroup: HostOrganizationGroup?
    @State private var selectedBook: HostShelfBook?
    @State private var name = ""
    @State private var ordinal = "0"
    // Identifies the snapshot currently displayed for review.
    @State private var edit = ""

    init(model: HostReaderModel, productURL: URL, books: [HostShelfBook]) {
        self.model = model
        self.books = books
        _organization = StateObject(wrappedValue: HostOrganization(productURL: productURL))
    }

    private func refresh() {
        organization.refresh(kind: kind, parent: parent, deleted: removed)
    }

    private func changeKind(_ value: Int) {
        kind = value; parent = nil; parentStack = []; selectedGroup = nil; selectedBook = nil; edit = ""
        refresh()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("书架整理").font(.headline).accessibilityAddTraits(.isHeader)
                Spacer()
                Button("完成") { dismiss() }.accessibilityIdentifier("organization.close")
            }
            HStack {
                Button("书架") { changeKind(0) }.accessibilityIdentifier("organization.kind.shelf")
                Button("分类") { changeKind(1) }.accessibilityIdentifier("organization.kind.tag")
                Button("系列") { changeKind(2) }.accessibilityIdentifier("organization.kind.series")
            }.buttonStyle(.bordered)
            Toggle("显示已移除", isOn: $removed)
                .accessibilityIdentifier("organization.removed")
                .onChange(of: removed) { _ in selectedGroup = nil; edit = ""; refresh() }
            HStack {
                TextField("名称", text: $name).textFieldStyle(.roundedBorder)
                    .accessibilityIdentifier("organization.name")
                TextField("顺序", text: $ordinal).textFieldStyle(.roundedBorder).frame(width: 70)
                    .accessibilityIdentifier("organization.ordinal")
            }
            HStack {
                Button("新建") {
                    selectedGroup = nil; selectedBook = nil; edit = "new"
                    organization.prepareGroup(kind: kind, id: "")
                }.accessibilityIdentifier("organization.create")
                Button("保存新建") {
                    organization.commitGroup(operation: 0, kind: kind, id: "", name: name,
                                             parent: kind == 0 ? parent : nil, ordinal: kind == 0 ? (UInt64(ordinal) ?? 0) : 0)
                }.disabled(edit != "new" || !organization.prepared || name.isEmpty)
                    .accessibilityIdentifier("organization.save")
                Button("刷新") { refresh() }.accessibilityIdentifier("organization.refresh")
                if kind == 0 && parent != nil {
                    Button("返回上层") { _ = parentStack.popLast(); parent = parentStack.last; selectedGroup = nil; edit = ""; refresh() }
                        .accessibilityIdentifier("organization.parent")
                }
            }.buttonStyle(.bordered)
            Text(selectedGroup?.name ?? "未选择分组")
                .accessibilityIdentifier("organization.selected")
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(organization.groups) { group in
                        Button(group.name) {
                            selectedGroup = group; selectedBook = nil; name = group.name
                            ordinal = String(group.ordinal); edit = "group"
                            organization.prepareGroup(kind: kind, id: group.id)
                            if !group.deleted { organization.refreshMembers(kind: kind, groupID: group.id) }
                        }.accessibilityIdentifier("organization.group.\(group.id)")
                    }
                    if organization.groupsMore {
                        Button("更多分组") { organization.nextGroups(kind: kind, parent: parent, deleted: removed) }
                            .accessibilityIdentifier("organization.more-groups")
                    }
                    if let group = selectedGroup {
                        HStack {
                            Button("重命名/排序") {
                                organization.commitGroup(operation: 0, kind: kind, id: group.id, name: name,
                                    parent: group.parent, ordinal: kind == 0 ? (UInt64(ordinal) ?? 0) : 0)
                            }.disabled(edit != "group" || !organization.prepared || group.deleted || name.isEmpty)
                                .accessibilityIdentifier("organization.rename")
                            Button("移除") {
                                organization.commitGroup(operation: 1, kind: kind, id: group.id, name: name,
                                    parent: group.parent, ordinal: group.ordinal)
                            }.disabled(edit != "group" || !organization.prepared || group.deleted)
                                .accessibilityIdentifier("organization.delete")
                            Button("恢复") {
                                organization.commitGroup(operation: 2, kind: kind, id: group.id, name: name,
                                    parent: group.parent, ordinal: group.ordinal)
                            }.disabled(edit != "group" || !organization.prepared || !group.deleted)
                                .accessibilityIdentifier("organization.restore")
                            if kind == 0 && !group.deleted {
                                Button("子书架") { parentStack.append(group.id); parent = group.id; selectedGroup = nil; edit = ""; refresh() }
                                    .accessibilityIdentifier("organization.children")
                            }
                        }.buttonStyle(.bordered)
                        if !group.deleted {
                            Text("分组中的书籍").font(.headline)
                            ForEach(organization.members) { member in
                                Button("\(member.title) · \(member.ordinal)") {
                                    dismiss()
                                    model.openShelfBook(member.book)
                                }
                                    .accessibilityIdentifier("organization.member.\(member.bookKey)")
                            }
                            if organization.membersMore {
                                Button("更多成员") { organization.nextMembers(kind: kind, groupID: group.id) }
                                    .accessibilityIdentifier("organization.more-members")
                            }
                            Text("书籍").font(.headline)
                            ForEach(books) { book in
                                Button(book.title) {
                                    selectedBook = book; edit = "member"
                                    organization.prepareMembership(kind: kind, groupID: group.id, bookKey: book.id)
                                }.accessibilityIdentifier("organization.book.\(book.id)")
                            }
                            if let book = selectedBook {
                                Text(organization.membershipPresent ? "member" : "not member")
                                    .accessibilityIdentifier("organization.membership")
                                HStack {
                                    Button("验证原件") { model.verifyOrganizationOriginal(book, organization: organization) }
                                        .accessibilityIdentifier("organization.verify-original")
                                    Button("添加") {
                                        organization.commitMembership(operation: 0, kind: kind, groupID: group.id,
                                            bookKey: book.id, ordinal: kind == 1 ? 0 : (UInt64(ordinal) ?? 0))
                                    }.disabled(edit != "member" || !organization.prepared)
                                        .accessibilityIdentifier("organization.add")
                                    Button("移除书籍") {
                                        organization.commitMembership(operation: 1, kind: kind, groupID: group.id,
                                            bookKey: book.id, ordinal: kind == 1 ? 0 : (UInt64(ordinal) ?? 0))
                                    }.disabled(edit != "member" || !organization.prepared)
                                        .accessibilityIdentifier("organization.remove")
                                    Button("恢复书籍") {
                                        organization.commitMembership(operation: 2, kind: kind, groupID: group.id,
                                            bookKey: book.id, ordinal: kind == 1 ? 0 : (UInt64(ordinal) ?? 0))
                                    }.disabled(edit != "member" || !organization.prepared)
                                        .accessibilityIdentifier("organization.restore-member")
                                }.buttonStyle(.bordered)
                            }
                        }
                    }
                }.frame(maxWidth: .infinity, alignment: .leading)
            }
            if organization.pending {
                Button("重试保留的操作") { organization.recoverEdit() }
                    .accessibilityIdentifier("organization.retry")
                Button("放弃未提交的操作") { organization.abandonPending() }
                    .accessibilityIdentifier("organization.abandon")
            }
#if EXR_APPLE_HOST_REVIEW
            if organization.stagedForReview {
                Text("已暂存").accessibilityIdentifier("organization.staged")
            }
#endif
            Text(organization.message).font(.caption).accessibilityIdentifier("organization.message")
        }
        .padding().frame(minWidth: 320, minHeight: 400)
        .disabled(organization.busy || model.organizationVerificationBusy)
        .onAppear { refresh() }
    }
}

struct ReaderScreen: View {
    @ObservedObject var model: HostReaderModel
    @State private var showSelection = false
    @State private var toolsVisible = true
    @Environment(\.hostChooseAccount) private var chooseAccount
    @Environment(\.hostAccountChooserVisible) private var accountChooserVisible
    @AccessibilityFocusState private var moreFocused: Bool
    @AccessibilityFocusState private var toolsToggleFocused: Bool
    @State private var showNotes = false
    @State private var showSearch = false
    @State private var showNavigation = false
    @State private var showReadingRecords = false
#if EXR_APPLE_WAVE3
    @State private var showWave3 = false
#endif
#if EXR_APPLE_PAGE_THEME
    @State private var showPageTheme = false
#endif
#if os(iOS)
    @Environment(\.verticalSizeClass) private var verticalSizeClass
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
#endif

    private var compactTools: Bool {
#if os(iOS)
        return verticalSizeClass == .compact || dynamicTypeSize.isAccessibilitySize
#else
        return false
#endif
    }

    private var pagingTools: some View {
        HStack(spacing: 10) {
            Button { model.firstPage() } label: { hostActionLabel("首页") }
                .accessibilityIdentifier("reader.first")
            Button { model.turn(-1) } label: { hostActionLabel("上一页") }
                .accessibilityIdentifier("reader.previous")
            Button { model.turn(1) } label: { hostActionLabel("下一页") }
                .accessibilityIdentifier("reader.next")
        }.buttonStyle(.bordered).disabled(model.busy)
    }

    private var fontTools: some View {
        HStack(spacing: 10) {
            Button { model.changeFont(-2) } label: { hostActionLabel("A-") }
                .accessibilityIdentifier("reader.font.decrease").accessibilityLabel(Text("减小字号"))
            Text("字号 \(model.fontSize)").font(.caption).lineLimit(1)
                .accessibilityIdentifier("reader.font.value")
            Button { model.changeFont(2) } label: { hostActionLabel("A+") }
                .accessibilityIdentifier("reader.font.increase").accessibilityLabel(Text("增大字号"))
        }.buttonStyle(.bordered).disabled(model.busy)
    }

    private var annotationTools: some View {
        HStack(spacing: 10) {
            Button { model.prepareSearch(); showSearch = true } label: { hostActionLabel("查找") }
                .accessibilityIdentifier("reader.search")
            Button { showSelection = true } label: { hostActionLabel("选文") }
                .accessibilityIdentifier("reader.select")
            Button { showNotes = true } label: { hostActionLabel("标注 \(model.notes.count)") }
                .accessibilityIdentifier("reader.notes")
            Button { model.prepareNavigation(); showNavigation = true } label: { hostActionLabel("目录") }
                .accessibilityIdentifier("reader.navigation")
        }.buttonStyle(.bordered).disabled(model.busy)
    }

    var body: some View {
        VStack(spacing: 6) {
            HStack {
                Button { model.backToLibrary() } label: { hostHeaderActionLabel("书架", symbol: "books.vertical", compact: compactTools) }
                    .accessibilityLabel(Text("书架"))
                    .accessibilityIdentifier("reader.back")
                Text(model.title).font(compactTools ? .caption : .headline).lineLimit(1)
                    .accessibilityIdentifier("reader.title")
                    .accessibilityAddTraits(.isHeader)
                Spacer()
                if compactTools {
                    Button { toolsVisible.toggle() } label: {
                        Image(systemName: toolsVisible ? "chevron.down" : "slider.horizontal.3")
                            .font(.system(size: 20))
                            .frame(width: 44, height: 44).contentShape(Rectangle())
                    }
                    .accessibilityLabel(toolsVisible ? "隐藏阅读工具" : "显示阅读工具")
                    .accessibilityIdentifier("reader.tools.toggle")
                    .accessibilityFocused($toolsToggleFocused)
                }
                Menu {
                    if let chooseAccount {
                        Button("书库账号") { chooseAccount() }
                            .accessibilityIdentifier("account.choose")
                    }
#if EXR_APPLE_WAVE3
                    Button("文件、字体与同步详情") { model.refreshWave3(); showWave3 = true }
                        .accessibilityIdentifier("reader.features")
#endif
                    Button("阅读记录") { model.prepareReadingRecords(); showReadingRecords = true }
                        .accessibilityIdentifier("reader.records")
#if EXR_APPLE_PAGE_THEME
                    Button("阅读主题") { showPageTheme = true }
                        .accessibilityIdentifier("reader.theme")
#endif
                } label: { Image(systemName: "ellipsis").font(.system(size: 20)).frame(width: 44, height: 44) }
                    .accessibilityLabel(Text("更多阅读操作"))
                    .accessibilityIdentifier("reader.more").disabled(model.busy)
                    .accessibilityFocused($moreFocused)
                if model.busy {
                    if compactTools {
                        Image(systemName: "hourglass").frame(width: 20, height: 20)
                            .accessibilityLabel(Text("处理中…"))
                            .accessibilityIdentifier("reader.busy")
                    } else {
                        Text("处理中…").font(.caption)
                            .accessibilityIdentifier("reader.busy")
                    }
                    Button { model.cancelWork() } label: { hostHeaderActionLabel("取消", symbol: "xmark", compact: compactTools) }
                        .accessibilityLabel(Text("取消"))
                        .accessibilityIdentifier("reader.cancel")
                }
            }
            // Header icons retain 44-point targets without automatic button
            // chrome expanding to the maximum body-text control height.
            .buttonStyle(.plain)
            .padding(.horizontal).padding(.top, 8)

            GeometryReader { geometry in
                ZStack {
#if EXR_APPLE_PAGE_THEME
                    hostPageThemeColor(model.current?.isFixed == true ? 0xffffffff : model.pageThemePalette.background ?? 0xffffffff)
#else
                    Color.white
#endif
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
#if EXR_APPLE_PAGE_THEME
            .background(hostPageThemeColor(model.current?.isFixed == true ? 0xffffffff : model.pageThemePalette.background ?? 0xffffffff))
#else
            .background(Color.white)
#endif
            .padding(.horizontal, 4)

            // One scrollable information row never competes vertically with
            // the page at accessibility sizes. Full strings remain available
            // to accessibility; text is not scaled down or truncated in state.
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 12) {
                    Text(model.location).font(.caption).lineLimit(1)
                        .accessibilityIdentifier("reader.location")
                    Text(model.progress).font(.caption).lineLimit(1)
                        .accessibilityIdentifier("reader.progress")
#if EXR_APPLE_HOST_REVIEW
                    Text("#\(model.stateHash)").font(.caption2).foregroundColor(.secondary)
                        .accessibilityIdentifier("reader.state")
#endif
                    if compactTools {
                        Text(model.statusText).font(.caption).lineLimit(1)
                            .accessibilityIdentifier("reader.status")
                    }
                }.fixedSize(horizontal: true, vertical: false)
            }.fixedSize(horizontal: false, vertical: true)

            if compactTools {
                if toolsVisible {
                    ScrollView(.horizontal) {
                        HStack(spacing: 16) { annotationTools; pagingTools; fontTools }
                            .fixedSize(horizontal: true, vertical: false).padding(.horizontal, 8)
                    }.fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("reader.tools.scroll")
                }
            } else {
                pagingTools
                fontTools
                annotationTools
                Text(model.statusText).font(.caption).lineLimit(2)
                    .accessibilityIdentifier("reader.status")
            }

            if !model.errorText.isEmpty {
                Text(model.errorText).font(.caption).foregroundColor(.red)
                    .accessibilityIdentifier("reader.error")
            }
        }
        // A keyboard in a native sheet does not resize/repaginate the reader
        // underneath it or overwrite a completed search navigation status.
        .ignoresSafeArea(.keyboard)
        .sheet(isPresented: $showSelection, onDismiss: { if compactTools { toolsToggleFocused = true } }) {
            SelectionSheet(model: model)
        }
        .sheet(isPresented: $showNotes, onDismiss: { if compactTools { toolsToggleFocused = true } }) {
            NotesSheet(model: model)
        }
        .sheet(isPresented: $showSearch, onDismiss: { if compactTools { toolsToggleFocused = true } }) { HostSearchSheet(model: model) }
        .sheet(isPresented: $showNavigation, onDismiss: { if compactTools { toolsToggleFocused = true } }) { HostNavigationSheet(model: model) }
        .sheet(isPresented: $showReadingRecords, onDismiss: { if compactTools { toolsToggleFocused = true } }) { HostReadingRecordsSheet(model: model) }
#if EXR_APPLE_WAVE3
        .sheet(isPresented: $showWave3, onDismiss: { if compactTools { toolsToggleFocused = true } }) { HostWave3Sheet(state: model.wave3, ownerBusy: model.busy, actions: model.wave3Actions) }
#endif
#if EXR_APPLE_PAGE_THEME
        .sheet(isPresented: $showPageTheme, onDismiss: { if compactTools { toolsToggleFocused = true } }) { HostPageThemeSheet(model: model) }
#endif
        .onChange(of: accountChooserVisible) { visible in if !visible { moreFocused = true } }
        .onChange(of: toolsVisible) { _ in toolsToggleFocused = true }
        .onDisappear { model.detach() }
        .onChange(of: model.location) { value in hostAnnounce(value) }
        .onChange(of: model.statusText) { value in if !model.busy { hostAnnounce(value) } }
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

    private var selectionContent: some View {
        VStack(spacing: 10) {
            Text("选择本页文字").font(.headline)
                .accessibilityIdentifier("selection.title")
                .accessibilityAddTraits(.isHeader)
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
            Button("保存高亮到阅读记录") {
                guard let context, let (start, end) = byteRange() else { hint = "请先选择文字"; return }
                model.highlightReadingRecord(start: context.baseOffset + start, end: context.baseOffset + end, context: context)
                hint = "正在保存高亮…"
            }.buttonStyle(.bordered).disabled(!isCurrent || model.busy || selectedText().isEmpty)
                .accessibilityIdentifier("selection.reading-highlight")
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
    }

    var body: some View {
        Group {
#if os(iOS)
            ScrollView { selectionContent }
#else
            selectionContent
#endif
        }
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
                .accessibilityAddTraits(.isHeader)
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
                .accessibilityAddTraits(.isHeader)
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
