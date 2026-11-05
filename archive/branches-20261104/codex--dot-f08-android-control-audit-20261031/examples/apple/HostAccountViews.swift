// SPDX-License-Identifier: MIT
import SwiftUI

// Read-only presentation routing; account/session ownership is unchanged.
struct HostReadingRouteKey: PreferenceKey {
    static var defaultValue = false
    static func reduce(value: inout Bool, nextValue: () -> Bool) { value = value || nextValue() }
}
private struct HostChooseAccountKey: EnvironmentKey {
    static let defaultValue: (() -> Void)? = nil
}
private struct HostAccountChooserVisibleKey: EnvironmentKey { static let defaultValue = false }
extension EnvironmentValues {
    var hostChooseAccount: (() -> Void)? {
        get { self[HostChooseAccountKey.self] }
        set { self[HostChooseAccountKey.self] = newValue }
    }
    var hostAccountChooserVisible: Bool {
        get { self[HostAccountChooserVisibleKey.self] }
        set { self[HostAccountChooserVisibleKey.self] = newValue }
    }
}

struct HostAccountRoot: View {
    @ObservedObject var accounts: HostAccounts
    @State private var choosing = false
    @State private var reading = false

    var body: some View {
        VStack(spacing: 0) {
            if !reading {
            HStack {
                Button { choosing = true } label: {
                    Text(accounts.current == nil ? "本地书库" : "云盘书库").font(.caption)
#if os(iOS)
                        .frame(minHeight: 44).contentShape(Rectangle())
#endif
                }
                    .accessibilityIdentifier("account.choose")
                    .accessibilityLabel(Text(accounts.current.map { "云盘书库，" + $0.root } ?? "本地书库"))
                Spacer()
            }.padding(.horizontal).padding(.top, 8)
            }
            HostRootView(profile: accounts.current, accounts: accounts).id(accounts.current?.id ?? "local")
        }
        .onPreferenceChange(HostReadingRouteKey.self) { reading = $0 }
        .environment(\.hostChooseAccount, { choosing = true })
        .environment(\.hostAccountChooserVisible, choosing)
        .sheet(isPresented: $choosing) { HostAccountChooser(accounts: accounts) }
    }
}

private struct HostAccountChooser: View {
    @ObservedObject var accounts: HostAccounts
    @Environment(\.dismiss) private var dismiss
    @State private var root = ""
    @State private var username = ""
    @State private var password = ""
    @State private var remember = true
    @State private var failure = ""
    @State private var updating: HostAccountProfile?
    private enum Field: Hashable { case root, username, password }
    @FocusState private var focused: Field?

    var body: some View {
        ScrollView {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("书库账号").font(.title2).accessibilityAddTraits(.isHeader)
                Spacer()
                Button("完成") { dismiss() }.accessibilityIdentifier("account.done")
            }
            Button("本地书库") { accounts.choose(nil); dismiss() }.accessibilityIdentifier("account.local")
            ForEach(accounts.profiles) { profile in
                HStack {
                    Button(profile.root) { accounts.choose(profile); dismiss() }
                        .lineLimit(1).accessibilityIdentifier("account.open.\(profile.id)")
                    Spacer()
                    Button("更新授权") { updating = profile; root = profile.root; failure = "" }
                        .accessibilityIdentifier("account.update.\(profile.id)")
                }
            }
            Divider()
            Text(updating == nil ? "连接 WebDAV" : "更新授权").font(.headline)
            TextField("HTTPS 文件夹地址，以 / 结尾", text: $root)
                .textFieldStyle(.roundedBorder).disabled(updating != nil)
                .focused($focused, equals: .root).submitLabel(.done)
                .disableAutocorrection(true)
#if os(iOS)
                .textInputAutocapitalization(.never).keyboardType(.URL)
#endif
                .accessibilityIdentifier("account.root")
            TextField("用户名（匿名访问可留空）", text: $username)
                .textFieldStyle(.roundedBorder).focused($focused, equals: .username).submitLabel(.done)
                .disableAutocorrection(true)
#if os(iOS)
                .textInputAutocapitalization(.never)
#endif
                .accessibilityIdentifier("account.username")
            SecureField("密码或应用专用密码", text: $password)
                .textFieldStyle(.roundedBorder).focused($focused, equals: .password).submitLabel(.done)
                .accessibilityIdentifier("account.password")
            Toggle("保存到钥匙串", isOn: $remember).accessibilityIdentifier("account.remember")
            Button(updating == nil ? "连接" : "保存授权") {
                do {
                    if let updating { try accounts.updateCredentials(updating, username: username, password: password, remember: remember) }
                    else { try accounts.create(root: root, username: username, password: password, remember: remember) }
                    username = ""; password = ""; failure = ""; updating = nil
                    dismiss()
                } catch { failure = error.localizedDescription }
            }.accessibilityIdentifier("account.connect")
            if !accounts.message.isEmpty { Text(accounts.message).font(.caption).foregroundColor(.secondary) }
            if !failure.isEmpty { Text(failure).foregroundColor(.red).accessibilityIdentifier("account.error") }
            Text("每个云盘账号使用独立书库。同步由你手动发起；本地书库始终可离线使用。")
                .font(.caption).foregroundColor(.secondary)
        }.padding()
        }
        .accessibilityIdentifier("account.form")
#if os(macOS)
        .frame(minWidth: 360, idealWidth: 480, minHeight: 480)
#endif
        .onSubmit { focused = nil }
        .onDisappear { username = ""; password = ""; root = ""; updating = nil; failure = ""; focused = nil }
    }
}

struct HostSyncControls: View {
    @ObservedObject var session: HostAccountSession
    let preparing: Bool
    var compact = false
    @State private var showingDetails = false
    let synchronize: () -> Void
    var body: some View {
        HStack {
            if !compact {
            VStack(alignment: .leading) {
                Text(session.preparing ? session.state : preparing ? "正在接收书架" : session.state).font(.caption)
                    .accessibilityIdentifier("account.sync.state")
                if !session.message.isEmpty { Text(session.message).font(.caption2).foregroundColor(.secondary) }
            }
            Spacer()
            } else {
                Text(session.preparing ? session.state : preparing ? "正在接收书架" : session.state).font(.caption2).lineLimit(1)
                    .accessibilityIdentifier("account.sync.state")
                    .accessibilityValue(Text(session.message))
            }
            Button { showingDetails = true } label: {
                Image(systemName: "info.circle").frame(width: 44, height: 44)
            }.accessibilityIdentifier("account.sync.details").accessibilityLabel(Text("同步详情"))
            if session.running || session.preparing {
                Button { session.cancel() } label: {
                    if compact { Image(systemName: "stop.circle").font(.system(size: 20)).frame(width: 44, height: 44).contentShape(Rectangle()) }
                    else { Text("取消同步") }
                }.accessibilityIdentifier("account.sync.cancel").accessibilityLabel(Text("取消同步"))
            } else {
                Button { synchronize() } label: {
                    if compact { Image(systemName: "arrow.triangle.2.circlepath").font(.system(size: 20)).frame(width: 44, height: 44).contentShape(Rectangle()) }
                    else { Text(session.canRetry ? "重试同步" : "同步") }
                }.disabled(preparing || session.preparing).accessibilityIdentifier("account.sync.start").accessibilityLabel(Text(session.canRetry ? "重试同步" : "同步"))
            }
        }.padding(.horizontal, compact ? 0 : 16)
        .sheet(isPresented: $showingDetails) {
            HostSyncDetails(session: session)
        }
    }
}

private struct HostSyncDetails: View {
    @ObservedObject var session: HostAccountSession
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Text("同步详情").font(.title2).accessibilityAddTraits(.isHeader)
                    Spacer()
                    Button("完成") { dismiss() }.accessibilityIdentifier("account.sync.details.done")
                }
                Text(session.state).accessibilityIdentifier("account.sync.details.state")
                if !session.detailReason.isEmpty {
                    Text(session.detailReason).accessibilityIdentifier("account.sync.details.reason")
                }
                if session.detailHTTPStatus > 0 {
                    Text("HTTP \(session.detailHTTPStatus)").accessibilityIdentifier("account.sync.details.http")
                }
                Text("尝试 \(session.detailAttempt)").accessibilityIdentifier("account.sync.details.attempt")
                Text("已读分片 \(session.completedShards)/256").accessibilityIdentifier("account.sync.details.shards")
                Text("操作 \(session.steps)，推送 \(session.detailPushed)，拉取 \(session.detailPulled)")
                    .accessibilityIdentifier("account.sync.details.operations")
                Text(session.message).font(.caption)
                Text("这里是本轮会话的操作计数，可能包含重复记录；一轮完成不代表整个书库已同步。")
                    .font(.caption).foregroundColor(.secondary)
            }.padding()
        }
#if os(macOS)
        .frame(minWidth: 360, idealWidth: 480, minHeight: 320)
#endif
    }
}
