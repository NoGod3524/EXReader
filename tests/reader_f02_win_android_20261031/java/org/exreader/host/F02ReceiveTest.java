// SPDX-License-Identifier: MIT
package org.exreader.host;
import android.app.Activity;
import android.app.Instrumentation;
import android.accessibilityservice.AccessibilityServiceInfo;
import android.content.Context;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.Rect;
import android.os.Bundle;
import android.os.SystemClock;
import android.view.MotionEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import java.io.File;
import java.io.FileOutputStream;
import java.lang.reflect.Field;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.function.Predicate;
import org.json.JSONArray;
import org.json.JSONObject;

/** Real target Activity operations. The positive original comes only from native HTTPS Receive. */
public final class F02ReceiveTest extends Instrumentation {
    private Context context;
    private Activity activity;
    private Bundle arguments;
    private JSONObject input;
    private String phase,activeCheck;
    private final JSONArray checks=new JSONArray();
    private final JSONObject observed=new JSONObject();
    private String activeSubstep="none";
    private long activeCheckStarted;
    private final JSONArray corruptTrace=new JSONArray();
    private JSONObject failureObservation=new JSONObject();
    private boolean observingCorrupt(){return "corrupt_original_rejected".equals(activeCheck);}
    private static String statusCategory(String value){
        if(value.contains("原件完整性校验失败"))return "original_integrity";
        if(value.contains("接收的原件校验失败"))return "receive_integrity";
        if(value.contains("原件下载未完成"))return "download_incomplete";
        if(value.contains("书籍已接收"))return "received";
        if(value.contains("当前不能接收"))return "receive_refused";
        if(value.contains("远端原件身份或大小不可接收"))return "identity_refused";
        if(value.contains("原件不在本机"))return "credentials_missing";
        if(value.contains("原件目录不可用"))return "directory_unavailable";
        if(value.contains("正在核对并接收原件"))return "receiving";
        if(value.contains("本轮同步结束"))return "scan_complete";
        if(value.contains("正在更新书架"))return "projecting";
        if(value.contains("请等待当前操作"))return "busy";
        if(value.contains("已取消"))return "cancelled";
        if(value.contains("就绪"))return "ready";
        return value.isEmpty()?"absent":"other_redacted";
    }
    private JSONObject statusObservation(){
        JSONObject out=new JSONObject();
        try{
            final String[] raw={""};
            act(n->"同步状态".contentEquals(n.getContentDescription()==null?"":n.getContentDescription()),n->raw[0]=text(n));
            String first=raw[0].split("\n",2)[0];
            out.put("category",statusCategory(first));
            if("download_incomplete".equals(statusCategory(first))){
                java.util.regex.Matcher code=java.util.regex.Pattern.compile("（(-?[0-9]{1,10})）").matcher(first);
                if(code.find())out.put("download_code",Long.parseLong(code.group(1)));
            }
        }catch(Throwable ignored){try{out.put("category","capture_unavailable");}catch(Exception absent){}}
        return out;
    }
    private JSONObject panelObservation(){
        try{
            Field instance=SyncController.class.getDeclaredField("instance");instance.setAccessible(true);
            Object controller=instance.get(null),panel=controller==null?null:field(controller,"listener");
            if(!(panel instanceof SyncPanel))return new JSONObject().put("available",false);
            final JSONObject[] captured={null};
            java.util.concurrent.CountDownLatch ready=new java.util.concurrent.CountDownLatch(1);
            new android.os.Handler(android.os.Looper.getMainLooper()).post(()->{
                JSONObject row=new JSONObject();
                try{
                    row.put("available",true).put("busy",field(panel,"busy"));
                    java.util.List<?> rows=(java.util.List<?>)field(panel,"books");
                    for(Object value:rows){
                        NativeSync.RemoteBook book=(NativeSync.RemoteBook)value;
                        if(book.key.equals(input.getString("book_key"))){
                            row.put("target_present",true).put("receivable",book.receivable())
                                .put("selection",book.selection).put("deleted",book.deleted)
                                .put("revision_present",!book.revision.isEmpty()).put("bytes",book.bytes)
                                .put("local_id",book.localId).put("txt_format","txt".equals(book.format))
                                .put("expected_sha",book.sha.equals(input.getString("sha256")));
                            return;
                        }
                    }
                    row.put("target_present",false);
                }catch(Throwable ignored){try{row.put("available",false);}catch(Exception absent){}}
                finally{captured[0]=row;ready.countDown();}
            });
            if(ready.await(200,TimeUnit.MILLISECONDS)&&captured[0]!=null)return captured[0];
            return new JSONObject().put("available",false).put("capture_timeout",true);
        }catch(Throwable ignored){return new JSONObject();}
    }
    private void corruptSnapshot(String label){
        if(!observingCorrupt())return;
        try{
            JSONObject row=new JSONObject().put("label",label).put("substep",activeSubstep)
                .put("elapsed_ms",SystemClock.elapsedRealtime()-activeCheckStarted).put("status",statusObservation());
            File cached=cache();
            row.put("cache_exists",cached.exists()).put("cache_is_file",cached.isFile()).put("cache_bytes",cached.length());
            if(cached.isFile()&&cached.length()<=131072)row.put("cache_sha256",hash(cached));
            File mode=file("f02-get-mode");
            row.put("mode_marker_exists",mode.isFile()).put("panel",panelObservation());
            corruptTrace.put(row);
        }catch(Throwable ignored){
            try{corruptTrace.put(new JSONObject().put("label",label).put("substep",activeSubstep).put("capture_unavailable",true));}catch(Exception absent){}
        }
    }
    private void corruptStep(String value){
        if(observingCorrupt()){activeSubstep=value;corruptSnapshot("before");}
    }
    private void corruptValue(String name,long value){
        if(observingCorrupt())try{corruptTrace.put(new JSONObject().put("substep",activeSubstep).put("elapsed_ms",SystemClock.elapsedRealtime()-activeCheckStarted).put(name,value));}catch(Exception ignored){}
    }
    private static String assertionReason(Throwable failure){
        String message=failure.getMessage();
        if("Actual UI target did not become ready".equals(message))return "ui_target_timeout";
        if("visible UI action".equals(message))return "ui_action_not_visible";
        if("actual SDK owner available".equals(message))return "sdk_owner_unavailable";
        if("failed receive cannot import an original".equals(message))return "failed_receive_imported_original";
        if("failed receive cannot publish cache".equals(message))return "failed_receive_published_cache";
        return "other_redacted";
    }
    private void failureSnapshot(Throwable failure){
        if(!observingCorrupt())return;
        corruptSnapshot("failure");
        try{
            JSONArray frames=new JSONArray();
            for(StackTraceElement frame:failure.getStackTrace()){
                if(frame.getClassName().equals(F02ReceiveTest.class.getName())||frame.getClassName().startsWith(F02ReceiveTest.class.getName()+"$")){
                    String method=frame.getMethodName();
                    if(method.matches("[A-Za-z0-9_$<>]{1,96}"))
                        frames.put(new JSONObject().put("method",method).put("line",frame.getLineNumber()));
                    if(frames.length()==12)break;
                }
            }
            failureObservation=new JSONObject().put("substep",activeSubstep).put("assertion_reason",assertionReason(failure))
                .put("test_frames",frames).put("status",statusObservation()).put("trace",corruptTrace);
            try{
                ExecutorService sdk=(ExecutorService)field(activity,"worker");
                if(sdk!=null&&!sdk.isShutdown()){
                    java.util.concurrent.Future<Integer> sampled=sdk.submit(()->store().nativeLibrary().books().length);
                    try{failureObservation.put("post_failure_sdk_books",sampled.get(2,TimeUnit.SECONDS)).put("sdk_sample","owner_read");}
                    finally{if(!sampled.isDone())sampled.cancel(false);}
                }else failureObservation.put("sdk_sample","owner_unavailable");
            }catch(Throwable ignored){try{failureObservation.put("sdk_sample","capture_unavailable");}catch(Exception absent){}}

        }catch(Throwable ignored){failureObservation=new JSONObject();}
    }
    // F02_COLD_CACHE_PRECONDITION_BEGIN
    private final JSONObject coldPreparation=new JSONObject();
    private final JSONObject normalDownload=new JSONObject();
    private final JSONObject duplicateGets=new JSONObject();
    private final JSONArray coldGuards=new JSONArray();
    private boolean coldSequence;
    private void coldNeed(boolean value,String reason)throws Exception{
        coldPreparation.put("last_condition",reason);
        if(!value)coldPreparation.put("status","failed").put("failure_code",reason);
        need(value,reason);
    }
    private Object syncControllerForTest()throws Exception{
        Field instance=SyncController.class.getDeclaredField("instance");instance.setAccessible(true);
        Object controller=instance.get(null);coldNeed(controller!=null,"sync_controller_present");return controller;
    }
    private JSONObject syncOwnerSnapshot(Object controller)throws Exception{
        ExecutorService owner=(ExecutorService)field(controller,"worker");
        return owner.submit(()->{
            JSONObject value=new JSONObject().put("controller_state",field(controller,"state")).put("epoch",field(controller,"epoch"))
                .put("sdk_task_present",field(controller,"sdkTask")!=null);
            for(String name:new String[]{"preparing","receiving","projecting","closingOwned","pollQueued"})value.put(name,field(controller,name));
            long token=(Long)field(controller,"session");value.put("session_present",token!=0);
            if(token!=0){
                NativeSync.Snapshot snapshot=new NativeSync.Snapshot(NativeSync.command(token,0));
                value.put("native_code",snapshot.code).put("native_state",snapshot.state).put("completed_shards",snapshot.completedShards);
            }
            value.put("target_present",false);
            File product=(File)field(controller,"product");
            for(String[] row:NativeSync.books(product.getAbsolutePath(),"")){
                NativeSync.RemoteBook book=new NativeSync.RemoteBook(row);
                if(book.key.equals(input.getString("book_key"))){
                    value.put("target_present",true).put("target_local_id",book.localId).put("target_receivable",book.receivable());break;
                }
            }
            return value;
        }).get(5,TimeUnit.SECONDS);
    }
    private boolean syncQuiescent(JSONObject value)throws Exception{
        if(!value.getBoolean("session_present")||value.getInt("controller_state")!=NativeSync.FINISHED
            ||value.getInt("native_state")!=NativeSync.FINISHED||value.getInt("native_code")!=0
            ||value.getInt("completed_shards")!=256||value.getBoolean("sdk_task_present")
            ||!value.getBoolean("target_present")||value.getLong("target_local_id")!=0||!value.getBoolean("target_receivable"))return false;
        for(String name:new String[]{"preparing","receiving","projecting","closingOwned","pollQueued"})if(value.getBoolean(name))return false;
        return true;
    }
    private JSONObject coldFileMeta(File target)throws Exception{
        if(!Files.exists(target.toPath(),java.nio.file.LinkOption.NOFOLLOW_LINKS))return new JSONObject().put("exists",false);
        android.system.StructStat value=android.system.Os.lstat(target.getAbsolutePath());
        boolean regular=(value.st_mode&0170000)==0100000;
        return new JSONObject().put("exists",true).put("regular",regular).put("symbolic",Files.isSymbolicLink(target.toPath()))
            .put("dev",value.st_dev).put("ino",value.st_ino).put("nlink",value.st_nlink).put("uid",value.st_uid)
            .put("size",value.st_size).put("mode",value.st_mode&0777).put("sha256",regular?hash(target):"not_regular");
    }
    private void prepareColdCache()throws Exception{
        observed.put("cold_cache_preparation",coldPreparation).put("normal_download",normalDownload).put("duplicate_original_gets",duplicateGets);
        coldPreparation.put("status","preparing").put("expected_bytes",input.getLong("bytes")).put("expected_sha256",input.getString("sha256")).put("guards",coldGuards);
        corruptStep("prepare_sync_owner");
        Object controller=syncControllerForTest();
        JSONObject first=syncOwnerSnapshot(controller);coldPreparation.put("owner_before",first);
        coldNeed(syncQuiescent(first),"sync_owner_finished_before_isolation");
        ExecutorService transfers=(ExecutorService)field(controller,"transfers");
        transfers.submit(()->{}).get(5,TimeUnit.SECONDS);
        JSONObject fenced=syncOwnerSnapshot(controller);coldPreparation.put("owner_fenced",fenced);
        coldNeed(syncQuiescent(fenced)&&first.getLong("epoch")==fenced.getLong("epoch"),"sync_and_transfer_owners_quiescent");
        int count=owner(()->store().nativeLibrary().books().length);coldPreparation.put("sdk_books_before",count);
        coldNeed(count==0,"cold_setup_sdk_empty");
        coldNeed(input.getLong("bytes")==12000&&input.getString("sha256").matches("[0-9a-f]{64}"),"fixed_cold_original_identity");
        File active=cache(),parent=new File(context.getFilesDir(),"sync-cache").getCanonicalFile();
        coldNeed(active.getCanonicalFile().getParentFile().equals(parent),"canonical_active_cache_parent");
        JSONObject before=coldFileMeta(active);coldPreparation.put("before",before);
        coldNeed(before.getBoolean("exists")&&before.getBoolean("regular")&&!before.getBoolean("symbolic")
            &&before.getLong("nlink")==1&&before.getLong("uid")==android.os.Process.myUid()&&before.getLong("uid")>0
            &&before.getLong("size")==12000&&before.getString("sha256").equals(input.getString("sha256")),"verified_initial_sync_cache");
        File directory=file("f02-cold-cache-isolation");
        coldNeed(!Files.exists(directory.toPath(),java.nio.file.LinkOption.NOFOLLOW_LINKS),"new_private_isolation_directory");
        Files.createDirectory(directory.toPath());android.system.Os.chmod(directory.getAbsolutePath(),0700);
        coldPreparation.put("directory_mode",android.system.Os.lstat(directory.getAbsolutePath()).st_mode&0777);
        String relative="f02-cold-cache-isolation/"+input.getString("sha256")+".txt";
        File isolated=file(relative);coldPreparation.put("quarantine_relative",relative).put("substep","atomic_isolation_move");
        Files.move(active.toPath(),isolated.toPath(),java.nio.file.StandardCopyOption.ATOMIC_MOVE);
        JSONObject after=coldFileMeta(isolated);coldPreparation.put("isolated",after).put("active_after",coldFileMeta(active));
        coldNeed(!Files.exists(active.toPath(),java.nio.file.LinkOption.NOFOLLOW_LINKS),"active_cache_absent_after_atomic_move");
        coldNeed(after.getBoolean("regular")&&!after.getBoolean("symbolic")&&after.getLong("dev")==before.getLong("dev")
            &&after.getLong("ino")==before.getLong("ino")&&after.getLong("nlink")==1&&after.getLong("uid")==before.getLong("uid")
            &&after.getLong("size")==before.getLong("size")&&after.getString("sha256").equals(before.getString("sha256")),"isolated_original_identity_preserved");
        JSONObject finalOwner=syncOwnerSnapshot(controller);coldPreparation.put("owner_after",finalOwner);
        coldNeed(syncQuiescent(finalOwner)&&finalOwner.getLong("epoch")==fenced.getLong("epoch"),"sync_owner_still_quiescent");
        coldSequence=true;coldPreparation.put("status","ready").put("substep","cold_ready");
        coldCacheMustRemainAbsent();
    }
    private void coldCacheMustRemainAbsent()throws Exception{
        if(!coldSequence)return;
        boolean exists=Files.exists(cache().toPath(),java.nio.file.LinkOption.NOFOLLOW_LINKS);
        coldGuards.put(new JSONObject().put("elapsed_ms",SystemClock.elapsedRealtime()).put("active_exists",exists));
        coldNeed(!exists,"cold_cache_not_rebuilt");
    }
    private JSONObject originalGetCounter()throws Exception{
        File counter=file("f02-original-get-counter.json");
        coldNeed(counter.isFile(),"original_get_counter_present");
        JSONObject value=new JSONObject(new String(Files.readAllBytes(counter.toPath()),StandardCharsets.UTF_8));
        coldNeed(value.getString("original_sha256").equals(input.getString("sha256"))&&value.getLong("count")>0
            &&value.getLong("last_event_seq")>0,"original_get_counter_identity");
        return value;
    }
    private void normalDownloadStart()throws Exception{
        coldCacheMustRemainAbsent();normalDownload.put("before",originalGetCounter());
    }
    private void normalDownloadEnd()throws Exception{
        JSONObject after=originalGetCounter();normalDownload.put("after",after);
        coldNeed(after.getLong("count")>normalDownload.getJSONObject("before").getLong("count")
            &&after.getInt("response_status")==200&&after.getBoolean("authenticated")
            &&after.getLong("response_bytes")==input.getLong("bytes")&&after.getString("response_sha256").equals(input.getString("sha256")),"normal_receive_performed_original_get");
        coldSequence=false;normalDownload.put("verified",true);
    }
    private void duplicateGetStart()throws Exception{
        duplicateGets.put("before",originalGetCounter()).put("cache_before",coldFileMeta(cache()));
    }
    private void duplicateGetEnd()throws Exception{
        JSONObject after=originalGetCounter();duplicateGets.put("after",after).put("cache_after",coldFileMeta(cache()));
        coldNeed(after.getLong("count")==duplicateGets.getJSONObject("before").getLong("count"),"duplicate_original_get_count_unchanged");
        duplicateGets.put("verified",true);
    }
    // F02_COLD_CACHE_PRECONDITION_END
    interface Check {void run() throws Exception;}
    @Override public void onCreate(Bundle args){super.onCreate(args);arguments=args;start();}
    static void need(boolean value,String reason){if(!value)throw new AssertionError(reason);}
    private void check(String name,Check action)throws Exception{
        activeCheck=name;activeCheckStarted=SystemClock.elapsedRealtime();Bundle status=new Bundle();status.putString("class",getClass().getName());status.putString("test",name);sendStatus(1,status);
        action.run();checks.put(new JSONObject().put("name",name).put("passed",true));sendStatus(0,status);
    }
    private Object field(Object target,String name)throws Exception{
        Field f=target.getClass().getDeclaredField(name);f.setAccessible(true);return f.get(target);
    }
    private <T>T owner(Callable<T> action)throws Exception{
        ExecutorService worker=(ExecutorService)field(activity,"worker");
        corruptValue("sdk_owner_available",worker!=null&&!worker.isShutdown()?1:0);
        need(worker!=null&&!worker.isShutdown(),"actual SDK owner available");
        T value=worker.submit(action).get(45,TimeUnit.SECONDS);
        if(value instanceof Integer)corruptValue("sdk_book_count",((Integer)value).longValue());
        return value;
    }
    private BookStore store()throws Exception{return (BookStore)field(activity,"store");}
    private AccessibilityNodeInfo find(AccessibilityNodeInfo node,Predicate<AccessibilityNodeInfo> predicate){
        if(node==null)return null;if(predicate.test(node))return node;
        for(int i=0;i<node.getChildCount();i++){
            AccessibilityNodeInfo child=node.getChild(i),result=find(child,predicate);
            if(result!=null){if(result!=child&&child!=null)child.recycle();return result;}
            if(child!=null)child.recycle();
        }return null;
    }
    private boolean act(Predicate<AccessibilityNodeInfo> predicate,java.util.function.Consumer<AccessibilityNodeInfo> action){
        AccessibilityNodeInfo root=getUiAutomation().getRootInActiveWindow(),found=null;if(root==null)return false;
        try{found=find(root,predicate);if(found==null)return false;if(action!=null)action.accept(found);return true;}
        finally{if(found!=null&&found!=root)found.recycle();root.recycle();}
    }
    private void until(Predicate<AccessibilityNodeInfo> predicate,java.util.function.Consumer<AccessibilityNodeInfo> action,long timeout){
        long end=SystemClock.elapsedRealtime()+timeout;
        while(SystemClock.elapsedRealtime()<end){try{if(act(predicate,action))return;}catch(IllegalStateException stale){}SystemClock.sleep(80);}
        corruptValue("wait_timeout_ms",timeout);corruptSnapshot("ui_timeout");
        throw new AssertionError("Actual UI target did not become ready");
    }
    private static String text(AccessibilityNodeInfo node){return node.getText()==null?"":node.getText().toString();}
    private static boolean id(AccessibilityNodeInfo node,String name){String value=node.getViewIdResourceName();return value!=null&&value.endsWith("/"+name);}
    private void tap(AccessibilityNodeInfo node){
        Rect r=new Rect();node.getBoundsInScreen(r);corruptValue("tap_width",r.width());corruptValue("tap_height",r.height());need(r.width()>0&&r.height()>0,"visible UI action");
        if(node.performAction(AccessibilityNodeInfo.ACTION_CLICK))return;
        long t=SystemClock.uptimeMillis();sendPointerSync(MotionEvent.obtain(t,t,MotionEvent.ACTION_DOWN,r.centerX(),r.centerY(),0));sendPointerSync(MotionEvent.obtain(t,t+30,MotionEvent.ACTION_UP,r.centerX(),r.centerY(),0));
    }
    private void click(String value){until(n->n.isEnabled()&&text(n).equalsIgnoreCase(value),this::tap,30000);}
    private void clickTitle()throws Exception{String title=input.getString("title");until(n->n.isEnabled()&&text(n).contains(title),this::tap,30000);}
    private void set(String description,String value){until(n->description.contentEquals(n.getContentDescription()==null?"":n.getContentDescription()),n->{Bundle b=new Bundle();b.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,value);need(n.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,b),"actual field edit");},30000);}
    private void status(String value){corruptStep("wait_integrity_status");until(n->"同步状态".contentEquals(n.getContentDescription()==null?"":n.getContentDescription())&&text(n).contains(value),null,120000);corruptSnapshot("status_matched");}
    private void panel(){click("More");click("同步");until(n->"同步状态".contentEquals(n.getContentDescription()==null?"":n.getContentDescription()),null,30000);}
    private File file(String name){return new File(context.getFilesDir(),name);}
    private void marker(String name)throws Exception{Files.write(file(name).toPath(),new byte[]{1});}
    private void waitFile(String name)throws Exception{long end=SystemClock.elapsedRealtime()+30000;while(SystemClock.elapsedRealtime()<end){if(file(name).isFile())return;SystemClock.sleep(80);}throw new AssertionError("Native request boundary not observed");}
    private File cache()throws Exception{return file("sync-cache/"+input.getString("sha256")+".txt");}
    private void receive()throws Exception{coldCacheMustRemainAbsent();corruptStep("select_title");clickTitle();corruptStep("click_receive");click("接收");corruptSnapshot("receive_clicked");}
    private void mode(String value)throws Exception{
        coldCacheMustRemainAbsent();corruptStep("set_fault_mode");
        Files.deleteIfExists(file("f02-get-blocked").toPath());Files.deleteIfExists(file("f02-get-release").toPath());
        Files.write(file("f02-get-mode").toPath(),value.getBytes(StandardCharsets.UTF_8));
        corruptSnapshot("mode_written");
    }
    private void empty()throws Exception{corruptStep("check_sdk_books");need(owner(()->store().nativeLibrary().books().length)==0,"failed receive cannot import an original");corruptStep("check_cache_absence");need(!cache().exists(),"failed receive cannot publish cache");corruptSnapshot("empty_verified");}
    private void launch(){
        activity=startActivitySync(new Intent(context,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TOP));
        need(activity!=null,"actual target Activity");
    }
    private boolean frame(AccessibilityNodeInfo n){
        try{return id(n,"reader_view")&&n.isVisibleToUser()&&new JSONObject(n.getExtras().getString("exreader.frame","{}")).optString("source_key").equals(input.getString("book_key"));}
        catch(Exception absent){return false;}
    }
    private JSONObject open()throws Exception{
        until(this::frame,null,45000);
        final String[] raw={null};until(this::frame,n->raw[0]=n.getExtras().getString("exreader.frame",""),30000);
        final PageSnapshot[] page={null};runOnMainSync(()->{try{page[0]=(PageSnapshot)field(activity,"current");}catch(Exception e){throw new RuntimeException(e);}});
        need(page[0]!=null&&page[0].bookId>0&&page[0].end>page[0].start&&page[0].sourceKey.equals(input.getString("book_key")),"actual page and original source");
        File dir=file("f02-captures");need(dir.isDirectory()||dir.mkdirs(),"screenshot directory");
        Bitmap image=getUiAutomation().takeScreenshot();need(image!=null,"actual screenshot");
        try(FileOutputStream out=new FileOutputStream(new File(dir,phase+".png"))){need(image.compress(Bitmap.CompressFormat.PNG,100,out),"screenshot encoding");}finally{image.recycle();}
        return new JSONObject().put("book",page[0].bookId).put("reader_visible",1).put("error",false).put("source_key",page[0].sourceKey).put("start",page[0].start).put("end",page[0].end).put("semantic_frame",new JSONObject(raw[0]));
    }
    private String hash(File file)throws Exception{return BookStore.syncFileHash(file,new HostTask(()->false));}
    private void stopHost()throws Exception{
        ExecutorService worker=(ExecutorService)field(activity,"worker");
        runOnMainSync(()->activity.finish());
        long end=SystemClock.elapsedRealtime()+30000;
        while(SystemClock.elapsedRealtime()<end&&(!worker.isTerminated()||NativeSyncProbe.sessions()!=0))SystemClock.sleep(80);
        need(worker.isTerminated()&&NativeSyncProbe.sessions()==0,"SDK worker and native session joined");
        observed.put("sdk_worker_terminated",true).put("native_sessions_after_close",0);
    }
    private JSONObject inspectClosed()throws Exception{
        String expected=input.getString("sha256");long bytes=input.getLong("bytes");
        try(NativeLibrary library=new NativeLibrary(file("library.db").getPath());
            CatalogStore catalog=new CatalogStore(context,file("reader-catalog.db"))){
            NativeLibrary.Book[] books=library.books();need(books.length==1&&books[0].format==NativeLibrary.FORMAT_TXT,"exact one real received TXT");
            long book=books[0].id,count=0;MessageDigest digest=MessageDigest.getInstance("SHA-256");
            try(NativeLibrary.Source source=library.source(book);FileOutputStream out=new FileOutputStream(file("f02-sdk-"+phase+".txt"))){
                byte[] block=new byte[65536];
                for(long at=0;at<source.size;){int n=source.read(at,block,(int)Math.min(block.length,source.size-at));need(n>0&&n<=block.length,"public SDK read");out.write(block,0,n);digest.update(block,0,n);at+=n;count+=n;}
            }
            StringBuilder h=new StringBuilder();for(byte b:digest.digest())h.append(String.format(java.util.Locale.ROOT,"%02x",b&255));
            need(count==bytes&&h.toString().equals(expected),"SDK retained exact Windows original");
            CatalogStore.ShelfBook row=catalog.localShelfTitle(input.getString("title"));
            need(row!=null&&row.sdkBookId==book&&row.key.bookKey.equals(input.getString("book_key")),"actual product mapping");
            return new JSONObject().put("book",book).put("books",books.length).put("bytes",count).put("sha256",h.toString()).put("book_key",row.key.bookKey);
        }
    }
    private void copyCases(long book)throws Exception{
        check("cancelled_copy_has_no_publication",()->owner(()->{
            File directory=file("f02-copy-cancel");HostTask t=new HostTask(()->false);t.cancel();boolean rejected=false;
            try(BookStore.ReaderCopy copy=store().prepareReaderCopy(book,input.getString("sha256"),input.getLong("bytes"),directory,t)){}
            catch(HostTask.Cancelled expected){rejected=true;}need(rejected&&!directory.exists(),"canceled copy has no files");return null;
        }));
        check("abandoned_copy_has_no_publication",()->owner(()->{
            HostTask t=new HostTask(()->false);File staged,published;
            try(BookStore.ReaderCopy copy=store().prepareReaderCopy(book,input.getString("sha256"),input.getLong("bytes"),file("f02-copy-abort"),t)){
                staged=copy.readFile();published=copy.publishedFile();need(staged.isFile()&&!published.exists()&&hash(staged).equals(input.getString("sha256")),"verified unpublished SDK copy");
                t.cancel();boolean refused=false;try{t.check();}catch(HostTask.Cancelled expected){refused=true;}need(refused,"copy preparation preserves cancel window");
            }
            need(!staged.exists()&&!published.exists(),"abandoned copy removed without publication");return null;
        }));
        check("wrong_original_is_refused",()->owner(()->{
            boolean rejected=false;File directory=file("f02-copy-wrong");
            try(BookStore.ReaderCopy copy=store().prepareReaderCopy(book,"0000000000000000000000000000000000000000000000000000000000000000",input.getLong("bytes"),directory,new HostTask(()->false))){}
            catch(java.io.IOException expected){rejected=true;}need(rejected&&!directory.exists(),"wrong original cannot create reader copy");return null;
        }));
    }
    private void online()throws Exception{
        check("strict_sdk342_shared_provider",()->{
            String[] sdk=NativeLibrary.syncIdentity();
            need(sdk.length==4&&sdk[0].equals("3.42.0")&&sdk[1].contains("libexreader.so")&&sdk[1].equals(sdk[2])&&sdk[3].contains("libexreader_host.so"),"strict installed SDK342 provider");
            observed.put("sdk",new JSONArray(Arrays.asList(sdk)));
        });
        check("fresh_activity_empty_sdk_and_mapping",()->{
            launch();until(n->"More shelf actions".contentEquals(n.getContentDescription()==null?"":n.getContentDescription()),null,30000);
            need(owner(()->store().nativeLibrary().books().length)==0&&owner(()->store().localShelfTitle(input.getString("title")))==null,"fresh independent mapping");panel();
        });
        check("actual_sync_scans_sender_wire_without_import",()->{
            click("云盘账号");set("云盘地址",input.getString("root"));set("云盘用户名",input.getString("user"));set("云盘密码",input.getString("password"));click("仅本次使用");status("仅本次使用凭据");
            click("立即同步");status("本轮同步结束");need(owner(()->store().nativeLibrary().books().length)==0,"scan does not import SDK original");
        });
        check("corrupt_original_rejected",()->{prepareColdCache();mode("corrupt");receive();status("完整性校验失败");empty();});
        check("truncated_original_rejected",()->{mode("truncate");receive();status("原件下载未完成");empty();});
        check("cancel_blocked_receive_preserves_empty_library",()->{
            mode("block");receive();waitFile("f02-get-blocked");long before=SystemClock.elapsedRealtime();click("取消同步");need(SystemClock.elapsedRealtime()-before<2000,"cancel remains responsive");marker("f02-get-release");status("已取消");empty();
        });
        check("explicit_receive_imports_exact_original",()->{
            normalDownloadStart();
            receive();status("书籍已接收");need(cache().isFile()&&cache().length()==input.getLong("bytes")&&hash(cache()).equals(input.getString("sha256")),"exact HTTPS cache");
            need(owner(()->store().nativeLibrary().books().length)==1,"real receive imports once");
            normalDownloadEnd();
        });
        check("duplicate_receive_keeps_one_sdk_mapping",()->{duplicateGetStart();receive();status("书籍已接收");need(owner(()->store().nativeLibrary().books().length)==1,"no duplicate SDK book");duplicateGetEnd();});
        check("actual_online_reader",()->{click("关闭");clickTitle();observed.put("open",open());});
        long book=observed.getJSONObject("open").getLong("book");copyCases(book);
        check("closed_host_sdk_original",()->{stopHost();observed.put("sdk_readback",inspectClosed());});
    }
    private void offline()throws Exception{
        check(phase.equals("offline")?"fresh_process_with_server_stopped_cache_removed":"second_process_reuses_verified_reader_copy",()->{
            need(!cache().exists(),"transport cache absent at new process");launch();
            until(n->frame(n)||n.isEnabled()&&text(n).contains(input.optString("title")),n->{if(!frame(n))tap(n);},45000);
        });
        check(phase.equals("offline")?"actual_sdk_backed_offline_reader":"actual_second_offline_reader",()->observed.put("open",open()));
        if(phase.equals("offline"))check("recovered_copy_hash_and_saved_path",()->{
            long book=observed.getJSONObject("open").getLong("book");
            String path=context.getSharedPreferences("host",0).getString("path_"+book,null);
            File copy=file("reader-originals/"+input.getString("sha256")+".txt").getCanonicalFile();
            need(path!=null&&new File(path).getCanonicalFile().equals(copy)&&copy.isFile()&&copy.length()==input.getLong("bytes")&&hash(copy).equals(input.getString("sha256")),"verified reader copy saved after publication");
            String[] leftovers=copy.getParentFile().list((dir,name)->name.startsWith(".reader-"));need(leftovers!=null&&leftovers.length==0,"no staged reader copy left");
            observed.put("reader_copy",new JSONObject().put("path",path).put("bytes",copy.length()).put("sha256",hash(copy)));
        });
        check(phase.equals("offline")?"closed_offline_sdk_original":"closed_second_sdk_original",()->{stopHost();observed.put("sdk_readback",inspectClosed());});
    }
    @Override public void onStart(){
        context=getTargetContext();phase=arguments.getString("phase");Throwable failure=null;Bundle result=new Bundle();
        try{
            AccessibilityServiceInfo service=getUiAutomation().getServiceInfo();service.flags|=AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS;getUiAutomation().setServiceInfo(service);
            need(BuildConfig.READER_SYNC&&BuildConfig.READER_READING,"actual sync/reading host");
            observed.put("runtime_apks",new JSONObject()
                .put("host",new JSONObject().put("sha256",hash(new File(context.getApplicationInfo().sourceDir))))
                .put("test",new JSONObject().put("sha256",hash(new File(getContext().getApplicationInfo().sourceDir)))));
            File incoming=file("f02-input.json");input=new JSONObject(new String(Files.readAllBytes(incoming.toPath()),StandardCharsets.UTF_8));Files.delete(incoming.toPath());
            if("online".equals(phase))online();else if("offline".equals(phase)||"reopen".equals(phase))offline();else throw new AssertionError("Unknown phase");
        }catch(Throwable error){failure=error;failureSnapshot(error);}
        finally{
            try{
                JSONObject report=new JSONObject().put("identity",new JSONObject().put("source",arguments.getString("source")).put("run",Long.parseLong(arguments.getString("run"))).put("attempt",Integer.parseInt(arguments.getString("attempt"))))
                    .put("phase",phase).put("pid",android.os.Process.myPid()).put("uid",android.os.Process.myUid()).put("sdk_version","3.42.0").put("passed",failure==null).put("checks",checks).put("count",checks.length()).put("observed",observed);
                observed.put("corrupt_trace",corruptTrace);
                report.put("active_substep",observingCorrupt()?activeSubstep:"outside_corrupt");
                if(failure!=null)report.put("failure_type",failure.getClass().getSimpleName()).put("active_check",activeCheck);
                if(failure!=null&&observingCorrupt())report.put("failure_observation",failureObservation);
                Files.write(file("f02-report-"+phase+".json").toPath(),report.toString(2).getBytes(StandardCharsets.UTF_8));
                result.putString("stream","F02_ANDROID "+phase+" checks="+checks.length()+" passed="+(failure==null)+"\n");
            }catch(Exception e){result.putString("stream","F02 report could not be written\n");failure=e;}
            finish(failure==null?Activity.RESULT_OK:Activity.RESULT_CANCELED,result);
        }
    }
}
