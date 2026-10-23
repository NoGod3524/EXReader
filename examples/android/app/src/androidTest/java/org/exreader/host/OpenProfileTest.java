// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.app.Activity;
import android.app.Instrumentation;
import android.os.Bundle;
import android.os.SystemClock;
import android.util.Log;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;

/** Diagnostic measurement, never product acceptance or a performance budget. */
public final class OpenProfileTest extends Instrumentation {
    @Override public void onCreate(Bundle args) { super.onCreate(args); start(); }
    @Override public void onStart() {
        Bundle result = new Bundle();
        try {
            File folder = new File(getTargetContext().getCacheDir(), "open-profile-" + SystemClock.elapsedRealtime());
            if (!folder.mkdirs()) throw new IllegalStateException("profile folder");
            File file = new File(folder, "Large.epub");
            try (InputStream input = getContext().getAssets().open("mapping/Large.epub");
                 FileOutputStream out = new FileOutputStream(file)) {
                byte[] buffer = new byte[65536]; int read;
                while ((read = input.read(buffer)) != -1) out.write(buffer, 0, read);
            }
            byte[] font;
            try (InputStream input = getTargetContext().getAssets().open("Reader.otf");
                 ByteArrayOutputStream out = new ByteArrayOutputStream()) {
                byte[] buffer = new byte[65536]; int read;
                while ((read = input.read(buffer)) != -1) out.write(buffer, 0, read);
                font = out.toByteArray();
            }
            try (BookStore store = new BookStore(getTargetContext(), new File(folder, "library.db"))) {
                long id = store.importFile(file.getPath(), 4, "Large profile").id;
                HostTask task = new HostTask(() -> false);
                for (int attempt = 0; attempt < 3; attempt++) {
                    long began = SystemClock.elapsedRealtime();
                    try (BoundedEpub epub = new BoundedEpub(store.nativeLibrary(), id, font, 24)) {
                        PageLoad load = epub.restore(attempt == 0 ? 0 : 1, task);
                        load.accept();
                        if (attempt == 0) {
                            load.snapshot.bitmap.recycle();
                            load = epub.next(task); load.accept(); epub.saveProgress(load.snapshot);
                        } else if (!load.snapshot.preserveProgress || load.snapshot.restoreNotice == null
                                || !load.snapshot.restoreNotice.contains("query budget exceeded"))
                            throw new AssertionError("must preserve timeout and unresolved-selector semantics");
                        Log.i("EXROpenProfile", "restore_attempt=" + attempt + " total_ms="
                                + (SystemClock.elapsedRealtime() - began) + " start=" + load.snapshot.start);
                        load.snapshot.bitmap.recycle();
                    }
                }
            }
            result.putString("stream", "EXR_OPEN_PROFILE_DONE diagnostic_only=true accepted=false\n");
            finish(Activity.RESULT_OK, result);
        } catch (Throwable error) {
            result.putString("shortMsg", Log.getStackTraceString(error));
            result.putString("stream", "EXR_OPEN_PROFILE_FAILED " + error);
            finish(Activity.RESULT_CANCELED, result);
        }
    }
}
