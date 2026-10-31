// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.accessibilityservice.AccessibilityServiceInfo;
import android.app.Activity;
import android.app.Application;
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
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.function.Consumer;
import java.util.function.Predicate;
import org.json.JSONArray;
import org.json.JSONObject;

/** Real reading-page font workflow. Document activity results are intercepted, not real DocumentsUI. */
public final class FontReaderUiTest extends Instrumentation {
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
        File admittedDatabase=new File(context.getFilesDir(),"library.db");
        if(!admittedDatabase.exists())NativeAdmission.initialize(context,admittedDatabase,NativeAdmission.CREATE);
        books=new JSONObject();try(NativeLibrary library=new NativeLibrary(context,new File(context.getFilesDir(),"library.db"))){
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
    private Wave3Host.Fonts fontsState()throws Exception {
        AtomicReference<Wave3Host.Fonts> value=new AtomicReference<>();AtomicReference<Throwable> error=new AtomicReference<>();CountDownLatch done=new CountDownLatch(1);
        runOnMainSync(()->((MainActivity)readerMonitor.getLastActivity()).fontList(new HostTask(()->false),v->{value.set(v);done.countDown();},e->{error.set(e);done.countDown();}));
        need(done.await(30,TimeUnit.SECONDS),"font state read completed on actual owner");
        if(error.get()!=null)throw new AssertionError("font state read",error.get());need(value.get()!=null,"actual font state available");return value.get();
    }
    private void samePage(JSONObject before,JSONObject after)throws Exception {
        for(String key:new String[]{"book","index","part","path","start","end","anchor_sha256","anchor_kind","preferences_point"})need(String.valueOf(before.get(key)).equals(String.valueOf(after.get(key))),"preserved accepted page "+key+": "+before.opt(key)+" -> "+after.opt(key));
        need(bitmap(before).equals(bitmap(after)),"bad font did not change actual rendered page pixels");
        need(before.getLong("accepted_token")==after.getLong("accepted_token"),"failed font import did not replace the accepted frame");
    }
    private void fontWorkflow()throws Exception {
        check("reader_valid_font_import_select_reopen_changes_pixels",()->{
            open("epub");JSONObject before=frame();String defaultBitmap=bitmap(before);
            need(NativeFonts.live()==0,"default reader has zero local-font leases");
            ActivityMonitor picker=stub(Intent.ACTION_OPEN_DOCUMENT,sandbox("wave3-fixtures/"+input.getString("font_file")));
            try {readerMore("本地字体");described("字体状态","字体仅用于",30000);click("导入字体…");described("字体状态","已导入",60000);need(picker.getHits()==1,"valid font import invokes exactly one intercepted document picker");}
            finally {removeMonitor(picker);}
            until(n->n.isVisibleToUser()&&id(n,"text1")&&text(n).contains(input.optString("font_label")),this::tap,"font row",30000);
            click("使用此字体");described("字体状态","已选择",30000);String selected=fontsState().selected;need(!selected.isEmpty(),"valid font selected in actual owner");
            capture("valid-font-selected-in-reader");closeDialog();samePage(before,frame());need(NativeFonts.live()==0,"selection does not replace current default layout");
            shelf();waitLeases(0,"default reader closed");open("epub");JSONObject changed=frame();
            need(!defaultBitmap.equals(bitmap(changed)),"selected font changes actual rendered pixels after reopen");waitLeases(1,"exactly one live selected-font lease after reopen");
            observations.put(new JSONObject().put("kind","valid-selection").put("before",before).put("after",changed).put("selected",selected).put("lease_count",NativeFonts.live()));capture("valid-font-reading");
        });
        check("reader_bad_font_preserves_noninitial_page_position_font_and_lease",()->{
            pageForward();pageForward();JSONObject before=frame();need(before.getLong("index")>0,"failure scenario is on a noninitial reading page");
            Wave3Host.Fonts fontsBefore=fontsState();need(!fontsBefore.selected.isEmpty(),"failure starts with a selected local font");waitLeases(1,"lease exists before invalid import");
            ActivityMonitor picker=stub(Intent.ACTION_OPEN_DOCUMENT,sandbox("wave3-fixtures/"+input.getString("bad_font_file")));
            try {readerMore("本地字体");described("字体状态","个本地字体",30000);click("导入字体…");described("字体状态","字体未导入",60000);need(picker.getHits()==1,"bad font invokes exactly one intercepted document picker");}
            finally {removeMonitor(picker);}
            need(described("字体状态").contains("原有字体保留"),"explicit rejected-font status retains original font");
            need(present(n->id(n,"text1")&&text(n).contains("使用中")),"selected font remains visibly active");
            need(!present(n->id(n,"text1")&&text(n).contains(input.optString("bad_font_file"))),"rejected font is absent from library");capture("bad-font-rejected-in-reader");
            closeDialog();JSONObject after=frame();samePage(before,after);Wave3Host.Fonts fontsAfter=fontsState();
            need(fontsBefore.selected.equals(fontsAfter.selected),"selected font identity is unchanged");need(fontsBefore.fonts.size()==fontsAfter.fonts.size(),"invalid font adds no library entry");waitLeases(1,"bad import preserves live reader lease");
            observations.put(new JSONObject().put("kind","bad-font-preservation").put("before",before).put("after",after).put("selected_before",fontsBefore.selected).put("selected_after",fontsAfter.selected).put("lease_count",NativeFonts.live()));capture("reader-preserved-after-bad-font");
        });
        check("reader_exit_releases_font_lease_and_reopen_keeps_position",()->{
            JSONObject before=frame();String selected=fontsState().selected;shelf();waitLeases(0,"reader exit releases every local-font lease");
            open("epub");JSONObject after=frame();
            for(String key:new String[]{"book","index","part","path","start","end","anchor_sha256","anchor_kind","preferences_point"})need(String.valueOf(before.get(key)).equals(String.valueOf(after.get(key))),"same-font reopen restores "+key);
            need(bitmap(before).equals(bitmap(after)),"same-font reopen restores page pixels");need(selected.equals(fontsState().selected),"selected font survives exit and reopen");waitLeases(1,"reopen reacquires exactly one lease");capture("font-position-reopened");
            observations.put(new JSONObject().put("kind","exit-reopen").put("before",before).put("after",after));shelf();waitLeases(0,"final exit releases every lease");
        });
    }
    @Override public void onStart(){
        context=getTargetContext();phase="font-reader";Throwable failure=null;Bundle result=new Bundle();
        try {
            AccessibilityServiceInfo service=getUiAutomation().getServiceInfo();readerMonitor=addMonitor(MainActivity.class.getName(),null,false);service.flags|=AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS|AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS;getUiAutomation().setServiceInfo(service);
            need(BuildConfig.READER_WAVE3&&BuildConfig.READER_READING,"formal font-enabled reader build");
            input=new JSONObject(new String(Files.readAllBytes(new File(context.getFilesDir(),"wave3-input.json").toPath()),StandardCharsets.UTF_8));seed();launch();fontWorkflow();
        }catch(Throwable error){failure=error;try{capture("failure");}catch(Throwable ignored){}}
        try {
            boolean passed=failure==null&&failedChecks==0;
            JSONObject report=new JSONObject().put("source_sha",arguments.getString("source_sha")).put("run_id",arguments.getString("run_id")).put("attempt",arguments.getString("attempt")).put("phase",phase).put("pid",android.os.Process.myPid()).put("passed",passed).put("failed_checks",failedChecks).put("checks",checks).put("count",checks.length()).put("observations",observations).put("font_leases",NativeFonts.live()).put("picker_mode","framework ActivityMonitor stub; DocumentsUI not exercised").put("physical_device",false);
            if(failure!=null)report.put("failure_trace",android.util.Log.getStackTraceString(failure));else if(firstFailure!=null)report.put("failure_trace",firstFailure);
            Files.write(new File(context.getFilesDir(),"font-reader-report.json").toPath(),report.toString(2).getBytes(StandardCharsets.UTF_8));result.putString("stream",passed?"FONT_READER_PASS":"FONT_READER_FAIL");finish(passed?Activity.RESULT_OK:Activity.RESULT_CANCELED,result);
        }catch(Exception error){result.putString("shortMsg","Font reader evidence unavailable");finish(Activity.RESULT_CANCELED,result);}
    }
}
