// SPDX-License-Identifier: MIT
package org.exreader.a11y;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;

import android.content.Context;
import android.graphics.Rect;
import android.os.Build;
import android.os.Bundle;
import android.os.SystemClock;
import android.view.accessibility.AccessibilityNodeInfo;

import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.uiautomator.By;
import androidx.test.uiautomator.StaleObjectException;
import androidx.test.uiautomator.UiDevice;
import androidx.test.uiautomator.UiObject2;
import androidx.test.uiautomator.Until;

import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;

import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Read-only accessibility audit of the installed EXReader Android host.
 *
 * The harness is a separate APK: the audited application is installed from its own
 * owner build, is never modified, re-signed or instrumented here, and every case only
 * observes the public accessibility tree (UiAutomator / AccessibilityNodeInfo) plus the
 * platform settings a real user can change (font scale, display density, orientation).
 *
 * A semantic tree captured on an emulator does not prove TalkBack speech on a physical
 * device; every such claim stays "unverified" in the emitted report.
 */
@RunWith(AndroidJUnit4.class)
public final class A11yAuditTest {
    private static final String APP = "org.exreader.host";
    private static final String PICKER = "com.android.documentsui";
    private static final int MIN_TARGET_DP = 48;
    private static final String[] EXPECTED = new String[]{
            "shelf_semantics",
            "hidden_panels",
            "status_announcement",
            "import_picker",
            "shelf_row_and_search",
            "organize_panel",
            "back_navigation",
            "reader_line_nodes",
            "reader_page_turn",
            "reader_toolbar_state",
            "annotate_flow",
            "notes_panel",
            "rotation",
            "large_font",
            "display_scaling"
    };

    private UiDevice device;
    private Context context;
    private Bundle args;
    private File output;
    private File trees;
    private File shots;
    private File caseDir;
    private int densityDpi;
    private final JSONArray cases = new JSONArray();
    private final JSONArray captures = new JSONArray();

    /** A named gap in the audited surface, carrying the minimal patch it would need. */
    private static final class Finding extends Exception {
        final String patch;
        Finding(String name, String patch) {
            super(name);
            this.patch = patch;
        }
    }

    private interface Body {
        void run() throws Exception;
    }

    @Before public void setup() throws Exception {
        device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation());
        context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        args = InstrumentationRegistry.getArguments();
        output = new File(context.getExternalFilesDir(null), "a11y-evidence");
        assertFalse("earlier accessibility evidence must not be reused", output.exists());
        trees = new File(output, "trees");
        shots = new File(output, "shots");
        caseDir = new File(output, "cases");
        assertTrue(trees.mkdirs());
        assertTrue(shots.mkdirs());
        assertTrue(caseDir.mkdirs());
        shell("settings put global window_animation_scale 0");
        shell("settings put global transition_animation_scale 0");
        shell("settings put global animator_duration_scale 0");
        shell("settings put global hide_error_dialogs 1");
        shell("settings put system font_scale 1.0");
        shell("wm density reset");
        SystemClock.sleep(1500);
        device.setOrientationNatural();
        SystemClock.sleep(500);
        device.pressHome();
        SystemClock.sleep(400);
        shell("am force-stop " + APP);
        SystemClock.sleep(300);
    }

    private String arg(String name) {
        String value = args == null ? null : args.getString(name);
        return value == null ? "" : value;
    }

    @After public void restore() throws Exception {
        if (device == null) {
            return;
        }
        try {
            shell("settings put system font_scale 1.0");
            shell("wm density reset");
            device.setOrientationNatural();
            SystemClock.sleep(600);
            device.pressHome();
            SystemClock.sleep(300);
            shell("am force-stop " + APP);
        } catch (Throwable ignored) {
            // The report already carries every recorded case; platform reset is best effort.
        }
    }

    @Test public void audit() throws Exception {
        session("shelf_semantics", this::shelfSemantics);
        session("hidden_panels", this::hiddenPanels);
        session("status_announcement", this::statusAnnouncement);
        session("import_picker", this::importPicker);
        session("shelf_row_and_search", this::shelfRowAndSearch);
        session("organize_panel", this::organizePanel);
        session("back_navigation", this::backNavigation);
        session("reader_line_nodes", this::readerLineNodes);
        session("reader_page_turn", this::readerPageTurn);
        session("reader_toolbar_state", this::readerToolbarState);
        session("annotate_flow", this::annotateFlow);
        session("notes_panel", this::notesPanel);
        session("rotation", this::rotation);
        session("large_font", this::largeFont);
        session("display_scaling", this::displayScaling);
        publish();
    }

    // ------------------------------------------------------------------ cases

    private void shelfSemantics() throws Exception {
        launch("");
        JSONObject capture = waitAndCapture("01-shelf-default", APP);
        for (String id : new String[]{"shelf_panel", "shelf_title", "import_button", "refresh_button",
                "more_button", "shelf_search", "shelf_summary", "book_list", "status_text"}) {
            requireView(capture, id);
        }
        JSONObject summary = view(capture, "shelf_summary");
        expect(summary.optJSONObject("extras") != null,
                "audited_host_identity_missing",
                "The audited APK must be the owner debug build; exreader.shelf observations were absent");
        requireNamed(capture);
        requireTargetSize(capture);
        requireLayoutIntegrity(capture);
    }

    private void hiddenPanels() throws Exception {
        JSONObject capture = waitAndCapture("02-shelf-hidden", APP);
        for (String id : new String[]{"notes_panel", "reader_panel", "loading_overlay", "selection_bar"}) {
            expect(view(capture, id) == null,
                    "hidden_panel_exposed:" + id,
                    "A GONE panel must stay out of the accessibility tree (importantForAccessibility=noHideDescendants or keep GONE)");
        }
        expect(view(capture, "shelf_panel") != null, "shelf_panel_missing", "The shelf panel must be present");
    }

    private void statusAnnouncement() throws Exception {
        click("refresh_button");
        SystemClock.sleep(900);
        JSONObject refreshed = capture("03-shelf-status");
        JSONObject status = view(refreshed, "status_text");
        expect(status != null, "status_text_missing", "status_text must be present");
        int live = status.optInt("live_region", 0);
        expect(live == 1 || live == 2,
                "status_not_announced",
                "Add android:accessibilityLiveRegion=\"polite\" to status_text and reader_status (res/layout/activity_main.xml)");
    }

    private void importPicker() throws Exception {
        click("import_button");
        JSONObject picker = waitAndCapture("04-system-picker", PICKER);
        expect(picker.getJSONArray("interactive").length() > 0,
                "picker_empty",
                "The system picker must expose actionable nodes for the import entry to be usable");
        pick("Sample.epub");
        assertTrue("host did not return from the system picker",
                device.wait(Until.hasObject(By.pkg(APP)), 20000));
        boolean reported = device.wait(Until.hasObject(By.textContains("Imported Sample.epub")), 45000);
        device.wait(Until.hasObject(By.textStartsWith("EXReader Android Sample")), 30000);
        JSONObject capture = waitAndCapture("05-shelf-imported", APP);
        expect(reported, "import_result_not_reported", "The import result must be reported to the user");
        JSONObject row = firstRow(capture);
        expect(row != null, "imported_book_missing", "The imported book must appear on the shelf");
        expect(row.optString("text").contains("EXReader Android Sample"),
                "imported_book_text", "The shelf row must carry the imported title");
    }

    private void shelfRowAndSearch() throws Exception {
        JSONObject capture = waitAndCapture("06-shelf-row", APP);
        JSONObject row = firstRow(capture);
        expect(row != null, "shelf_row_missing", "A shelf row must be exposed");
        String text = row.optString("text");
        expect(text.contains("EPUB"), "shelf_row_format_missing",
                "The row label must state the format next to title/author/size");
        expect(!row.optString("name").isEmpty(), "shelf_row_unnamed", "The row must have a single accessible name");
        JSONObject list = view(capture, "book_list");
        expect(list != null, "book_list_missing", "The shelf list must be present");
        expect(list.optBoolean("scrollable"), "shelf_list_not_scrollable",
                "Keep the shelf list scrollable for accessibility scrolling");
        JSONObject search = view(capture, "shelf_search");
        expect(search != null, "shelf_search_missing", "The search field must be present");
        expect(search.optBoolean("editable"), "shelf_search_not_editable", "The search field must be editable");
        expect(!search.optString("name").isEmpty(), "shelf_search_unnamed", "The search field needs a label or hint");
        UiObject2 field = device.wait(Until.findObject(By.res(APP + ":id/shelf_search")), 10000);
        assertNotNull(field);
        field.setText("missing title");
        SystemClock.sleep(1200);
        JSONObject filtered = capture("07-shelf-search-empty");
        expect(firstRow(filtered) == null, "search_did_not_filter", "The shelf must reflect the search query");
        hideKeyboard();
        UiObject2 clear = device.wait(Until.findObject(By.res(APP + ":id/shelf_search")), 10000);
        assertNotNull(clear);
        clear.setText("");
        SystemClock.sleep(1200);
        hideKeyboard();
    }

    private void organizePanel() throws Exception {
        click("more_button");
        assertTrue("the More menu must list Organize", device.wait(Until.hasObject(By.text("Organize")), 10000));
        clickText("Organize");
        JSONObject capture = waitAndCapture("08-organize", APP);
        for (String label : new String[]{"Close", "Up", "Kind", "Removed", "New", "Books",
                "Add book", "Saved intent", "Previous", "Next", "Refresh", "Cancel"}) {
            expect(findByText(capture.getJSONObject("tree"), label) != null,
                    "organize_control_missing:" + label,
                    "The organizer must expose its '" + label + "' control");
        }
        requireNamed(capture);
        requireTargetSize(capture);
        requireLayoutIntegrity(capture);
        JSONObject container = findByDesc(capture.getJSONObject("tree"), "Organize panel");
        expect(container != null, "organize_container_unnamed", "The organizer container needs a name");
        expect(!container.optBoolean("clickable"),
                "organize_container_clickable",
                "Drop setClickable(true) / the container contentDescription in OrganizationPanel so an empty-area "
                        + "container is not announced as an activatable control");
    }

    private void backNavigation() throws Exception {
        device.pressBack();
        JSONObject shelf = waitAndCapture("09-back-organize", APP);
        expect(findByDesc(shelf.getJSONObject("tree"), "Organize panel") == null,
                "back_did_not_close_organize", "Back must close the organizer without leaving the shelf");
        requireView(shelf, "shelf_panel");
        openFirstBook();
        JSONObject reader = waitAndCapture("10-reader", APP);
        requireView(reader, "reader_panel");
        device.pressBack();
        JSONObject back = waitAndCapture("11-back-reader", APP);
        expect(view(back, "reader_panel") == null, "back_did_not_leave_reader", "Back must leave the reader");
        requireView(back, "shelf_panel");
    }

    private void readerLineNodes() throws Exception {
        openFirstBook();
        JSONObject capture = waitAndCapture("12-reader-lines", APP);
        AccessibilityNodeInfo root = root();
        List<AccessibilityNodeInfo> views = root.findAccessibilityNodeInfosByViewId(APP + ":id/reader_view");
        assertFalse("reader_view must be present", views.isEmpty());
        List<AccessibilityNodeInfo> lines = views.get(0).findAccessibilityNodeInfosByText("EXReader");
        expect(!lines.isEmpty(),
                "reader_text_not_exposed",
                "Publish the visible page text as accessibility nodes: ReaderView already builds one virtual node "
                        + "per line in AccessibilityNodeProvider; keep lineText populated for every page");
        int named = 0;
        for (AccessibilityNodeInfo line : lines) {
            if (!safe(line.getText()).isEmpty()) {
                named++;
            }
        }
        expect(named > 0, "reader_line_text_empty", "Each virtual line node must carry its own text");
        JSONObject node = view(capture, "reader_view");
        expect(node != null, "reader_view_missing", "The reading surface must be present");
        expect(node.optString("desc").startsWith("Reading page"),
                "reader_surface_description",
                "Keep the ReaderView content description stating page position for the reading surface");
    }

    private void readerPageTurn() throws Exception {
        JSONObject observed = capture("13-reader-actions");
        String before = pageLabel(observed);
        AccessibilityNodeInfo root = root();
        List<AccessibilityNodeInfo> views = root.findAccessibilityNodeInfosByViewId(APP + ":id/reader_view");
        assertFalse("reader_view must be present", views.isEmpty());
        AccessibilityNodeInfo view = views.get(0);
        boolean forward = false;
        boolean backward = false;
        for (AccessibilityNodeInfo.AccessibilityAction action : view.getActionList()) {
            if (action.getId() == AccessibilityNodeInfo.ACTION_SCROLL_FORWARD) {
                forward = true;
            }
            if (action.getId() == AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD) {
                backward = true;
            }
        }
        expect(forward && backward,
                "page_turn_not_reachable_by_semantics",
                "ReaderView.onInitializeAccessibilityNodeInfo should add ACTION_SCROLL_FORWARD/BACKWARD and route them "
                        + "to MainActivity.turnPage(1)/turnPage(-1); alternatively add visible Next/Previous page "
                        + "buttons to res/layout/activity_main.xml. Today a screen reader user cannot change pages "
                        + "because the only page-turn path is a raw left/right tap zone.");
        expect(view.performAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD), "page_turn_action_refused",
                "ACTION_SCROLL_FORWARD must be accepted once advertised");
        SystemClock.sleep(2500);
        JSONObject after = capture("14-reader-turned");
        expect(!pageLabel(after).equals(before), "page_turn_action_ineffective",
                "The advertised scroll action must actually advance the page");
    }

    private void readerToolbarState() throws Exception {
        JSONObject capture = waitAndCapture("15-reader-toolbar", APP);
        for (String id : new String[]{"back_button", "rebuild_view", "font_up", "font_down",
                "select_button", "notes_button", "page_label", "font_label", "reader_view"}) {
            requireView(capture, id);
        }
        JSONObject up = view(capture, "font_up");
        JSONObject label = view(capture, "font_label");
        String size = label == null ? "" : label.optString("text");
        expect(size.startsWith("Size "), "font_size_value_missing",
                "The current font size must stay readable next to its controls");
        String state = up.optString("state");
        String value = size.replace("Size ", "");
        expect(state.contains(value),
                "control_state_not_exposed",
                "Set an AccessibilityNodeInfo stateDescription on font_up/font_down (or include the current size in "
                        + "their content description) so 'Increase font size' announces the value it changes "
                        + "(WCAG 4.1.2 name/role/value).");
        expect(!up.optString("name").isEmpty(), "font_control_unnamed", "The font controls must be named");
        requireNamed(capture);
        requireTargetSize(capture);
        requireLayoutIntegrity(capture);
    }

    private void annotateFlow() throws Exception {
        click("select_button");
        SystemClock.sleep(500);
        JSONObject mode = capture("16-reader-select-mode");
        JSONObject surface = view(mode, "reader_view");
        assertNotNull("reader_view must be present", surface);
        JSONObject box = surface.getJSONObject("bounds");
        int centerX = (box.getInt("left") + box.getInt("right")) / 2;
        int centerY = (box.getInt("top") + box.getInt("bottom")) / 2;
        device.click(centerX, centerY);
        SystemClock.sleep(700);
        JSONObject selected = capture("17-reader-selected");
        JSONObject bar = view(selected, "selection_bar");
        expect(bar != null, "selection_bar_missing",
                "A tap in select mode must select a glyph and reveal the selection bar (ReaderView.hit + updateSelection)");
        click("annotate_button");
        JSONObject dialog = waitAndCapture("18-annotate-dialog", APP);
        expect(findByText(dialog.getJSONObject("tree"), "New annotation") != null,
                "annotate_dialog_untitled", "The annotation dialog must carry a title");
        JSONObject input = findClass(dialog.getJSONObject("tree"), "android.widget.EditText");
        expect(input != null, "annotate_input_missing", "The annotation dialog needs a comment field");
        expect(!input.optString("name").isEmpty(), "annotate_input_unnamed",
                "Give the comment field a visible label; a bare hint is used as name only while the field is empty");
        requireTargetSize(dialog);
        UiObject2 field = device.findObject(By.clazz("android.widget.EditText"));
        assertNotNull(field);
        field.setText("a11y audit note");
        clickText("Save");
        boolean counted = false;
        for (int attempt = 0; attempt < 60 && !counted; attempt++) {
            UiObject2 notesControl = device.findObject(By.res(APP + ":id/notes_button"));
            String label = notesControl == null ? null : notesControl.getText();
            counted = label != null && label.contains("(1)");
            if (!counted) {
                SystemClock.sleep(250);
            }
        }
        JSONObject saved = waitAndCapture("19-annotate-saved", APP);
        JSONObject notes = view(saved, "notes_button");
        expect(counted && notes != null && notes.optString("text").contains("(1)"),
                "annotation_count_not_updated",
                "Keep the annotation count in the notes control text so it is announced");
    }

    private void notesPanel() throws Exception {
        click("notes_button");
        JSONObject capture = waitAndCapture("20-notes-panel", APP);
        requireView(capture, "notes_panel");
        requireView(capture, "notes_close");
        JSONObject list = view(capture, "note_list");
        expect(list != null, "notes_list_missing", "The annotation list must be present");
        expect(findByText(capture.getJSONObject("tree"), "a11y audit note") != null,
                "annotation_row_missing", "The saved annotation must be listed");
        requireNamed(capture);
        device.pressBack();
        JSONObject back = waitAndCapture("21-notes-back", APP);
        expect(view(back, "notes_panel") == null, "back_did_not_close_notes",
                "Back must close the annotation panel");
        expect(view(back, "reader_view") != null, "back_left_reader",
                "Back from annotations must return to the page, not to the shelf");
    }

    private void rotation() throws Exception {
        JSONObject portrait = capture("22-reader-portrait");
        String before = pageLabel(portrait);
        try {
            device.setOrientationLeft();
            SystemClock.sleep(2000);
            JSONObject landscape = waitAndCapture("23-reader-landscape", APP);
            expect(landscape.getInt("display_width") > landscape.getInt("display_height"),
                    "rotation_not_applied", "The device must actually be in landscape for this case");
            requireLayoutIntegrity(landscape);
            requireTargetSize(landscape);
            expect(pageLabel(landscape).equals(before), "rotation_lost_page",
                    "The reading position must survive the orientation change");
        } finally {
            device.setOrientationNatural();
            SystemClock.sleep(1500);
        }
    }

    private void largeFont() throws Exception {
        try {
            shell("settings put system font_scale 2.0");
            SystemClock.sleep(2000);
            relaunch("");
            ensureShelf();
            JSONObject shelf = waitAndCapture("24-shelf-font200", APP);
            expect(fontScale() >= 1.9f, "font_scale_not_applied", "The platform must report font_scale 2.0");
            requireNamed(shelf);
            requireLayoutIntegrity(shelf);
            requireTargetSize(shelf);
            openFirstBook();
            JSONObject reader = waitAndCapture("25-reader-font200", APP);
            requireNamed(reader);
            requireLayoutIntegrity(reader);
            requireTargetSize(reader);
        } finally {
            // A finding must not leak the platform configuration into the next case.
            shell("settings put system font_scale 1.0");
            SystemClock.sleep(1500);
            relaunch("");
        }
    }

    private void displayScaling() throws Exception {
        try {
            shell("wm density 480");
            SystemClock.sleep(2000);
            relaunch("");
            ensureShelf();
            JSONObject shelf = waitAndCapture("26-shelf-density480", APP);
            expect(density() >= 470, "density_override_not_applied", "The platform must report the 480 dpi override");
            requireNamed(shelf);
            requireLayoutIntegrity(shelf);
            requireTargetSize(shelf);
        } finally {
            shell("wm density reset");
            SystemClock.sleep(1500);
            relaunch("");
        }
    }

    // -------------------------------------------------------------- reporting

    private void session(String id, Body body) throws Exception {
        JSONObject item = new JSONObject();
        int before = captures.length();
        long started = SystemClock.elapsedRealtimeNanos();
        try {
            if (!"import_picker".equals(id)) {
                ensureHost();
            }
            body.run();
            item.put("verdict", "pass");
        } catch (Finding finding) {
            item.put("verdict", "fail");
            item.put("finding", finding.getMessage());
            item.put("patch", finding.patch);
        } catch (Throwable error) {
            item.put("verdict", "fail");
            item.put("error", error.toString());
            for (StackTraceElement frame : error.getStackTrace()) {
                if (frame.getClassName().equals(getClass().getName())) {
                    item.put("test_source_line", frame.getLineNumber());
                    break;
                }
            }
        }
        JSONArray produced = new JSONArray();
        for (int at = before; at < captures.length(); at++) {
            produced.put(captures.getString(at));
        }
        item.put("id", id);
        item.put("captures", produced);
        item.put("started_elapsed_ns", started);
        item.put("finished_elapsed_ns", SystemClock.elapsedRealtimeNanos());
        write(new File(caseDir, id + ".json"), item.toString(2));
        cases.put(item);
        SystemClock.sleep(200);
    }

    private void publish() throws Exception {
        int failed = 0;
        for (int at = 0; at < cases.length(); at++) {
            if (!"pass".equals(cases.getJSONObject(at).getString("verdict"))) {
                failed++;
            }
        }
        boolean complete = cases.length() == EXPECTED.length;
        if (complete) {
            for (int at = 0; at < EXPECTED.length; at++) {
                if (!EXPECTED[at].equals(cases.getJSONObject(at).getString("id"))) {
                    complete = false;
                }
            }
        }
        JSONObject result = identity()
                .put("schema", 1)
                .put("kind", "reader-a11y-android-audit")
                .put("application_id", APP)
                .put("harness_package", InstrumentationRegistry.getInstrumentation().getContext().getPackageName())
                .put("target_package", context.getPackageName())
                .put("cases", cases)
                .put("expected_cases", new JSONArray(java.util.Arrays.asList(EXPECTED)))
                .put("case_count", cases.length())
                .put("passed", cases.length() - failed)
                .put("failed", failed)
                .put("skipped", 0)
                .put("captures", captures)
                .put("audit_completed", complete)
                .put("accessibility_accepted", complete && failed == 0)
                .put("default_font_scale", "1.0")
                .put("audited_font_scales", new JSONArray(java.util.Arrays.asList("1.0", "2.0")))
                .put("audited_density_dpi", new JSONArray(java.util.Arrays.asList(density(), 480)))
                .put("coverage", coverage())
                .put("unverified", unverified());
        write(new File(output, "validation.json"), result.toString(2));
        assertTrue("every expected audit case must run", complete);
    }

    private JSONObject coverage() throws Exception {
        return new JSONObject()
                .put("shelf", new JSONObject().put("implemented", true)
                        .put("cases", new JSONArray(java.util.Arrays.asList("shelf_semantics", "shelf_row_and_search"))))
                .put("import", new JSONObject().put("implemented", true)
                        .put("cases", new JSONArray(Collections.singletonList("import_picker"))))
                .put("organize", new JSONObject().put("implemented", true)
                        .put("cases", new JSONArray(Collections.singletonList("organize_panel"))))
                .put("read", new JSONObject().put("implemented", true)
                        .put("cases", new JSONArray(java.util.Arrays.asList("reader_line_nodes",
                                "reader_page_turn", "reader_toolbar_state", "rotation", "large_font", "display_scaling"))))
                .put("annotate", new JSONObject().put("implemented", true)
                        .put("cases", new JSONArray(java.util.Arrays.asList("annotate_flow", "notes_panel"))))
                .put("navigation", new JSONObject().put("implemented", true)
                        .put("cases", new JSONArray(Collections.singletonList("back_navigation"))))
                .put("account", new JSONObject().put("implemented", false)
                        .put("reason", "the application has no account, purchase or sync screen; nothing to audit"));
    }

    private JSONArray unverified() throws Exception {
        return new JSONArray()
                .put(item("talkback_speech", "a semantic tree is not TalkBack speech; unverified without a physical device"))
                .put(item("physical_device", "no physical Android device ran this audit"))
                .put(item("other_api_levels", "only API 34 was executed; other levels and vendor skins stay unverified"))
                .put(item("rtl_and_locale", "only the default locale and LTR layout ran"))
                .put(item("contrast", "colour contrast is not measured from the semantic tree; screenshots are retained for review"))
                .put(item("account_surfaces", "no account page exists in this application, so nothing was granted"));
    }

    private static JSONObject item(String name, String note) throws Exception {
        return new JSONObject().put("item", name).put("status", "unverified").put("note", note);
    }

    private JSONObject identity() throws Exception {
        return new JSONObject()
                .put("source_sha", arg("exr_source_sha"))
                .put("run_id", arg("exr_run_id"))
                .put("attempt", arg("exr_attempt"))
                .put("sdk", Build.VERSION.SDK_INT)
                .put("abi", Build.SUPPORTED_ABIS[0])
                .put("model", Build.MODEL);
    }

    // --------------------------------------------------------------- captures

    private JSONObject capture(String name) throws Exception {
        densityDpi = density();
        File xml = new File(trees, name + ".xml");
        File png = new File(shots, name + ".png");
        device.dumpWindowHierarchy(xml);
        assertTrue("window hierarchy dump failed: " + name, xml.length() > 0);
        assertTrue("screenshot failed: " + name, device.takeScreenshot(png));
        AccessibilityNodeInfo root = root();
        assertNotNull("no active accessibility window: " + name, root);
        JSONArray interactive = new JSONArray();
        JSONObject tree = serialize(root, interactive, 0);
        JSONObject value = new JSONObject()
                .put("capture", name)
                .put("root_package", safe(root.getPackageName()))
                .put("root_class", safe(root.getClassName()))
                .put("density_dpi", densityDpi)
                .put("font_scale", fontScaleText())
                .put("rotation", device.getDisplayRotation())
                .put("display_width", device.getDisplayWidth())
                .put("display_height", device.getDisplayHeight())
                .put("xml", "trees/" + name + ".xml")
                .put("xml_bytes", xml.length())
                .put("screenshot", "shots/" + name + ".png")
                .put("screenshot_bytes", png.length())
                .put("tree", tree)
                .put("interactive", interactive);
        write(new File(trees, name + ".json"), value.toString(2));
        captures.put(name);
        return value;
    }

    private JSONObject serialize(AccessibilityNodeInfo info, JSONArray interactive, int depth) throws Exception {
        JSONObject value = new JSONObject();
        value.put("class", safe(info.getClassName()));
        value.put("view_id", safe(info.getViewIdResourceName()));
        value.put("text", safe(info.getText()));
        value.put("desc", safe(info.getContentDescription()));
        value.put("package", safe(info.getPackageName()));
        Rect box = new Rect();
        info.getBoundsInScreen(box);
        value.put("bounds", new JSONObject().put("left", box.left).put("top", box.top)
                .put("right", box.right).put("bottom", box.bottom));
        value.put("width_dp", dp(box.width()));
        value.put("height_dp", dp(box.height()));
        value.put("visible", info.isVisibleToUser());
        value.put("enabled", info.isEnabled());
        value.put("clickable", info.isClickable());
        value.put("long_clickable", info.isLongClickable());
        value.put("focusable", info.isFocusable());
        value.put("focused", info.isFocused());
        value.put("scrollable", info.isScrollable());
        value.put("editable", info.isEditable());
        value.put("checkable", info.isCheckable());
        value.put("checked", info.isChecked());
        value.put("selected", info.isSelected());
        value.put("important", info.isImportantForAccessibility());
        if (Build.VERSION.SDK_INT >= 28) {
            value.put("screen_reader_focusable", info.isScreenReaderFocusable());
        }
        if (Build.VERSION.SDK_INT >= 26) {
            value.put("hint", safe(info.getHintText()));
        }
        if (Build.VERSION.SDK_INT >= 30) {
            value.put("state", safe(info.getStateDescription()));
            value.put("live_region", info.getLiveRegion());
        }
        JSONArray actions = new JSONArray();
        for (AccessibilityNodeInfo.AccessibilityAction action : info.getActionList()) {
            actions.put(new JSONObject().put("id", action.getId()).put("label", safe(action.getLabel())));
        }
        value.put("actions", actions);
        value.put("name", accessibleName(info));
        AccessibilityNodeInfo.CollectionInfo collection = info.getCollectionInfo();
        if (collection != null) {
            value.put("collection", new JSONObject().put("rows", collection.getRowCount())
                    .put("columns", collection.getColumnCount()));
        }
        if (info.getExtras() != null && !info.getExtras().isEmpty()) {
            JSONObject extras = new JSONObject();
            for (String key : info.getExtras().keySet()) {
                extras.put(key, String.valueOf(info.getExtras().get(key)));
            }
            value.put("extras", extras);
        }
        int childCount = info.getChildCount();
        value.put("child_count", childCount);
        JSONArray children = new JSONArray();
        if (depth < 40) {
            for (int index = 0; index < childCount; index++) {
                AccessibilityNodeInfo child = info.getChild(index);
                if (child != null) {
                    children.put(serialize(child, interactive, depth + 1));
                }
            }
        }
        value.put("children", children);
        if (info.isClickable() || info.isLongClickable() || info.isEditable()) {
            interactive.put(new JSONObject()
                    .put("view_id", safe(info.getViewIdResourceName()))
                    .put("class", safe(info.getClassName()))
                    .put("text", safe(info.getText()))
                    .put("desc", safe(info.getContentDescription()))
                    .put("name", accessibleName(info))
                    .put("width_dp", dp(box.width()))
                    .put("height_dp", dp(box.height()))
                    .put("left", box.left)
                    .put("top", box.top)
                    .put("right", box.right)
                    .put("bottom", box.bottom)
                    .put("enabled", info.isEnabled())
                    .put("visible", info.isVisibleToUser())
                    .put("focusable", info.isFocusable())
                    .put("actions", actions));
        }
        return value;
    }

    // ------------------------------------------------------------- assertions

    private void requireView(JSONObject capture, String id) throws Exception {
        expect(view(capture, id) != null, "missing_view:" + id,
                "Capture " + capture.getString("capture") + " does not expose " + id);
    }

    private void requireNamed(JSONObject capture) throws Exception {
        JSONArray list = capture.getJSONArray("interactive");
        StringBuilder missing = new StringBuilder();
        for (int at = 0; at < list.length(); at++) {
            JSONObject node = list.getJSONObject(at);
            if (node.optString("name").isEmpty()) {
                missing.append(label(node)).append(' ');
            }
        }
        expect(missing.length() == 0, "unnamed_interactive_control",
                "Every interactive view needs a name (contentDescription or text): " + missing);
    }

    private void requireTargetSize(JSONObject capture) throws Exception {
        JSONArray list = capture.getJSONArray("interactive");
        StringBuilder small = new StringBuilder();
        for (int at = 0; at < list.length(); at++) {
            JSONObject node = list.getJSONObject(at);
            int width = node.optInt("width_dp");
            int height = node.optInt("height_dp");
            if (width < MIN_TARGET_DP || height < MIN_TARGET_DP) {
                small.append(label(node)).append('(').append(width).append('x').append(height).append("dp) ");
            }
        }
        expect(small.length() == 0, "touch_target_below_" + MIN_TARGET_DP + "dp",
                "Enlarge the touch target (or add touch delegate padding): " + small);
    }

    private void requireLayoutIntegrity(JSONObject capture) throws Exception {
        int width = capture.getInt("display_width");
        int height = capture.getInt("display_height");
        JSONArray list = capture.getJSONArray("interactive");
        StringBuilder collapsed = new StringBuilder();
        StringBuilder offscreen = new StringBuilder();
        StringBuilder overlapping = new StringBuilder();
        for (int at = 0; at < list.length(); at++) {
            JSONObject node = list.getJSONObject(at);
            if (node.optInt("width_dp") <= 0 || node.optInt("height_dp") <= 0) {
                collapsed.append(label(node)).append(' ');
            }
            if (node.optInt("right") > width + 2 || node.optInt("bottom") > height + 2
                    || node.optInt("left") < -2 || node.optInt("top") < -2) {
                offscreen.append(label(node)).append(' ');
            }
            for (int other = at + 1; other < list.length(); other++) {
                JSONObject pair = list.getJSONObject(other);
                int overlapWidth = Math.min(node.optInt("right"), pair.optInt("right"))
                        - Math.max(node.optInt("left"), pair.optInt("left"));
                int overlapHeight = Math.min(node.optInt("bottom"), pair.optInt("bottom"))
                        - Math.max(node.optInt("top"), pair.optInt("top"));
                if (overlapWidth <= 4 || overlapHeight <= 4) {
                    continue;
                }
                long area = (long) node.optInt("width_dp") * node.optInt("height_dp");
                long pairArea = (long) pair.optInt("width_dp") * pair.optInt("height_dp");
                long overlapDp = (long) Math.round(overlapWidth * 160f / Math.max(1, densityDpi))
                        * Math.round(overlapHeight * 160f / Math.max(1, densityDpi));
                // A clickable container that fully contains another control is nesting, not a squeeze.
                if (overlapDp >= Math.min(area, pairArea) - 8) {
                    continue;
                }
                overlapping.append(label(node)).append('~').append(label(pair)).append(' ');
            }
        }
        expect(collapsed.length() == 0 && offscreen.length() == 0 && overlapping.length() == 0,
                "layout_integrity_" + capture.getString("capture"),
                "collapsed=[" + collapsed + "] offscreen=[" + offscreen + "] overlapping=[" + overlapping
                        + "]; wrap the toolbar rows (HorizontalScrollView/Flow) or reduce controls at large font scale");
    }

    private void expect(boolean condition, String finding, String patch) throws Finding {
        if (!condition) {
            throw new Finding(finding, patch);
        }
    }

    // ---------------------------------------------------------------- helpers

    private static String label(JSONObject node) {
        String id = node.optString("view_id");
        if (!id.isEmpty()) {
            return id.substring(id.indexOf('/') + 1);
        }
        String name = node.optString("name");
        if (name.isEmpty()) {
            name = node.optString("class");
        }
        return name.length() > 24 ? name.substring(0, 24) : name;
    }

    private static JSONObject view(JSONObject capture, String id) throws Exception {
        return findById(capture.getJSONObject("tree"), APP + ":id/" + id);
    }

    private static JSONObject firstRow(JSONObject capture) throws Exception {
        JSONObject list = findById(capture.getJSONObject("tree"), APP + ":id/book_list");
        return list == null ? null : firstTextNode(list);
    }

    private static JSONObject firstTextNode(JSONObject node) {
        if (!node.optString("text").trim().isEmpty()) {
            return node;
        }
        JSONArray children = node.optJSONArray("children");
        if (children == null) {
            return null;
        }
        for (int at = 0; at < children.length(); at++) {
            JSONObject found = firstTextNode(children.optJSONObject(at));
            if (found != null) {
                return found;
            }
        }
        return null;
    }

    private static JSONObject findById(JSONObject node, String viewId) throws Exception {
        if (node == null) {
            return null;
        }
        if (viewId.equals(node.optString("view_id"))) {
            return node;
        }
        JSONArray children = node.optJSONArray("children");
        if (children == null) {
            return null;
        }
        for (int at = 0; at < children.length(); at++) {
            JSONObject found = findById(children.getJSONObject(at), viewId);
            if (found != null) {
                return found;
            }
        }
        return null;
    }

    private static JSONObject findByText(JSONObject node, String needle) throws Exception {
        if (node == null) {
            return null;
        }
        if (node.optString("text").contains(needle) || node.optString("desc").contains(needle)) {
            return node;
        }
        JSONArray children = node.optJSONArray("children");
        if (children == null) {
            return null;
        }
        for (int at = 0; at < children.length(); at++) {
            JSONObject found = findByText(children.getJSONObject(at), needle);
            if (found != null) {
                return found;
            }
        }
        return null;
    }

    private static JSONObject findByDesc(JSONObject node, String needle) throws Exception {
        if (node == null) {
            return null;
        }
        if (node.optString("desc").contains(needle)) {
            return node;
        }
        JSONArray children = node.optJSONArray("children");
        if (children == null) {
            return null;
        }
        for (int at = 0; at < children.length(); at++) {
            JSONObject found = findByDesc(children.getJSONObject(at), needle);
            if (found != null) {
                return found;
            }
        }
        return null;
    }

    private static JSONObject findClass(JSONObject node, String className) throws Exception {
        if (node == null) {
            return null;
        }
        if (className.equals(node.optString("class"))) {
            return node;
        }
        JSONArray children = node.optJSONArray("children");
        if (children == null) {
            return null;
        }
        for (int at = 0; at < children.length(); at++) {
            JSONObject found = findClass(children.getJSONObject(at), className);
            if (found != null) {
                return found;
            }
        }
        return null;
    }

    private JSONObject waitAndCapture(String name, String pkg) throws Exception {
        device.wait(Until.hasObject(By.pkg(pkg)), 45000);
        SystemClock.sleep(800);
        JSONObject value = capture(name);
        expect(pkg.equals(value.getString("root_package")), "root_package_mismatch",
                "expected " + pkg + " but the active window belongs to " + value.getString("root_package"));
        return value;
    }

    private void launch(String extra) throws Exception {
        device.executeShellCommand("am start -W -n " + APP + "/.MainActivity " + extra);
        if (!device.wait(Until.hasObject(By.pkg(APP)), 20000)) {
            device.pressHome();
            SystemClock.sleep(600);
            device.executeShellCommand("am start -W -n " + APP + "/.MainActivity " + extra);
            assertTrue("the audited host did not come to the foreground",
                    device.wait(Until.hasObject(By.pkg(APP)), 30000));
        }
        SystemClock.sleep(900);
    }

    /** Dismiss a foreign window (the system picker) without touching the host itself. */
    private void ensureHost() throws Exception {
        for (int attempt = 0; attempt < 4; attempt++) {
            AccessibilityNodeInfo root = root();
            if (root != null && APP.equals(safe(root.getPackageName()))) {
                return;
            }
            device.pressBack();
            SystemClock.sleep(700);
        }
        launch("");
    }

    private void relaunch(String extra) throws Exception {
        device.executeShellCommand("am force-stop " + APP);
        SystemClock.sleep(600);
        launch(extra);
    }

    private void ensureShelf() throws Exception {
        long end = SystemClock.uptimeMillis() + 30000;
        while (SystemClock.uptimeMillis() < end) {
            AccessibilityNodeInfo root = root();
            List<AccessibilityNodeInfo> shelves = root == null
                    ? Collections.<AccessibilityNodeInfo>emptyList()
                    : root.findAccessibilityNodeInfosByViewId(APP + ":id/shelf_panel");
            if (!shelves.isEmpty()) {
                SystemClock.sleep(500);
                return;
            }
            device.pressBack();
            SystemClock.sleep(900);
        }
    }

    private void openFirstBook() throws Exception {
        UiObject2 row = device.wait(Until.findObject(By.textStartsWith("EXReader Android Sample")), 20000);
        assertNotNull("the imported shelf row must be clickable", row);
        row.click();
        assertTrue("the reader must open",
                device.wait(Until.hasObject(By.res(APP + ":id/reader_view")), 45000));
        device.wait(Until.hasObject(By.res(APP + ":id/page_label")), 30000);
        SystemClock.sleep(1200);
    }

    private void click(String id) throws Exception {
        long end = SystemClock.uptimeMillis() + 20000;
        while (SystemClock.uptimeMillis() < end) {
            try {
                UiObject2 value = device.findObject(By.res(APP + ":id/" + id));
                if (value != null && value.isEnabled()) {
                    value.click();
                    SystemClock.sleep(350);
                    return;
                }
            } catch (StaleObjectException stale) {
                SystemClock.sleep(120);
            }
            SystemClock.sleep(120);
        }
        throw new AssertionError("control missing or not ready: " + id);
    }

    private void clickText(String text) throws Exception {
        long end = SystemClock.uptimeMillis() + 20000;
        while (SystemClock.uptimeMillis() < end) {
            try {
                UiObject2 value = device.findObject(By.text(text));
                if (value != null && value.isEnabled()) {
                    value.click();
                    SystemClock.sleep(350);
                    return;
                }
            } catch (StaleObjectException stale) {
                SystemClock.sleep(120);
            }
            SystemClock.sleep(120);
        }
        throw new AssertionError("text control missing: " + text);
    }

    private void pick(String name) throws Exception {
        long end = SystemClock.uptimeMillis() + 90000;
        while (SystemClock.uptimeMillis() < end) {
            try {
                UiObject2 file = device.findObject(By.text(name));
                if (file != null && file.isEnabled()) {
                    file.click();
                    assertTrue("the picker must return to the host",
                            device.wait(Until.hasObject(By.pkg(APP)), 30000));
                    return;
                }
                // DCIM only appears in the picker's storage root. Inside "Download" the
                // rows are a scrollable list, and the drawer's Download entry would
                // navigate back out of the folder.
                if (device.hasObject(By.text("DCIM"))) {
                    UiObject2 folder = device.findObject(By.text("Download"));
                    if (folder != null && folder.isEnabled()) {
                        folder.click();
                        SystemClock.sleep(600);
                        continue;
                    }
                }
                int centreX = device.getDisplayWidth() / 2;
                device.swipe(centreX, (int) (device.getDisplayHeight() * 0.72),
                        centreX, (int) (device.getDisplayHeight() * 0.38), 24);
                SystemClock.sleep(450);
            } catch (StaleObjectException stale) {
                SystemClock.sleep(200);
            }
        }
        throw new AssertionError("the system picker did not list " + name);
    }

    private void hideKeyboard() throws Exception {
        if (shell("dumpsys input_method").contains("mInputShown=true")) {
            device.pressBack();
            SystemClock.sleep(300);
        }
    }

    private String pageLabel(JSONObject capture) throws Exception {
        JSONObject node = view(capture, "page_label");
        if (node == null) {
            return "";
        }
        String text = node.optString("text");
        int cut = text.indexOf(' ');
        return cut > 0 ? text.substring(0, cut) : text;
    }

    private AccessibilityNodeInfo root() {
        return InstrumentationRegistry.getInstrumentation().getUiAutomation().getRootInActiveWindow();
    }

    private String shell(String command) throws Exception {
        return device.executeShellCommand(command);
    }

    private int density() {
        String raw;
        try {
            raw = shell("wm density");
        } catch (Exception error) {
            raw = "";
        }
        int physical = match(raw, "Physical density:\\s*(\\d+)");
        int override = match(raw, "Override density:\\s*(\\d+)");
        return override > 0 ? override : physical > 0 ? physical : 160;
    }

    private String fontScaleText() {
        try {
            return shell("settings get system font_scale").trim();
        } catch (Exception error) {
            return "";
        }
    }

    private float fontScale() {
        try {
            return Float.parseFloat(fontScaleText());
        } catch (Exception error) {
            return 0f;
        }
    }

    private static int match(String raw, String pattern) {
        Matcher matcher = Pattern.compile(pattern).matcher(raw == null ? "" : raw);
        return matcher.find() ? Integer.parseInt(matcher.group(1)) : 0;
    }

    private int dp(int pixels) {
        return Math.round(pixels * 160f / Math.max(1, densityDpi));
    }

    private static String accessibleName(AccessibilityNodeInfo info) {
        String desc = safe(info.getContentDescription());
        if (!desc.isEmpty()) {
            return desc;
        }
        String text = safe(info.getText());
        if (!text.isEmpty()) {
            return text;
        }
        if (Build.VERSION.SDK_INT >= 26) {
            return safe(info.getHintText());
        }
        return "";
    }

    private static String safe(CharSequence value) {
        return value == null ? "" : value.toString();
    }

    private static void write(File file, String text) throws Exception {
        try (FileOutputStream out = new FileOutputStream(file)) {
            out.write((text + "\n").getBytes(StandardCharsets.UTF_8));
        }
    }
}
