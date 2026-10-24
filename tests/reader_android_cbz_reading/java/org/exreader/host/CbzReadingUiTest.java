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
public final class CbzReadingUiTest extends Instrumentation {
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
        runOnMainSync(()->{Activity activity=readerMonitor.getLastActivity();if(activity!=null){android.view.View view=activity.findViewById(org.exreader.host.R.id.reader_view);if(view!=null){AccessibilityNodeInfo info=view.createAccessibilityNodeInfo();try{observed.set(info.getExtras().getString("exreader.frame",""));}finally{info.recycle();}}}});
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
        long wanted=book(role),deadline=SystemClock.elapsedRealtime()+30000;String expectedKey=key(role);boolean ready=false;while(SystemClock.elapsedRealtime()<deadline){AtomicReference<Boolean> settled=new AtomicReference<>(false);runOnMainSync(()->{try{CatalogShelf shelf=(CatalogShelf)ReadingReview.field(activity(),"catalogShelf");android.widget.ListView list=activity().findViewById(R.id.book_list);android.view.View row=list.getChildCount()==1?list.getChildAt(0):null;JSONObject observed=new JSONObject(shelf.observation());settled.set(observed.getString("query").equals(title)&&!observed.getBoolean("loading")&&observed.getLong("generation")==observed.getLong("applied_generation")&&shelf.getCount()==1&&shelf.getItemId(0)==wanted&&list.isEnabled()&&row!=null&&row.isShown()&&row.isLaidOut()&&row.getHeight()>0&&!list.isLayoutRequested()&&expectedKey.equals(row.getTag()));}catch(Exception error){throw new RuntimeException(error);}});if(settled.get()){ready=true;break;}SystemClock.sleep(60);}need(ready,"exact shelf book identity loaded and actually laid out before click");
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
                JSONObject row=originals.getJSONObject(i);File file=new File(context.getFilesDir(),"cbz-reading-fixtures/"+row.getString("file"));need(file.length()==row.getLong("bytes"),"seed original length");
                NativeLibrary.ImportResult result=row.getString("role").equals("legacy")?library.importLegacyFile(file.getAbsolutePath(),format(row.getString("format")),row.getString("title")):library.importFile(file.getAbsolutePath(),format(row.getString("format")),row.getString("title"));need(hash(library,result.id).equals(row.getString("sha256")),"SDK original fixture identity");
                String title=null;for(NativeLibrary.Book found:library.books())if(found.id==result.id)title=found.title;
                need(title!=null,"SDK book after import");books.put(row.getString("role"),new JSONObject().put("id",result.id).put("title",title).put("sha256",row.getString("sha256")).put("format",row.getString("format")));
                need(context.getSharedPreferences("host",0).edit().putString("path_"+result.id,file.getAbsolutePath()).putLong("size_"+result.id,file.length()).commit(),"host original path registered");
            }
            library.saveProgress(book("txt"),0);library.saveNote(book("txt"),0,0,0,"retained existing SDK note");
        }
        Files.write(new File(context.getFilesDir(),"cbz-reading-books.json").toPath(),books.toString().getBytes(StandardCharsets.UTF_8));
    }
    private String snapshot()throws Exception {
        JSONObject result=new JSONObject();JSONArray rows=new JSONArray();
        try(NativeLibrary library=new NativeLibrary(new File(context.getFilesDir(),"library.db").getAbsolutePath())){
            NativeLibrary.Book[] items=library.books();Arrays.sort(items,(a,b)->Long.compare(a.id,b.id));need(items.length==7,"seven exact originals retained");
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
        File folder=new File(context.getFilesDir(),"cbz-reading-captures");need(folder.isDirectory()||folder.mkdirs(),"search captures directory");Bitmap image=null;deadline=SystemClock.elapsedRealtime()+10000;while(image==null&&SystemClock.elapsedRealtime()<deadline){image=getUiAutomation().takeScreenshot();if(image==null)SystemClock.sleep(80);}need(image!=null,"actual CBZ screenshot after window transition");try(FileOutputStream output=new FileOutputStream(new File(folder,name+".png"))){need(image.compress(Bitmap.CompressFormat.PNG,100,output),"PNG written");}finally{image.recycle();}
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
        click("Select");AtomicReference<Rect> bounds=new AtomicReference<>();runOnMainSync(()->{ReaderView view=activity().findViewById(R.id.reader_view);AccessibilityNodeInfo line=view.getAccessibilityNodeProvider().createAccessibilityNodeInfo(1);Rect rect=new Rect();line.getBoundsInScreen(rect);line.recycle();bounds.set(rect);});Rect rect=bounds.get();need(rect!=null&&rect.width()>30,"actual first text line bounds");float x=rect.left+6,y=rect.centerY(),end=Math.min(rect.right-3,rect.left+150);long now=SystemClock.uptimeMillis();sendPointerSync(MotionEvent.obtain(now,now,MotionEvent.ACTION_DOWN,x,y,0));SystemClock.sleep(100);sendPointerSync(MotionEvent.obtain(now,now+100,MotionEvent.ACTION_MOVE,end,y,0));sendPointerSync(MotionEvent.obtain(now,now+150,MotionEvent.ACTION_UP,end,y,0));
        long deadline=SystemClock.elapsedRealtime()+10000;while(SystemClock.elapsedRealtime()<deadline){JSONObject actual=frame();if(actual.optLong("selection_end",-1)>actual.optLong("selection_start",-1))return;SystemClock.sleep(40);}throw new AssertionError("real pointer gesture did not select page text");
    }
    private void highlight(String body)throws Exception{selectText();panel();click("标注选中文本");setText(body);click("保存");settled();}
    private final JSONArray actualPages=new JSONArray();private byte[] face;
    private byte[] face()throws Exception{if(face==null)try(java.io.InputStream input=context.getAssets().open("Reader.otf")){face=input.readAllBytes();}return face;}
    private String graph()throws Exception{JSONObject value=new JSONObject(snapshot());value.remove("sdk");return value.toString();}
    private void idle()throws Exception{owner(store->true);long end=SystemClock.elapsedRealtime()+30000;while(SystemClock.elapsedRealtime()<end){AtomicReference<Boolean> done=new AtomicReference<>(false);runOnMainSync(()->{try{done.set(((Integer)ReadingReview.field(activity(),"operation"))==0);}catch(Exception error){throw new RuntimeException(error);}});if(done.get())return;SystemClock.sleep(40);}throw new AssertionError("real CBZ worker idle");}
    private JSONObject settledFrame()throws Exception{long end=SystemClock.elapsedRealtime()+30000;while(SystemClock.elapsedRealtime()<end){JSONObject actual=frame();if(actual.getLong("drawn_token")==actual.getLong("accepted_token")&&actual.getLong("settled_token")==actual.getLong("accepted_token")&&actual.getLong("drawn_revision")==actual.getLong("revision")&&actual.getLong("settled_revision")==actual.getLong("revision"))return actual;SystemClock.sleep(50);}throw new AssertionError("actual drawn/settled CBZ frame");}
    private void atPage(int target)throws Exception{for(int count=0;count<5;count++){JSONObject before=frame();int current=before.getInt("index");if(current==target){idle();return;}long token=before.getLong("accepted_token");runOnMainSync(()->{ReaderView view=activity().findViewById(R.id.reader_view);need(view.performAccessibilityAction(current<target?AccessibilityNodeInfo.ACTION_SCROLL_FORWARD:AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD,null),"actual native page scroll");});long end=SystemClock.elapsedRealtime()+120000;while(frame().optLong("accepted_token",0)<=token&&SystemClock.elapsedRealtime()<end)SystemClock.sleep(50);need(frame().getLong("accepted_token")>token,"CBZ scroll rendered a real new page");}throw new AssertionError("actual CBZ target page not reached");}
    private void assertPage(int expected)throws Exception{
        JSONObject actual=settledFrame();String id=input.getJSONObject("cbz_expected").getJSONArray("page_ids").getString(expected);JSONArray rgb=input.getJSONObject("cbz_expected").getJSONArray("rgb").getJSONArray(expected);int color=0xff000000|(rgb.getInt(0)<<16)|(rgb.getInt(1)<<8)|rgb.getInt(2);
        need(actual.getInt("index")==expected&&actual.getBoolean("fixed_public_text")&&actual.getLong("fixed_public_text_bytes")==0&&actual.getString("fixed_page_id").equals(id),"actual current renderer owns genuine empty SDK snapshot and exact page ID");
        need(actual.getString("source_key").equals(key("cbz"))&&actual.getString("fixed_renderer_source_key").equals(key("cbz"))&&actual.getInt("fixed_renderer")!=0,"actual source bytes, displayed source and persistent renderer identity agree");
        AtomicReference<Integer> pixel=new AtomicReference<>();runOnMainSync(()->{try{PageSnapshot page=(PageSnapshot)ReadingReview.field(activity(),"current");need(page.text!=null&&page.text.length==0&&page.glyphCount()==0&&page.regionCount()==0,"real image-only snapshot has no invented OCR region");pixel.set(page.bitmap.getPixel(page.bitmap.getWidth()/2,page.bitmap.getHeight()/2));}catch(Exception error){throw new RuntimeException(error);}});
        actualPages.put(new JSONObject().put("phase",phase).put("index",expected).put("page_id",id).put("argb",pixel.get()&0xffffffffL).put("expected_argb",color&0xffffffffL).put("source_key",key("cbz")).put("renderer",actual.getInt("fixed_renderer")).put("text_bytes",0));need(pixel.get()==color,"actual raw SDK center pixel equals independently predeclared RGB: actual="+Integer.toHexString(pixel.get())+" expected="+Integer.toHexString(color));
    }
    private NativeReadingSdk.Match[] both(ReadingCapture capture)throws Exception{return owner(store->{NativeReadingSdk.Match independent=NativeReadingSdk.resolve(store,book("cbz"),capture,face(),24,task(),control());FixedSession actual=(FixedSession)ReadingReview.field(activity(),"fixed");need(actual.cbz()&&actual.sourceKey().equals(key("cbz")),"borrow actual current renderer on its owner worker");return new NativeReadingSdk.Match[]{independent,actual.resolveCurrent(capture,task())};});}
    private String fixture(ReadingCapture capture,String body)throws Exception{String id=ReadingRequests.newId();owner(store->{NativeReadingProduct.Result result=NativeReadingProduct.apply(store,ReadingRequests.newId(),new String[0],NativeReadingProduct.BOOKMARK,NativeReadingProduct.PUT,key("cbz"),id,ReadingCapture.FIXED,capture,body);need(result.saved(),"public G03 deliberately altered hint/page negative fixture");return true;});return id;}
    private ReadingCapture altered(ReadingCapture original,long hint,String id,byte[][] bytes){long[] numbers=original.numbers();numbers[1]=hint;String[] route=original.route();route[3]=id;return new ReadingCapture(numbers,route,bytes);}
    private void freshView(long old)throws Exception{long end=SystemClock.elapsedRealtime()+120000;while(SystemClock.elapsedRealtime()<end){try{JSONObject actual=frame();if(actual.optLong("book",-1)==book("cbz")&&actual.optLong("view",old)!=old&&actual.has("bitmap_identity")&&act(node->id(node,"reader_view")&&node.isVisibleToUser()&&node.isEnabled(),null)){idle();settledFrame();return;}}catch(AssertionError absent){}SystemClock.sleep(80);}throw new AssertionError("real CBZ view and bitmap restored after rotation");}
    @Override public void onStart(){
        context=getTargetContext();phase=arguments.getString("phase");Throwable failure=null;Bundle result=new Bundle();
        try{
            readerMonitor=addMonitor(MainActivity.class.getName(),null,false);AccessibilityServiceInfo service=getUiAutomation().getServiceInfo();service.flags|=AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS|AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS;getUiAutomation().setServiceInfo(service);
            need(BuildConfig.READER_PREFERENCES&&BuildConfig.READER_READING&&BuildConfig.READER_NAVIGATION&&BuildConfig.READER_SEARCH&&BuildConfig.READER_SYNC,"all real Android host integrations enabled");input=new JSONObject(new String(Files.readAllBytes(new File(context.getFilesDir(),"cbz-reading-input.json").toPath()),StandardCharsets.UTF_8));
            if(phase.equals("first")){
                seed();launch();open("cbz");
                check("actual_cbz_renderer_public_empty_text_and_three_distinct_pages",()->{int renderer=frame().getInt("fixed_renderer");for(int page=0;page<3;page++){atPage(page);assertPage(page);need(frame().getInt("fixed_renderer")==renderer,"all pages painted by the same live public SDK document");capture("cbz-page-"+page);}need(NativeLibrary.syncIdentity()[1].contains("libexreader.so"),"original SDK provider retained");});
                check("genuine_cbz_bookmark_progress_and_empty_tags_do_not_write_sdk",()->{atPage(1);String sdk=sdk(),page=stableFrame();panel();until(node->text(node).equals("标注选中文本")&&!node.isEnabled(),null,"image-only highlighter unavailable without invented OCR",30000);click("保存进度");settled();bookmark("CBZ page two");ReadingRecord point=record("cbz","CBZ page two"),progress=records("cbz").progress;for(ReadingRecord row:new ReadingRecord[]{point,progress}){need(row.readable()&&row.capture.mode==ReadingCapture.FIXED&&row.capture.pageId.equals("002.png")&&row.capture.unit==1&&row.capture.start==0&&row.capture.end==0,"genuine public CBZ point copied through G03/G04");need(row.capture.partPath==null&&row.capture.chapter==null,"fixed location has no invented chapter");for(byte[] bytes:row.capture.bytes())need(bytes!=null&&bytes.length==0,"public empty bytes never converted to NULL");}need(sdk().equals(sdk)&&stableFrame().equals(page),"product bookmark/progress neither change SDK notes/progress nor pixels");capture("cbz-product-points");closePanel();});
                check("wrong_hint_uses_independent_and_current_found_page_id",()->{ReadingCapture original=record("cbz","CBZ page two").capture;ReadingCapture changed=altered(original,999,original.pageId,original.bytes());NativeReadingSdk.Match[] matches=both(changed);for(NativeReadingSdk.Match match:matches)need(match.found()&&match.unit==1&&match.start==0&&match.end==0&&match.recaptured.pageId.equals("002.png"),"both real public documents ignore untrusted hint and independently find exact page ID");fixture(changed,"CBZ wrong hint");atPage(2);String graph=graph();panel();jump("CBZ wrong hint");assertPage(1);need(record("cbz","CBZ wrong hint").capture.unit==999&&graph().equals(graph),"navigation neither falls back to hint nor rewrites stored graph");capture("cbz-wrong-hint-found");});
                check("missing_null_nul_and_wrong_source_never_guess",()->{ReadingCapture original=record("cbz","CBZ page two").capture,missing=altered(original,1,"missing-cbz-page",original.bytes());for(NativeReadingSdk.Match match:both(missing))need(!match.found()&&match.start==-1&&match.unit==-1,"missing page ID has no old-hint fallback");fixture(missing,"CBZ missing page");String state=snapshot(),page=stableFrame();panel();contains("CBZ missing page");click("跳转到此处");status("位置无法匹配");unchanged(state,page);closePanel();
                    byte[][] bytes=original.bytes();bytes[0]=null;ReadingCapture nullExact=altered(original,1,original.pageId,bytes);owner(store->{int refused=0;try{NativeReadingSdk.resolve(store,book("cbz"),nullExact,face(),24,task(),control());}catch(RuntimeException error){need(error.getMessage().contains("code 1"),"independent SDK explicitly refuses NULL exact");refused++;}try{((FixedSession)ReadingReview.field(activity(),"fixed")).resolveCurrent(nullExact,task());}catch(RuntimeException error){need(error.getMessage().contains("code 1"),"current SDK explicitly refuses NULL exact");refused++;}need(refused==2,"NULL exact never fabricated as an empty point");return true;});
                    bytes=original.bytes();bytes[0]=new byte[]{0};long[] numbers=original.numbers();numbers[3]=1;ReadingCapture nul=new ReadingCapture(numbers,original.route(),bytes);for(NativeReadingSdk.Match match:both(nul))need(!match.found()&&match.start==-1,"explicit fixed NUL length stays a miss instead of an invented empty point");
                    String[] route=original.route();route[0]="cbz:"+"0".repeat(64);ReadingCapture foreign=new ReadingCapture(original.numbers(),route,original.bytes());owner(store->{boolean a=false,b=false;try{NativeReadingSdk.resolve(store,book("cbz"),foreign,face(),24,task(),control());}catch(IllegalStateException error){a=true;}try{((FixedSession)ReadingReview.field(activity(),"fixed")).resolveCurrent(foreign,task());}catch(IllegalArgumentException error){b=true;}need(a&&b,"SDK source and actual renderer both refuse another source key");return true;});need(snapshot().equals(state)&&stableFrame().equals(page),"all source/selector negatives preserve stores and pixels");capture("cbz-location-refusals");});
                check("note_edit_delete_and_explicit_restore_keep_real_cbz_selector",()->{ReadingRecord before=record("cbz","CBZ page two");String sdk=sdk(),page=stableFrame();panel();contains("CBZ page two");click("编辑文字");setText("CBZ renamed 🙂");click("保存");settled();ReadingRecord edited=record("cbz","CBZ renamed 🙂");need(Arrays.equals(before.capture.numbers(),edited.capture.numbers())&&Arrays.equals(before.capture.route(),edited.capture.route())&&Arrays.deepEquals(before.capture.bytes(),edited.capture.bytes())&&before.anchorVersion==edited.anchorVersion,"NOTE_TEXT preserves every genuine empty selector tag and parser/version");contains("CBZ renamed 🙂");click("删除");click("删除");settled();ReadingRecord deleted=owner(store->NativeReadingProduct.selected(store,key("cbz"),before.id,"",false,control()));need(deleted.deleted&&deleted.capture==null,"CBZ tombstone has no invented capture");contains("已删除");click("选择保留版本恢复");until(node->text(node).startsWith("版本 ")&&text(node).contains("CBZ page two"),this::tap,"explicit original retained CBZ version",30000);click("恢复");settled();ReadingRecord restored=record("cbz","CBZ page two");need(restored.id.equals(before.id)&&restored.operation.equals("restore")&&Arrays.deepEquals(restored.capture.bytes(),before.capture.bytes())&&restored.capture.pageId.equals("002.png"),"explicit restore recaptures actual current renderer target after independent FOUND");need(sdk().equals(sdk)&&stableFrame().equals(page),"edit/delete/restore never auto-navigate or copy SDK notes");capture("cbz-explicit-restored");closePanel();});
                check("product_progress_navigates_to_current_renderer_found_page",()->{atPage(2);String graph=graph();panel();until(node->description(node,"已保存进度")&&node.isEnabled(),this::tap,"actual saved fixed progress",30000);click("跳转到此处");long end=SystemClock.elapsedRealtime()+120000;while(frame().getInt("index")!=1&&SystemClock.elapsedRealtime()<end)SystemClock.sleep(60);assertPage(1);need(graph().equals(graph),"progress navigation is read-only to product revisions/outbox");capture("cbz-progress-found");});
                check("cancel_capture_and_changed_display_copy_preserve_every_store",()->{String state=snapshot(),page=stableFrame();panel();gate("capture");click("添加书签");setText("CBZ cancelled never saved");click("保存");arrived("capture");click("取消读取");status("已取消");unchanged(state,page);need(!new File(context.getFilesDir(),"reading-request.json").exists(),"cancel creates no pending product request");closePanel();
                    File file=new File(context.getSharedPreferences("host",0).getString("path_"+book("cbz"),""));byte[] original=Files.readAllBytes(file.toPath());try{Files.write(file.toPath(),Arrays.copyOf(original,original.length+1));panel();click("添加书签");setText("CBZ wrong original never saved");click("保存");status("未能完成");unchanged(state,page);need(!new File(context.getFilesDir(),"reading-request.json").exists(),"changed displayed copy cannot enter a request");closePanel();}finally{Files.write(file.toPath(),original);}capture("cbz-capture-cancel-source");});
                check("close_and_actual_rotation_cancel_real_cbz_resolve",()->{String state=snapshot();panel();gate("resolve");contains("CBZ page two");click("跳转到此处");arrived("resolve");closePanel();owner(store->true);need(snapshot().equals(state),"closing actual resolve leaves all stores unchanged");panel();gate("resolve");contains("CBZ page two");click("跳转到此处");arrived("resolve");long old=frame().getLong("view");getUiAutomation().setRotation(android.app.UiAutomation.ROTATION_FREEZE_90);freshView(old);long rotated=frame().getLong("view");getUiAutomation().setRotation(android.app.UiAutomation.ROTATION_FREEZE_0);freshView(rotated);assertPage(1);need(snapshot().equals(state),"rotation cancels stale source work and reopens actual immutable renderer without graph mutations");capture("cbz-after-rotation");});
                Files.write(new File(context.getFilesDir(),"cbz-reading-reopen-baseline.json").toPath(),snapshot().getBytes(StandardCharsets.UTF_8));
            }else{
                books=new JSONObject(new String(Files.readAllBytes(new File(context.getFilesDir(),"cbz-reading-books.json").toPath()),StandardCharsets.UTF_8));launch();waitFrame(book("cbz"));idle();assertPage(1);
                if(phase.equals("crash")){panel();gate("committed");click("添加书签");setText("CBZ lost response exact request");click("保存");arrived("committed");Files.write(new File(context.getFilesDir(),"cbz-reading-crash-baseline.json").toPath(),snapshot().getBytes(StandardCharsets.UTF_8));Files.write(new File(context.getFilesDir(),"cbz-reading-crash-ready").toPath(),new byte[]{1});SystemClock.sleep(60000);throw new AssertionError("driver must kill the real postcommit CBZ process");}
                else if(phase.equals("retry"))check("real_cbz_postcommit_process_kill_exact_retry_has_no_duplicate",()->{String before=snapshot(),committed=new String(Files.readAllBytes(new File(context.getFilesDir(),"cbz-reading-crash-baseline.json").toPath()),StandardCharsets.UTF_8);need(before.equals(committed),"real commit survived process death");JSONObject pending=new JSONObject(ReadingCapture.decode(Files.readAllBytes(new File(context.getFilesDir(),"reading-request.json").toPath())));ReadingRecord saved=record("cbz","CBZ lost response exact request");need(saved.id.equals(pending.getString("annotation"))&&saved.head.equals(pending.getString("revision"))&&saved.capture.pageId.equals("002.png"),"stable original ID/head and real page selector survived kill");panel();click("上次保存待确认");click("继续确认保存");settled();need(snapshot().equals(before)&&!new File(context.getFilesDir(),"reading-request.json").exists(),"same exact persisted request confirms without duplicate/history/outbox/SDK mutation");capture("cbz-exact-retry");closePanel();Files.write(new File(context.getFilesDir(),"cbz-reading-reopen-baseline.json").toPath(),snapshot().getBytes(StandardCharsets.UTF_8));});
                else if(phase.equals("reopen"))check("fresh_process_retains_cbz_empty_tags_and_actual_found_navigation",()->{String before=new String(Files.readAllBytes(new File(context.getFilesDir(),"cbz-reading-reopen-baseline.json").toPath()),StandardCharsets.UTF_8);need(snapshot().equals(before),"source SDK and complete product graph remain identical after fresh process");ReadingRecord saved=record("cbz","CBZ page two");for(byte[] bytes:saved.capture.bytes())need(bytes!=null&&bytes.length==0,"empty selector tags persist without NULL conversion");for(NativeReadingSdk.Match match:both(saved.capture))need(match.found()&&match.unit==1&&match.recaptured.pageId.equals("002.png"),"independent and actual fresh renderer still public FOUND");panel();jump("CBZ page two");assertPage(1);capture("cbz-reopened-found");});
                else throw new AssertionError("unknown CBZ phase");
            }
        }catch(Throwable error){failure=error;try{capture("failure");}catch(Throwable captureError){error.addSuppressed(captureError);}}
        try{
            JSONObject report=new JSONObject().put("source_sha",arguments.getString("source_sha")).put("run_id",arguments.getString("run_id")).put("attempt",arguments.getString("attempt")).put("phase",phase).put("pid",android.os.Process.myPid()).put("passed",failure==null).put("checks",checks).put("count",checks.length()).put("observations",observations).put("actual_pages",actualPages);
            if(failure!=null)report.put("failed_check",active).put("failure",failure.getMessage()).put("failure_trace",android.util.Log.getStackTraceString(failure));
            Files.write(new File(context.getFilesDir(),"cbz-reading-ui-"+phase+".json").toPath(),report.toString(2).getBytes(StandardCharsets.UTF_8));result.putString("stream",failure==null?"CBZ_READING_UI_PASS "+phase:"CBZ_READING_UI_FAIL "+phase);finish(failure==null?Activity.RESULT_OK:Activity.RESULT_CANCELED,result);
        }catch(Exception error){result.putString("shortMsg","CBZ evidence unavailable");finish(Activity.RESULT_CANCELED,result);}
    }
}
