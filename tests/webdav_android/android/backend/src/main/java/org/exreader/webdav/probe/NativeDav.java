// SPDX-License-Identifier: MIT
package org.exreader.webdav.probe;
public final class NativeDav {
    static { System.loadLibrary("webdav-consumer"); }
    private NativeDav(){}
    public static native int bind();
    public static native byte[] request(String root,String auth,String dir,String action,String resource,String filename,long[] limits,boolean nativeThread);
}
