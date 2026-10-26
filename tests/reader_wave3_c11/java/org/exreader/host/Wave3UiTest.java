// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.accessibilityservice.AccessibilityServiceInfo;
import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.graphics.Bitmap;
import android.graphics.Rect;
import android.net.Uri;
import android.os.Bundle;
import android.os.SystemClock;
import android.view.MotionEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityWindowInfo;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.function.Consumer;
import java.util.function.Predicate;
import org.json.JSONArray;
import org.json.JSONObject;

/** Real MainActivity controls over the five reviewed modules; pickers return real private-file URIs through the framework. */
public final class Wave3UiTest extends Instrumentation {
    private Bundle arguments;private Context context;private JSONObject input,books;private ActivityMonitor readerMonitor;
    private final JSONArray checks=new JSONArray(),observations=new JSONArray();private String phase,active;
    interface Check {void run()throws Exception;}
    @Override public void onCreate(Bundle args){super.onCreate(args);arguments=args;start();}
    static void need(boolean condition,String message){if(!condition)throw new AssertionError(message);}
    private String firstFailure,firstFailedCheck;private int failedChecks;
    /** Each check records its own real outcome; one failure never hides the rest. */
    private void check(String name,Check action){
        active=name;Bundle report=new Bundle();report.putString("class",getClass().getName());report.putString("test",name);sendStatus(1,report);
        try{
            action.run();
            checks.put(new JSONObject().put("name",name).put("pass",true));
        }catch(Throwable error){
            failedChecks++;
            try{checks.put(new JSONObject().put("name",name).put("pass",false).put("failure_class",error.getClass().getName()).put("failure",error.getMessage()==null?"":error.getMessage()));}catch(Exception ignored){}
            if(firstFailure==null){firstFailedCheck=name;firstFailure=android.util.Log.getStackTraceString(error);}
            try{capture("failure-"+name);}catch(Throwable captureError){error.addSuppressed(captureError);}
            android.util.Log.i("EXRWave3","check failed "+name+": "+error);
        }
        sendStatus(0,report);
    }
    private AccessibilityNodeInfo find(AccessibilityNodeInfo node,Predicate<AccessibilityNodeInfo> match){
        if(node==null)return null;if(match.test(node))return node;
        for(int i=0;i<node.getChildCount();i++){AccessibilityNodeInfo child=node.getChild(i),found=find(child,match);if(found!=null){if(found!=child&&child!=null)child.recycle();return found;}if(child!=null)child.recycle();}return null;
    }
    private boolean act(Predicate<AccessibilityNodeInfo> match,Consumer<AccessibilityNodeInfo> action){
        AccessibilityNodeInfo root=getUiAutomation().getRootInActiveWindow(),found=null;if(root==null)return false;
        try{found=find(root,match);if(found==null)return false;if(action!=null)action.accept(found);return true;}
        finally{if(found!=null&&found!=root)found.recycle();root.recycle();}
    }
    private void until(Predicate<AccessibilityNodeInfo> match,Consumer<AccessibilityNodeInfo> action,String label,long timeout){
        long end=SystemClock.elapsedRealtime()+timeout;while(SystemClock.elapsedRealtime()<end){try{if(act(match,action))return;}catch(IllegalStateException stale){}SystemClock.sleep(80);}throw new AssertionError("UI expected "+label+" in "+active);
    }
    private boolean present(Predicate<AccessibilityNodeInfo> match){try{return act(match,null);}catch(IllegalStateException stale){return false;}}
    static String text(AccessibilityNodeInfo node){return node.getText()==null?"":node.getText().toString();}
    static boolean id(AccessibilityNodeInfo node,String value){return node.getViewIdResourceName()!=null&&node.getViewIdResourceName().endsWith("/"+value);}
    static boolean description(AccessibilityNodeInfo node,String value){return value.contentEquals(node.getContentDescription()==null?"":node.getContentDescription());}
    private void tap(AccessibilityNodeInfo node){
        if(node.performAction(AccessibilityNodeInfo.ACTION_CLICK))return;Rect rect=new Rect();node.getBoundsInScreen(rect);need(rect.width()>0&&rect.height()>0,"visible click target");
        long now=SystemClock.uptimeMillis();sendPointerSync(MotionEvent.obtain(now,now,MotionEvent.ACTION_DOWN,rect.centerX(),rect.centerY(),0));sendPointerSync(MotionEvent.obtain(now,now+30,MotionEvent.ACTION_UP,rect.centerX(),rect.centerY(),0));
    }
    private void longTap(AccessibilityNodeInfo node){
        if(node.performAction(AccessibilityNodeInfo.ACTION_LONG_CLICK))return;Rect rect=new Rect();node.getBoundsInScreen(rect);need(rect.width()>0&&rect.height()>0,"visible long-press target");
        long now=SystemClock.uptimeMillis();sendPointerSync(MotionEvent.obtain(now,now,MotionEvent.ACTION_DOWN,rect.centerX(),rect.centerY(),0));SystemClock.sleep(900);sendPointerSync(MotionEvent.obtain(now,SystemClock.uptimeMillis(),MotionEvent.ACTION_UP,rect.centerX(),rect.centerY(),0));
    }
    private void click(String label){until(node->node.isVisibleToUser()&&node.isEnabled()&&text(node).equalsIgnoreCase(label),this::tap,"click "+label,30000);}
    private void clickId(String value){until(node->id(node,value)&&node.isVisibleToUser()&&node.isEnabled(),this::tap,"click "+value,30000);}
    private void disabled(String label){until(node->node.isVisibleToUser()&&!node.isEnabled()&&text(node).equalsIgnoreCase(label),null,"disabled "+label,15000);}
    private String described(String value){String[] out={null};act(node->description(node,value),node->out[0]=text(node));return out[0];}
    private void described(String value,String contains,long timeout){
        try{until(node->description(node,value)&&text(node).contains(contains),null,value+" containing "+contains,timeout);}
        catch(AssertionError missing){String observed;try{observed=described(value);}catch(Throwable unreadable){observed="<unreadable "+unreadable.getClass().getSimpleName()+">";}
            throw new AssertionError(missing.getMessage()+"; observed "+value+"="+(observed==null?"<absent>":observed));}
    }
    private void setText(String value,String field){until(node->description(node,field)&&node.isEnabled(),node->{Bundle args=new Bundle();args.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,value);need(node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,args),"set "+field);},"set "+field,30000);}
    private JSONObject frame()throws Exception {
        List<AccessibilityWindowInfo> windows=getUiAutomation().getWindows();try{for(AccessibilityWindowInfo window:windows){
            AccessibilityNodeInfo root=window.getRoot(),node=null;
            try{node=find(root,value->id(value,"reader_view"));if(node!=null){String value=node.getExtras().getString("exreader.frame","");if(!value.isEmpty())return new JSONObject(value);}}
            finally{if(node!=null&&node!=root)node.recycle();if(root!=null)root.recycle();}
        }}finally{for(AccessibilityWindowInfo window:windows)window.recycle();}
        AtomicReference<String> observed=new AtomicReference<>();
        runOnMainSync(()->{Activity activity=readerMonitor.getLastActivity();if(activity!=null){android.view.View view=activity.findViewById(org.exreader.host.R.id.reader_view);if(view!=null){AccessibilityNodeInfo info=view.createAccessibilityNodeInfo();try{observed.set(info.getExtras().getString("exreader.frame",""));}finally{info.recycle();}}}});
        String actual=observed.get();if(actual!=null&&!actual.isEmpty())return new JSONObject(actual);
        throw new AssertionError("actual ReaderView frame unavailable");
    }
    private JSONObject waitFrame(long book)throws Exception {long end=SystemClock.elapsedRealtime()+120000;while(SystemClock.elapsedRealtime()<end){try{JSONObject value=frame();if(value.optLong("book",-1)==book&&value.has("bitmap_identity"))return value;}catch(AssertionError notReady){}SystemClock.sleep(80);}throw new AssertionError("real book frame not ready");}
    private String bitmap(JSONObject frame)throws Exception{return frame.getJSONObject("bitmap_identity").getString("logical_argb_sha256");}
    private void launch(){context.startActivity(new Intent(context,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TOP));}
    private long book(String role)throws Exception{return books.getJSONObject(role).getLong("id");}
    private void shelf()throws Exception {
        long end=SystemClock.elapsedRealtime()+30000;boolean clicked=false;
        while(SystemClock.elapsedRealtime()<end){
            if(present(node->node.isVisibleToUser()&&id(node,"import_button")))return;
            try{if(!clicked)clicked=act(node->id(node,"back_button")&&node.isVisibleToUser()&&node.isEnabled(),this::tap);}catch(IllegalStateException stale){}
            SystemClock.sleep(80);
        }
        throw new AssertionError("UI expected shelf in "+active);
    }
    private void open(String role)throws Exception {
        shelf();String title=books.getJSONObject(role).getString("title");
        until(node->node.isEnabled()&&(text(node).equals(title)||text(node).startsWith(title+"\n")),this::tap,"book "+title,30000);waitFrame(book(role));
    }
    private void readerMore(String item){until(node->description(node,"阅读更多操作")&&node.isEnabled(),this::tap,"reading More",30000);click(item);}
    private void shelfMore(String item){until(node->id(node,"more_button")&&node.isEnabled(),this::tap,"shelf More",30000);click(item);}
    private void pageForward()throws Exception {long token=frame().optLong("accepted_token",-1);until(node->id(node,"reader_view")&&node.isEnabled(),node->need(node.performAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD),"page forward action"),"reader page forward",30000);settledFrame(token);}
    private void settledFrame(long previous)throws Exception {long end=SystemClock.elapsedRealtime()+60000;while(SystemClock.elapsedRealtime()<end){try{if(frame().optLong("accepted_token",-1)!=previous)return;}catch(AssertionError notReady){}SystemClock.sleep(80);}throw new AssertionError("page did not change");}
    private static String hash(File file)throws Exception {
        MessageDigest digest=MessageDigest.getInstance("SHA-256");try(java.io.FileInputStream in=new java.io.FileInputStream(file)){byte[] chunk=new byte[65536];for(int count;(count=in.read(chunk))>0;)digest.update(chunk,0,count);}
        StringBuilder out=new StringBuilder();for(byte value:digest.digest())out.append(String.format(Locale.ROOT,"%02x",value&255));return out.toString();
    }
    private int format(String value){switch(value){case "txt":return NativeLibrary.FORMAT_TXT;case "epub":return NativeLibrary.FORMAT_EPUB;case "pdf":return NativeLibrary.FORMAT_PDF;default:throw new AssertionError("fixture format");}}
    private void seed()throws Exception {
        books=new JSONObject();try(NativeLibrary library=new NativeLibrary(new File(context.getFilesDir(),"library.db").getAbsolutePath())){
            JSONArray originals=input.getJSONArray("books");for(int i=0;i<originals.length();i++){
                JSONObject row=originals.getJSONObject(i);File file=new File(context.getFilesDir(),"wave3-fixtures/"+row.getString("file"));need(file.length()==row.getLong("bytes"),"seed original length");
                NativeLibrary.ImportResult result=library.importFile(file.getAbsolutePath(),format(row.getString("format")),row.getString("title"));
                String title=null;for(NativeLibrary.Book found:library.books())if(found.id==result.id)title=found.title;
                need(title!=null,"SDK book after import");books.put(row.getString("role"),new JSONObject().put("id",result.id).put("title",title).put("sha256",row.getString("sha256")).put("format",row.getString("format")));
                need(context.getSharedPreferences("host",0).edit().putString("path_"+result.id,file.getAbsolutePath()).putLong("size_"+result.id,file.length()).commit(),"host original path registered");
            }
        }
        Files.write(new File(context.getFilesDir(),"wave3-books.json").toPath(),books.toString().getBytes(StandardCharsets.UTF_8));
    }
    private int count(String table)throws Exception {
        try(SQLiteDatabase product=SQLiteDatabase.openDatabase(new File(context.getFilesDir(),"reader-catalog.db").getAbsolutePath(),null,SQLiteDatabase.OPEN_READONLY);Cursor cursor=product.rawQuery("SELECT COUNT(*) FROM "+table,null)){cursor.moveToFirst();return cursor.getInt(0);}
    }
    private String syncRows()throws Exception {
        JSONObject result=new JSONObject();try(SQLiteDatabase db=SQLiteDatabase.openDatabase(new File(context.getFilesDir(),"reader-catalog.db").getAbsolutePath(),null,SQLiteDatabase.OPEN_READONLY)){
            for(String table:new String[]{"reader_revisions","reader_outbox"}){JSONArray rows=new JSONArray();try(Cursor cursor=db.rawQuery("SELECT * FROM "+table+" ORDER BY revision_id",null)){while(cursor.moveToNext()){JSONArray row=new JSONArray();for(int i=0;i<cursor.getColumnCount();i++)row.put(cursor.isNull(i)?JSONObject.NULL:cursor.getString(i));rows.put(row);}}result.put(table,rows);}
        }return result.toString();
    }
    private int annotationCount()throws Exception {
        try(SQLiteDatabase product=SQLiteDatabase.openDatabase(new File(context.getFilesDir(),"reader-catalog.db").getAbsolutePath(),null,SQLiteDatabase.OPEN_READONLY);
            Cursor cursor=product.rawQuery("SELECT COUNT(*) FROM reader_revisions WHERE entity_kind='annotation'",null)){cursor.moveToFirst();return cursor.getInt(0);}
    }
    private String sdkState()throws Exception {
        JSONArray rows=new JSONArray();try(NativeLibrary library=new NativeLibrary(new File(context.getFilesDir(),"library.db").getAbsolutePath())){
            NativeLibrary.Book[] items=library.books();java.util.Arrays.sort(items,(a,b)->Long.compare(a.id,b.id));
            for(NativeLibrary.Book value:items){JSONObject row=new JSONObject().put("id",value.id).put("title",value.title).put("position",value.position);
                if(!value.fixed()&&!(value.format==NativeLibrary.FORMAT_EPUB&&library.bounded(value.id)))row.put("progress",new JSONArray(library.progress(value.id)));
                if(!value.fixed())row.put("notes",library.notes(value.id).length);rows.put(row);}
        }
        return rows.toString();
    }
    private ActivityMonitor stub(String action,Uri result)throws Exception {
        IntentFilter filter=new IntentFilter(action);filter.addCategory(Intent.CATEGORY_OPENABLE);filter.addDataType("*/*");
        return addMonitor(filter,new ActivityResult(Activity.RESULT_OK,new Intent().setData(result)),true);
    }
    private Uri sandbox(String name){return Uri.fromFile(new File(context.getFilesDir(),name));}
    private void capture(String name)throws Exception {
        Bitmap image=getUiAutomation().takeScreenshot();need(image!=null,"wave3 screenshot");File folder=new File(context.getFilesDir(),"wave3-captures");need(folder.isDirectory()||folder.mkdirs(),"captures directory");
        try(FileOutputStream output=new FileOutputStream(new File(folder,name+".png"))){need(image.compress(Bitmap.CompressFormat.PNG,100,output),"PNG written");}finally{image.recycle();}
        observations.put(new JSONObject().put("name",name));
    }
    private void waitLeases(int expected,String label)throws Exception {long end=SystemClock.elapsedRealtime()+30000;while(SystemClock.elapsedRealtime()<end){if(NativeFonts.live()==expected)return;SystemClock.sleep(50);}throw new AssertionError(label+": live font leases "+NativeFonts.live()+" expected "+expected);}
    private void closeDialog(){click("关闭");}
    /** Drops a panel an earlier check left open so this check observes its own subject. */
    private void settle(){for(int attempt=0;attempt<2;attempt++){if(!present(node->node.isVisibleToUser()&&node.isEnabled()&&text(node).equals("关闭")))return;click("关闭");SystemClock.sleep(300);}}
    /** Real debug launch flags on the existing Activity, as the frozen review driver does. */
    private void configure(String flags)throws Exception{getUiAutomation().executeShellCommand("am start --activity-single-top -n "+context.getPackageName()+"/.MainActivity --ez exr_review true "+flags);SystemClock.sleep(400);}
    private String byId(String value){String[] out={null};act(node->id(node,value),node->out[0]=text(node));return out[0];}
    private ReadingPreferences appearance()throws Exception{ReadingPreferences[] out={null};runOnMainSync(()->{Activity activity=readerMonitor.getLastActivity();if(activity instanceof MainActivity)out[0]=((MainActivity)activity).preferences();});need(out[0]!=null,"in-memory reading appearance available");return out[0];}
    private byte[] storedAppearance()throws Exception{File file=new File(new File(context.getFilesDir(),"reading-settings"),"preferences.json");return Files.exists(file.toPath())?Files.readAllBytes(file.toPath()):new byte[0];}
    interface HostCall<T> {void begin(MainActivity host,Consumer<T> done,Consumer<Throwable> failed);}
    private <T> T hostCall(HostCall<T> action)throws Exception {
        AtomicReference<T> result=new AtomicReference<>();AtomicReference<Throwable> failure=new AtomicReference<>();CountDownLatch finished=new CountDownLatch(1);
        runOnMainSync(()->action.begin((MainActivity)readerMonitor.getLastActivity(),value->{result.set(value);finished.countDown();},error->{failure.set(error);finished.countDown();}));
        need(finished.await(120,TimeUnit.SECONDS),"actual host owner call completed");
        if(failure.get()!=null)throw new AssertionError("actual host call failed",failure.get());
        return result.get();
    }

    private void annotationCancellation()throws Exception {
        check("annotation_batch_cancel_retains_committed_receipt_and_stops_remaining_items",()->{
            open("txt");File staged=new File(context.getFilesDir(),"wave3-fixtures/annotations.jsonl");long selected=book("txt");
            NativeWave3.ImportResult preview=hostCall((host,done,failed)->host.annotationImport(selected,staged,false,"",new HostTask(()->false),done,failed));
            need(preview.ok()&&preview.wouldCreate>=2&&preview.found>0,"real FOUND preview offers a multi-item batch: status="+preview.status+" reason="+preview.message+" heads="+preview.heads+" new="+preview.wouldCreate+" found="+preview.found+" unresolved="+preview.unresolved+" nulls="+preview.nulls);
            boolean genuine=false;for(NativeWave3.ImportItem item:preview.items)if(item.found==NativeWave3.FOUND_YES&&item.kind.equals("annotation"))genuine=true;
            need(genuine,"at least one nonNULL annotation selector resolves through the real SDK FOUND callback");
            int baseline=count("reader_revisions");HostTask task=new HostTask(()->{try{return count("reader_revisions")>baseline;}catch(Exception error){throw new IllegalStateException(error);}});
            NativeWave3.ImportResult result=hostCall((host,done,failed)->host.annotationImport(selected,staged,true,preview.fingerprint,task,done,failed));
            need(result.status==NativeWave3.AI_CANCELLED,"batch observes cancellation after the first committed revision");
            need(result.committed>0&&result.created>0&&result.nextIndex>0&&result.nextIndex<preview.heads,"receipt retains committed prefix and an unprocessed suffix");
            need(count("reader_revisions")>baseline,"already committed records survive cancellation");
            long committedItems=0;for(NativeWave3.ImportItem item:result.items)if(item.committed)committedItems++;
            need(committedItems==result.committed,"per-item receipt agrees with retained committed count");
        });
    }

    private void staleJump()throws Exception {
        check("closed_panel_drops_real_pending_jump_peek_on_owner",()->{
            NativeWave3.Move move=hostCall((host,done,failed)->host.jumpMove(bookUnchecked("txt"),NativeWave3.BACK,new HostTask(()->false),done,failed));
            need(move.navigable()&&move.token!=0,"real public FOUND owns a pending jump token");
            NativeWave3.State pending=hostCall((host,done,failed)->host.jumpState(new HostTask(()->false),done,failed));need(pending.outstanding==1,"real copied peek remains pending before stale delivery");
            java.lang.reflect.Field field=MainActivity.class.getDeclaredField("jumpPanel");field.setAccessible(true);AtomicReference<Throwable> failure=new AtomicReference<>();
            runOnMainSync(()->{try{MainActivity host=(MainActivity)readerMonitor.getLastActivity();JumpPanel panel=(JumpPanel)field.get(host);panel.show(bookUnchecked("txt"));long stamp=panel.request();panel.close();panel.post(stamp,()->failure.set(new AssertionError("stale jump callback reached closed UI")),()->host.dropJump(move));}catch(Throwable error){failure.set(error);}});
            if(failure.get()!=null)throw new AssertionError(failure.get());
            NativeWave3.State released=hostCall((host,done,failed)->host.jumpState(new HostTask(()->false),done,failed));need(released.outstanding==0,"stale UI delivery released token on existing product owner");
            need(released.cursor==pending.cursor&&released.count==pending.count,"dropping stale peek does not move history");
        });
    }
    private long bookUnchecked(String role){try{return book(role);}catch(Exception error){throw new IllegalStateException(error);}}

    private void cancellationBoundaries()throws Exception {
        check("stage_cancel_before_and_after_rename_removes_private_files",()->{
            File source=new File(context.getFilesDir(),"wave3-fixtures/not-a-font.txt");
            for(int boundary:new int[]{2,3}) {
                File directory=new File(context.getFilesDir(),"stage-cancel-"+boundary);need(directory.mkdirs(),"fresh private staging directory");
                int[] checks={0};HostTask task=new HostTask(()->++checks[0]>=boundary);
                try {Wave3Files.stage(context.getContentResolver(),Uri.fromFile(source),directory,".font",1048576,task);throw new AssertionError("stage ignored cancellation");}
                catch(HostTask.Cancelled expected) {need(checks[0]==boundary,"exact EOF/rename cancellation boundary");}
                File[] remaining=directory.listFiles();need(remaining!=null&&remaining.length==0,"cancelled staging retained neither .part nor renamed file");
            }
        });
        check("original_export_cancel_receipt_and_ordinary_exception_under_checkjni",()->{
            JSONObject original=input.getJSONArray("books").getJSONObject(0);
            File source=new File(context.getFilesDir(),"wave3-fixtures/"+original.getString("file"));
            try(NativeLibrary library=new NativeLibrary(new File(context.getFilesDir(),"cancel-export.db").getAbsolutePath())) {
                long selected=library.importFile(source.getAbsolutePath(),format(original.getString("format")),"Cancellation original").id;
                File directory=new File(context.getFilesDir().getCanonicalFile(),"cancel-export");need(directory.mkdirs(),"fresh export directory");
                NativeOriginalExport.Result cancelled=NativeOriginalExport.export(library.checked(),new long[]{selected},directory.getAbsolutePath(),new HostTask(()->true));
                need(cancelled.status==NativeOriginalExport.CANCELLED,"cooperative cancellation returns the real receipt: status="+cancelled.status+" items="+cancelled.items.length+" format="+original.getString("format"));
                for(NativeOriginalExport.Item item:cancelled.items)need(!item.committed,"cancel before processing committed no item");
                RuntimeException sentinel=new RuntimeException("ordinary cancellation callback failure");
                try {NativeOriginalExport.export(library.checked(),new long[]{selected},directory.getAbsolutePath(),new HostTask(()->{throw sentinel;}));throw new AssertionError("ordinary exception was swallowed");}
                catch(RuntimeException actual) {need(actual==sentinel,"ordinary Java exception identity preserved across JNI");}
                JSONObject second=input.getJSONArray("books").getJSONObject(1);File secondSource=new File(context.getFilesDir(),"wave3-fixtures/"+second.getString("file"));
                long next=library.importFile(secondSource.getAbsolutePath(),format(second.getString("format")),"Second cancellation original").id;
                File published=new File(directory,original.getString("sha256")+"."+original.getString("format"));
                NativeOriginalExport.Result partial=NativeOriginalExport.export(library.checked(),new long[]{selected,next},directory.getAbsolutePath(),new HostTask(published::isFile));
                need(partial.status==NativeOriginalExport.CANCELLED&&partial.items.length==2,"second item cancellation returns both original receipts");
                need(partial.items[0].saved()&&partial.items[0].book==selected&&partial.items[0].bytes==original.getLong("bytes")&&partial.items[0].sha.equals(original.getString("sha256")),"completed first original keeps its committed receipt and identity");
                need(partial.items[1].book==next&&partial.items[1].status==NativeOriginalExport.CANCELLED&&!partial.items[1].committed,"remaining original is cancelled before publication");
                need(published.isFile()&&hash(published).equals(original.getString("sha256")),"first complete original survives batch cancellation byte for byte");
            }
        });
    }

    private void fonts()throws Exception {
        File font=new File(context.getFilesDir(),"wave3-fixtures/"+input.getString("font_file"));need(font.isFile(),"font fixture present");
        String fontLabel=input.getString("font_label"),badFontFile=input.getString("bad_font_file");
        check("wave3_surfaces_present_and_no_leases",()->{
            need(BuildConfig.READER_WAVE3&&BuildConfig.READER_SELECTOR_BYTES_CANDIDATE&&BuildConfig.READER_SYNC&&BuildConfig.READER_READING,"formal wave3 feature build");
            need(NativeFonts.live()==0,"no font lease before any layout");
            shelf();
            until(node->id(node,"more_button")&&node.isEnabled(),this::tap,"shelf More",30000);need(present(node->text(node).equals("本地字体")),"本地字体 menu item");need(present(node->text(node).equals("同步")),"同步 menu item");
            getUiAutomation().performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK);
        });
        check("local_font_saf_import_select_lease_and_release",()->{
            open("epub");String defaultBitmap=bitmap(frame());need(NativeFonts.live()==0,"bundled font holds no local-font lease");
            shelf();
            ActivityMonitor picker=stub(Intent.ACTION_OPEN_DOCUMENT,sandbox("wave3-fixtures/"+input.getString("font_file")));
            shelfMore("本地字体");described("字体状态","字体仅用于",30000);click("导入字体…");
            described("字体状态","已导入",60000);removeMonitor(picker);need(picker.getHits()>=1,"system document picker was invoked");
            capture("font-imported");
            until(node->node.isVisibleToUser()&&id(node,"text1")&&text(node).contains(fontLabel),this::tap,"imported font row",30000);click("使用此字体");described("字体状态","已选择",30000);
            closeDialog();need(NativeFonts.live()==0,"selection alone holds no lease");
            open("epub");String fontBitmap=bitmap(frame());need(!fontBitmap.equals(defaultBitmap),"selected local font changes the real page pixels");
            need(NativeFonts.live()>=1,"paging layout borrows the selected font lease");capture("font-reading");
            shelf();waitLeases(0,"leaving the reader releases every lease");
        });
        check("invalid_font_rejected_and_library_unchanged",()->{
            ActivityMonitor picker=stub(Intent.ACTION_OPEN_DOCUMENT,sandbox("wave3-fixtures/"+input.getString("bad_font_file")));
            shelfMore("本地字体");described("字体状态","个本地字体",30000);String before=described("字体状态");click("导入字体…");described("字体状态","字体未导入",60000);removeMonitor(picker);
            need(described("字体状态").contains("原有字体保留"),"previous fonts retained");need(!present(node->id(node,"text1")&&text(node).contains(badFontFile)),"rejected file is not listed");
            need(present(node->id(node,"text1")&&text(node).contains("使用中")),"selected font still active");capture("font-rejected");closeDialog();
        });
    }
    /** The quick size control publishes page, progress and stored appearance together. */
    private void quickSize()throws Exception {
        check("quick_size_cancel_keeps_accepted_frame_and_stored_appearance",()->{
            settle();open("epub");String accepted=bitmap(frame());String label=byId("font_label");
            ReadingPreferences before=appearance();byte[] stored=storedAppearance();
            configure("--es review_pause page-before-render");
            clickId("font_up");
            until(node->id(node,"loading_text")&&text(node).equals("Review page-before-render"),null,"size request gate",30000);
            clickId("cancel_button");
            until(node->id(node,"reader_status")&&text(node).contains("Operation canceled"),null,"size cancellation",30000);
            configure("");
            need(appearance().font==before.font,"cancelled request kept the in-memory size: "+appearance().font+" expected "+before.font);
            need(java.util.Arrays.equals(stored,storedAppearance()),"cancelled request kept the stored appearance bytes");
            need(bitmap(frame()).equals(accepted),"cancelled request kept the accepted page");
            need(label!=null&&label.equals(byId("font_label")),"cancelled request kept the reported size: "+label+" -> "+byId("font_label"));
            capture("size-cancelled");shelf();waitLeases(0,"leaving after a cancelled size request releases every lease");
        });
        check("quick_size_settings_failure_keeps_frame_and_stored_appearance",()->{
            settle();open("epub");String accepted=bitmap(frame());String label=byId("font_label");
            ReadingPreferences before=appearance();byte[] stored=storedAppearance();
            configure("--ez review_fail_preferences true");
            clickId("font_up");
            until(node->id(node,"reader_status")&&text(node).contains("Reading settings were not saved"),null,"settings save failure",60000);
            configure("");
            need(appearance().font==before.font,"failed save kept the in-memory size: "+appearance().font+" expected "+before.font);
            need(java.util.Arrays.equals(stored,storedAppearance()),"failed save kept the stored appearance bytes");
            need(bitmap(frame()).equals(accepted),"failed save kept the accepted page");
            need(label!=null&&label.equals(byId("font_label")),"failed save kept the reported size: "+label+" -> "+byId("font_label"));
            capture("size-save-failed");shelf();waitLeases(0,"leaving after a failed size save releases every lease");
        });
    }
    private void originals()throws Exception {
        check("original_export_private_original_receipt_and_saf_save",()->{
            shelf();JSONObject epub=books.getJSONObject("epub");String title=epub.getString("title");
            until(node->node.isEnabled()&&(text(node).equals(title)||text(node).startsWith(title+"\n")),this::longTap,"long press "+title,30000);click("导出原件");
            described("原件导出状态","✓",120000);String receipt=described("原件导出状态");need(receipt.contains("SHA-256 "+epub.getString("sha256").substring(0,12)),"per-item receipt carries the original identity");
            File exported=null;File[] produced=new File(context.getFilesDir().getCanonicalFile(),"original-export").listFiles();need(produced!=null,"private export directory");for(File candidate:produced)if(candidate.isFile()&&candidate.getName().toLowerCase(Locale.ROOT).endsWith(".epub")&&hash(candidate).equals(epub.getString("sha256")))exported=candidate;need(exported!=null,"complete private original equals the fixture byte for byte");
            capture("original-receipt");
            File sink=new File(context.getFilesDir(),"wave3-sink/original.epub");sink.getParentFile().mkdirs();sink.delete();
            ActivityMonitor creator=stub(Intent.ACTION_CREATE_DOCUMENT,Uri.fromFile(sink));click("保存到…");described("原件导出状态","已保存",60000);removeMonitor(creator);
            need(creator.getHits()>=1&&sink.isFile()&&hash(sink).equals(epub.getString("sha256")),"SAF destination equals the private original");need(exported.isFile()&&hash(exported).equals(epub.getString("sha256")),"private original retained after save");closeDialog();
        });
    }
    private void bookmark(String body)throws Exception {readerMore("阅读记录");click("添加书签");setText(body,"阅读记录文字");click("保存");described("阅读记录状态","已保存",60000);closeDialog();}
    private void annotations()throws Exception {
        check("annotation_export_private_files_and_saf_save",()->{
            open("txt");bookmark("wave3 bookmark one");pageForward();bookmark("wave3 bookmark two");
            readerMore("标注导入 / 导出");click("导出标注");described("标注状态","已形成",120000);String status=described("标注状态");need(status.contains("条标注"),"export statistics shown");
            String sha=books.getJSONObject("txt").getString("sha256");File jsonl=new File(context.getFilesDir().getCanonicalFile(),"annotation-export/"+sha+"/annotations.jsonl"),markdown=new File(context.getFilesDir().getCanonicalFile(),"annotation-export/"+sha+"/annotations.md");
            need(jsonl.isFile()&&markdown.isFile(),"complete private export files");String json=new String(Files.readAllBytes(jsonl.toPath()),StandardCharsets.UTF_8);need(json.contains("exreader-annotation-export-raw3")&&json.contains("wave3 bookmark"),"portable raw0.2 export format with the actual bookmarks");
            File sink=new File(context.getFilesDir(),"wave3-sink/annotations.jsonl");sink.getParentFile().mkdirs();sink.delete();
            ActivityMonitor creator=stub(Intent.ACTION_CREATE_DOCUMENT,Uri.fromFile(sink));click("保存 JSONL…");described("标注状态","已保存",60000);removeMonitor(creator);
            need(sink.isFile()&&hash(sink).equals(hash(jsonl)),"SAF JSONL equals the private export");capture("annotation-export");closeDialog();
        });
        check("annotation_import_wrong_book_rejected_without_write",()->{
            open("epub");int revisions=count("reader_revisions"),outbox=count("reader_outbox");String sdk=sdkState();
            ActivityMonitor picker=stub(Intent.ACTION_OPEN_DOCUMENT,sandbox("wave3-sink/annotations.jsonl"));readerMore("标注导入 / 导出");click("导入标注文件…");
            described("标注状态","不能导入",120000);removeMonitor(picker);need(picker.getHits()>=1,"picker invoked");capture("annotation-wrong-book");
            need(count("reader_revisions")==revisions&&count("reader_outbox")==outbox&&sdkState().equals(sdk),"rejected import wrote no product revision, outbox row or SDK state");closeDialog();
        });
    }
    private void jumps()throws Exception {
        String query=input.getJSONObject("expected").getString("txt_unique_query");
        check("jump_history_back_forward_over_real_search_landing",()->{
            open("txt");JSONObject first=frame();long firstStart=first.getLong("start");
            readerMore("位置历史");described("位置历史状态","位置",30000);need(present(node->node.isVisibleToUser()&&!node.isEnabled()&&text(node).equals("返回上一位置")),"nothing earlier before any jump");closeDialog();
            readerMore("书内搜索");setText(input.getJSONObject("expected").getString("txt_unique_query"),"书内搜索词");click("搜索");described("搜索状态","1 个结果",120000);
            long token=frame().getLong("accepted_token");until(node->id(node,"text1")&&node.isVisibleToUser()&&node.isEnabled()&&text(node).contains(query),this::tap,"search result",30000);settledFrame(token);
            JSONObject target=waitFrame(book("txt"));long targetStart=target.getLong("start");need(targetStart>firstStart,"search jump landed on a later real page");
            readerMore("位置历史");described("位置历史状态","可返回",30000);String before=described("位置历史状态");need(before.contains("/ 2"),"two real landings recorded: "+before);
            long beforeToken=frame().getLong("accepted_token");click("返回上一位置");settledFrame(beforeToken);JSONObject back=waitFrame(book("txt"));need(back.getLong("start")==firstStart,"back returned to the earlier real page");
            readerMore("位置历史");described("位置历史状态","可前进",30000);need(present(node->node.isVisibleToUser()&&!node.isEnabled()&&text(node).equals("返回上一位置")),"oldest entry has nothing earlier");
            long backToken=frame().getLong("accepted_token");click("前进到下一位置");settledFrame(backToken);JSONObject forward=waitFrame(book("txt"));need(forward.getLong("start")==targetStart,"forward returned to the search landing");
            readerMore("位置历史");described("位置历史状态","可返回",30000);need(present(node->node.isVisibleToUser()&&!node.isEnabled()&&text(node).equals("前进到下一位置")),"newest entry has nothing later");capture("jump-history");closeDialog();
        });
    }
    private void syncView()throws Exception {
        check("sync_status_view_without_session_and_real_failed_session",()->{
            shelf();int revisions=count("reader_revisions"),outbox=count("reader_outbox");String idleBefore=syncRows();
            shelfMore("同步");described("同步状态详情","尚未开始同步",30000);capture("sync-view-idle");
            need(count("reader_revisions")==revisions&&count("reader_outbox")==outbox&&syncRows().equals(idleBefore),"the idle status view did not write, retry or ack");
            click("云盘账号");setText(input.getString("sync_root"),"云盘地址");setText("wave3-user","云盘用户名");setText("wave3-password-not-saved","云盘密码");click("仅本次使用");
            until(node->description(node,"同步状态")&&text(node).contains("仅本次使用"),null,"account kept in memory only",60000);
            click("立即同步");described("同步状态详情","阶段：",120000);
            long end=SystemClock.elapsedRealtime()+120000;String detail="";while(SystemClock.elapsedRealtime()<end){detail=described("同步状态详情");if(detail!=null&&detail.contains("（failed）"))break;SystemClock.sleep(200);}
            need(detail!=null&&detail.contains("（failed）"),"real failed session phase: "+detail);need(detail.contains("原因："),"a fixed safe reason is shown: "+detail);need(detail.contains("待上传记录"),"pending queue read from the real outbox: "+detail);
            need(!detail.contains("wave3-password-not-saved")&&!detail.contains("127.0.0.1"),"view never exposes credentials or the server");capture("sync-view-failed");
            String prepared=syncRows();android.util.Log.i("EXRWave3","sync preparation before="+idleBefore+" after="+prepared+" failure="+detail);
            revisions=count("reader_revisions");outbox=count("reader_outbox");closeDialog();shelfMore("同步");described("同步状态详情","（failed）",30000);click("刷新书目");SystemClock.sleep(1000);
            need(count("reader_revisions")==revisions&&count("reader_outbox")==outbox&&syncRows().equals(prepared),"the failed-session status refresh did not ack, retry or write any revision");closeDialog();
        });
    }
    private void toc()throws Exception {
        check("toc_directory_entry_reaches_real_chapter",()->{
            open("epub");long token=frame().getLong("accepted_token");
            readerMore("目录 / 按页入口");
            described("目录状态","项",120000);
            until(node->node.isVisibleToUser()&&node.isEnabled()&&text(node).contains("Chapter 2"),this::tap,"directory chapter row",30000);
            settledFrame(token);
            until(node->id(node,"reader_status")&&text(node).contains("已跳转到目录目标"),null,"toc landing",60000);
            capture("toc-landing");
        });
    }
    private void rotation()throws Exception {
        String fontLabel=input.getString("font_label");
        check("rotation_keeps_selected_font_and_releases_leases",()->{
            open("epub");String before=bitmap(frame());need(NativeFonts.live()>=1,"selected font leased while reading");
            long token=frame().getLong("accepted_token");getUiAutomation().setRotation(android.view.Surface.ROTATION_90);SystemClock.sleep(1500);
            try{waitLeases(1,"the recreated Activity reopens exactly one lease");waitFrame(book("epub"));}finally{getUiAutomation().setRotation(android.view.Surface.ROTATION_0);}
            SystemClock.sleep(1500);JSONObject after=waitFrame(book("epub"));need(after.optLong("accepted_token",-1)!=token||!bitmap(after).isEmpty(),"reader restored after rotation");
            shelf();waitLeases(0,"leaving after rotation releases every lease");
            shelfMore("本地字体");described("字体状态","使用中",30000);need(present(node->id(node,"text1")&&text(node).contains("使用中")),"selection survived the Activity restart");
            until(node->node.isVisibleToUser()&&id(node,"text1")&&text(node).contains(fontLabel),this::tap,"font row",30000);click("删除此字体");click("删除");described("字体状态","已删除",30000);
            need(!present(node->id(node,"text1")&&text(node).contains(fontLabel)),"removed font no longer listed");closeDialog();
            open("epub");need(bitmap(frame()).equals(before)==false,"default font restored after removal");need(NativeFonts.live()==0,"bundled font after removal holds no lease");
        });
    }
    private void restore()throws Exception {
        check("annotation_preview_confirm_import_creates_records",()->{
            open("txt");int revisions=count("reader_revisions");need(annotationCount()==0,"fresh store: no annotation to duplicate");
            ActivityMonitor picker=stub(Intent.ACTION_OPEN_DOCUMENT,sandbox("wave3-fixtures/annotations.jsonl"));readerMore("标注导入 / 导出");click("导入标注文件…");
            described("标注状态","预览（尚未写入）",120000);removeMonitor(picker);String preview=described("标注状态");need(preview.contains("将新增 2")||preview.contains("将新增 3"),"preview reports what would be created: "+preview);need(java.util.regex.Pattern.compile("位置已确认 [1-9][0-9]*").matcher(preview).find(),"nonNULL selector received a genuine public FOUND: "+preview);
            need(count("reader_revisions")==revisions,"preview wrote nothing");need(present(node->node.isVisibleToUser()&&node.isEnabled()&&text(node).equals("确认导入")),"explicit confirm offered");capture("annotation-preview");
            click("确认导入");described("标注状态","导入完成",120000);String done=described("标注状态");need(done.contains("新增 2")||done.contains("新增 3"),"records created: "+done);
            need(count("reader_revisions")>revisions&&count("reader_outbox")>0,"imported heads are real revisions queued for sync");capture("annotation-imported");closeDialog();
        });
        check("annotation_reimport_all_duplicates_no_new_rows",()->{
            int revisions=count("reader_revisions"),outbox=count("reader_outbox");
            ActivityMonitor picker=stub(Intent.ACTION_OPEN_DOCUMENT,sandbox("wave3-fixtures/annotations.jsonl"));readerMore("标注导入 / 导出");click("导入标注文件…");
            described("标注状态","预览（尚未写入）",120000);removeMonitor(picker);need(described("标注状态").contains("将新增 0"),"nothing new on a repeat: "+described("标注状态"));
            click("确认导入");described("标注状态","导入完成",120000);need(described("标注状态").contains("新增 0"),"exact duplicates create nothing");
            need(count("reader_revisions")==revisions&&count("reader_outbox")==outbox,"repeat import added no revision or outbox row");closeDialog();
        });
        check("tampered_file_rejected_before_any_write",()->{
            int revisions=count("reader_revisions"),outbox=count("reader_outbox");String sdk=sdkState();
            ActivityMonitor picker=stub(Intent.ACTION_OPEN_DOCUMENT,sandbox("wave3-fixtures/annotations-tampered.jsonl"));readerMore("标注导入 / 导出");click("导入标注文件…");
            described("标注状态","不能导入",120000);removeMonitor(picker);need(!present(node->node.isVisibleToUser()&&node.isEnabled()&&text(node).equals("确认导入")),"no confirm offered for a rejected file");
            need(count("reader_revisions")==revisions&&count("reader_outbox")==outbox&&sdkState().equals(sdk),"tampered file wrote nothing");capture("annotation-tampered");closeDialog();
        });
        check("imported_bookmark_navigable_by_public_found",()->{
            readerMore("阅读记录");described("阅读记录状态","条记录",60000);until(node->id(node,"text1")&&node.isVisibleToUser()&&text(node).contains("wave3 bookmark two"),this::tap,"imported bookmark row",30000);
            long token=frame().getLong("accepted_token");click("跳转到此处");settledFrame(token);need(waitFrame(book("txt")).getInt("index")>=1,"imported bookmark navigated to its real page");capture("imported-bookmark");
        });
    }
    @Override public void onStart(){
        context=getTargetContext();phase=arguments.getString("phase");Throwable failure=null;Bundle result=new Bundle();
        try{
            AccessibilityServiceInfo service=getUiAutomation().getServiceInfo();readerMonitor=addMonitor(MainActivity.class.getName(),null,false);service.flags|=AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS|AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS;getUiAutomation().setServiceInfo(service);
            need(BuildConfig.READER_WAVE3,"wave3 feature-on formal app");input=new JSONObject(new String(Files.readAllBytes(new File(context.getFilesDir(),"wave3-input.json").toPath()),StandardCharsets.UTF_8));
            if(phase.equals("first")){seed();cancellationBoundaries();launch();jumps();staleJump();fonts();quickSize();originals();annotations();syncView();rotation();toc();}
            else if(phase.equals("cancel")){seed();launch();annotationCancellation();}
            else if(phase.equals("restore")){seed();launch();restore();}
            else throw new AssertionError("Unknown wave3 UI phase");
        }catch(Throwable error){failure=error;try{capture("failure");}catch(Throwable captureError){error.addSuppressed(captureError);}}
        try{
            boolean passed=failure==null&&failedChecks==0;
            JSONObject report=new JSONObject().put("source_sha",arguments.getString("source_sha")).put("run_id",arguments.getString("run_id")).put("attempt",arguments.getString("attempt")).put("phase",phase).put("pid",android.os.Process.myPid()).put("passed",passed).put("failed_checks",failedChecks).put("checks",checks).put("count",checks.length()).put("observations",observations).put("font_leases",NativeFonts.live());
            if(failure!=null)report.put("failed_check",active).put("failure_class",failure.getClass().getName()).put("failure",failure.getMessage()).put("failure_trace",android.util.Log.getStackTraceString(failure));
            else if(firstFailure!=null)report.put("failed_check",firstFailedCheck).put("failure_trace",firstFailure);
            Files.write(new File(context.getFilesDir(),"wave3-ui-"+phase+".json").toPath(),report.toString(2).getBytes(StandardCharsets.UTF_8));
            result.putString("stream",passed?"WAVE3_UI_PASS "+phase:"WAVE3_UI_FAIL "+phase);finish(passed?Activity.RESULT_OK:Activity.RESULT_CANCELED,result);
        }catch(Exception error){result.putString("shortMsg","Wave3 UI evidence unavailable");finish(Activity.RESULT_CANCELED,result);}
    }
}
