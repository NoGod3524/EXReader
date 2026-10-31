// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.app.Activity;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.Looper;
import android.view.Choreographer;
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
    private FileOutputStream output,readyOutput;
    private final long windowId;
    private final Handler mainHandler=new Handler(Looper.getMainLooper());
    private final Choreographer choreographer=Choreographer.getInstance();
    private final CatalogFrameLatch catalogLatch;
    private final Choreographer.FrameCallback catalogFrame;
    private final Runnable clearCatalogLatch;
    private long readyBytes,readyEvents;
    private long frames,dropped,bytes;
    private boolean failed;

    static ShelfWindowMetrics start(Activity activity,long createdNs) {
        if ((!BuildConfig.DEBUG && !BuildConfig.F08_REVIEW) || !activity.getIntent().getBooleanExtra("shelf_metrics",false))return null;
        return new ShelfWindowMetrics(activity,createdNs);
    }

    private ShelfWindowMetrics(Activity activity,long createdNs) {
        window=activity.getWindow();
        long id=WINDOWS.incrementAndGet();windowId=id;
        catalogLatch=new CatalogFrameLatch(window);
        clearCatalogLatch=()->{
            catalogLatch.clear();
            readyEvent("clear",catalogLatch.generation,catalogLatch.revision,"cleared",SystemClock.elapsedRealtimeNanos());
        };
        catalogFrame=frameTimeNanos->{
            String status=catalogLatch.frame(window,frameTimeNanos);
            if(!mainHandler.postAtFrontOfQueue(clearCatalogLatch)){catalogLatch.clear();status="clear_enqueue_failed";}
            readyEvent("latch",catalogLatch.generation,catalogLatch.revision,status,SystemClock.elapsedRealtimeNanos());
        };
        File root=new File(activity.getExternalFilesDir(null),"shelf-window-metrics");
        if (!root.isDirectory() && !root.mkdirs())throw new IllegalStateException("Shelf metrics folder unavailable");
        File file=new File(root,"window-"+Process.myPid()+"-"+id+".jsonl");
        File readyRoot=new File(root,"catalog-ready");
        File readyFile=new File(readyRoot,file.getName());
        thread.start(); handler=new Handler(thread.getLooper());
        handler.post(()->{
            try {
                output=new FileOutputStream(file);
                if(!readyRoot.isDirectory()&&!readyRoot.mkdirs())throw new IllegalStateException("Catalog binding folder unavailable");
                readyOutput=new FileOutputStream(readyFile);
                writeReady(new JSONObject().put("kind","start").put("schema",1).put("pid",Process.myPid()).put("window_id",id)
                        .put("activity_started_elapsed_ns",createdNs).put("max_events",64).put("max_bytes",65536));
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
                        .put("callback_elapsed_ns",SystemClock.elapsedRealtimeNanos()).put("callback_mono_ns",System.nanoTime()).put("drop_count",drop)
                        .put("total_ns",copy.getMetric(FrameMetrics.TOTAL_DURATION)).put("first_draw",copy.getMetric(FrameMetrics.FIRST_DRAW_FRAME))
                        .put("intended_vsync_ns",copy.getMetric(FrameMetrics.INTENDED_VSYNC_TIMESTAMP))
                        .put("vsync_ns",copy.getMetric(FrameMetrics.VSYNC_TIMESTAMP))
                        .put("unknown_ns",copy.getMetric(FrameMetrics.UNKNOWN_DELAY_DURATION))
                        .put("animation_ns",copy.getMetric(FrameMetrics.ANIMATION_DURATION))
                        .put("input_ns",copy.getMetric(FrameMetrics.INPUT_HANDLING_DURATION))
                        .put("layout_measure_ns",copy.getMetric(FrameMetrics.LAYOUT_MEASURE_DURATION))
                        .put("draw_ns",copy.getMetric(FrameMetrics.DRAW_DURATION))
                        .put("sync_ns",copy.getMetric(FrameMetrics.SYNC_DURATION))
                        .put("gpu_ns",copy.getMetric(FrameMetrics.GPU_DURATION)).put("deadline_ns",copy.getMetric(FrameMetrics.DEADLINE)));
            } catch(Exception error){fail(error);}
        };
        window.addOnFrameMetricsAvailableListener(listener,handler);
    }

    boolean catalogApplied(long generation,long revision,boolean pending) {
        String status=catalogLatch.arm(window,generation,revision,pending);
        readyEvent("apply",generation,revision,status,SystemClock.elapsedRealtimeNanos());
        if(!"armed".equals(status))return false;
        choreographer.postFrameCallback(catalogFrame);return true;
    }
    void catalogReady(long generation,long revision,long elapsedNs) {
        readyEvent("ready_pre_draw",generation,revision,catalogLatch.ready(window,generation,revision),elapsedNs);
    }
    void catalogTreeDraw(long generation,long revision) {
        readyEvent("tree_draw_begin",generation,revision,catalogLatch.draw(window,generation,revision),SystemClock.elapsedRealtimeNanos());
    }
    private void readyEvent(String kind,long generation,long revision,String status,long elapsedNs) {
        final long monoNs=System.nanoTime(),frameTimeNs=catalogLatch.frameTimeNs;
        final boolean active=catalogLatch.active;
        final String readyStatus=catalogLatch.readyStatus,drawStatus=catalogLatch.drawStatus;
        handler.post(()->{
            try {
                JSONObject event=new JSONObject().put("kind",kind).put("pid",Process.myPid()).put("window_id",windowId)
                        .put("latch_id",1).put("generation",generation).put("revision",revision).put("status",status)
                        .put("elapsed_ns",elapsedNs).put("mono_ns",monoNs).put("frame_time_ns",frameTimeNs)
                        .put("active",active).put("ready_status",readyStatus).put("draw_status",drawStatus);
                writeReady(event);
            }catch(Exception error){fail(error);}
        });
    }
    private void writeReady(JSONObject value)throws Exception {
        byte[] raw=(value.toString()+"\n").getBytes(StandardCharsets.UTF_8);
        if(++readyEvents>64||readyBytes+raw.length>65536)throw new IllegalStateException("Catalog binding bound");
        readyOutput.write(raw);readyBytes+=raw.length;
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
        choreographer.removeFrameCallback(catalogFrame);mainHandler.removeCallbacks(clearCatalogLatch);catalogLatch.close();
        readyEvent("stop",catalogLatch.generation,catalogLatch.revision,catalogLatch.readyStatus,SystemClock.elapsedRealtimeNanos());
        window.removeOnFrameMetricsAvailableListener(listener);
        handler.post(()->{
            try {if(readyOutput!=null)readyOutput.close();}
            catch(Exception error){fail(error);}
            try {
                if(output!=null&&!failed)write(new JSONObject().put("kind","stop").put("frames",frames).put("dropped",dropped));
            } catch(Exception error){fail(error);} finally{
                try {if(output!=null)output.close();}catch(Exception error){fail(error);}
                thread.quitSafely();
            }
        });
    }
}
