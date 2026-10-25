// SPDX-License-Identifier: MIT
// Coordinated, bounded copy of a picked file into an app-private staging
// directory. See docs/READER-APPLE-FILE-ENTRY.md for the full contract.
import Foundation
import CryptoKit

/// Owns one private staging directory.
///
/// Threading: stage(url:) and stage(urls:) block and must run off the main
/// thread (otherwise .calledOnMainThread). They may run concurrently; the
/// pending-limit accounting is internally locked. stageInBackground runs the
/// batch on a private serial queue and calls `completion` on that queue.
/// Re-entrancy: no callback may call close(); completion handlers may call any
/// other method. The component never creates a thread of its own other than that
/// serial queue and never touches the main thread.
///
/// Memory: one 64 KiB buffer per running copy, regardless of file size.
///
/// Commit boundary: a request exists once its `<id>.json` manifest was renamed
/// into place (after the data file was synced and renamed). Failure,
/// cancellation or a crash before that leaves at most `.tmp-*` or unreferenced
/// `<id>.data` files, which sweepOrphans() removes. Staged bytes are never
/// modified after commit and are only deleted by release(_:) or sweepOrphans().
public final class FileEntryStagingArea {
    public let directory: URL
    public let maxFileBytes: UInt64
    public let maxPendingBytes: UInt64
    public let maxPendingRequests: Int
    public let requestDownload: Bool
    private let hooks: FileEntryHooks

    private let lock = NSLock()
    private var closed = false
    private var running: [UUID: FileEntryCancellation] = [:]
    private let running_group = DispatchGroup()
    private var pendingBytes: UInt64 = 0
    private var pendingCount = 0
    private var reservedBytes: UInt64 = 0
    private var reservedCount = 0
    private let worker = DispatchQueue(label: "org.exreader.file-entry", qos: .userInitiated)

    private struct Manifest: Codable {
        var version: Int
        var id: String
        var displayName: String
        var byteCount: UInt64
        var sha256: String
        var format: String?
        var origin: String
    }

    /// Creates `directory` (mode 0700, excluded from backup) when missing and
    /// counts committed requests already staged in it. Limits can only be
    /// lowered relative to FileEntryLimits.
    public init(directory: URL, maxFileBytes: UInt64 = FileEntryLimits.maxFileBytes,
                maxPendingBytes: UInt64 = FileEntryLimits.maxPendingBytes,
                maxPendingRequests: Int = FileEntryLimits.maxPendingRequests,
                requestDownload: Bool = true, hooks: FileEntryHooks = .live) throws {
        self.directory = directory
        self.maxFileBytes = min(maxFileBytes, FileEntryLimits.maxFileBytes)
        self.maxPendingBytes = min(maxPendingBytes, FileEntryLimits.maxPendingBytes)
        self.maxPendingRequests = max(0, min(maxPendingRequests, FileEntryLimits.maxPendingRequests))
        self.requestDownload = requestDownload
        self.hooks = hooks
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true,
                                                attributes: [.posixPermissions: 0o700])
        var directoryInfo = stat()
        guard lstat(directory.path, &directoryInfo) == 0,
              (directoryInfo.st_mode & 0o170000) == 0o040000,
              directoryInfo.st_uid == geteuid(), chmod(directory.path, 0o700) == 0 else {
            throw FileEntryError.accessDenied
        }
        var root = directory
        var values = URLResourceValues()
        values.isExcludedFromBackup = true
        try? root.setResourceValues(values)
        let existing = pendingRequests()
        pendingCount = existing.count
        pendingBytes = existing.reduce(0) { $0 + $1.byteCount }
    }

    // MARK: Staging

    /// Copies one file. Blocking; see the class comment for threading.
    /// Order of work: closed/main-thread checks, security scope start, iCloud
    /// availability, coordinated read, size and kind checks on the opened
    /// descriptor, 64 KiB copy with SHA-256 and cancellation checks, source
    /// re-validation, sync, atomic commit, scope stop (also on every failure).
    public func stage(url: URL, origin: FileEntryRequest.Origin = .picker,
                      cancellation: FileEntryCancellation = FileEntryCancellation()) throws -> FileEntryRequest {
        if Thread.isMainThread { throw FileEntryError.calledOnMainThread }
        let token = try begin(cancellation)
        defer { end(token) }
        if cancellation.isCancelled { throw FileEntryError.cancelled }

        let scoped = hooks.scope.start(url)
        defer { if scoped { hooks.scope.stop(url) } }

        if hooks.ubiquity(url) == .notDownloaded {
            var requested = false
            if requestDownload {
                requested = (try? FileManager.default.startDownloadingUbiquitousItem(at: url)) != nil
            }
            throw FileEntryError.notDownloaded(downloadRequested: requested)
        }

        // Coordination can block forever on a FIFO or device node, so reject those first.
        var kind = stat()
        if stat(url.path, &kind) == 0 && (kind.st_mode & 0o170000) != 0o100000 { throw FileEntryError.notRegularFile }

        let coordinator = NSFileCoordinator(filePresenter: nil)
        cancellation.onCancel { coordinator.cancel() }
        var coordinationError: NSError?
        var outcome: Result<FileEntryRequest, FileEntryError>?
        coordinator.coordinate(readingItemAt: url, options: [], error: &coordinationError) { readable in
            outcome = self.copy(source: readable, displayName: Self.diskName(url),
                                origin: origin, cancellation: cancellation)
        }
        if let outcome = outcome { return try outcome.get() }
        if cancellation.isCancelled { throw FileEntryError.cancelled }
        let code = coordinationError?.code ?? -1
        if let error = coordinationError, error.domain == NSCocoaErrorDomain {
            if code == NSUserCancelledError { throw FileEntryError.cancelled }
            if code == NSFileNoSuchFileError || code == NSFileReadNoSuchFileError { throw FileEntryError.notFound }
            if code == NSFileReadNoPermissionError { throw FileEntryError.accessDenied }
        }
        throw FileEntryError.coordination(code: code)
    }

    /// Copies each URL in order. One failure never discards the others. At most
    /// FileEntryLimits.maxBatchCount entries are attempted; later entries are
    /// .tooManyFiles. After cancellation or close() the rest are .cancelled /
    /// .closed without being opened. Result i belongs to urls[i].
    public func stage(urls: [URL], origin: FileEntryRequest.Origin = .picker,
                      cancellation: FileEntryCancellation = FileEntryCancellation()) -> [Result<FileEntryRequest, FileEntryError>] {
        var results: [Result<FileEntryRequest, FileEntryError>] = []
        results.reserveCapacity(urls.count)
        for (index, url) in urls.enumerated() {
            if index >= FileEntryLimits.maxBatchCount {
                results.append(.failure(.tooManyFiles(limit: FileEntryLimits.maxBatchCount)))
            } else if cancellation.isCancelled {
                results.append(.failure(.cancelled))
            } else {
                do {
                    results.append(.success(try stage(url: url, origin: origin, cancellation: cancellation)))
                } catch let error as FileEntryError {
                    results.append(.failure(error))
                } catch {
                    results.append(.failure(.io(errno: 0, stage: "unknown")))
                }
            }
        }
        return results
    }

    /// Same as stage(urls:) on a private serial queue; callable from the main
    /// thread. `completion` runs on that queue, never on the caller's thread.
    public func stageInBackground(urls: [URL], origin: FileEntryRequest.Origin = .picker,
                                  cancellation: FileEntryCancellation = FileEntryCancellation(),
                                  completion: @escaping ([Result<FileEntryRequest, FileEntryError>]) -> Void) {
        // Enqueue under the same lock as close: all pre-close callbacks must
        // have drained before close returns. Later calls still receive .closed.
        lock.lock()
        worker.async {
            completion(self.stage(urls: urls, origin: origin, cancellation: cancellation))
        }
        lock.unlock()
    }

    // MARK: Ownership

    /// Requests committed in this directory, including those from earlier runs.
    /// An entry needs a decodable manifest, a data file of the recorded size and,
    /// when verifyContents is true, a matching SHA-256 (reads every file).
    public func pendingRequests(verifyContents: Bool = false) -> [FileEntryRequest] {
        guard let names = try? FileManager.default.contentsOfDirectory(atPath: directory.path) else { return [] }
        var found: [FileEntryRequest] = []
        for name in names.sorted() where name.hasSuffix(".json") {
            let id = String(name.dropLast(5))
            guard Self.isID(id), let manifest = readManifest(id: id), manifest.id == id else { continue }
            let path = dataPath(id)
            var info = stat()
            guard lstat(path, &info) == 0, (info.st_mode & 0o170000) == 0o100000,
                  info.st_size >= 0, UInt64(info.st_size) == manifest.byteCount else { continue }
            if verifyContents, Self.hash(file: path) != manifest.sha256 { continue }
            found.append(FileEntryRequest(id: id, stagedPath: path, displayName: manifest.displayName,
                                          byteCount: manifest.byteCount, sha256: manifest.sha256,
                                          format: manifest.format.flatMap { FileFormatHint(rawValue: $0) },
                                          origin: FileEntryRequest.Origin(rawValue: manifest.origin) ?? .other))
        }
        return found
    }

    /// Deletes the staged bytes of a request (manifest last, so a crash in
    /// between leaves only a sweepable orphan). Idempotent. The path is derived
    /// from `request.id` only; the request's stagedPath is never trusted. Call it
    /// after the SDK import committed or when the user dropped the request.
    public func release(_ request: FileEntryRequest) {
        guard Self.isID(request.id) else { return }
        lock.lock()
        defer { lock.unlock() }
        let data = dataPath(request.id), manifest = manifestPath(request.id)
        var info = stat()
        let had = stat(manifest, &info) == 0
        let size = readManifest(id: request.id)?.byteCount ?? 0
        // Do not free a reservation unless the pair was actually removed.
        if unlink(data) != 0 && errno != ENOENT { return }
        let removed = unlink(manifest) == 0
        if had && removed {
            pendingCount = max(0, pendingCount - 1)
            pendingBytes = pendingBytes >= size ? pendingBytes - size : 0
        }
    }

    /// Removes `.tmp-*` files, data files without manifest and manifests without
    /// matching data, only for names this component creates. Returns the number
    /// of removed items. Does nothing while a copy is running.
    @discardableResult
    public func sweepOrphans() -> Int {
        lock.lock()
        defer { lock.unlock() }
        if !running.isEmpty { return 0 }
        guard let names = try? FileManager.default.contentsOfDirectory(atPath: directory.path) else { return 0 }
        let committed = Set(pendingRequests().map { $0.id })
        var removed = 0
        for name in names {
            let path = directory.appendingPathComponent(name).path
            let isData = name.hasSuffix(".data"), isManifest = name.hasSuffix(".json")
            guard isData || isManifest else { continue }
            var id = String(name.dropLast(5))
            let temporary = id.hasPrefix(".tmp-")
            if temporary { id = String(id.dropFirst(5)) }
            guard Self.isID(id) else { continue }
            if temporary || !committed.contains(id), unlink(path) == 0 { removed += 1 }
        }
        let remaining = pendingRequests()
        pendingCount = remaining.count
        pendingBytes = remaining.reduce(0) { $0 + $1.byteCount }
        return removed
    }

    /// Refuses new work, cancels running copies and waits for them to leave
    /// (each removes its temporary file). Committed requests stay staged.
    /// Idempotent. Never call it from afterChunk or from a stage() caller's own
    /// cancellation handler.
    public func close() {
        lock.lock()
        closed = true
        let active = Array(running.values)
        lock.unlock()
        for item in active { item.cancel() }
        running_group.wait()
        worker.sync {} // Includes callbacks and queued-but-not-started batches.
    }

    // MARK: Internals

    private func begin(_ cancellation: FileEntryCancellation) throws -> UUID {
        lock.lock()
        defer { lock.unlock() }
        if closed { throw FileEntryError.closed }
        let token = UUID()
        running[token] = cancellation
        running_group.enter()
        return token
    }

    private func end(_ token: UUID) {
        lock.lock()
        running[token] = nil
        lock.unlock()
        running_group.leave()
    }

    private func reserve(_ bytes: UInt64) throws {
        lock.lock()
        defer { lock.unlock() }
        if pendingCount + reservedCount + 1 > maxPendingRequests
            || pendingBytes + reservedBytes + bytes > maxPendingBytes {
            throw FileEntryError.tooManyPending
        }
        reservedCount += 1
        reservedBytes += bytes
    }

    private func unreserve(_ bytes: UInt64) {
        lock.lock()
        reservedCount -= 1
        reservedBytes -= bytes
        lock.unlock()
    }

    private func dataPath(_ id: String) -> String { directory.appendingPathComponent(id + ".data").path }
    private func manifestPath(_ id: String) -> String { directory.appendingPathComponent(id + ".json").path }

    private func readManifest(id: String) -> Manifest? {
        var info = stat()
        guard lstat(manifestPath(id), &info) == 0, (info.st_mode & 0o170000) == 0o100000,
              info.st_size > 0 && info.st_size <= 65_536 else { return nil }
        guard let data = try? Data(contentsOf: URL(fileURLWithPath: manifestPath(id))) else { return nil }
        guard let manifest = try? JSONDecoder().decode(Manifest.self, from: data), manifest.version == 1,
              manifest.byteCount <= FileEntryLimits.maxFileBytes,
              manifest.sha256.utf8.count == 64,
              manifest.sha256.utf8.allSatisfy({ (0x30...0x39).contains($0) || (0x61...0x66).contains($0) }) else { return nil }
        return manifest
    }

    /// Last path component as the file system names it (the bytes of the file-system
    /// representation), without Foundation's Unicode canonicalization.
    static func diskName(_ url: URL) -> String {
        let name: String? = url.withUnsafeFileSystemRepresentation { pointer in
            guard let pointer = pointer else { return nil }
            let bytes = Array(UnsafeBufferPointer(start: pointer, count: strlen(pointer)))
            let tail = bytes.split(separator: 0x2f, omittingEmptySubsequences: true).last ?? []
            return String(decoding: tail.map { UInt8(bitPattern: $0) }, as: UTF8.self)
        }
        return name ?? url.lastPathComponent
    }

    static func isID(_ text: String) -> Bool {
        guard text.utf8.count == 36 else { return false }
        for (index, byte) in text.utf8.enumerated() {
            if index == 8 || index == 13 || index == 18 || index == 23 {
                if byte != 0x2d { return false }
            } else if !((byte >= 0x30 && byte <= 0x39) || (byte >= 0x61 && byte <= 0x66)) {
                return false
            }
        }
        return true
    }

    static func hex(_ digest: SHA256.Digest) -> String {
        digest.map { String(format: "%02x", $0) }.joined()
    }

    static func hash(file path: String) -> String? {
        let descriptor = open(path, O_RDONLY | O_CLOEXEC)
        if descriptor < 0 { return nil }
        defer { Darwin.close(descriptor) }
        var hasher = SHA256()
        let size = FileEntryLimits.copyChunkBytes
        let buffer = UnsafeMutableRawPointer.allocate(byteCount: size, alignment: 16)
        defer { buffer.deallocate() }
        while true {
            let count = read(descriptor, buffer, size)
            if count < 0 {
                if errno == EINTR { continue }
                return nil
            }
            if count == 0 { break }
            hasher.update(bufferPointer: UnsafeRawBufferPointer(start: buffer, count: count))
        }
        return hex(hasher.finalize())
    }

    private static func fail(_ stage: String) -> FileEntryError {
        let code = errno
        switch code {
        case ENOENT, ENOTDIR: return .notFound
        case EACCES, EPERM: return .accessDenied
        default: return .io(errno: code, stage: stage)
        }
    }

    private static func sync(_ descriptor: Int32) -> Bool {
        return fcntl(descriptor, F_FULLFSYNC) == 0 || fsync(descriptor) == 0
    }

    private static func writeAll(_ descriptor: Int32, _ buffer: UnsafeRawPointer, _ count: Int) -> Bool {
        var done = 0
        while done < count {
            let written = write(descriptor, buffer + done, count - done)
            if written < 0 {
                if errno == EINTR { continue }
                return false
            }
            if written == 0 { errno = EIO; return false }
            done += written
        }
        return true
    }

    private func copy(source: URL, displayName: String, origin: FileEntryRequest.Origin,
                      cancellation: FileEntryCancellation) -> Result<FileEntryRequest, FileEntryError> {
        let format = FileFormatHint.from(pathExtension: (displayName as NSString).pathExtension)
        // O_NONBLOCK keeps a FIFO from blocking open(); the kind check follows.
        let input = open(source.path, O_RDONLY | O_CLOEXEC | O_NONBLOCK)
        if input < 0 { return .failure(Self.fail("open-source")) }
        defer { Darwin.close(input) }
        var before = stat()
        if fstat(input, &before) != 0 { return .failure(Self.fail("stat-source")) }
        if (before.st_mode & 0o170000) != 0o100000 { return .failure(.notRegularFile) }
        guard before.st_size >= 0 else { return .failure(.changedDuringCopy) }
        let size = hooks.reportedSize?(UInt64(before.st_size)) ?? UInt64(before.st_size)
        let limit = min(maxFileBytes, format?.byteLimit ?? FileEntryLimits.maxFileBytes)
        if size > limit { return .failure(.tooLarge(limit: limit)) }
        do { try reserve(size) } catch { return .failure(.tooManyPending) }
        defer { unreserve(size) }

        let id = UUID().uuidString.lowercased()
        let temp = directory.appendingPathComponent(".tmp-" + id + ".data").path
        let output = open(temp, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0o600)
        if output < 0 { return .failure(Self.fail("create-temporary")) }
        var outputOpen = true
        var keep = false
        defer {
            if outputOpen { Darwin.close(output) }
            if !keep { unlink(temp) }
        }

        var hasher = SHA256()
        let chunk = FileEntryLimits.copyChunkBytes
        let buffer = UnsafeMutableRawPointer.allocate(byteCount: chunk, alignment: 16)
        defer { buffer.deallocate() }
        var total: UInt64 = 0
        var index = 0
        while true {
            if cancellation.isCancelled { return .failure(.cancelled) }
            let count = read(input, buffer, chunk)
            if count < 0 {
                if errno == EINTR { continue }
                return .failure(Self.fail("read-source"))
            }
            if count == 0 { break }
            total += UInt64(count)
            if total > size { return .failure(.changedDuringCopy) }
            hasher.update(bufferPointer: UnsafeRawBufferPointer(start: buffer, count: count))
            if !Self.writeAll(output, buffer, count) { return .failure(Self.fail("write-staged")) }
            hooks.afterChunk?(index, source)
            index += 1
        }
        if cancellation.isCancelled { return .failure(.cancelled) }
        var after = stat()
        if total != size || fstat(input, &after) != 0 || UInt64(after.st_size) != size
            || after.st_mtimespec.tv_sec != before.st_mtimespec.tv_sec
            || after.st_mtimespec.tv_nsec != before.st_mtimespec.tv_nsec {
            return .failure(.changedDuringCopy)
        }
        if !Self.sync(output) { return .failure(Self.fail("sync-staged")) }
        if Darwin.close(output) != 0 { outputOpen = false; return .failure(Self.fail("close-staged")) }
        outputOpen = false

        let digest = Self.hex(hasher.finalize())
        let dataFinal = dataPath(id)
        if rename(temp, dataFinal) != 0 { return .failure(Self.fail("publish-data")) }
        keep = true
        let manifest = Manifest(version: 1, id: id, displayName: displayName, byteCount: size, sha256: digest,
                                format: format?.rawValue, origin: origin.rawValue)
        let manifestTemp = directory.appendingPathComponent(".tmp-" + id + ".json").path
        guard let encoded = try? JSONEncoder().encode(manifest) else {
            unlink(dataFinal)
            return .failure(.io(errno: 0, stage: "encode-manifest"))
        }
        let manifestOut = open(manifestTemp, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0o600)
        if manifestOut < 0 {
            let error = Self.fail("create-manifest")
            unlink(dataFinal)
            return .failure(error)
        }
        let wrote = encoded.withUnsafeBytes { raw -> Bool in
            guard let base = raw.baseAddress else { return true }
            return Self.writeAll(manifestOut, base, raw.count)
        }
        let synced = Self.sync(manifestOut)
        let closedManifest = Darwin.close(manifestOut) == 0
        lock.lock()
        defer { lock.unlock() }
        if closed || cancellation.isCancelled {
            unlink(manifestTemp)
            unlink(dataFinal)
            return .failure(.cancelled)
        }
        if !wrote || !synced || !closedManifest || rename(manifestTemp, manifestPath(id)) != 0 {
            let error = Self.fail("publish-manifest")
            unlink(manifestTemp)
            unlink(dataFinal)
            return .failure(error)
        }
        let folder = open(directory.path, O_RDONLY | O_CLOEXEC)
        if folder >= 0 {
            _ = Self.sync(folder)
            Darwin.close(folder)
        }
        pendingCount += 1
        pendingBytes += size
        return .success(FileEntryRequest(id: id, stagedPath: dataFinal, displayName: displayName, byteCount: size,
                                         sha256: digest, format: format, origin: origin))
    }
}
