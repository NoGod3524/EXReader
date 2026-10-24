// SPDX-License-Identifier: MIT
package org.exreader.host;
/** Debug-only independent native registry observation for lifecycle tests. */
final class NativeSyncProbe {
    static {System.loadLibrary("exreader_product");}
    static native int sessions();
}
