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
public final class ReadingUiTest extends Instrumentation {
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
                JSONObject row=originals.getJSONObject(i);File file=new File(context.getFilesDir(),"reading-fixtures/"+row.getString("file"));need(file.length()==row.getLong("bytes"),"seed original length");
                NativeLibrary.ImportResult result=row.getString("role").equals("legacy")?library.importLegacyFile(file.getAbsolutePath(),format(row.getString("format")),row.getString("title")):library.importFile(file.getAbsolutePath(),format(row.getString("format")),row.getString("title"));need(hash(library,result.id).equals(row.getString("sha256")),"SDK original fixture identity");
                String title=null;for(NativeLibrary.Book found:library.books())if(found.id==result.id)title=found.title;
                need(title!=null,"SDK book after import");books.put(row.getString("role"),new JSONObject().put("id",result.id).put("title",title).put("sha256",row.getString("sha256")).put("format",row.getString("format")));
                need(context.getSharedPreferences("host",0).edit().putString("path_"+result.id,file.getAbsolutePath()).putLong("size_"+result.id,file.length()).commit(),"host original path registered");
            }
            library.saveProgress(book("txt"),0);library.saveNote(book("txt"),0,0,0,"retained existing SDK note");
        }
        Files.write(new File(context.getFilesDir(),"reading-books.json").toPath(),books.toString().getBytes(StandardCharsets.UTF_8));
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
        AccessibilityNodeInfo root=getUiAutomation().getRootInActiveWindow();need(root!=null,"search capture root");int[] count={0};JSONObject value;try{value=tree(root,0,count);}finally{root.recycle();}
        File folder=new File(context.getFilesDir(),"reading-captures");need(folder.isDirectory()||folder.mkdirs(),"search captures directory");Bitmap image=getUiAutomation().takeScreenshot();need(image!=null,"search screenshot");try(FileOutputStream output=new FileOutputStream(new File(folder,name+".png"))){need(image.compress(Bitmap.CompressFormat.PNG,100,output),"PNG written");}finally{image.recycle();}
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
    private byte[] retained(String role,ReadingRecord record)throws Exception{String key=key(role);return owner(store->NativeReadingProduct.retained(store,key,record.id,record.head,record.kind==ReadingRecord.PROGRESS,control()));}
    private String inject(String role,ReadingRecord original,String body,int state)throws Exception{
        JSONObject wire=new JSONObject(ReadingCapture.decode(retained(role,original)));String id=ReadingRequests.newId(),head=ReadingRequests.newId();wire.put("id",head).put("entity_key",key(role)+":"+id).put("parents",new JSONArray());wire.getJSONObject("payload").put("annotation_id",id).put("text",body);
        if(state==ReadingRecord.PENDING)wire.put("parents",new JSONArray().put(ReadingRequests.newId()));
        owner(store->NativeReadingProbe.receive(store.productOwner(),ReadingCapture.encode(wire.toString(),1048576)));
        if(state==ReadingRecord.CONCURRENT){wire.put("id",ReadingRequests.newId());owner(store->NativeReadingProbe.receive(store.productOwner(),ReadingCapture.encode(wire.toString(),1048576)));}
        if(state==ReadingRecord.BLOCKED){String deleted=ReadingRequests.newId();JSONObject tombstone=new JSONObject(wire.toString()).put("id",deleted).put("parents",new JSONArray().put(head)).put("operation","delete").put("payload",JSONObject.NULL);owner(store->NativeReadingProbe.receive(store.productOwner(),ReadingCapture.encode(tombstone.toString(),1048576)));wire.put("id",ReadingRequests.newId()).put("parents",new JSONArray().put(deleted));owner(store->NativeReadingProbe.receive(store.productOwner(),ReadingCapture.encode(wire.toString(),1048576)));}
        return id;
    }
    private void selectorBoundaries()throws Exception{
        byte[] font;try(java.io.InputStream input=context.getAssets().open("Reader.otf");java.io.ByteArrayOutputStream output=new java.io.ByteArrayOutputStream()){byte[] bytes=new byte[65536];for(int count;(count=input.read(bytes))>0;)output.write(bytes,0,count);font=output.toByteArray();}
        for(String role:new String[]{"txt","pdf"}){open(role);AtomicReference<PageSnapshot> actual=new AtomicReference<>();runOnMainSync(()->{try{actual.set((PageSnapshot)ReadingReview.field(activity(),"current"));}catch(Exception error){throw new RuntimeException(error);}});PageSnapshot page=actual.get();long end=page.starts.length>1?page.ends[1]:page.start;need(end>page.start,"genuine source selector range");File original=new File(context.getSharedPreferences("host",0).getString("path_"+page.bookId,""));final byte[] face=font;
            owner(store->{ReadingCapture real=NativeReadingSdk.capture(store,page,page.start,end,face,24f,original,task(),control());byte[][] changed=real.bytes();Arrays.fill(changed[0],(byte)'!');NativeReadingSdk.Match missing=NativeReadingSdk.resolve(store,page.bookId,new ReadingCapture(real.numbers(),real.route(),changed),face,24f,task(),control());need(!missing.found()&&missing.start==-1,"valid missing selector never falls back to old offset");
                if(real.mode==ReadingCapture.REFLOW){changed=real.bytes();changed[0]=null;NativeReadingSdk.Match legacy=NativeReadingSdk.resolve(store,page.bookId,new ReadingCapture(real.numbers(),real.route(),changed),face,24f,task(),control());need(!legacy.found()&&legacy.state==NativeReadingSdk.LEGACY,"NULL stays legacy, never an invented point");}
                else{changed=real.bytes();changed[0][0]=0;NativeReadingSdk.Match nul=NativeReadingSdk.resolve(store,page.bookId,new ReadingCapture(real.numbers(),real.route(),changed),face,24f,task(),control());need(!nul.found(),"fixed embedded NUL retains explicit byte length");String[] route=real.route();route[3]="missing-page-id";NativeReadingSdk.Match absent=NativeReadingSdk.resolve(store,page.bookId,new ReadingCapture(real.numbers(),route,real.bytes()),face,24f,task(),control());need(!absent.found()&&absent.unit==-1,"missing page ID never trusts page hint");}
                return true;
            });
        }
    }
    private void requestOwnerBoundaries()throws Exception{
        File directory=new File(context.getFilesDir(),"reading-request-owner-probe");need(directory.isDirectory()||directory.mkdir(),"private request fixture directory");ReadingRequests first=new ReadingRequests(directory);first.clear();ReadingCapture capture=record("txt","TXT point 🙂").capture;
        ReadingRequests.Pending old=new ReadingRequests.Pending(book("txt"),key("txt"),ReadingRequests.newId(),ReadingRequests.newId(),ReadingRequests.newId(),new String[0],NativeReadingProduct.BOOKMARK,NativeReadingProduct.PUT,capture.mode,capture,"older request");
        ReadingRequests.Pending newer=new ReadingRequests.Pending(book("txt"),key("txt"),ReadingRequests.newId(),ReadingRequests.newId(),ReadingRequests.newId(),new String[0],NativeReadingProduct.BOOKMARK,NativeReadingProduct.PUT,capture.mode,capture,"newer request");
        first.save(old);first.clear();AtomicReference<Throwable> failure=new AtomicReference<>();Thread replacement=new Thread(()->{try{new ReadingRequests(directory).save(newer);}catch(Throwable error){failure.set(error);}});replacement.start();replacement.join(5000);need(!replacement.isAlive()&&failure.get()==null,"new Activity owner saves its own durable request");boolean refused=false;try{first.clear(old.revision);}catch(java.io.IOException expected){refused=true;}need(refused&&first.read().revision.equals(newer.revision),"delayed old owner cleanup never erases newer uncertain request");first.clear(newer.revision);
        java.util.concurrent.CountDownLatch start=new java.util.concurrent.CountDownLatch(1);java.util.concurrent.atomic.AtomicInteger saved=new java.util.concurrent.atomic.AtomicInteger(),blocked=new java.util.concurrent.atomic.AtomicInteger();Thread[] writers=new Thread[2];ReadingRequests.Pending[] values={old,newer};for(int i=0;i<2;i++){final int index=i;writers[i]=new Thread(()->{try{ReadingRequests requests=new ReadingRequests(directory);start.await();requests.save(values[index]);saved.incrementAndGet();}catch(java.io.IOException occupied){blocked.incrementAndGet();}catch(Throwable error){failure.set(error);}});writers[i].start();}start.countDown();for(Thread writer:writers){writer.join(5000);need(!writer.isAlive(),"bounded private request writer completion");}need(failure.get()==null&&saved.get()==1&&blocked.get()==1&&first.read()!=null,"two Activity owners cannot overwrite one uncertain request");first.clear();
    }
    private void legacyProjection()throws Exception{
        open("legacy");need(frame().getInt("part")==-1,"real old EPUB uses global renderer");byte[] font;try(java.io.InputStream input=context.getAssets().open("Reader.otf");java.io.ByteArrayOutputStream output=new java.io.ByteArrayOutputStream()){byte[] bytes=new byte[65536];for(int count;(count=input.read(bytes))>0;)output.write(bytes,0,count);font=output.toByteArray();}final byte[] face=font;long id=book("legacy");String key=key("legacy");
        Method capture=NativeReadingSdk.class.getDeclaredMethod("nativeCapture",long.class,long.class,int.class,long.class,String.class,long.class,long.class,String.class,byte[].class,float.class,ReadingControl.class);capture.setAccessible(true);
        owner(store->{need(!store.bounded(id),"legacy import really retains unbounded SDK mode");ReadingCapture chapter=(ReadingCapture)capture.invoke(null,store.nativeLibrary().checked(),id,ReadingCapture.EPUB,1L,"b.xhtml",0L,0L,key,face,28f,control());need(chapter.mode==ReadingCapture.EPUB&&chapter.unit==1&&chapter.partPath.equals("b.xhtml"),"genuine independent public pager capture in second chapter");NativeCatalog.Result bootstrap=store.bootstrapBook(id,ReadingRequests.newId(),new String[0],task());need(bootstrap.status==NativeCatalog.Result.OK,"explicit typed source fact fixture");NativeReadingProduct.Result saved=NativeReadingProduct.apply(store,ReadingRequests.newId(),new String[0],NativeReadingProduct.BOOKMARK,NativeReadingProduct.PUT,key,ReadingRequests.newId(),chapter.mode,chapter,"foreign chapter projection");need(saved.saved(),"G03 retains real foreign chapter selector");return true;});
        need(record("legacy","foreign chapter projection").capture.mode==ReadingCapture.EPUB,"G04 returns retained chapter identity without conversion");String state=snapshot(),page=stableFrame();panel();contains("foreign chapter projection");click("跳转到此处");status("记录的分页方式与当前文档不同，未跳转");unchanged(state,page);capture("legacy-projection-refused");closePanel();
    }
    private void assertUnsafe(String role,String id,int state)throws Exception{NativeReadingProduct.Page page=records(role);for(ReadingRecord row:page.rows)if(row.id.equals(id)){need(row.state==state&&row.capture==null&&row.body.isEmpty()&&row.head.isEmpty(),"unsafe G04 has counts but no chosen version");return;}throw new AssertionError("unsafe graph missing");}
    @Override public void onStart(){
        context=getTargetContext();phase=arguments.getString("phase");Throwable failure=null;Bundle result=new Bundle();
        try{
            readerMonitor=addMonitor(MainActivity.class.getName(),null,false);AccessibilityServiceInfo service=getUiAutomation().getServiceInfo();service.flags|=AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS|AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS;getUiAutomation().setServiceInfo(service);
            need(BuildConfig.READER_READING&&BuildConfig.READER_NAVIGATION&&BuildConfig.READER_SEARCH&&BuildConfig.READER_SYNC,"all actual reading features enabled");input=new JSONObject(new String(Files.readAllBytes(new File(context.getFilesDir(),"reading-input.json").toPath()),StandardCharsets.UTF_8));
            if(phase.equals("first")){
                seed();launch();
                check("same_sdk_product_sqlite_and_installed_g03_g04",()->{open("txt");String[] providers=NativeReadingProbe.identity();need(providers.length==3&&providers[0].contains("libexreader_product.so")&&Arrays.stream(providers).allMatch(providers[0]::equals),"G03 G04 and sole product SQLite in original product DSO");need(NativeLibrary.syncIdentity()[1].contains("libexreader.so"),"original SDK provider");});
                check("read_only_empty_list_preserves_sdk_product_and_pixels",()->{String state=snapshot(),page=stableFrame();panel();status("0 条记录");unchanged(state,page);capture("empty-records");closePanel();unchanged(state,page);});
                check("real_txt_progress_and_point_bookmark_do_not_write_sdk",()->{String sdk=sdk(),page=stableFrame();panel();click("保存进度");settled();ReadingRecord progress=records("txt").progress;need(progress.readable()&&progress.capture.start==progress.capture.end&&progress.anchorVersion==2&&progress.capture.chapter==null,"real SDK point preserved with nullable scope");bookmark("TXT point 🙂");ReadingRecord point=record("txt","TXT point 🙂");need(point.readable()&&point.capture.mode==ReadingCapture.REFLOW&&point.capture.start==point.capture.end,"actual point bookmark");need(sdk().equals(sdk)&&stableFrame().equals(page),"product saving never rewrites SDK or reader frame");capture("txt-point-progress");closePanel();});
                check("real_txt_selection_highlight_and_note_edit_keep_selector",()->{String sdk=sdk();highlight("Original note");ReadingRecord before=record("txt","Original note");need(before.capture.end>before.capture.start,"real gesture range captured");contains("Original note");click("编辑文字");setText("Edited note 🙂");click("保存");settled();ReadingRecord after=record("txt","Edited note 🙂");need(Arrays.equals(before.capture.numbers(),after.capture.numbers())&&Arrays.equals(before.capture.route(),after.capture.route())&&Arrays.deepEquals(before.capture.bytes(),after.capture.bytes())&&before.anchorVersion==after.anchorVersion,"NOTE_TEXT preserves exact selector parser null tags");need(sdk().equals(sdk),"note edit leaves SDK notes and progress alone");capture("txt-range-note");closePanel();});
                check("explicit_current_found_navigation_renders_without_sdk_note_copy",()->{panel();jump("TXT point 🙂");need(frame().getLong("start")==0,"genuine point resolved and rendered");capture("txt-found");});
                check("delete_and_explicit_retained_restore_do_not_auto_navigate",()->{panel();ReadingRecord before=record("txt","TXT point 🙂");String page=stableFrame(),sdk=sdk();contains("TXT point 🙂");click("删除");click("删除");settled();ReadingRecord tombstone=owner(store->NativeReadingProduct.selected(store,key("txt"),before.id,"",false,control()));need(tombstone.deleted&&tombstone.state==ReadingRecord.SAFE&&tombstone.capture==null,"safe tombstone keeps no invented capture");contains("已删除");click("选择保留版本恢复");until(node->text(node).startsWith("版本 1"),this::tap,"explicit retained version",30000);click("恢复");settled();ReadingRecord restored=record("txt","TXT point 🙂");need(restored.id.equals(before.id)&&restored.readable()&&restored.operation.equals("restore"),"G03 explicit restore creates history on same entity");need(stableFrame().equals(page)&&sdk().equals(sdk),"delete and restore neither navigate nor write SDK");capture("explicit-restored-record");closePanel();});
                check("epub_actual_capture_keeps_spine_path_and_current_font",()->{open("epub");until(node->id(node,"font_up")&&node.isEnabled(),this::tap,"font increase",30000);long end=SystemClock.elapsedRealtime()+120000;while(frame().optDouble("font",0)!=28&&SystemClock.elapsedRealtime()<end)SystemClock.sleep(60);need(frame().optDouble("font",0)==28,"actual EPUB 28pt layout");String sdk=sdk();panel();bookmark("EPUB point");ReadingRecord point=record("epub","EPUB point");need(point.capture.mode==ReadingCapture.EPUB&&point.capture.unit==frame().getInt("part")&&point.capture.partPath.equals(frame().getString("path")),"actual bounded spine index and path");need(sdk().equals(sdk),"EPUB product point not SDK progress");closePanel();highlight("EPUB range");ReadingRecord range=record("epub","EPUB range");need(range.capture.end>range.capture.start,"actual bounded range");closePanel();panel();jump("EPUB point");capture("epub-record-found");});
                check("pdf_and_cbz_real_page_id_points",()->{
                    for(String role:new String[]{"pdf","blank","cbz"}){
                        open(role);String sdk=sdk();JSONObject before=frame();panel();bookmark(role+" point");ReadingRecord point=record(role,role+" point");
                        need(point.capture.mode==ReadingCapture.FIXED&&point.capture.pageId!=null&&point.capture.start==point.capture.end,"public fixed point keeps exact page ID");
                        if(role.equals("cbz")){
                            need(before.getBoolean("fixed_public_text")&&before.getLong("fixed_public_text_bytes")==0&&point.capture.pageId.equals(before.getString("fixed_page_id")),"CBZ real renderer empty snapshot and public page ID");
                            for(byte[] selector:point.capture.bytes())need(selector!=null&&selector.length==0,"genuine SDK empty bytes remain distinct from NULL through G03/G04");
                        }
                        need(sdk().equals(sdk),"fixed product point leaves SDK state alone");closePanel();panel();jump(role+" point");need(frame().getInt("index")==0,"exact page ID rendered");
                        if(role.equals("cbz"))need(frame().getString("fixed_page_id").equals(point.capture.pageId),"independent and actual current renderer FOUND agree before drawing CBZ");
                        capture(role+"-point-found");
                    }
                });
                check("missing_legacy_nul_and_fixed_page_id_are_never_guessed",()->{selectorBoundaries();requestOwnerBoundaries();legacyProjection();});
                check("unsafe_graphs_display_counts_without_exposing_or_choosing_heads",()->{open("txt");ReadingRecord sample=record("txt","Edited note 🙂");String conflict=inject("txt",sample,"conflict-hidden",ReadingRecord.CONCURRENT),pending=inject("txt",sample,"pending-hidden",ReadingRecord.PENDING),blocked=inject("txt",sample,"blocked-hidden",ReadingRecord.BLOCKED);assertUnsafe("txt",conflict,ReadingRecord.CONCURRENT);assertUnsafe("txt",pending,ReadingRecord.PENDING);assertUnsafe("txt",blocked,ReadingRecord.BLOCKED);String state=snapshot(),page=stableFrame();panel();contains("版本有冲突");until(node->text(node).contains("未选择任何版本"),null,"unsafe explanation",30000);click("返回");need(!act(node->text(node).contains("conflict-hidden")||text(node).contains("pending-hidden"),null),"unsafe body never displayed");unchanged(state,page);capture("unsafe-record-counts");closePanel();});
                check("stale_selected_head_never_overwrites_new_head",()->{panel();contains("Edited note 🙂");click("编辑文字");ReadingRecord old=record("txt","Edited note 🙂");owner(store->{NativeReadingProduct.Result changed=NativeReadingProduct.apply(store,ReadingRequests.newId(),new String[]{old.head},NativeReadingProduct.NOTE_TEXT,NativeReadingProduct.PUT,key("txt"),old.id,old.mode,null,"changed on owner");need(changed.saved(),"public concurrent change fixture");return true;});setText("stale text");click("保存");until(node->description(node,"阅读记录状态")&&text(node).contains("未能完成"),null,"stale head refused",30000);need(record("txt","changed on owner").id.equals(old.id)&&!new File(context.getFilesDir(),"reading-request.json").exists(),"stale refusal retains new head and no uncertain request");closePanel();});
                check("cancel_real_capture_keeps_stores_and_actual_frame",()->{String state=snapshot(),page=stableFrame();panel();gate("capture");click("添加书签");setText("cancelled never saved");click("保存");arrived("capture");long began=SystemClock.elapsedRealtime();click("取消读取");need(SystemClock.elapsedRealtime()-began<2000,"cancel never waits for SDK owner");status("已取消");unchanged(state,page);need(!new File(context.getFilesDir(),"reading-request.json").exists(),"cancel before publication has no pending request");closePanel();});
                check("close_rotation_background_drop_real_pending_reads",()->{String state=snapshot();panel();gate("list");click("刷新");arrived("list");closePanel();owner(store->true);need(snapshot().equals(state),"close discards list without mutation");panel();gate("list");click("刷新");arrived("list");long oldView=frame().getLong("view");getUiAutomation().setRotation(android.app.UiAutomation.ROTATION_FREEZE_90);long end=SystemClock.elapsedRealtime()+120000;while(SystemClock.elapsedRealtime()<end){try{if(frame().optLong("view",oldView)!=oldView&&frame().has("bitmap_identity"))break;}catch(AssertionError absent){}SystemClock.sleep(80);}need(frame().getLong("view")!=oldView,"actual rotation creates new reader view");long rotatedView=frame().getLong("view");getUiAutomation().setRotation(android.app.UiAutomation.ROTATION_FREEZE_0);freshView(book("txt"),rotatedView);panel();gate("list");click("刷新");arrived("list");getUiAutomation().executeShellCommand("input keyevent KEYCODE_HOME").close();owner(store->true);need(snapshot().equals(state),"rotation and background do not pick records or mutate history");launch();waitFrame(book("txt"));capture("reader-after-lifecycle");});
                check("bounded_record_pagination_and_plain_text_labels",()->{ReadingRecord sample=record("txt","changed on owner");for(int i=0;i<35;i++)inject("txt",sample,"bulk "+i,ReadingRecord.SAFE);String state=snapshot(),page=stableFrame();panel();status("32 条记录");click("下一批");until(node->description(node,"阅读记录状态")&&!text(node).startsWith("32 条"),null,"second bounded page",30000);click("上一批");status("32 条记录");unchanged(state,page);capture("records-keyset-pagination");closePanel();});
                Files.write(new File(context.getFilesDir(),"reading-reopen-baseline.json").toPath(),snapshot().getBytes(StandardCharsets.UTF_8));
            }else{
                books=new JSONObject(new String(Files.readAllBytes(new File(context.getFilesDir(),"reading-books.json").toPath()),StandardCharsets.UTF_8));launch();waitFrame(book("txt"));
                if(phase.equals("crash")){panel();gate("committed");click("添加书签");setText("lost response exact request");click("保存");arrived("committed");Files.write(new File(context.getFilesDir(),"reading-crash-ready").toPath(),new byte[]{1});SystemClock.sleep(60000);throw new AssertionError("driver must kill process at real postcommit gate");}
                else if(phase.equals("retry"))check("real_process_kill_after_commit_replays_identical_request_without_duplicate",()->{String before=snapshot();byte[] pending=Files.readAllBytes(new File(context.getFilesDir(),"reading-request.json").toPath());JSONObject request=new JSONObject(ReadingCapture.decode(pending));String id=request.getString("annotation"),rid=request.getString("revision");need(record("txt","lost response exact request").id.equals(id),"commit survived real process kill before response");panel();click("上次保存待确认");click("继续确认保存");settled();need(snapshot().equals(before)&&!new File(context.getFilesDir(),"reading-request.json").exists(),"exact retry neither duplicates history nor requeues outbox");need(record("txt","lost response exact request").head.equals(rid),"same stable revision confirmed");capture("process-kill-exact-retry");closePanel();Files.write(new File(context.getFilesDir(),"reading-reopen-baseline.json").toPath(),snapshot().getBytes(StandardCharsets.UTF_8));});
                else if(phase.equals("reopen"))check("process_reopen_retains_reading_graph_and_releases_old_panels",()->{String before=new String(Files.readAllBytes(new File(context.getFilesDir(),"reading-reopen-baseline.json").toPath()),StandardCharsets.UTF_8);need(snapshot().equals(before),"all originals notes progress graph queues survive fresh process");panel();status("32 条记录");capture("records-after-reopen");closePanel();});
                else throw new AssertionError("Unknown reading phase");
            }
        }catch(Throwable error){failure=error;try{capture("failure");}catch(Throwable captureError){error.addSuppressed(captureError);}}
        try{
            JSONObject report=new JSONObject().put("source_sha",arguments.getString("source_sha")).put("run_id",arguments.getString("run_id")).put("attempt",arguments.getString("attempt")).put("phase",phase).put("pid",android.os.Process.myPid()).put("passed",failure==null).put("checks",checks).put("count",checks.length()).put("observations",observations);
            if(failure!=null)report.put("failed_check",active).put("failure_class",failure.getClass().getName()).put("failure",failure.getMessage()).put("failure_trace",android.util.Log.getStackTraceString(failure));
            Files.write(new File(context.getFilesDir(),"reading-ui-"+phase+".json").toPath(),report.toString(2).getBytes(StandardCharsets.UTF_8));result.putString("stream",failure==null?"READING_UI_PASS "+phase:"READING_UI_FAIL "+phase);finish(failure==null?Activity.RESULT_OK:Activity.RESULT_CANCELED,result);
        }catch(Exception error){result.putString("shortMsg","Reading evidence unavailable");finish(Activity.RESULT_CANCELED,result);}
    }
}
