// SPDX-License-Identifier: MIT
package org.exreader.sessionprobe;
final class NativeSdk {
    static {System.loadLibrary("session-sdk-owner");}
    private NativeSdk(){}
    static native long open(String path);
    static native long[] importFile(long owner,String path,int format);
    static native String[] exportOriginal(long owner,long book,String path,long cancelAt,long maximum);
    static native void close(long owner);
}
