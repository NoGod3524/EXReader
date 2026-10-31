// SPDX-License-Identifier: MIT
import Foundation
import Darwin
import CEXReaderC02

enum HostC02Action {
    case create, enroll, recoverEnrollment
}

struct HostC02Failure: Error, LocalizedError {
    let detail: String
    var errorDescription: String? { detail }
}

enum HostC02Admission {
    private static let mobileAuthority = ".exreader-c02-admission"

#if os(iOS)
    static func mobile<T>(path: URL, _ body: (OpaquePointer, String) throws -> T) throws -> T {
        guard let raw = NSHomeDirectory().withCString({ realpath($0, nil) }) else {
            throw HostC02Failure(detail: "无法确认应用书库目录")
        }
        let home = String(cString: raw)
        free(raw)
        var expected = stat()
        guard home.withCString({ lstat($0, &expected) }) == 0,
              expected.st_uid == geteuid(), UInt32(expected.st_mode) & UInt32(S_IFMT) == UInt32(S_IFDIR) else {
            throw HostC02Failure(detail: "应用书库目录身份无效")
        }
        let descriptor = home.withCString { Darwin.open($0, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC) }
        guard descriptor >= 0 else { throw HostC02Failure(detail: "应用书库目录无法打开") }
        defer { close(descriptor) }
        var actual = stat()
        guard fstat(descriptor, &actual) == 0, actual.st_dev == expected.st_dev,
              actual.st_ino == expected.st_ino else {
            throw HostC02Failure(detail: "应用书库目录已改变")
        }
#if EXR_APPLE_C02_REVIEW
        HostC02Review.scopes.append(["canonical_home":home,"device":UInt64(truncatingIfNeeded:actual.st_dev),
            "inode":UInt64(truncatingIfNeeded:actual.st_ino),"mode":UInt32(actual.st_mode),
            "uid":actual.st_uid,"euid":geteuid(),"fd_cloexec":fcntl(descriptor,F_GETFD) & FD_CLOEXEC != 0,
            "expected_device":UInt64(truncatingIfNeeded:expected.st_dev),
            "expected_inode":UInt64(truncatingIfNeeded:expected.st_ino)])
#endif
        var identity = pc02_identity(device: UInt64(truncatingIfNeeded: actual.st_dev), inode: UInt64(truncatingIfNeeded: actual.st_ino))
        var scope: OpaquePointer?
        guard pc02_scope_create(descriptor, &identity, &scope) != 0, let scope else {
            throw HostC02Failure(detail: "应用书库目录不满足访问要求")
        }
        defer { _ = pc02_scope_close(scope) }
        let parent = path.deletingLastPathComponent().path
        guard let resolved = parent.withCString({ realpath($0, nil) }) else {
            throw HostC02Failure(detail: "书库所在目录无法确认")
        }
        let directory = String(cString: resolved)
        free(resolved)
        let full = directory + "/" + path.lastPathComponent
        guard directory == home || directory.hasPrefix(home + "/"),
              !path.lastPathComponent.isEmpty, !path.lastPathComponent.utf8.contains(0) else {
            throw HostC02Failure(detail: "书库不在当前应用目录内")
        }
        let relative = String(full.dropFirst(home.count + 1))
        return try body(scope, relative)
    }
#endif

    static func open(path: URL) throws -> OpaquePointer {
        var result: OpaquePointer?
        let opened: Int32
#if os(iOS)
        opened = try mobile(path: path) { scope, relative in
            mobileAuthority.withCString { authority in
                relative.withCString { pc02_open_in(scope, authority, $0, UInt32(PC02_SHARED), nil, nil, &result) }
            }
        }
#else
        opened = path.path.withCString { pc02_sdk_open_user($0, &result) }
#endif
        guard opened != 0, let result else {
            throw HostC02Failure(detail: "书库尚未登记，或存在待恢复操作")
        }
        guard pc02_check(result) != 0 else {
            _ = pc02_close(result)
            throw HostC02Failure(detail: "书库访问状态已改变")
        }
        return result
    }

    static func perform(_ action: HostC02Action, path: URL) throws {
        var proof = pc02_sdk_proof()
        let accepted: Int32
#if os(iOS)
        accepted = try mobile(path: path) { scope, relative in
            mobileAuthority.withCString { authority in
                relative.withCString { library in
                    switch action {
                    case .create: return pc02_sdk_enroll_in(scope, authority, library, 1, &proof)
                    case .enroll: return pc02_sdk_enroll_in(scope, authority, library, 0, &proof)
                    case .recoverEnrollment: return pc02_sdk_recover_enrollment_in(scope, authority, library, &proof)
                    }
                }
            }
        }
#else
        accepted = path.path.withCString { library in
            switch action {
            case .create: return pc02_sdk_enroll_user(library, 1, &proof)
            case .enroll: return pc02_sdk_enroll_user(library, 0, &proof)
            case .recoverEnrollment: return pc02_sdk_recover_enrollment_user(library, &proof)
            }
        }
#endif
        guard accepted != 0 else {
            throw HostC02Failure(detail: "书库登记或恢复未完成，原文件已保留")
        }
    }
}

final class HostC02Lease {
    let handle: OpaquePointer
    let libraryPath: String

    init(path: URL) throws {
        let admitted = try HostC02Admission.open(path: path)
        guard let path = pc02_library_path(admitted), path.pointee != 0 else {
            _ = pc02_close(admitted)
            throw HostC02Failure(detail: "书库实际路径无法确认")
        }
        handle = admitted
        libraryPath = String(cString: path)
    }

    func check() throws {
        guard pc02_check(handle) != 0 else { throw HostC02Failure(detail: "书库访问状态已改变") }
    }

    deinit { _ = pc02_close(handle) }
}

#if EXR_APPLE_C02_REVIEW
enum HostC02Review {
    static var sdkOpenCalls = 0
    static var scopes: [[String: Any]] = []
}
#endif
