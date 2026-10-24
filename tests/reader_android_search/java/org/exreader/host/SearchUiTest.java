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
public final class SearchUiTest extends Instrumentation {
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
    private void contains(String label){until(node->id(node,"text1")&&node.isVisibleToUser()&&node.isEnabled()&&text(node).contains(label),this::tap,"result "+label,30000);}
    private String searchStatus(){String[] value={null};act(node->description(node,"搜索状态"),node->value[0]=text(node));return value[0];}
    private void status(String value){until(node->description(node,"搜索状态")&&text(node).contains(value),null,"search status "+value,120000);}
    private void panel(){until(node->description(node,"阅读更多操作")&&node.isEnabled(),this::tap,"reading More",30000);click("书内搜索");until(node->description(node,"书内搜索词"),null,"search input",30000);}
    private void start(String value){
        until(node->description(node,"书内搜索词")&&node.isEnabled(),node->{Bundle args=new Bundle();args.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,value);need(node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,args),"set actual search input");},"set search input",30000);click("搜索");
    }
    private String settled(){long end=SystemClock.elapsedRealtime()+120000;while(SystemClock.elapsedRealtime()<end){String value=searchStatus();if(value!=null&&!value.equals("正在搜索")&&!value.equals("正在定位")&&!value.startsWith("输入文字后"))return value;SystemClock.sleep(80);}throw new AssertionError("search did not settle: "+active);}
    private void search(String value){start(value);settled();}
    private void zero(){long end=SystemClock.elapsedRealtime()+30000;while(SystemClock.elapsedRealtime()<end){if(NativeSearchProbe.live()==0)return;SystemClock.sleep(50);}throw new AssertionError("search native handle did not close");}
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
    private void launch(){context.startActivity(new Intent(context,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TOP).putExtra("exr_search_gate",true));}
    private long book(String role)throws Exception{return books.getJSONObject(role).getLong("id");}
    private void open(String role)throws Exception {
        if(act(node->description(node,"搜索状态"),null)){click("关闭");zero();}
        if(act(node->id(node,"back_button"),null))click("Shelf");
        until(node->id(node,"import_button"),null,"shelf restored",30000);String title=books.getJSONObject(role).getString("title");
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
                JSONObject row=originals.getJSONObject(i);File file=new File(context.getFilesDir(),"search-fixtures/"+row.getString("file"));need(file.length()==row.getLong("bytes"),"seed original length");
                NativeLibrary.ImportResult result=library.importFile(file.getAbsolutePath(),format(row.getString("format")),row.getString("title"));need(hash(library,result.id).equals(row.getString("sha256")),"SDK original fixture identity");
                String title=null;for(NativeLibrary.Book found:library.books())if(found.id==result.id)title=found.title;
                need(title!=null,"SDK book after import");books.put(row.getString("role"),new JSONObject().put("id",result.id).put("title",title).put("sha256",row.getString("sha256")).put("format",row.getString("format")));
                need(context.getSharedPreferences("host",0).edit().putString("path_"+result.id,file.getAbsolutePath()).putLong("size_"+result.id,file.length()).commit(),"host original path registered");
            }
            library.saveProgress(book("txt"),0);library.saveNote(book("txt"),0,0,0,"retained existing SDK note");
        }
        Files.write(new File(context.getFilesDir(),"search-books.json").toPath(),books.toString().getBytes(StandardCharsets.UTF_8));
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
    private void gate()throws Exception {for(String name:new String[]{"search-gate-arrived","search-gate-release","search-gate-arm"})Files.deleteIfExists(new File(context.getFilesDir(),name).toPath());Files.write(new File(context.getFilesDir(),"search-gate-arm").toPath(),new byte[]{1});}
    private void arrived()throws Exception {long end=SystemClock.elapsedRealtime()+30000;while(SystemClock.elapsedRealtime()<end){if(new File(context.getFilesDir(),"search-gate-arrived").isFile()){need(NativeSearchProbe.live()==1,"real installed Search call owns its handle at control boundary");return;}SystemClock.sleep(30);}throw new AssertionError("installed search control boundary not observed");}
    private void choose(String label)throws Exception {JSONObject before=frame();long token=before.getLong("accepted_token"),book=before.getLong("book");contains(label);until(node->id(node,"reader_view"),null,"reader after explicit FOUND selection",120000);long end=SystemClock.elapsedRealtime()+120000;while(SystemClock.elapsedRealtime()<end){JSONObject after=frame();if(after.optLong("book",-1)==book&&after.optLong("accepted_token",0)>token){zero();return;}SystemClock.sleep(80);}throw new AssertionError("FOUND selection did not publish a new real page");}
    private void closePanel(){click("关闭");zero();}
    private void readonlyQuery(String query,String status)throws Exception {String state=snapshot(),page=stableFrame();panel();search(query);status(status);unchanged(state,page);closePanel();unchanged(state,page);}
    private JSONObject tree(AccessibilityNodeInfo node,int depth,int[] count)throws Exception {
        need(depth<=32&&++count[0]<=2048,"semantic tree bounds");JSONArray children=new JSONArray();for(int i=0;i<node.getChildCount();i++){AccessibilityNodeInfo child=node.getChild(i);if(child!=null){try{children.put(tree(child,depth+1,count));}finally{child.recycle();}}}
        return new JSONObject().put("id",node.getViewIdResourceName()).put("text",text(node)).put("description",String.valueOf(node.getContentDescription())).put("actions",node.getActions()).put("children",children);
    }
    private void capture(String name)throws Exception {
        AccessibilityNodeInfo root=getUiAutomation().getRootInActiveWindow();need(root!=null,"search capture root");int[] count={0};JSONObject value;try{value=tree(root,0,count);}finally{root.recycle();}
        File folder=new File(context.getFilesDir(),"search-captures");need(folder.isDirectory()||folder.mkdirs(),"search captures directory");Bitmap image=getUiAutomation().takeScreenshot();need(image!=null,"search screenshot");try(FileOutputStream output=new FileOutputStream(new File(folder,name+".png"))){need(image.compress(Bitmap.CompressFormat.PNG,100,output),"PNG written");}finally{image.recycle();}
        JSONObject observation=new JSONObject().put("name",name).put("nodes",count[0]).put("tree",value);try{observation.put("frame",frame());}catch(AssertionError absent){}observations.put(observation);
    }
    private static Object invoke(Method method,Object...arguments)throws Exception {try{return method.invoke(null,arguments);}catch(InvocationTargetException wrapped){Throwable error=wrapped.getCause();if(error instanceof Exception)throw (Exception)error;throw new AssertionError(error);}}
    private void boundaries()throws Exception {
        Method version=NativeSearch.class.getDeclaredMethod("nativeVersion"),open=NativeSearch.class.getDeclaredMethod("nativeOpen",long.class,long.class,int.class,String.class,String.class,byte[].class,float.class,NativeSearch.Control.class),next=NativeSearch.class.getDeclaredMethod("nativeNext",long.class,int.class,NativeSearch.Control.class),close=NativeSearch.class.getDeclaredMethod("nativeClose",long.class),resolve=NativeSearch.class.getDeclaredMethod("nativeResolve",long.class,long.class,int.class,long.class,long.class,long.class,String[].class,byte[][].class,byte[].class,float.class,HostTask.class);
        for(Method method:new Method[]{version,open,next,close,resolve})method.setAccessible(true);
        byte[] font;try(java.io.InputStream stream=context.getAssets().open("Reader.otf");java.io.ByteArrayOutputStream out=new java.io.ByteArrayOutputStream()){byte[] chunk=new byte[65536];for(int count;(count=stream.read(chunk))>0;)out.write(chunk,0,count);font=out.toByteArray();}
        try(NativeLibrary library=new NativeLibrary(new File(context.getFilesDir(),"library.db").getAbsolutePath())){
            HostTask task=new HostTask(()->false);NativeSearch.Control control=new NativeSearch.Control(task,context.getFilesDir(),false);String parser=(String)invoke(version),key="txt:"+books.getJSONObject("txt").getString("sha256")+"|exreader-sdk-"+parser;
            for(String invalid:new String[]{"","\0","\ud800","中".repeat(1366)}){boolean refused=false;try{long handle=(Long)invoke(open,library.checked(),book("txt"),NativeSearch.REFLOW,key,invalid,font,24f,control);if(handle!=0)invoke(close,handle);}catch(IllegalArgumentException|NativeSearch.Failure expected){refused=true;}need(refused,"JNI rejects empty/NUL/unpaired/oversized UTF-8 query");need(NativeSearchProbe.live()==0,"failed open retains no source handle");}
            long handle=(Long)invoke(open,library.checked(),book("txt"),NativeSearch.REFLOW,key,"Z-hit 249",font,24f,control);need(handle!=0,"installed module opens through JNI");
            try{
                boolean refused=false;try{invoke(next,handle,0,control);}catch(IllegalArgumentException expected){refused=true;}need(refused,"bounded JNI batch limit enforced");
                final long borrowedHandle=handle;AtomicReference<Throwable> wrong=new AtomicReference<>();Thread thread=new Thread(()->{try{invoke(next,borrowedHandle,1,control);}catch(Throwable error){wrong.set(error);}});thread.start();thread.join(5000);need(!thread.isAlive()&&wrong.get() instanceof IllegalArgumentException,"native handle refuses another thread before SDK access");
                NativeSearch.Batch batch=(NativeSearch.Batch)invoke(next,handle,32,control);need(batch.hits.length==1,"refused owner/limit calls did not advance cursor");NativeSearch.Hit hit=batch.hits[0];
                byte[][] altered=hit.bytes();altered[0]="missing immutable quote".getBytes(StandardCharsets.UTF_8);refused=false;try{invoke(resolve,library.checked(),book("txt"),hit.mode,hit.unit,hit.start,hit.end,hit.route(),altered,font,24f,task);}catch(NativeSearch.Failure expected){refused=expected.code==4&&expected.sdk==1;}need(refused,"selector range and quote length mismatch is refused by public SDK");
                altered=hit.bytes();Arrays.fill(altered[0],(byte)'!');long[] missing=(long[])invoke(resolve,library.checked(),book("txt"),hit.mode,hit.unit,hit.start,hit.end,hit.route(),altered,font,24f,task);need(missing[0]==0&&missing[2]==-1&&missing[3]==-1,"valid missing selector never falls back to offsets");
                altered[0]=new byte[]{0};refused=false;try{invoke(resolve,library.checked(),book("txt"),hit.mode,hit.unit,hit.start,hit.end,hit.route(),altered,font,24f,task);}catch(NativeSearch.Failure expected){refused=true;}need(refused,"reflow C-string selector refuses embedded NUL without truncation");
            }finally{invoke(close,handle);}
            key="pdf:"+books.getJSONObject("pdf").getString("sha256")+"|exreader-sdk-"+parser;handle=(Long)invoke(open,library.checked(),book("pdf"),NativeSearch.FIXED,key,"Fixed page four.",font,24f,control);
            try{NativeSearch.Hit hit=((NativeSearch.Batch)invoke(next,handle,32,control)).hits[0];byte[][] nul=hit.bytes();need(nul[0].length>1,"fixed quote has explicit bytes");nul[0][0]=0;long[] value=(long[])invoke(resolve,library.checked(),book("pdf"),hit.mode,hit.unit,hit.start,hit.end,hit.route(),nul,font,24f,task);need(value[0]==0&&value[2]==-1,"fixed selector explicit NUL bytes preserved as missing, not empty-prefix FOUND");String[] route=hit.route();route[2]="missing-page-id";value=(long[])invoke(resolve,library.checked(),book("pdf"),hit.mode,hit.unit,hit.start,hit.end,route,hit.bytes(),font,24f,task);need(value[0]==0&&value[1]==-1,"missing fixed ID never guesses from page hint");}finally{invoke(close,handle);}
        }
        zero();
    }
    @Override public void onStart(){
        context=getTargetContext();phase=arguments.getString("phase");Throwable failure=null;Bundle result=new Bundle();
        try{
            AccessibilityServiceInfo service=getUiAutomation().getServiceInfo();readerMonitor=addMonitor(MainActivity.class.getName(),null,false);service.flags|=AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS|AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS;getUiAutomation().setServiceInfo(service);
            need(BuildConfig.READER_SEARCH&&BuildConfig.READER_SYNC,"feature-on formal app");input=new JSONObject(new String(Files.readAllBytes(new File(context.getFilesDir(),"search-input.json").toPath()),StandardCharsets.UTF_8));expected=input.getJSONObject("expected");
            if(phase.equals("first")){
                seed();launch();
                check("installed_search_and_same_shared_sdk_provider",()->{open("txt");String[] identity=NativeSearchProbe.identity(),sdk=NativeLibrary.syncIdentity();need(identity.length==3&&identity[0].equals(sdk[1])&&identity[0].contains("libexreader.so")&&identity[1].contains("libexreader_host.so")&&identity[2].equals("0.1.0"),"actual shared SDK and installed search archive provider");});
                check("txt_bounded_batches_preserve_source_notes_progress_outbox_and_page",()->{String state=snapshot(),page=stableFrame();panel();search(expected.getString("txt_many_query"));int total=0,batches=0;while(true){String value=settled();need(value.matches("[0-9]+ 个结果.*"),"literal results status");int count=Integer.parseInt(value.substring(0,value.indexOf(' ')));need(count>0&&count<=32,"one bounded batch");total+=count;batches++;unchanged(state,page);if(value.contains("已搜索完毕"))break;need(batches<16,"bounded continuation terminates");click("更多结果");}need(total==expected.getInt("txt_many_count")&&batches==8,"all 250 ordered literal hits in eight bounded batches");capture("txt-results");closePanel();});
                check("unicode_query_and_explicit_empty_result_preserve_reader",()->{readonlyQuery(expected.getString("txt_unicode_query"),"2 个结果");readonlyQuery("THIS_LITERAL_DOES_NOT_OCCUR","没有找到匹配文字");});
                check("invalid_query_reports_error_without_touching_stores",()->{String state=snapshot(),page=stableFrame();panel();click("搜索");status("请输入有效的搜索词");unchanged(state,page);search("中".repeat(1366));status("请输入有效的搜索词");need(NativeSearchProbe.live()==0,"invalid query opens no native search");unchanged(state,page);closePanel();});
                check("ambiguous_selection_keeps_list_page_and_stored_progress",()->{String state=snapshot(),page=stableFrame();panel();search(expected.getString("txt_ambiguous_query"));status("2 个结果");contains(expected.getString("txt_ambiguous_query"));status("位置有歧义，未跳转");unchanged(state,page);capture("ambiguous");closePanel();});
                check("txt_explicit_found_selection_navigates_real_page",()->{String state=snapshot(),page=stableFrame();panel();search(expected.getString("txt_unique_query"));status("1 个结果");unchanged(state,page);choose(expected.getString("txt_unique_query"));JSONObject frame=waitFrame(book("txt"));need(frame.getInt("index")>0&&frame.getLong("start")>0&&frame.getLong("selection_start")>=frame.getLong("start"),"FOUND result changes actual rendered page");capture("txt-found");});
                check("bounded_epub_unique_and_repeated_spine_routes",()->{open("epub");String state=snapshot(),page=stableFrame();panel();search(expected.getString("epub_unique_query"));status("1 个结果");unchanged(state,page);choose("第 2 章");need(waitFrame(book("epub")).getInt("part")==1,"real second bounded chapter selected");long oldToken=frame().getLong("accepted_token");until(node->id(node,"font_up")&&node.isEnabled(),this::tap,"increase real EPUB font",30000);long fontDeadline=SystemClock.elapsedRealtime()+120000;while(SystemClock.elapsedRealtime()<fontDeadline){JSONObject changed=frame();if(changed.optLong("accepted_token",0)>oldToken&&changed.optDouble("font",0)==28)break;SystemClock.sleep(80);}need(frame().optDouble("font",0)==28&&frame().optLong("accepted_token",0)>oldToken,"real EPUB layout changed to 28 before search");panel();search(expected.getString("epub_repeated_query"));status("2 个结果");choose("第 3 章");need(waitFrame(book("epub")).getInt("part")==2,"repeated path uses explicit spine index");capture("epub-found");});
                check("pdf_text_found_and_textless_pdf_empty_are_distinct",()->{open("pdf");String state=snapshot(),page=stableFrame();panel();search(expected.getString("pdf_unique_query"));status("1 个结果");unchanged(state,page);choose("第 4 页");need(waitFrame(book("pdf")).getInt("index")==3,"PDF ID-resolved fourth page rendered");capture("pdf-found");open("blank");readonlyQuery(expected.getString("blank_query"),"没有找到匹配文字");});
                check("cbz_is_explicitly_unsupported_not_empty",()->{open("cbz");String state=snapshot(),page=stableFrame();panel();search("any text");status("此格式不支持文字搜索（CBZ）");need(NativeSearchProbe.live()==0,"no CBZ text search handle");unchanged(state,page);capture("cbz-unsupported");closePanel();});
                check("jni_query_selector_byte_and_owner_boundaries",()->{String state=snapshot(),page=stableFrame();boundaries();unchanged(state,page);});
                check("cancel_real_installed_search_control_then_retry",()->{open("long");String state=snapshot(),page=stableFrame();panel();gate();start(expected.getString("long_query"));arrived();long before=SystemClock.elapsedRealtime();click("取消搜索");need(SystemClock.elapsedRealtime()-before<2000,"cancel action does not wait for SDK worker");status("已取消");zero();unchanged(state,page);search("P0000");status("1 个结果");unchanged(state,page);closePanel();});
                check("close_real_control_releases_and_reopens_search",()->{String state=snapshot(),page=stableFrame();panel();gate();start(expected.getString("long_query"));arrived();click("关闭");zero();unchanged(state,page);panel();search("P0001");status("1 个结果");unchanged(state,page);closePanel();});
                check("background_closes_control_and_manual_reopen_is_clean",()->{String state=snapshot();panel();gate();start(expected.getString("long_query"));arrived();getUiAutomation().executeShellCommand("input keyevent KEYCODE_HOME").close();zero();need(snapshot().equals(state),"background search cancellation leaves stores unchanged");launch();waitFrame(book("long"));panel();until(node->description(node,"书内搜索词")&&emptyInput(node),null,"empty reopened query",30000);closePanel();Files.write(new File(context.getFilesDir(),"search-reopen-baseline.json").toPath(),snapshot().getBytes(StandardCharsets.UTF_8));});
            }else if(phase.equals("reopen")){
                books=new JSONObject(new String(Files.readAllBytes(new File(context.getFilesDir(),"search-books.json").toPath()),StandardCharsets.UTF_8));
                check("process_reopen_has_no_search_and_preserves_original_stores",()->{need(NativeSearchProbe.live()==0,"native search not restored across process");String baseline=new String(Files.readAllBytes(new File(context.getFilesDir(),"search-reopen-baseline.json").toPath()),StandardCharsets.UTF_8);need(snapshot().equals(baseline),"SDK originals notes progress and product queues survive process restart");launch();waitFrame(book("long"));panel();until(node->description(node,"书内搜索词")&&emptyInput(node),null,"query starts empty after process restart",30000);closePanel();});
                check("real_search_after_process_restart",()->{open("txt");readonlyQuery(expected.getString("txt_unicode_query"),"2 个结果");capture("reopened-reader");});
            }else throw new AssertionError("Unknown search UI phase");
        }catch(Throwable error){failure=error;try{capture("failure");}catch(Throwable captureError){error.addSuppressed(captureError);}}
        try{
            JSONObject report=new JSONObject().put("source_sha",arguments.getString("source_sha")).put("run_id",arguments.getString("run_id")).put("attempt",arguments.getString("attempt")).put("phase",phase).put("pid",android.os.Process.myPid()).put("passed",failure==null).put("checks",checks).put("count",checks.length()).put("observations",observations).put("native_live",NativeSearchProbe.live());
            if(failure!=null){report.put("failed_check",active).put("failure_class",failure.getClass().getName()).put("failure",failure.getMessage()).put("failure_trace",android.util.Log.getStackTraceString(failure));if(failure instanceof NativeSearch.Failure){NativeSearch.Failure nativeFailure=(NativeSearch.Failure)failure;report.put("failure_module_code",nativeFailure.code).put("failure_sdk_code",nativeFailure.sdk);}}
            Files.write(new File(context.getFilesDir(),"search-ui-"+phase+".json").toPath(),report.toString(2).getBytes(StandardCharsets.UTF_8));
            result.putString("stream",failure==null?"SEARCH_UI_PASS "+phase:"SEARCH_UI_FAIL "+phase);finish(failure==null?Activity.RESULT_OK:Activity.RESULT_CANCELED,result);
        }catch(Exception error){result.putString("shortMsg","Search UI evidence unavailable");finish(Activity.RESULT_CANCELED,result);}
    }
}
