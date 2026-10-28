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
    private JSONObject tree(AccessibilityNodeInfo node)throws Exception{
        if(node==null)return new JSONObject();JSONArray children=new JSONArray();for(int i=0;i<node.getChildCount();i++){AccessibilityNodeInfo child=node.getChild(i);if(child!=null){try{children.put(tree(child));}finally{child.recycle();}}}
        return new JSONObject().put("id",node.getViewIdResourceName()).put("text",text(node)).put("description",String.valueOf(node.getContentDescription())).put("class",String.valueOf(node.getClassName())).put("enabled",node.isEnabled()).put("frame",node.getExtras().getString("exreader.frame","")).put("children",children);
    }
    private void field(String name,String value){until(n->desc(n,name),n->{Bundle b=new Bundle();b.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,value);need(n.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,b),"account UI field");},name,30000);}
    private void status(String value){until(n->desc(n,"同步状态")&&text(n).contains(value),null,value,120000);}
    private void panel(){click("More");click("同步");}
    private void records(){until(n->desc(n,"阅读更多操作")&&n.isEnabled(),this::tap,"reader More",30000);click("阅读记录");}
    private JSONObject frame()throws Exception{String[] raw={null};until(n->id(n,"reader_view")&&n.getExtras().containsKey("exreader.frame"),n->raw[0]=n.getExtras().getString("exreader.frame"),"rendered frame",30000);return new JSONObject(raw[0]);}
    private JSONObject settled()throws Exception{long end=SystemClock.elapsedRealtime()+30000;while(SystemClock.elapsedRealtime()<end){JSONObject f=frame();if(f.optLong("settled_token")>0&&f.optLong("settled_token")==f.optLong("accepted_token")&&f.optLong("settled_revision")==f.optLong("revision")&&f.optLong("bitmap_width")>0&&f.optLong("bitmap_height")>0&&(f.optLong("end")>f.optLong("start")||f.optLong("bounded_visual_boxes")>0))return f;SystemClock.sleep(100);}throw new AssertionError("native frame did not settle");}
    private JSONObject location()throws Exception{
        // Read-only evidence from the existing product owner; never seed or apply a record here.
        try(BookStore store=new BookStore(context,new File(context.getFilesDir(),"library.db"))){
            HostTask task=new HostTask(()->false);ReadingRecord record=NativeReadingProduct.list(store,input.getString("book_identity"),"",false,new ReadingControl(task,null,"relay-evidence",false)).progress;
            need(record.readable()&&record.capture.mode==ReadingCapture.EPUB,"safe application EPUB progress");ReadingCapture c=record.capture;
            return new JSONObject().put("part",c.unit).put("path",c.partPath).put("start",c.start).put("end",c.end).put("exact",c.text(0)).put("prefix",c.text(1)).put("suffix",c.text(2)).put("parser",c.parser).put("head",record.head).put("book_identity",c.bookKey);
        }
    }
    private JSONArray annotations()throws Exception {
        try(BookStore store=new BookStore(context,new File(context.getFilesDir(),"library.db"))) {
            ReadingRecord[] rows=NativeReadingProduct.list(store,input.getString("book_identity"),"",false,new ReadingControl(new HostTask(()->false),null,"record-relay-evidence",false)).rows;
            JSONArray output=new JSONArray();for(ReadingRecord r:rows){need(r.readable(),"received record is safe");ReadingCapture c=r.capture;
                output.put(new JSONObject().put("id",r.id).put("head",r.head).put("body",r.body).put("kind",r.kind).put("part",c.unit).put("path",c.partPath).put("start",c.start).put("end",c.end).put("exact",c.text(0)).put("prefix",c.text(1)).put("suffix",c.text(2)));}return output;
        }
    }
    private JSONObject byBody(JSONArray rows,String body)throws Exception{for(int i=0;i<rows.length();i++)if(rows.getJSONObject(i).getString("body").equals(body))return rows.getJSONObject(i);throw new AssertionError("missing actual record: "+body);}
    private void row(JSONObject r)throws Exception{String body=r.getString("body"),exact=r.getString("exact");until(n->n.isEnabled()&&(text(n).contains(body)&&!body.isEmpty()||!exact.isEmpty()&&text(n).startsWith("高亮")),this::tap,"record row "+body,30000);}
    private void onTarget(JSONObject f,JSONObject loc)throws Exception{
        need(f.getString("source_key").equals(input.getString("book_identity")),"actual frame original identity");
        need(f.getLong("part")==loc.getLong("part")&&f.getString("path").equals(loc.getString("path")),"public parser part identity");
        need(f.getLong("start")<=loc.getLong("start")&&f.getLong("end")>loc.getLong("start"),"target lies in actual rendered page; no equal-page assumption across reflow");
    }
    @Override public void onStart(){context=getTargetContext();Throwable failure=null;Bundle result=new Bundle();
        try{
            AccessibilityServiceInfo service=getUiAutomation().getServiceInfo();service.flags|=AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS;getUiAutomation().setServiceInfo(service);
            File inputFile=new File(context.getFilesDir(),"relay-input.json");input=new JSONObject(new String(Files.readAllBytes(inputFile.toPath()),StandardCharsets.UTF_8));Files.delete(inputFile.toPath());
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
                click("关闭");until(n->n.isEnabled()&&id(n,"text1")&&text(n).startsWith(input.optString("remote_title")+"\n"),this::tap,"received shelf row",30000);evidence.put("initial_frame",settled());
            });
            check("windows_records_real_public_resolution",()->{
                JSONArray incoming=annotations();need(incoming.length()==3,"exactly Windows bookmark annotation and ambiguous bookmark");evidence.put("incoming_records",incoming);JSONArray frames=new JSONArray();
                for(int i=0;i<incoming.length();i++){JSONObject record=incoming.getJSONObject(i);if(record.getString("body").equals("Ambiguous bookmark"))continue;records();row(record);click("跳转到此处");until(n->id(n,"reader_status")&&text(n).contains("已跳转到阅读记录"),null,"public record resolver",30000);JSONObject f=settled();onTarget(f,record);frames.put(f);}
                evidence.put("resolved_frames",frames);
            });
            check("ambiguous_record_is_explicit_and_does_not_move_page",()->{
                JSONObject before=settled(),ambiguous=byBody(annotations(),"Ambiguous bookmark");records();row(ambiguous);click("跳转到此处");
                until(n->desc(n,"阅读记录状态")&&text(n).contains("位置有歧义，未跳转"),null,"explicit ambiguous no navigation",30000);click("关闭");JSONObject after=settled();
                need(before.getLong("part")==after.getLong("part")&&before.getLong("start")==after.getLong("start")&&before.getLong("end")==after.getLong("end"),"ambiguous record leaves real page intact");evidence.put("ambiguous_before",before).put("ambiguous_after",after);
            });
            check("android_edits_received_note_and_adds_bookmark",()->{
                JSONArray incoming=evidence.getJSONArray("incoming_records");JSONObject note=byBody(incoming,"Windows note");records();row(note);click("编辑文字");field("阅读记录文字","Android edited note");click("保存");until(n->desc(n,"阅读记录状态")&&text(n).contains("已保存"),null,"edit committed",30000);
                JSONObject edited=byBody(annotations(),"Android edited note");need(edited.getString("id").equals(note.getString("id"))&&!edited.getString("head").equals(note.getString("head")),"same annotation new revision");click("关闭");
                JSONObject before=settled();until(n->id(n,"reader_view"),n->need(n.performAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD),"actual next page"),"next page",30000);
                long end=SystemClock.elapsedRealtime()+30000;while(settled().getLong("start")==before.getLong("start")&&SystemClock.elapsedRealtime()<end)SystemClock.sleep(100);JSONObject next=settled();need(next.getLong("start")!=before.getLong("start"),"page actually moved");
                records();click("添加书签");field("阅读记录文字","Android new bookmark");click("保存");until(n->desc(n,"阅读记录状态")&&text(n).contains("已保存"),null,"new bookmark committed",30000);JSONArray outgoing=annotations();need(outgoing.length()==4,"no duplicate incoming records");onTarget(next,byBody(outgoing,"Android new bookmark"));evidence.put("outgoing_records",outgoing).put("new_bookmark_frame",next);click("关闭");
            });
            check("application_sync_and_duplicate_idempotence",()->{
                click("Shelf");panel();click("立即同步");status("本轮同步结束");JSONArray before=annotations();click("立即同步");status("本轮同步结束");JSONArray after=annotations();need(before.toString().equals(after.toString()),"repeat sync preserves exact record heads and count");evidence.put("records_after_repeat",after);click("断开");
            });
        }catch(Throwable error){failure=error;AccessibilityNodeInfo root=getUiAutomation().getRootInActiveWindow();try{evidence.put("failure_ui",tree(root));}catch(Exception capture){error.addSuppressed(capture);}finally{if(root!=null)root.recycle();}}
        try{
            evidence.put("source_sha",arguments.getString("source_sha")).put("run_id",arguments.getString("run_id")).put("attempt",arguments.getString("attempt")).put("passed",failure==null).put("checks",checks).put("phase","android").put("api",android.os.Build.VERSION.SDK_INT).put("abi",android.os.Build.SUPPORTED_ABIS[0]).put("physical_device",false).put("picker_used",false).put("pid",android.os.Process.myPid());
            if(input!=null)for(String key:new String[]{"original_sha256","original_bytes","book_identity","remote_title","windows_program_sha256"})evidence.put(key,input.get(key));
            if(failure!=null){java.io.StringWriter trace=new java.io.StringWriter();failure.printStackTrace(new java.io.PrintWriter(trace));evidence.put("failed_check",active).put("failure",failure.toString()).put("failure_stack",trace.toString());}
            Files.write(new File(context.getFilesDir(),"relay-android-report.json").toPath(),evidence.toString(2).getBytes(StandardCharsets.UTF_8));result.putString("stream",failure==null?"RELAY_ANDROID_PASS":"RELAY_ANDROID_FAIL "+active);finish(failure==null?Activity.RESULT_OK:Activity.RESULT_CANCELED,result);
        }catch(Throwable error){result.putString("shortMsg","relay evidence unavailable");finish(Activity.RESULT_CANCELED,result);}
    }
}
