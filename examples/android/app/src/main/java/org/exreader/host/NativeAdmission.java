// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.content.Context;
import android.os.ParcelFileDescriptor;
import android.os.Process;
import android.system.ErrnoException;
import android.system.Os;
import android.system.OsConstants;
import android.system.StructStat;
import java.io.File;
import java.io.IOException;

/** The OS Context, never an import or migration package, chooses this scope. */
final class NativeAdmission {
    static { System.loadLibrary("exreader_host"); }
    static final int CREATE = 1, ENROLL = 2, RECOVER_ENROLLMENT = 3;
    static final String AUTHORITY = "no_backup/c02-admission";

    static final class Required extends IllegalStateException {
        Required(String message) { super(message); }
    }

    static final class Container implements AutoCloseable {
        final ParcelFileDescriptor descriptor;
        final long device, inode;
        final String relative;
        Container(Context context, File database) throws IOException {
            File supplied = context.getApplicationContext().getDataDir().getAbsoluteFile();
            File canonical = supplied.getCanonicalFile();
            String path = database.getAbsolutePath();
            String original = supplied.getPath() + File.separator;
            String actual = canonical.getPath() + File.separator;
            // Preserve the leaf spelling. Native openat rejects symlinks and "..".
            if (path.startsWith(original)) relative = path.substring(original.length());
            else if (path.startsWith(actual)) relative = path.substring(actual.length());
            else throw new Required("Library must remain inside this application's storage");
            descriptor = ParcelFileDescriptor.open(canonical, ParcelFileDescriptor.MODE_READ_ONLY);
            try {
                StructStat identity = Os.fstat(descriptor.getFileDescriptor());
                if (identity.st_uid != Process.myUid() || !OsConstants.S_ISDIR(identity.st_mode))
                    throw new Required("Application storage identity differs");
                device = identity.st_dev;
                inode = identity.st_ino;
            } catch (ErrnoException | RuntimeException error) {
                descriptor.close();
                throw new IOException("Cannot verify application storage", error);
            }
        }
        @Override public void close() throws IOException { descriptor.close(); }
    }

    private static volatile Runnable attemptObserver;
    static void observeAttemptForTest(Runnable observer) {
        if (!BuildConfig.C02_ADMISSION_TEST) throw new IllegalStateException("Test actor is disabled");
        attemptObserver = observer;
    }

    static long open(Context context, File database) {
        try (Container container = new Container(context, database)) {
            return nativeOpen(container.descriptor.getFd(), container.device, container.inode, container.relative);
        } catch (IOException error) {
            throw new Required("Cannot verify application storage: " + error.getMessage());
        } finally {
            Runnable observer = attemptObserver;
            if (BuildConfig.C02_ADMISSION_TEST && observer != null) observer.run();
        }
    }

    /** A separate, explicit user action; ordinary open never calls this. */
    static void initialize(Context context, File database, int operation) {
        if (operation < CREATE || operation > RECOVER_ENROLLMENT) throw new IllegalArgumentException("Unknown library action");
        try (Container container = new Container(context, database)) {
            nativeEnroll(container.descriptor.getFd(), container.device, container.inode, container.relative, operation);
        } catch (IOException error) {
            throw new Required("Cannot verify application storage: " + error.getMessage());
        }
    }

    static void event(Context context, File database, String event) {
        if (!BuildConfig.DEBUG) return;
        try (Container container = new Container(context, database)) {
            nativeEvent(container.descriptor.getFd(), event);
        } catch (IOException error) { throw new IllegalStateException(error); }
    }

    private static native long nativeOpen(int contextFd, long device, long inode, String libraryRelative);
    private static native void nativeEnroll(int contextFd, long device, long inode, String libraryRelative, int operation);
    private static native void nativeEvent(int contextFd, String event);
}
