// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.os.Handler;
import android.os.Process;
import android.os.SystemClock;
import android.util.Log;
import android.view.Choreographer;
import android.view.View;
import android.view.Window;
import org.json.JSONObject;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Consumer;

/** F08_REVIEW + explicit shelf_metrics only. Never schedules or changes a product draw. */
final class ReaderFrameObserver implements AutoCloseable {
    private static final int MAX_EVENTS=20000, MAX_PENDING=256;
    private static final long MAX_BYTES=32L*1024*1024;
    private final Window window;
    private final long windowId;
    private final Handler handler;
    private final Consumer<Exception> parentFailure;
    private final Choreographer choreographer=Choreographer.getInstance();
    private final AtomicInteger pending=new AtomicInteger();
    private final AtomicBoolean failureQueued=new AtomicBoolean();
    private final AtomicLong attempted=new AtomicLong(), rejected=new AtomicLong();
    private FileOutputStream output;
    private long events,bytes,acceptId,generation=-1,drawId;
    private PageSnapshot accepted;
    private volatile boolean failed,closed;

    ReaderFrameObserver(Window window,long windowId,Handler handler,File root,Consumer<Exception> parentFailure) {
        this.window=window;this.windowId=windowId;this.handler=handler;this.parentFailure=parentFailure;
        File directory=new File(root,"reader-draw");
        File file=new File(directory,"window-"+Process.myPid()+"-"+windowId+".jsonl");
        handler.post(()->{
            try {
                if(!directory.isDirectory()&&!directory.mkdirs())throw new IllegalStateException("Reader trace folder");
                output=new FileOutputStream(file);
                write(base("start").put("schema",1).put("signal","ReaderView.canvas.drawBitmap")
                        .put("join_metric","VSYNC_TIMESTAMP").put("clock","System.nanoTime")
                        .put("max_events",MAX_EVENTS).put("max_pending",MAX_PENDING).put("max_bytes",MAX_BYTES));
            }catch(Exception error){fail(error);}
        });
    }

    void pageSet(ReaderView view,PageSnapshot page) {
        accepted=null;generation=-1;
        try { submit(snapshot(base("page_set"),view,page)); }
        catch(Exception error){failedEvent(error);}
    }

    void accept(ReaderView view,long requestGeneration,PageSnapshot page) {
        accepted=page;generation=requestGeneration;acceptId++;
        try { submit(snapshot(base("accept"),view,page).put("accept_id",acceptId)
                .put("request_generation",generation).put("same_current_page",page==view.page())); }
        catch(Exception error){failedEvent(error);}
    }

    void empty(ReaderView view,PageSnapshot page) {
        try { submit(snapshot(base("no_bitmap"),view,page)); }
        catch(Exception error){failedEvent(error);}
    }

    void draw(ReaderView view,PageSnapshot page,long beginNs,long endNs,boolean painted,
              float panX,float panY,float limitX,float limitY) {
        long frameTime=-1;String clockStatus="ok";
        try {frameTime=choreographer.getFrameTimeNanos();}
        catch(IllegalStateException unavailable){clockStatus=unavailable.toString();}
        try {
            submit(snapshot(base("bitmap_draw"),view,page).put("draw_id",++drawId).put("accept_id",acceptId)
                    .put("request_generation",generation).put("accepted_snapshot",page==accepted)
                    .put("same_current_page",page==view.page())
                    .put("frame_time_ns",frameTime).put("frame_time_status",clockStatus)
                    .put("draw_begin_mono_ns",beginNs).put("draw_end_mono_ns",endNs).put("painted",painted)
                    .put("pan_x",panX).put("pan_y",panY).put("pan_limit_x",limitX).put("pan_limit_y",limitY));
        }catch(Exception error){failedEvent(error);}
    }

    void stopRequest(int expectedPid,long expectedWindow,String status,long elapsedNs) {
        if(closed)return;
        try {submit(base("stop_request").put("expected_pid",expectedPid).put("expected_window_id",expectedWindow)
                .put("status",status).put("requested_elapsed_ns",elapsedNs));}
        catch(Exception error){failedEvent(error);}
    }

    private JSONObject base(String kind)throws Exception {
        return new JSONObject().put("kind",kind).put("pid",Process.myPid()).put("window_id",windowId)
                .put("window_identity",System.identityHashCode(window))
                .put("elapsed_ns",SystemClock.elapsedRealtimeNanos()).put("mono_ns",System.nanoTime());
    }
    private JSONObject snapshot(JSONObject event,ReaderView view,PageSnapshot page)throws Exception {
        View decor=window.getDecorView();
        boolean sameWindow=view.isAttachedToWindow()&&view.getRootView()==decor
                &&view.getWindowToken()!=null&&view.getWindowToken()==decor.getWindowToken();
        event.put("view_identity",System.identityHashCode(view)).put("same_window",sameWindow)
                .put("attached",view.isAttachedToWindow()).put("shown",view.isShown())
                .put("view_width",view.getWidth()).put("view_height",view.getHeight())
                .put("snapshot_identity",page==null?0:System.identityHashCode(page))
                .put("page_present",page!=null).put("bitmap_present",page!=null&&page.bitmap!=null);
        if(page!=null){
            boolean bitmap=page.bitmap!=null,recycled=bitmap&&page.bitmap.isRecycled();
            event.put("book_id",page.bookId).put("page_index",page.index).put("page_count",page.pageCount)
                    .put("part",page.part).put("start",page.start).put("end",page.end)
                    .put("font",page.layoutFont).put("zoom",page.layoutZoom).put("fixed",page.fixed)
                    .put("source_key",page.sourceKey==null?JSONObject.NULL:page.sourceKey)
                    .put("bitmap_recycled",recycled)
                    .put("bitmap_width",bitmap&&!recycled?page.bitmap.getWidth():JSONObject.NULL)
                    .put("bitmap_height",bitmap&&!recycled?page.bitmap.getHeight():JSONObject.NULL);
        }
        return event;
    }

    private void submit(JSONObject event) {
        long sequence=attempted.incrementAndGet();
        if(closed||failed||failureQueued.get()){rejected.incrementAndGet();return;}
        if(pending.incrementAndGet()>MAX_PENDING){
            pending.decrementAndGet();rejected.incrementAndGet();
            failedEvent(new IllegalStateException("Reader trace enqueue bound"));return;
        }
        try {event.put("sequence",sequence);}catch(Exception error){pending.decrementAndGet();failedEvent(error);return;}
        if(!handler.post(()->{
            try {
                if(++events>MAX_EVENTS)throw new IllegalStateException("Reader trace event bound");
                write(event);
            }catch(Exception error){fail(error);}finally{pending.decrementAndGet();}
        })){pending.decrementAndGet();rejected.incrementAndGet();failedEvent(new IllegalStateException("Reader trace handler stopped"));}
    }
    private void write(JSONObject event)throws Exception {
        byte[] raw=(event.toString()+"\n").getBytes(StandardCharsets.UTF_8);
        if(bytes+raw.length>MAX_BYTES)throw new IllegalStateException("Reader trace byte bound");
        output.write(raw);bytes+=raw.length;
    }
    private void failedEvent(Exception error) {
        if(!failureQueued.compareAndSet(false,true))return;
        Log.e("EXRReaderMetrics","Capture failed: "+error);
        if(!handler.post(()->fail(error)))failed=true;
    }
    private void fail(Exception error) {
        if(failed)return;failed=true;failureQueued.set(true);
        Log.e("EXRReaderMetrics","Capture failed: "+error);
        if(output!=null)try {write(base("error").put("detail",error.toString()));}
        catch(Exception ignored){Log.e("EXRReaderMetrics","Could not retain capture failure");}
    }
    boolean closedCleanly() {return closed&&output==null&&!failed;}

    @Override public void close() {close("activity_destroy",SystemClock.elapsedRealtimeNanos());}
    void close(String reason,long requestedNs) {
        if(closed)return;closed=true;
        if(!handler.post(()->{
            try {
                if(output!=null){
                    write(base("stop").put("events",events).put("attempted",attempted.get())
                            .put("rejected",rejected.get()).put("pending",pending.get()).put("failed",failed)
                            .put("stop_reason",reason).put("scope_end_requested_elapsed_ns",requestedNs));
                    output.close();output=null;
                }
            }catch(Exception error){
                fail(error);parentFailure.accept(error);
                if(output!=null)try {output.close();}catch(Exception again){parentFailure.accept(again);}
            }
        })){
            Exception error=new IllegalStateException("Reader trace close handler stopped");
            failed=true;parentFailure.accept(error);
        }
    }
}
