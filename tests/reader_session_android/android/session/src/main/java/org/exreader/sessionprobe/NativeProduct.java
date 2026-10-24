// SPDX-License-Identifier: MIT
package org.exreader.sessionprobe;
final class NativeProduct {
    static {System.loadLibrary("session-product-owner");}
    private NativeProduct(){}
    static native int bind();
    static native byte[] provider();
    static native byte[] prepareBook(String product,String pending,String format,String sha,long bytes,String title,String author,String sortTitle);
    static native byte[] inspectBook(String product,String key);
    static native byte[] projectBook(String product,String key,String head,String sortTitle);
    static native byte[] attach(String product,String format,String sha,long bytes,long sdkId,String location,String title,String author,String sortTitle);
    static native byte[] outbox(String product);
    static native long create(String product,String cache,String originals,String account,String root,String authorization,int timeout);
    static native byte[] command(long session,int command);
    static native byte[] stats();
}
