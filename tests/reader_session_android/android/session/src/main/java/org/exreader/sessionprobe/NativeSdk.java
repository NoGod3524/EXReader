// SPDX-License-Identifier: MIT
package org.exreader.sessionprobe;
final class NativeSdk {
    static {System.loadLibrary("session-sdk-owner");}
    private NativeSdk(){}
    static native long open(String path);
    static native long[] importFile(long owner,String path,int format);
    static native String[] exportOriginal(long owner,long book,String path,long cancelAt,long maximum);
    static native void close(long owner);
    static native byte[][] inspect(long owner,long book);
    static native long[] reopenAfterImport(long owner,long oldBook,String path,int format,boolean cancel);
    static native long readingGlobalImport(String database,String original);
    static native byte[] readingCapture(String database,long[] books,String font);
    static native long[] readingResolve(String database,long book,int mode,long unit,long start,long end,String[] selector,String font);
    static native long[] readingAudit(String database,long[] books,boolean initialize);
}
