// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.Process;
import android.os.SystemClock;
import android.os.Trace;
import android.view.FrameMetrics;
import android.view.View;
import android.view.Window;
import android.widget.ListView;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

/** Same production Activity/ListView/Window/PID; test-only ABBA, never an F08 pass. */
public final class FrameLayerTest extends Instrumentation {
    private static final int MAX_FRAMES=20000;
    private static final int[] METRICS={FrameMetrics.UNKNOWN_DELAY_DURATION,FrameMetrics.INPUT_HANDLING_DURATION,
        FrameMetrics.ANIMATION_DURATION,FrameMetrics.LAYOUT_MEASURE_DURATION,FrameMetrics.DRAW_DURATION,
        FrameMetrics.SYNC_DURATION,FrameMetrics.COMMAND_ISSUE_DURATION,FrameMetrics.SWAP_BUFFERS_DURATION,
        FrameMetrics.TOTAL_DURATION,FrameMetrics.FIRST_DRAW_FRAME,FrameMetrics.INTENDED_VSYNC_TIMESTAMP,
        FrameMetrics.VSYNC_TIMESTAMP,FrameMetrics.GPU_DURATION,FrameMetrics.DEADLINE};
    private static final String[] NAMES={"unknown_ns","input_ns","animation_ns","layout_measure_ns","draw_ns",
        "sync_ns","command_issue_ns","swap_buffers_ns","total_ns","first_draw","intended_vsync_ns","vsync_ns","gpu_ns","deadline_ns"};
    private static final class Sample {
        final long[] values=new long[METRICS.length];
        final long callbackMono,callbackBoot;
        final int drop;
        final boolean sameWindow;
        Sample(Window observed,Window expected,FrameMetrics value,int lost){
            FrameMetrics copy=new FrameMetrics(value);
            for(int i=0;i<METRICS.length;i++)values[i]=copy.getMetric(METRICS[i]);
            callbackMono=System.nanoTime();callbackBoot=SystemClock.elapsedRealtimeNanos();drop=lost;sameWindow=observed==expected;
        }
    }
    private Bundle arguments;
    private HandlerThread thread;
    private Handler handler;
    private final ArrayList<Sample> frames=new ArrayList<>();
    private final ConcurrentLinkedQueue<String> problems=new ConcurrentLinkedQueue<>();
    private final AtomicInteger activityCreates=new AtomicInteger();
    private Window window;
    private MainActivity activity;
    private ListView list;
    private Window.OnFrameMetricsAvailableListener listener;
    private File directory;
    private long registeredMono,callbacks,drops,overflow;
    private int originalLayer=-1;
    private final JSONArray segments=new JSONArray();
    @Override public void onCreate(Bundle args){super.onCreate(args);arguments=args;start();}
    private static void require(boolean value,String message){if(!value)throw new AssertionError(message);}
    private static JSONObject clocks()throws Exception {
        long a=System.nanoTime(),boot=SystemClock.elapsedRealtimeNanos(),b=System.nanoTime();
        return new JSONObject().put("mono_before_ns",a).put("boot_ns",boot).put("mono_after_ns",b);
    }
    private void write(String name,JSONObject value)throws Exception {
        Files.write(new File(directory,name).toPath(),value.toString(2).getBytes(StandardCharsets.UTF_8));
    }
    private void waitFile(String name,long timeoutMs)throws Exception {
        long until=SystemClock.uptimeMillis()+timeoutMs;
        while(!new File(directory,name).isFile()&&SystemClock.uptimeMillis()<until)SystemClock.sleep(25);
        require(new File(directory,name).isFile(),"Missing host checkpoint "+name);
    }
    @Override public void callActivityOnCreate(Activity created,Bundle state){
        if(created instanceof MainActivity){
            activityCreates.incrementAndGet();
            require(window==null,"MainActivity recreated during one-process experiment");
            activity=(MainActivity)created;window=created.getWindow();registeredMono=System.nanoTime();
            listener=(observed,value,drop)->{
                callbacks++;drops+=drop;
                if(frames.size()>=MAX_FRAMES){overflow++;return;}
                try{frames.add(new Sample(observed,window,value,drop));}
                catch(Throwable error){problems.add("callback: "+error);}
            };
            window.addOnFrameMetricsAvailableListener(listener,handler);
        }
        super.callActivityOnCreate(created,state);
    }
    private JSONObject snapshot(){
        AtomicReference<JSONObject> result=new AtomicReference<>();
        runOnMainSync(()->{
            try{
                View first=list.getChildCount()>0?list.getChildAt(0):null;
                result.set(new JSONObject().put("mono_ns",System.nanoTime()).put("pid",Process.myPid())
                    .put("activity_identity",System.identityHashCode(activity)).put("window_identity",System.identityHashCode(window))
                    .put("view_identity",System.identityHashCode(list)).put("resource_name",activity.getResources().getResourceName(list.getId()))
                    .put("layer_type",list.getLayerType()).put("view_hardware_accelerated",list.isHardwareAccelerated())
                    .put("window_flags",window.getAttributes().flags).put("attached",list.isAttachedToWindow()).put("shown",list.isShown())
                    .put("width",list.getWidth()).put("height",list.getHeight()).put("rows",list.getCount())
                    .put("first_position",list.getFirstVisiblePosition()).put("last_position",list.getLastVisiblePosition())
                    .put("first_top",first==null?JSONObject.NULL:first.getTop()).put("first_label",first==null?JSONObject.NULL:first.getContentDescription())
                    .put("canvas_hardware_accelerated",JSONObject.NULL).put("canvas_observation","No production Canvas override or draw interception"));
            }catch(Exception error){throw new IllegalStateException(error);}
        });
        return result.get();
    }
    private void awaitList()throws Exception {
        long until=SystemClock.uptimeMillis()+60000;
        while(SystemClock.uptimeMillis()<until){
            AtomicReference<Boolean> ready=new AtomicReference<>(false);
            runOnMainSync(()->{list=activity.findViewById(R.id.book_list);ready.set(list!=null&&list.isShown()&&list.getCount()>0&&list.getHeight()>0);});
            if(ready.get())return;
            SystemClock.sleep(50);
        }
        throw new AssertionError("Production book_list did not become visible");
    }
    private void segment(int slot,int layer)throws Exception {
        String name="F08_ABBA_"+slot+"_"+(layer==View.LAYER_TYPE_NONE?"NONE":"SOFTWARE");
        JSONObject value=new JSONObject().put("slot",slot).put("name",name).put("requested_layer",layer);
        segments.put(value);
        long[] begin={0};
        runOnMainSync(()->{begin[0]=System.nanoTime();Trace.beginAsyncSection(name,slot+1);list.setLayerType(layer,null);});
        value.put("start_mono_ns",begin[0]).put("start",snapshot()).put("trace_enabled",Trace.isEnabled());
        int distance=Math.max(1,value.getJSONObject("start").getInt("height")*2);
        long[] forward={0};
        runOnMainSync(()->{forward[0]=System.nanoTime();list.smoothScrollBy(distance,1000);});
        value.put("forward_action_mono_ns",forward[0]).put("distance_px",distance).put("scroll_duration_ms",1000);
        SystemClock.sleep(1100);
        value.put("forward",snapshot());
        long[] reverse={0};
        runOnMainSync(()->{reverse[0]=System.nanoTime();list.smoothScrollBy(-distance,1000);});
        value.put("reverse_action_mono_ns",reverse[0]);
        SystemClock.sleep(1400);
        value.put("end",snapshot());
        long[] end={0};runOnMainSync(()->{end[0]=System.nanoTime();Trace.endAsyncSection(name,slot+1);});
        value.put("end_mono_ns",end[0]);
        JSONObject start=value.getJSONObject("start"),moved=value.getJSONObject("forward");
        require(start.getInt("first_position")!=moved.getInt("first_position")||start.optInt("first_top")!=moved.optInt("first_top"),"No actual forward ListView movement");
        require(moved.getInt("first_position")!=value.getJSONObject("end").getInt("first_position")||moved.optInt("first_top")!=value.getJSONObject("end").optInt("first_top"),"No actual reverse ListView movement");
        require(start.getInt("layer_type")==layer,"Requested layer did not apply");
        write("checkpoint-"+slot+".json",value);
        waitFile("checkpoint-"+slot+"-go",10000);
    }
    @Override public void onStart(){
        Bundle result=new Bundle();JSONObject report=new JSONObject();boolean success=false;
        try{
            directory=new File(getTargetContext().getExternalFilesDir(null),"f08-frame-layer");
            require(directory.isDirectory()||directory.mkdirs(),"Diagnostic output directory");
            report.put("source_sha",arguments.getString("source_sha")).put("run_id",arguments.getString("run_id"))
                .put("attempt",arguments.getString("attempt")).put("api",android.os.Build.VERSION.SDK_INT)
                .put("abi",android.os.Build.SUPPORTED_ABIS[0]).put("pid",Process.myPid()).put("f08_accepted",false)
                .put("max_frames",MAX_FRAMES).put("clock_begin",clocks()).put("frame_clock","System.nanoTime/CLOCK_MONOTONIC")
                .put("pattern","NONE,SOFTWARE,SOFTWARE,NONE").put("segments",segments)
                .put("first_draw_policy","Retain every frame; classify FIRST_DRAW_FRAME separately and include in all-frame result")
                .put("outside_policy","Retain all callbacks outside the four intended-vsync intervals")
                .put("gpu_semantics","API34 GPU_COMPLETED minus COMMAND_SUBMISSION_COMPLETED; completion may include acquire-fence wait")
                .put("budgets",new JSONObject().put("p95_ms",16.67).put("p99_ms",33.34).put("tti_ms",2000).put("pss_bytes",512L*1024*1024));
            try(BookStore store=new BookStore(getTargetContext(),new File(getTargetContext().getFilesDir(),"library.db"))){
                require(!store.metadataRepairPending()&&store.books().size()==2202,"Complete original 2202 real-SDK seed");
                report.put("books",2202);
            }
            thread=new HandlerThread("f08-frame-layer-metrics");thread.start();handler=new Handler(thread.getLooper());
            long launch=System.nanoTime();
            Intent intent=new Intent(getTargetContext(),MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            intent.putExtra("shelf_metrics",false);
            Activity launched=startActivitySync(intent);
            require(launched==activity&&window!=null,"One real MainActivity/Window was instrumented");
            awaitList();
            originalLayer=list.getLayerType();require(originalLayer==View.LAYER_TYPE_NONE,"Production ListView default layer changed");
            report.put("activity_launch_mono_ns",launch).put("ready_mono_ns",System.nanoTime()).put("original_layer",originalLayer)
                .put("initial",snapshot()).put("registered_mono_ns",registeredMono);
            write("ready.json",new JSONObject().put("pid",Process.myPid()).put("mono_ns",System.nanoTime()));
            waitFile("go",60000);
            for(int slot=0;slot<4;slot++)segment(slot,(slot==0||slot==3)?View.LAYER_TYPE_NONE:View.LAYER_TYPE_SOFTWARE);
            SystemClock.sleep(1000);
            success=true;
        }catch(Throwable error){problems.add(android.util.Log.getStackTraceString(error));}
        finally{
            try{
                if(window!=null&&listener!=null)runOnMainSync(()->window.removeOnFrameMetricsAvailableListener(listener));
                if(handler!=null){CountDownLatch drained=new CountDownLatch(1);handler.post(drained::countDown);require(drained.await(5,TimeUnit.SECONDS),"Frame callback handler did not drain");}
                if(list!=null&&originalLayer>=0)runOnMainSync(()->list.setLayerType(originalLayer,null));
                report.put("restored",list==null?JSONObject.NULL:snapshot()).put("activity_creates",activityCreates.get())
                    .put("callbacks",callbacks).put("stored_frames",frames.size()).put("callback_drops",drops).put("overflow_callbacks",overflow)
                    .put("clock_end",clocks()).put("completed",success).put("f08_accepted",false);
                JSONArray issues=new JSONArray();for(String problem:problems)issues.put(problem);report.put("problems",issues);
                StringBuilder raw=new StringBuilder();
                for(int index=0;index<frames.size();index++){
                    Sample frame=frames.get(index);JSONObject row=new JSONObject().put("sequence",index+1).put("pid",Process.myPid())
                        .put("window_identity",System.identityHashCode(window)).put("same_window",frame.sameWindow).put("drop_count",frame.drop)
                        .put("callback_mono_ns",frame.callbackMono).put("callback_boot_ns",frame.callbackBoot);
                    for(int metric=0;metric<NAMES.length;metric++)row.put(NAMES[metric],frame.values[metric]);
                    raw.append(row.toString()).append('\n');
                }
                Files.write(new File(directory,"frames.jsonl").toPath(),raw.toString().getBytes(StandardCharsets.UTF_8));
                write("report.json",report);
                waitFile("release",30000);
            }catch(Throwable error){success=false;result.putString("detail",android.util.Log.getStackTraceString(error));}
            if(thread!=null)thread.quitSafely();
            if(activity!=null)runOnMainSync(()->activity.finish());
            result.putString("stream",success&&problems.isEmpty()?"F08_FRAME_LAYER_OK\n":"F08_FRAME_LAYER_FAILED "+problems+" "+result.getString("detail","")+"\n");
            finish(success&&problems.isEmpty()?Activity.RESULT_OK:Activity.RESULT_CANCELED,result);
        }
    }
}
