// SPDX-License-Identifier: MIT
package org.exreader.host;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;
import java.util.Arrays;
import java.util.UUID;

/** Immutable original retrieval only. Runs on the transfer owner, never the SDK owner. */
final class SyncOriginal {
    static File receive(NativeSync.RemoteBook book, File directory, String root,
                        byte[] authorization, HostTask task) throws Exception {
        File staged = null;
        try {
            task.check();
            if (!book.receivable() || !book.sha.matches("[0-9a-f]{64}")
                    || !book.format.matches("txt|epub|pdf|mobi|docx|fb2|rtf|cbz|html")
                    || !book.key.equals(book.format + ":" + book.sha)
                    || book.bytes > 128L * 1024 * 1024)
                throw new IOException("远端原件身份或大小不可接收");
            if (!directory.isDirectory() && !directory.mkdirs()) throw new IOException("原件目录不可用");
            File cached = new File(directory, book.sha + "." + book.format);
            if (valid(cached, book, task)) return cached;
            String name = "receive-" + UUID.randomUUID() + ".part";
            staged = new File(directory, name);
            if (authorization == null) throw new IOException("原件不在本机，请连接云盘后重试");
            int code = NativeSync.fetchOriginal(root, authorization,
                    "exreader-sync-v1/objects/" + book.sha.substring(0, 2) + "/" + cached.getName(),
                    directory.getAbsolutePath(), name, task);
            task.check();
            if (code != 0) throw new IOException("原件下载未完成，可重试（" + code + "）");
            if (!valid(staged, book, task)) throw new IOException("原件完整性校验失败，未替换本机书籍");
            task.check();
            // Only verified bytes replace the cache; imported SDK sources and reading records are untouched.
            Files.move(staged.toPath(), cached.toPath(), StandardCopyOption.ATOMIC_MOVE,
                    StandardCopyOption.REPLACE_EXISTING);
            staged = null;
            return cached;
        } finally {
            if (authorization != null) Arrays.fill(authorization, (byte) 0);
            if (staged != null) Files.deleteIfExists(staged.toPath());
        }
    }
    static boolean valid(File file, NativeSync.RemoteBook book, HostTask task) throws IOException {
        task.check();
        return file.isFile() && file.length() == book.bytes
                && BookStore.syncFileHash(file, task).equals(book.sha);
    }
}
