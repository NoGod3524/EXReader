// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.*;
import android.os.*;
import android.os.Process;
import android.system.*;
import org.json.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicReference;

/** Actual app-UID reader/borrow admission. The native actor performs no migration. */
public final class C02HostTest extends Instrumentation {
    private Context context;
    private File database, evidence;
    private final JSONArray cases = new JSONArray();
    private int checks;
    private void require(boolean value, String message) {
        ++checks;
        if (!value) throw new AssertionError(message);
    }
    private void passed(String name) throws Exception {
        cases.put(new JSONObject().put("name", name).put("passed", true));
        Bundle status = new Bundle();
        status.putString("class", getClass().getName()); status.putString("test", name);
        status.putInt("current", cases.length()); status.putInt("numtests", 14); status.putString("stream", ".");
        sendStatus(0, status);
    }
    @Override public void onCreate(Bundle arguments) { super.onCreate(arguments); start(); }
    @Override public void onStart() {
        Throwable failure = null;
        try {
            context = getTargetContext().getApplicationContext();
            require(Process.myUid() >= 10000 && Os.geteuid() == Process.myUid(), "actual app UID required; root is refused");
            database = new File(context.getFilesDir(), "library.db");
            evidence = new File(context.getFilesDir(), "c02-evidence");
            require(evidence.mkdir(), "fresh evidence directory");
            execute();
        } catch (Throwable error) { failure = error; android.util.Log.e("C02HostTest", "Admission failed", error); }
        try {
            JSONObject report = new JSONObject().put("schema", 1).put("actual_sdk", true)
                    .put("actual_android_host", true).put("actual_migration", false)
                    .put("uid", Process.myUid()).put("euid", Os.geteuid()).put("pid", Process.myPid())
                    .put("scope", context.getDataDir().getCanonicalPath())
                    .put("authority_relative", NativeAdmission.AUTHORITY).put("library_relative", "files/library.db")
                    .put("cases", cases).put("passed", cases.length()).put("checks", checks)
                    .put("failure", failure == null ? JSONObject.NULL : android.util.Log.getStackTraceString(failure));
            write(new File(evidence, "device-report.json"), report.toString(2).getBytes(StandardCharsets.UTF_8));
        } catch (Throwable error) { if (failure == null) failure = error; }
        Bundle result = new Bundle();
        result.putString("stream", failure == null ? "\nOK (14 tests)\n" : "\nFAILURES!!\n" + android.util.Log.getStackTraceString(failure));
        finish(failure == null ? Activity.RESULT_OK : Activity.RESULT_CANCELED, result);
    }

    private void execute() throws Exception {
        String start = events();
        try (BookStore ignored = new BookStore(context, database)) { throw new AssertionError("missing registration opened"); }
        catch (NativeAdmission.Required expected) {}
        require(!database.exists(), "ordinary open created library");
        require(!new File(context.getDataDir(), NativeAdmission.AUTHORITY).exists(), "ordinary open created authority");
        require(!new File(context.getFilesDir(), "reader-catalog.db").exists(), "ordinary open created catalog");
        require(count(events(), "sdk_open") == count(start, "sdk_open") && count(events(), "catalog_open") == 0,
                "missing registration reached SDK/catalog");
        passed("ordinary_missing_refuses_before_sdk_and_catalog");

        NativeAdmission.initialize(context, database, NativeAdmission.CREATE);
        require(database.isFile(), "explicit creation missing actual SDK database");
        passed("explicit_creation_uses_sdk_proof");

        File original = new File(context.getFilesDir(), "c02-original.txt");
        write(original, C02Probe.ORIGINAL);
        long book;
        try (BookStore store = new BookStore(context, database)) {
            book = store.nativeLibrary().importFile(original.getPath(), NativeLibrary.FORMAT_TXT, "C02 retained original").id;
            require(book > 0 && store.nativeLibrary().books().length == 1, "actual SDK seed");
        }
        String opened = events();
        require(opened.indexOf("event=shared_acquired ") < opened.indexOf("event=sdk_open ") &&
                opened.indexOf("event=sdk_open ") < opened.indexOf("event=catalog_open "), "catalog did not follow admission/SDK");
        passed("real_catalog_opens_after_shared_admission");

        try { new NativeLibrary(context, new File(context.getFilesDir(), "../files/library.db")); throw new AssertionError("dot escape opened"); }
        catch (NativeAdmission.Required expected) {}
        File alias = new File(context.getFilesDir(), "c02-alias.db");
        Os.symlink(database.getPath(), alias.getPath());
        try { new NativeLibrary(context, alias); throw new AssertionError("symlink alias opened"); }
        catch (NativeAdmission.Required expected) {}
        finally { java.nio.file.Files.delete(alias.toPath()); }
        passed("context_relative_dot_and_symlink_escape_refused");

        try (Actor source = new Actor(C02SourceService.class)) {
            Bundle ready = source.call(C02ActorService.SOURCE, book);
            require(ready.getInt("uid") == Process.myUid() && ready.getInt("pid") != Process.myPid(), "source actor is not app UID/separate process");
            require(ready.getBoolean("source_read_after_sdk_close"), "source not usable after actual SDK primary close");
            passed("actual_source_survives_native_sdk_primary_close");
            require(!C02Probe.canOwn(context), "other process OWNER admitted while native source live");
            snapshot("source-held");
            passed("native_source_blocks_other_process_owner");
            source.call(C02ActorService.RELEASE, 0);
            require(C02Probe.canOwn(context), "OWNER still blocked after last actual source release");
            String released = events();
            int close = released.lastIndexOf("event=sdk_close ");
            int release = released.lastIndexOf("event=source_release_end ");
            int lease = released.lastIndexOf("event=lease_close ");
            require(close >= 0 && close < release && release < lease, "lease released before native source teardown");
            snapshot("source-released");
            passed("last_native_release_allows_owner_with_ordered_events");
        }

        byte[] exact;
        try (Actor owner = new Actor(C02OwnerService.class)) {
            Bundle ready = owner.call(C02ActorService.PENDING, 0);
            exact = ready.getByteArray("pending");
            require(exact != null && exact.length > 100, "exact pending descriptor missing");
            require(ready.getInt("uid") == Process.myUid() && ready.getInt("pid") != Process.myPid(), "pending actor UID/process differs");
            require(events().contains("event=native_phase_1102 "), "PENDING durable event absent before IPC reply");
            snapshot("pending-owner-live");
            passed("pending_is_durable_before_owner_reply");
            CountDownLatch dead = new CountDownLatch(1);
            owner.endpoint.getBinder().linkToDeath(dead::countDown, 0);
            Process.killProcess(ready.getInt("pid"));
            require(dead.await(20, TimeUnit.SECONDS), "owner process death barrier timed out");
            require(!C02Probe.canOwn(context), "fresh OWNER admitted after killed PENDING owner");
            snapshot("pending-owner-dead");
            passed("process_death_retains_pending_without_auto_clean");
        }

        int sdkBefore = count(events(), "sdk_open"), catalogBefore = count(events(), "catalog_open");
        CountDownLatch attempted = new CountDownLatch(1);
        NativeAdmission.observeAttemptForTest(attempted::countDown);
        Activity activity = startActivitySync(new Intent(context, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        try {
            require(attempted.await(20, TimeUnit.SECONDS), "fresh Activity admission completion barrier timed out");
            require(count(events(), "sdk_open") == sdkBefore && count(events(), "catalog_open") == catalogBefore,
                    "fresh actual Activity reached SDK/catalog while PENDING");
        } finally {
            NativeAdmission.observeAttemptForTest(null);
            runOnMainSync(activity::finish); waitForIdleSync();
        }
        snapshot("pending-fresh-host-refused");
        passed("fresh_actual_activity_refuses_before_sdk_and_catalog");

        byte[] stale = exact.clone(); stale[0] ^= 1;
        require(!C02Probe.recover(context, stale), "stale generation descriptor recovered");
        require(!C02Probe.canOwn(context), "stale descriptor cleaned authority");
        passed("stale_pending_descriptor_is_refused");

        require(C02Probe.recover(context, exact), "fresh independent actual SDK fixture proof did not finish");
        require(C02Probe.canOwn(context), "clean authority does not admit OWNER");
        require(events().contains("event=native_phase_1202 ") && events().contains("event=native_phase_1205 "),
                "durable CLEAN/Binding events missing");
        snapshot("clean-after-independent-proof");
        passed("independent_sdk_fixture_proof_finishes_exact_pending");

        try (BookStore store = new BookStore(context, database);
             NativeLibrary.Source source = store.nativeLibrary().source(book)) {
            byte[] actual = new byte[C02Probe.ORIGINAL.length];
            require(source.size == actual.length && source.read(0, actual, actual.length) == actual.length &&
                    Arrays.equals(actual, C02Probe.ORIGINAL), "fresh actual SDK original differs after recovery");
        }
        passed("fresh_reader_after_clean_retains_exact_original");
        require(!C02Probe.recover(context, exact), "old exact descriptor replay accepted after CLEAN");
        require(C02Probe.canOwn(context), "replay damaged clean authority");
        snapshot("final");
        passed("old_descriptor_replay_cannot_reopen_clean_generation");
        require(cases.length() == 14, "scenario count differs");
    }

    private final class Actor implements AutoCloseable {
        Messenger endpoint;
        private final CountDownLatch connected = new CountDownLatch(1);
        private final ServiceConnection connection = new ServiceConnection() {
            @Override public void onServiceConnected(ComponentName name, IBinder service) {
                endpoint = new Messenger(service); connected.countDown();
            }
            @Override public void onServiceDisconnected(ComponentName name) {}
        };
        Actor(Class<?> type) throws Exception {
            require(context.bindService(new Intent(context, type), connection, Context.BIND_AUTO_CREATE), "bind actor");
            require(connected.await(20, TimeUnit.SECONDS) && endpoint != null, "actor connection barrier");
        }
        Bundle call(int operation, long book) throws Exception {
            CountDownLatch reply = new CountDownLatch(1);
            AtomicReference<Bundle> value = new AtomicReference<>();
            Messenger receiver = new Messenger(new Handler(Looper.getMainLooper(), message -> {
                value.set(message.getData()); reply.countDown(); return true;
            }));
            Message request = Message.obtain(null, operation);
            Bundle body = new Bundle(); body.putLong("book", book); request.setData(body); request.replyTo = receiver;
            endpoint.send(request);
            require(reply.await(20, TimeUnit.SECONDS), "actor response barrier");
            Bundle result = value.get();
            require(result != null && !result.containsKey("error"), result == null ? "actor missing reply" : result.getString("error"));
            return result;
        }
        @Override public void close() { context.unbindService(connection); }
    }

    private String events() throws IOException {
        File file = new File(context.getDataDir(), "c02-native-events.log");
        return file.exists() ? new String(java.nio.file.Files.readAllBytes(file.toPath()), StandardCharsets.UTF_8) : "";
    }
    private static int count(String text, String event) {
        int count = 0, cursor = 0; String needle = "event=" + event + " ";
        while ((cursor = text.indexOf(needle, cursor)) >= 0) { ++count; cursor += needle.length(); }
        return count;
    }
    private static void write(File file, byte[] bytes) throws IOException {
        try (FileOutputStream output = new FileOutputStream(file)) { output.write(bytes); output.getFD().sync(); }
    }
    private static String hex(byte[] bytes) {
        StringBuilder out = new StringBuilder();
        for (byte value : bytes) out.append(String.format(Locale.ROOT, "%02x", value & 255));
        return out.toString();
    }
    private void snapshot(String phase) throws Exception {
        File destination = new File(evidence, phase);
        require(destination.mkdir(), "snapshot directory exists");
        JSONObject observations = new JSONObject().put("phase", phase).put("pid", Process.myPid()).put("euid", Os.geteuid());
        try (NativeAdmission.Container container = new NativeAdmission.Container(context, database)) {
            observations.put("scope_fd", metadata(context.getDataDir().getCanonicalPath(),
                    Os.fstat(container.descriptor.getFileDescriptor())));
        }
        JSONArray objects = new JSONArray();
        observe(new File(context.getDataDir(), NativeAdmission.AUTHORITY), new File(destination, "authority"), objects);
        observe(database.getParentFile(), null, objects);
        observe(database, new File(destination, "library.db"), objects);
        File events = new File(context.getDataDir(), "c02-native-events.log");
        observe(events, new File(destination, "native-events.log"), objects);
        File descriptor = new File(context.getFilesDir(), "c02-pending.bin");
        if (descriptor.exists()) observe(descriptor, new File(destination, "pending-descriptor.bin"), objects);
        observations.put("objects", objects);
        write(new File(destination, "observations.json"), observations.toString(2).getBytes(StandardCharsets.UTF_8));
    }
    private JSONObject metadata(String path, StructStat st) throws Exception {
        return new JSONObject().put("path", path).put("dev", st.st_dev).put("ino", st.st_ino)
                .put("mode", st.st_mode).put("uid", st.st_uid).put("gid", st.st_gid)
                .put("nlink", st.st_nlink).put("size", st.st_size);
    }
    private void observe(File source, File copy, JSONArray observations) throws Exception {
        // Metadata is captured inside the application UID from the pinned fd.
        StructStat before = Os.lstat(source.getPath());
        require(!OsConstants.S_ISLNK(before.st_mode), "snapshot refuses symlink");
        java.io.FileDescriptor descriptor = Os.open(source.getPath(), OsConstants.O_RDONLY |
                OsConstants.O_CLOEXEC | OsConstants.O_NOFOLLOW, 0);
        boolean handedToStream = false;
        try {
            StructStat actual = Os.fstat(descriptor);
            require(actual.st_dev == before.st_dev && actual.st_ino == before.st_ino, "snapshot replaced during pin");
            JSONObject row = metadata(source.getCanonicalPath(), actual);
            observations.put(row);
            if (OsConstants.S_ISDIR(actual.st_mode)) {
                if (copy == null) return;
                require(copy.mkdir(), "authority copy directory exists");
                File[] children = source.listFiles();
                require(children != null, "authority directory unreadable");
                Arrays.sort(children, Comparator.comparing(File::getName));
                for (File child : children) observe(child, new File(copy, child.getName()), observations);
            } else {
                require(OsConstants.S_ISREG(actual.st_mode) && copy != null, "unexpected authority object");
                MessageDigest digest = MessageDigest.getInstance("SHA-256");
                handedToStream = true;
                try (FileInputStream input = new FileInputStream(descriptor); FileOutputStream output = new FileOutputStream(copy)) {
                    byte[] chunk = new byte[65536]; int size;
                    while ((size = input.read(chunk)) != -1) { digest.update(chunk, 0, size); output.write(chunk, 0, size); }
                    output.getFD().sync();
                    StructStat after = Os.fstat(descriptor);
                    require(after.st_dev == actual.st_dev && after.st_ino == actual.st_ino && after.st_size == actual.st_size,
                            "snapshot object changed while streaming");
                }
                row.put("sha256", hex(digest.digest()));
                row.put("raw", evidence.toPath().relativize(copy.toPath()).toString());
            }
        } finally { if (!handedToStream) Os.close(descriptor); }
    }
}
