// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.app.Activity;
import android.app.Instrumentation;
import android.accessibilityservice.AccessibilityServiceInfo;
import android.content.Context;
import android.content.Intent;
import android.graphics.Rect;
import android.os.Bundle;
import android.os.SystemClock;
import android.view.accessibility.AccessibilityNodeInfo;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.function.Predicate;
import org.json.JSONArray;
import org.json.JSONObject;

/** Only actual app UI mutates originals, accounts and reading records. */
public final class RelayAndroidTest extends Instrumentation {
    private Bundle arguments; private Context context; private JSONObject input;
    private final JSONArray checks=new JSONArray(); private final JSONObject evidence=new JSONObject();
    private String active="initialization";
    interface Work { void run() throws Exception; }
    @Override public void onCreate(Bundle args){super.onCreate(args);arguments=args;start();}
    static void need(boolean value,String label){if(!value)throw new AssertionError(label);}
    private void check(String name,Work work)throws Exception{active=name;work.run();checks.put(new JSONObject().put("name",name).put("pass",true));}
    private static String text(AccessibilityNodeInfo node){return node.getText()==null?"":node.getText().toString();}
    private static boolean id(AccessibilityNodeInfo node,String name){String value=node.getViewIdResourceName();return value!=null&&value.endsWith("/"+name);}
    private static boolean desc(AccessibilityNodeInfo node,String name){return name.contentEquals(node.getContentDescription()==null?"":node.getContentDescription());}
    private AccessibilityNodeInfo find(AccessibilityNodeInfo node,Predicate<AccessibilityNodeInfo> test){
        if(node==null)return null;if(test.test(node))return node;
        for(int n=0;n<node.getChildCount();n++){AccessibilityNodeInfo child=node.getChild(n),found=find(child,test);if(found!=null){if(found!=child&&child!=null)child.recycle();return found;}if(child!=null)child.recycle();}return null;
    }
    private void until(Predicate<AccessibilityNodeInfo> test,java.util.function.Consumer<AccessibilityNodeInfo> action,String label,long timeout){
        long end=SystemClock.elapsedRealtime()+timeout;
        while(SystemClock.elapsedRealtime()<end){AccessibilityNodeInfo root=getUiAutomation().getRootInActiveWindow(),node=null;
            try{node=find(root,test);if(node!=null){if(action!=null)action.accept(node);return;}}
            finally{if(node!=null&&node!=root)node.recycle();if(root!=null)root.recycle();}SystemClock.sleep(100);}
        throw new AssertionError("UI timeout: "+label);
    }
    private void tap(AccessibilityNodeInfo node){Rect bounds=new Rect();node.getBoundsInScreen(bounds);need(bounds.width()>0&&bounds.height()>0,"visible UI control");if(node.performAction(AccessibilityNodeInfo.ACTION_CLICK))return;long now=SystemClock.uptimeMillis();sendPointerSync(android.view.MotionEvent.obtain(now,now,android.view.MotionEvent.ACTION_DOWN,bounds.centerX(),bounds.centerY(),0));sendPointerSync(android.view.MotionEvent.obtain(now,now+30,android.view.MotionEvent.ACTION_UP,bounds.centerX(),bounds.centerY(),0));}
    private void click(String name){until(n->n.isEnabled()&&text(n).equalsIgnoreCase(name),this::tap,name,30000);}
    private void field(String name,String value){until(n->desc(n,name),n->{Bundle b=new Bundle();b.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,value);need(n.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,b),"account UI field");},name,30000);}
    private void status(String value){until(n->desc(n,"同步状态")&&text(n).contains(value),null,value,120000);}
    private void panel(){click("More");click("同步");}
    private void records(){until(n->desc(n,"阅读更多操作")&&n.isEnabled(),this::tap,"reader More",30000);click("阅读记录");}
    private JSONObject frame()throws Exception{String[] raw={null};until(n->id(n,"reader_view")&&n.getExtras().containsKey("exreader.frame"),n->raw[0]=n.getExtras().getString("exreader.frame"),"rendered frame",30000);return new JSONObject(raw[0]);}
    private JSONObject settled()throws Exception{long end=SystemClock.elapsedRealtime()+30000;while(SystemClock.elapsedRealtime()<end){JSONObject f=frame();if(f.optLong("settled_token")>0&&f.optLong("settled_token")==f.optLong("accepted_token")&&f.optLong("settled_revision")==f.optLong("revision")&&f.optLong("end")>f.optLong("start"))return f;SystemClock.sleep(100);}throw new AssertionError("native frame did not settle");}
    private JSONObject location()throws Exception{
        // Read-only evidence from the existing product owner; never seed or apply a record here.
        try(BookStore store=new BookStore(context,new File(context.getFilesDir(),"library.db"))){
            HostTask task=new HostTask(()->false);ReadingRecord record=NativeReadingProduct.list(store,input.getString("book_identity"),"",false,new ReadingControl(task,null,"relay-evidence",false)).progress;
            need(record.readable()&&record.capture.mode==ReadingCapture.EPUB,"safe application EPUB progress");ReadingCapture c=record.capture;
            return new JSONObject().put("part",c.unit).put("path",c.partPath).put("start",c.start).put("end",c.end).put("exact",c.text(0)).put("prefix",c.text(1)).put("suffix",c.text(2)).put("parser",c.parser).put("head",record.head).put("book_identity",c.bookKey);
        }
    }
    private void onTarget(JSONObject f,JSONObject loc)throws Exception{
        need(f.getString("source_key").equals(input.getString("book_identity")),"actual frame original identity");
        need(f.getLong("part")==loc.getLong("part")&&f.getString("path").equals(loc.getString("path")),"public parser part identity");
        need(f.getLong("start")<=loc.getLong("start")&&f.getLong("end")>loc.getLong("start"),"target lies in actual rendered page; no equal-page assumption across reflow");
    }
    @Override public void onStart(){context=getTargetContext();Throwable failure=null;Bundle result=new Bundle();
        try{
            AccessibilityServiceInfo service=getUiAutomation().getServiceInfo();service.flags|=AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS;getUiAutomation().setServiceInfo(service);
            File incoming=new File(context.getFilesDir(),"relay-input.json");input=new JSONObject(new String(Files.readAllBytes(incoming.toPath()),StandardCharsets.UTF_8));Files.delete(incoming.toPath());
            need(BuildConfig.READER_SYNC&&BuildConfig.READER_READING&&BuildConfig.READER_SELECTOR_BYTES_CANDIDATE,"real candidate product features");
            check("empty_library_real_account_and_sync",()->{
                context.startActivity(new Intent(context,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TOP));panel();click("云盘账号");
                field("云盘地址",input.getString("root"));field("云盘用户名",input.getString("user"));field("云盘密码",input.getString("password"));click("仅本次使用");status("仅本次使用凭据");click("立即同步");status("本轮同步结束");
            });
            check("explicit_application_receive_original",()->{until(n->n.isEnabled()&&text(n).contains(input.optString("remote_title")),this::tap,"remote book",30000);click("接收");status("书籍已接收");
                File original=new File(new File(context.getFilesDir(),"sync-cache"),input.getString("original_sha256")+".epub");need(original.length()==input.getLong("original_bytes"),"received exact byte length");need(BookStore.syncFileHash(original,new HostTask(()->false)).equals(input.getString("original_sha256")),"received SHA256 from Apple original");
                try(NativeLibrary library=new NativeLibrary(new File(context.getFilesDir(),"library.db").getPath())){
                    NativeLibrary.Book[] books=library.books();need(books.length==1,"exactly one app-received original");
                    java.security.MessageDigest digest=java.security.MessageDigest.getInstance("SHA-256");
                    try(NativeLibrary.Source source=library.source(books[0].id)){
                        need(source.size==input.getLong("original_bytes"),"public SDK original byte length");byte[] chunk=new byte[65536];
                        for(long offset=0;offset<source.size;){int count=source.read(offset,chunk,(int)Math.min(chunk.length,source.size-offset));need(count>0,"public SDK source bytes");digest.update(chunk,0,count);offset+=count;}
                    }
                    StringBuilder hash=new StringBuilder();for(byte value:digest.digest())hash.append(String.format(java.util.Locale.ROOT,"%02x",value&255));
                    need(hash.toString().equals(input.getString("original_sha256")),"public SDK original SHA256 matches Apple");evidence.put("public_source_sha256",hash.toString());
                }
                click("关闭");until(n->n.isEnabled()&&text(n).contains(input.optString("remote_title")),this::tap,"local received book",30000);evidence.put("initial_frame",settled());
            });
            check("apple_progress_public_parse_real_jump",()->{
                JSONObject incomingLocation=location(),expected=input.getJSONObject("location");for(String key:new String[]{"part","path","start","end","exact","prefix","suffix"})need(String.valueOf(incomingLocation.opt(key)).equals(String.valueOf(expected.opt(key))),"Apple wire location matches "+key);
                evidence.put("incoming_location",incomingLocation);records();until(n->desc(n,"已保存进度")&&n.isEnabled(),this::tap,"saved progress",30000);click("跳转到此处");
                until(n->id(n,"reader_status")&&text(n).contains("已跳转到阅读记录"),null,"public resolver jump",30000);JSONObject restored=settled();onTarget(restored,incomingLocation);evidence.put("restored_frame",restored);
            });
            check("real_forward_pages_and_application_save",()->{
                JSONObject before=settled();for(int i=0;i<3;i++){JSONObject old=settled();until(n->id(n,"reader_view"),n->need(n.performAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD),"native forward action"),"page forward",30000);
                    long end=SystemClock.elapsedRealtime()+30000;boolean moved=false;while(SystemClock.elapsedRealtime()<end){JSONObject now=settled();if(now.getLong("part")!=old.getLong("part")||now.getLong("start")!=old.getLong("start")){moved=true;break;}SystemClock.sleep(100);}need(moved,"real EPUB page advanced");}
                JSONObject after=settled();need(after.getLong("part")>before.getLong("part")||after.getLong("start")>before.getLong("start"),"later reading position");evidence.put("outgoing_frame",after);records();click("保存进度");until(n->desc(n,"阅读记录状态")&&text(n).contains("已保存"),null,"application progress saved",30000);
                JSONObject saved=location();onTarget(after,saved);need(!saved.getString("head").equals(evidence.getJSONObject("incoming_location").getString("head")),"new app revision");evidence.put("location",saved);click("关闭");
            });
            check("application_sync_outgoing_position",()->{click("Shelf");panel();click("立即同步");status("本轮同步结束");click("断开");});
        }catch(Throwable error){failure=error;}
        try{
            evidence.put("source_sha",arguments.getString("source_sha")).put("run_id",arguments.getString("run_id")).put("attempt",arguments.getString("attempt")).put("passed",failure==null).put("checks",checks).put("phase","android").put("api",android.os.Build.VERSION.SDK_INT).put("abi",android.os.Build.SUPPORTED_ABIS[0]).put("physical_device",false).put("picker_used",false).put("pid",android.os.Process.myPid());
            if(input!=null)for(String key:new String[]{"original_sha256","original_bytes","book_identity","remote_title"})evidence.put(key,input.get(key));
            if(failure!=null)evidence.put("failed_check",active).put("failure",failure.toString());
            Files.write(new File(context.getFilesDir(),"relay-android-report.json").toPath(),evidence.toString(2).getBytes(StandardCharsets.UTF_8));result.putString("stream",failure==null?"RELAY_ANDROID_PASS":"RELAY_ANDROID_FAIL "+active);finish(failure==null?Activity.RESULT_OK:Activity.RESULT_CANCELED,result);
        }catch(Throwable error){result.putString("shortMsg","relay evidence unavailable");finish(Activity.RESULT_CANCELED,result);}
    }
}
