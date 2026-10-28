// SPDX-License-Identifier: MIT
import Foundation
import Combine
import CReaderProduct

struct HostOrganizationGroup: Identifiable {
    let id: String
    let name: String
    let parent: String?
    let ordinal: UInt64
    let deleted: Bool
}

struct HostOrganizationMember: Identifiable {
    let bookKey: String
    let title: String
    let ordinal: UInt64
    let book: HostShelfBook
    var id: String { bookKey }
}

private final class OrganizationGroups { var rows: [HostOrganizationGroup] = [] }
private final class OrganizationMembers { var rows: [HostOrganizationMember] = [] }
private let organizationGroupVisit: @convention(c) (UnsafeMutableRawPointer?, UnsafePointer<reader_catalog_group_row>?) -> Int32 = { context, row in
    guard let context, let row, let id = row.pointee.id, let name = row.pointee.name else { return 1 }
    let box = Unmanaged<OrganizationGroups>.fromOpaque(context).takeUnretainedValue()
    box.rows.append(HostOrganizationGroup(id: String(cString: id), name: String(cString: name),
        parent: row.pointee.parent_id.map { String(cString: $0) }, ordinal: row.pointee.ordinal,
        deleted: row.pointee.deleted != 0))
    return 0
}
private let organizationMemberVisit: @convention(c) (UnsafeMutableRawPointer?, UnsafePointer<reader_catalog_group_book_row>?) -> Int32 = { context, row in
    guard let context, let row, let key = row.pointee.book.book_key, let title = row.pointee.book.title,
          let sort = row.pointee.book.sort_title, let author = row.pointee.book.author,
          let format = row.pointee.book.format, let bytes = Int64(exactly: row.pointee.book.source_bytes) else { return 1 }
    let box = Unmanaged<OrganizationMembers>.fromOpaque(context).takeUnretainedValue()
    let bookKey = String(cString: key), bookTitle = String(cString: title)
    let book = HostShelfBook(key: HostShelfKey(sort: String(cString: sort), key: bookKey),
        sdkID: row.pointee.book.sdk_book_id, title: bookTitle, author: String(cString: author),
        format: String(cString: format), bytes: bytes)
    box.rows.append(HostOrganizationMember(bookKey: bookKey, title: bookTitle, ordinal: row.pointee.ordinal, book: book))
    return 0
}

// Each native handle is opened, used and closed inside one queue work item.
// A dispatch queue may change OS threads between items, so no owner crosses a
// work-item boundary. The copied native snapshot retains the exact heads the
// user observed; it is never replaced by a fresh snapshot at commit time.
final class HostOrganization: ObservableObject {
    @Published private(set) var busy = false
    @Published private(set) var message = ""
    @Published private(set) var groups: [HostOrganizationGroup] = []
    @Published private(set) var members: [HostOrganizationMember] = []
    @Published private(set) var prepared = false
    @Published private(set) var groupsMore = false
    @Published private(set) var membersMore = false
    @Published private(set) var pending = false
    @Published private(set) var membershipPresent = false
    @Published private(set) var membershipDeleted = false
    @Published private(set) var needsBootstrap = false
    @Published private(set) var stagedForReview = false
    private let queue = DispatchQueue(label: "org.exreader.organization")
    private let productURL: URL
    private var queued = 0
    private var lastGroups: (Int, String?, Bool)?
    private var lastMembers: (Int, String)?
    private var snapshot: OpaquePointer?
    private var snapshotIdentity = ""

    init(productURL: URL) {
        self.productURL = productURL
        inspectPending()
    }
    deinit { if let snapshot { reader_metadata_snapshot_free(snapshot) } }

    private var pendingURL: URL { productURL.deletingLastPathComponent().appendingPathComponent("organization.pending") }
    private func detail<T>(_ tuple: inout T) -> String {
        withUnsafeBytes(of: &tuple) { bytes in
            let chars = bytes.bindMemory(to: CChar.self)
            guard let base = chars.baseAddress else { return "" }
            return String(cString: base)
        }
    }
    private func failure(_ code: reader_metadata_status, _ error: inout reader_metadata_error) -> Error {
        let text = detail(&error.message)
        return NSError(domain: "EXReaderOrganization", code: Int(code.rawValue),
                       userInfo: [NSLocalizedDescriptionKey: text.isEmpty ? "整理操作失败" : text])
    }
    private func withOwner<T>(_ body: (OpaquePointer) throws -> T) throws -> T {
        var owner: OpaquePointer?, error = reader_metadata_error()
        let status = productURL.path.withCString { product in pendingURL.path.withCString { pending in
#if EXR_APPLE_RAW3
            reader_metadata_open_raw_v3(product, pending, &owner, &error)
#else
            reader_metadata_open(product, pending, &owner, &error)
#endif
        } }
        guard status == READER_METADATA_OK, let owner else { throw failure(status, &error) }
        var closeOwner: OpaquePointer? = owner
        defer { _ = reader_metadata_close(&closeOwner, &error) }
        return try body(owner)
    }
    private func run<T>(_ work: @escaping () throws -> T, publish: @escaping (T) -> Void) {
        queued += 1; busy = true
        queue.async {
            let result = Result { try work() }
            DispatchQueue.main.async {
                self.queued -= 1; self.busy = self.queued != 0
                switch result {
                case .success(let value): publish(value)
                case .failure(let error): self.prepared = false; self.message = error.localizedDescription
                }
            }
        }
    }
    private func inspectPending() {
        run({ try self.withOwner { owner in
            var result = reader_metadata_result(), error = reader_metadata_error()
            let code = reader_metadata_pending(owner, &result, &error)
            guard code == READER_METADATA_OK || code == READER_METADATA_NO_PENDING else { throw self.failure(code, &error) }
            return code == READER_METADATA_OK
        } }, publish: { self.pending = $0; if $0 { self.message = "有待恢复的整理操作。" } })
    }
    private func clearSnapshot() {
        if let snapshot { reader_metadata_snapshot_free(snapshot) }
        snapshot = nil; snapshotIdentity = ""
    }
    private func checkedKind(_ value: Int) throws -> reader_group_kind {
        guard (0...2).contains(value) else { throw HostError.invalidInput("分组类型无效") }
        return reader_group_kind(rawValue: UInt32(value))
    }
    private func checkedOperation(_ value: Int) throws -> reader_command_operation {
        guard (0...2).contains(value) else { throw HostError.invalidInput("操作无效") }
        return reader_command_operation(rawValue: UInt32(value))
    }
    func refresh(kind: Int, parent: String? = nil, deleted: Bool = false) {
        lastGroups = (kind, parent, deleted)
        groups = []; groupsMore = false
        loadGroups(kind: kind, parent: parent, deleted: deleted, after: nil)
    }
    func nextGroups(kind: Int, parent: String? = nil, deleted: Bool = false) {
        guard groupsMore, let last = groups.last else { return }
        loadGroups(kind: kind, parent: parent, deleted: deleted, after: last)
    }
    private func loadGroups(kind: Int, parent: String?, deleted: Bool, after: HostOrganizationGroup?) {
        run({
            guard (0...2).contains(kind) else { throw HostError.invalidInput("分组类型无效") }
            var catalog: OpaquePointer?, error = reader_catalog_error()
            guard self.productURL.path.withCString({ reader_catalog_open($0, &catalog, &error) }) == 0, let handle = catalog else { throw HostError.invalidInput("无法打开产品书库") }
            defer { _ = reader_catalog_close(&catalog, &error) }
            let box = OrganizationGroups(), context = Unmanaged.passUnretained(box).toOpaque()
            let groupKind = reader_catalog_group_kind(rawValue: UInt32(kind))
            let code: Int32
            if deleted {
                if let after { code = after.id.withCString { reader_catalog_removed_groups_page(handle, groupKind, $0, 1, 200, organizationGroupVisit, context, &error) } }
                else { code = reader_catalog_removed_groups_page(handle, groupKind, nil, 1, 200, organizationGroupVisit, context, &error) }
            } else {
                code = hostProductStrings([parent ?? "", after?.id ?? ""]) { p in
                    var cursor = reader_catalog_group_cursor(); cursor.ordinal = after?.ordinal ?? 0; cursor.id = p[1]
                    return withUnsafePointer(to: &cursor) { cp in
                        reader_catalog_groups_page(handle, groupKind, parent == nil || parent == "" ? nil : p[0], after == nil ? nil : cp, 1, 200, organizationGroupVisit, context, &error)
                    }
                }
            }
            guard code == 0 else { throw HostError.invalidInput("无法读取分组") }
            return box.rows
        }, publish: { self.groups.append(contentsOf: $0); self.groupsMore = $0.count == 200 })
    }
    func refreshMembers(kind: Int, groupID: String) {
        lastMembers = (kind, groupID)
        members = []; membersMore = false
        loadMembers(kind: kind, groupID: groupID, after: nil)
    }
    func nextMembers(kind: Int, groupID: String) {
        guard membersMore, let last = members.last else { return }
        loadMembers(kind: kind, groupID: groupID, after: last)
    }
    private func loadMembers(kind: Int, groupID: String, after: HostOrganizationMember?) {
        run({
            guard (0...2).contains(kind) else { throw HostError.invalidInput("分组类型无效") }
            var catalog: OpaquePointer?, error = reader_catalog_error()
            guard self.productURL.path.withCString({ reader_catalog_open($0, &catalog, &error) }) == 0, let handle = catalog else { throw HostError.invalidInput("无法打开产品书库") }
            defer { _ = reader_catalog_close(&catalog, &error) }
            let box = OrganizationMembers(), context = Unmanaged.passUnretained(box).toOpaque()
            let code = hostProductStrings([groupID, after?.bookKey ?? ""]) { p in
                var cursor = reader_catalog_member_cursor(); cursor.ordinal = after?.ordinal ?? 0; cursor.book_key = p[1]
                return withUnsafePointer(to: &cursor) { cp in
                    reader_catalog_group_books_page(handle, reader_catalog_group_kind(rawValue: UInt32(kind)), p[0], after == nil ? nil : cp, nil, 0, 1, 200, organizationMemberVisit, context, &error)
                }
            }
            guard code == 0 else { throw HostError.invalidInput("无法读取分组成员") }
            return box.rows
        }, publish: { self.members.append(contentsOf: $0); self.membersMore = $0.count == 200 })
    }
    func prepareGroup(kind: Int, id: String) {
        prepared = false
        run({
            self.clearSnapshot()
            return try self.withOwner { owner in
                var error = reader_metadata_error(), snap: OpaquePointer?
                let code = try id.withCString { reader_metadata_prepare_group(owner, try self.checkedKind(kind), $0, &snap, &error) }
                guard code == READER_METADATA_OK, let snap else { if let snap { reader_metadata_snapshot_free(snap) }; throw self.failure(code, &error) }
                self.snapshot = snap; self.snapshotIdentity = "g:\(kind):\(id)"
                return true
            }
        }, publish: { self.prepared = $0; self.message = "已读取分组版本。" })
    }
    func prepareMembership(kind: Int, groupID: String, bookKey: String) {
        prepared = false; needsBootstrap = false
        membershipPresent = false; membershipDeleted = false
        run({
            self.clearSnapshot()
            return try self.withOwner { owner in
                var error = reader_metadata_error(), snap: OpaquePointer?
                let code = try hostProductStrings([groupID, bookKey]) { p in reader_metadata_prepare_membership(owner, try self.checkedKind(kind), p[0], p[1], &snap, &error) }
                if code == READER_METADATA_NEEDS_BOOTSTRAP {
                    if let snap { reader_metadata_snapshot_free(snap) }
                    return (false, false, false, true)
                }
                guard code == READER_METADATA_OK, let snap else { if let snap { reader_metadata_snapshot_free(snap) }; throw self.failure(code, &error) }
                guard let view = reader_metadata_snapshot_view(snap) else { reader_metadata_snapshot_free(snap); throw HostError.invalidInput("无法读取成员版本") }
                let present = view.pointee.present != 0, deleted = view.pointee.deleted != 0
                self.snapshot = snap; self.snapshotIdentity = "m:\(kind):\(groupID):\(bookKey)"
                return (true, present, deleted, false)
            }
        }, publish: { self.prepared = $0.0; self.membershipPresent = $0.1; self.membershipDeleted = $0.2; self.needsBootstrap = $0.3; self.message = $0.3 ? "书籍需要验证原件后建立历史。" : "已读取成员版本。" })
    }
    private func finish(_ owner: OpaquePointer, _ staged: reader_metadata_status, _ result: inout reader_metadata_result, _ error: inout reader_metadata_error) throws -> (Bool, String) {
        guard staged == READER_METADATA_OK else { throw failure(staged, &error) }
#if EXR_APPLE_HOST_REVIEW
        // Review harness can terminate the process at the durable boundary.
        if ProcessInfo.processInfo.environment["EXR_ORGANIZATION_PAUSE_AFTER_STAGE"] == "1" {
            DispatchQueue.main.async { self.stagedForReview = true }
            Thread.sleep(forTimeInterval: 30)
        }
#endif
        let status = reader_metadata_finish_pending(owner, &result, &error)
        if status == READER_METADATA_OK { return (false, "整理操作已保存。") }
        let text = detail(&error.message)
        return (true, result.committed != 0 ? "操作已提交，清理待恢复。\(text)" : "操作待恢复。\(text)")
    }
    func commitGroup(operation: Int, kind: Int, id: String, name: String, parent: String? = nil, ordinal: UInt64 = 0) {
        run({ try self.withOwner { owner in
            guard let snap = self.snapshot, self.snapshotIdentity == "g:\(kind):\(id)" else { throw HostError.invalidInput("请先读取此分组的版本") }
            var error = reader_metadata_error(), result = reader_metadata_result()
            let status = try hostProductStrings([id, name, parent ?? ""]) { p -> reader_metadata_status in
                var command = reader_group_command(); command.operation = try self.checkedOperation(operation); command.kind = try self.checkedKind(kind)
                command.id = p[0]; command.name = p[1]; command.parent_id = parent == nil || parent == "" ? nil : p[2]; command.ordinal = ordinal
                return reader_metadata_stage_group(owner, snap, &command, &result, &error)
            }
            self.clearSnapshot()
            return try self.finish(owner, status, &result, &error)
        } }, publish: { self.prepared = false; self.pending = $0.0; self.message = $0.1; if !$0.0, let query = self.lastGroups { self.refresh(kind: query.0, parent: query.1, deleted: query.2) } })
    }
    func commitMembership(operation: Int, kind: Int, groupID: String, bookKey: String, ordinal: UInt64 = 0) {
        run({ try self.withOwner { owner in
            guard let snap = self.snapshot, self.snapshotIdentity == "m:\(kind):\(groupID):\(bookKey)" else { throw HostError.invalidInput("请先读取此成员的版本") }
            var error = reader_metadata_error(), result = reader_metadata_result()
            let status = try hostProductStrings([groupID, bookKey]) { p -> reader_metadata_status in
                var command = reader_membership_command(); command.operation = try self.checkedOperation(operation); command.kind = try self.checkedKind(kind)
                command.group_id = p[0]; command.book_key = p[1]; command.ordinal = ordinal
                return reader_metadata_stage_membership(owner, snap, &command, &result, &error)
            }
            self.clearSnapshot()
            return try self.finish(owner, status, &result, &error)
        } }, publish: { self.prepared = false; self.pending = $0.0; self.message = $0.1; if !$0.0 { self.membershipPresent = operation != 1; self.membershipDeleted = operation == 1; if let query = self.lastMembers { self.refreshMembers(kind: query.0, groupID: query.1) } } })
    }
    func reportError(_ text: String) { message = text }
#if EXR_APPLE_HOST_REVIEW
    // Exercise a real independent writer while the user's earlier snapshot
    // remains held. This entry point is only present in review builds.
    func reviewCompetingRename(kind: Int, groupID: String) {
        run({ try self.withOwner { owner in
            var error = reader_metadata_error(), snap: OpaquePointer?, result = reader_metadata_result()
            let code = try groupID.withCString { reader_metadata_prepare_group(owner, try self.checkedKind(kind), $0, &snap, &error) }
            guard code == READER_METADATA_OK, let snap else {
                if let snap { reader_metadata_snapshot_free(snap) }
                throw self.failure(code, &error)
            }
            defer { reader_metadata_snapshot_free(snap) }
            guard let view = reader_metadata_snapshot_view(snap) else { throw HostError.invalidInput("无法读取竞争版本") }
            var command = view.pointee.group
            let status = "Concurrent Shelf".withCString { name in
                command.operation = READER_COMMAND_PUT; command.name = name
                return reader_metadata_stage_group(owner, snap, &command, &result, &error)
            }
            guard status == READER_METADATA_OK else { throw self.failure(status, &error) }
            let finished = reader_metadata_finish_pending(owner, &result, &error)
            guard finished == READER_METADATA_OK else { throw self.failure(finished, &error) }
            return true
        } }, publish: { _ in self.message = "竞争版本已提交。" })
    }
#endif
    func recoverEdit() {
        run({ try self.withOwner { owner in
            var result = reader_metadata_result(), error = reader_metadata_error()
            let status = reader_metadata_finish_pending(owner, &result, &error)
            if status == READER_METADATA_OK || status == READER_METADATA_NO_PENDING { return (false, "待处理操作已恢复。") }
            let text = self.detail(&error.message)
            return (true, result.committed != 0 ? "操作已提交，清理仍待恢复。\(text)" : "恢复未完成。\(text)")
        } }, publish: { self.pending = $0.0; self.message = $0.1
            if !$0.0 {
                if let query = self.lastGroups { self.refresh(kind: query.0, parent: query.1, deleted: query.2) }
                if let query = self.lastMembers { self.refreshMembers(kind: query.0, groupID: query.1) }
            }
        })
    }
    func abandonPending() {
        run({ try self.withOwner { owner in
            var error = reader_metadata_error()
            let status = reader_metadata_abandon_pending(owner, &error)
            guard status == READER_METADATA_OK || status == READER_METADATA_NO_PENDING else { throw self.failure(status, &error) }
            return true
        } }, publish: { _ in self.pending = false; self.message = "未提交的待处理操作已放弃。" })
    }
    func bootstrap(bookKey: String, format: String, sha256: String, bytes: UInt64) {
        run({ try self.withOwner { owner in
            var error = reader_metadata_error(), snap: OpaquePointer?, result = reader_metadata_result()
            let code = bookKey.withCString { reader_metadata_prepare_book(owner, $0, &snap, &error) }
            if code == READER_METADATA_OK { if let snap { reader_metadata_snapshot_free(snap) }; return (false, "书籍历史已存在；请重新读取成员版本。") }
            guard code == READER_METADATA_NEEDS_BOOTSTRAP, let snap else { if let snap { reader_metadata_snapshot_free(snap) }; throw self.failure(code, &error) }
            defer { reader_metadata_snapshot_free(snap) }
            let status = hostProductStrings([format, sha256]) { p -> reader_metadata_status in
                var source = reader_metadata_verified_source(); source.format = p[0]; source.source_sha256 = p[1]; source.source_bytes = bytes
                return reader_metadata_stage_bootstrap(owner, snap, &source, &result, &error)
            }
            return try self.finish(owner, status, &result, &error)
        } }, publish: { self.pending = $0.0; self.needsBootstrap = $0.0; self.message = $0.0 ? $0.1 : "原件验证完成，书籍历史已建立；请重新读取成员版本。" })
    }
}
