// SPDX-License-Identifier: MIT
package org.exreader.display.probe;

import android.app.Activity;
import android.app.Dialog;
import android.app.Instrumentation;
import android.content.Intent;
import android.content.pm.ActivityInfo;
import android.os.Bundle;
import android.os.Looper;
import android.os.SystemClock;
import android.view.View;
import android.view.Window;
import android.view.WindowManager;
import org.exreader.display.ReaderDisplay;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.ArrayList;
import java.util.concurrent.atomic.AtomicReference;

/** Platform Instrumentation, not JVM/stub tests; compiled against installed AAR. */
public final class DisplayInstrumentation extends Instrumentation {
    private static final int KEEP = WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON;
    private ProbeActivity activity;
    private ReaderDisplay display;
    private long token;
    private JSONArray observations;
    private int assertions;
    private final ArrayList<Activity> opened = new ArrayList<>();
    private final JSONArray results = new JSONArray();
    private int failures;
    interface Checked { void run() throws Exception; }
    @Override public void onCreate(Bundle arguments) { super.onCreate(arguments); start(); }
    @Override public void onStart() {
        test("normal_numeric_switch", () -> ui(() -> {
            configure(0.25f, true); ok(display.activate(token)); props(activity, 0.25f, true);
            configure(1f, false); props(activity, 1f, false);
            configure(0f, true); props(activity, 0f, true);
        }));
        test("follows_system_exact", () -> ui(() -> {
            configure(0.4f, true); ok(display.activate(token));
            configure(-1f, false); props(activity, -1f, false);
        }));
        test("rejects_nonfinite_atomic", () -> ui(() -> {
            configure(0.3f, true); ok(display.activate(token));
            for (float value : new float[]{Float.NaN, Float.POSITIVE_INFINITY, Float.NEGATIVE_INFINITY}) {
                eq(display.configure(token, value, false), ReaderDisplay.Status.INVALID_BRIGHTNESS);
                props(activity, 0.3f, true);
            }
        }));
        test("rejects_out_of_range_atomic", () -> ui(() -> {
            configure(0.3f, true); ok(display.activate(token));
            for (float value : new float[]{-2f, -0.001f, 1.0001f}) {
                eq(display.configure(token, value, false), ReaderDisplay.Status.INVALID_BRIGHTNESS);
                props(activity, 0.3f, true);
            }
        }));
        test("wrong_thread_no_effect", () -> {
            ui(() -> { configure(0.3f, true); ok(display.activate(token)); });
            check(Looper.myLooper() != Looper.getMainLooper(), "actual worker");
            eq(display.configure(token, 0.8f, false), ReaderDisplay.Status.WRONG_THREAD);
            eq(display.close(), ReaderDisplay.Status.WRONG_THREAD);
            eq(new ReaderDisplay().attach(activity.getWindow()), ReaderDisplay.Status.WRONG_THREAD);
            ui(() -> props(activity, 0.3f, true));
        });
        test("reentrant_no_effect", () -> ui(() -> {
            configure(0.3f, true);
            AtomicReference<ReaderDisplay.Status> returned = new AtomicReference<>();
            ProbeActivity.attributeHook = () -> returned.set(display.configure(token, 0.9f, false));
            ok(display.activate(token)); eq(returned.get(), ReaderDisplay.Status.REENTRANT);
            props(activity, 0.3f, true);
        }));
        test("duplicate_attach_no_effect", () -> ui(() -> {
            configure(0.3f, true); ok(display.activate(token));
            eq(display.attach(activity.getWindow()), ReaderDisplay.Status.ALREADY_ATTACHED);
            check(display.generation() == token, "generation unchanged"); props(activity, 0.3f, true);
        }));
        test("null_window_rejected", () -> ui(() -> {
            ReaderDisplay other = new ReaderDisplay();
            eq(other.attach(null), ReaderDisplay.Status.INVALID_WINDOW);
            check(other.generation() == 0, "failed attach generation"); ok(other.close());
        }));
        test("preexisting_keep_preserved", () -> ui(() -> {
            ok(display.detach(token)); external(activity, 0.6f, true);
            ok(display.attach(activity.getWindow())); token = display.generation();
            configure(0.6f, true); ok(display.activate(token));
            ok(display.restore(token)); props(activity, 0.6f, true);
        }));
        test("external_brightness_preserved", () -> ui(() -> {
            configure(0.3f, true); ok(display.activate(token));
            external(activity, 0.8f, true); ok(display.restore(token)); props(activity, 0.8f, false);
            configure(0.2f, true); ok(display.activate(token));
            external(activity, 0.9f, true); configure(0.1f, true);
            ok(display.restore(token)); props(activity, 0.9f, false);
        }));
        test("external_keep_preserved", () -> ui(() -> {
            external(activity, 0.6f, true); configure(0.3f, false); ok(display.activate(token));
            external(activity, 0.3f, true); ok(display.restore(token)); props(activity, 0.6f, true);
        }));
        test("unrelated_flags_preserved", () -> ui(() -> {
            configure(0.3f, true); ok(display.activate(token));
            activity.getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
            ok(display.restore(token)); props(activity, -1f, false);
            check((activity.getWindow().getAttributes().flags & WindowManager.LayoutParams.FLAG_SECURE) != 0, "external secure flag retained");
        }));
        test("cancel_restore_retry", () -> ui(() -> {
            configure(0.3f, true); props(activity, -1f, false);
            ok(display.activate(token)); ok(display.deactivate(token)); props(activity, -1f, false);
            ok(display.activate(token)); props(activity, 0.3f, true);
            ok(display.restore(token)); props(activity, -1f, false);
        }));
        test("close_and_after_close", () -> ui(() -> {
            configure(0.3f, true); ok(display.activate(token)); ok(display.close());
            props(activity, -1f, false);
            eq(display.configure(token, 0.2f, true), ReaderDisplay.Status.CLOSED);
            eq(display.activate(token), ReaderDisplay.Status.CLOSED);
            eq(display.attach(activity.getWindow()), ReaderDisplay.Status.CLOSED);
            eq(display.close(), ReaderDisplay.Status.CLOSED);
            display = null;
        }));
        test("exclusive_same_window", () -> ui(() -> {
            ReaderDisplay other = new ReaderDisplay();
            eq(other.attach(activity.getWindow()), ReaderDisplay.Status.CONFLICT);
            configure(0.3f, true); ok(display.activate(token)); ok(other.close());
            props(activity, 0.3f, true); ok(display.detach(token));
            other = new ReaderDisplay(); ok(other.attach(activity.getWindow())); ok(other.close());
        }));
        test("independent_windows", () -> {
            ui(() -> { configure(0.3f, true); ok(display.activate(token)); });
            ProbeActivity second = launch(OtherActivity.class); focus(second);
            ReaderDisplay other = new ReaderDisplay();
            ui(() -> {
                check(second.getWindow() != activity.getWindow(), "distinct Window objects");
                ok(other.attach(second.getWindow())); long secondToken = other.generation();
                ok(other.configure(secondToken, 0.7f, true)); ok(other.activate(secondToken));
                props(activity, -1f, false); props(second, 0.7f, true);
                ok(display.close()); display = null; props(second, 0.7f, true); ok(other.close());
                props(second, -1f, false);
            });
        });
        test("focus_loss_restore_no_autoactivate", () -> {
            Dialog[] dialog = new Dialog[1];
            ui(() -> {
                configure(0.3f, true); ok(display.activate(token));
                dialog[0] = new Dialog(activity); dialog[0].setTitle("Focus boundary"); dialog[0].show();
            });
            waitFor(() -> !activity.hasWindowFocus(), "focus loss");
            ui(() -> { props(activity, -1f, false); dialog[0].dismiss(); });
            focus(activity);
            ui(() -> { props(activity, -1f, false); ok(display.activate(token)); props(activity, 0.3f, true); });
        });
        test("pause_background_restore", () -> {
            ui(() -> { configure(0.3f, true); ok(display.activate(token)); });
            ProbeActivity second = launch(OtherActivity.class); focus(second);
            ui(() -> { props(activity, -1f, false); eq(display.activate(token), ReaderDisplay.Status.NOT_VISIBLE); second.finish(); });
            focus(activity);
            ui(() -> { props(activity, -1f, false); ok(display.activate(token)); props(activity, 0.3f, true); });
        });
        test("rotation_old_token_rejected", () -> {
            ProbeActivity old = activity; Window oldWindow = old.getWindow(); long oldToken = token;
            int oldOrientation = old.getResources().getConfiguration().orientation;
            ui(() -> {
                configure(0.3f, true); ok(display.activate(token));
                old.setRequestedOrientation(oldOrientation == android.content.res.Configuration.ORIENTATION_LANDSCAPE
                        ? ActivityInfo.SCREEN_ORIENTATION_PORTRAIT : ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE);
            });
            waitFor(() -> old.isDestroyed() && ProbeActivity.latest != old, "rotation destroys old Activity");
            activity = ProbeActivity.latest; opened.add(activity); focus(activity);
            ui(() -> {
                check(activity.getWindow() != oldWindow, "rotation replaced Window");
                check(activity.getResources().getConfiguration().orientation != oldOrientation, "orientation changed");
                props(old, -1f, false); ok(display.attach(activity.getWindow())); token = display.generation();
                check(token != oldToken, "new generation"); configure(0.7f, true); ok(display.activate(token));
                eq(display.deactivate(oldToken), ReaderDisplay.Status.STALE_GENERATION);
                eq(display.configure(oldToken, 0.1f, false), ReaderDisplay.Status.STALE_GENERATION);
                props(activity, 0.7f, true);
            });
        });
        test("window_recreation_releases_old", () -> {
            ProbeActivity old = activity; long oldToken = token;
            ui(() -> { configure(0.3f, true); ok(display.activate(token)); old.recreate(); });
            waitFor(() -> old.isDestroyed() && ProbeActivity.latest != old, "recreation");
            activity = ProbeActivity.latest; opened.add(activity); focus(activity);
            ui(() -> {
                props(old, -1f, false); props(activity, -1f, false);
                ok(display.attach(activity.getWindow())); token = display.generation();
                eq(display.activate(oldToken), ReaderDisplay.Status.STALE_GENERATION);
                configure(0.4f, true); ok(display.activate(token)); props(activity, 0.4f, true);
            });
        });
        test("destroyed_window_rejected", () -> {
            ProbeActivity old = activity; Window oldWindow = old.getWindow();
            ui(() -> { configure(0.3f, true); ok(display.activate(token)); old.finish(); });
            waitFor(old::isDestroyed, "actual Activity destruction");
            ui(() -> {
                props(old, -1f, false); ReaderDisplay other = new ReaderDisplay();
                eq(other.attach(oldWindow), ReaderDisplay.Status.INVALID_WINDOW); ok(other.close());
                eq(display.configure(token, 0.8f, false), ReaderDisplay.Status.STALE_GENERATION);
            });
        });
        test("hidden_window_activate_rejected", () -> ui(() -> {
            configure(0.3f, true); activity.getWindow().getDecorView().setVisibility(View.INVISIBLE);
            eq(display.activate(token), ReaderDisplay.Status.NOT_VISIBLE); props(activity, -1f, false);
            activity.getWindow().getDecorView().setVisibility(View.VISIBLE);
        }));
        test("detach_old_callbacks_rejected", () -> ui(() -> {
            long old = token; configure(0.3f, true); ok(display.activate(token)); ok(display.detach(token));
            props(activity, -1f, false); ok(display.attach(activity.getWindow())); token = display.generation();
            configure(0.7f, true); ok(display.activate(token));
            eq(display.detach(old), ReaderDisplay.Status.STALE_GENERATION);
            eq(display.restore(old), ReaderDisplay.Status.STALE_GENERATION); props(activity, 0.7f, true);
        }));
        Bundle bundle = new Bundle();
        try {
            ProbeActivity finalActivity = launch(ProbeActivity.class); focus(finalActivity);
            JSONObject report = ProbeActivity.identity(finalActivity);
            report.put("schema", 1); report.put("module", "EXReaderAndroidDisplay");
            report.put("job", "android"); report.put("cases", results);
            report.put("accepted", failures == 0); report.put("physical_effect", "UNAVAILABLE");
            ProbeActivity.write(finalActivity, "suite.json", report);
            bundle.putString("stream", "\nDISPLAY_SUITE " + results.length() + " cases, " + failures + " failures\n");
        } catch (Throwable error) { failures++; bundle.putString("shortMsg", error.toString()); }
        finish(failures == 0 ? Activity.RESULT_OK : Activity.RESULT_CANCELED, bundle);
    }
    private void test(String name, Checked body) {
        observations = new JSONArray(); assertions = 0; Throwable failure = null;
        try {
            activity = launch(ProbeActivity.class); focus(activity); display = new ReaderDisplay();
            ui(() -> { ok(display.attach(activity.getWindow())); token = display.generation(); props(activity, -1f, false); });
            body.run();
        } catch (Throwable error) { failure = error; }
        finally {
            try { ui(() -> {
                ProbeActivity.attributeHook = null;
                if (display != null) display.close();
                display = null;
                for (Activity item : opened) if (!item.isDestroyed()) item.finish();
                opened.clear();
            }); waitForIdleSync(); }
            catch (Throwable error) { if (failure == null) failure = error; }
        }
        try {
            JSONObject row = new JSONObject(); row.put("name", name);
            row.put("passed", failure == null); row.put("assertions", assertions); row.put("observations", observations);
            if (failure != null) { failures++; row.put("error", android.util.Log.getStackTraceString(failure)); }
            results.put(row);
            Bundle progress = new Bundle(); progress.putString("stream", "DISPLAY_CASE " + name + " " + (failure == null ? "PASS" : "FAIL " + failure) + "\n");
            sendStatus(failure == null ? 0 : -2, progress);
        } catch (Exception e) { throw new RuntimeException(e); }
    }
    private ProbeActivity launch(Class<? extends ProbeActivity> cls) {
        Intent intent = new Intent(getTargetContext(), cls); intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        ProbeActivity result = (ProbeActivity) startActivitySync(intent); opened.add(result); return result;
    }
    interface Condition { boolean get(); }
    private void waitFor(Condition condition, String message) throws Exception {
        for (int i = 0; i < 100; i++) {
            boolean[] ready = {false}; ui(() -> ready[0] = condition.get());
            if (ready[0]) return; SystemClock.sleep(100);
        }
        throw new AssertionError("timeout: " + message);
    }
    private void focus(Activity target) throws Exception { waitFor(target::hasWindowFocus, "Activity focus"); waitForIdleSync(); }
    private void ui(Checked action) throws Exception {
        AtomicReference<Throwable> error = new AtomicReference<>();
        runOnMainSync(() -> { try {
            if (Looper.myLooper() != Looper.getMainLooper()) throw new AssertionError("not UI thread");
            action.run();
        } catch (Throwable e) { error.set(e); } });
        if (error.get() != null) throw new Exception("UI failure", error.get());
    }
    private void configure(float brightness, boolean keep) { ok(display.configure(token, brightness, keep)); }
    private void props(Activity target, float brightness, boolean keep) throws Exception {
        WindowManager.LayoutParams params = target.getWindow().getAttributes();
        JSONObject row = new JSONObject();
        row.put("brightness", params.screenBrightness); row.put("keep", (params.flags & KEEP) != 0);
        row.put("expected_brightness", brightness); row.put("expected_keep", keep);
        row.put("main_thread", Looper.myLooper() == Looper.getMainLooper()); observations.put(row);
        check(Float.floatToIntBits(params.screenBrightness) == Float.floatToIntBits(brightness), "brightness: " + params.screenBrightness + " != " + brightness);
        check(((params.flags & KEEP) != 0) == keep, "keep flag");
    }
    private void external(Activity target, float brightness, boolean keep) {
        WindowManager.LayoutParams params = new WindowManager.LayoutParams(); params.copyFrom(target.getWindow().getAttributes());
        params.screenBrightness = brightness; params.flags = keep ? params.flags | KEEP : params.flags & ~KEEP;
        target.getWindow().setAttributes(params);
    }
    private void ok(ReaderDisplay.Status value) { eq(value, ReaderDisplay.Status.OK); }
    private void eq(Object actual, Object expected) { check(expected.equals(actual), actual + " != " + expected); }
    private void check(boolean condition, String message) { assertions++; if (!condition) throw new AssertionError(message); }
}
