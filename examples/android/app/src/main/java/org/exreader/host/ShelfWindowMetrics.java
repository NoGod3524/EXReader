// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.app.Activity;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.Process;
import android.os.SystemClock;
import android.util.Log;
import android.view.FrameMetrics;
import android.view.Window;
import org.json.JSONObject;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicLong;

/** Explicit debug capture only; records completed metrics from each actual Window instance. */
final class ShelfWindowMetrics implements AutoCloseable {
    private static final AtomicLong WINDOWS=new AtomicLong();
    private static final int MAX_FRAMES=20000;
    private static final long MAX_BYTES=32L*1024*1024;
    private final Window window;
    private final HandlerThread thread=new HandlerThread("exr-shelf-frame-metrics");
    private final Handler handler;
    private final Window.OnFrameMetricsAvailableListener listener;
    private FileOutputStream output;
    private long frames,dropped,bytes;
    private boolean failed;

    static ShelfWindowMetrics start(Activity activity,long createdNs) {
        if (!BuildConfig.DEBUG || !activity.getIntent().getBooleanExtra("shelf_metrics",false))return null;
        return new ShelfWindowMetrics(activity,createdNs);
    }

    private ShelfWindowMetrics(Activity activity,long createdNs) {
        window=activity.getWindow();
        long id=WINDOWS.incrementAndGet();
        File root=new File(activity.getExternalFilesDir(null),"shelf-window-metrics");
        if (!root.isDirectory() && !root.mkdirs())throw new IllegalStateException("Shelf metrics folder unavailable");
        File file=new File(root,"window-"+Process.myPid()+"-"+id+".jsonl");
        thread.start(); handler=new Handler(thread.getLooper());
        handler.post(()->{
            try {
                output=new FileOutputStream(file);
                write(new JSONObject().put("kind","start").put("schema",1).put("pid",Process.myPid()).put("window_id",id)
                        .put("activity_started_elapsed_ns",createdNs).put("registered_elapsed_ns",SystemClock.elapsedRealtimeNanos())
                        .put("max_frames",MAX_FRAMES).put("max_bytes",MAX_BYTES));
            } catch(Exception error){fail(error);}
        });
        listener=(observed,reusable,drop)->{
            FrameMetrics copy=new FrameMetrics(reusable);
            if(failed)return;
            try {
                if(observed!=window || frames>=MAX_FRAMES || bytes>=MAX_BYTES)throw new IllegalStateException("Shelf window metrics identity/bound");
                dropped+=drop;
                write(new JSONObject().put("kind","frame").put("pid",Process.myPid()).put("window_id",id).put("sequence",++frames)
                        .put("callback_elapsed_ns",SystemClock.elapsedRealtimeNanos()).put("drop_count",drop)
                        .put("total_ns",copy.getMetric(FrameMetrics.TOTAL_DURATION)).put("first_draw",copy.getMetric(FrameMetrics.FIRST_DRAW_FRAME))
                        .put("intended_vsync_ns",copy.getMetric(FrameMetrics.INTENDED_VSYNC_TIMESTAMP))
                        .put("vsync_ns",copy.getMetric(FrameMetrics.VSYNC_TIMESTAMP))
                        .put("input_ns",copy.getMetric(FrameMetrics.INPUT_HANDLING_DURATION))
                        .put("layout_measure_ns",copy.getMetric(FrameMetrics.LAYOUT_MEASURE_DURATION))
                        .put("draw_ns",copy.getMetric(FrameMetrics.DRAW_DURATION))
                        .put("sync_ns",copy.getMetric(FrameMetrics.SYNC_DURATION))
                        .put("gpu_ns",copy.getMetric(FrameMetrics.GPU_DURATION)).put("deadline_ns",copy.getMetric(FrameMetrics.DEADLINE)));
            } catch(Exception error){fail(error);}
        };
        window.addOnFrameMetricsAvailableListener(listener,handler);
    }

    private void write(JSONObject value)throws Exception {
        byte[] raw=(value.toString()+"\n").getBytes(StandardCharsets.UTF_8); output.write(raw); bytes+=raw.length;
    }
    private void fail(Exception error) {
        if(failed)return; failed=true; Log.e("EXRShelfMetrics","Capture failed: "+error);
        if(output!=null)try{write(new JSONObject().put("kind","error").put("detail",error.toString()));}
        catch(Exception ignored){Log.e("EXRShelfMetrics","Could not retain capture failure");}
    }
    @Override public void close() {
        window.removeOnFrameMetricsAvailableListener(listener);
        handler.post(()->{
            try {
                if(output!=null){if(!failed)write(new JSONObject().put("kind","stop").put("frames",frames).put("dropped",dropped));output.close();}
            } catch(Exception error){fail(error);} finally{thread.quitSafely();}
        });
    }
}
