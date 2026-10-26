package org.exreader.host;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.content.Intent;
import android.os.Bundle;
import android.os.SystemClock;
import android.view.accessibility.AccessibilityNodeInfo;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.function.Predicate;
import org.json.JSONArray;
import org.json.JSONObject;

/** Real Activity and session on API34; fixture secrets never leave private storage. */
public final class OrganizationSyncTest extends Instrumentation {
    private Context context; private Bundle args; private JSONObject input; private JSONArray checks=new JSONArray(); private String target="";
    interface Check { void run() throws Exception; }
    @Override public void onCreate(Bundle args){super.onCreate(args);this.args=args;start();}
    private void check(String name,Check test)throws Exception{test.run();checks.put(new JSONObject().put("name",name).put("pass",true));}
    private static void need(boolean value,String message){if(!value)throw new AssertionError(message);}
    private AccessibilityNodeInfo find(AccessibilityNodeInfo node,Predicate<AccessibilityNodeInfo> predicate){
        if(node==null)return null;if(predicate.test(node))return node;
        for(int i=0;i<node.getChildCount();i++){AccessibilityNodeInfo child=node.getChild(i),found=find(child,predicate);if(found!=null){if(found!=child&&child!=null)child.recycle();return found;}if(child!=null)child.recycle();}return null;
    }
    private void waitFor(Predicate<AccessibilityNodeInfo> predicate,java.util.function.Consumer<AccessibilityNodeInfo> action,long timeout){
        long end=SystemClock.elapsedRealtime()+timeout;
        while(SystemClock.elapsedRealtime()<end){AccessibilityNodeInfo root=getUiAutomation().getRootInActiveWindow(),found=null;
            try{if(root!=null&&(found=find(root,predicate))!=null){if(action!=null)action.accept(found);return;}}catch(IllegalStateException ignored){}finally{if(found!=null&&found!=root)found.recycle();if(root!=null)root.recycle();}SystemClock.sleep(80);}
        AccessibilityNodeInfo root=getUiAutomation().getRootInActiveWindow();StringBuilder tree=new StringBuilder();
        if(root!=null){describe(root,tree,0);root.recycle();}
        throw new AssertionError("UI element not ready: "+target+"; tree="+tree);
    }
    private void describe(AccessibilityNodeInfo node,StringBuilder out,int depth){
        if(depth>20||out.length()>12000)return;String type=String.valueOf(node.getClassName());out.append('[').append(type).append('|').append(type.contains("EditText")?"<redacted>":text(node)).append('|').append(node.getContentDescription()).append(']');
        for(int i=0;i<node.getChildCount();i++){AccessibilityNodeInfo child=node.getChild(i);if(child!=null){describe(child,out,depth+1);child.recycle();}}
    }
    private static String text(AccessibilityNodeInfo n){return n.getText()==null?"":n.getText().toString();}
    private void click(String label){target="click "+label;waitFor(n->n.isEnabled()&&text(n).equalsIgnoreCase(label),n->need(n.performAction(AccessibilityNodeInfo.ACTION_CLICK),"click "+label),30000);}
    private void field(String label,String value){target="field "+label;waitFor(n->label.contentEquals(n.getContentDescription()==null?"":n.getContentDescription()),n->{Bundle b=new Bundle();b.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,value);need(n.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,b),"field");},30000);}
    private void status(String value){target="status "+value;waitFor(n->"同步状态".contentEquals(n.getContentDescription()==null?"":n.getContentDescription())&&text(n).contains(value),null,180000);}
    private void launch(){target="launch More shelf actions";context.startActivity(new Intent(context,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));waitFor(n->"More shelf actions".contentEquals(n.getContentDescription()==null?"":n.getContentDescription()),null,30000);}
    private void configure()throws Exception{click("More");click("同步");click("云盘账号");field("云盘地址",input.getString("root"));field("云盘用户名",input.getString("user"));field("云盘密码",input.getString("password"));click("仅本次使用");status("仅本次使用凭据");}
    @Override public void onStart(){context=getTargetContext();Throwable failure=null;
        try{
            input=new JSONObject(new String(Files.readAllBytes(new File(context.getFilesDir(),"organization-sync-input.json").toPath()),StandardCharsets.UTF_8));
            Files.delete(new File(context.getFilesDir(),"organization-sync-input.json").toPath());
            check("actual_activity_sync_and_saved_intent_barrier",()->{
                IntentJournal journal=new IntentJournal(context.getSharedPreferences("organization",0));
                IntentJournal.Command command=IntentJournal.Command.group(0,0,"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","Pending local edit","",0,new String[0]);
                journal.create(command,null);launch();configure();click("立即同步");status("有待恢复的本地修改");
                long owner=NativeCatalog.open(new File(context.getFilesDir(),"reader-catalog.db").getAbsolutePath());try{need(NativeCatalog.metadata(owner,input.getString("book_key"))==null,"pending intent blocks book projection");}finally{NativeCatalog.close(owner);}
                need(context.getSharedPreferences("organization",0).edit().clear().commit(),"test clears its pending intent");
            });
            check("queued_cancel_then_continue",()->{
                SyncController controller=SyncController.get(context);
                java.lang.reflect.Field field=SyncController.class.getDeclaredField("worker");field.setAccessible(true);
                java.util.concurrent.ScheduledExecutorService worker=(java.util.concurrent.ScheduledExecutorService)field.get(controller);
                java.util.concurrent.CountDownLatch entered=new java.util.concurrent.CountDownLatch(1),release=new java.util.concurrent.CountDownLatch(1);
                worker.execute(()->{entered.countDown();try{release.await();}catch(InterruptedException e){Thread.currentThread().interrupt();}});
                need(entered.await(10,java.util.concurrent.TimeUnit.SECONDS),"worker barrier");
                controller.continueProjection();controller.cancel();release.countDown();status("投影已暂停");
                java.lang.reflect.Field pages=SyncController.class.getDeclaredField("projectPages");pages.setAccessible(true);
                java.util.concurrent.CountDownLatch enteredAgain=new java.util.concurrent.CountDownLatch(1),releaseAgain=new java.util.concurrent.CountDownLatch(1);
                worker.execute(()->{enteredAgain.countDown();try{releaseAgain.await();}catch(InterruptedException e){Thread.currentThread().interrupt();}});
                need(enteredAgain.await(10,java.util.concurrent.TimeUnit.SECONDS),"budget barrier");
                controller.continueProjection();worker.execute(()->{try{pages.setInt(controller,200);}catch(IllegalAccessException e){throw new AssertionError(e);}});releaseAgain.countDown();
                status("书架更新达到本轮上限");
                click("继续更新书架");status("书架有冲突或缺少依赖");
            });
            check("metadata_without_sdk_original_and_same_page_delete_conflict",()->{
                long owner=NativeCatalog.open(new File(context.getFilesDir(),"reader-catalog.db").getAbsolutePath());try{
                    String[] book=NativeCatalog.metadata(owner,input.getString("book_key"));need(book!=null&&book[3].equals("Remote metadata only")&&book[7].equals("0"),"remote book metadata projected");
                    String[] deleted=NativeCatalog.metadata(owner,input.getString("deleted_key"));need(deleted!=null&&deleted[7].equals("1")&&!deleted[3].equals(input.getString("deleted_key")),"deleted title not replaced by key");
                    need(NativeCatalog.metadata(owner,input.getString("conflict_key"))==null,"conflicted book not projected");
                    need(NativeCatalog.groupFind(owner,0,input.getString("shelf_id")).length==1,"shelf projected");
                    need(NativeCatalog.memberFind(owner,0,input.getString("shelf_id"),input.getString("book_key")).length==1,"membership projected");
                    need(NativeCatalog.groupFind(owner,0,input.getString("orphan_id")).length==0,"missing parent retained pending");
                }finally{NativeCatalog.close(owner);}
                try(NativeLibrary library=new NativeLibrary(new File(context.getFilesDir(),"library.db").getAbsolutePath())){need(library.books().length==0,"metadata needs no imported SDK original");}
            });
            check("queued_close_retires_session_before_next_batch",()->{
                SyncController controller=SyncController.get(context);
                java.lang.reflect.Field field=SyncController.class.getDeclaredField("worker");field.setAccessible(true);
                java.util.concurrent.ScheduledExecutorService worker=(java.util.concurrent.ScheduledExecutorService)field.get(controller);
                java.util.concurrent.CountDownLatch entered=new java.util.concurrent.CountDownLatch(1),release=new java.util.concurrent.CountDownLatch(1);
                worker.execute(()->{entered.countDown();try{release.await();}catch(InterruptedException e){Thread.currentThread().interrupt();}});
                need(entered.await(10,java.util.concurrent.TimeUnit.SECONDS),"worker barrier");
                controller.continueProjection();controller.close();release.countDown();
                long end=SystemClock.elapsedRealtime()+30000;while(NativeSyncProbe.sessions()!=0&&SystemClock.elapsedRealtime()<end)SystemClock.sleep(80);
                need(NativeSyncProbe.sessions()==0,"closed session must be destroyed");
            });
            check("visible_native_organization_panel",()->{click("关闭");click("More");click("Organize");waitFor(n->text(n).equals("Cloud Shelf"),null,30000);click("Cloud Shelf");click("Books");waitFor(n->text(n).contains("Remote metadata only"),null,30000);});
        }catch(Throwable error){failure=error;}
        try{JSONObject report=new JSONObject().put("source_sha",args.getString("source_sha")).put("run_id",args.getString("run_id")).put("attempt",args.getString("attempt")).put("passed",failure==null).put("checks",checks).put("count",checks.length());if(failure!=null)report.put("failure",failure.toString());Files.write(new File(context.getFilesDir(),"organization-sync-report.json").toPath(),report.toString(2).getBytes(StandardCharsets.UTF_8));Bundle out=new Bundle();out.putString("stream",failure==null?"ORGANIZATION_SYNC_PASS":"ORGANIZATION_SYNC_FAIL "+failure);finish(failure==null?Activity.RESULT_OK:Activity.RESULT_CANCELED,out);}catch(Exception error){finish(Activity.RESULT_CANCELED,new Bundle());}
    }
}
