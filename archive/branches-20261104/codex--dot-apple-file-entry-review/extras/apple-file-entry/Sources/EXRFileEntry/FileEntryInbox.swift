// SPDX-License-Identifier: MIT
// File-sharing / "Open in" Inbox discovery. Pure path logic: nothing here
// copies, locks or deletes except the explicit removeOriginal.
import Foundation

public enum FileEntryInbox {
    /// Regular files with a recognized book extension directly inside
    /// `documentsDirectory` (iTunes/Finder file sharing and the Files app) and
    /// `documentsDirectory/Inbox` ("Open in" and share-sheet copies), sorted by
    /// path, at most FileEntryLimits.maxInboxEntries. Hidden names, directories,
    /// symbolic links and every other extension (for example the app's own
    /// database) are skipped. Files are not opened, read or removed.
    public static func candidates(documentsDirectory: URL) -> [URL] {
        var result: [URL] = []
        for folder in [documentsDirectory, documentsDirectory.appendingPathComponent("Inbox", isDirectory: true)] {
            guard let names = try? FileManager.default.contentsOfDirectory(atPath: folder.path) else { continue }
            for name in names.sorted() where !name.hasPrefix(".") {
                let url = folder.appendingPathComponent(name)
                guard FileFormatHint.from(pathExtension: url.pathExtension) != nil else { continue }
                var info = stat()
                guard lstat(url.path, &info) == 0, (info.st_mode & 0o170000) == 0o100000 else { continue }
                result.append(url)
                if result.count >= FileEntryLimits.maxInboxEntries { return result }
            }
        }
        return result
    }

    public enum RemovalError: Error, Equatable {
        case notInbox
        case notRegularFile
        case failed(errno: Int32)
    }

    /// Deletes one original after the host has a committed staged request (or
    /// has decided to drop it). Never called by the component itself. Only a
    /// regular file that sits directly in Documents or Documents/Inbox is
    /// removed; any other path, directory or symbolic link is refused.
    public static func removeOriginal(_ url: URL, documentsDirectory: URL) throws {
        let parent = url.deletingLastPathComponent().standardizedFileURL.resolvingSymlinksInPath().path
        let documents = documentsDirectory.standardizedFileURL.resolvingSymlinksInPath().path
        guard parent == documents || parent == documents + "/Inbox" else { throw RemovalError.notInbox }
        var info = stat()
        guard lstat(url.path, &info) == 0 else { throw RemovalError.failed(errno: errno) }
        guard (info.st_mode & 0o170000) == 0o100000 else { throw RemovalError.notRegularFile }
        if unlink(url.path) != 0 { throw RemovalError.failed(errno: errno) }
    }
}
