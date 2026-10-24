// SPDX-License-Identifier: MIT
package org.exreader.host;

/** Only the existing SDK owner worker calls this installed-package bridge. */
final class NativePreferences {
    static {System.loadLibrary("exreader_host");}
    static native ReadingPreferences defaults();
    static native ReadingPreferences load(String path,HostTask task);
    static native ReadingPreferences importLegacy(float font,int zoom,int present);
    static native void validate(ReadingPreferences value);
    static native void save(ReadingPreferences value,String path,HostTask task);
    static native int effectiveTheme(ReadingPreferences value,int system);
}
