// SPDX-License-Identifier: MIT
package org.exreader.host.uitest;

import static org.junit.Assert.*;

import android.content.Context;
import android.graphics.Rect;
import android.os.Build;
import android.os.Bundle;
import android.os.SystemClock;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.uiautomator.By;
import androidx.test.uiautomator.UiDevice;
import androidx.test.uiautomator.UiObject2;
import androidx.test.uiautomator.Until;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Independent black-box regressions; every import uses the system document picker. */
@RunWith(AndroidJUnit4.class)
public final class HostReviewTest {
    private static final String APP = "org.exreader.host";
    private UiDevice device;
    private Context context;
    private Bundle args;
    private File output;
    private final List<JSONObject> results = new ArrayList<>();
    private JSONObject sequence = new JSONObject();
    private interface Body { void run(List<String> assertions) throws Exception; }

    @Before public void setup() throws Exception {
        device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation());
        context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        args = InstrumentationRegistry.getArguments();
        output = new File(context.getExternalFilesDir(null), "review-evidence");
        if (output.exists()) throw new IllegalStateException("Preserve earlier review evidence");
        assertTrue(new File(output, "cases").mkdirs());
        assertTrue(new File(output, "shots").mkdirs());
        device.setOrientationNatural();
    }

    @Test public void review() throws Exception {
        run("duplicate_cancel_keeps_original", a -> {
            sample();
            String before = sources();
            configure("--es review_pause import-copied");
            pick("Sample.epub");
            awaitText("Review import-copied");
            click("cancel_button");
            awaitText("Import canceled");
            assertEquals(before, sources());
            open("Sample.epub");
            next(2);
            a.add("reused original bytes unchanged and real SDK reopens and renders page 2");
        });
        run("new_copy_cancel_cleans_file", a -> {
            sample(); String before = sources();
            configure("--es review_pause import-copied");
            pick("NewReview.txt"); awaitText("Review import-copied");
            assertNotEquals(before, sources());
            click("cancel_button"); awaitText("Import canceled");
            assertEquals(before, sources());
            assertFalse(bookExists("NewReview.txt"));
            open("Sample.epub"); next(2);
            a.add("new app-owned copy existed then was removed; no book row; original remains readable");
        });
        run("late_insert_cancel_rolls_back_new_book", a -> {
            sample(); String before = sources();
            configure("--es review_pause import-inserted");
            pick("NewReview.txt"); awaitText("Review import-inserted");
            assertNotEquals(before, sources());
            click("cancel_button"); awaitText("Import canceled");
            assertEquals(before, sources()); assertFalse(bookExists("NewReview.txt"));
            restart(); assertFalse(bookExists("NewReview.txt"));
            open("Sample.epub"); next(2);
            a.add("after actual native insert, cancellation removes row and owned bytes across restart");
        });
        run("duplicate_late_cancel_keeps_original", a -> {
            sample(); String before = sources();
            configure("--es review_pause import-inserted");
            pick("Sample.epub"); awaitText("Review import-inserted");
            click("cancel_button"); awaitText("Import canceled");
            assertEquals(before, sources());
            restart(); open("Sample.epub"); next(2);
            a.add("post-native dedup cancellation retains the reused row and original bytes after restart");
        });
        run("late_cancel_after_commit_reports_success", a -> {
            sample(); configure("--es review_pause import-committed");
            pick("NewReview.txt"); awaitText("Review import-committed");
            click("cancel_button");
            device.executeShellCommand("run-as " + APP + " touch files/review-release");
            awaitText("Imported NewReview.txt");
            assertTrue(bookExists("NewReview.txt"));
            restart(); open("NewReview.txt");
            assertTrue(text("book_title").contains("NewReview.txt"));
            assertNotNull(find("reader_view"));
            a.add("cancel after publication is reported as success and committed book reopens from real storage");
        });
        run("failed_open_preserves_reader", a -> {
            sample(); pick("NewReview.txt"); awaitText("Imported NewReview.txt");
            open("Sample.epub");
            String page = text("page_label");
            device.executeShellCommand("run-as " + APP + " sh -c 'rm files/books/*.txt'");
            configure("--es review_open_title NewReview.txt");
            awaitText("Could not open NewReview.txt");
            assertEquals(page, text("page_label"));
            assertTrue(text("book_title").contains("Sample.epub"));
            next(2);
            a.add("actual missing candidate source does not destroy prior native session, frame or next-page operation");
        });
        run("failed_progress_preserves_frame", a -> {
            sample(); open("Sample.epub");
            String before = text("page_label");
            configure("--ez review_fail_progress true");
            tapNext(); awaitText("Page error:");
            assertEquals(before, text("page_label"));
            next(2);
            device.executeShellCommand("am force-stop " + APP);
            launch(""); awaitPage(2);
            a.add("real SQLite INSERT rejection keeps accepted page and next cursor; retry and process restart restore page 2");
        });
        run("selection_invalidated_while_busy", a -> {
            sample(); open("Sample.epub"); selectLine();
            assertNotNull(find("annotate_button"));
            configure("--es review_pause page-before-render");
            click("font_up"); awaitText("Review page-before-render");
            assertNotNull("ordinary page request must expose its loading overlay", find("loading_overlay"));
            assertTrue("ordinary page request must expose an enabled cancel control", find("cancel_button").isEnabled());
            UiObject2 annotate = find("annotate_button");
            assertTrue(annotate == null || !annotate.isEnabled());
            click("cancel_button"); awaitText("Operation canceled");
            assertNull(find("selection_status"));
            assertTrue(text("notes_button").contains("Notes (0)"));
            configure(""); next(2);
            a.add("ordinary page path exposes loading and cancel before the debug gate; busy frame invalidates selection; cancellation creates no annotation and reader recovers");
        });
        run("unicode_comment_round_trip", a -> {
            sample(); open("Sample.epub"); selectLine();
            click("annotate_button");
            UiObject2 input = waitId("note_comment", 5000); assertNotNull(input);
            String comment = "Review 😀 保存 e\u0301";
            input.setText(comment);
            UiObject2 save = device.findObject(By.text("Save")); assertNotNull(save); save.click();
            awaitText("Annotation saved"); click("notes_button");
            assertNotNull(device.wait(Until.findObject(By.textContains(comment)), 10000));
            click("notes_close");
            device.executeShellCommand("am force-stop " + APP); launch("");
            awaitPage(1); click("notes_button");
            assertNotNull(device.wait(Until.findObject(By.textContains(comment)), 10000));
            a.add("standard UTF-8 emoji/Chinese/combining-mark comment survives native SDK insertion, query and process restart");
        });
        run("destroyed_activity_releases_worker", a -> {
            reset(""); pick("Large.epub"); awaitText("Imported Large.epub"); open("Large.epub");
            long begin = SystemClock.elapsedRealtime();
            for (int page = 2; page <= 49; page++) next(page);
            long elapsed = SystemClock.elapsedRealtime() - begin;
            String logs = device.executeShellCommand("logcat -d -s EXRHost:I '*:S'");
            Matcher matcher = Pattern.compile("paging (\\{[^\\r\\n]+\\})").matcher(logs);
            JSONObject last = null;
            while (matcher.find()) last = new JSONObject(matcher.group(1));
            assertNotNull(last);
            assertEquals(48, last.getInt("index"));
            assertEquals(49, last.getInt("native_next_calls"));
            assertEquals(0, last.getInt("recovery_calls"));
            sequence.put("fixture", "Large.epub"); sequence.put("rendered_pages", 49);
            sequence.put("native_next_calls", 49); sequence.put("recovery_calls", 0);
            sequence.put("sequential_elapsed_ms", elapsed);
            int closedBefore = occurrences(logs, "worker shutdown complete");
            configure("--es review_pause progress-before-write");
            tapNext(); awaitText("Review progress-before-write");
            JSONObject oldAttempt = lastProgressAttempt(device.executeShellCommand("logcat -d -s EXRHost:I '*:S'"));
            assertNotNull(oldAttempt); assertEquals(49, oldAttempt.getInt("index"));
            configure("--ez review_recreate true");
            awaitText("Opening Large.epub...");
            long waitingDeadline = SystemClock.uptimeMillis() + 20000;
            JSONObject waiting = null;
            while (SystemClock.uptimeMillis() < waitingDeadline) {
                JSONObject attempt = lastProgressAttempt(device.executeShellCommand("logcat -d -s EXRHost:I '*:S'"));
                if (attempt != null && attempt.getLong("owner") != oldAttempt.getLong("owner")
                        && attempt.getInt("index") == 48) { waiting = attempt; break; }
                SystemClock.sleep(100);
            }
            assertNotNull("rebuilt Activity must attempt its page-49 progress commit while old commit is paused", waiting);
            assertEquals(oldAttempt.getLong("book"), waiting.getLong("book"));
            assertNotNull("new Activity must remain loading until the old progress lock is released", find("loading_overlay"));
            assertTrue(text("loading_text").startsWith("Opening Large.epub"));
            assertFalse("new frame must not publish while old progress commit holds the lock", text("page_label").startsWith("p.49 ·"));
            device.executeShellCommand("run-as " + APP + " touch files/review-release");
            awaitPage(49);
            long deadline = SystemClock.uptimeMillis() + 15000;
            boolean closed = false;
            while (SystemClock.uptimeMillis() < deadline) {
                String after = device.executeShellCommand("logcat -d -s EXRHost:I '*:S'");
                if (occurrences(after, "worker shutdown complete") > closedBefore) { closed = true; break; }
                SystemClock.sleep(100);
            }
            assertTrue("destroyed Activity worker did not complete real SDK/store cleanup", closed);
            next(50);
            device.executeShellCommand("am force-stop " + APP); launch(""); awaitPage(50);
            a.add("49 actual pages require 49 native next calls, zero recovery replay; rebuilt owner attempts commit but remains loading without publishing until old progress commit is released; latest page 50 survives process restart");
        });
        int passed = 0;
        JSONArray cases = new JSONArray();
        for (JSONObject item : results) { cases.put(item); if ("pass".equals(item.getString("status"))) passed++; }
        JSONObject report = new JSONObject();
        report.put("schema", 1); report.put("suite", "android-host-review");
        report.put("source_sha", args.getString("exr_source_sha", ""));
        report.put("run_id", args.getString("exr_run_id", ""));
        report.put("attempt", args.getString("exr_attempt", ""));
        report.put("apk_sha256", args.getString("apk_sha256", ""));
        report.put("test_apk_sha256", args.getString("test_apk_sha256", ""));
        report.put("api", Build.VERSION.SDK_INT); report.put("abi", Build.SUPPORTED_ABIS[0]);
        boolean emulator = Build.FINGERPRINT.contains("generic") || Build.MODEL.contains("sdk_gphone")
                || Build.HARDWARE.contains("ranchu") || Build.PRODUCT.contains("sdk");
        report.put("device_is_emulator", emulator);
        report.put("physical_device_execution", !emulator);
        report.put("package", APP); report.put("cases", cases); report.put("sequence", sequence);
        report.put("summary", new JSONObject().put("total", results.size()).put("passed", passed)
                .put("failed", results.size() - passed).put("skipped", 0));
        write(new File(output, "validation.json"), report.toString(2));
        assertEquals("Independent Android runtime regressions failed", 10, passed);
    }

    private void run(String id, Body body) throws Exception {
        JSONObject result = new JSONObject().put("id", id).put("status", "fail");
        List<String> assertions = new ArrayList<>(); long begin = SystemClock.elapsedRealtime();
        try { body.run(assertions); result.put("status", "pass"); }
        catch (Throwable error) { result.put("error", error.getClass().getSimpleName() + ": " + error.getMessage()); }
        File shot = new File(output, "shots/" + id + ".png");
        if (!device.takeScreenshot(shot)) result.put("status", "fail");
        result.put("screenshot", "shots/" + id + ".png"); result.put("screenshot_bytes", shot.length());
        result.put("screenshot_sha256", sha(shot)); result.put("assertions", new JSONArray(assertions));
        result.put("elapsed_ms", SystemClock.elapsedRealtime() - begin);
        write(new File(output, "cases/" + id + ".json"), result.toString(2)); results.add(result);
    }
    private void sample() throws Exception { reset(""); pick("Sample.epub"); awaitText("Imported Sample.epub"); assertTrue(bookExists("Sample.epub")); }
    private void reset(String flags) throws Exception {
        device.executeShellCommand("am force-stop " + APP); device.executeShellCommand("pm clear " + APP); launch(flags);
        assertNotNull(waitId("shelf_panel", 15000));
    }
    private void restart() throws Exception {
        device.executeShellCommand("am force-stop " + APP); launch(""); assertNotNull(waitId("shelf_panel", 15000));
    }
    private void launch(String flags) throws Exception {
        device.executeShellCommand("am start -W -n " + APP + "/.MainActivity --ez exr_review true " + flags);
        assertNotNull(device.wait(Until.findObject(By.pkg(APP)), 15000));
    }
    private void configure(String flags) throws Exception {
        device.executeShellCommand("am start -W --activity-single-top -n " + APP + "/.MainActivity --ez exr_review true " + flags);
        device.waitForIdle();
    }
    private void pick(String name) throws Exception {
        click("import_button");
        long deadline = SystemClock.uptimeMillis() + 30000;
        while (SystemClock.uptimeMillis() < deadline) {
            UiObject2 file = device.findObject(By.text(name));
            if (file != null) { file.click(); return; }
            UiObject2 folder = device.findObject(By.text("Download"));
            if (folder == null) folder = device.findObject(By.text("Downloads"));
            if (folder != null) folder.click();
            else {
                UiObject2 roots = device.findObject(By.descContains("Show roots"));
                if (roots != null) roots.click();
                else device.swipe(device.getDisplayWidth()/2, device.getDisplayHeight()*3/4,
                        device.getDisplayWidth()/2, device.getDisplayHeight()/4, 20);
            }
            SystemClock.sleep(200);
        }
        throw new AssertionError("System picker did not list " + name);
    }
    private void open(String name) throws Exception {
        UiObject2 row = device.wait(Until.findObject(By.textStartsWith(name + "\n")), 15000);
        assertNotNull("book row missing: " + name, row); row.click(); awaitPage(1);
        assertNotNull(waitId("reader_view", 10000));
    }
    private boolean bookExists(String name) { return device.wait(Until.hasObject(By.textStartsWith(name + "\n")), 1500); }
    private void next(int page) throws Exception { tapNext(); awaitPage(page); }
    private void tapNext() throws Exception {
        UiObject2 view = waitId("reader_view", 10000); assertNotNull(view);
        Rect box = view.getVisibleBounds(); device.click(box.right - box.width()/6, box.centerY());
    }
    private void awaitPage(int page) throws Exception {
        long deadline = SystemClock.uptimeMillis() + 20000;
        while (SystemClock.uptimeMillis() < deadline) {
            UiObject2 label = find("page_label");
            if (label != null && label.getText().startsWith("p." + page + " ·") &&
                    find("loading_overlay") == null && find("select_button") != null && find("select_button").isEnabled()) return;
            SystemClock.sleep(100);
        }
        throw new AssertionError("actual reader did not reach page " + page);
    }
    private void awaitText(String value) throws Exception { assertTrue("missing status: " + value, device.wait(Until.hasObject(By.textContains(value)), 20000)); }
    private void click(String id) throws Exception { UiObject2 view = waitId(id, 10000); assertNotNull(id, view); view.click(); }
    private UiObject2 waitId(String id, long timeout) { return device.wait(Until.findObject(By.res(APP + ":id/" + id)), timeout); }
    private UiObject2 find(String id) { return device.findObject(By.res(APP + ":id/" + id)); }
    private String text(String id) { UiObject2 view = find(id); return view == null ? "" : String.valueOf(view.getText()); }
    private String sources() throws Exception { return device.executeShellCommand("run-as " + APP + " sh -c 'sha256sum files/books/*'").trim(); }
    private void selectLine() throws Exception {
        click("select_button"); Rect reader = waitId("reader_view", 5000).getVisibleBounds();
        for (UiObject2 line : device.findObjects(By.textContains("EXReader"))) {
            Rect box = line.getVisibleBounds();
            if (box.height() > 0 && box.top >= reader.top && box.bottom <= reader.bottom && box.width() > 40) {
                device.swipe(box.left + 6, box.centerY(), box.right - 6, box.centerY(), 24);
                awaitText("Selected:"); return;
            }
        }
        throw new AssertionError("real SDK line geometry missing");
    }
    private static int occurrences(String text, String value) { return text.split(Pattern.quote(value), -1).length - 1; }
    private static JSONObject lastProgressAttempt(String logs) throws Exception {
        Matcher matcher = Pattern.compile("progress attempt (\\{[^\\r\\n]+\\})").matcher(logs);
        JSONObject last = null;
        while (matcher.find()) last = new JSONObject(matcher.group(1));
        return last;
    }
    private static void write(File file, String value) throws Exception { try (FileOutputStream out = new FileOutputStream(file)) { out.write(value.getBytes(StandardCharsets.UTF_8)); } }
    private static String sha(File file) throws Exception {
        MessageDigest hash = MessageDigest.getInstance("SHA-256");
        try (FileInputStream input = new FileInputStream(file)) { byte[] b = new byte[65536]; int n; while ((n = input.read(b)) > 0) hash.update(b, 0, n); }
        StringBuilder out = new StringBuilder(); for (byte b : hash.digest()) out.append(String.format(java.util.Locale.ROOT, "%02x", b & 255)); return out.toString();
    }
}
