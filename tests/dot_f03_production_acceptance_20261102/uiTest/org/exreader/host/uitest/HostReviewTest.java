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
import androidx.test.uiautomator.StaleObjectException;
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
import java.util.SortedMap;
import java.util.TreeMap;
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
        output = new File(context.getExternalFilesDir(null), "bounded".equals(args.getString("exr_suite"))?"bounded-evidence":"review-evidence");
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
            for (String name : ownedSources().keySet()) {
                if (name.endsWith(".txt")) device.executeShellCommand("run-as " + APP + " rm files/books/" + name);
            }
            assertTrue("owned text source must be gone", anyTextSource(ownedSources()).isEmpty());
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
            assertNotNull("selection controls must appear for a real selection", waitId("annotate_button", 10000));
            configure("--es review_pause page-before-render");
            click("font_up"); awaitText("Review page-before-render");
            assertNotNull("ordinary page request must expose its loading overlay", waitId("loading_overlay", 5000));
            UiObject2 cancel = waitId("cancel_button", 5000);
            assertNotNull("ordinary page request must expose a cancel control", cancel);
            assertTrue("ordinary page request must expose an enabled cancel control", cancel.isEnabled());
            UiObject2 annotate = find("annotate_button");
            assertTrue("busy frame must not keep annotation enabled", annotate == null || !annotate.isEnabled());
            click("cancel_button"); awaitText("Operation canceled");
            assertTrue("cancellation must clear the selection bar", waitGone("selection_status", 5000));
            assertTrue("cancellation must leave the annotation count at zero", waitButtonText("Notes (0)", 5000));
            configure(""); next(2);
            a.add("ordinary page path exposes loading and cancel before the debug gate; busy frame invalidates selection; cancellation creates no annotation and reader recovers");
        });
        run("unicode_comment_round_trip", a -> {
            sample(); open("Sample.epub"); selectLine();
            click("annotate_button");
            UiObject2 input = waitId("note_comment", 10000); assertNotNull("comment field missing", input);
            String comment = "Review 😀 保存 e\u0301";
            setText("note_comment", comment);
            clickText("Save", "annotation save");
            awaitText("Annotation saved");
            click("notes_button");
            assertNotNull("annotation row missing", waitText(comment, 20000));
            click("notes_close");
            device.executeShellCommand("am force-stop " + APP); launch("");
            awaitPage(1); click("notes_button");
            assertNotNull("annotation row missing after process restart", waitText(comment, 20000));
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
            final long pauseStart = SystemClock.uptimeMillis();
            JSONObject oldAttempt = null;
            boolean reviewReleased = false;
            Throwable reviewFailure = null;
            try {
            tapNext(); awaitText("Review progress-before-write");
            oldAttempt = lastProgressAttempt(device.executeShellCommand("logcat -d -s EXRHost:I '*:S'"));
            assertNotNull(oldAttempt); assertEquals(49, oldAttempt.getInt("index"));
            LargeRestoreWait commitWait = new LargeRestoreWait(
                    "review-recreate-commit", oldAttempt.getLong("book"), false, pauseStart + 50000);
            configure("--ez review_recreate true");
            awaitText("Opening Large.epub...");
            commitWait.beginOriginalWindow();
            long waitingDeadline = commitWait.deadline;
            JSONObject waiting = null;
            while (SystemClock.uptimeMillis() < waitingDeadline) {
                commitWait.observe();
                JSONObject attempt = lastProgressAttempt(device.executeShellCommand("logcat -d -s EXRHost:I '*:S'"));
                if (SystemClock.uptimeMillis() >= waitingDeadline) break;
                if (attempt != null && attempt.getLong("book") == oldAttempt.getLong("book")
                        && attempt.getLong("owner") != oldAttempt.getLong("owner")
                        && attempt.getInt("index") == 48) { waiting = attempt; break; }
                SystemClock.sleep(100);
            }
            android.util.Log.i("EXRReview", "restore observation commit candidate" + commitWait.detail());
            assertNotNull("rebuilt Activity must attempt its page-49 progress commit while old commit is paused", waiting);
            commitWait.requireCommit(waiting, oldAttempt.getLong("owner"), 48);
            assertEquals(oldAttempt.getLong("book"), waiting.getLong("book"));
            assertNotNull("new Activity must remain loading until the old progress lock is released", find("loading_overlay"));
            assertTrue(text("loading_text").startsWith("Opening Large.epub"));
            assertFalse("new frame must not publish while old progress commit holds the lock", text("page_label").startsWith("p.49 ·"));
            LargeRestoreWait releasedWait = new LargeRestoreWait(
                    "review-release-page49", waiting.getLong("book"), false, Long.MAX_VALUE);
            assertTrue("old progress pause must still have ten seconds reserved before release",
                    SystemClock.uptimeMillis() - pauseStart <= 50000);
            String releaseReceipt = device.executeShellCommand("run-as " + APP + " sh -c " +
                    "test${IFS}!${IFS}-e${IFS}files/review-release&&" +
                    "test${IFS}!${IFS}-e${IFS}files/review-release-r8.tmp&&" +
                    "touch${IFS}files/review-release-r8.tmp&&" +
                    "test${IFS}-f${IFS}files/review-release-r8.tmp&&" +
                    "mv${IFS}files/review-release-r8.tmp${IFS}files/review-release&&" +
                    "echo${IFS}F03_RELEASE_PUBLISHED_0").trim();
            assertEquals("real release marker must exist before atomic publication; all shell operations must exit zero",
                    "F03_RELEASE_PUBLISHED_0", releaseReceipt);
            reviewReleased = true;
            assertTrue("release must finish before the unchanged sixty-second gate can expire",
                    SystemClock.uptimeMillis() - pauseStart <= 55000);
            awaitLargeRestorePage(49, releasedWait);
            } catch (Exception | Error error) {
                reviewFailure = error;
                throw error;
            } finally {
                if (!reviewReleased) {
                    // Best-effort cleanup preserves the first failure and never grants a pass.
                    try { device.executeShellCommand("run-as " + APP + " touch files/review-release"); }
                    catch (Exception | Error cleanup) {
                        if (reviewFailure != null) reviewFailure.addSuppressed(cleanup);
                        else throw cleanup;
                    }
                }
            }
            long deadline = SystemClock.uptimeMillis() + 15000;
            boolean closed = false;
            while (SystemClock.uptimeMillis() < deadline) {
                String after = device.executeShellCommand("logcat -d -s EXRHost:I '*:S'");
                if (occurrences(after, "worker shutdown complete") > closedBefore) { closed = true; break; }
                SystemClock.sleep(100);
            }
            assertTrue("destroyed Activity worker did not complete real SDK/store cleanup", closed);
            next(50);
            LargeRestoreWait restartWait = new LargeRestoreWait(
                    "review-restart-page50", oldAttempt.getLong("book"), true, Long.MAX_VALUE);
            device.executeShellCommand("am force-stop " + APP); launch(""); awaitLargeRestorePage(50, restartWait);
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

    @Test public void bounded() throws Exception {
        boundedCase("bounded_source_delete_restore",a->{
            sample(); open("Sample.epub");
            assertTrue(logs().contains("bounded=true")); assertTrue(logs().contains("bounded page {"));
            for(String name:ownedSources().keySet()) if(name.endsWith(".epub")) device.executeShellCommand("run-as "+APP+" rm files/books/"+name);
            assertTrue(ownedSources().isEmpty()); next(2);
            device.executeShellCommand("am force-stop "+APP); launch(""); awaitPage(2);
            a.add("package-only bounded import reads DB original after sidecar deletion, continues and survives process restart");
        });
        boundedCase("bounded_cross_chapter_font",a->{
            reset(""); pick("Cross.epub"); awaitText("Imported Cross.epub"); open("Cross.epub");
            next(2); assertNotNull(waitText("EXReader second unique",10000));
            click("font_up"); awaitPage(2); assertNotNull(waitText("EXReader second unique",10000));
            device.executeShellCommand("am force-stop "+APP); launch(""); awaitPage(2);
            assertNotNull(waitText("EXReader second unique",10000));
            Rect frame=waitId("reader_view",10000).getVisibleBounds(); device.click(frame.left+frame.width()/6,frame.centerY());
            awaitPage(1); assertNotNull(waitText("EXReader first unique",10000));
            a.add("cross-chapter next/previous, font change and process recovery preserve part-local identity and page text virtual nodes");
        });
        boundedCase("bounded_note_domain_restart",a->{
            reset(""); pick("Cross.epub"); awaitText("Imported Cross.epub"); open("Cross.epub");
            addBoundedNote("First 😀 章"); next(2); addBoundedNote("Second 注释 e\u0301");
            device.executeShellCommand("am force-stop "+APP); launch(""); awaitPage(2);
            assertTrue(waitButtonText("Notes (2)",15000)); click("notes_button");
            UiObject2 first=waitText("First 😀 章",15000); assertNotNull(first); first.click();
            awaitText("Jumped to annotation"); awaitPage(1);
            assertNotNull(waitText("EXReader first unique",10000));
            assertTrue(find("reader_view").getContentDescription().contains("Selection:"));
            a.add("two part-scoped quote notes and Unicode comments survive restart; unique FOUND navigation renders first chapter and selection highlight");
        });
        boundedCase("bounded_duplicate_spine",a->{
            reset(""); pick("DuplicateSpine.epub"); awaitText("Imported DuplicateSpine.epub"); open("DuplicateSpine.epub");
            next(2); next(3); assertNotNull(waitText("EXReader repeated route",10000));
            device.executeShellCommand("am force-stop "+APP); launch(""); awaitPage(3);
            String log=logs(); Matcher match=Pattern.compile("paging (\\{[^\\r\\n]+\\})").matcher(log); JSONObject last=null;
            while(match.find()) last=new JSONObject(match.group(1)); assertNotNull(last); assertEquals(2,last.getInt("part"));
            assertNotNull(waitText("EXReader repeated route",10000));
            a.add("same decoded package path in spine positions 0 and 2 is stored and restored using distinct part index");
        });
        boundedCase("bounded_legacy_dedup",a->{
            reset("--ez review_legacy_import true"); pick("Sample.epub"); awaitText("Imported Sample.epub"); open("Sample.epub");
            addBoundedNote("Legacy kept"); next(2); device.pressBack();
            pick("Sample.epub"); awaitText("Already in shelf: Sample.epub");
            device.executeShellCommand("am force-stop "+APP); launch("");
            UiObject2 row=device.wait(Until.findObject(By.textStartsWith("Sample.epub\n")),15000); assertNotNull(row); row.click(); awaitPage(2);
            assertTrue(waitButtonText("Notes (1)",15000));
            assertTrue(logs().contains("bounded=false"));
            a.add("explicit legacy memory import deduplicates with bounded file import without changing mode, global progress or original note");
        });
        boundedCase("bounded_schema6_upgrade",a->{
            reset("--ez review_legacy_import true"); pick("Sample.epub"); awaitText("Imported Sample.epub"); open("Sample.epub");
            addBoundedNote("Before schema migration"); next(2);
            configure("--ez review_schema6 true"); awaitText("Review schema 6 upgraded to 7");
            UiObject2 row=device.wait(Until.findObject(By.textStartsWith("Sample.epub\n")),15000); assertNotNull(row); row.click(); awaitPage(2);
            assertTrue(waitButtonText("Notes (1)",15000));
            a.add("legacy-only test database removes schema7 tables and declares schema6; SDK reopens to schema7 without changing legacy progress/note");
        });
        boundedCase("bounded_progress_write_reject",a->{
            sample(); open("Sample.epub"); String before=text("page_label");
            configure("--ez review_fail_progress true"); tapNext(); awaitText("Page error:");
            assertEquals(before,text("page_label"));
            assertTrue("must reject real SQLite write rather than source IO",text("reader_status").contains("host-review") && text("reader_status").contains("code 7"));
            next(2); device.executeShellCommand("am force-stop "+APP); launch(""); awaitPage(2);
            a.add("real epub_progress INSERT rejection is EXR_DATABASE/host-review, keeps frame/cursor, and retries/restores successfully");
        });
        boundedCase("bounded_external_commit_reopen",a->{
            sample(); open("Sample.epub"); String before=text("page_label");
            configure("--ez review_external_commit true"); tapNext(); awaitText("Page error:");
            assertEquals(before,text("page_label")); assertTrue(text("reader_status").contains("code 3"));
            next(2); assertTrue(logs().contains("bounded page {"));
            a.add("external connection commit invalidates old DB source with EXR_IO; fresh source/publication recovers accepted cursor and continues");
        });
        boundedCase("bounded_damaged_next_preserves_frame",a->{
            reset(""); pick("DamagedNext.epub"); awaitText("Imported DamagedNext.epub"); open("DamagedNext.epub");
            String before=text("page_label");
            tapNext(); awaitText("Page error:");
            assertTrue("malformed later chapter must report real EXR_FORMAT",text("reader_status").contains("code 5"));
            assertEquals(before,text("page_label")); assertNotNull(waitText("EXReader boundary accepted",10000));
            assertNull(waitText("EXReader boundary forbidden jump",1000));
            tapNext(); awaitText("Page error:"); assertEquals(before,text("page_label"));
            device.executeShellCommand("am force-stop "+APP); launch(""); awaitPage(1);
            assertNotNull(waitText("EXReader boundary accepted",10000));
            a.add("malformed next reading chapter produces real EXR_FORMAT twice, retains accepted frame and persisted position across process restart, and never advances to the later valid chapter");
        });
        boundedCase("bounded_budget_limit_preserves_frame",a->{
            reset(""); pick("BudgetNext.epub"); awaitText("Imported BudgetNext.epub"); open("BudgetNext.epub");
            String before=text("page_label");
            configure("--ei review_chapter_budget 1048576"); tapNext(); awaitText("Page error:");
            assertTrue("actual 1MiB chapter options must report EXR_LIMIT",text("reader_status").contains("code 6"));
            assertEquals(before,text("page_label")); assertNotNull(waitText("EXReader boundary accepted",10000));
            assertNull(waitText("EXReader boundary forbidden jump",1000));
            device.executeShellCommand("am force-stop "+APP); launch(""); awaitPage(1);
            next(2); assertNotNull(waitText("EXReader budget chapter",10000));
            a.add("real workspace_budget=1MiB rejects next chapter with EXR_LIMIT, retains frame and persisted position, and default 8MiB retry opens that same chapter rather than treating LIMIT as EOF");
            reset(""); pick("Large.epub"); awaitText("Imported Large.epub"); open("Large.epub"); next(2);
            String saved=progressIdentity("before-budget");
            JSONObject budgetBefore = lastProgressAttempt(logs()); assertNotNull(budgetBefore);
            LargeRestoreWait budgetWait = new LargeRestoreWait(
                    "budget-restart-page2", budgetBefore.getLong("book"), true, Long.MAX_VALUE);
            device.executeShellCommand("am force-stop "+APP); launch(""); awaitLargeRestorePage(2, budgetWait);
            assertTrue("real 5s query budget must be observable",text("reader_status").contains("query budget exceeded"));
            assertTrue(logs().contains("bounded progress resolution budget exhausted"));
            Matcher query=Pattern.compile("bounded progress resolve elapsed_ms=(\\d+) state=-2").matcher(logs());
            long queryMillis=-1; while(query.find()) queryMillis=Long.parseLong(query.group(1));
            assertTrue("timeout must consume the actual five-second query budget",queryMillis>=5000);
            assertEquals(saved,progressIdentity("after-budget"));
            click("font_up"); awaitPage(2); assertEquals(saved,progressIdentity("after-font"));
            next(3); assertNotEquals(saved,progressIdentity("after-explicit-next"));
            a.add("real five-second point-selector query timeout is distinct from FOUND/MISSING; validated stored chapter offset is explicit, original selector survives restore/font, and only explicit next saves a new selector");
        });
        boundedCase("bounded_empty_next_explicit_error",a->{
            reset(""); pick("EmptyNext.epub"); awaitText("Imported EmptyNext.epub"); open("EmptyNext.epub");
            String before=text("page_label"); long began=SystemClock.elapsedRealtime();
            tapNext(); awaitText("Page error:");
            assertTrue(text("reader_status").contains("Empty reading chapter is not supported"));
            assertTrue("empty chapter must terminate within the ordinary UI bound",SystemClock.elapsedRealtime()-began<20000);
            assertEquals(before,text("page_label")); assertNotNull(waitText("EXReader boundary accepted",10000));
            assertNull(waitText("EXReader boundary forbidden jump",1000));
            device.executeShellCommand("am force-stop "+APP); launch(""); awaitPage(1);
            a.add("empty reading chapter is explicitly unsupported, terminates without crash or loop, retains accepted frame and persisted position, and does not silently jump to a later chapter");
        });
        int passed=0; JSONArray cases=new JSONArray();
        for(JSONObject item:results) { cases.put(item); if("pass".equals(item.getString("status"))) passed++; }
        boolean emulator=Build.HARDWARE.contains("ranchu") || Build.PRODUCT.contains("sdk") || Build.FINGERPRINT.contains("generic");
        JSONObject report=new JSONObject().put("schema",1).put("suite","android-host-bounded").put("package",APP)
            .put("source_sha",args.getString("exr_source_sha","")).put("run_id",args.getString("exr_run_id","")).put("attempt",args.getString("exr_attempt",""))
            .put("apk_sha256",args.getString("apk_sha256","")).put("test_apk_sha256",args.getString("test_apk_sha256",""))
            .put("api",Build.VERSION.SDK_INT).put("abi",Build.SUPPORTED_ABIS[0]).put("device_is_emulator",emulator).put("physical_device_execution",!emulator)
            .put("cases",cases).put("summary",new JSONObject().put("total",results.size()).put("passed",passed).put("failed",results.size()-passed).put("skipped",0));
        write(new File(output,"validation.json"),report.toString(2)); assertEquals("Bounded Android regressions failed",11,passed);
    }
    private void boundedCase(String id,Body body) throws Exception { run(id,body); }
    private String logs() throws Exception { return device.executeShellCommand("logcat -d -s EXRHost:I '*:S'"); }
    private String progressIdentity(String label) throws Exception {
        configure("--es review_progress_identity "+label); String prefix="Review selector "+label+" ";
        awaitText(prefix); String value=text("reader_status"); assertTrue(value.startsWith(prefix));
        String digest=value.substring(prefix.length()); assertTrue(digest.matches("[0-9a-f]{64}")); return digest;
    }
    private void addBoundedNote(String value) throws Exception {
        selectLine(); click("annotate_button"); setText("note_comment",value); clickText("Save","bounded note save"); awaitText("Annotation saved");
        if(find("selection_cancel")!=null) click("selection_cancel");
    }

    private void run(String id, Body body) throws Exception {
        android.util.Log.i("EXRReview", "case start " + id);
        JSONObject result = new JSONObject().put("id", id).put("status", "fail");
        List<String> assertions = new ArrayList<>(); long begin = SystemClock.elapsedRealtime();
        try { body.run(assertions); result.put("status", "pass"); }
        catch (Throwable error) {
            StackTraceElement frame = null;
            for (StackTraceElement element : error.getStackTrace()) {
                if (element.getClassName().startsWith("org.exreader.host.uitest.")) { frame = element; break; }
            }
            result.put("error", error.getClass().getSimpleName() + (frame == null ? "" : " line " + frame.getLineNumber())
                    + ": " + error.getMessage());
            try {
                result.put("detail", text("status_text") + " | " + text("reader_status") + " | notes="
                        + text("notes_button") + " | page=" + text("page_label")
                        + " | selection=" + (find("selection_status") != null) + " | reader=" + (find("reader_view") != null));
            } catch (Throwable ignored) { }
        }
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
        // am start -W can wait indefinitely for a failed launch; observe UI below.
        device.executeShellCommand("am start -n " + APP + "/.MainActivity --ez exr_review true " + flags);
        assertNotNull(device.wait(Until.findObject(By.pkg(APP)), 15000));
    }
    private void configure(String flags) throws Exception {
        device.executeShellCommand("am start --activity-single-top -n " + APP + "/.MainActivity --ez exr_review true " + flags);
        device.waitForIdle();
    }
    private void pick(String name) throws Exception {
        // R7: real Downloads navigation only; every retry shares the original deadline.
        final long deadline = SystemClock.uptimeMillis() + 30000;
        final String documents = "com.android.documentsui";
        final android.app.UiAutomation automation =
                InstrumentationRegistry.getInstrumentation().getUiAutomation();
        final class Picker {
            int backward, forward, matches;
            String phase = "root", header = "";
            boolean eventTop;
            int treeNodes, navigationCollections;
            String navigationKey = "";
            String rootGeometry = "";
            int geometryRetries, rootCandidates;
            boolean invalidRootGeometry;
            java.util.Set<String> beforeCollections = new java.util.HashSet<>();
            long left() { return Math.max(0, deadline - SystemClock.uptimeMillis()); }
            String detail() {
                return " [picker phase=" + phase + " root=" + header +
                        " matches=" + matches + " backward=" + backward +
                        " forward=" + forward + " nav_collections=" + navigationCollections +
                        " tree_nodes=" + treeNodes + " geometry_retries=" + geometryRetries +
                        " root_geometry=" + rootGeometry + " elapsed_ms=" +
                        (30000 - left()) + "]";
            }
            void need(boolean value, String message) {
                if (!value) throw new AssertionError(message + detail());
            }
            void pause() {
                need(left() > 0, "System picker did not list " + name);
                SystemClock.sleep(Math.min(80, left()));
            }
            void visit(int depth) {
                need(left() > 0 && depth <= 32 && ++treeNodes <= 2048,
                        "Picker tree deadline/depth/node bound");
            }
            String collectionKey(android.view.accessibility.AccessibilityNodeInfo node) {
                if (!node.isVisibleToUser() || node.getCollectionInfo() == null ||
                        node.getViewIdResourceName() == null || node.getClassName() == null ||
                        !documents.contentEquals(node.getPackageName() == null ? "" : node.getPackageName()))
                    return "";
                return node.getViewIdResourceName() + "|" + node.getClassName();
            }
            boolean inDirectory(android.view.accessibility.AccessibilityNodeInfo node) {
                android.view.accessibility.AccessibilityNodeInfo current =
                        android.view.accessibility.AccessibilityNodeInfo.obtain(node);
                try {
                    for (int depth = 0; current != null; depth++) {
                        visit(depth);
                        String id = current.getViewIdResourceName();
                        if (id != null && id.endsWith("/dir_list")) return true;
                        android.view.accessibility.AccessibilityNodeInfo parent = current.getParent();
                        current.recycle(); current = parent;
                    }
                    return false;
                } finally { if (current != null) current.recycle(); }
            }
            void collections(android.view.accessibility.AccessibilityNodeInfo node, int depth,
                    java.util.Set<String> keys) {
                visit(depth);
                String key = collectionKey(node);
                if (!key.isEmpty()) keys.add(key);
                for (int i = 0; i < node.getChildCount(); i++) {
                    android.view.accessibility.AccessibilityNodeInfo child = node.getChild(i);
                    if (child != null) {
                        try { collections(child, depth + 1, keys); }
                        finally { child.recycle(); }
                    }
                }
            }
            java.util.Set<String> collections() {
                treeNodes = 0;
                java.util.Set<String> keys = new java.util.HashSet<>();
                android.view.accessibility.AccessibilityNodeInfo root = automation.getRootInActiveWindow();
                need(root != null, "DocumentsUI root snapshot missing");
                try {
                    need(documents.contentEquals(root.getPackageName() == null ? "" : root.getPackageName()),
                            "Refusing non-DocumentsUI root snapshot");
                    collections(root, 0, keys);
                } finally { root.recycle(); }
                return keys;
            }
            boolean containsDirectory(android.view.accessibility.AccessibilityNodeInfo node, int depth) {
                visit(depth);
                String id = node.getViewIdResourceName();
                if (id != null && id.endsWith("/dir_list")) return true;
                for (int i = 0; i < node.getChildCount(); i++) {
                    android.view.accessibility.AccessibilityNodeInfo child = node.getChild(i);
                    if (child != null) {
                        try { if (containsDirectory(child, depth + 1)) return true; }
                        finally { child.recycle(); }
                    }
                }
                return false;
            }
            void rootTitles(android.view.accessibility.AccessibilityNodeInfo node, int depth,
                    android.view.accessibility.AccessibilityNodeInfo collection, String key,
                    List<Rect> rows, List<String> keys) {
                visit(depth);
                String id = node.getViewIdResourceName();
                String text = node.getText() == null ? "" : node.getText().toString();
                if (id != null && id.endsWith("/title") &&
                        (text.equals("Download") || text.equals("Downloads")) &&
                        documents.contentEquals(node.getPackageName() == null ? "" : node.getPackageName()) &&
                        node.isVisibleToUser() && node.isEnabled()) {
                    need(!inDirectory(node), "Root candidate is a file-list descendant");
                    android.view.accessibility.AccessibilityNodeInfo row =
                            android.view.accessibility.AccessibilityNodeInfo.obtain(node);
                    try {
                        for (int hops = 0; row != null && !row.equals(collection); hops++) {
                            visit(hops);
                            if (row.isClickable() && row.isVisibleToUser() && row.isEnabled() &&
                                    (row.getActions() & android.view.accessibility.AccessibilityNodeInfo.ACTION_CLICK) != 0) {
                                Rect bounds = new Rect(), container = new Rect();
                                row.getBoundsInScreen(bounds); collection.getBoundsInScreen(container);
                                rootCandidates++;
                                rootGeometry = "row=" + bounds.toShortString() + ",container=" + container.toShortString();
                                // The same containment proof remains mandatory. A transient invalid
                                // snapshot is observed again, never clicked or treated as valid.
                                if (bounds.isEmpty() || !container.contains(bounds)) {
                                    geometryRetries++;
                                    invalidRootGeometry = true;
                                    break;
                                }
                                rows.add(bounds); keys.add(key);
                                break;
                            }
                            android.view.accessibility.AccessibilityNodeInfo parent = row.getParent();
                            row.recycle(); row = parent;
                        }
                    } finally { if (row != null) row.recycle(); }
                }
                for (int i = 0; i < node.getChildCount(); i++) {
                    android.view.accessibility.AccessibilityNodeInfo child = node.getChild(i);
                    if (child != null) {
                        try { rootTitles(child, depth + 1, collection, key, rows, keys); }
                        finally { child.recycle(); }
                    }
                }
            }
            void navigation(android.view.accessibility.AccessibilityNodeInfo node, int depth,
                    List<Rect> rows, List<String> keys) {
                visit(depth);
                String key = collectionKey(node);
                if (!key.isEmpty() && !beforeCollections.contains(key) &&
                        !inDirectory(node) && !containsDirectory(node, 0)) {
                    navigationCollections++;
                    rootTitles(node, 0, node, key, rows, keys);
                }
                for (int i = 0; i < node.getChildCount(); i++) {
                    android.view.accessibility.AccessibilityNodeInfo child = node.getChild(i);
                    if (child != null) {
                        try { navigation(child, depth + 1, rows, keys); }
                        finally { child.recycle(); }
                    }
                }
            }
            Rect rootRow() {
                treeNodes = 0; navigationCollections = 0; rootCandidates = 0; invalidRootGeometry = false;
                android.view.accessibility.AccessibilityNodeInfo root = automation.getRootInActiveWindow();
                need(root != null, "Drawer tree missing");
                List<Rect> rows = new ArrayList<>(); List<String> keys = new ArrayList<>();
                try {
                    need(documents.contentEquals(root.getPackageName() == null ? "" : root.getPackageName()),
                            "Drawer is not DocumentsUI");
                    navigation(root, 0, rows, keys);
                } finally { root.recycle(); }
                matches = rows.size();
                need(rootCandidates <= 1, "Multiple exact Downloads navigation rows");
                if (invalidRootGeometry) return null;
                need(matches <= 1, "Multiple exact Downloads navigation rows");
                if (matches == 0) return null;
                need(navigationCollections == 1, "Ambiguous newly visible navigation collections");
                navigationKey = keys.get(0);
                return rows.get(0);
            }
            boolean id(UiObject2 node, String suffix) {
                String resource = node.getResourceName();
                return resource != null && resource.endsWith("/" + suffix);
            }
            UiObject2 resource(String suffix) {
                return device.findObject(By.pkg(documents).res(
                        java.util.regex.Pattern.compile(".*:id/" + suffix)));
            }
            boolean opened() {
                UiObject2 title = resource("header_title");
                header = title == null || title.getText() == null ? "" : title.getText();
                // Keep diagnostics bounded even if an unexpected window supplies text.
                if (header.length() > 96) header = header.substring(0, 96);
                return header.equals("Files in Download") || header.equals("Files in Downloads");
            }
            UiObject2 list() {
                need(opened(), "Downloads root not confirmed");
                UiObject2 value = resource("dir_list");
                need(value != null && !value.getVisibleBounds().isEmpty(),
                        "Real DocumentsUI Downloads list missing");
                return value;
            }
            boolean rowZero(android.view.accessibility.AccessibilityNodeInfo node, Rect bounds, int depth) {
                visit(depth);
                android.view.accessibility.AccessibilityNodeInfo.CollectionItemInfo item =
                        node.getCollectionItemInfo();
                Rect visible = new Rect();
                node.getBoundsInScreen(visible);
                if (item != null && item.getRowIndex() == 0 && node.getViewIdResourceName() != null &&
                        node.getViewIdResourceName().endsWith("/item_root") && node.isVisibleToUser() &&
                        !visible.isEmpty() && visible.top >= bounds.top &&
                        visible.bottom <= bounds.bottom) return true;
                for (int i = 0; i < node.getChildCount(); i++) {
                    android.view.accessibility.AccessibilityNodeInfo child = node.getChild(i);
                    if (child != null) {
                        try { if (rowZero(child, bounds, depth + 1)) return true; }
                        finally { child.recycle(); }
                    }
                }
                return false;
            }
            android.view.accessibility.AccessibilityNodeInfo findList(
                    android.view.accessibility.AccessibilityNodeInfo node, int depth) {
                if (node == null) return null;
                visit(depth);
                String resource = node.getViewIdResourceName();
                if (documents.contentEquals(node.getPackageName() == null ? "" : node.getPackageName()) &&
                        resource != null && resource.endsWith("/dir_list") &&
                        node.isVisibleToUser()) return android.view.accessibility.AccessibilityNodeInfo.obtain(node);
                for (int i = 0; i < node.getChildCount(); i++) {
                    android.view.accessibility.AccessibilityNodeInfo child = node.getChild(i);
                    if (child != null) {
                        try {
                            android.view.accessibility.AccessibilityNodeInfo found = findList(child, depth + 1);
                            if (found != null) return found;
                        } finally { child.recycle(); }
                    }
                }
                return null;
            }
            android.view.accessibility.AccessibilityNodeInfo freshList() {
                list();
                treeNodes = 0;
                android.view.accessibility.AccessibilityNodeInfo root = automation.getRootInActiveWindow();
                need(root != null, "DocumentsUI accessibility root missing");
                try {
                    need(documents.contentEquals(root.getPackageName() == null ? "" : root.getPackageName()),
                            "Refusing non-DocumentsUI window");
                    android.view.accessibility.AccessibilityNodeInfo found = findList(root, 0);
                    need(found != null, "Downloads accessibility list missing");
                    return found;
                } finally { root.recycle(); }
            }
            boolean atTop() {
                android.view.accessibility.AccessibilityNodeInfo node = freshList();
                try {
                    Rect bounds = new Rect();
                    node.getBoundsInScreen(bounds);
                    return eventTop || rowZero(node, bounds, 0);
                } finally { node.recycle(); }
            }
            void scroll(boolean back) throws Exception {
                need(left() > 0, "System picker did not list " + name);
                if (back) need(++backward <= 16, "Downloads backward action limit");
                else need(++forward <= 16, "Downloads forward action limit");
                final int action = back ?
                        android.view.accessibility.AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD :
                        android.view.accessibility.AccessibilityNodeInfo.ACTION_SCROLL_FORWARD;
                final boolean[] acted = {false};
                android.view.accessibility.AccessibilityEvent event = null;
                try {
                    event = automation.executeAndWaitForEvent(() -> {
                        android.view.accessibility.AccessibilityNodeInfo node = freshList();
                        try {
                            need(node.isScrollable() && (node.getActions() & action) != 0,
                                    "Downloads list does not support requested scroll");
                            acted[0] = node.performAction(action);
                            need(acted[0], "Downloads scroll action refused; boundary unproven");
                        } finally { node.recycle(); }
                    }, observed -> {
                        if (observed.getEventType() !=
                                android.view.accessibility.AccessibilityEvent.TYPE_VIEW_SCROLLED ||
                                !documents.contentEquals(observed.getPackageName() == null ? "" :
                                        observed.getPackageName())) return false;
                        android.view.accessibility.AccessibilityNodeInfo node = observed.getSource();
                        if (node == null) return false;
                        try {
                            String resource = node.getViewIdResourceName();
                            return resource != null && resource.endsWith("/dir_list");
                        } finally { node.recycle(); }
                    }, Math.max(1, Math.min(1500, left())));
                    need(acted[0], "Downloads scroll lacked an action");
                    eventTop = back && event.getFromIndex() == 0 && event.getToIndex() >= 0 &&
                            event.getItemCount() > 0;
                } catch (java.util.concurrent.TimeoutException missingEvent) {
                    need(false, "Downloads scroll has no matching bounded event");
                } finally { if (event != null) event.recycle(); }
                pause();
            }
            UiObject2 document() {
                UiObject2 directory = list();
                List<UiObject2> candidates = directory.findObjects(By.pkg(documents).text(name));
                List<UiObject2> rows = new ArrayList<>();
                for (UiObject2 candidate : candidates) {
                    if (!id(candidate, "title") || !candidate.isEnabled() ||
                            candidate.getVisibleBounds().isEmpty()) continue;
                    UiObject2 row = candidate.getParent();
                    for (int hops = 0; row != null && !id(row, "item_root") && !id(row, "dir_list"); hops++) {
                        need(left() > 0 && hops < 32, "File row ancestry bound");
                        row = row.getParent();
                    }
                    if (row != null && id(row, "item_root") && row.isEnabled() &&
                            !row.getVisibleBounds().isEmpty()) rows.add(row);
                }
                matches = rows.size();
                need(matches <= 1, "Multiple exact DocumentsUI file rows");
                return matches == 1 ? rows.get(0) : null;
            }
        }
        Picker picker = new Picker();
        android.accessibilityservice.AccessibilityServiceInfo service = automation.getServiceInfo();
        final int oldFlags = service.flags;
        service.flags |= android.accessibilityservice.AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS;
        automation.setServiceInfo(service);
        try {
            click("import_button");
            boolean drawerRequested = false, rootClicked = false;
            while (picker.left() > 0) {
                try {
                    if (picker.phase.equals("root")) {
                        if (!device.hasObject(By.pkg(documents))) { picker.pause(); continue; }
                        if (!drawerRequested) {
                            UiObject2 originalList = picker.resource("dir_list");
                            if (originalList == null || originalList.getVisibleBounds().isEmpty()) {
                                picker.pause(); continue;
                            }
                            UiObject2 drawer = device.findObject(By.pkg(documents).desc("Show roots"));
                            if (drawer == null) drawer = device.findObject(
                                    By.pkg(documents).desc("Open navigation drawer"));
                            if (drawer != null && drawer.isEnabled()) {
                                picker.beforeCollections = picker.collections();
                                drawer.click();
                                drawerRequested = true;
                            }
                        } else if (!rootClicked) {
                            Rect row = picker.rootRow();
                            if (row != null) {
                                // Reacquire the complete live containment proof immediately before touch.
                                String key = picker.navigationKey;
                                picker.pause();
                                Rect current = picker.rootRow();
                                if (current == null || !key.equals(picker.navigationKey) || !row.equals(current)) {
                                    picker.geometryRetries++;
                                    picker.pause();
                                    continue;
                                }
                                picker.need(picker.left() > 0 &&
                                        device.click(current.centerX(), current.centerY()),
                                        "Real Downloads root touch failed");
                                rootClicked = true;
                            }
                        } else if (!picker.collections().contains(picker.navigationKey) &&
                                picker.opened()) {
                            picker.list();
                            picker.phase = "rewind";
                        }
                        picker.pause();
                        continue;
                    }
                    picker.need(picker.opened(), "Downloads root changed during lookup");
                    if (picker.phase.equals("rewind")) {
                        if (!picker.atTop()) { picker.scroll(true); continue; }
                        picker.phase = "find";
                    }
                    UiObject2 file = picker.document();
                    if (file != null) {
                        picker.need(picker.left() > 0, "System picker did not list " + name);
                        file.click();
                        assertTrue("picker must return to the reader" + picker.detail(),
                                device.wait(Until.hasObject(By.pkg(APP)), 10000));
                        return;
                    }
                    picker.scroll(false);
                } catch (StaleObjectException transientNode) {
                    picker.pause(); // Reacquire the same phase, never renew the deadline.
                }
            }
            throw new AssertionError("System picker did not list " + name + picker.detail());
        } finally {
            service.flags = oldFlags;
            automation.setServiceInfo(service);
        }
    }
    private void open(String name) throws Exception {
        long deadline = SystemClock.uptimeMillis() + 20000;
        while (true) {
            // Re-fetch the row every attempt: the shelf adapter rebuilds it after an import.
            UiObject2 row = device.findObject(By.textStartsWith(name + "\n"));
            if (row != null) {
                try {
                    row.click();
                    break;
                } catch (StaleObjectException transientNode) {
                    if (SystemClock.uptimeMillis() > deadline) throw new AssertionError("book row did not accept a click: " + name);
                    SystemClock.sleep(200);
                }
            } else if (SystemClock.uptimeMillis() > deadline) {
                throw new AssertionError("book row not found: " + name);
            } else {
                SystemClock.sleep(150);
            }
        }
        SystemClock.sleep(200);
        awaitPage(1);
        assertNotNull(waitId("reader_view", 10000));
    }
    private boolean bookExists(String name) { return device.wait(Until.hasObject(By.textStartsWith(name + "\n")), 1500); }
    private void next(int page) throws Exception { tapNext(); awaitPage(page); }
    private void tapNext() throws Exception {
        UiObject2 view = waitId("reader_view", 10000); assertNotNull("reader surface missing before paging", view);
        Rect box = view.getVisibleBounds(); device.click(box.right - box.width()/6, box.centerY());
    }
    /** R8: bounded observation of four Large.epub restore endpoints, never a performance pass. */
    private final class LargeRestoreWait {
        final String phase, anchor;
        final long book, began, deadline, oldPid;
        final boolean freshProcess;
        long pid, owner = -1, commitIndex = -1;
        int opens, resolves, pages, renderedPage = -1;
        boolean oldTwentyExceeded;
        long ordinaryBegan = -1;
        String stages = "";
        final Pattern hostLine = Pattern.compile(
                "^\\S+\\s+\\S+\\s+(\\d+)\\s+\\d+\\s+[A-Z]\\s+EXRHost\\s*:\\s*(.*)$");
        LargeRestoreWait(String phase, long book, boolean freshProcess, long outerDeadline) throws Exception {
            this.phase = phase; this.book = book; this.freshProcess = freshProcess;
            began = SystemClock.uptimeMillis();
            deadline = Math.min(began + 45000, outerDeadline);
            String before = logs();
            String last = ""; long previousPid = -1;
            for (String line : before.split("\\r?\\n")) {
                Matcher record = hostLine.matcher(line);
                if (!record.matches()) continue;
                last = line;
                if (record.group(2).startsWith("progress attempt ")) {
                    JSONObject attempt = new JSONObject(record.group(2).substring("progress attempt ".length()));
                    if (attempt.getLong("book") == book) previousPid = Long.parseLong(record.group(1));
                }
            }
            assertTrue("Large restore requires a real preceding book/process identity", book > 0 && previousPid > 0 && !last.isEmpty());
            anchor = last; oldPid = previousPid; pid = freshProcess ? 0 : oldPid;
            assertTrue("Large restore has no remaining observation budget", SystemClock.uptimeMillis() < deadline);
            android.util.Log.i("EXRReview", "restore observation begin " + phase + " book=" + book + " old_pid=" + oldPid);
        }
        void beginOriginalWindow() {
            assertTrue("original twenty-second observation reference must start exactly once", ordinaryBegan < 0);
            ordinaryBegan = SystemClock.uptimeMillis();
        }
        void observe() throws Exception {
            long now = SystemClock.uptimeMillis();
            if (ordinaryBegan >= 0 && now - ordinaryBegan >= 20000 && !oldTwentyExceeded) {
                oldTwentyExceeded = true;
                android.util.Log.i("EXRReview", "restore original_20s_not_met phase=" + phase);
            }
            String current = logs();
            int boundary = current.lastIndexOf(anchor);
            assertTrue("Large restore log checkpoint disappeared" + detail(), boundary >= 0);
            String fresh = current.substring(boundary + anchor.length());
            opens = 0; resolves = 0; pages = 0; renderedPage = -1; owner = -1; commitIndex = -1;
            StringBuilder observed = new StringBuilder();
            for (String line : fresh.split("\\r?\\n")) {
                Matcher record = hostLine.matcher(line);
                if (!record.matches()) continue;
                long recordPid = Long.parseLong(record.group(1));
                String message = record.group(2);
                if (message.equals("storage mode book=" + book + " bounded=true")) {
                    if (freshProcess) {
                        assertTrue("restart must not reuse the old process" + detail(), recordPid != oldPid);
                        if (pid == 0) pid = recordPid;
                        else assertEquals("one restore cannot splice multiple process identities" + detail(), pid, recordPid);
                    } else {
                        assertEquals("Activity recreation must remain in its original process" + detail(), oldPid, recordPid);
                    }
                }
                if (pid <= 0 || recordPid != pid) continue;
                assertFalse("Large restore reported an actual operation error: " + message + detail(),
                        message.startsWith("status Could not open ") || message.startsWith("status Page error:") ||
                        message.startsWith("status Library error:") || message.equals("status Operation canceled"));
                boolean keep = false;
                if (message.startsWith("bounded open ")) { opens++; keep = true; }
                if (message.startsWith("bounded progress resolve ")) { resolves++; keep = true; }
                if (message.startsWith("bounded progress resolution budget exhausted")) keep = true;
                if (message.startsWith("progress attempt ")) {
                    JSONObject attempt = new JSONObject(message.substring("progress attempt ".length()));
                    if (attempt.getLong("book") == book) {
                        owner = attempt.getLong("owner"); commitIndex = attempt.getLong("index"); keep = true;
                    }
                }
                if (message.startsWith("metric ")) {
                    JSONObject metric = new JSONObject(message.substring("metric ".length()));
                    if ("page".equals(metric.optString("event")) && metric.getLong("book") == book) {
                        pages++; renderedPage = metric.getInt("page"); keep = true;
                    }
                }
                if (keep && observed.length() < 3000) observed.append(message).append(" | ");
            }
            stages = observed.toString();
        }
        void requireCommit(JSONObject attempt, long oldOwner, int index) throws Exception {
            observe();
            assertTrue("new owner attempt must occur inside the single restore deadline" + detail(),
                    SystemClock.uptimeMillis() < deadline);
            assertTrue("real new owner/book/index attempt must precede release" + detail(),
                    pid == oldPid && attempt.getLong("book") == book &&
                    attempt.getLong("owner") != oldOwner && attempt.getInt("index") == index &&
                    owner == attempt.getLong("owner") && commitIndex == index);
        }
        String detail() {
            return " [restore phase=" + phase + " book=" + book + " pid=" + pid +
                    " old_pid=" + oldPid + " elapsed_ms=" + (SystemClock.uptimeMillis() - began) +
                    " original_20s_not_met=" + (ordinaryBegan >= 0 && (oldTwentyExceeded || SystemClock.uptimeMillis() - ordinaryBegan >= 20000)) +
                    " open=" + opens + " resolve=" + resolves + " page_events=" + pages +
                    " owner=" + owner + " index=" + commitIndex + " stages=" + stages + "]";
        }
    }
    private void awaitLargeRestorePage(int page, LargeRestoreWait wait) throws Exception {
        wait.beginOriginalWindow();
        while (SystemClock.uptimeMillis() < wait.deadline) {
            wait.observe();
            UiObject2 label = find("page_label"), select = find("select_button");
            if (label != null && label.getText().startsWith("p." + page + " \u00b7") &&
                    find("loading_overlay") == null && select != null && select.isEnabled()) {
                assertTrue("Large restore page must belong to its real operation" + wait.detail(),
                        SystemClock.uptimeMillis() < wait.deadline && wait.pid > 0 && wait.pages > 0 && wait.renderedPage == page &&
                        (!wait.freshProcess || wait.pid != wait.oldPid));
                android.util.Log.i("EXRReview", "restore observation complete" + wait.detail());
                return;
            }
            SystemClock.sleep(Math.min(100, Math.max(1, wait.deadline - SystemClock.uptimeMillis())));
        }
        throw new AssertionError("actual reader did not reach page " + page + wait.detail());
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
    private void click(String id) throws Exception {
        long deadline = SystemClock.uptimeMillis() + 20000;
        while (SystemClock.uptimeMillis() < deadline) {
            UiObject2 view = waitId(id, 8000);
            assertNotNull("control not found: " + id, view);
            try {
                view.click();
                SystemClock.sleep(150);
                return;
            } catch (StaleObjectException transientNode) {
                SystemClock.sleep(150);
            }
        }
        throw new AssertionError("control did not accept a click: " + id);
    }
    private void clickText(String value, String what) throws Exception {
        long deadline = SystemClock.uptimeMillis() + 15000;
        while (SystemClock.uptimeMillis() < deadline) {
            UiObject2 object = device.findObject(By.text(Pattern.compile("(?i)^" + Pattern.quote(value) + "$")));
            if (object != null && object.isEnabled()) {
                try {
                    object.click();
                    SystemClock.sleep(150);
                    return;
                } catch (StaleObjectException transientNode) {
                    SystemClock.sleep(150);
                }
            }
            SystemClock.sleep(150);
        }
        throw new AssertionError(what + " did not accept a click");
    }
    private void setText(String id, String value) throws Exception {
        long deadline = SystemClock.uptimeMillis() + 15000;
        while (SystemClock.uptimeMillis() < deadline) {
            UiObject2 field = waitId(id, 5000);
            assertNotNull("field not found: " + id, field);
            try {
                field.setText(value);
                return;
            } catch (StaleObjectException transientNode) {
                SystemClock.sleep(150);
            }
        }
        throw new AssertionError("field did not accept text: " + id);
    }
    private boolean waitGone(String id, long timeout) {
        long deadline = SystemClock.uptimeMillis() + timeout;
        while (SystemClock.uptimeMillis() < deadline) {
            if (find(id) == null) return true;
            SystemClock.sleep(100);
        }
        return false;
    }
    private boolean waitButtonText(String needle, long timeout) {
        // Material button styles upper-case their label, so compare the button text case-insensitively.
        String expected = needle.toUpperCase(java.util.Locale.ROOT);
        long deadline = SystemClock.uptimeMillis() + timeout;
        while (SystemClock.uptimeMillis() < deadline) {
            if (text("notes_button").toUpperCase(java.util.Locale.ROOT).contains(expected)) return true;
            SystemClock.sleep(150);
        }
        return false;
    }
    private UiObject2 waitText(String value, long timeout) { return device.wait(Until.findObject(By.textContains(value)), timeout); }
    private UiObject2 waitId(String id, long timeout) { return device.wait(Until.findObject(By.res(APP + ":id/" + id)), timeout); }
    private UiObject2 find(String id) { return device.findObject(By.res(APP + ":id/" + id)); }
    private String text(String id) { UiObject2 view = find(id); return view == null ? "" : String.valueOf(view.getText()); }
    private String sources() throws Exception {
        SortedMap<String, String> digests = ownedSources();
        assertFalse("app-owned source observation must not be empty", digests.isEmpty());
        return digests.toString();
    }
    /**
     * Reads the app-owned copies as the device shell sees them. The shell API tokenises the
     * command line, so every run-as argument is a plain token: no quoting, no globbing.
     */
    private SortedMap<String, String> ownedSources() throws Exception {
        SortedMap<String, String> digests = new TreeMap<>();
        String listing = device.executeShellCommand("run-as " + APP + " ls files/books").trim();
        if (listing.isEmpty()) return digests;
        for (String name : listing.split("\\s+")) {
            if (name.isEmpty() || name.endsWith(".part")) continue;
            String line = device.executeShellCommand("run-as " + APP + " sha256sum files/books/" + name).trim();
            assertTrue("owned source digest unavailable for " + name + ": " + line,
                    line.matches("[0-9a-f]{64}\\s+files/books/" + Pattern.quote(name)));
            digests.put(name, line.substring(0, 64));
        }
        return digests;
    }
    private static String anyTextSource(SortedMap<String, String> digests) {
        for (String name : digests.keySet()) if (name.endsWith(".txt")) return name;
        return "";
    }
    private void selectLine() throws Exception {
        click("select_button");
        UiObject2 view = waitId("reader_view", 10000);
        assertNotNull("reader surface missing", view);
        Rect reader = view.getVisibleBounds();
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
