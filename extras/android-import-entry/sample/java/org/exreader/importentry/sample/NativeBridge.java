// SPDX-License-Identifier: MIT
package org.exreader.importentry.sample;

import android.content.Context;
import android.os.ParcelFileDescriptor;
import android.os.Process;
import android.system.Os;
import android.system.OsConstants;
import android.system.StructStat;
import java.io.File;

/** All calls use one SDK owner thread. The OS Context fixes this app's authority. */
public final class NativeBridge {
    private NativeBridge() {}
    private interface Operation<T> { T run(int fd, long device, long inode) throws Exception; }
    private static <T> T context(Context supplied, boolean initialize, Operation<T> operation) {
        Context app = supplied.getApplicationContext();
        if (initialize) { app.getFilesDir(); app.getNoBackupFilesDir(); }
        try (ParcelFileDescriptor descriptor = ParcelFileDescriptor.open(app.getDataDir().getCanonicalFile(),
                ParcelFileDescriptor.MODE_READ_ONLY)) {
            StructStat identity = Os.fstat(descriptor.getFileDescriptor());
            if (identity.st_uid != Process.myUid() || !OsConstants.S_ISDIR(identity.st_mode))
                throw new IllegalStateException("Application storage identity differs");
            return operation.run(descriptor.getFd(), identity.st_dev, identity.st_ino);
        } catch (RuntimeException error) { throw error; }
        catch (Exception error) { throw new IllegalStateException("Cannot verify application storage", error); }
    }

    /** Opens files/library.db only after SH admission; creates or enrolls nothing. */
    public static long open(Context context) {
        return context(context, false, (fd, device, inode) -> nativeOpen(fd, device, inode));
    }
    /** Separate explicit new-library user action or fresh test-fixture seed. */
    public static void create(Context context) { initialize(context, 1); }
    /** Separate explicit verification action for an existing, unregistered library. */
    public static void enroll(Context context) { initialize(context, 2); }
    /** Explicit recovery of an interrupted initial registration only. */
    public static void recoverEnrollment(Context context) { initialize(context, 3); }
    private static void initialize(Context context, int operation) {
        if (!context(context, operation != 3, (fd, device, inode) -> nativeInitialize(fd, device, inode, operation)))
            throw new IllegalStateException("Explicit library verification failed; evidence was preserved");
    }
    /** A package-selected path cannot choose a native authority. */
    @Deprecated public static long open(String path) {
        throw new IllegalArgumentException("Use the OS Context and an explicitly initialized library");
    }
    private static native long nativeOpen(int contextFd, long device, long inode);
    private static native boolean nativeInitialize(int contextFd, long device, long inode, int operation);
    /** Returns {exr_status, bookId, created}. Does not delete the staged file. */
    public static native long[] commit(long handle, String stagedPath, int exrFormat, String title, long size);
    public static native String lastError(long handle);
    public static native void close(long handle);
}
