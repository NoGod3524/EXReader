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
public final class FixedPanUiTest extends Instrumentation {
    private Bundle arguments;private Context context;private JSONObject input,books,expected;private ActivityMonitor readerMonitor;
    private final JSONArray checks=new JSONArray(),observations=new JSONArray();private String phase,active;
    interface Check {void run()throws Exception;}
    @Override public void onCreate(Bundle args){super.onCreate(args);arguments=args;start();}
    static void need(boolean condition,String message){if(!condition)throw new AssertionError(message);}
    private void onMain(Runnable action){
        AtomicReference<Throwable> failure=new AtomicReference<>();
        runOnMainSync(()->{try{action.run();}catch(Throwable error){failure.set(error);}});
        Throwable error=failure.get();
        if(error instanceof Error)throw (Error)error;
        if(error instanceof RuntimeException)throw (RuntimeException)error;
        if(error!=null)throw new RuntimeException(error);
    }
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
        if(node.performAction(AccessibilityNodeInfo.ACTION_CLICK))return;touch(node);
    }
    private void touch(AccessibilityNodeInfo node){Rect rect=new Rect();node.getBoundsInScreen(rect);need(rect.width()>0&&rect.height()>0,"visible touch target");long now=SystemClock.uptimeMillis();sendPointerSync(MotionEvent.obtain(now,now,MotionEvent.ACTION_DOWN,rect.centerX(),rect.centerY(),0));SystemClock.sleep(50);sendPointerSync(MotionEvent.obtain(now,SystemClock.uptimeMillis(),MotionEvent.ACTION_UP,rect.centerX(),rect.centerY(),0));}
    private void click(String label){until(node->node.isVisibleToUser()&&node.isEnabled()&&text(node).equalsIgnoreCase(label),this::tap,"click "+label,30000);}
    private void contains(String label){until(node->id(node,"text1")&&node.isVisibleToUser()&&node.isEnabled()&&text(node).contains(label),this::tap,"result "+label,30000);}
    private String searchStatus(){String[] value={null};act(node->description(node,"阅读记录状态"),node->value[0]=text(node));return value[0];}
    private void status(String value){until(node->description(node,"阅读记录状态")&&text(node).contains(value),null,"search status "+value,120000);}
    private void panel(){until(node->description(node,"阅读更多操作")&&node.isEnabled(),this::tap,"reading More",30000);click("阅读记录");status(" 条记录");}
    private JSONObject frame()throws Exception {
        java.util.List<AccessibilityWindowInfo> windows=getUiAutomation().getWindows();try{for(AccessibilityWindowInfo window:windows){
            AccessibilityNodeInfo root=window.getRoot(),node=null;
            try{node=find(root,value->id(value,"reader_view"));if(node!=null){String value=node.getExtras().getString("exreader.frame","");if(!value.isEmpty())return new JSONObject(value);}}
            finally{if(node!=null&&node!=root)node.recycle();if(root!=null)root.recycle();}
        }}finally{for(AccessibilityWindowInfo window:windows)window.recycle();}
        // A modal dialog can occlude its owner from AccessibilityWindowInfo. Read
        // the same live view's accessibility extras on the UI thread in that case.
        AtomicReference<String> observed=new AtomicReference<>();
        onMain(()->{Activity activity=readerMonitor.getLastActivity();if(activity!=null){android.view.View view=activity.findViewById(org.exreader.host.R.id.reader_view);if(view!=null){AccessibilityNodeInfo info=view.createAccessibilityNodeInfo();try{observed.set(info.getExtras().getString("exreader.frame",""));}finally{info.recycle();}}}});
        String actual=observed.get();if(actual!=null&&!actual.isEmpty())return new JSONObject(actual);
        throw new AssertionError("actual ReaderView frame unavailable");
    }
    private JSONObject waitFrame(long book)throws Exception {long end=SystemClock.elapsedRealtime()+120000;while(SystemClock.elapsedRealtime()<end){try{JSONObject value=frame();if(value.optLong("book",-1)==book&&value.has("bitmap_identity"))return value;}catch(AssertionError notReady){}SystemClock.sleep(80);}throw new AssertionError("real book frame not ready");}
    private String stableFrame()throws Exception {
        JSONObject source=frame(),value=new JSONObject();for(String key:new String[]{"book","index","part","path","start","end","font","accepted_token"})value.put(key,source.opt(key));
        value.put("bitmap",source.getJSONObject("bitmap_identity").getString("logical_argb_sha256"));return value.toString();
    }
    private void launch(){context.startActivity(new Intent(context,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TOP).putExtra("exr_reading_gate",true));}
    private long book(String role)throws Exception{return books.getJSONObject(role).getLong("id");}
    private void open(String role)throws Exception {
        if(act(node->description(node,"阅读记录状态"),null)){click("关闭");}
        until(node->node.isVisibleToUser()&&((id(node,"back_button")&&node.isEnabled())||id(node,"import_button")),node->{if(id(node,"back_button"))tap(node);},"reader or shelf ready after modal close",30000);
        until(node->node.isVisibleToUser()&&id(node,"import_button"),null,"shelf restored",30000);String title=books.getJSONObject(role).getString("title");
        until(node->id(node,"shelf_search")&&node.isVisibleToUser()&&node.isEnabled(),node->{Bundle args=new Bundle();args.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,title);need(node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,args),"filter actual shelf for exact book");},"actual shelf filter",30000);
        long wanted=book(role),deadline=SystemClock.elapsedRealtime()+30000;String expectedKey=key(role);boolean ready=false;while(SystemClock.elapsedRealtime()<deadline){AtomicReference<Boolean> settled=new AtomicReference<>(false);onMain(()->{try{CatalogShelf shelf=(CatalogShelf)ReadingReview.field(activity(),"catalogShelf");android.widget.ListView list=activity().findViewById(R.id.book_list);android.view.View row=list.getChildCount()==1?list.getChildAt(0):null;JSONObject observed=new JSONObject(shelf.observation());settled.set(observed.getString("query").equals(title)&&!observed.getBoolean("loading")&&observed.getLong("generation")==observed.getLong("applied_generation")&&shelf.getCount()==1&&shelf.getItemId(0)==wanted&&list.isEnabled()&&row!=null&&row.isShown()&&row.isLaidOut()&&row.getHeight()>0&&!list.isLayoutRequested()&&expectedKey.equals(row.getTag()));}catch(Exception error){throw new RuntimeException(error);}});if(settled.get()){ready=true;break;}SystemClock.sleep(60);}need(ready,"exact shelf book identity loaded and actually laid out before click");
        until(node->id(node,"text1")&&node.isVisibleToUser()&&node.isEnabled()&&(text(node).equals(title)||text(node).startsWith(title+"\n")),this::touch,"book "+title,30000);waitFrame(wanted);
    }
    private static String hash(NativeLibrary library,long id)throws Exception {
        MessageDigest digest=MessageDigest.getInstance("SHA-256");try(NativeLibrary.Source source=library.source(id)){byte[] chunk=new byte[65536];for(long at=0;at<source.size;){int count=source.read(at,chunk,(int)Math.min(chunk.length,source.size-at));need(count>0,"public original read");digest.update(chunk,0,count);at+=count;}}
        StringBuilder out=new StringBuilder();for(byte value:digest.digest())out.append(String.format(Locale.ROOT,"%02x",value&255));return out.toString();
    }
    private int format(String value){switch(value){case "txt":return NativeLibrary.FORMAT_TXT;case "epub":return NativeLibrary.FORMAT_EPUB;case "pdf":return NativeLibrary.FORMAT_PDF;case "cbz":return NativeLibrary.FORMAT_CBZ;default:throw new AssertionError("fixture format");}}
    private void seed()throws Exception {
        books=new JSONObject();try(NativeLibrary library=new NativeLibrary(new File(context.getFilesDir(),"library.db").getAbsolutePath())){
            JSONArray originals=input.getJSONArray("books");for(int i=0;i<originals.length();i++){
                JSONObject row=originals.getJSONObject(i);File file=new File(context.getFilesDir(),"fixed-pan-fixtures/"+row.getString("file"));need(file.length()==row.getLong("bytes"),"seed original length");
                NativeLibrary.ImportResult result=row.getString("role").equals("legacy")?library.importLegacyFile(file.getAbsolutePath(),format(row.getString("format")),row.getString("title")):library.importFile(file.getAbsolutePath(),format(row.getString("format")),row.getString("title"));need(hash(library,result.id).equals(row.getString("sha256")),"SDK original fixture identity");
                String title=null;for(NativeLibrary.Book found:library.books())if(found.id==result.id)title=found.title;
                need(title!=null,"SDK book after import");books.put(row.getString("role"),new JSONObject().put("id",result.id).put("title",title).put("sha256",row.getString("sha256")).put("format",row.getString("format")));
                need(context.getSharedPreferences("host",0).edit().putString("path_"+result.id,file.getAbsolutePath()).putLong("size_"+result.id,file.length()).commit(),"host original path registered");
            }
            library.saveProgress(book("txt"),0);library.saveNote(book("txt"),0,0,0,"retained existing SDK note");
        }
        Files.write(new File(context.getFilesDir(),"fixed-pan-books.json").toPath(),books.toString().getBytes(StandardCharsets.UTF_8));
    }
    private String snapshot()throws Exception {
        JSONObject result=new JSONObject();JSONArray rows=new JSONArray();
        try(NativeLibrary library=new NativeLibrary(new File(context.getFilesDir(),"library.db").getAbsolutePath())){
            NativeLibrary.Book[] items=library.books();Arrays.sort(items,(a,b)->Long.compare(a.id,b.id));need(items.length==input.getJSONArray("books").length(),"every exact declared original retained");
            for(NativeLibrary.Book value:items){JSONObject row=new JSONObject().put("id",value.id).put("format",value.format).put("title",value.title).put("position",value.position).put("favorite",value.favorite).put("status",value.status).put("source_sha256",hash(library,value.id));JSONArray notes=new JSONArray();
                if(value.fixed()){for(NativeLibrary.FixedNote note:library.fixedNotes(value.id))notes.put(new JSONArray().put(note.id).put(note.page).put(note.start).put(note.end).put(note.comment).put(note.selected));}
                else if(value.format==NativeLibrary.FORMAT_EPUB&&library.bounded(value.id)){for(NativeLibrary.Note note:library.notes(value.id))notes.put(new JSONArray().put(note.id).put(note.start).put(note.end).put(note.comment).put(note.selected));row.put("progress",BoundedEpub.progressIdentity(library,value.id));}
                else{for(NativeLibrary.Note note:library.notes(value.id))notes.put(new JSONArray().put(note.id).put(note.start).put(note.end).put(note.comment).put(note.selected));row.put("progress",new JSONArray(library.progress(value.id)));}
                row.put("notes",notes);rows.put(row);
            }
        }
        result.put("sdk",rows);try(SQLiteDatabase product=SQLiteDatabase.openDatabase(new File(context.getFilesDir(),"reader-catalog.db").getAbsolutePath(),null,SQLiteDatabase.OPEN_READONLY)){
            for(String table:new String[]{"reader_revisions","reader_outbox"}){JSONArray values=new JSONArray();try(Cursor cursor=product.rawQuery("SELECT * FROM "+table+" ORDER BY revision_id",null)){while(cursor.moveToNext()){JSONArray row=new JSONArray();for(int i=0;i<cursor.getColumnCount();i++)row.put(cursor.isNull(i)?JSONObject.NULL:cursor.getType(i)==Cursor.FIELD_TYPE_BLOB?android.util.Base64.encodeToString(cursor.getBlob(i),android.util.Base64.NO_WRAP):cursor.getString(i));values.put(row);}}result.put(table,values);}
        }
        return result.toString();
    }
    private void unchanged(String state,String page)throws Exception{need(snapshot().equals(state),"source/SDK notes/progress/product revisions/outbox unchanged");need(stableFrame().equals(page),"reader page and pixels unchanged while searching");}
    private JSONObject tree(AccessibilityNodeInfo node,int depth,int[] count)throws Exception {
        need(depth<=32&&++count[0]<=2048,"semantic tree bounds");JSONArray children=new JSONArray();for(int i=0;i<node.getChildCount();i++){AccessibilityNodeInfo child=node.getChild(i);if(child!=null){try{children.put(tree(child,depth+1,count));}finally{child.recycle();}}}
        return new JSONObject().put("id",node.getViewIdResourceName()).put("text",text(node)).put("description",String.valueOf(node.getContentDescription())).put("actions",node.getActions()).put("children",children);
    }
    private void capture(String name)throws Exception {
        long deadline=SystemClock.elapsedRealtime()+10000;AccessibilityNodeInfo root=null;while(root==null&&SystemClock.elapsedRealtime()<deadline){root=getUiAutomation().getRootInActiveWindow();if(root==null)SystemClock.sleep(80);}need(root!=null,"actual CBZ semantic root after window transition");int[] count={0};JSONObject value;try{value=tree(root,0,count);}finally{root.recycle();}
        File folder=new File(context.getFilesDir(),"fixed-pan-captures");need(folder.isDirectory()||folder.mkdirs(),"search captures directory");Bitmap image=null;deadline=SystemClock.elapsedRealtime()+10000;while(image==null&&SystemClock.elapsedRealtime()<deadline){image=getUiAutomation().takeScreenshot();if(image==null)SystemClock.sleep(80);}need(image!=null,"actual CBZ screenshot after window transition");try(FileOutputStream output=new FileOutputStream(new File(folder,name+".png"))){need(image.compress(Bitmap.CompressFormat.PNG,100,output),"PNG written");}finally{image.recycle();}
        JSONObject observation=new JSONObject().put("name",name).put("nodes",count[0]).put("tree",value);try{observation.put("frame",frame());}catch(AssertionError absent){}observations.put(observation);
    }
    private Activity activity(){Activity activity=readerMonitor.getLastActivity();need(activity!=null,"actual host activity");return activity;}
    private <T>T owner(ReadingReview.Call<T> call)throws Exception{return ReadingReview.call(activity(),call);}
    private HostTask task(){return new HostTask(()->false);}
    private ReadingControl control(){return new ReadingControl(task(),context.getFilesDir(),"probe",false);}
    private String key(String role)throws Exception{return books.getJSONObject(role).getString("format")+":"+books.getJSONObject(role).getString("sha256");}
    private NativeReadingProduct.Page records(String role)throws Exception {String key=key(role);return owner(store->NativeReadingProduct.list(store,key,"",false,control()));}
    private ReadingRecord record(String role,String body)throws Exception{String key=key(role);return owner(store->{String after="";for(int i=0;i<128;i++){NativeReadingProduct.Page page=NativeReadingProduct.list(store,key,after,false,control());for(ReadingRecord row:page.rows)if(row.body.equals(body))return row;if(page.complete)break;after=page.next;}throw new AssertionError("Actual copied G04 record missing: "+body);});}
    private String sdk()throws Exception{return new JSONObject(snapshot()).getJSONArray("sdk").toString();}
    private long revisions()throws Exception{try(SQLiteDatabase db=SQLiteDatabase.openDatabase(new File(context.getFilesDir(),"reader-catalog.db").getAbsolutePath(),null,SQLiteDatabase.OPEN_READONLY);Cursor row=db.rawQuery("SELECT count(*) FROM reader_revisions",null)){need(row.moveToFirst(),"revision count");return row.getLong(0);}}
    private void settled()throws Exception{owner(store->true);status(" 条记录");}
    private void closePanel(){click("关闭");}
    private void freshView(long book,long previous)throws Exception{long end=SystemClock.elapsedRealtime()+120000;while(SystemClock.elapsedRealtime()<end){try{JSONObject actual=frame();if(actual.optLong("book",-1)==book&&actual.optLong("view",previous)!=previous&&actual.has("bitmap_identity")&&act(node->id(node,"reader_view")&&node.isVisibleToUser(),null))return;}catch(AssertionError notReady){}SystemClock.sleep(80);}throw new AssertionError("new visible reader view and bitmap not ready after rotation");}
    private void setText(String value){until(node->description(node,"阅读记录文字")&&node.isEnabled(),node->{Bundle args=new Bundle();args.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,value);need(node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,args),"actual editor text");},"record editor",30000);}
    private void bookmark(String body)throws Exception{click("添加书签");setText(body);click("保存");settled();}
    private void gate(String stage)throws Exception{for(String suffix:new String[]{"arm","arrived","release"})Files.deleteIfExists(new File(context.getFilesDir(),"reading-"+stage+"-gate-"+suffix).toPath());Files.write(new File(context.getFilesDir(),"reading-"+stage+"-gate-arm").toPath(),new byte[]{1});}
    private void arrived(String stage){long end=SystemClock.elapsedRealtime()+60000;while(SystemClock.elapsedRealtime()<end){if(new File(context.getFilesDir(),"reading-"+stage+"-gate-arrived").isFile())return;SystemClock.sleep(30);}throw new AssertionError("actual reading control not reached: "+stage);}
    private void jump(String label)throws Exception{long token=frame().getLong("accepted_token");contains(label);click("跳转到此处");long end=SystemClock.elapsedRealtime()+120000;while(SystemClock.elapsedRealtime()<end){if(frame().optLong("accepted_token",0)>token)return;SystemClock.sleep(60);}throw new AssertionError("FOUND did not render actual page");}
    private void selectText()throws Exception{
        click("Select");AtomicReference<Rect> bounds=new AtomicReference<>();onMain(()->{ReaderView view=activity().findViewById(R.id.reader_view);AccessibilityNodeInfo line=view.getAccessibilityNodeProvider().createAccessibilityNodeInfo(1);Rect rect=new Rect();line.getBoundsInScreen(rect);line.recycle();bounds.set(rect);});Rect rect=bounds.get();need(rect!=null&&rect.width()>30,"actual first text line bounds");float x=rect.left+6,y=rect.centerY(),end=Math.min(rect.right-3,rect.left+150);long now=SystemClock.uptimeMillis();sendPointerSync(MotionEvent.obtain(now,now,MotionEvent.ACTION_DOWN,x,y,0));SystemClock.sleep(100);sendPointerSync(MotionEvent.obtain(now,now+100,MotionEvent.ACTION_MOVE,end,y,0));sendPointerSync(MotionEvent.obtain(now,now+150,MotionEvent.ACTION_UP,end,y,0));
        long deadline=SystemClock.elapsedRealtime()+10000;while(SystemClock.elapsedRealtime()<deadline){JSONObject actual=frame();if(actual.optLong("selection_end",-1)>actual.optLong("selection_start",-1))return;SystemClock.sleep(40);}throw new AssertionError("real pointer gesture did not select page text");
    }
    private void highlight(String body)throws Exception{selectText();panel();click("标注选中文本");setText(body);click("保存");settled();}
    private final JSONArray pixels=new JSONArray(),panFrames=new JSONArray(),gestures=new JSONArray();
    private void idle()throws Exception{owner(store->true);long end=SystemClock.elapsedRealtime()+30000;while(SystemClock.elapsedRealtime()<end){AtomicReference<Boolean> ready=new AtomicReference<>(false);onMain(()->{try{ready.set(((Integer)ReadingReview.field(activity(),"operation"))==0);}catch(Exception error){throw new RuntimeException(error);}});if(ready.get())return;SystemClock.sleep(40);}throw new AssertionError("actual SDK worker idle");}
    private JSONObject settledFrame()throws Exception{long end=SystemClock.elapsedRealtime()+30000;while(SystemClock.elapsedRealtime()<end){JSONObject value=frame();if(value.getLong("drawn_token")==value.getLong("accepted_token")&&value.getLong("settled_token")==value.getLong("accepted_token")&&value.getLong("drawn_revision")==value.getLong("revision")&&value.getLong("settled_revision")==value.getLong("revision"))return value;SystemClock.sleep(40);}throw new AssertionError("actual drawn/settled viewport");}
    private void settings(){until(node->description(node,"阅读更多操作")&&node.isEnabled(),this::tap,"reader More",30000);click("阅读设置");until(node->description(node,"字号 pt"),null,"actual native settings",30000);}
    private boolean scrollSettings(boolean forward){return act(node->node.isScrollable()&&"android.widget.ScrollView".contentEquals(node.getClassName()),node->node.performAction(forward?AccessibilityNodeInfo.ACTION_SCROLL_FORWARD:AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD));}
    private void visible(String label){for(int i=0;i<12;i++){if(act(node->description(node,label)&&node.isVisibleToUser(),null))return;scrollSettings(true);SystemClock.sleep(80);}throw new AssertionError("setting visible: "+label);}
    private void edit(String label,String value){for(int i=0;i<12;i++)scrollSettings(false);visible(label);until(node->description(node,label),node->{Bundle data=new Bundle();data.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,value);need(node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,data),"real settings text");},"setting "+label,30000);}
    private void choose(String label,String value){for(int i=0;i<12;i++)scrollSettings(false);visible(label);until(node->description(node,label)&&node.isVisibleToUser(),this::tap,"setting "+label,30000);click(value);}
    private void appearance(int zoom,String direction,String operation)throws Exception{settings();edit("固定页缩放 %",Integer.toString(zoom));choose("翻页方向",direction);choose("翻页操作",operation);long token=frame().getLong("accepted_token");click("应用");long end=SystemClock.elapsedRealtime()+120000;while(SystemClock.elapsedRealtime()<end){if(frame().getLong("accepted_token")>token&&!act(node->description(node,"阅读设置状态"),null)){idle();settledFrame();return;}SystemClock.sleep(60);}throw new AssertionError("real candidate settings frame accepted");}
    private Rect readerBounds(){Rect bounds=new Rect();until(node->id(node,"reader_view")&&node.isVisibleToUser(),node->node.getBoundsInScreen(bounds),"visible actual reader bounds",30000);return bounds;}
    private void drag(float fromX,float fromY,float toX,float toY,boolean cancel)throws Exception{Rect box=readerBounds();float x=box.left+box.width()*fromX,y=box.top+box.height()*fromY,ex=box.left+box.width()*toX,ey=box.top+box.height()*toY;long now=SystemClock.uptimeMillis();sendPointerSync(MotionEvent.obtain(now,now,MotionEvent.ACTION_DOWN,x,y,0));SystemClock.sleep(50);sendPointerSync(MotionEvent.obtain(now,now+50,MotionEvent.ACTION_MOVE,ex,ey,0));SystemClock.sleep(30);sendPointerSync(MotionEvent.obtain(now,SystemClock.uptimeMillis(),cancel?MotionEvent.ACTION_CANCEL:MotionEvent.ACTION_UP,ex,ey,0));idle();settledFrame();}
    private boolean panAction(int action)throws Exception{AtomicReference<Boolean> accepted=new AtomicReference<>(false);onMain(()->{ReaderView view=activity().findViewById(R.id.reader_view);accepted.set(view.performAccessibilityAction(action,null));});if(accepted.get())settledFrame();return accepted.get();}
    private void corner(int which)throws Exception{boolean left=(which&1)==0,top=which<2;for(int i=0;i<8;i++){JSONObject value=settledFrame();if(Math.abs(value.getDouble("pan_x")-(left?1:-1)*value.getDouble("pan_limit_x"))<.1&&Math.abs(value.getDouble("pan_y")-(top?1:-1)*value.getDouble("pan_limit_y"))<.1)return;drag(left?.2f:.8f,top?.2f:.8f,left?.8f:.2f,top?.8f:.2f,false);}throw new AssertionError("real drag did not reach fixed-page corner "+which);}
    private void observePixel(String role,int which)throws Exception{JSONObject actual=settledFrame();JSONArray point=input.getJSONObject("pan_expected").getJSONArray("points").getJSONArray(which),rgb=input.getJSONObject("pan_expected").getJSONArray("rgb").getJSONArray(which);int expected=0xff000000|(rgb.getInt(0)<<16)|(rgb.getInt(1)<<8)|rgb.getInt(2);Rect box=readerBounds();double scale=actual.getDouble("fit")*actual.getDouble("render_scale");int x=Math.round((float)(box.left+actual.getDouble("offset_x")+point.getInt(0)*scale)),y=Math.round((float)(box.top+actual.getDouble("offset_y")+point.getInt(1)*scale));need(box.contains(x,y),"independent actual page-corner point lies inside visible reader after pan");Bitmap screen=getUiAutomation().takeScreenshot();need(screen!=null,"actual viewport screenshot");int color;try{color=screen.getPixel(x,y);}finally{screen.recycle();}pixels.put(new JSONObject().put("role",role).put("corner",which).put("source_x",point.getInt(0)).put("source_y",point.getInt(1)).put("screen_x",x).put("screen_y",y).put("argb",color&0xffffffffL).put("expected_argb",expected&0xffffffffL));need(color==expected,"real displayed page-corner RGB actual="+Integer.toHexString(color)+" expected="+Integer.toHexString(expected));panFrames.put(new JSONObject().put("role",role).put("corner",which).put("frame",actual));}
    private byte[] saved()throws Exception{return Files.readAllBytes(new File(context.getFilesDir(),"reading-settings/preferences.json").toPath());}
    private void changed(long token)throws Exception{long end=SystemClock.elapsedRealtime()+120000;while(frame().getLong("accepted_token")<=token&&SystemClock.elapsedRealtime()<end)SystemClock.sleep(50);need(frame().getLong("accepted_token")>token,"original page navigation actually published a new SDK frame");idle();settledFrame();}
    private void fresh(long old)throws Exception{long end=SystemClock.elapsedRealtime()+120000;while(SystemClock.elapsedRealtime()<end){try{JSONObject actual=frame();if(actual.optLong("book",-1)==book("cbz")&&actual.optLong("view",old)!=old){idle();settledFrame();return;}}catch(AssertionError absent){}SystemClock.sleep(60);}throw new AssertionError("actual recreated CBZ view ready");}
    private void sameViewport(JSONObject before,JSONObject after)throws Exception{
        need(after.getInt("viewport_height")==before.getInt("viewport_height")&&after.getInt("viewport_width")==before.getInt("viewport_width")&&after.getDouble("offset_x")==before.getDouble("offset_x")&&after.getDouble("offset_y")==before.getDouble("offset_y")&&after.getLong("accepted_token")==before.getLong("accepted_token"),"selection entry and revealing actions never resize or shift the actual active page");
    }
    private void croppedRotations()throws Exception{
        for(int rotation:new int[]{0,90,180,270}){
            String role="crop"+rotation;JSONObject plan=null;JSONArray originals=input.getJSONArray("books");
            for(int i=0;i<originals.length();i++)if(originals.getJSONObject(i).getString("role").equals(role))plan=originals.getJSONObject(i);
            need(plan!=null,"predeclared cropped PDF plan");String visible=plan.getString("visible_marker"),hidden=plan.getString("hidden_marker");
            open(role);appearance(300,"从左向右","点击和滑动");corner(3);String state=snapshot();byte[] file=saved();JSONObject actual=settledFrame();
            need(Math.abs(actual.getDouble("bitmap_width")/actual.getDouble("render_scale")-plan.getDouble("viewport_width"))<1&&Math.abs(actual.getDouble("bitmap_height")/actual.getDouble("render_scale")-plan.getDouble("viewport_height"))<1,"actual renderer uses cropped and rotated public viewport dimensions");
            for(boolean longPress:new boolean[]{false,true}){
            JSONObject beforeMode=settledFrame();if(!longPress)click("Select");actual=settledFrame();sameViewport(beforeMode,actual);AtomicReference<float[]> endpoints=new AtomicReference<>();
            onMain(()->{
                need(!activity().findViewById(R.id.selection_bar).isShown(),"no persistent empty selection toolbar");
                ReaderView view=activity().findViewById(R.id.reader_view);PageSnapshot page=view.page();boolean visibleSeen=false,hiddenSeen=false;
                for(int i=0;i<page.lineText.length;i++){
                    AccessibilityNodeInfo node=view.getAccessibilityNodeProvider().createAccessibilityNodeInfo(i+1);
                    try{if(text(node).contains(visible)){need(node.isVisibleToUser(),"rotated cropped marker node visible after actual pan");visibleSeen=true;}if(text(node).contains(hidden)){need(!node.isVisibleToUser(),"opposite rotated cropped marker clipped after actual pan");hiddenSeen=true;}}
                    finally{node.recycle();}
                }
                need(visibleSeen&&hiddenSeen,"rotated text remains a complete semantic line");
                String text=new String(page.text,StandardCharsets.UTF_8);int start=text.indexOf(visible),first=-1,last=-1;need(start>=0,"independent ASCII fixture marker in public text");
                for(int i=0;i<page.starts.length;i++)if(page.ends[i]>start&&page.starts[i]<start+visible.length()){if(first<0)first=i;last=i;}
                need(first>=0&&last>first,"actual source text regions cover marker");float[] points=new float[4];
                for(int end=0;end<2;end++){float[] quad=page.quads[end==0?first:last];for(int point=0;point<4;point++){points[end*2]+=quad[point*2]/4;points[end*2+1]+=quad[point*2+1]/4;}}
                endpoints.set(points);
            });
            Rect box=readerBounds();double scale=actual.getDouble("render_scale")*actual.getDouble("fit");float[] points=endpoints.get();
            for(int end=0;end<2;end++){points[end*2]=(float)(box.left+actual.getDouble("offset_x")+points[end*2]*scale);points[end*2+1]=(float)(box.top+actual.getDouble("offset_y")+points[end*2+1]*scale);need(box.contains(Math.round(points[end*2]),Math.round(points[end*2+1])),"rotated selection endpoint lies in real visible viewport");}
            long now=SystemClock.uptimeMillis();JSONObject held;
            sendPointerSync(MotionEvent.obtain(now,now,MotionEvent.ACTION_DOWN,points[0],points[1],0));
            try{
                SystemClock.sleep(longPress?650:60);held=settledFrame();
                need(held.getBoolean("selection_mode")&&held.getLong("selection_end")>held.getLong("selection_start"),"actual timer/pointer enters real selection mode before drag");sameViewport(actual,held);
                sendPointerSync(MotionEvent.obtain(now,SystemClock.uptimeMillis(),MotionEvent.ACTION_MOVE,points[2],points[3],0));
            }catch(Exception|Error failure){sendPointerSync(MotionEvent.obtain(now,SystemClock.uptimeMillis(),MotionEvent.ACTION_CANCEL,points[0],points[1],0));throw failure;}
            sendPointerSync(MotionEvent.obtain(now,SystemClock.uptimeMillis(),MotionEvent.ACTION_UP,points[2],points[3],0));
            AtomicReference<String> selected=new AtomicReference<>();onMain(()->{Selection selection=((ReaderView)activity().findViewById(R.id.reader_view)).getSelection();selected.set(selection==null?"":selection.text);});
            need(selected.get().equals(visible),"actual rotated cropped PDF pointer selects exact visible source marker role="+role+" actual="+selected.get()+" expected="+visible);
            JSONObject after=settledFrame();sameViewport(actual,after);AtomicReference<Rect> toolbar=new AtomicReference<>();
            onMain(()->{android.view.View bar=activity().findViewById(R.id.selection_bar);Rect bounds=new Rect();need(bar.isShown()&&bar.getGlobalVisibleRect(bounds),"actual contextual selection actions visible");toolbar.set(bounds);});
            Rect selectedBounds=new Rect((int)Math.floor(Math.min(points[0],points[2])),(int)Math.floor(Math.min(points[1],points[3])),(int)Math.ceil(Math.max(points[0],points[2]))+1,(int)Math.ceil(Math.max(points[1],points[3]))+1);
            need(!Rect.intersects(toolbar.get(),selectedBounds),"contextual actions stay opposite actual selected marker");
            gestures.put(new JSONObject().put("role",role).put("long_press",longPress).put("held_ms",longPress?650:60).put("expected",visible).put("selected",selected.get()).put("before_mode",beforeMode).put("before_down",actual).put("held",held).put("after",after).put("toolbar",new JSONArray().put(toolbar.get().left).put(toolbar.get().top).put(toolbar.get().right).put(toolbar.get().bottom)));
            capture(role+(longPress?"-longpress-selection":"-panned-selection"));click("Selecting");
            need(snapshot().equals(state)&&Arrays.equals(file,saved()),"cropped rotated pan and selection never modify SDK product or settings");
            }
        }
        open("pdf");appearance(300,"从左向右","点击和滑动");corner(3);
    }
    private void selectBottomRight()throws Exception{click("Select");settledFrame();AtomicReference<Rect> bounds=new AtomicReference<>();AtomicReference<Boolean> hidden=new AtomicReference<>(false);onMain(()->{ReaderView view=activity().findViewById(R.id.reader_view);for(int i=0;i<view.page().lineText.length;i++){AccessibilityNodeInfo node=view.getAccessibilityNodeProvider().createAccessibilityNodeInfo(i+1);try{if(text(node).contains("BOTTOMRIGHT")){Rect rect=new Rect();node.getBoundsInScreen(rect);need(node.isVisibleToUser(),"panned real marker semantic node visible");bounds.set(rect);}if(text(node).contains("TOPLEFT"))hidden.set(!node.isVisibleToUser());}finally{node.recycle();}}});Rect rect=bounds.get();need(rect!=null&&rect.width()>50&&hidden.get(),"on-screen and clipped text semantic visibility uses actual pan");Rect reader=readerBounds();need(Rect.intersects(reader,rect),"native marker line lies in actual panned viewport");long now=SystemClock.uptimeMillis();float x=rect.left+3,y=rect.centerY(),end=rect.right-3;sendPointerSync(MotionEvent.obtain(now,now,MotionEvent.ACTION_DOWN,x,y,0));SystemClock.sleep(60);sendPointerSync(MotionEvent.obtain(now,now+60,MotionEvent.ACTION_MOVE,end,y,0));sendPointerSync(MotionEvent.obtain(now,SystemClock.uptimeMillis(),MotionEvent.ACTION_UP,end,y,0));AtomicReference<String> value=new AtomicReference<>();onMain(()->{ReaderView view=activity().findViewById(R.id.reader_view);Selection selection=view.getSelection();value.set(selection==null?"":selection.text);});need(value.get().contains("BOTTOMRIGHT"),"real selected public text follows translated current PDF coordinates");capture("pdf-panned-selection");click("Selecting");}
    private void multiTouch()throws Exception{Rect box=readerBounds();long now=SystemClock.uptimeMillis();float x=box.centerX(),y=box.centerY();sendPointerSync(MotionEvent.obtain(now,now,MotionEvent.ACTION_DOWN,x,y,0));MotionEvent.PointerProperties one=new MotionEvent.PointerProperties(),two=new MotionEvent.PointerProperties();one.id=0;one.toolType=MotionEvent.TOOL_TYPE_FINGER;two.id=1;two.toolType=MotionEvent.TOOL_TYPE_FINGER;MotionEvent.PointerCoords a=new MotionEvent.PointerCoords(),b=new MotionEvent.PointerCoords();a.x=x;a.y=y;a.pressure=a.size=1;b.x=x+20;b.y=y+20;b.pressure=b.size=1;sendPointerSync(MotionEvent.obtain(now,now+20,MotionEvent.ACTION_POINTER_DOWN|(1<<MotionEvent.ACTION_POINTER_INDEX_SHIFT),2,new MotionEvent.PointerProperties[]{one,two},new MotionEvent.PointerCoords[]{a,b},0,0,1,1,0,0,android.view.InputDevice.SOURCE_TOUCHSCREEN,0));sendPointerSync(MotionEvent.obtain(now,now+40,MotionEvent.ACTION_POINTER_UP|(1<<MotionEvent.ACTION_POINTER_INDEX_SHIFT),2,new MotionEvent.PointerProperties[]{one,two},new MotionEvent.PointerCoords[]{a,b},0,0,1,1,0,0,android.view.InputDevice.SOURCE_TOUCHSCREEN,0));sendPointerSync(MotionEvent.obtain(now,now+60,MotionEvent.ACTION_UP,x+150,y+150,0));idle();settledFrame();}
    @Override public void onStart(){
        context=getTargetContext();phase=arguments.getString("phase");Throwable failure=null;Bundle result=new Bundle();
        try{
            readerMonitor=addMonitor(MainActivity.class.getName(),null,false);AccessibilityServiceInfo service=getUiAutomation().getServiceInfo();service.flags|=AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS|AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS;getUiAutomation().setServiceInfo(service);
            need(BuildConfig.READER_PREFERENCES&&BuildConfig.READER_READING&&BuildConfig.READER_NAVIGATION&&BuildConfig.READER_SEARCH&&BuildConfig.READER_SYNC,"all inherited actual host integrations enabled");
            input=new JSONObject(new String(Files.readAllBytes(new File(context.getFilesDir(),"fixed-pan-input.json").toPath()),StandardCharsets.UTF_8));
            if(phase.equals("first")){
                seed();launch();open("cbz");
                check("real_pdf_cbz_four_corners_strict_display_pixels_and_no_store_write",()->{for(String role:new String[]{"cbz","pdf"}){open(role);appearance(300,"从左向右","点击和滑动");String state=snapshot();byte[] file=saved();JSONObject original=settledFrame();need(original.getDouble("pan_limit_x")>0&&original.getDouble("pan_limit_y")>0,"native zoom overflows both real viewport axes");for(int which=0;which<4;which++){corner(which);observePixel(role,which);need(frame().getLong("accepted_token")==original.getLong("accepted_token")&&frame().getInt("index")==original.getInt("index"),"drag never turns or replaces the actual SDK page");capture(role+"-corner-"+which);}need(snapshot().equals(state)&&Arrays.equals(file,saved()),"four-corner panning writes neither SDK/product nor F3 settings");}});
                check("panned_pdf_selection_and_clipped_semantic_bounds_match_actual_page",()->{croppedRotations();String state=snapshot();selectBottomRight();need(snapshot().equals(state),"selection after pan leaves SDK/product stores unchanged");});
                check("directional_accessibility_pan_clamps_and_keeps_page_navigation_distinct",()->{String state=snapshot();long token=frame().getLong("accepted_token");for(int action:new int[]{AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_LEFT.getId(),AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_UP.getId(),AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_RIGHT.getId(),AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_DOWN.getId()}){int steps=0;while(panAction(action))need(++steps<=16,"directional semantic panning bounded");need(!panAction(action),"actual edge refuses additional viewport movement");}need(frame().getLong("accepted_token")==token&&snapshot().equals(state),"semantic pan never masquerades as next page or writes stores");capture("pdf-semantic-edge");});
                check("cancel_and_multitouch_never_emit_spurious_fixed_page_turn",()->{String state=snapshot();long token=frame().getLong("accepted_token");drag(.2f,.2f,.8f,.8f,true);multiTouch();need(frame().getLong("accepted_token")==token&&snapshot().equals(state),"cancel/multiple contacts cannot emit a tap or swipe page turn");capture("pdf-cancelled-touch");});
                check("nonoverflow_axis_retains_swipe_and_new_page_resets_pan",()->{appearance(110,"上下翻页","滑动");JSONObject start=settledFrame();need(start.getDouble("pan_limit_x")>0&&start.getDouble("pan_limit_y")==0,"real wide-axis-only overflow fixture");drag(.2f,.5f,.8f,.5f,false);need(Math.abs(frame().getDouble("pan_x"))>0&&frame().getLong("accepted_token")==start.getLong("accepted_token"),"horizontal actual overflow drag pans");long token=frame().getLong("accepted_token");int index=frame().getInt("index");drag(.5f,.8f,.5f,.2f,false);changed(token);need(frame().getInt("index")==index+1&&frame().getDouble("pan_x")==0&&frame().getDouble("pan_y")==0,"nonoverflow vertical swipe keeps original page turn and new page resets pan");capture("pdf-axis-page-turn");});
                check("fit_fixed_and_reflow_keep_original_turn_controls",()->{appearance(100,"从左向右","点击");JSONObject start=settledFrame();need(start.getDouble("pan_limit_x")==0&&start.getDouble("pan_limit_y")==0,"fit-page viewport has no pan state");need(!panAction(AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_LEFT.getId())&&!panAction(AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_DOWN.getId()),"fit-page pan actions do not falsely claim movement");long token=frame().getLong("accepted_token");drag(.85f,.5f,.85f,.5f,false);changed(token);open("txt");appearance(100,"上下翻页","滑动");token=frame().getLong("accepted_token");drag(.5f,.8f,.5f,.2f,false);changed(token);need(frame().getDouble("pan_limit_x")==0&&frame().getDouble("pan_limit_y")==0,"reflow remains on its original paging path");capture("txt-original-turn");});
                check("actual_rotation_reopens_same_fixed_page_with_transient_pan_reset",()->{open("cbz");appearance(300,"从左向右","点击");corner(3);String state=snapshot();byte[] file=saved();long old=frame().getLong("view");getUiAutomation().setRotation(android.app.UiAutomation.ROTATION_FREEZE_90);fresh(old);long rotated=frame().getLong("view");getUiAutomation().setRotation(android.app.UiAutomation.ROTATION_FREEZE_0);fresh(rotated);JSONObject actual=settledFrame();need(actual.getInt("index")==0&&actual.getDouble("pan_x")==0&&actual.getDouble("pan_y")==0&&actual.getDouble("zoom")==3,"actual rotation retains selected fixed page and zoom but discards ephemeral viewport offset");need(snapshot().equals(state)&&Arrays.equals(file,saved()),"rotation/pan never persists hidden viewport state into SDK product or settings");capture("cbz-rotation-reset");Files.write(new File(context.getFilesDir(),"fixed-pan-reopen-baseline.json").toPath(),snapshot().getBytes(StandardCharsets.UTF_8));Files.write(new File(context.getFilesDir(),"fixed-pan-reopen-preferences.json").toPath(),saved());});
            }else if(phase.equals("reopen")){
                books=new JSONObject(new String(Files.readAllBytes(new File(context.getFilesDir(),"fixed-pan-books.json").toPath()),StandardCharsets.UTF_8));launch();waitFrame(book("cbz"));idle();settledFrame();
                check("fresh_process_keeps_native_zoom_source_and_zero_pan_then_drags",()->{JSONObject actual=settledFrame();need(actual.getInt("index")==0&&actual.getDouble("zoom")==3&&actual.getDouble("pan_x")==0&&actual.getDouble("pan_y")==0&&actual.getDouble("pan_limit_x")>0&&actual.getDouble("pan_limit_y")>0,"fresh process reopens real zoomed CBZ without persisting pan");String baseline=new String(Files.readAllBytes(new File(context.getFilesDir(),"fixed-pan-reopen-baseline.json").toPath()),StandardCharsets.UTF_8);need(snapshot().equals(baseline)&&Arrays.equals(saved(),Files.readAllBytes(new File(context.getFilesDir(),"fixed-pan-reopen-preferences.json").toPath())),"source and SDK/product/settings bytes retain exact baseline");corner(0);observePixel("cbz-reopen",0);capture("cbz-reopened-pan");});
            }else throw new AssertionError("unknown fixed pan phase");
        }catch(Throwable error){failure=error;try{capture("failure");}catch(Throwable captureError){error.addSuppressed(captureError);}}
        try{
            JSONObject report=new JSONObject().put("source_sha",arguments.getString("source_sha")).put("run_id",arguments.getString("run_id")).put("attempt",arguments.getString("attempt")).put("phase",phase).put("pid",android.os.Process.myPid()).put("passed",failure==null).put("checks",checks).put("count",checks.length()).put("observations",observations).put("display_pixels",pixels).put("pan_frames",panFrames).put("selection_gestures",gestures);
            if(failure!=null)report.put("failed_check",active).put("failure",failure.getMessage()).put("failure_trace",android.util.Log.getStackTraceString(failure));
            Files.write(new File(context.getFilesDir(),"fixed-pan-ui-"+phase+".json").toPath(),report.toString(2).getBytes(StandardCharsets.UTF_8));result.putString("stream",failure==null?"FIXED_PAN_UI_PASS "+phase:"FIXED_PAN_UI_FAIL "+phase);finish(failure==null?Activity.RESULT_OK:Activity.RESULT_CANCELED,result);
        }catch(Exception error){result.putString("shortMsg","Fixed pan evidence unavailable");finish(Activity.RESULT_CANCELED,result);}
    }
}
