// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.app.Activity;
import android.content.Context;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.Process;
import android.os.SystemClock;
import android.provider.Settings;
import android.util.Log;
import android.view.FrameMetrics;
import android.view.View;
import android.view.Window;

import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicLong;

/** Diagnostic branch only: copies delivered, completed window metrics on a dedicated thread. */
final class FrameMetricsTrace {
    private static final String MODE = "exreader_frame_metrics_mode";
    private static final String PHASE = "exreader_frame_metrics_phase";
    private static final int MAX_FRAMES = 10000;
    private static final long MAX_BYTES = 16L * 1024 * 1024;
    private static final AtomicLong WINDOWS = new AtomicLong();
    private static Config config;
    private final Window window;
    private final HandlerThread thread = new HandlerThread("exr-frame-metrics");
    private final Handler handler;
    private final Window.OnFrameMetricsAvailableListener listener;
    private final JSONObject header;
    private FileOutputStream output;
    private long frames, dropped, bytes;
    private boolean failed;

    private static final class Config {
        final String mode, phase;
        Config(String mode, String phase) { this.mode = mode; this.phase = phase; }
    }

    private static synchronized Config config(Context context) {
        if (config != null) return config;
        // This explicitly configured shell setting survives the original script's pm clear and restarts.
        String mode = Settings.Global.getString(context.getContentResolver(), MODE);
        String phase = Settings.Global.getString(context.getContentResolver(), PHASE);
        if (mode == null && phase == null) return config = new Config("disabled", "disabled");
        if (!("none".equals(mode) || "software".equals(mode)) || phase == null || !phase.matches("[AB][12]"))
            throw new IllegalStateException("Invalid explicit frame metrics configuration");
        return config = new Config(mode, phase);
    }

    static int layerType(Context context) {
        if (!BuildConfig.DEBUG) return View.LAYER_TYPE_SOFTWARE;
        return "none".equals(config(context).mode) ? View.LAYER_TYPE_NONE : View.LAYER_TYPE_SOFTWARE;
    }

    static FrameMetricsTrace start(Activity activity, ReaderView reader) {
        if (!BuildConfig.DEBUG) return null;
        Config selected = config(activity);
        if ("disabled".equals(selected.mode)) return null;
        return new FrameMetricsTrace(activity, reader, selected);
    }

    private FrameMetricsTrace(Activity activity, ReaderView reader, Config selected) {
        window = activity.getWindow();
        long id = WINDOWS.incrementAndGet();
        File root = new File(activity.getExternalFilesDir(null), "frame-metrics");
        if (!root.isDirectory() && !root.mkdirs()) throw new IllegalStateException("Frame trace folder unavailable");
        File file = new File(root, selected.phase + "-" + Process.myPid() + "-" + id + ".jsonl");
        try {
            header = new JSONObject().put("kind", "start").put("schema", 1)
                .put("phase", selected.phase).put("mode", selected.mode).put("layer_type", reader.getLayerType())
                .put("pid", Process.myPid()).put("window_id", id)
                .put("registered_elapsed_ns", SystemClock.elapsedRealtimeNanos())
                .put("max_frames", MAX_FRAMES).put("max_bytes", MAX_BYTES);
        } catch (Exception error) { throw new IllegalStateException(error); }
        thread.start();
        handler = new Handler(thread.getLooper());
        handler.post(() -> {
            try { output = new FileOutputStream(file); write(header); }
            catch (Exception error) { fail(error); }
        });
        listener = (observedWindow, reusable, dropCountSinceLastInvocation) -> {
            // FrameMetrics passed by the system is reused after this callback; retain its own copy now.
            FrameMetrics copy = new FrameMetrics(reusable);
            if (failed) return;
            try {
                if (frames >= MAX_FRAMES || bytes >= MAX_BYTES) throw new IllegalStateException("Frame trace budget exhausted");
                long ordinal = ++frames;
                dropped += dropCountSinceLastInvocation;
                JSONObject row = new JSONObject().put("kind", "frame").put("pid", Process.myPid())
                    .put("window_id", id).put("sequence", ordinal).put("phase", selected.phase).put("mode", selected.mode)
                    .put("callback_elapsed_ns", SystemClock.elapsedRealtimeNanos()).put("drop_count", dropCountSinceLastInvocation)
                    .put("total_ns", copy.getMetric(FrameMetrics.TOTAL_DURATION))
                    .put("intended_vsync_ns", copy.getMetric(FrameMetrics.INTENDED_VSYNC_TIMESTAMP))
                    .put("vsync_ns", copy.getMetric(FrameMetrics.VSYNC_TIMESTAMP))
                    .put("first_draw", copy.getMetric(FrameMetrics.FIRST_DRAW_FRAME))
                    .put("unknown_delay_ns", copy.getMetric(FrameMetrics.UNKNOWN_DELAY_DURATION))
                    .put("input_ns", copy.getMetric(FrameMetrics.INPUT_HANDLING_DURATION))
                    .put("animation_ns", copy.getMetric(FrameMetrics.ANIMATION_DURATION))
                    .put("layout_measure_ns", copy.getMetric(FrameMetrics.LAYOUT_MEASURE_DURATION))
                    .put("draw_ns", copy.getMetric(FrameMetrics.DRAW_DURATION))
                    .put("sync_ns", copy.getMetric(FrameMetrics.SYNC_DURATION))
                    .put("command_issue_ns", copy.getMetric(FrameMetrics.COMMAND_ISSUE_DURATION))
                    .put("swap_buffers_ns", copy.getMetric(FrameMetrics.SWAP_BUFFERS_DURATION))
                    .put("gpu_ns", copy.getMetric(FrameMetrics.GPU_DURATION))
                    .put("deadline_ns", copy.getMetric(FrameMetrics.DEADLINE));
                write(row);
            } catch (Exception error) { fail(error); }
        };
        window.addOnFrameMetricsAvailableListener(listener, handler);
    }

    private void write(JSONObject row) throws Exception {
        byte[] data = (row.toString() + "\n").getBytes(StandardCharsets.UTF_8);
        output.write(data);
        bytes += data.length;
    }

    private void fail(Exception error) {
        if (failed) return;
        failed = true;
        Log.e("EXRFrameMetrics", "Trace failed: " + error);
        if (output != null) {
            try { write(new JSONObject().put("kind", "error").put("detail", error.toString())); }
            catch (Exception ignored) { Log.e("EXRFrameMetrics", "Could not retain trace failure"); }
        }
    }

    void close() {
        window.removeOnFrameMetricsAvailableListener(listener);
        handler.post(() -> {
            try {
                if (output != null) {
                    if (!failed) write(new JSONObject().put("kind", "stop").put("frames", frames).put("dropped", dropped));
                    output.close();
                }
            } catch (Exception error) { fail(error); }
            finally { thread.quitSafely(); }
        });
    }
}
