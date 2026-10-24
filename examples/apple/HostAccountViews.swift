// SPDX-License-Identifier: MIT
import SwiftUI

struct HostAccountRoot: View {
    @ObservedObject var accounts: HostAccounts
    @State private var choosing = false

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Button(accounts.current == nil ? "本地书库" : "云盘书库") { choosing = true }
                    .accessibilityIdentifier("account.choose")
                    .accessibilityLabel(Text(accounts.current.map { "云盘书库，" + $0.root } ?? "本地书库"))
                Spacer()
            }.padding(.horizontal).padding(.top, 8)
            HostRootView(profile: accounts.current, accounts: accounts).id(accounts.current?.id ?? "local")
        }
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
    private enum Field { case root, username, password }
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
                .accessibilityIdentifier("account.root")
            TextField("用户名（匿名访问可留空）", text: $username)
                .textFieldStyle(.roundedBorder).focused($focused, equals: .username).submitLabel(.done)
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
#if os(macOS)
        .frame(minWidth: 360, idealWidth: 480, minHeight: 480)
#endif
        .onSubmit { focused = nil }
        .onDisappear { username = ""; password = "" }
    }
}

struct HostSyncControls: View {
    @ObservedObject var session: HostAccountSession
    let preparing: Bool
    let synchronize: () -> Void
    var body: some View {
        HStack {
            VStack(alignment: .leading) {
                Text(preparing || session.preparing ? "正在准备原书" : session.state).font(.caption)
                    .accessibilityIdentifier("account.sync.state")
                if !session.message.isEmpty { Text(session.message).font(.caption2).foregroundColor(.secondary) }
            }
            Spacer()
            if session.running { Button("取消同步") { session.cancel() }.accessibilityIdentifier("account.sync.cancel") }
            else { Button("同步") { synchronize() }.disabled(preparing || session.preparing).accessibilityIdentifier("account.sync.start") }
        }.padding(.horizontal)
    }
}
