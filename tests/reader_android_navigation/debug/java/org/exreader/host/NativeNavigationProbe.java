// SPDX-License-Identifier: MIT
package org.exreader.host;
final class NativeNavigationProbe {
    static {System.loadLibrary("exreader_host");}
    static native int live();
    static native String[] identity();
    static native String cfi(long library,long book,int mode);
}
