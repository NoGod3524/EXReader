// SPDX-License-Identifier: MIT
package org.exreader.host;
final class Raw3Probe {
    static {System.loadLibrary("exreader_product");}
    static native String[] family(long owner);
}
