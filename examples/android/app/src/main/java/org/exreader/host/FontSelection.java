// SPDX-License-Identifier: MIT
package org.exreader.host;

/** The one selected local font. Paging reads it on the SDK owner and leases per pager. */
final class FontSelection {
    private static volatile long library;
    private static volatile String hash="";
    private FontSelection() {}
    static void attach(long handle,String selected){hash=selected==null?"":selected;library=handle;}
    static void select(String selected){hash=selected==null?"":selected;}
    static void detach(){library=0;hash="";}
    static boolean active(){return library!=0&&!hash.isEmpty();}
    static long library(){return library;}
    static String hash(){return hash;}
}
