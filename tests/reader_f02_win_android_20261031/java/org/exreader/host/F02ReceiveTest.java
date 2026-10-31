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
    interface Check {void run() throws Exception;}
    @Override public void onCreate(Bundle args){super.onCreate(args);arguments=args;start();}
    static void need(boolean value,String reason){if(!value)throw new AssertionError(reason);}
    private void check(String name,Check action)throws Exception{
        activeCheck=name;Bundle status=new Bundle();status.putString("class",getClass().getName());status.putString("test",name);sendStatus(1,status);
        action.run();checks.put(new JSONObject().put("name",name).put("passed",true));sendStatus(0,status);
    }
    private Object field(Object target,String name)throws Exception{
        Field f=target.getClass().getDeclaredField(name);f.setAccessible(true);return f.get(target);
    }
    private <T>T owner(Callable<T> action)throws Exception{
        ExecutorService worker=(ExecutorService)field(activity,"worker");
        need(worker!=null&&!worker.isShutdown(),"actual SDK owner available");
        return worker.submit(action).get(45,TimeUnit.SECONDS);
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
        throw new AssertionError("Actual UI target did not become ready");
    }
    private static String text(AccessibilityNodeInfo node){return node.getText()==null?"":node.getText().toString();}
    private static boolean id(AccessibilityNodeInfo node,String name){String value=node.getViewIdResourceName();return value!=null&&value.endsWith("/"+name);}
    private void tap(AccessibilityNodeInfo node){
        Rect r=new Rect();node.getBoundsInScreen(r);need(r.width()>0&&r.height()>0,"visible UI action");
        if(node.performAction(AccessibilityNodeInfo.ACTION_CLICK))return;
        long t=SystemClock.uptimeMillis();sendPointerSync(MotionEvent.obtain(t,t,MotionEvent.ACTION_DOWN,r.centerX(),r.centerY(),0));sendPointerSync(MotionEvent.obtain(t,t+30,MotionEvent.ACTION_UP,r.centerX(),r.centerY(),0));
    }
    private void click(String value){until(n->n.isEnabled()&&text(n).equalsIgnoreCase(value),this::tap,30000);}
    private void clickTitle()throws Exception{String title=input.getString("title");until(n->n.isEnabled()&&text(n).contains(title),this::tap,30000);}
    private void set(String description,String value){until(n->description.contentEquals(n.getContentDescription()==null?"":n.getContentDescription()),n->{Bundle b=new Bundle();b.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,value);need(n.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,b),"actual field edit");},30000);}
    private void status(String value){until(n->"同步状态".contentEquals(n.getContentDescription()==null?"":n.getContentDescription())&&text(n).contains(value),null,120000);}
    private void panel(){click("More");click("同步");until(n->"同步状态".contentEquals(n.getContentDescription()==null?"":n.getContentDescription()),null,30000);}
    private File file(String name){return new File(context.getFilesDir(),name);}
    private void marker(String name)throws Exception{Files.write(file(name).toPath(),new byte[]{1});}
    private void waitFile(String name)throws Exception{long end=SystemClock.elapsedRealtime()+30000;while(SystemClock.elapsedRealtime()<end){if(file(name).isFile())return;SystemClock.sleep(80);}throw new AssertionError("Native request boundary not observed");}
    private File cache()throws Exception{return file("sync-cache/"+input.getString("sha256")+".txt");}
    private void receive()throws Exception{clickTitle();click("接收");}
    private void mode(String value)throws Exception{
        Files.deleteIfExists(file("f02-get-blocked").toPath());Files.deleteIfExists(file("f02-get-release").toPath());
        Files.write(file("f02-get-mode").toPath(),value.getBytes(StandardCharsets.UTF_8));
    }
    private void empty()throws Exception{need(owner(()->store().nativeLibrary().books().length)==0,"failed receive cannot import an original");need(!cache().exists(),"failed receive cannot publish cache");}
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
        check("corrupt_original_rejected",()->{mode("corrupt");receive();status("完整性校验失败");empty();});
        check("truncated_original_rejected",()->{mode("truncate");receive();status("原件下载未完成");empty();});
        check("cancel_blocked_receive_preserves_empty_library",()->{
            mode("block");receive();waitFile("f02-get-blocked");long before=SystemClock.elapsedRealtime();click("取消同步");need(SystemClock.elapsedRealtime()-before<2000,"cancel remains responsive");marker("f02-get-release");status("已取消");empty();
        });
        check("explicit_receive_imports_exact_original",()->{
            receive();status("书籍已接收");need(cache().isFile()&&cache().length()==input.getLong("bytes")&&hash(cache()).equals(input.getString("sha256")),"exact HTTPS cache");
            need(owner(()->store().nativeLibrary().books().length)==1,"real receive imports once");
        });
        check("duplicate_receive_keeps_one_sdk_mapping",()->{receive();status("书籍已接收");need(owner(()->store().nativeLibrary().books().length)==1,"no duplicate SDK book");});
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
        }catch(Throwable error){failure=error;}
        finally{
            try{
                JSONObject report=new JSONObject().put("identity",new JSONObject().put("source",arguments.getString("source")).put("run",Long.parseLong(arguments.getString("run"))).put("attempt",Integer.parseInt(arguments.getString("attempt"))))
                    .put("phase",phase).put("pid",android.os.Process.myPid()).put("uid",android.os.Process.myUid()).put("sdk_version","3.42.0").put("passed",failure==null).put("checks",checks).put("count",checks.length()).put("observed",observed);
                if(failure!=null)report.put("failure_type",failure.getClass().getSimpleName()).put("active_check",activeCheck);
                Files.write(file("f02-report-"+phase+".json").toPath(),report.toString(2).getBytes(StandardCharsets.UTF_8));
                result.putString("stream","F02_ANDROID "+phase+" checks="+checks.length()+" passed="+(failure==null)+"\n");
            }catch(Exception e){result.putString("stream","F02 report could not be written\n");failure=e;}
            finish(failure==null?Activity.RESULT_OK:Activity.RESULT_CANCELED,result);
        }
    }
}
