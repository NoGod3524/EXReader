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
    final ReaderFrameObserver readerObserver;
    private final HandlerThread thread=new HandlerThread("exr-shelf-frame-metrics") {
        @Override public void run() {
            try {super.run();}finally{if(BuildConfig.F08_REVIEW)writeClosedReceipt();}
        }
    };
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
    private volatile boolean closed,sealed;
    private final File captureFailureFile,closedReceiptFile;
    private String closeReason="not_closed";
    private long listenerRemovedElapsedNs,listenerRemovedMonoNs;

    static ShelfWindowMetrics start(Activity activity,long createdNs) {
        if ((!BuildConfig.DEBUG && !BuildConfig.F08_REVIEW) || !activity.getIntent().getBooleanExtra("shelf_metrics",false))return null;
        return new ShelfWindowMetrics(activity,createdNs);
    }

    private ShelfWindowMetrics(Activity activity,long createdNs) {
        window=activity.getWindow();
        long id=WINDOWS.incrementAndGet();windowId=id;
        catalogLatch=new CatalogFrameLatch(window);
        clearCatalogLatch=()->{
            if(closed)return;
            catalogLatch.clear();
            readyEvent("clear",catalogLatch.generation,catalogLatch.revision,"cleared",SystemClock.elapsedRealtimeNanos());
        };
        catalogFrame=frameTimeNanos->{
            if(closed)return;
            String status=catalogLatch.frame(window,frameTimeNanos);
            if(!mainHandler.postAtFrontOfQueue(clearCatalogLatch)){catalogLatch.clear();status="clear_enqueue_failed";}
            readyEvent("latch",catalogLatch.generation,catalogLatch.revision,status,SystemClock.elapsedRealtimeNanos());
        };
        File root=new File(activity.getExternalFilesDir(null),"shelf-window-metrics");
        if (!root.isDirectory() && !root.mkdirs())throw new IllegalStateException("Shelf metrics folder unavailable");
        File file=new File(root,"window-"+Process.myPid()+"-"+id+".jsonl");
        File readyRoot=new File(root,"catalog-ready");
        File readyFile=new File(readyRoot,file.getName());
        captureFailureFile=new File(root,"window-"+Process.myPid()+"-"+id+"-capture-error.json");
        closedReceiptFile=new File(root,"window-"+Process.myPid()+"-"+id+"-closed.json");
        thread.start(); handler=new Handler(thread.getLooper());
        readerObserver=BuildConfig.F08_REVIEW?new ReaderFrameObserver(window,id,handler,root,this::fail):null;
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
            if(sealed){externalFailure(new IllegalStateException("Frame callback after collector seal"));return;}
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
                        .put("command_issue_ns",copy.getMetric(FrameMetrics.COMMAND_ISSUE_DURATION))
                        .put("swap_buffers_ns",copy.getMetric(FrameMetrics.SWAP_BUFFERS_DURATION))
                        .put("gpu_ns",copy.getMetric(FrameMetrics.GPU_DURATION)).put("deadline_ns",copy.getMetric(FrameMetrics.DEADLINE)));
            } catch(Exception error){fail(error);}
        };
        window.addOnFrameMetricsAvailableListener(listener,handler);
    }

    boolean catalogApplied(long generation,long revision,boolean pending) {
        if(closed)return false;
        String status=catalogLatch.arm(window,generation,revision,pending);
        readyEvent("apply",generation,revision,status,SystemClock.elapsedRealtimeNanos());
        if(!"armed".equals(status))return false;
        choreographer.postFrameCallback(catalogFrame);return true;
    }
    void catalogReady(long generation,long revision,long elapsedNs) {
        if(closed)return;
        readyEvent("ready_pre_draw",generation,revision,catalogLatch.ready(window,generation,revision),elapsedNs);
    }
    void catalogTreeDraw(long generation,long revision) {
        if(closed)return;
        readyEvent("tree_draw_begin",generation,revision,catalogLatch.draw(window,generation,revision),SystemClock.elapsedRealtimeNanos());
    }
    private void readyEvent(String kind,long generation,long revision,String status,long elapsedNs) {
        if(closed)return;
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
    private void writeClosedReceipt() {
        File pendingFile=new File(closedReceiptFile.getPath()+".pending");
        try {
            JSONObject value=new JSONObject().put("kind","capture_closed").put("pid",Process.myPid()).put("window_id",windowId)
                    .put("stop_reason",closeReason).put("failed",failed||!closed||!sealed||captureFailureFile.exists())
                    .put("reader_closed_clean",readerObserver!=null&&readerObserver.closedCleanly())
                    .put("listener_removed_elapsed_ns",listenerRemovedElapsedNs).put("listener_removed_mono_ns",listenerRemovedMonoNs)
                    .put("closed_elapsed_ns",SystemClock.elapsedRealtimeNanos()).put("closed_mono_ns",System.nanoTime());
            if(pendingFile.exists()||closedReceiptFile.exists())throw new IllegalStateException("Capture close receipt already exists");
            try(FileOutputStream receipt=new FileOutputStream(pendingFile)){
                receipt.write((value.toString()+"\n").getBytes(StandardCharsets.UTF_8));
            }
            if(!pendingFile.renameTo(closedReceiptFile))throw new IllegalStateException("Capture close receipt rename failed");
        }catch(Exception error){externalFailure(error);}
    }

    private void externalFailure(Exception error) {
        failed=true;
        Log.e("EXRShelfMetrics","Capture failed after seal: "+error);
        if(captureFailureFile.exists())return;
        try(FileOutputStream failure=new FileOutputStream(captureFailureFile)){
            failure.write((new JSONObject().put("kind","error").put("pid",Process.myPid()).put("window_id",windowId)
                    .put("elapsed_ns",SystemClock.elapsedRealtimeNanos()).put("detail",error.toString()).toString()+"\n")
                    .getBytes(StandardCharsets.UTF_8));
        }catch(Exception again){Log.e("EXRShelfMetrics","Could not retain post-seal failure: "+again);}
    }
    private void fail(Exception error) {
        if(sealed){externalFailure(error);return;}
        if(failed)return; failed=true; Log.e("EXRShelfMetrics","Capture failed: "+error);
        if(output!=null)try{write(new JSONObject().put("kind","error").put("detail",error.toString()));}
        catch(Exception ignored){Log.e("EXRShelfMetrics","Could not retain capture failure");}
    }
    boolean readerStopRequest(int expectedPid,long expectedWindow,long elapsedNs) {
        if(!BuildConfig.F08_REVIEW)return false;
        String status=closed?"rejected_closed":expectedPid!=Process.myPid()||expectedWindow!=windowId
                ?"rejected_owner":"accepted";
        Log.i("EXRShelfMetrics","F08 capture stop status="+status+" expected_pid="+expectedPid+" expected_window="+expectedWindow
                +" pid="+Process.myPid()+" window="+windowId+" elapsed_ns="+elapsedNs);
        if(readerObserver!=null)readerObserver.stopRequest(expectedPid,expectedWindow,status,elapsedNs);
        return "accepted".equals(status);
    }
    @Override public void close() {close("activity_destroy",SystemClock.elapsedRealtimeNanos());}
    void close(String reason,long requestedNs) {
        if(closed)return;
        closeReason=reason;
        choreographer.removeFrameCallback(catalogFrame);mainHandler.removeCallbacks(clearCatalogLatch);catalogLatch.close();
        readyEvent("stop",catalogLatch.generation,catalogLatch.revision,catalogLatch.readyStatus,SystemClock.elapsedRealtimeNanos());
        closed=true;
        if(BuildConfig.F08_REVIEW&&readerObserver!=null)readerObserver.close(reason,requestedNs);
        window.removeOnFrameMetricsAvailableListener(listener);
        listenerRemovedElapsedNs=SystemClock.elapsedRealtimeNanos();listenerRemovedMonoNs=System.nanoTime();
        // Drain messages already captured by the registered listener before closing its files.
        if(!handler.post(()->{
            if(!handler.post(()->{
            try {if(readyOutput!=null)readyOutput.close();}
            catch(Exception error){fail(error);}
            try {
                if(output!=null&&!failed)write(new JSONObject().put("kind","stop").put("frames",frames).put("dropped",dropped)
                        .put("stop_reason",reason).put("scope_end_requested_elapsed_ns",requestedNs)
                        .put("listener_removed_elapsed_ns",listenerRemovedElapsedNs).put("listener_removed_mono_ns",listenerRemovedMonoNs)
                        .put("footer_elapsed_ns",SystemClock.elapsedRealtimeNanos()).put("footer_mono_ns",System.nanoTime()));
            } catch(Exception error){fail(error);} finally{
                sealed=true;
                try {if(output!=null)output.close();}catch(Exception error){externalFailure(error);}
                output=null;
                thread.quitSafely();
            }
            }))fail(new IllegalStateException("Collector final close enqueue failed"));
        }))fail(new IllegalStateException("Collector close handler stopped"));
    }
}
