package org.exreader.importprobe;

import android.content.Context;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.exreader.importentry.ImportEntry;
import org.exreader.importentry.ImportError;
import org.exreader.importentry.ImportOwner;
import org.exreader.importentry.ImportTicket;
import org.exreader.importentry.ReadyRequest;
import org.exreader.importentry.sample.NativeBridge;
import org.json.JSONException;
import org.json.JSONObject;

/**
 * Probe host: the single "sdk-owner" thread is the only one that touches the native SDK, exactly as the
 * documented integration requires. Every observation is appended to files/evidence.jsonl.
 */
final class ProbeHost implements ImportOwner {
    private static ProbeHost instance;
    private final Context app;
    private final ExecutorService sdkOwner = Executors.newSingleThreadExecutor(r -> new Thread(r, "sdk-owner"));
    private final Object logLock = new Object();
    private final File evidence;
    private volatile boolean hold;
    private long handle;
    private ImportEntry entry;
    private ImportTicket lastTicket;

    static synchronized ProbeHost get(Context context) {
        if (instance == null) instance = new ProbeHost(context.getApplicationContext());
        return instance;
    }

    private ProbeHost(Context app) {
        this.app = app;
        this.evidence = new File(app.getFilesDir(), "evidence.jsonl");
        sdkOwner.execute(() -> {
            try {
                System.loadLibrary("exreader");
                System.loadLibrary("importprobe");
                handle = NativeBridge.open(new File(app.getFilesDir(), "probe.exrlib").getAbsolutePath());
                entry = ImportEntry.create(app, app.getFilesDir(), sdkOwner, this);
                List<ReadyRequest> left = entry.pendingReady();
                StringBuilder ids = new StringBuilder();
                for (ReadyRequest r : left) ids.append(r.id()).append(' ');
                log("entry-created", "handle", handle != 0, "pending", ids.toString().trim(), "pid", android.os.Process.myPid());
                for (ReadyRequest r : left) commitOne(r);
            } catch (IOException | RuntimeException | LinkageError e) {
                log("entry-error", "error", String.valueOf(e));
            }
        });
    }

    /** Runs on the SDK owner: the entry is created there, so every later call is queued behind it. */
    void submit(android.content.Intent intent) {
        sdkOwner.execute(() -> {
            if (entry == null) { log("submit-refused", "reason", "no entry"); return; }
            List<ImportTicket> tickets = entry.submit(intent);
            if (!tickets.isEmpty()) lastTicket = tickets.get(tickets.size() - 1);
            log("submitted", "count", tickets.size(), "action", String.valueOf(intent.getAction()));
        });
    }

    void command(String cmd, String arg) {
        sdkOwner.execute(() -> {
            if (entry == null) { log("command-refused", "cmd", cmd); return; }
            switch (cmd) {
                case "hold": hold = "on".equals(arg); log("hold", "on", hold); break;
                case "commit-pending": for (ReadyRequest r : entry.pendingReady()) commitOne(r); break;
                case "cancel-all": closeAndRecreate(); break;
                case "status": log("status", "maxChunk", entry.maxChunkBytes(), "pending", entry.pendingReady().size(), "handle", handle != 0); break;
                case "cancel-last": log("cancel-last", "accepted", lastTicket != null && lastTicket.cancel()); break;
                case "submit-uri": {
                    ImportTicket t = entry.submit(android.net.Uri.parse(arg), null);
                    lastTicket = t;
                    log("submitted", "count", 1, "action", "submit-uri");
                    break;
                }
                default: log("command-unknown", "cmd", cmd);
            }
        });
    }

    /** close() releases the staging lock once the copy thread has drained, so a new entry may need a moment. */
    private void closeAndRecreate() {
        log("close-entry");
        entry.close();
        for (int attempt = 0; attempt < 50; attempt++) {
            try {
                entry = ImportEntry.create(app, app.getFilesDir(), sdkOwner, this);
                log("entry-recreated", "attempts", attempt + 1);
                return;
            } catch (IOException e) {
                try { Thread.sleep(100); } catch (InterruptedException ie) { return; }
            }
        }
        log("entry-recreate-failed");
    }

    /** Called on the main thread on purpose: the native owner check must refuse it. */
    void wrongThread() {
        long[] res = NativeBridge.commit(handle, "/nonexistent", 1, "", 1);
        log("wrong-thread", "status", res[0], "thread", Thread.currentThread().getName());
    }

    @Override public void onReady(ImportTicket ticket, ReadyRequest request) {
        log("ready", "id", request.id(), "uri", String.valueOf(ticket.uri()), "size", request.size(),
                "format", request.format().name(), "title", request.title(), "already", request.alreadyStaged(),
                "thread", Thread.currentThread().getName(), "state", ticket.state().name());
        if (!hold) commitOne(request);
    }

    @Override public void onFailed(ImportTicket ticket, ImportError error) {
        log("failed", "uri", String.valueOf(ticket.uri()), "code", error.code().name(), "message", error.message(),
                "thread", Thread.currentThread().getName(), "state", ticket.state().name());
    }

    private void commitOne(ReadyRequest r) {
        long[] res = NativeBridge.commit(handle, r.file().getAbsolutePath(), r.format().exrCode(), r.title(), r.size());
        log("commit", "id", r.id(), "status", res[0], "bookId", res[1], "created", res[2],
                "error", res[0] == 0 ? "" : NativeBridge.lastError(handle), "thread", Thread.currentThread().getName());
        if (res[0] == 0) {
            log("readback", "id", r.id(), "bookId", res[1], "equal", ProbeNative.equalsStaged(handle, res[1], r.file().getAbsolutePath()));
            entry.release(r);
            log("released", "id", r.id(), "fileExists", r.file().exists());
        }
    }

    void log(String ev, Object... kv) {
        try {
            JSONObject o = new JSONObject();
            o.put("ev", ev);
            o.put("ms", System.currentTimeMillis());
            for (int i = 0; i + 1 < kv.length; i += 2) o.put((String) kv[i], kv[i + 1]);
            synchronized (logLock) {
                try (FileOutputStream out = new FileOutputStream(evidence, true)) {
                    out.write((o + "\n").getBytes(StandardCharsets.UTF_8));
                    out.getFD().sync();
                }
            }
        } catch (JSONException | IOException ignored) {
            // Evidence is best effort here; the driver treats missing events as failures.
        }
    }
}
