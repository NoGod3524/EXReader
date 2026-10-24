// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.app.Activity;
import android.app.Instrumentation;
import android.accessibilityservice.AccessibilityServiceInfo;
import android.content.Context;
import android.content.Intent;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.graphics.Bitmap;
import android.graphics.Rect;
import android.os.Bundle;
import android.os.SystemClock;
import android.view.MotionEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityWindowInfo;
import java.io.File;
import java.io.FileOutputStream;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Consumer;
import java.util.function.Predicate;
import org.json.JSONArray;
import org.json.JSONObject;

/** Actual controls over the installed module; only negative JNI checks use reflection. */
public final class NavigationUiTest extends Instrumentation {
    private Bundle arguments;private Context context;private JSONObject input,books,expected;private ActivityMonitor readerMonitor;
    private final JSONArray checks=new JSONArray(),observations=new JSONArray();private String phase,active;
    interface Check {void run()throws Exception;}
    @Override public void onCreate(Bundle args){super.onCreate(args);arguments=args;start();}
    static void need(boolean condition,String message){if(!condition)throw new AssertionError(message);}
    private void check(String name,Check action)throws Exception {
        active=name;Bundle report=new Bundle();report.putString("class",getClass().getName());report.putString("test",name);sendStatus(1,report);
        action.run();checks.put(new JSONObject().put("name",name).put("pass",true));sendStatus(0,report);
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
    static String text(AccessibilityNodeInfo node){return node.getText()==null?"":node.getText().toString();}
    static boolean id(AccessibilityNodeInfo node,String value){return node.getViewIdResourceName()!=null&&node.getViewIdResourceName().endsWith("/"+value);}
    static boolean description(AccessibilityNodeInfo node,String value){return value.contentEquals(node.getContentDescription()==null?"":node.getContentDescription());}
    static boolean emptyInput(AccessibilityNodeInfo node){return node.isShowingHintText()||text(node).isEmpty();}
    private void tap(AccessibilityNodeInfo node){
        if(node.performAction(AccessibilityNodeInfo.ACTION_CLICK))return;Rect rect=new Rect();node.getBoundsInScreen(rect);need(rect.width()>0&&rect.height()>0,"visible click target");
        long now=SystemClock.uptimeMillis();sendPointerSync(MotionEvent.obtain(now,now,MotionEvent.ACTION_DOWN,rect.centerX(),rect.centerY(),0));sendPointerSync(MotionEvent.obtain(now,now+30,MotionEvent.ACTION_UP,rect.centerX(),rect.centerY(),0));
    }
    private void click(String label){until(node->node.isVisibleToUser()&&node.isEnabled()&&text(node).equalsIgnoreCase(label),this::tap,"click "+label,30000);}
    private void result(String label,boolean select){long end=SystemClock.elapsedRealtime()+30000;while(SystemClock.elapsedRealtime()<end){if(act(node->id(node,"text1")&&node.isVisibleToUser()&&node.isEnabled()&&text(node).contains(label),select?this::tap:null))return;act(node->description(node,"目录条目"),node->node.performAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD));SystemClock.sleep(100);}throw new AssertionError("Actual visible directory row missing: "+label);}
    private void contains(String label){result(label,true);}
    private String searchStatus(){String[] value={null};act(node->description(node,"目录状态"),node->value[0]=text(node));return value[0];}
    private void status(String value){until(node->description(node,"目录状态")&&text(node).contains(value),null,"search status "+value,120000);}
    private void panel(){until(node->description(node,"阅读更多操作")&&node.isEnabled(),this::tap,"reading More",30000);click("目录 / 按页入口");until(node->description(node,"目录状态"),null,"navigation status",30000);}
    private void zero(){long end=SystemClock.elapsedRealtime()+30000;while(SystemClock.elapsedRealtime()<end){if(NativeNavigationProbe.live()==0)return;SystemClock.sleep(50);}throw new AssertionError("search native handle did not close");}
    private JSONObject frame()throws Exception {
        java.util.List<AccessibilityWindowInfo> windows=getUiAutomation().getWindows();try{for(AccessibilityWindowInfo window:windows){
            AccessibilityNodeInfo root=window.getRoot(),node=null;
            try{node=find(root,value->id(value,"reader_view"));if(node!=null){String value=node.getExtras().getString("exreader.frame","");if(!value.isEmpty())return new JSONObject(value);}}
            finally{if(node!=null&&node!=root)node.recycle();if(root!=null)root.recycle();}
        }}finally{for(AccessibilityWindowInfo window:windows)window.recycle();}
        // A modal dialog can occlude its owner from AccessibilityWindowInfo. Read
        // the same live view's accessibility extras on the UI thread in that case.
        AtomicReference<String> observed=new AtomicReference<>();
        runOnMainSync(()->{Activity activity=readerMonitor.getLastActivity();if(activity!=null){android.view.View view=activity.findViewById(org.exreader.host.R.id.reader_view);if(view!=null){AccessibilityNodeInfo info=view.createAccessibilityNodeInfo();try{observed.set(info.getExtras().getString("exreader.frame",""));}finally{info.recycle();}}}});
        String actual=observed.get();if(actual!=null&&!actual.isEmpty())return new JSONObject(actual);
        throw new AssertionError("actual ReaderView frame unavailable");
    }
    private JSONObject waitFrame(long book)throws Exception {long end=SystemClock.elapsedRealtime()+120000;while(SystemClock.elapsedRealtime()<end){try{JSONObject value=frame();if(value.optLong("book",-1)==book&&value.has("bitmap_identity"))return value;}catch(AssertionError notReady){}SystemClock.sleep(80);}throw new AssertionError("real book frame not ready");}
    private String stableFrame()throws Exception {
        JSONObject source=frame(),value=new JSONObject();for(String key:new String[]{"book","index","part","path","start","end","font","accepted_token"})value.put(key,source.opt(key));
        value.put("bitmap",source.getJSONObject("bitmap_identity").getString("logical_argb_sha256"));return value.toString();
    }
    private void launch(){context.startActivity(new Intent(context,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TOP).putExtra("exr_navigation_gate",true));}
    private long book(String role)throws Exception{return books.getJSONObject(role).getLong("id");}
    private void open(String role)throws Exception {
        if(act(node->description(node,"目录状态"),null)){click("关闭");zero();}
        until(node->node.isVisibleToUser()&&((id(node,"back_button")&&node.isEnabled())||id(node,"import_button")),node->{if(id(node,"back_button"))tap(node);},"reader or shelf ready after modal close",30000);
        until(node->node.isVisibleToUser()&&id(node,"import_button"),null,"shelf restored",30000);String title=books.getJSONObject(role).getString("title");
        until(node->node.isEnabled()&&(text(node).equals(title)||text(node).startsWith(title+"\n")),this::tap,"book "+title,30000);waitFrame(book(role));
    }
    private static String hash(NativeLibrary library,long id)throws Exception {
        MessageDigest digest=MessageDigest.getInstance("SHA-256");try(NativeLibrary.Source source=library.source(id)){byte[] chunk=new byte[65536];for(long at=0;at<source.size;){int count=source.read(at,chunk,(int)Math.min(chunk.length,source.size-at));need(count>0,"public original read");digest.update(chunk,0,count);at+=count;}}
        StringBuilder out=new StringBuilder();for(byte value:digest.digest())out.append(String.format(Locale.ROOT,"%02x",value&255));return out.toString();
    }
    private int format(String value){switch(value){case "txt":return NativeLibrary.FORMAT_TXT;case "epub":return NativeLibrary.FORMAT_EPUB;case "pdf":return NativeLibrary.FORMAT_PDF;case "cbz":return NativeLibrary.FORMAT_CBZ;default:throw new AssertionError("fixture format");}}
    private void seed()throws Exception {
        books=new JSONObject();try(NativeLibrary library=new NativeLibrary(new File(context.getFilesDir(),"library.db").getAbsolutePath())){
            JSONArray originals=input.getJSONArray("books");for(int i=0;i<originals.length();i++){
                JSONObject row=originals.getJSONObject(i);File file=new File(context.getFilesDir(),"navigation-fixtures/"+row.getString("file"));need(file.length()==row.getLong("bytes"),"seed original length");
                NativeLibrary.ImportResult result=library.importFile(file.getAbsolutePath(),format(row.getString("format")),row.getString("title"));need(hash(library,result.id).equals(row.getString("sha256")),"SDK original fixture identity");
                String title=null;for(NativeLibrary.Book found:library.books())if(found.id==result.id)title=found.title;
                need(title!=null,"SDK book after import");books.put(row.getString("role"),new JSONObject().put("id",result.id).put("title",title).put("sha256",row.getString("sha256")).put("format",row.getString("format")));
                need(context.getSharedPreferences("host",0).edit().putString("path_"+result.id,file.getAbsolutePath()).putLong("size_"+result.id,file.length()).commit(),"host original path registered");
            }
            library.saveFixedNote(book("pdf"),0,0,0,4,"retained navigation SDK note");
        }
        Files.write(new File(context.getFilesDir(),"navigation-books.json").toPath(),books.toString().getBytes(StandardCharsets.UTF_8));
    }
    private String snapshot()throws Exception {
        JSONObject result=new JSONObject();JSONArray rows=new JSONArray();
        try(NativeLibrary library=new NativeLibrary(new File(context.getFilesDir(),"library.db").getAbsolutePath())){
            NativeLibrary.Book[] items=library.books();Arrays.sort(items,(a,b)->Long.compare(a.id,b.id));need(items.length==6,"six exact originals retained");
            for(NativeLibrary.Book value:items){JSONObject row=new JSONObject().put("id",value.id).put("format",value.format).put("title",value.title).put("position",value.position).put("favorite",value.favorite).put("status",value.status).put("source_sha256",hash(library,value.id));JSONArray notes=new JSONArray();
                if(value.fixed()){for(NativeLibrary.FixedNote note:library.fixedNotes(value.id))notes.put(new JSONArray().put(note.id).put(note.page).put(note.start).put(note.end).put(note.comment).put(note.selected));}
                else{for(NativeLibrary.Note note:library.notes(value.id))notes.put(new JSONArray().put(note.id).put(note.start).put(note.end).put(note.comment).put(note.selected));if(value.format==NativeLibrary.FORMAT_EPUB&&library.bounded(value.id))row.put("progress",BoundedEpub.progressIdentity(library,value.id));else row.put("progress",new JSONArray(library.progress(value.id)));}
                row.put("notes",notes);rows.put(row);
            }
        }
        result.put("sdk",rows);try(SQLiteDatabase product=SQLiteDatabase.openDatabase(new File(context.getFilesDir(),"reader-catalog.db").getAbsolutePath(),null,SQLiteDatabase.OPEN_READONLY)){
            for(String table:new String[]{"reader_revisions","reader_outbox"}){JSONArray values=new JSONArray();try(Cursor cursor=product.rawQuery("SELECT * FROM "+table+" ORDER BY revision_id",null)){while(cursor.moveToNext()){JSONArray row=new JSONArray();for(int i=0;i<cursor.getColumnCount();i++)row.put(cursor.isNull(i)?JSONObject.NULL:cursor.getType(i)==Cursor.FIELD_TYPE_BLOB?android.util.Base64.encodeToString(cursor.getBlob(i),android.util.Base64.NO_WRAP):cursor.getString(i));values.put(row);}}result.put(table,values);}
        }
        return result.toString();
    }
    private void unchanged(String state,String page)throws Exception{need(snapshot().equals(state),"source/SDK notes/progress/product revisions/outbox unchanged");need(stableFrame().equals(page),"reader page and pixels unchanged while searching");}
    private void gate()throws Exception {for(String name:new String[]{"navigation-gate-arrived","navigation-gate-release","navigation-gate-arm"})Files.deleteIfExists(new File(context.getFilesDir(),name).toPath());Files.write(new File(context.getFilesDir(),"navigation-gate-arm").toPath(),new byte[]{1});}
    private void arrived()throws Exception {long end=SystemClock.elapsedRealtime()+30000;while(SystemClock.elapsedRealtime()<end){if(new File(context.getFilesDir(),"navigation-gate-arrived").isFile()){need(NativeNavigationProbe.live()==1,"real installed Search call owns its handle at control boundary");return;}SystemClock.sleep(30);}throw new AssertionError("installed search control boundary not observed");}
    private void choose(String label)throws Exception {JSONObject before=frame();long token=before.getLong("accepted_token"),book=before.getLong("book");contains(label);until(node->id(node,"reader_view"),null,"reader after explicit FOUND selection",120000);long end=SystemClock.elapsedRealtime()+120000;while(SystemClock.elapsedRealtime()<end){JSONObject after=frame();if(after.optLong("book",-1)==book&&after.optLong("accepted_token",0)>token){zero();return;}SystemClock.sleep(80);}throw new AssertionError("FOUND selection did not publish a new real page");}
    private void closePanel(){click("关闭");zero();}
    private JSONObject tree(AccessibilityNodeInfo node,int depth,int[] count)throws Exception {
        need(depth<=32&&++count[0]<=2048,"semantic tree bounds");JSONArray children=new JSONArray();for(int i=0;i<node.getChildCount();i++){AccessibilityNodeInfo child=node.getChild(i);if(child!=null){try{children.put(tree(child,depth+1,count));}finally{child.recycle();}}}
        return new JSONObject().put("id",node.getViewIdResourceName()).put("text",text(node)).put("description",String.valueOf(node.getContentDescription())).put("actions",node.getActions()).put("children",children);
    }
    private void capture(String name)throws Exception {
        AccessibilityNodeInfo root=getUiAutomation().getRootInActiveWindow();need(root!=null,"search capture root");int[] count={0};JSONObject value;try{value=tree(root,0,count);}finally{root.recycle();}
        File folder=new File(context.getFilesDir(),"navigation-captures");need(folder.isDirectory()||folder.mkdirs(),"search captures directory");Bitmap image=getUiAutomation().takeScreenshot();need(image!=null,"search screenshot");try(FileOutputStream output=new FileOutputStream(new File(folder,name+".png"))){need(image.compress(Bitmap.CompressFormat.PNG,100,output),"PNG written");}finally{image.recycle();}
        JSONObject observation=new JSONObject().put("name",name).put("nodes",count[0]).put("tree",value);try{observation.put("frame",frame());}catch(AssertionError absent){}observations.put(observation);
    }
    private static Object invoke(Method method,Object...arguments)throws Exception {try{return method.invoke(null,arguments);}catch(InvocationTargetException wrapped){Throwable error=wrapped.getCause();if(error instanceof Exception)throw (Exception)error;throw new AssertionError(error);}}
    private void ready(){long end=SystemClock.elapsedRealtime()+120000;while(SystemClock.elapsedRealtime()<end){String[] value={null};act(node->description(node,"目录状态"),node->value[0]=text(node));if(value[0]!=null&&(value[0].startsWith("目录 ·")||value[0].startsWith("按页入口")||value[0].equals("此书没有自带目录")))return;SystemClock.sleep(80);}throw new AssertionError("real directory did not become ready");}
    private void directory(){panel();ready();}
    private void firstTarget(){contains("First & chapter");click("打开此目标");}
    private void row(int index){long end=SystemClock.elapsedRealtime()+30000;while(SystemClock.elapsedRealtime()<end){int[] found={0};if(act(node->id(node,"text1")&&node.isVisibleToUser()&&found[0]++==index,this::tap))return;SystemClock.sleep(80);}throw new AssertionError("visible page row "+index+" unavailable");}
    private void jumped(long token,String role)throws Exception {until(node->id(node,"reader_view")&&node.isVisibleToUser(),null,"actual reader after directory selection",120000);long end=SystemClock.elapsedRealtime()+120000;while(SystemClock.elapsedRealtime()<end){JSONObject value=frame();if(value.optLong("book",-1)==book(role)&&value.optLong("accepted_token",0)>token){zero();return;}SystemClock.sleep(80);}throw new AssertionError("directory selection did not publish a real frame");}
    private String cfi(int mode)throws Exception {try(NativeLibrary library=new NativeLibrary(new File(context.getFilesDir(),"library.db").getAbsolutePath())){return NativeNavigationProbe.cfi(library.checked(),book("nav"),mode);}}
    private void inputCfi(String value){click("CFI 位置");until(node->description(node,"EPUB CFI"),node->{Bundle args=new Bundle();args.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,value);need(node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,args),"set actual CFI input");},"CFI input",30000);click("定位");}
    private void boundaryChecks()throws Exception {
        Method open=NativeNavigation.class.getDeclaredMethod("nativeOpen",long.class,long.class,int.class,String.class,byte[].class,NativeNavigation.Control.class),info=NativeNavigation.class.getDeclaredMethod("nativeInfo",long.class),page=NativeNavigation.class.getDeclaredMethod("nativePage",long.class,long.class,long.class,int.class),resolve=NativeNavigation.class.getDeclaredMethod("nativeResolve",long.class,long.class,long.class,int.class,String.class,long.class,long.class,String.class,byte[].class,NativeNavigation.Control.class),close=NativeNavigation.class.getDeclaredMethod("nativeClose",long.class);for(Method method:new Method[]{open,info,page,resolve,close})method.setAccessible(true);
        byte[] font;try(java.io.InputStream stream=context.getAssets().open("Reader.otf")){font=stream.readAllBytes();}
        try(NativeLibrary library=new NativeLibrary(new File(context.getFilesDir(),"library.db").getAbsolutePath())){
            String key="epub:"+books.getJSONObject("nav").getString("sha256")+"@exreader-sdk-"+NativeNavigation.nativeParser();HostTask task=new HostTask(()->false);NativeNavigation.Control control=new NativeNavigation.Control(task,context.getFilesDir(),false);long handle=(Long)invoke(open,library.checked(),book("nav"),NativeNavigation.PUBLICATION,key,font,control);need(handle!=0,"installed navigation opens through JNI");
            try{long[] before=(long[])invoke(info,handle);need(before[3]==expected.getInt("nav_total_rows"),"actual SDK snapshot has all 48 rows");for(Object[] invalid:new Object[][]{{handle,-2L,0L,32},{handle,-1L,-1L,32},{handle,-1L,0L,0},{handle,-1L,0L,33}}){boolean refused=false;try{invoke(page,invalid);}catch(IllegalArgumentException error){refused=true;}need(refused,"invalid native page boundary refused");}
                AtomicReference<Throwable> wrong=new AtomicReference<>();Thread other=new Thread(()->{try{invoke(info,handle);}catch(Throwable error){wrong.set(error);}});other.start();other.join(5000);need(!other.isAlive()&&wrong.get() instanceof IllegalArgumentException,"snapshot refuses another thread");need(Arrays.equals(before,(long[])invoke(info,handle)),"owner snapshot unchanged after refusal");
                NativeNavigation.Result mismatch=new NativeNavigation.Result((String[][])invoke(resolve,handle,library.checked(),book("nav"),NativeNavigation.PUBLICATION,key+"-wrong",0L,-1L,null,font,control));need(mismatch.status==11&&mismatch.offset<0,"wrong original/parser key cannot produce a destination");
                NativeNavigation.Result explicit=new NativeNavigation.Result((String[][])invoke(resolve,handle,library.checked(),book("nav"),NativeNavigation.PUBLICATION,key,0L,1L,null,font,control));need(explicit.status==11&&explicit.offset<0,"wrong explicit spine identity refused without a destination");
            }finally{invoke(close,handle);}
        }zero();
    }
    @Override public void onStart(){
        context=getTargetContext();phase=arguments.getString("phase");Throwable failure=null;Bundle result=new Bundle();
        try{
            readerMonitor=addMonitor(MainActivity.class.getName(),null,false);AccessibilityServiceInfo service=getUiAutomation().getServiceInfo();service.flags|=AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS|AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS;getUiAutomation().setServiceInfo(service);
            need(BuildConfig.READER_NAVIGATION&&BuildConfig.READER_SEARCH&&BuildConfig.READER_SYNC,"formal optional navigation/search/sync enabled");input=new JSONObject(new String(Files.readAllBytes(new File(context.getFilesDir(),"navigation-input.json").toPath()),StandardCharsets.UTF_8));expected=input.getJSONObject("expected");
            if(phase.equals("first")){
                seed();launch();
                check("installed_navigation_and_single_shared_sdk_provider",()->{open("nav");String[] identity=NativeNavigationProbe.identity(),sdk=NativeLibrary.syncIdentity();need(identity.length==3&&identity[0].equals(sdk[1])&&identity[0].contains("libexreader.so")&&identity[1].contains("libexreader_host.so")&&identity[2].equals("0.1.0"),"actual installed navigation and original shared SDK provider");});
                check("root_pagination_and_read_only_directory_preserve_actual_frame_and_stores",()->{String state=snapshot(),before=stableFrame();directory();status("45 项 · 本批 32 项");unchanged(state,before);click("下一批条目");status("45 项 · 本批 13 项 · 已列完");unchanged(state,before);capture("paginated-directory");closePanel();unchanged(state,before);});
                check("hierarchy_unicode_fragment_selects_independently_verified_part",()->{directory();contains("First & chapter");click("查看子项");status("1 项");long token=frame().getLong("accepted_token");contains("子节 🙂");jumped(token,"nav");need(frame().getInt("part")==1,"real Unicode-path fragment navigates to second spine");capture("nested-fragment-found");open("ncx");directory();contains("First & chapter");click("查看子项");long ncxToken=frame().getLong("accepted_token");contains("子节 🙂");jumped(ncxToken,"ncx");need(frame().getInt("part")==1,"real EPUB2 NCX fragment route rendered");capture("ncx-fragment-found");open("nav");});
                check("external_targets_do_not_launch_or_change_reader",()->{String state=snapshot(),before=stableFrame();directory();contains("Group");click("查看子项");contains("Outside");status("外部目标，未打开");unchanged(state,before);closePanel();unchanged(state,before);directory();contains("Mail");status("外部目标，未打开");unchanged(state,before);closePanel();});
                check("part_only_requires_explicit_start_confirmation",()->{directory();String state=snapshot(),before=stableFrame();contains("Chapter");until(node->text(node).equals("仅打开章节开头"),null,"PART_ONLY confirmation",30000);need(stableFrame().equals(before)&&snapshot().equals(state),"PART_ONLY never jumps before explicit acceptance");click("不跳转");unchanged(state,before);contains("Chapter");long token=frame().getLong("accepted_token");click("仅打开章节开头");jumped(token,"nav");need(frame().getInt("part")==2&&frame().getLong("start")==0,"explicit PART_ONLY starts verified chapter only");capture("part-only-confirmed");});
                check("unresolved_and_container_escape_never_guess",()->{String state=snapshot(),before=stableFrame();directory();contains("Missing");status("目标无法匹配");unchanged(state,before);contains("Escape");status("目标无法匹配");unchanged(state,before);closePanel();});
                check("plain_label_and_empty_authored_navigation",()->{directory();result("<script>alert(1)</script> label",false);closePanel();open("empty");String state=snapshot(),before=stableFrame();directory();status("此书没有自带目录");unchanged(state,before);capture("empty-directory");closePanel();});
                check("repeated_spine_needs_explicit_identity_and_never_first_match",()->{open("repeated");directory();String state=snapshot(),before=stableFrame();contains("First");click("打开此目标");until(node->text(node).equals("第 2 章"),null,"both repeated spine candidates",30000);need(snapshot().equals(state)&&stableFrame().equals(before),"ambiguous route did not auto-select");click("不跳转");unchanged(state,before);contains("First");click("打开此目标");long token=frame().getLong("accepted_token");click("第 2 章");jumped(token,"repeated");need(frame().getInt("part")==1,"explicit second repeated path selected");capture("repeated-spine-explicit");});
                check("full_cfi_from_public_sdk_resolves_again_and_navigates",()->{open("nav");directory();long token=frame().getLong("accepted_token");inputCfi(cfi(0));jumped(token,"nav");need(frame().getInt("part")==1,"actual independent CFI route rendered");capture("cfi-found");});
                check("surrogate_collapsed_and_corrupt_cfi_stay_unmoved",()->{String state=snapshot(),before=stableFrame();directory();for(int kind:new int[]{1,2}){inputCfi(cfi(kind));status("无法精确映射此 CFI 位置，未跳转");unchanged(state,before);}inputCfi("epubcfi(broken)");status("目标无法匹配");unchanged(state,before);capture("cfi-refused");closePanel();});
                check("pdf_pages_are_not_authored_outline",()->{open("pdf");String state=snapshot(),before=stableFrame();directory();status("按页入口 · 非作者大纲 · 3 页");need(!act(node->text(node).contains("Authored Outline Title"),null),"PDF author outline never exposed");unchanged(state,before);long token=frame().getLong("accepted_token");row(2);jumped(token,"pdf");need(frame().getInt("index")==2,"verified PDF page ID selects real third page");capture("pdf-by-page");});
                check("cbz_pages_use_actual_page_ids",()->{open("cbz");directory();status("按页入口 · 非作者大纲 · 3 页");long token=frame().getLong("accepted_token");row(1);jumped(token,"cbz");need(frame().getInt("index")==1,"verified CBZ page ID selects real second page");capture("cbz-by-page");});
                check("jni_boundaries_thread_and_verified_identity_are_enforced",()->{String state=snapshot(),before=stableFrame();boundaryChecks();unchanged(state,before);});
                check("cancel_real_resolve_then_close_and_retry_is_clean",()->{open("nav");String state=snapshot(),before=stableFrame();directory();gate();firstTarget();arrived();long began=SystemClock.elapsedRealtime();click("取消读取");need(SystemClock.elapsedRealtime()-began<2000,"cancel action does not wait for SDK worker");status("已取消");unchanged(state,before);closePanel();directory();status("45 项");unchanged(state,before);closePanel();});
                check("close_and_actual_rotation_cancel_stale_results",()->{String state=snapshot(),before=stableFrame();directory();gate();firstTarget();arrived();closePanel();unchanged(state,before);directory();gate();firstTarget();arrived();long oldView=frame().getLong("view");need(getUiAutomation().setRotation(android.app.UiAutomation.ROTATION_FREEZE_90),"actual device rotation requested");zero();long end=SystemClock.elapsedRealtime()+120000;while(SystemClock.elapsedRealtime()<end){try{JSONObject actual=frame();if(actual.getLong("book")==book("nav")&&actual.getLong("view")!=oldView&&actual.has("bitmap_identity"))break;}catch(AssertionError ignored){}SystemClock.sleep(80);}need(frame().getLong("view")!=oldView,"rotation created a fresh actual reader view");need(snapshot().equals(state),"rotation cancelled target without changing originals notes progress or product queues");capture("rotated-reader");long rotatedView=frame().getLong("view");getUiAutomation().setRotation(android.app.UiAutomation.ROTATION_FREEZE_0);long resetEnd=SystemClock.elapsedRealtime()+120000;while(SystemClock.elapsedRealtime()<resetEnd){try{JSONObject restored=frame();if(restored.optLong("book",-1)==book("nav")&&restored.optLong("view",rotatedView)!=rotatedView&&restored.has("bitmap_identity"))break;}catch(AssertionError ignored){}SystemClock.sleep(80);}need(frame().getLong("view")!=rotatedView,"reset rotation restored a fresh actual reader");});
                check("background_releases_snapshot_and_manual_reopen_starts_at_root",()->{String state=snapshot();directory();gate();firstTarget();arrived();getUiAutomation().executeShellCommand("input keyevent KEYCODE_HOME").close();zero();need(snapshot().equals(state),"background rejects stale result without stores changes");launch();waitFrame(book("nav"));directory();status("45 项 · 本批 32 项");closePanel();Files.write(new File(context.getFilesDir(),"navigation-reopen-baseline.json").toPath(),snapshot().getBytes(StandardCharsets.UTF_8));});
            }else if(phase.equals("reopen")){
                books=new JSONObject(new String(Files.readAllBytes(new File(context.getFilesDir(),"navigation-books.json").toPath()),StandardCharsets.UTF_8));
                check("process_reopen_has_no_snapshot_or_stale_destination",()->{need(NativeNavigationProbe.live()==0,"no native navigation snapshot restored");String baseline=new String(Files.readAllBytes(new File(context.getFilesDir(),"navigation-reopen-baseline.json").toPath()),StandardCharsets.UTF_8);need(snapshot().equals(baseline),"all stores retained across actual process restart");launch();waitFrame(book("nav"));directory();status("45 项 · 本批 32 项");closePanel();});
                check("real_navigation_works_after_process_restart",()->{directory();long token=frame().getLong("accepted_token");contains("First & chapter");click("查看子项");contains("子节 🙂");jumped(token,"nav");need(frame().getInt("part")==1,"actual navigation after process restart");capture("reopened-navigation");});
            }else throw new AssertionError("Unknown navigation phase");
        }catch(Throwable error){failure=error;try{capture("failure");}catch(Throwable captureError){error.addSuppressed(captureError);}}
        try{
            JSONObject report=new JSONObject().put("source_sha",arguments.getString("source_sha")).put("run_id",arguments.getString("run_id")).put("attempt",arguments.getString("attempt")).put("phase",phase).put("pid",android.os.Process.myPid()).put("passed",failure==null).put("checks",checks).put("count",checks.length()).put("observations",observations).put("native_live",NativeNavigationProbe.live());
            if(failure!=null){report.put("failed_check",active).put("failure_class",failure.getClass().getName()).put("failure",failure.getMessage()).put("failure_trace",android.util.Log.getStackTraceString(failure));if(failure instanceof NativeNavigation.Failure){NativeNavigation.Failure nativeFailure=(NativeNavigation.Failure)failure;report.put("failure_module_code",nativeFailure.code).put("failure_sdk_code",nativeFailure.sdk);}}
            Files.write(new File(context.getFilesDir(),"navigation-ui-"+phase+".json").toPath(),report.toString(2).getBytes(StandardCharsets.UTF_8));result.putString("stream",failure==null?"NAVIGATION_UI_PASS "+phase:"NAVIGATION_UI_FAIL "+phase);finish(failure==null?Activity.RESULT_OK:Activity.RESULT_CANCELED,result);
        }catch(Exception error){result.putString("shortMsg","Navigation evidence unavailable");finish(Activity.RESULT_CANCELED,result);}
    }
}
