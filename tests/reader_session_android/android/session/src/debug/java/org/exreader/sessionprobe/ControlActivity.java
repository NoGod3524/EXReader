// SPDX-License-Identifier: MIT
package org.exreader.sessionprobe;
import android.app.Activity;
import android.os.Bundle;
public final class ControlActivity extends Activity {
    @Override public void onCreate(Bundle saved){super.onCreate(saved);SessionController.get(this);}
}
