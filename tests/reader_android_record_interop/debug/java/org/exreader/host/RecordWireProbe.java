// SPDX-License-Identifier: MIT
package org.exreader.host;

/** Review only: exact committed public revision bytes on the existing owner. */
final class RecordWireProbe {
    static {System.loadLibrary("exreader_product");}
    static native byte[][] outbox(long owner);
    static native byte[] retained(long owner,String revision);
    static native String[] ownerIdentity(long owner);
}
