// SPDX-License-Identifier: MIT
package org.exreader.host;
import android.app.Activity;
import android.app.Instrumentation;
import android.accessibilityservice.AccessibilityServiceInfo;
import android.content.Context;
import android.content.Intent;
import android.graphics.Rect;
import android.graphics.Bitmap;
import android.os.Bundle;
import android.os.SystemClock;
import android.view.MotionEvent;
import android.view.View;
import android.view.accessibility.AccessibilityNodeInfo;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.function.Predicate;
import org.exreader.credentials.CredentialStore;
import org.json.JSONArray;
import org.json.JSONObject;

/** Operates the actual target Activity; fixture credentials never enter arguments/logs. */
public final class SyncStatusTest extends Instrumentation {
    private Bundle arguments;
    private Context context;
    private JSONObject input;
    private final JSONArray checks=new JSONArray();
    private final JSONArray observations=new JSONArray();
    private String phase;
    private String activeCheck;
    interface Check {void run()throws Exception;}
    @Override public void onCreate(Bundle args){super.onCreate(args);arguments=args;start();}
    static void need(boolean value,String label){if(!value)throw new AssertionError(label);}
    private void check(String name,Check action)throws Exception{
        activeCheck=name;
        Bundle start=new Bundle();start.putString("class",getClass().getName());start.putString("test",name);sendStatus(1,start);
        action.run();checks.put(new JSONObject().put("name",name).put("pass",true));sendStatus(0,start);
    }
    private AccessibilityNodeInfo find(AccessibilityNodeInfo node,Predicate<AccessibilityNodeInfo> test){
        if(node==null)return null;if(test.test(node))return node;
        for(int n=0;n<node.getChildCount();n++){AccessibilityNodeInfo child=node.getChild(n);AccessibilityNodeInfo found=find(child,test);if(found!=null){if(found!=child&&child!=null)child.recycle();return found;}if(child!=null)child.recycle();}return null;
    }
    private boolean act(Predicate<AccessibilityNodeInfo> match,java.util.function.Consumer<AccessibilityNodeInfo> action){
        AccessibilityNodeInfo root=getUiAutomation().getRootInActiveWindow();if(root==null)return false;AccessibilityNodeInfo found=null;
        try{found=find(root,match);if(found==null)return false;if(action!=null)action.accept(found);return true;}finally{if(found!=null&&found!=root)found.recycle();root.recycle();}
    }
    private void until(Predicate<AccessibilityNodeInfo> match,java.util.function.Consumer<AccessibilityNodeInfo> action,long milliseconds){
        long deadline=SystemClock.elapsedRealtime()+milliseconds;while(SystemClock.elapsedRealtime()<deadline){try{if(act(match,action))return;}catch(IllegalStateException stale){}SystemClock.sleep(80);}throw new AssertionError("UI target did not become ready");
    }
    private static String text(AccessibilityNodeInfo node){return node.getText()==null?"":node.getText().toString();}
    private static boolean id(AccessibilityNodeInfo node,String name){String value=node.getViewIdResourceName();return value!=null&&value.endsWith("/"+name);}
    private static String state(AccessibilityNodeInfo node){CharSequence value=android.os.Build.VERSION.SDK_INT>=30?node.getStateDescription():node.getContentDescription();return value==null?"":value.toString();}
    private JSONObject tree(AccessibilityNodeInfo node,int depth,int[] count)throws Exception{
        need(depth<=32&&++count[0]<=2048,"semantic tree bounds");Rect bounds=new Rect();node.getBoundsInScreen(bounds);JSONArray children=new JSONArray();
        for(int n=0;n<node.getChildCount();n++){AccessibilityNodeInfo child=node.getChild(n);if(child!=null){try{children.put(tree(child,depth+1,count));}finally{child.recycle();}}}
        return new JSONObject().put("class",String.valueOf(node.getClassName())).put("id",node.getViewIdResourceName()).put("text",text(node)).put("description",String.valueOf(node.getContentDescription())).put("state",state(node)).put("frame",node.getExtras().getString("exreader.frame","")).put("live_region",node.getLiveRegion()).put("actions",node.getActions()).put("visible",node.isVisibleToUser()).put("bounds",new JSONArray(new int[]{bounds.left,bounds.top,bounds.right,bounds.bottom})).put("children",children);
    }
    private void capture(String name)throws Exception{
        AccessibilityNodeInfo root=getUiAutomation().getRootInActiveWindow();need(root!=null,"semantic capture root");int[] count={0};JSONObject tree;
        try{tree=tree(root,0,count);}finally{root.recycle();}
        File folder=new File(context.getFilesDir(),"host-ui-captures");need(folder.isDirectory()||folder.mkdirs(),"capture folder");Bitmap image=getUiAutomation().takeScreenshot();need(image!=null,"semantic screenshot");try(FileOutputStream output=new FileOutputStream(new File(folder,name+".png"))){need(image.compress(Bitmap.CompressFormat.PNG,100,output),"screenshot bytes");}finally{image.recycle();}
        observations.put(new JSONObject().put("name",name).put("nodes",count[0]).put("font_scale",context.getResources().getConfiguration().fontScale).put("tree",tree));
    }
    private void click(String label){until(node->node.isEnabled()&&text(node).equalsIgnoreCase(label),this::tap,30000);}
    private void clickContains(String label){until(node->node.isEnabled()&&text(node).contains(label),this::tap,30000);}
    private void tap(AccessibilityNodeInfo node){
        Rect rect=new Rect();node.getBoundsInScreen(rect);need(rect.width()>0&&rect.height()>0,"UI action is visible");
        if(node.performAction(AccessibilityNodeInfo.ACTION_CLICK))return;
        long now=SystemClock.uptimeMillis();sendPointerSync(MotionEvent.obtain(now,now,MotionEvent.ACTION_DOWN,rect.centerX(),rect.centerY(),0));sendPointerSync(MotionEvent.obtain(now,now+30,MotionEvent.ACTION_UP,rect.centerX(),rect.centerY(),0));
    }
    private void field(String label,String value){until(node->label.contentEquals(node.getContentDescription()==null?"":node.getContentDescription()),node->{Bundle args=new Bundle();args.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,value);need(node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,args),"set UI field");},30000);}
    private void status(String value){until(node->"同步状态".contentEquals(node.getContentDescription()==null?"":node.getContentDescription())&&text(node).contains(value),null,120000);}
    private void detail(String value){until(node->"同步状态详情".contentEquals(node.getContentDescription()==null?"":node.getContentDescription())&&text(node).contains(value)&&node.getLiveRegion()==View.ACCESSIBILITY_LIVE_REGION_POLITE,null,120000);}
    private void panel(){click("More");click("同步");until(node->"同步状态".contentEquals(node.getContentDescription()==null?"":node.getContentDescription()),null,30000);need(!act(node->id(node,"import_button")||id(node,"more_button"),null),"native sync dialog hides background shelf");}
    private void settings(boolean saved)throws Exception{click("云盘账号");if(context.getSharedPreferences("reader-sync",0).getString("root","").isEmpty())field("云盘地址",input.getString("root"));field("云盘用户名",input.getString("user"));field("云盘密码",input.getString("password"));click(saved?"安全保存":"仅本次使用");status(saved?"凭据已安全保存":"仅本次使用凭据");}
    private void waitFile(String name)throws Exception{long end=SystemClock.elapsedRealtime()+60000;while(SystemClock.elapsedRealtime()<end){if(new File(context.getFilesDir(),name).isFile())return;SystemClock.sleep(80);}throw new AssertionError("fixture boundary not observed");}
    private void marker(String name)throws Exception{Files.write(new File(context.getFilesDir(),name).toPath(),new byte[]{1});}
    private void closed()throws Exception{long end=SystemClock.elapsedRealtime()+30000;while(SystemClock.elapsedRealtime()<end){if(NativeSyncProbe.sessions()==0)return;SystemClock.sleep(100);}throw new AssertionError("native session not destroyed after CLOSED");}
    private void launch(){context.startActivity(new Intent(context,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TOP));until(node->"More shelf actions".contentEquals(node.getContentDescription()==null?"":node.getContentDescription()),null,30000);}
    private int credential(){String id=context.getSharedPreferences("reader-sync",0).getString("account","");byte[] bytes=new byte[2048];int[] count={0};int result=CredentialStore.open(context,"org.exreader.reader.webdav").get(id,bytes,count);Arrays.fill(bytes,(byte)0);return result;}
    private void seed()throws Exception{
        File file=new File(context.getFilesDir(),"host-ui-local.txt");Files.write(file.toPath(),input.getString("local_text").getBytes(StandardCharsets.UTF_8));
        try(NativeLibrary library=new NativeLibrary(new File(context.getFilesDir(),"library.db").getAbsolutePath())){NativeLibrary.ImportResult imported=library.importFile(file.getAbsolutePath(),NativeLibrary.FORMAT_TXT,"UI local original");library.saveProgress(imported.id,8);need(context.getSharedPreferences("host",0).edit().putString("path_"+imported.id,file.getAbsolutePath()).putLong("size_"+imported.id,file.length()).commit(),"host-owned original path registered");}
    }
    private String sourceHash(NativeLibrary library,long id)throws Exception{MessageDigest digest=MessageDigest.getInstance("SHA-256");try(NativeLibrary.Source source=library.source(id)){byte[] chunk=new byte[65536];for(long at=0;at<source.size;){int count=source.read(at,chunk,(int)Math.min(chunk.length,source.size-at));need(count>0,"public source read");digest.update(chunk,0,count);at+=count;}}StringBuilder hash=new StringBuilder();for(byte value:digest.digest())hash.append(String.format(java.util.Locale.ROOT,"%02x",value&255));return hash.toString();}
    private void inspect()throws Exception{
        String[] identity=NativeLibrary.syncIdentity();need(identity.length==4&&identity[0].equals(arguments.getString("sdk_version","3.40.0"))&&identity[1].contains("libexreader.so")&&identity[2].equals(identity[1])&&identity[3].contains("libexreader_host.so"),"same shared public SDK provider");
        try(NativeLibrary library=new NativeLibrary(new File(context.getFilesDir(),"library.db").getAbsolutePath());CatalogStore catalog=new CatalogStore(context,new File(context.getFilesDir(),"reader-catalog.db"))){
            NativeLibrary.Book[] books=library.books();need(books.length==2,"exact original deduplication");long local=0,remote=0;for(NativeLibrary.Book book:books){if(book.format==NativeLibrary.FORMAT_TXT)local=book.id;else if(book.format==NativeLibrary.FORMAT_EPUB)remote=book.id;}
            need(local>0&&remote>0,"both SDK originals retained");long[] progress=library.progress(local);need(progress[0]==1&&progress[1]==8,"existing local progress unchanged");need(library.notes(local).length==0,"zero local SDK note copies");
            need(sourceHash(library,remote).equals(input.getString("remote_sha")),"public SDK remote original identity");CatalogStore.ShelfBook row=catalog.localShelfTitle(input.getString("remote_title"));need(row!=null&&row.sdkBookId==remote&&row.author.equals(input.getString("remote_author")),"remote metadata and mapping preserved");
            String[] provider=NativeCatalog.provider(catalog.nativeOwner());need(provider[3].contains("libexreader_product.so"),"product SQLite remains separate");
        }
    }
    private File originalCache()throws Exception{return new File(new File(context.getFilesDir(),"sync-cache"),input.getString("remote_sha")+".epub");}
    private void verifiedCache()throws Exception{long end=SystemClock.elapsedRealtime()+30000;while(SystemClock.elapsedRealtime()<end){File file=originalCache();if(file.isFile()&&BookStore.syncFileHash(file,new HostTask(()->false)).equals(input.getString("remote_sha")))return;SystemClock.sleep(80);}throw new AssertionError("verified remote cache never became available");}
    private boolean remoteFrame(AccessibilityNodeInfo node){try{return id(node,"reader_view")&&new JSONObject(node.getExtras().getString("exreader.frame","{}")).optString("source_key").equals("epub:"+input.getString("remote_sha"));}catch(Exception missing){return false;}}
    private void evict()throws Exception{Files.deleteIfExists(originalCache().toPath());need(!originalCache().exists(),"cache really absent");}
    private void getMode(String mode)throws Exception{Files.deleteIfExists(new File(context.getFilesDir(),"d22-get-blocked").toPath());Files.deleteIfExists(new File(context.getFilesDir(),"d22-get-release").toPath());Files.write(new File(context.getFilesDir(),"d22-get-mode").toPath(),mode.getBytes(StandardCharsets.UTF_8));}
    private void receiveRemote(){clickContains(input.optString("remote_title"));click("接收");}
    private void onlyLocal()throws Exception{try(NativeLibrary library=new NativeLibrary(new File(context.getFilesDir(),"library.db").getPath())){need(library.books().length==1,"failed receive cannot import SDK original");}}
    private void readRemote()throws Exception{
        click("关闭");clickContains(input.getString("remote_title"));
        until(this::remoteFrame,null,30000);
        capture("d22-remote-reading");click("Shelf");panel();
    }
    @Override public void onStart(){
        context=getTargetContext();phase=arguments.getString("phase");Bundle result=new Bundle();Throwable failure=null;
        try{
            AccessibilityServiceInfo service=getUiAutomation().getServiceInfo();service.flags|=AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS;getUiAutomation().setServiceInfo(service);
            String expectedSdk=arguments.getString("sdk_version","3.40.0");need(expectedSdk.equals("3.40.0")||expectedSdk.equals("3.41.0"),"supported expected SDK version");
            need(BuildConfig.READER_SYNC,"formal sync build enabled");File incoming=new File(context.getFilesDir(),"host-ui-input.json");input=new JSONObject(new String(Files.readAllBytes(incoming.toPath()),StandardCharsets.UTF_8));Files.delete(incoming.toPath());
            if(phase.equals("first")){
                check("initial_read_only_status",()->{seed();launch();panel();detail("尚未开始同步");});
                check("authentication_failure_visible",()->{
                    click("云盘账号");field("云盘地址",input.getString("root"));field("云盘用户名",input.getString("user"));field("云盘密码","incorrect-fixture-password");click("仅本次使用");status("仅本次使用凭据");
                    click("立即同步");status("凭据无效");detail("（failed）");detail("needs-credentials");
                    click("关闭");panel();detail("（failed）");click("刷新书目");detail("（failed）");
                });
                check("correct_credentials_cancel_and_retry",()->{
                    settings(true);need(credential()==CredentialStore.OK,"Keystore credential saved");
                    click("立即同步");waitFile("host-ui-put-blocked");detail("（syncing）");long before=SystemClock.elapsedRealtime();click("取消同步");need(SystemClock.elapsedRealtime()-before<2000,"cancel UI remains responsive");marker("host-ui-cancel-clicked");status("已取消");detail("（cancelled）");
                    click("立即同步");status("本轮同步结束");detail("（sweep-complete）");detail("一轮完成不等于整库已同步");
                });
                check("forget_keeps_binding",()->{click("云盘账号");click("移除凭据");click("移除");status("凭据已移除");closed();need(credential()==CredentialStore.NOT_FOUND,"credential removed");click("立即同步");status("请输入云盘凭据");});
            }else if(phase.equals("secure-reopen")){
                check("secure_credentials_and_originals_survive_process_restart",()->{need(credential()==CredentialStore.OK,"Keystore reopened");inspect();launch();panel();});
                check("offline_actual_reader_after_process_restart",()->{marker("d22-offline");readRemote();inspect();Files.deleteIfExists(new File(context.getFilesDir(),"d22-offline").toPath());});
                check("background_close_does_not_wait_on_ui",()->{click("立即同步");waitFile("host-ui-listing-blocked");long before=SystemClock.elapsedRealtime();getUiAutomation().executeShellCommand("input keyevent KEYCODE_HOME").close();marker("host-ui-background-requested");need(SystemClock.elapsedRealtime()-before<2000,"background UI nonblocking");closed();launch();panel();});
                check("manual_sync_after_background_reopens_owned_session",()->{click("立即同步");status("本轮同步结束");inspect();});
                check("forget_credentials_keeps_library_and_binding",()->{click("云盘账号");click("移除凭据");click("移除");status("凭据已移除");closed();need(credential()==CredentialStore.NOT_FOUND,"secure record removed");click("立即同步");status("请输入云盘凭据");inspect();});
                check("explicit_session_only_credentials",()->{settings(false);need(credential()==CredentialStore.NOT_FOUND,"no plaintext or encrypted persistent session credential");click("立即同步");status("本轮同步结束");click("断开");closed();});
            }else if(phase.equals("session-reopen")){
                check("session_only_credential_not_restored_after_kill",()->{need(credential()==CredentialStore.NOT_FOUND,"session secret absent after kill");launch();panel();click("立即同步");status("请输入云盘凭据");need(NativeSyncProbe.sessions()==0,"no unauthenticated native session");inspect();});
            }else if(phase.equals("semantics")){
                launch();
                check("polite_status_semantics",()->{click("Refresh");until(node->id(node,"status_text")&&node.getLiveRegion()==View.ACCESSIBILITY_LIVE_REGION_POLITE&&!text(node).isEmpty(),null,30000);capture("shelf-status");});
                check("organizer_hides_covered_shelf_semantics",()->{click("More");click("Organize");until(node->"Organize panel".contentEquals(node.getContentDescription()==null?"":node.getContentDescription()),null,30000);need(!act(node->id(node,"import_button")||id(node,"shelf_search")||id(node,"more_button"),null),"covered shelf controls removed from semantic tree");capture("organizer");click("Close");until(node->id(node,"import_button"),null,30000);});
                check("reader_semantic_scroll_changes_real_page",()->{
                    clickContains("UI local original");Predicate<AccessibilityNodeInfo> reader=node->ReaderView.class.getName().contentEquals(node.getClassName()==null?"":node.getClassName());String[] before={null};
                    until(reader,node->before[0]=String.valueOf(node.getContentDescription()),30000);capture("reader-before");
                    until(reader,node->{need((node.getActions()&AccessibilityNodeInfo.ACTION_SCROLL_FORWARD)!=0&&(node.getActions()&AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD)!=0,"both page actions exposed");need(node.performAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD),"forward semantic action");},30000);
                    until(node->reader.test(node)&&!String.valueOf(node.getContentDescription()).equals(before[0]),null,30000);capture("reader-after-forward");until(reader,node->need(node.performAction(AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD),"backward semantic action"),30000);
                    until(node->reader.test(node)&&String.valueOf(node.getContentDescription()).equals(before[0]),null,30000);
                });
                check("font_value_and_large_font_controls",()->{
                    click("Select");until(node->id(node,"reader_status")&&node.getLiveRegion()==View.ACCESSIBILITY_LIVE_REGION_POLITE&&!text(node).isEmpty(),null,30000);click("Selecting");
                    String[] before={null};until(node->id(node,"font_up")&&!state(node).isEmpty(),node->before[0]=state(node),30000);until(node->id(node,"font_up"),this::tap,30000);until(node->id(node,"font_up")&&!state(node).isEmpty()&&!state(node).equals(before[0]),null,30000);
                    capture("reader-toolbar");
                    getUiAutomation().executeShellCommand("settings put system font_scale 2.0").close();long deadline=SystemClock.elapsedRealtime()+30000;while(context.getResources().getConfiguration().fontScale<1.9f&&SystemClock.elapsedRealtime()<deadline)SystemClock.sleep(100);need(context.getResources().getConfiguration().fontScale>=1.9f,"real system font scale changed");
                    until(node->id(node,"font_up")&&!state(node).isEmpty(),node->{Rect bounds=new Rect();node.getBoundsInScreen(bounds);need(bounds.width()>0&&bounds.height()>0,"font control visible at large system font");},30000);
                    click("Shelf");click("More");click("Organize");until(node->"Organize panel".contentEquals(node.getContentDescription()==null?"":node.getContentDescription()),null,30000);need(!act(node->id(node,"import_button")||id(node,"more_button"),null),"large font organizer keeps shelf hidden");capture("large-font-organizer");click("Close");
                });
            }else throw new AssertionError("unknown phase");
        }catch(Throwable error){failure=error;if("semantics".equals(phase))try{capture("failure");}catch(Throwable captureError){error.addSuppressed(captureError);}}
        finally{if("semantics".equals(phase))try{getUiAutomation().executeShellCommand("settings put system font_scale 1.0").close();}catch(Exception ignored){}}
        try{
            JSONObject report=new JSONObject().put("source_sha",arguments.getString("source_sha")).put("run_id",arguments.getString("run_id")).put("attempt",arguments.getString("attempt")).put("expected_sdk_version",arguments.getString("sdk_version","3.40.0")).put("phase",phase).put("pid",android.os.Process.myPid()).put("api",android.os.Build.VERSION.SDK_INT).put("abi",android.os.Build.SUPPORTED_ABIS[0]).put("passed",failure==null).put("checks",checks).put("count",checks.length()).put("observations",observations);
            if(failure!=null)report.put("failed_check",activeCheck).put("failure_class",failure.getClass().getName()).put("failure",failure.getMessage());
            Files.write(new File(context.getFilesDir(),"host-ui-"+phase+".json").toPath(),report.toString(2).getBytes(StandardCharsets.UTF_8));
            result.putString("stream",failure==null?"HOST_SYNC_UI_PASS "+phase:"HOST_SYNC_UI_FAIL "+phase);finish(failure==null?Activity.RESULT_OK:Activity.RESULT_CANCELED,result);
        }catch(Exception error){result.putString("shortMsg","UI evidence unavailable");finish(Activity.RESULT_CANCELED,result);}
    }
}
