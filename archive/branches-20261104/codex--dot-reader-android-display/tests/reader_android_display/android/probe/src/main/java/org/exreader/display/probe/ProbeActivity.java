// SPDX-License-Identifier: MIT
package org.exreader.display.probe;

import android.app.Activity;
import android.os.Bundle;
import android.os.Process;
import android.view.WindowManager;
import android.widget.TextView;
import org.exreader.display.ReaderDisplay;
import org.json.JSONObject;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.file.Files;
import java.security.MessageDigest;

public class ProbeActivity extends Activity {
    static volatile ProbeActivity latest;
    static Runnable attributeHook;
    private boolean processWritten;
    private ReaderDisplay processLease;
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        latest = this;
        TextView text = new TextView(this);
        text.setText("EXReader native display probe\nWindow-only brightness and keep-screen-on");
        text.setTextSize(22); text.setPadding(24, 48, 24, 24);
        setContentView(text);
    }
    @Override public void onWindowAttributesChanged(WindowManager.LayoutParams params) {
        super.onWindowAttributesChanged(params);
        Runnable hook = attributeHook;
        if (hook != null) { attributeHook = null; hook.run(); }
    }
    @Override public void onWindowFocusChanged(boolean focused) {
        super.onWindowFocusChanged(focused);
        String mode = getIntent().getStringExtra("phase");
        if (!focused || processWritten || mode == null) return;
        processWritten = true;
        try {
            if ("seed".equals(mode)) {
                processLease = new ReaderDisplay();
                if (processLease.attach(getWindow()) != ReaderDisplay.Status.OK) throw new AssertionError("attach");
                long token = processLease.generation();
                if (processLease.configure(token, 0.73f, true) != ReaderDisplay.Status.OK) throw new AssertionError("configure");
                if (processLease.activate(token) != ReaderDisplay.Status.OK) throw new AssertionError("activate");
            }
            JSONObject result = identity(this);
            result.put("phase", mode);
            result.put("pid", Process.myPid());
            result.put("brightness", getWindow().getAttributes().screenBrightness);
            result.put("keep", (getWindow().getAttributes().flags & WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON) != 0);
            write(this, "process-" + mode + ".json", result);
        } catch (Exception e) { throw new RuntimeException(e); }
    }
    static JSONObject identity(Activity activity) throws Exception {
        JSONObject result = new JSONObject();
        result.put("source_sha", BuildConfig.SOURCE_SHA);
        result.put("run_id", BuildConfig.RUN_ID);
        result.put("run_attempt", BuildConfig.RUN_ATTEMPT);
        result.put("aar_sha256", BuildConfig.AAR_SHA256);
        byte[] bytes = Files.readAllBytes(new File(activity.getApplicationInfo().sourceDir).toPath());
        byte[] hash = MessageDigest.getInstance("SHA-256").digest(bytes);
        StringBuilder hex = new StringBuilder();
        for (byte b : hash) hex.append(String.format(java.util.Locale.ROOT, "%02x", b & 255));
        result.put("installed_apk_sha256", hex.toString());
        result.put("apk_bytes", bytes.length);
        result.put("module_version", ReaderDisplay.VERSION);
        result.put("api", android.os.Build.VERSION.SDK_INT);
        return result;
    }
    static void write(Activity activity, String name, JSONObject value) throws Exception {
        try (FileOutputStream stream = new FileOutputStream(new File(activity.getFilesDir(), name))) {
            stream.write(value.toString(2).getBytes(java.nio.charset.StandardCharsets.UTF_8));
            stream.getFD().sync();
        }
    }
}
