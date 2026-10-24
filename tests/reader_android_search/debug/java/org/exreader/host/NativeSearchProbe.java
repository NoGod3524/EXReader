// SPDX-License-Identifier: MIT
package org.exreader.host;
/** Counter only: no native handle registry and no production entry point. */
public final class NativeSearchProbe {
    static {System.loadLibrary("exreader_host");}
    public static native int live();
    public static native String[] identity();
}
