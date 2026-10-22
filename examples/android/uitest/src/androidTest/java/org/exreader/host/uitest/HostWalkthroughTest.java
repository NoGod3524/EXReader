// SPDX-License-Identifier: MIT
package org.exreader.host.uitest;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;

import android.app.Instrumentation;
import android.content.Context;
import android.graphics.Rect;
import android.os.Build;
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
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.regex.Pattern;

/**
 * Black-box walkthrough of the installed host. The test APK instruments itself,
 * so it can force-stop and restart the reader process without dying.
 */
@RunWith(AndroidJUnit4.class)
public final class HostWalkthroughTest {
    private static final String APP = "org.exreader.host";
    private static final String PICKER = "com.android.documentsui";

    private interface Body { void run() throws Exception; }

    private UiDevice device;
    private Context context;
    private File evidenceDir;
    private File caseDir;
    private File shotDir;
    private int sequence;
    private long startedAt;
    private final List<JSONObject> results = new ArrayList<>();
    private final List<String> failures = new ArrayList<>();

    @Before public void setUp() throws Exception {
        Instrumentation instrumentation = InstrumentationRegistry.getInstrumentation();
        device = UiDevice.getInstance(instrumentation);
        context = instrumentation.getTargetContext();
        File base = context.getExternalFilesDir(null);
        evidenceDir = new File(base, "evidence");
        caseDir = new File(evidenceDir, "cases");
        shotDir = new File(evidenceDir, "shots");
        if (!caseDir.isDirectory() && !caseDir.mkdirs()) throw new IllegalStateException("Cannot create evidence folder");
        if (!shotDir.isDirectory() && !shotDir.mkdirs()) throw new IllegalStateException("Cannot create screenshot folder");
        device.executeShellCommand("am force-stop " + APP);
        device.executeShellCommand("pm clear " + APP);
        device.executeShellCommand("settings put global window_animation_scale 0");
        device.executeShellCommand("settings put global transition_animation_scale 0");
        device.executeShellCommand("settings put global animator_duration_scale 0");
        device.setOrientationNatural();
        device.waitForIdle();
        startedAt = System.currentTimeMillis();
    }

    @Test public void walkthrough() {
        step("cold_start_shelf", "Cold start shows an empty shelf", () -> {
            device.executeShellCommand("am start -W -n " + APP + "/.MainActivity");
            assertNotNull("shelf did not appear", waitId("shelf_panel", 20000));
            assertNotNull("import button missing", waitId("import_button", 5000));
            assertTrue("sdk label missing", text("sdk_label").contains("EXReader"));
            assertTrue("expected empty shelf", !bookExists("Sample.epub"));
        });

        step("picker_cancel", "System picker cancel returns to the shelf", () -> {
            click("import_button");
            waitPicker();
            leavePicker();
            assertTrue("cancel status missing", waitTextContains("Selection canceled", 10000));
            assertFalse("cancel added a book", bookExists("Sample.epub"));
        });

        step("import_epub", "System picker imports an EPUB into the shelf", () -> {
            pickFile("Sample.epub");
            assertTrue("import status missing", waitTextContains("Imported Sample.epub", 30000));
            assertTrue("book row missing", waitBookRow("Sample.epub"));
        });

        step("open_epub", "Open EPUB shows the first reflow page", () -> {
            clickBookRow("Sample.epub");
            assertNotNull("reader missing", waitId("reader_panel", 20000));
            assertTrue("page label missing", waitLabelContains("p.1", 15000));
            assertTrue("open status missing", text("reader_status").contains("Opened Sample.epub"));
        });

        step("page_next", "Tap the right zone to turn forward", () -> {
            tapReader(1);
            assertTrue("page 2 not reached", waitLabelContains("p.2", 15000));
        });

        step("page_prev", "Tap the left zone to turn back", () -> {
            tapReader(-1);
            assertTrue("page 1 not reached", waitLabelContains("p.1", 15000));
        });

        step("font_increase", "Font increase reflows and keeps the position", () -> {
            click("font_up");
            assertTrue("font status missing", waitIdText("reader_status", "Font size 28", 15000));
            assertTrue("page label lost", text("page_label").contains("p."));
        });

        step("font_decrease", "Font decrease reflows back", () -> {
            click("font_down");
            assertTrue("font status missing", waitIdText("reader_status", "Font size 24", 15000));
        });

        step("touch_select", "Touch drag selects real page text", () -> {
            click("select_button");
            assertTrue("select mode status missing", waitIdText("reader_status", "Select mode on", 5000));
            UiObject2 line = findLineNode("EXReader");
            assertNotNull("no accessible text line on the page", line);
            Rect bounds = line.getVisibleBounds();
            device.swipe(bounds.left + 6, bounds.centerY(), bounds.right - 6, bounds.centerY(), 24);
            assertTrue("selection status missing", waitIdText("selection_status", "Selected:", 8000));
            assertTrue("selection text too short", text("selection_status").length() > 16);
        });

        step("copy_selection", "Copy places the selection on the clipboard", () -> {
            click("copy_button");
            SystemClock.sleep(2000);
            assertTrue("copy status missing", waitIdText("reader_status", "Copied", 10000));
            assertTrue("copy count missing", text("reader_status").contains("characters"));
        });

        step("note_add", "Add an annotation from the selection", () -> {
            click("annotate_button");
            assertNotNull("comment field missing", waitId("note_comment", 8000));
            device.findObject(By.res(APP + ":id/note_comment")).setText("note one");
            clickLabel("Save");
            assertTrue("save status missing", waitIdText("reader_status", "Annotation saved", 15000));
            assertTrue("note count missing", waitButtonText("Notes (1)", 15000));
        });

        step("notes_read", "Read the annotation list back", () -> {
            click("notes_button");
            assertNotNull("note list missing", waitId("note_list", 8000));
            assertNotNull("annotation row missing", findNoteRow("note one"));
            click("notes_close");
            assertNotNull("notes panel did not close", waitId("reader_panel", 5000));
        });

        step("note_edit", "Edit the annotation comment", () -> {
            click("notes_button");
            UiObject2 row = findNoteRow("note one");
            assertNotNull("annotation row missing", row);
            row.longClick();
            assertNotNull("comment field missing", waitId("note_comment", 8000));
            device.findObject(By.res(APP + ":id/note_comment")).setText("note one edited");
            clickLabel("Save");
            assertTrue("update status missing", waitIdText("reader_status", "Annotation updated", 15000));
            assertNotNull("edited row missing", findNoteRow("note one edited"));
            click("notes_close");
        });

        step("note_navigate", "Navigate from an annotation to its page", () -> {
            click("notes_button");
            UiObject2 row = findNoteRow("note one edited");
            assertNotNull("annotation row missing", row);
            row.click();
            assertTrue("jump status missing", waitIdText("reader_status", "Jumped to annotation", 15000));
            assertNotNull("reader missing after jump", waitId("page_label", 8000));
        });

        step("rotate_landscape", "Rotation recreates the activity and keeps state", () -> {
            device.setOrientationLeft();
            SystemClock.sleep(1200);
            assertNotNull("reader missing after rotation", waitId("reader_panel", 20000));
            assertTrue("page label missing after rotation", text("page_label").contains("p."));
            assertTrue("annotations lost after rotation", waitButtonText("Notes (1)", 15000));
        });

        step("rotate_portrait", "Rotate back to portrait", () -> {
            device.setOrientationNatural();
            SystemClock.sleep(1200);
            assertNotNull("reader missing after rotation", waitId("reader_panel", 20000));
            assertTrue("page label missing after rotation", text("page_label").contains("p."));
        });

        step("activity_rebuild", "Explicit activity recreation restores the reader", () -> {
            click("rebuild_view");
            SystemClock.sleep(800);
            assertNotNull("reader missing after rebuild", waitId("reader_panel", 20000));
            assertTrue("page label missing after rebuild", text("page_label").contains("p."));
            assertTrue("annotations lost after rebuild", waitButtonText("Notes (1)", 15000));
        });

        step("background_resume", "Home and resume keeps the reader state", () -> {
            device.pressHome();
            SystemClock.sleep(900);
            device.executeShellCommand("am start -W -n " + APP + "/.MainActivity");
            assertNotNull("reader missing after resume", waitId("reader_panel", 20000));
            assertTrue("page label missing after resume", text("page_label").contains("p."));
        });

        step("process_restart_reflow", "Process restart restores page and annotations", () -> {
            tapReader(1);
            assertTrue("page 2 not reached", waitLabelContains("p.2", 15000));
            device.executeShellCommand("am force-stop " + APP);
            SystemClock.sleep(900);
            device.executeShellCommand("am start -W -n " + APP + "/.MainActivity");
            assertNotNull("reader missing after restart", waitId("reader_panel", 25000));
            assertTrue("page 2 not restored", waitLabelContains("p.2", 20000));
            assertTrue("annotations lost after restart", waitButtonText("Notes (1)", 20000));
        });

        step("notes_after_restart", "Annotations survive the process restart", () -> {
            click("notes_button");
            assertNotNull("annotation missing after restart", findNoteRow("note one edited"));
            click("notes_close");
        });

        step("note_delete", "Delete the annotation", () -> {
            click("notes_button");
            UiObject2 row = findNoteRow("note one edited");
            assertNotNull("annotation row missing", row);
            row.longClick();
            assertNotNull("comment field missing", waitId("note_comment", 8000));
            clickLabel("Delete");
            assertTrue("delete status missing", waitIdText("reader_status", "Annotation deleted", 15000));
            assertTrue("note count not zero", waitButtonText("Notes (0)", 15000));
        });

        step("import_txt", "Import a plain text book", () -> {
            backToShelf();
            pickFile("Sample.txt");
            assertTrue("txt import missing", waitTextContains("Imported Sample.txt", 30000));
            assertTrue("txt row missing", waitBookRow("Sample.txt"));
        });

        step("open_txt", "Open the text book", () -> {
            clickBookRow("Sample.txt");
            assertNotNull("reader missing", waitId("reader_panel", 20000));
            assertTrue("txt page missing", waitLabelContains("p.1", 15000));
            backToShelf();
        });

        step("import_pdf", "Import the fixed-page PDF", () -> {
            pickFile("Sample.pdf");
            assertTrue("pdf import missing", waitTextContains("Imported Sample.pdf", 30000));
            assertTrue("pdf row missing", waitBookRow("Sample.pdf"));
        });

        step("open_pdf", "Open the PDF in fixed-page mode", () -> {
            clickBookRow("Sample.pdf");
            assertNotNull("reader missing", waitId("reader_panel", 20000));
            assertTrue("pdf page label missing", waitLabelContains("PDF p.1/5", 20000));
            assertNotNull("zoom controls missing", find("zoom_up"));
        });

        step("pdf_next", "PDF page forward", () -> {
            tapReader(1);
            assertTrue("pdf page 2 not reached", waitLabelContains("PDF p.2/5", 15000));
        });

        step("pdf_prev", "PDF page back", () -> {
            tapReader(-1);
            assertTrue("pdf page 1 not reached", waitLabelContains("PDF p.1/5", 15000));
        });

        step("pdf_zoom", "PDF zoom changes the rendered page", () -> {
            click("zoom_up");
            assertTrue("zoom status missing", waitIdText("zoom_label", "1.25", 15000));
            click("zoom_down");
            assertTrue("zoom reset missing", waitIdText("zoom_label", "1.00", 15000));
        });

        step("pdf_select_copy", "Select and copy PDF text", () -> {
            click("select_button");
            assertTrue("select mode missing", waitIdText("reader_status", "Select mode on", 5000));
            UiObject2 line = findLineNode("A");
            assertNotNull("pdf text line missing", line);
            line.click();
            assertTrue("pdf selection missing", waitIdText("selection_status", "Selected: A", 8000));
            click("copy_button");
            assertTrue("pdf copy missing", waitIdText("reader_status", "Copied 1 characters", 8000));
        });

        step("pdf_note_add", "Add a fixed-page annotation", () -> {
            click("annotate_button");
            assertNotNull("comment field missing", waitId("note_comment", 8000));
            device.findObject(By.res(APP + ":id/note_comment")).setText("pdf note");
            clickLabel("Save");
            assertTrue("pdf note save missing", waitIdText("reader_status", "Annotation saved", 15000));
            assertTrue("pdf note count missing", waitButtonText("Notes (1)", 15000));
        });

        step("pdf_process_restart", "PDF page progress and notes survive restart", () -> {
            click("selection_cancel");
            tapReader(1);
            assertTrue("pdf page 2 not reached", waitLabelContains("PDF p.2/5", 15000));
            device.executeShellCommand("am force-stop " + APP);
            SystemClock.sleep(900);
            device.executeShellCommand("am start -W -n " + APP + "/.MainActivity");
            assertNotNull("pdf reader missing after restart", waitId("reader_panel", 25000));
            assertTrue("pdf page 2 not restored", waitLabelContains("PDF p.2/5", 20000));
            assertTrue("pdf note lost after restart", waitButtonText("Notes (1)", 20000));
        });

        step("pdf_note_delete", "Delete the fixed-page annotation", () -> {
            click("notes_button");
            UiObject2 row = findNoteRow("pdf note");
            assertNotNull("pdf annotation row missing", row);
            row.longClick();
            assertNotNull("comment field missing", waitId("note_comment", 8000));
            clickLabel("Delete");
            assertTrue("pdf delete status missing", waitIdText("reader_status", "Annotation deleted", 15000));
            assertTrue("pdf note count not zero", waitButtonText("Notes (0)", 15000));
        });

        step("import_bigchapter", "Import a single large chapter", () -> {
            backToShelf();
            pickFile("BigChapter.epub");
            assertTrue("big chapter import missing", waitTextContains("Imported BigChapter.epub", 60000));
            assertTrue("big chapter row missing", waitBookRow("BigChapter.epub"));
        });

        step("open_bigchapter", "Open the large chapter", () -> {
            clickBookRow("BigChapter.epub");
            assertNotNull("big chapter reader missing", waitId("reader_panel", 30000));
            assertTrue("big chapter page missing", waitLabelContains("p.1", 20000));
        });

        step("bigchapter_next", "Page inside the large chapter", () -> {
            tapReader(1);
            assertTrue("big chapter page 2 missing", waitLabelContains("p.2", 20000));
            backToShelf();
        });

        step("import_ambiguous", "Import a book with repeated text", () -> {
            pickFile("Ambiguous.epub");
            assertTrue("ambiguous import missing", waitTextContains("Imported Ambiguous.epub", 30000));
        });

        step("ambiguous_restore", "A repeated-text anchor is reported as not exact", () -> {
            clickBookRow("Ambiguous.epub");
            assertNotNull("ambiguous reader missing", waitId("reader_panel", 20000));
            assertTrue("ambiguous page 1 missing", waitLabelContains("p.1", 15000));
            tapReader(1);
            assertTrue("ambiguous page 2 missing", waitLabelContains("p.2", 15000));
            tapReader(1);
            assertTrue("ambiguous page 3 missing", waitLabelContains("p.3", 15000));
            backToShelf();
            clickBookRow("Ambiguous.epub");
            assertNotNull("ambiguous reader missing on reopen", waitId("reader_panel", 20000));
            assertTrue("ambiguity was not reported",
                    waitIdText("reader_status", "not exact", 20000));
        });

        step("corrupt_import", "A malformed EPUB is reported without a crash", () -> {
            backToShelf();
            pickFile("Broken.epub");
            assertTrue("error status missing", waitTextContains("Could not open Broken.epub", 30000));
            assertFalse("corrupt book entered the shelf", bookExists("Broken.epub"));
        });

        step("retry_import", "Retry with a valid book after the failure", () -> {
            pickFile("Second.epub");
            assertTrue("retry import missing", waitTextContains("Imported Second.epub", 30000));
            assertTrue("retry row missing", waitBookRow("Second.epub"));
        });

        step("duplicate_import", "Duplicate import reuses the existing row", () -> {
            pickFile("Sample.epub");
            assertTrue("duplicate status missing", waitTextContains("Already in shelf: Sample.epub", 30000));
        });

        step("too_large", "The 32 MiB host limit is enforced", () -> {
            pickFile("TooLarge.epub");
            assertTrue("limit status missing", waitTextContains("exceeds 32 MiB", 30000));
        });

        step("cancel_large_import", "Cancel an in-flight import", () -> {
            pickFile("Large.epub");
            assertNotNull("cancel control missing", waitId("cancel_button", 8000));
            click("cancel_button");
            assertTrue("cancel status missing", waitTextContains("Import canceled", 30000));
            assertFalse("canceled book entered the shelf", bookExists("Large.epub"));
        });

        step("book_switch", "Switch between two books without stale pages", () -> {
            clickBookRow("Sample.epub");
            assertNotNull("first book missing", waitId("reader_panel", 20000));
            backToShelf();
            clickBookRow("Second.epub");
            assertNotNull("second book missing", waitId("reader_panel", 20000));
            assertTrue("wrong book title", text("book_title").contains("Second.epub"));
            assertTrue("wrong page", text("page_label").contains("p."));
            backToShelf();
        });

        step("accessibility_semantics", "Controls and page lines expose accessible names", () -> {
            UiObject2 importButton = waitId("import_button", 8000);
            assertNotNull(importButton);
            assertNotNull("import has no accessible name", importButton.getContentDescription());
            assertTrue("import name missing", importButton.getContentDescription().toString().contains("Import"));
            clickBookRow("Second.epub");
            assertNotNull("reader missing", waitId("reader_view", 15000));
            UiObject2 reader = find("reader_view");
            assertNotNull(reader);
            assertNotNull("reader has no accessible name", reader.getContentDescription());
            assertTrue("reader name missing", reader.getContentDescription().toString().contains("Reading page"));
            assertNotNull("no accessible text line", findLineNode("Second"));
            assertTrue("select has no accessible name",
                    find("select_button").getContentDescription().toString().contains("Select"));
        });

        step("native_metrics", "Native page metrics and handle closure are logged", () -> {
            String log = device.executeShellCommand("logcat -d -s EXRHost:I");
            int pages = count(log, "metric {\"event\":\"page\"");
            int opens = count(log, "handle open book=");
            int closes = count(log, "handle close book=");
            int copies = count(log, "metric {\"event\":\"copy\"");
            assertTrue("too few page metrics: " + pages, pages >= 12);
            assertTrue("no native handle opens", opens >= 3);
            assertTrue("no native handle closes", closes >= 2);
            assertTrue("no copy metric", copies >= 2);
        });

        writeValidation();
        if (!failures.isEmpty()) {
            StringBuilder message = new StringBuilder(failures.size() + " case(s) failed:");
            for (String failure : failures) message.append("\n").append(failure);
            throw new AssertionError(message.toString());
        }
    }

    private void step(String id, String title, Body body) {
        sequence++;
        long started = SystemClock.uptimeMillis();
        String status = "pass";
        String detail = "";
        String screenshot = null;
        try {
            body.run();
        } catch (Throwable error) {
            status = "fail";
            detail = error.getClass().getSimpleName() + ": " + error.getMessage();
            failures.add(id + " - " + detail);
            screenshot = screenshot(id + "-fail");
        }
        if (screenshot == null) screenshot = screenshot(id);
        long duration = SystemClock.uptimeMillis() - started;
        try {
            JSONObject entry = new JSONObject();
            entry.put("id", id);
            entry.put("title", title);
            entry.put("status", status);
            entry.put("detail", detail);
            entry.put("duration_ms", duration);
            if (screenshot != null) entry.put("screenshot", screenshot);
            results.add(entry);
            File file = new File(caseDir, String.format(Locale.US, "%02d-%s.json", sequence, id));
            try (FileOutputStream output = new FileOutputStream(file)) {
                output.write(entry.toString(2).getBytes(StandardCharsets.UTF_8));
            }
        } catch (Throwable error) {
            failures.add(id + " - evidence write failed: " + error);
        }
    }

    private String screenshot(String id) {
        String name = String.format(Locale.US, "%02d-%s.png", sequence, id);
        File file = new File(shotDir, name);
        for (int attempt = 0; attempt < 3; attempt++) {
            try {
                device.waitForIdle();
                if (device.takeScreenshot(file)) return "shots/" + name;
            } catch (Throwable ignored) {
            }
            SystemClock.sleep(300);
        }
        return null;
    }

    private void writeValidation() {
        try {
            boolean emulator = Build.FINGERPRINT.contains("generic")
                    || Build.MODEL.contains("sdk_gphone")
                    || Build.HARDWARE.contains("ranchu")
                    || Build.PRODUCT.contains("sdk");
            JSONObject validation = new JSONObject();
            validation.put("schema", 1);
            validation.put("package", APP);
            validation.put("device_is_emulator", emulator);
            validation.put("physical_device_execution", !emulator);
            validation.put("api", Build.VERSION.SDK_INT);
            validation.put("abi", Build.SUPPORTED_ABIS.length > 0 ? Build.SUPPORTED_ABIS[0] : "unknown");
            validation.put("model", Build.MODEL);
            validation.put("hardware", Build.HARDWARE);
            validation.put("started_at", new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssXXX", Locale.US).format(new Date(startedAt)));
            validation.put("duration_ms", System.currentTimeMillis() - startedAt);
            JSONArray cases = new JSONArray();
            int passed = 0;
            int failed = 0;
            for (JSONObject record : results) {
                cases.put(record);
                if ("pass".equals(record.getString("status"))) passed++;
                else failed++;
            }
            validation.put("cases", cases);
            JSONObject summary = new JSONObject();
            summary.put("total", results.size());
            summary.put("passed", passed);
            summary.put("failed", failed);
            summary.put("skipped", 0);
            validation.put("summary", summary);
            JSONArray limitations = new JSONArray();
            limitations.put("x86_64 emulator only; no physical-device installation or signing");
            limitations.put("TalkBack human review is not part of this run");
            limitations.put("fixed-page fixture is the repository PDF with one text glyph per page");
            limitations.put("large-chapter case uses a 2 MiB single chapter, not a multi-megabyte stress book");
            limitations.put("cancellation is cooperative between host copy, SDK import and render boundaries");
            validation.put("limitations", limitations);
            File file = new File(evidenceDir, "validation.json");
            try (FileOutputStream output = new FileOutputStream(file)) {
                output.write(validation.toString(2).getBytes(StandardCharsets.UTF_8));
            }
        } catch (Throwable error) {
            failures.add("validation write failed: " + error);
        }
    }

    private void launch() throws Exception {
        device.executeShellCommand("am start -W -n " + APP + "/.MainActivity");
        device.waitForIdle();
    }

    private void waitPicker() throws Exception {
        long deadline = SystemClock.uptimeMillis() + 20000;
        while (SystemClock.uptimeMillis() < deadline) {
            if (device.hasObject(By.pkg(PICKER)) || device.hasObject(By.pkg("com.google.android.documentsui"))) return;
            SystemClock.sleep(200);
        }
        throw new AssertionError("system picker did not open");
    }

    private void leavePicker() {
        for (int attempt = 0; attempt < 4; attempt++) {
            if (device.hasObject(By.pkg(APP))) return;
            device.pressBack();
            SystemClock.sleep(600);
        }
    }

    private void pickFile(String name) throws Exception {
        click("import_button");
        waitPicker();
        long deadline = SystemClock.uptimeMillis() + 25000;
        while (SystemClock.uptimeMillis() < deadline) {
            UiObject2 file = device.findObject(By.textContains(name));
            if (file != null && file.isEnabled()) {
                file.click();
                device.wait(Until.hasObject(By.pkg(APP)), 10000);
                return;
            }
            if (device.hasObject(By.textContains("Files in Download"))) {
                device.swipe(device.getDisplayWidth() / 2, (int) (device.getDisplayHeight() * 0.78),
                        device.getDisplayWidth() / 2, (int) (device.getDisplayHeight() * 0.25), 24);
                SystemClock.sleep(600);
                continue;
            }
            UiObject2 folder = findLabel("Download");
            if (folder == null) folder = findLabel("Downloads");
            if (folder != null && folder.getVisibleBounds().width() > 0) {
                folder.click();
                SystemClock.sleep(700);
                continue;
            }
            UiObject2 roots = device.findObject(By.descContains("Show roots"));
            if (roots != null) {
                roots.click();
                SystemClock.sleep(500);
                continue;
            }
            SystemClock.sleep(250);
        }
        throw new AssertionError("picker never listed " + name);
    }

    private void backToShelf() throws Exception {
        if (device.hasObject(By.res(APP + ":id/notes_panel"))) {
            click("notes_close");
        }
        UiObject2 back = waitId("back_button", 4000);
        if (back != null) {
            back.click();
            assertNotNull("shelf missing after back", waitId("shelf_panel", 15000));
        }
    }

    private void tapReader(int delta) throws Exception {
        UiObject2 reader = waitId("reader_view", 8000);
        assertNotNull("reader view missing", reader);
        Rect bounds = reader.getVisibleBounds();
        int y = bounds.centerY();
        int x = delta < 0 ? bounds.left + Math.max(20, bounds.width() / 6)
                : bounds.right - Math.max(20, bounds.width() / 6);
        device.click(x, y);
        SystemClock.sleep(250);
    }

    private UiObject2 findLineNode(String needle) throws Exception {
        Rect reader = boundsOf("reader_view");
        if (reader == null) return null;
        long deadline = SystemClock.uptimeMillis() + 10000;
        while (SystemClock.uptimeMillis() < deadline) {
            for (UiObject2 object : device.findObjects(By.textContains(needle))) {
                Rect bounds = object.getVisibleBounds();
                if (bounds.width() <= 0 || bounds.height() <= 0) continue;
                if (bounds.top >= reader.top - 2 && bounds.bottom <= reader.bottom + 2
                        && bounds.left >= reader.left - 2 && bounds.right <= reader.right + 2
                        && bounds.height() <= reader.height() + 4) {
                    return object;
                }
            }
            SystemClock.sleep(200);
        }
        return null;
    }

    private UiObject2 findNoteRow(String needle) throws Exception {
        Rect list = boundsOf("note_list");
        if (list == null) return null;
        long deadline = SystemClock.uptimeMillis() + 10000;
        while (SystemClock.uptimeMillis() < deadline) {
            for (UiObject2 object : device.findObjects(By.textContains(needle))) {
                Rect bounds = object.getVisibleBounds();
                if (bounds.width() <= 0 || bounds.height() <= 0) continue;
                if (bounds.top >= list.top - 2 && bounds.bottom <= list.bottom + 2) return object;
            }
            SystemClock.sleep(200);
        }
        return null;
    }

    private boolean waitBookRow(String title) throws Exception {
        long deadline = SystemClock.uptimeMillis() + 15000;
        while (SystemClock.uptimeMillis() < deadline) {
            if (bookExists(title)) return true;
            SystemClock.sleep(200);
        }
        return false;
    }

    private boolean bookExists(String title) throws Exception {
        Rect list = boundsOf("book_list");
        if (list == null) return false;
        for (UiObject2 object : device.findObjects(By.textContains(title))) {
            Rect bounds = object.getVisibleBounds();
            if (bounds.width() <= 0 || bounds.height() <= 0) continue;
            if (bounds.top >= list.top - 2 && bounds.bottom <= list.bottom + 2) return true;
        }
        return false;
    }

    private void clickBookRow(String title) throws Exception {
        Rect list = boundsOf("book_list");
        assertNotNull("book list missing", list);
        long deadline = SystemClock.uptimeMillis() + 10000;
        while (SystemClock.uptimeMillis() < deadline) {
            for (UiObject2 object : device.findObjects(By.textContains(title))) {
                Rect bounds = object.getVisibleBounds();
                if (bounds.width() > 0 && bounds.height() > 0
                        && bounds.top >= list.top - 2 && bounds.bottom <= list.bottom + 2) {
                    object.click();
                    SystemClock.sleep(250);
                    return;
                }
            }
            SystemClock.sleep(200);
        }
        throw new AssertionError("book row not found: " + title);
    }

    private Rect boundsOf(String id) {
        UiObject2 object = device.findObject(By.res(APP + ":id/" + id));
        if (object == null) return null;
        Rect bounds = object.getVisibleBounds();
        return bounds.width() > 0 && bounds.height() > 0 ? bounds : null;
    }

    private UiObject2 find(String id) {
        return device.findObject(By.res(APP + ":id/" + id));
    }

    private UiObject2 waitId(String id, long timeout) {
        return device.wait(Until.findObject(By.res(APP + ":id/" + id)), timeout);
    }

    private void click(String id) throws Exception {
        UiObject2 object = waitId(id, 10000);
        assertNotNull("control not found: " + id, object);
        object.click();
        SystemClock.sleep(200);
    }

    private String text(String id) {
        UiObject2 object = find(id);
        if (object == null) return "";
        CharSequence value = object.getText();
        return value == null ? "" : value.toString();
    }

    private boolean waitLabelContains(String needle, long timeout) throws Exception {
        long deadline = SystemClock.uptimeMillis() + timeout;
        while (SystemClock.uptimeMillis() < deadline) {
            if (text("page_label").contains(needle)) return true;
            SystemClock.sleep(150);
        }
        return false;
    }

    private boolean waitButtonText(String needle, long timeout) throws Exception {
        long deadline = SystemClock.uptimeMillis() + timeout;
        String upper = needle.toUpperCase(Locale.ROOT);
        while (SystemClock.uptimeMillis() < deadline) {
            if (text("notes_button").toUpperCase(Locale.ROOT).contains(upper)) return true;
            SystemClock.sleep(150);
        }
        return false;
    }

    private boolean waitIdText(String id, String needle, long timeout) throws Exception {
        long deadline = SystemClock.uptimeMillis() + timeout;
        while (SystemClock.uptimeMillis() < deadline) {
            if (text(id).contains(needle)) return true;
            SystemClock.sleep(150);
        }
        return false;
    }

    private boolean waitTextContains(String needle, long timeout) throws Exception {
        long deadline = SystemClock.uptimeMillis() + timeout;
        while (SystemClock.uptimeMillis() < deadline) {
            if (device.hasObject(By.textContains(needle))) return true;
            SystemClock.sleep(150);
        }
        return false;
    }

    private UiObject2 findLabel(String label) {
        return device.findObject(By.text(Pattern.compile("(?i)^" + Pattern.quote(label) + "$")));
    }

    private void clickLabel(String label) throws Exception {
        long deadline = SystemClock.uptimeMillis() + 8000;
        while (SystemClock.uptimeMillis() < deadline) {
            UiObject2 object = findLabel(label);
            if (object != null && object.isEnabled()) {
                object.click();
                SystemClock.sleep(200);
                return;
            }
            SystemClock.sleep(150);
        }
        throw new AssertionError("button not found: " + label);
    }

    private static int count(String value, String needle) {
        int count = 0;
        int index = 0;
        while ((index = value.indexOf(needle, index)) >= 0) {
            count++;
            index += needle.length();
        }
        return count;
    }
}
