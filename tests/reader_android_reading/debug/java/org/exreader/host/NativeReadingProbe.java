// SPDX-License-Identifier: MIT
package org.exreader.host;
/** Debug-only public-revision receive for honest unsafe-graph UI fixtures. */
final class NativeReadingProbe {
    static {System.loadLibrary("exreader_product");}
    static native String[] identity();
    static int receive(long owner,byte[] wire){try{byte[] digest=java.security.MessageDigest.getInstance("SHA-256").digest(wire);StringBuilder hash=new StringBuilder(64);for(byte value:digest){hash.append(Character.forDigit((value>>>4)&15,16));hash.append(Character.forDigit(value&15,16));}return nativeReceive(owner,wire,hash.toString());}catch(java.security.NoSuchAlgorithmException impossible){throw new AssertionError(impossible);}}
    private static native int nativeReceive(long owner,byte[] wire,String expectedSha256);
}
