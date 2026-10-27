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

/** Android real system document-creator original save. */
public final class OriginalSaveUiTest extends Instrumentation {
    private Bundle arguments;private Context context;private JSONObject input,books;
    private ActivityMonitor readerMonitor;private String active="original-system-save";
    private final JSONArray checks=new JSONArray();
    @Override public void onCreate(Bundle args){super.onCreate(args);arguments=args;start();}
    static void need(boolean condition,String message){if(!condition)throw new AssertionError(message);}
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

    private static boolean docs(AccessibilityNodeInfo n){return "com.android.documentsui".contentEquals(n.getPackageName()==null?"":n.getPackageName());}
    private void systemTap(AccessibilityNodeInfo n){
        Rect r=new Rect();n.getBoundsInScreen(r);need(r.width()>0&&r.height()>0,"visible system picker target");
        try(java.io.FileInputStream in=new android.os.ParcelFileDescriptor.AutoCloseInputStream(
            getUiAutomation().executeShellCommand("input touchscreen tap "+r.centerX()+" "+r.centerY()));
            java.io.ByteArrayOutputStream out=new java.io.ByteArrayOutputStream()){
            byte[] buffer=new byte[4096];for(int count;(count=in.read(buffer))>0;)out.write(buffer,0,count);
            String reply=out.toString("UTF-8");
            need(!reply.contains("Usage:")&&!reply.contains("Error:"),"system touchscreen input");
        }catch(Exception error){throw new RuntimeException(error);}
    }
    private String savedHash(String name,long expected)throws Exception {
        MessageDigest digest=MessageDigest.getInstance("SHA-256");long total=0;
        try(java.io.FileInputStream in=new android.os.ParcelFileDescriptor.AutoCloseInputStream(
            getUiAutomation().executeShellCommand("cat /sdcard/Download/"+name))){
            byte[] buf=new byte[65536];for(int n;(n=in.read(buf))>0;){digest.update(buf,0,n);total+=n;}
        }
        need(total==expected,"system destination byte count");
        StringBuilder value=new StringBuilder();for(byte b:digest.digest())value.append(String.format(Locale.ROOT,"%02x",b&255));return value.toString();
    }
    private void saveOriginal()throws Exception {
        String run=arguments.getString("run_id","");need(run.matches("[0-9]+"),"run id");
        String filename="exreader-original-"+run+".epub";
        seed();launch();shelf();JSONObject row=books.getJSONObject("epub");String title=row.getString("title");
        until(n->n.isVisibleToUser()&&n.isEnabled()&&(text(n).equals(title)||text(n).startsWith(title+"\n")),this::longTap,"shelf original",60000);
        click("导出原件");described("原件导出状态","✓",120000);click("保存到…");
        until(n->docs(n)&&n.isVisibleToUser(),null,"real DocumentsUI",60000);
        Bitmap shot=getUiAutomation().takeScreenshot();need(shot!=null,"system picker screenshot");
        try(FileOutputStream out=new FileOutputStream(new File(context.getFilesDir(),"real-original-picker.png"))){
            need(shot.compress(Bitmap.CompressFormat.PNG,100,out),"system picker capture");
        }finally{shot.recycle();}
        checks.put(new JSONObject().put("name","real_documentsui_opened").put("pass",true));
        boolean drawer=act(n->docs(n)&&n.isVisibleToUser()&&(description(n,"Show roots")||description(n,"Open navigation drawer")||description(n,"Show navigation drawer")),this::systemTap);
        if(drawer) until(n->docs(n)&&n.isVisibleToUser()&&text(n).equalsIgnoreCase("Downloads"),this::systemTap,"Downloads",30000);
        until(n->docs(n)&&n.isVisibleToUser()&&n.isEditable(),n->{
            Bundle b=new Bundle();b.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,filename);
            need(n.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,b),"set filename");
        },"system filename",30000);
        until(n->docs(n)&&n.isVisibleToUser()&&n.isEnabled()&&text(n).equalsIgnoreCase("Save"),this::systemTap,"system Save",30000);
        described("原件导出状态","已保存",120000);
        need(savedHash(filename,input.getJSONArray("books").getJSONObject(1).getLong("bytes")).equals(row.getString("sha256")),"export bytes match original");
        checks.put(new JSONObject().put("name","system_saved_original_matches_source").put("pass",true));
    }
    @Override public void onStart(){
        context=getTargetContext();Throwable failure=null;
        try{
            AccessibilityServiceInfo service=getUiAutomation().getServiceInfo();readerMonitor=addMonitor(MainActivity.class.getName(),null,false);
            service.flags|=AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS|AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS;getUiAutomation().setServiceInfo(service);
            need(BuildConfig.READER_WAVE3,"wave3 host");input=new JSONObject(new String(Files.readAllBytes(new File(context.getFilesDir(),"wave3-input.json").toPath()),StandardCharsets.UTF_8));saveOriginal();
        }catch(Throwable error){failure=error;}
        try{
            JSONObject report=new JSONObject().put("source_sha",arguments.getString("source_sha")).put("run_id",arguments.getString("run_id"))
                .put("attempt",arguments.getString("attempt")).put("passed",failure==null).put("checks",checks).put("count",checks.length())
                .put("picker","real DocumentsUI Downloads").put("physical_device",false);
            if(failure!=null)report.put("failure_trace",android.util.Log.getStackTraceString(failure));
            Files.write(new File(context.getFilesDir(),"real-original-save.json").toPath(),report.toString(2).getBytes(StandardCharsets.UTF_8));
            Bundle result=new Bundle();result.putString("stream",failure==null?"ORIGINAL_SAVE_PASS":"ORIGINAL_SAVE_FAIL");finish(failure==null?Activity.RESULT_OK:Activity.RESULT_CANCELED,result);
        }catch(Exception error){Bundle result=new Bundle();result.putString("shortMsg","save report unavailable");finish(Activity.RESULT_CANCELED,result);}
    }
}
