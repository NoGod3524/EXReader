// SPDX-License-Identifier: MIT
package org.exreader.host;
/** Debug-only public-revision receive for honest unsafe-graph UI fixtures. */
final class NativeReadingProbe {
    static {System.loadLibrary("exreader_product");}
    static native String[] identity();
    static native int receive(long owner,byte[] validatedWire);
}
