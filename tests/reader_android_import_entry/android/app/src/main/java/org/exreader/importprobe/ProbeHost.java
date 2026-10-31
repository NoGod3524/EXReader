package org.exreader.importprobe;

import android.content.Context;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.atomic.AtomicInteger;
import org.exreader.importentry.ImportEntry;
import org.exreader.importentry.ImportError;
import org.exreader.importentry.ImportOwner;
import org.exreader.importentry.ImportTicket;
import org.exreader.importentry.ReadyRequest;
import org.exreader.importentry.ReviewChecks;
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
    private ReadyRequest staleRequest;
    private ImportEntry staleEntry;

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
                // Explicit fixture creation is separate from ordinary open.
                if (!new File(app.getFilesDir(), "library.db").exists()) NativeBridge.create(app);
                handle = NativeBridge.open(app);
                if (handle == 0) throw new IllegalStateException("Library admission refused");
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
                case "release-pending": for (ReadyRequest r : entry.pendingReady()) entry.release(r); log("released-pending"); break;
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
                case "review-ticket-races":
                    try { log("review-ticket-races", "result", ReviewChecks.ticketRaces()); }
                    catch (Throwable error) { log("review-ticket-races", "ok", false, "error", android.util.Log.getStackTraceString(error)); }
                    break;
                case "review-release-first": reviewFirstLease(); break;
                case "review-release-last": reviewLastLease(); break;
                case "review-stale-release": reviewStaleLease(); break;
                case "review-foreign-release": reviewForeignLease(); break;
                case "review-close-generation": reviewCloseGeneration(); break;
                case "review-callback-failure": reviewCallbackFailure(); break;
                case "review-fd-count": {
                    String[] files = new File("/proc/self/fd").list();
                    org.json.JSONArray targets = new org.json.JSONArray();
                    if (files != null) for (String fd : files) {
                        try { targets.put(new JSONObject().put("fd", fd).put("target", android.system.Os.readlink("/proc/self/fd/" + fd))); }
                        catch (android.system.ErrnoException | JSONException ignored) { }
                    }
                    log("review-fd-count", "count", files == null ? -1 : files.length, "targets", targets);
                    break;
                }
                default: log("command-unknown", "cmd", cmd);
            }
        });
    }

    private void reviewFirstLease() {
        List<ReadyRequest> values = entry.pendingReady();
        boolean valid = values.size() == 2 && values.get(0) != values.get(1) && values.get(0).id().equals(values.get(1).id());
        if (valid) {
            staleRequest = values.get(0); staleEntry = entry; entry.release(staleRequest);
            valid = entry.pendingReady().size() == 1 && values.get(1).file().isFile();
        }
        log("review-release-first", "ok", valid);
    }

    private void reviewCallbackFailure() {
        ImportEntry direct = null;
        try {
            AtomicInteger readyCalls = new AtomicInteger(), failedCalls = new AtomicInteger();
            AtomicReference<ImportTicket> first = new AtomicReference<>();
            CountDownLatch delivered = new CountDownLatch(2);
            direct = ImportEntry.create(app, new File(app.getFilesDir(), "direct-callback-entry"), Runnable::run, new ImportOwner() {
                public void onReady(ImportTicket ticket, ReadyRequest request) {
                    int count = readyCalls.incrementAndGet();
                    if (count == 1) first.set(ticket);
                    delivered.countDown();
                    if (count == 1) throw new IllegalStateException("expected owner callback failure");
                }
                public void onFailed(ImportTicket ticket, ImportError error) { failedCalls.incrementAndGet(); }
            });
            android.net.Uri uri = android.net.Uri.parse("content://org.exreader.importprobe.source.docs/document/txt-short");
            direct.submit(uri, "text/plain"); direct.submit(uri, "text/plain");
            if (!delivered.await(30, TimeUnit.SECONDS)) throw new AssertionError("actual direct-executor provider callbacks missing");
            List<ReadyRequest> values = direct.pendingReady();
            boolean valid = readyCalls.get() == 2 && failedCalls.get() == 0 && first.get().state() == ImportTicket.State.COMMITTED && values.size() == 2 && values.get(0).file().isFile();
            File file = values.isEmpty() ? null : values.get(0).file();
            for (ReadyRequest request : values) direct.release(request);
            valid &= file != null && !file.exists() && direct.pendingReady().isEmpty();
            log("review-callback-failure", "ok", valid, "ready_calls", readyCalls.get(), "failed_calls", failedCalls.get(), "first_state", first.get().state().name(), "released_leases", values.size());
        } catch (Throwable error) { log("review-callback-failure", "ok", false, "error", android.util.Log.getStackTraceString(error)); }
        finally { if (direct != null) { for (ReadyRequest request : direct.pendingReady()) direct.release(request); direct.close(); } }
    }

    private void reviewLastLease() {
        List<ReadyRequest> values = entry.pendingReady(); boolean valid = values.size() == 1;
        if (valid) { ReadyRequest last = values.get(0); commitOne(last); valid = !last.file().exists() && entry.pendingReady().isEmpty(); }
        log("review-release-last", "ok", valid);
    }

    private void reviewStaleLease() {
        List<ReadyRequest> values = entry.pendingReady(); boolean valid = values.size() == 1 && staleRequest != null;
        if (valid) { staleEntry.release(staleRequest); entry.release(staleRequest); valid = values.get(0).file().isFile() && entry.pendingReady().size() == 1; }
        log("review-stale-release", "ok", valid);
    }

    private void reviewForeignLease() {
        ImportEntry foreign = null; ReadyRequest other = null;
        try {
            List<ReadyRequest> values = entry.pendingReady(); if (values.size() != 1) throw new AssertionError("one current lease required");
            ReadyRequest current = values.get(0); CountDownLatch finished = new CountDownLatch(1);
            AtomicReference<ReadyRequest> result = new AtomicReference<>(); AtomicReference<ImportError> failure = new AtomicReference<>();
            foreign = ImportEntry.create(app, new File(app.getFilesDir(), "foreign-entry"), Runnable::run, new ImportOwner() {
                public void onReady(ImportTicket ticket, ReadyRequest ready) { result.set(ready); finished.countDown(); }
                public void onFailed(ImportTicket ticket, ImportError error) { failure.set(error); finished.countDown(); }
            });
            foreign.submit(android.net.Uri.parse("content://org.exreader.importprobe.source.docs/document/txt-short"), "text/plain");
            if (!finished.await(30, TimeUnit.SECONDS) || failure.get() != null) throw new AssertionError("foreign actual provider copy failed");
            other = result.get(); entry.release(other); foreign.release(current);
            boolean valid = other.file().isFile() && current.file().isFile() && entry.pendingReady().size() == 1 && foreign.pendingReady().size() == 1;
            foreign.release(other); valid &= !other.file().exists() && current.file().isFile();
            log("review-foreign-release", "ok", valid);
        } catch (Throwable error) { log("review-foreign-release", "ok", false, "error", android.util.Log.getStackTraceString(error)); }
        finally { if (foreign != null) { if (other != null) foreign.release(other); foreign.close(); } }
    }

    private void reviewCloseGeneration() {
        List<ReadyRequest> values = entry.pendingReady(); boolean valid = values.size() == 1;
        if (valid) {
            ImportEntry old = entry; ReadyRequest oldRequest = values.get(0); closeAndRecreate();
            List<ReadyRequest> recovered = entry.pendingReady(); old.release(oldRequest); entry.release(oldRequest);
            valid = recovered.size() == 1 && recovered.get(0) != oldRequest && recovered.get(0).file().isFile();
            if (valid) { ReadyRequest current = recovered.get(0); commitOne(current); valid = !current.file().exists(); }
        }
        log("review-close-generation", "ok", valid);
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
