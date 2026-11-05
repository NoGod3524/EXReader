// SPDX-License-Identifier: MIT
package org.exreader.tts.probe;

import android.app.Activity;
import android.os.Bundle;

import java.util.concurrent.atomic.AtomicInteger;

/**
 * Host stand-in for a reading screen: it deliberately has no android:configChanges
 * entry, so a rotation destroys and recreates it while the TTS handle lives on in
 * the process. The probe counts creations to prove the recreation was real.
 */
public final class SessionActivity extends Activity {
    private static final AtomicInteger CREATIONS = new AtomicInteger();
    private static volatile SessionActivity current;

    public static int creations() {
        return CREATIONS.get();
    }

    public static SessionActivity current() {
        return current;
    }

    @Override protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        CREATIONS.incrementAndGet();
        current = this;
    }

    @Override protected void onResume() {
        super.onResume();
        current = this;
    }

    @Override protected void onDestroy() {
        if (current == this) current = null;
        super.onDestroy();
    }
}
