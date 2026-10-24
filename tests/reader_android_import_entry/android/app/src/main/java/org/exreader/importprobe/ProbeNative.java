package org.exreader.importprobe;

final class ProbeNative {
    private ProbeNative() { }

    /** Streams the stored original of a book and compares it byte for byte with the staged file. */
    static native boolean equalsStaged(long handle, long bookId, String stagedPath);
}
