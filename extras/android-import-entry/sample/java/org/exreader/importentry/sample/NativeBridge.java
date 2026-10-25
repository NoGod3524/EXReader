package org.exreader.importentry.sample;

/**
 * Installed sample. All methods must be called on the single thread that opened the handle (the host's SDK owner);
 * the ImportEntry owner executor should be that thread.
 */
public final class NativeBridge {
    private NativeBridge() { }

    /** Opens the host library; returns 0 on failure. */
    public static native long open(String libraryPath);

    /** Returns {exr_status, bookId, created}. Does not delete the staged file. */
    public static native long[] commit(long handle, String stagedPath, int exrFormat, String title, long size);

    public static native String lastError(long handle);

    public static native void close(long handle);
}
