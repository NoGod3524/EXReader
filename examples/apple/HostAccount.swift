// SPDX-License-Identifier: MIT
import Foundation
import Combine
import CReaderProduct

struct HostAccountProfile: Codable, Equatable, Identifiable {
    let id: String
    let root: String
    var anonymous: Bool? = nil

    func directory(in base: URL) -> URL {
        base.appendingPathComponent("accounts", isDirectory: true).appendingPathComponent(id, isDirectory: true)
    }
}

// Owns only profile metadata and native session handles, never an SDK object.
final class HostAccounts: ObservableObject {
    @Published private(set) var profiles: [HostAccountProfile] = []
    @Published private(set) var selected: String?
    @Published private(set) var message = ""
    private var credentials: OpaquePointer?
    private var transient: [String: Data] = [:]
    private var sessions: [String: HostAccountSession] = [:]
    private let folder: URL
    private var metadataWritable = true

    init(folder: URL? = nil) {
        self.folder = folder ?? FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("EXReader", isDirectory: true)
        if exr_credentials_open("org.exreader.host.webdav", &credentials) != EXR_CRED_OK { credentials = nil }
        do {
            let url = self.folder.appendingPathComponent("accounts.json")
            if FileManager.default.fileExists(atPath: url.path) {
                let size = try url.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0
                guard size > 0, size <= 64 * 1024 else { throw HostError.invalidInput("账号记录大小无效") }
                let loaded = try JSONDecoder().decode([HostAccountProfile].self, from: Data(contentsOf: url))
                guard loaded.count <= 16, Set(loaded.map(\.id)).count == loaded.count,
                      loaded.allSatisfy({ UUID(uuidString: $0.id)?.uuidString.lowercased() == $0.id }) else {
                    throw HostError.invalidInput("账号记录身份无效")
                }
                for profile in loaded { try validateRoot(profile.root) }
                profiles = loaded
                let previous = UserDefaults.standard.string(forKey: "EXRSelectedAccount")
                selected = loaded.contains(where: { $0.id == previous }) ? previous : nil
            }
        } catch {
            metadataWritable = false
            message = "账号记录无法读取；原文件已保留，请先恢复该文件"
        }
    }

    deinit {
        if let credentials { exr_credentials_close(credentials) }
        for var value in transient.values { value.withUnsafeMutableBytes { exr_credentials_wipe($0.baseAddress, $0.count) } }
    }

    var current: HostAccountProfile? { profiles.first { $0.id == selected } }

    private func validateRoot(_ root: String) throws {
        guard !root.utf8.contains(0), root.utf8.count <= 8192 else { throw HostError.invalidInput("云盘地址无效") }
        var client: OpaquePointer?, error = exr_webdav_error()
        let result = root.withCString { text -> exr_webdav_status in
            var config = exr_webdav_config(); config.root_url = text
            return exr_webdav_create(&config, &client, &error)
        }
        if let client { exr_webdav_free(client) }
        guard result == EXR_DAV_OK else { throw HostError.invalidInput("请输入以 / 结尾的 HTTPS WebDAV 文件夹地址") }
    }

    private func encodedProfiles(_ values: [HostAccountProfile]) throws -> Data {
        guard metadataWritable else { throw HostError.invalidInput("账号记录无法读取；请先恢复原文件") }
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys]
        let data = try encoder.encode(values)
        guard data.count <= 64 * 1024 else { throw HostError.invalidInput("账号记录超过 64 KiB，请缩短云盘地址或减少账号") }
        return data
    }

    private func persistProfiles(_ data: Data) throws {
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        try data.write(to: folder.appendingPathComponent("accounts.json"), options: .atomic)
    }

    func create(root: String, username: String, password: String, remember: Bool) throws {
        guard profiles.count < 16 else { throw HostError.invalidInput("账号数量已达 16 个") }
        try validateRoot(root)
        guard !profiles.contains(where: { $0.root == root }) else { throw HostError.invalidInput("该云盘账号已经存在") }
        let profile = HostAccountProfile(id: UUID().uuidString.lowercased(), root: root, anonymous: username.isEmpty && password.isEmpty)
        let updated = profiles + [profile]
        let metadata = try encodedProfiles(updated)
        try updateCredentials(profile, username: username, password: password, remember: remember)
        do {
            try persistProfiles(metadata)
        } catch {
            transient.removeValue(forKey: profile.id)
            if let credentials { _ = profile.id.withCString { exr_credentials_delete(credentials, $0) } }
            throw error
        }
        profiles = updated
        choose(profile)
    }

    func updateCredentials(_ profile: HostAccountProfile, username: String, password: String, remember: Bool) throws {
        guard metadataWritable else { throw HostError.invalidInput("账号记录无法读取；请先恢复原文件") }
        guard !username.contains(":"), !username.utf8.contains(0), !password.utf8.contains(0) else {
            throw HostError.invalidInput("用户名或密码包含不支持的字符")
        }
        var authorization = username.isEmpty && password.isEmpty ? Data() :
            Data(("Basic " + Data((username + ":" + password).utf8).base64EncodedString()).utf8)
        defer { authorization.withUnsafeMutableBytes { exr_credentials_wipe($0.baseAddress, $0.count) } }
        guard authorization.count <= Int(EXR_CREDENTIALS_SECRET_MAX) else { throw HostError.invalidInput("授权信息过长") }
        var updated = profiles
        var metadata: Data?
        if let index = profiles.firstIndex(where: { $0.id == profile.id }), profiles[index].anonymous != authorization.isEmpty {
            updated[index].anonymous = authorization.isEmpty
            metadata = try encodedProfiles(updated)
        }
        sessions[profile.id]?.close()
        // The metadata file contains only an independent UUID and the root URL.
        transient[profile.id] = authorization
        var stored = false, removed = true
        if remember, !authorization.isEmpty, let credentials {
            stored = profile.id.withCString { account in
                authorization.withUnsafeBytes { bytes in
                    exr_credentials_put(credentials, account, bytes.bindMemory(to: UInt8.self).baseAddress, bytes.count) == EXR_CRED_OK
                }
            }
        } else if let credentials {
            let result = profile.id.withCString { exr_credentials_delete(credentials, $0) }
            removed = result == EXR_CRED_OK || result == EXR_CRED_NOT_FOUND
        }
        if let metadata {
            try persistProfiles(metadata)
            profiles = updated
        }
        if authorization.isEmpty { message = removed ? "匿名连接，未保存授权信息" : "匿名连接；钥匙串中的旧授权未能移除" }
        else if stored { message = "授权信息已保存到钥匙串" }
        else if remember { message = "本次使用新的授权，钥匙串更新未完成" }
        else { message = removed ? "授权信息仅保留在本次运行中" : "本次使用临时授权；钥匙串中的旧授权未能移除" }
    }

    func authorization(for profile: HostAccountProfile) throws -> Data {
        if let value = transient[profile.id] { return value }
        if profiles.first(where: { $0.id == profile.id })?.anonymous == true { return Data() }
        guard let credentials else { throw HostError.invalidInput("请重新输入此账号的授权信息") }
        var buffer = [UInt8](repeating: 0, count: Int(EXR_CREDENTIALS_SECRET_MAX)), count = 0
        defer { buffer.withUnsafeMutableBytes { exr_credentials_wipe($0.baseAddress, $0.count) } }
        let result = profile.id.withCString { account in
            buffer.withUnsafeMutableBufferPointer { exr_credentials_get(credentials, account, $0.baseAddress, $0.count, &count) }
        }
        guard result == EXR_CRED_OK else { throw HostError.invalidInput("请重新输入此账号的授权信息") }
        return Data(buffer.prefix(count))
    }

    func choose(_ profile: HostAccountProfile?) {
        guard selected != profile?.id else { return }
        for session in sessions.values { session.close() }
        selected = profile?.id
        UserDefaults.standard.set(selected, forKey: "EXRSelectedAccount")
    }

    func controller(for profile: HostAccountProfile) -> HostAccountSession {
        if let value = sessions[profile.id] { return value }
        let value = HostAccountSession()
        sessions[profile.id] = value
        return value
    }
}

final class HostAccountSession: ObservableObject {
    @Published private(set) var state = "未同步"
    @Published private(set) var running = false
    @Published private(set) var preparing = false
    @Published private(set) var steps: UInt64 = 0
    @Published private(set) var completedSweeps: UInt64 = 0
    @Published private(set) var completedShards: UInt32 = 0
    @Published private(set) var message = ""
    private var handle: OpaquePointer?
#if EXR_APPLE_WAVE3
    private let wave3HandleLock = NSRecursiveLock()

    func wave3SyncSnapshot(catalog: HostCatalog) throws -> HostWave3SyncSnapshot? {
        wave3HandleLock.lock()
        defer { wave3HandleLock.unlock() }
        guard let handle else { return nil }
        return try HostWave3Worker.sync(session: handle, catalog: catalog)
    }
#endif
    private var timer: Timer?
    private var closeRequested = false
    private var completion: (() -> Void)?
    private var cancelPreparation: (() -> Void)?

    func beginPreparation(cancel: @escaping () -> Void) throws {
        guard !running, !preparing, !closeRequested else { throw HostError.invalidInput("此账号已在准备、同步或关闭") }
        preparing = true; cancelPreparation = cancel
    }

    func finishPreparation() { preparing = false; cancelPreparation = nil }

    deinit {
        timer?.invalidate()
        if let handle {
            _ = reader_session_request_close(handle)
            // Closing is bounded by the native transport deadline; never join on UI.
            DispatchQueue.global(qos: .utility).async {
                var value: OpaquePointer? = handle
                var snapshot = reader_session_snapshot()
                while reader_session_observe(handle, &snapshot) == READER_SESSION_OK && snapshot.state != READER_SESSION_CLOSED {
                    Thread.sleep(forTimeInterval: 0.05)
                }
                _ = reader_session_destroy(&value)
            }
        }
    }

    func start(profile: HostAccountProfile, directory: URL, authorization: Data, completed: @escaping () -> Void) throws {
#if EXR_APPLE_WAVE3
        wave3HandleLock.lock()
        defer { wave3HandleLock.unlock() }
#endif
        guard !running, !preparing, !closeRequested else { throw HostError.invalidInput("同步会话正在准备、运行或关闭") }
        if handle == nil {
            let privateDirectory = directory.appendingPathComponent("sync", isDirectory: true)
            let originals = directory.appendingPathComponent("sync-originals", isDirectory: true)
            for path in [privateDirectory, originals] { try FileManager.default.createDirectory(at: path, withIntermediateDirectories: true) }
            let product = directory.appendingPathComponent("reader-catalog.db").path
            guard let secret = String(data: authorization, encoding: .utf8), !secret.utf8.contains(0),
                  !secret.contains("\r"), !secret.contains("\n") else { throw HostError.invalidInput("授权信息无效，请重新输入") }
            let result = product.withCString { productPath in privateDirectory.path.withCString { privatePath in
                originals.path.withCString { originalsPath in profile.id.withCString { account in
                    profile.root.withCString { root in secret.withCString { auth -> reader_session_status in
                        var config = reader_session_config()
                        config.product_path = productPath; config.private_directory = privatePath
                        config.original_directory = originalsPath; config.account_id = account
                        config.dav.root_url = root; config.dav.authorization = auth; config.dav.timeout_ms = 30000
#if EXR_APPLE_RAW3
                        return reader_session_create_raw_v3(&config, &handle)
#else
                        return reader_session_create(&config, &handle)
#endif
                    } }
                } }
            } }
            guard result == READER_SESSION_OK else { throw HostError.invalidInput("无法创建云盘同步会话") }
        }
        guard let handle, reader_session_start(handle) == READER_SESSION_OK else { throw HostError.invalidInput("云盘同步会话尚未就绪") }
        completion = completed; running = true; state = "正在同步"; message = ""
        if timer == nil {
            timer = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in self?.observe() }
        }
    }

    func cancel() { if let handle { _ = reader_session_cancel(handle) } }

    func close() {
        cancelPreparation?()
        guard let handle else { return }
        closeRequested = true
        _ = reader_session_request_close(handle)
        state = "正在关闭"
        if timer == nil { timer = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in self?.observe() } }
    }

    private func observe() {
#if EXR_APPLE_WAVE3
        guard wave3HandleLock.try() else { return }
        defer { wave3HandleLock.unlock() }
#endif
        guard let handle else { return }
        var snapshot = reader_session_snapshot()
        guard reader_session_observe(handle, &snapshot) == READER_SESSION_OK else { return }
        steps = snapshot.steps; completedSweeps = snapshot.completed_sweeps; completedShards = snapshot.completed_shards
        switch snapshot.state {
        case READER_SESSION_RUNNING: state = "正在同步"
        case READER_SESSION_CANCELLING: state = "正在取消"
        case READER_SESSION_CLOSING: state = "正在关闭"
        case READER_SESSION_CLOSED:
            state = "已关闭"; running = false
            guard reader_session_destroy(&self.handle) == READER_SESSION_OK else { return }
            closeRequested = false; timer?.invalidate(); timer = nil; completion = nil
        case READER_SESSION_FINISHED, READER_SESSION_CANCELLED, READER_SESSION_FAILED:
            let wasRunning = running; running = false
            timer?.invalidate(); timer = nil
            state = snapshot.state == READER_SESSION_FINISHED ? "本轮扫描完成" : snapshot.state == READER_SESSION_CANCELLED ? "已取消" : "同步失败"
            message = snapshot.state == READER_SESSION_FINISHED ? "可再次同步以接收后续变更" : "已提交的历史会保留，可手动重试"
            if wasRunning { let callback = completion; completion = nil; callback?() }
        default: break
        }
    }
}
