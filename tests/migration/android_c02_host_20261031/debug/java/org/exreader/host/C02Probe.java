// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.content.Context;
import java.io.File;

/** Debug-only native gate actor; this does not claim to run a migration. */
final class C02Probe {
    static { System.loadLibrary("exreader_host"); }
    static final byte[] ORIGINAL = "C02 Android actual SDK original.\n".getBytes(java.nio.charset.StandardCharsets.UTF_8);
    private interface Operation<T> { T run(NativeAdmission.Container container); }
    private static <T> T in(Context context, Operation<T> operation) throws Exception {
        try (NativeAdmission.Container container = new NativeAdmission.Container(context, new File(context.getFilesDir(), "library.db"))) {
            return operation.run(container);
        }
    }
    static boolean canOwn(Context context) throws Exception {
        return in(context, c -> nativeCanOwn(c.descriptor.getFd(), c.device, c.inode, c.relative));
    }
    static long begin(Context context) throws Exception {
        return in(context, c -> nativeBegin(c.descriptor.getFd(), c.device, c.inode, c.relative));
    }
    static boolean recover(Context context, byte[] exact) throws Exception {
        return in(context, c -> nativeRecover(c.descriptor.getFd(), c.device, c.inode, c.relative, exact));
    }
    static native byte[] pending(long owner);
    private static native boolean nativeCanOwn(int fd, long device, long inode, String path);
    private static native long nativeBegin(int fd, long device, long inode, String path);
    private static native boolean nativeRecover(int fd, long device, long inode, String path, byte[] exact);
}
