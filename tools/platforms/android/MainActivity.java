package org.exreader.platformprobe;

import android.app.Activity;
import android.os.Bundle;
import android.util.Log;
import android.widget.TextView;
import java.io.*;
import org.exreader.EXReader;

public final class MainActivity extends Activity {
    static { System.loadLibrary("exreader"); System.loadLibrary("platform_probe"); }
    private static native int probe(String book, String font, String directory, boolean reopen);

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        TextView view = new TextView(this);
        setContentView(view);
        boolean reopen = getIntent().getBooleanExtra("reopen", false);
        try {
            File directory = getFilesDir();
            for (String name : new String[]{"smoke.epub", "font.otf"}) {
                File destination = new File(directory, name);
                if (!reopen) {
                    try (InputStream input = getAssets().open(name); OutputStream output = new FileOutputStream(destination)) {
                        byte[] buffer = new byte[16384]; int n;
                        while ((n = input.read(buffer)) != -1) output.write(buffer, 0, n);
                    }
                }
            }
            // Exercise the shipped Java/JNI binding as well as the shared C probe.
            Log.i("EXRPlatform", "PASS shipped_jni version=" + EXReader.version() + " pid=" + android.os.Process.myPid());
            int result = probe(new File(directory, "smoke.epub").getPath(), new File(directory, "font.otf").getPath(), directory.getPath(), reopen);
            try (BufferedReader reader = new BufferedReader(new FileReader(new File(directory, reopen ? "reopen.log" : "create.log")))) {
                String line;
                while ((line = reader.readLine()) != null) Log.i("EXRPlatform", line);
            }
            Log.i("EXRPlatform", "EXIT_CODE=" + result + " reopen=" + reopen);
            view.setText(result == 0 ? "PASS: " + (reopen ? "5/5" : "create; ready to reopen") : "FAIL: see logcat");
        } catch (Throwable failure) {
            Log.e("EXRPlatform", "FAIL runtime", failure);
            view.setText("FAIL: " + failure);
        }
    }
}
