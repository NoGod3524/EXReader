// SPDX-License-Identifier: MIT
package org.exreader.tts.probe;

import android.content.Context;

/** JNI surface of the probe app: the installed consumer plus the engine bridge. */
public final class NativeTts {
    static { System.loadLibrary("tts-consumer"); }
    private NativeTts() {}
    public static native void setContext(Context context);
    public static native void setMode(int engineExpected);
    public static native int caseCount();
    public static native String caseName(int id);
    public static native int runCase(int id);
    public static native String caseDetail();
    public static native int rotationBegin();
    public static native int rotationFinish();
}
