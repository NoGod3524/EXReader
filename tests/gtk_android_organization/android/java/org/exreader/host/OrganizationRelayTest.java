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
public final class OrganizationRelayTest extends Instrumentation {
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
    private void click(String label){target="click "+label;waitFor(n->n.isEnabled()&&text(n).equalsIgnoreCase(label),n->{AccessibilityNodeInfo at=n;while(!at.isClickable()&&at.getParent()!=null)at=at.getParent();need(at.performAction(AccessibilityNodeInfo.ACTION_CLICK),"click "+label);},30000);}
    private void field(String label,String value){target="field "+label;waitFor(n->label.contentEquals(n.getContentDescription()==null?"":n.getContentDescription()),n->{if(!n.isEnabled()){need(label.equals("云盘地址")&&text(n).equals(value),"bound account root must remain identical");return;}Bundle b=new Bundle();b.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,value);need(n.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,b),"field "+label);},30000);}
    private void status(String value){target="status "+value;waitFor(n->"同步状态".contentEquals(n.getContentDescription()==null?"":n.getContentDescription())&&text(n).contains(value),null,180000);}
    private void launch(){target="launch More shelf actions";context.startActivity(new Intent(context,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));waitFor(n->"More shelf actions".contentEquals(n.getContentDescription()==null?"":n.getContentDescription()),null,30000);}
    private void configure()throws Exception{click("More");click("同步");click("云盘账号");field("云盘地址",input.getString("root"));field("云盘用户名",input.getString("user"));field("云盘密码",input.getString("password"));click("仅本次使用");status("仅本次使用凭据");}
    private JSONObject data; private JSONArray screens=new JSONArray();
    private void visible(String value){target="visible "+value;waitFor(n->text(n).equals(value)||text(n).startsWith(value+" ·"),null,30000);}
    private void row(String value){target="row "+value;waitFor(n->text(n).equals(value)||text(n).startsWith(value+" ·"),n->{AccessibilityNodeInfo at=n;while(!at.isClickable()&&at.getParent()!=null)at=at.getParent();need(at.performAction(AccessibilityNodeInfo.ACTION_CLICK),"row "+value);},30000);}
    private void shot(String name)throws Exception{
        android.graphics.Bitmap b=getUiAutomation().takeScreenshot();need(b!=null,"screenshot");
        try(java.io.FileOutputStream out=new java.io.FileOutputStream(new File(context.getFilesDir(),"org-"+name+".png"))){need(b.compress(android.graphics.Bitmap.CompressFormat.PNG,100,out),"encode");}b.recycle();screens.put(name);
        AccessibilityNodeInfo root=getUiAutomation().getRootInActiveWindow();StringBuilder tree=new StringBuilder();if(root!=null){describe(root,tree,0);root.recycle();}
        Files.write(new File(context.getFilesDir(),"org-"+name+".txt").toPath(),tree.toString().getBytes(StandardCharsets.UTF_8));
    }
    private void sync(){click("立即同步");status("本轮同步结束，书架已更新");click("关闭");}
    private void syncReceive()throws Exception{
        click("立即同步");status("本轮同步结束，书架已更新");row("Relay GTK.txt");click("接收");status("书籍已接收");
        try(NativeLibrary library=new NativeLibrary(new File(context.getFilesDir(),"library.db").getPath())){
            NativeLibrary.Book[] books=library.books();need(books.length==1,"one explicitly app-received original");
            java.security.MessageDigest digest=java.security.MessageDigest.getInstance("SHA-256");
            try(NativeLibrary.Source source=library.source(books[0].id)){
                need(source.size>0,"received source bytes");byte[] chunk=new byte[65536];
                for(long offset=0;offset<source.size;){int count=source.read(offset,chunk,(int)Math.min(chunk.length,source.size-offset));need(count>0,"SDK source readable");digest.update(chunk,0,count);offset+=count;}
            }
            StringBuilder hash=new StringBuilder();for(byte value:digest.digest())hash.append(String.format(java.util.Locale.ROOT,"%02x",value&255));
            need(hash.toString().equals(data.getString("original_sha256")),"received public SDK source equals GTK original");
        }
        check("explicit_native_receive_and_public_original_hash",()->{});click("关闭");
    }
    private void organize(){click("More");click("Organize");target="organize New action";waitFor(n->n.isEnabled()&&"New".contentEquals(n.getContentDescription()==null?"":n.getContentDescription()),null,30000);}
    private void kind(int n){click("Kind");click(new String[]{"Shelves","Tags","Series"}[n]);}
    private void create(String name){click("New");field("Name",name);click("Save");visible(name);}
    private void groupAction(String name,String action){
        row(name);target="group menu "+name+" / "+action;
        // The background toolbar also has Books/Children buttons. Wait for the
        // asynchronous group menu's TextView item, never click that toolbar.
        waitFor(n->n.isEnabled()&&"android.widget.TextView".contentEquals(n.getClassName())&&text(n).equals(action),n->{AccessibilityNodeInfo at=n;while(!at.isClickable()&&at.getParent()!=null)at=at.getParent();need(at.performAction(AccessibilityNodeInfo.ACTION_CLICK),"group action "+action);},30000);
    }
    private void member(String name)throws Exception{groupAction(name,"Books");visible("Relay GTK.txt");}
    private void add(String name){groupAction(name,"Books");click("Add book");row("Relay GTK.txt");click("Add");visible("Relay GTK.txt");}
    private String findId(int kind,String name)throws Exception{return findId(kind,name,"");}
    private String findId(int kind,String name,String parent)throws Exception{
        long owner=NativeCatalog.open(new File(context.getFilesDir(),"reader-catalog.db").getAbsolutePath());
        try{for(String[] r:NativeCatalog.groups(owner,kind,parent,null,0,false,false))if(r[1].equals(name))return r[0];throw new AssertionError("group absent "+name);}finally{NativeCatalog.close(owner);}
    }
    private JSONObject snapshot()throws Exception{
        JSONObject result=new JSONObject();long owner=NativeCatalog.open(new File(context.getFilesDir(),"reader-catalog.db").getAbsolutePath());
        try{for(String key:new String[]{"shelf","child","tag","series","android_0","android_1","android_2","android_child"})if(data.has(key)){
            int k=key.equals("tag")?1:key.equals("series")?2:key.startsWith("android_")&&!key.equals("android_child")?Integer.parseInt(key.substring(8)):0;
            JSONArray groups=new JSONArray(),members=new JSONArray();for(String[] row:NativeCatalog.groupFind(owner,k,data.getString(key)))groups.put(new JSONArray(java.util.Arrays.asList(row)));
            for(String[] row:NativeCatalog.memberFind(owner,k,data.getString(key),data.getString("book_key")))members.put(new JSONArray(java.util.Arrays.asList(row)));
            result.put(key,new JSONObject().put("groups",groups).put("members",members));
        }}finally{NativeCatalog.close(owner);}return result;
    }
    private void verifyVisible(boolean finalStage)throws Exception{
        organize();kind(0);member("GTK parent");click("Children");groupAction("GTK child","Books");visible("Relay GTK.txt");shot("child");
        kind(1);member(finalStage?"Android edited tag":"GTK tag");shot("tag");kind(2);member("GTK series");shot("series");
        if(finalStage){for(int n=0;n<3;n++){kind(n);member(new String[]{"Android shelf","Android tag","Android series"}[n]);shot("android-"+n);}
            kind(0);groupAction("Android shelf","Children");member("Android child");shot("android-child");}
        click("Close");
    }
    @Override public void onStart(){context=getTargetContext();Throwable failure=null;JSONObject rows=null;
        try{
            File file=new File(context.getFilesDir(),"organization-relay-input.json");input=new JSONObject(new String(Files.readAllBytes(file.toPath()),StandardCharsets.UTF_8));Files.delete(file.toPath());data=input.getJSONObject("relay_data");
            boolean last="android-final".equals(input.getString("phase")),restart="true".equals(args.getString("restart"));
            launch();
            if(restart){verifyVisible(true);rows=snapshot();check("process_restart_real_ui_retains_groups_members",()->{});}
            else{
                configure();syncReceive();verifyVisible(last);check("receive_other_host_native_organization_ui",()->{});
                JSONObject before=snapshot();configure();sync();need(before.toString().equals(snapshot().toString()),"duplicate sync changed exact organization rows");check("duplicate_sync_has_no_duplicate_rows",()->{});
                if(!last){
                    organize();kind(1);groupAction("GTK tag","Edit");field("Name","Android edited tag");click("Save");visible("Android edited tag");
                    member("Android edited tag");row("Relay GTK.txt");click("Remove");
                    kind(2);groupAction("GTK series","Delete");click("Delete");click("Removed");visible("GTK series");shot("deleted-series");click("Active");
                    for(int n=0;n<3;n++){kind(n);String name=new String[]{"Android shelf","Android tag","Android series"}[n];create(name);data.put("android_"+n,findId(n,name));add(name);shot("created-"+n);}
                    kind(0);groupAction("Android shelf","Children");create("Android child");data.put("android_child",findId(0,"Android child",data.getString("android_0")));add("Android child");shot("created-child");
                    click("Close");check("android_native_ui_edits_removes_creates_and_classifies",()->{});configure();sync();check("android_application_publishes_actual_revisions",()->{});
                }
                rows=snapshot();
            }
        }catch(Throwable error){failure=error;}
        try{JSONObject report=new JSONObject().put("source_sha",args.getString("source_sha")).put("run_id",args.getString("run_id")).put("attempt",args.getString("attempt")).put("api",android.os.Build.VERSION.SDK_INT).put("passed",failure==null).put("checks",checks).put("rows",rows).put("relay_data",data).put("screens",screens);if(failure!=null)report.put("failure",failure.toString());Files.write(new File(context.getFilesDir(),"organization-relay-report.json").toPath(),report.toString(2).getBytes(StandardCharsets.UTF_8));Bundle out=new Bundle();out.putString("stream",failure==null?"ORG_RELAY_PASS":"ORG_RELAY_FAIL "+failure);finish(failure==null?Activity.RESULT_OK:Activity.RESULT_CANCELED,out);}catch(Exception error){finish(Activity.RESULT_CANCELED,new Bundle());}
    }
}
