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
public final class PreferencesUiTest extends Instrumentation {
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
    private void launch(){context.startActivity(new Intent(context,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TOP).putExtra("exr_preferences_gate",true));}
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
                JSONObject row=originals.getJSONObject(i);File file=new File(context.getFilesDir(),"preferences-fixtures/"+row.getString("file"));need(file.length()==row.getLong("bytes"),"seed original length");
                NativeLibrary.ImportResult result=row.getString("role").equals("legacy")?library.importLegacyFile(file.getAbsolutePath(),format(row.getString("format")),row.getString("title")):library.importFile(file.getAbsolutePath(),format(row.getString("format")),row.getString("title"));need(hash(library,result.id).equals(row.getString("sha256")),"SDK original fixture identity");
                String title=null;for(NativeLibrary.Book found:library.books())if(found.id==result.id)title=found.title;
                need(title!=null,"SDK book after import");books.put(row.getString("role"),new JSONObject().put("id",result.id).put("title",title).put("sha256",row.getString("sha256")).put("format",row.getString("format")));
                need(context.getSharedPreferences("host",0).edit().putString("path_"+result.id,file.getAbsolutePath()).putLong("size_"+result.id,file.length()).commit(),"host original path registered");
            }
            library.saveProgress(book("txt"),0);library.saveNote(book("txt"),0,0,0,"retained existing SDK note");
        }
        Files.write(new File(context.getFilesDir(),"preferences-books.json").toPath(),books.toString().getBytes(StandardCharsets.UTF_8));
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
    private JSONObject tree(AccessibilityNodeInfo node,int depth,int[] count)throws Exception {
        need(depth<=32&&++count[0]<=2048,"semantic tree bounds");JSONArray children=new JSONArray();for(int i=0;i<node.getChildCount();i++){AccessibilityNodeInfo child=node.getChild(i);if(child!=null){try{children.put(tree(child,depth+1,count));}finally{child.recycle();}}}
        return new JSONObject().put("id",node.getViewIdResourceName()).put("text",text(node)).put("description",String.valueOf(node.getContentDescription())).put("actions",node.getActions()).put("children",children);
    }
    private void capture(String name)throws Exception {
        long deadline=SystemClock.elapsedRealtime()+10000;AccessibilityNodeInfo root=null;while(root==null&&SystemClock.elapsedRealtime()<deadline){root=getUiAutomation().getRootInActiveWindow();if(root==null)SystemClock.sleep(80);}need(root!=null,"actual semantic root after window transition");int[] count={0};JSONObject value;try{value=tree(root,0,count);}finally{root.recycle();}
        File folder=new File(context.getFilesDir(),"preferences-captures");need(folder.isDirectory()||folder.mkdirs(),"search captures directory");Bitmap image=null;deadline=SystemClock.elapsedRealtime()+10000;while(image==null&&SystemClock.elapsedRealtime()<deadline){image=getUiAutomation().takeScreenshot();if(image==null)SystemClock.sleep(80);}need(image!=null,"actual screenshot after window transition");try(FileOutputStream output=new FileOutputStream(new File(folder,name+".png"))){need(image.compress(Bitmap.CompressFormat.PNG,100,output),"PNG written");}finally{image.recycle();}
        JSONObject observation=new JSONObject().put("name",name).put("nodes",count[0]).put("tree",value);try{observation.put("frame",frame());}catch(AssertionError absent){}observations.put(observation);
    }
    private Activity activity(){Activity activity=readerMonitor.getLastActivity();need(activity!=null,"actual host activity");return activity;}
    private <T>T owner(ReadingReview.Call<T> call)throws Exception{return ReadingReview.call(activity(),call);}
    private HostTask task(){return new HostTask(()->false);}
    private ReadingControl control(){return new ReadingControl(task(),context.getFilesDir(),"probe",false);}
    private String key(String role)throws Exception{return books.getJSONObject(role).getString("format")+":"+books.getJSONObject(role).getString("sha256");}
    private File settings(){return new File(context.getFilesDir(),"reading-settings/preferences.json");}
    private byte[] saved()throws Exception{return settings().isFile()?Files.readAllBytes(settings().toPath()):new byte[0];}
    private void same(byte[] file,String page)throws Exception{need(Arrays.equals(file,saved()),"last complete preferences file unchanged");need(stableFrame().equals(page),"old accepted page and original pixels retained");}
    private void settingsPanel(){until(node->description(node,"阅读更多操作")&&node.isEnabled(),this::tap,"reader More",30000);click("阅读设置");until(node->description(node,"字号 pt"),null,"native settings editor",30000);}
    private boolean scroll(boolean forward){return act(node->node.isScrollable()&&"android.widget.ScrollView".contentEquals(node.getClassName()),node->node.performAction(forward?AccessibilityNodeInfo.ACTION_SCROLL_FORWARD:AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD));}
    private void visible(String label){for(int i=0;i<12;i++){if(act(node->description(node,label)&&node.isVisibleToUser(),null))return;scroll(true);SystemClock.sleep(80);}throw new AssertionError("settings control visible: "+label);}
    private void edit(String label,String value){for(int i=0;i<12;i++)scroll(false);visible(label);until(node->description(node,label),node->{Bundle data=new Bundle();data.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,value);need(node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,data),"native text entry "+label);},"settings "+label,30000);}
    private void choose(String label,String value){for(int i=0;i<12;i++)scroll(false);visible(label);until(node->description(node,label)&&node.isVisibleToUser(),this::tap,"settings choice "+label,30000);click(value);}
    private void panelFailure(String value){until(node->description(node,"阅读设置状态")&&text(node).contains(value),null,"settings refusal "+value,120000);}
    private void idle()throws Exception{owner(store->true);long end=SystemClock.elapsedRealtime()+30000;while(SystemClock.elapsedRealtime()<end){AtomicReference<Boolean> done=new AtomicReference<>(false);runOnMainSync(()->{try{done.set(((Integer)ReadingReview.field(activity(),"operation"))==0);}catch(Exception error){throw new RuntimeException(error);}});if(done.get())return;SystemClock.sleep(30);}throw new AssertionError("host owner returned to idle");}
    private JSONObject applied(long token)throws Exception{long end=SystemClock.elapsedRealtime()+120000;while(SystemClock.elapsedRealtime()<end){JSONObject page=frame();if(page.optLong("accepted_token",0)>token&&!act(node->description(node,"阅读设置状态"),null)){idle();return page;}String[] error={null};act(node->description(node,"阅读设置状态")&&(text(node).contains("未保存")||text(node).contains("Reading settings")||text(node).contains("Invalid")),node->error[0]=text(node));if(error[0]!=null)throw new AssertionError("actual host refused settings: "+error[0]);SystemClock.sleep(60);}throw new AssertionError("settings did not publish actual new frame");}
    private void apply()throws Exception{long token=frame().getLong("accepted_token");click("应用");applied(token);}
    private void paging(boolean forward)throws Exception{long token=frame().getLong("accepted_token");AtomicReference<Boolean> accepted=new AtomicReference<>(false);runOnMainSync(()->{ReaderView view=activity().findViewById(R.id.reader_view);accepted.set(view.performAccessibilityAction(forward?AccessibilityNodeInfo.ACTION_SCROLL_FORWARD:AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD,null));});need(accepted.get(),"actual semantic page navigation");long end=SystemClock.elapsedRealtime()+120000;while(frame().optLong("accepted_token",0)<=token&&SystemClock.elapsedRealtime()<end)SystemClock.sleep(40);need(frame().optLong("accepted_token",0)>token,"actual page rendered");idle();}
    private void gesture(float fromX,float fromY,float toX,float toY)throws Exception{Rect box=new Rect();until(node->id(node,"reader_view")&&node.isVisibleToUser(),node->node.getBoundsInScreen(box),"real reader gesture bounds",30000);float x=box.left+box.width()*fromX,y=box.top+box.height()*fromY,ex=box.left+box.width()*toX,ey=box.top+box.height()*toY;long now=SystemClock.uptimeMillis();sendPointerSync(MotionEvent.obtain(now,now,MotionEvent.ACTION_DOWN,x,y,0));if(fromX!=toX||fromY!=toY){SystemClock.sleep(60);sendPointerSync(MotionEvent.obtain(now,now+60,MotionEvent.ACTION_MOVE,ex,ey,0));}SystemClock.sleep(40);sendPointerSync(MotionEvent.obtain(now,SystemClock.uptimeMillis(),MotionEvent.ACTION_UP,ex,ey,0));idle();SystemClock.sleep(100);}
    private void changed(long token)throws Exception{long end=SystemClock.elapsedRealtime()+120000;while(frame().optLong("accepted_token",0)<=token&&SystemClock.elapsedRealtime()<end)SystemClock.sleep(40);need(frame().optLong("accepted_token",0)>token,"preferred actual gesture turned page");idle();}
    private void nativeReopenChecks()throws Exception{
        byte[] original=saved();JSONObject document=new JSONObject(new String(original,StandardCharsets.UTF_8));File other=new File(context.getFilesDir(),"preferences-invalid.json");
        for(String variant:new String[]{"version","truncated","oversize"}){
            byte[] data=variant.equals("version")?new JSONObject(document.toString()).put("format_version",999).toString().getBytes(StandardCharsets.UTF_8):variant.equals("truncated")?Arrays.copyOf(original,original.length/2):new byte[65537];Files.write(other.toPath(),data);
            boolean refused=false;try{owner(store->NativePreferences.load(other.getPath(),task()));}catch(Exception error){refused=true;}
            need(refused&&Arrays.equals(data,Files.readAllBytes(other.toPath()))&&Arrays.equals(original,saved()),"invalid/unknown load keeps exact disk bytes and active saved record");
        }
        Files.delete(other.toPath());
    }
    private JSONObject themeGap()throws Exception{
        byte[] font;try(java.io.InputStream input=context.getAssets().open("Reader.otf")){font=input.readAllBytes();}
        try(org.exreader.EXReader.Document doc=new org.exreader.EXReader.Document("<html><body><p>Theme pixel probe</p></body></html>".getBytes(StandardCharsets.UTF_8),org.exreader.EXReader.Format.HTML)){
            org.exreader.EXReader.LayoutConfig config=new org.exreader.EXReader.LayoutConfig();config.width=600;config.height=860;config.margin=48;config.userCSS="* { color: #e6e6e6; background-color: #101010; }";
            try(org.exreader.EXReader.Pager pager=doc.pager(font,0,config);org.exreader.EXReader.ReflowPage page=pager.next()){
                need(page!=null,"actual public SDK theme probe page");org.exreader.EXReader.Bitmap image=page.render();
                String corner=String.format(Locale.ROOT,"%02x%02x%02x%02x",image.pixels[0]&255,image.pixels[1]&255,image.pixels[2]&255,image.pixels[3]&255);
                need(!corner.equals("101010ff"),"requested full-page dark palette is not implemented by CSS");
                return new JSONObject().put("accepted",false).put("requested_background_rgba","101010ff").put("actual_corner_rgba",corner).put("user_css_attempted",config.userCSS).put("public_api_gap","exr_layout_config has no page backdrop/foreground override; exr_render_page_ex accepts channels/control, not a palette");
            }
        }
    }
    private JSONObject colorFailure;
    @Override public void onStart(){
        context=getTargetContext();phase=arguments.getString("phase");Throwable failure=null;Bundle result=new Bundle();
        try{
            readerMonitor=addMonitor(MainActivity.class.getName(),null,false);AccessibilityServiceInfo service=getUiAutomation().getServiceInfo();service.flags|=AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS|AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS;getUiAutomation().setServiceInfo(service);
            need(BuildConfig.READER_PREFERENCES&&BuildConfig.READER_READING&&BuildConfig.READER_NAVIGATION&&BuildConfig.READER_SEARCH&&BuildConfig.READER_SYNC,"actual full Android host feature flags");input=new JSONObject(new String(Files.readAllBytes(new File(context.getFilesDir(),"preferences-input.json").toPath()),StandardCharsets.UTF_8));
            if(phase.equals("first")){
                seed();launch();open("txt");
                check("installed_f3_defaults_and_explicit_legacy_import",()->{owner(store->{ReadingPreferences p=NativePreferences.defaults();need(p.font==24&&p.line==1.6f&&p.paragraph==12&&p.margin==48&&p.theme==1&&p.direction==1&&p.input==1&&p.zoom==100,"actual installed F3 defaults");ReadingPreferences old=NativePreferences.importLegacy(28,125,3);need(old.font==28&&old.zoom==125&&old.margin==48,"explicit legacy bits preserve unlisted defaults");need(NativePreferences.importLegacy(200,300,0).font==24,"unlisted legacy field never imported");return true;});need(frame().getDouble("margin")==48,"F3 default used in actual reader layout");});
                check("txt_real_relayout_preserves_public_found_point",()->{paging(true);JSONObject before=frame();long point=before.getLong("start");need(point>0,"genuine noninitial text point");String state=snapshot();settingsPanel();edit("字号 pt","30");edit("行距倍数","1.8");edit("段距 pt","18");edit("页边距 pt","40");apply();JSONObject after=frame();need(after.getLong("start")<=point&&after.getLong("end")>point&&after.getLong("preferences_point")==point,"public FOUND point inside new page");need(after.getDouble("font")==30&&after.getDouble("line_spacing")==1.8f&&after.getDouble("paragraph_spacing")==18&&after.getDouble("margin")==40,"four actual SDK layout inputs");need(after.getDouble("glyph_font_first")>=29.9&&after.getDouble("actual_first_x")>=39.9&&after.getDouble("actual_baseline_delta")>0,"actual SDK glyph geometry follows setting");need(!after.getJSONObject("bitmap_identity").getString("logical_argb_sha256").equals(before.getJSONObject("bitmap_identity").getString("logical_argb_sha256")),"actual new SDK bitmap");need(snapshot().equals(state),"relayout changes no SDK progress/notes/product revisions/outbox/source");capture("txt-relayout");});
                check("invalid_fields_keep_previous_file_model_and_pixels",()->{for(String[] invalid:new String[][]{{"字号 pt","3"},{"行距倍数","0.9"},{"段距 pt","-1"},{"页边距 pt","1025"},{"固定页缩放 %","401"},{"固定页缩放 %","125.5"}}){byte[] file=saved();String page=stableFrame();settingsPanel();edit(invalid[0],invalid[1]);click("应用");panelFailure(invalid[0].equals("固定页缩放 %")&&invalid[1].contains(".")?"整数":"RANGE");same(file,page);click("取消");}capture("range-refused");});
                check("sdk_composed_geometry_failure_keeps_last_settings",()->{byte[] file=saved();String page=stableFrame();settingsPanel();edit("页边距 pt","400");click("应用");panelFailure("Invalid");same(file,page);click("取消");});
                check("cancel_prepublication_discards_candidate_and_file",()->{byte[] file=saved();String page=stableFrame();Files.write(new File(context.getFilesDir(),"reading-preferences-gate-arm").toPath(),new byte[]{1});settingsPanel();edit("字号 pt","32");click("应用");long end=SystemClock.elapsedRealtime()+60000;while(!new File(context.getFilesDir(),"reading-preferences-gate-arrived").isFile()&&SystemClock.elapsedRealtime()<end)SystemClock.sleep(40);need(new File(context.getFilesDir(),"reading-preferences-gate-arrived").isFile(),"actual rendered candidate before durable publication");click("取消");idle();same(file,page);capture("cancel-retains-page");});
                check("real_atomic_save_io_failure_keeps_accepted_page",()->{File directory=settings().getParentFile();byte[] file=saved();String page=stableFrame();need(directory.setWritable(false,false),"real app directory made read-only");try{settingsPanel();edit("字号 pt","34");click("应用");panelFailure("IO");same(file,page);click("取消");}finally{need(directory.setWritable(true,true),"settings directory write permission restored");}});
                check("bounded_and_legacy_epub_keep_projection_and_part",()->{for(String role:new String[]{"epub","legacy"}){open(role);JSONObject before=frame();long point=before.getLong("start");String state=snapshot();settingsPanel();edit("字号 pt","36");edit("行距倍数","2");edit("段距 pt","20");edit("页边距 pt","44");apply();JSONObject after=frame();need(after.getInt("part")==before.getInt("part")&&String.valueOf(after.opt("path")).equals(String.valueOf(before.opt("path")))&&after.getLong("start")<=point&&after.getLong("end")>point,"same real EPUB projection/spine/path and FOUND point");need(after.getDouble("glyph_font_first")>0&&after.getDouble("margin")==44,"real EPUB font geometry");if(role.equals("legacy"))need(after.getLong("preferences_range_end")>after.getLong("preferences_point"),"ambiguous legacy point replaced only by independently FOUND real visible range");need(snapshot().equals(state),"EPUB preference change is read-only to existing SDK/product stores");capture(role+"-settings");}});
                check("fixed_pdf_and_cbz_zoom_real_pixels_same_page",()->{for(String role:new String[]{"pdf","cbz"}){open(role);JSONObject before=frame();String state=snapshot();settingsPanel();edit("固定页缩放 %",before.getDouble("zoom")==1.25?"150":"125");apply();JSONObject after=frame();need(after.getInt("index")==before.getInt("index")&&after.getInt("bitmap_width")>before.getInt("bitmap_width"),"fixed same live page rendered at new native scale");need(snapshot().equals(state),"zoom writes only local F3 settings");capture(role+"-zoom");}});
                check("rtl_and_vertical_taps_follow_saved_preferences",()->{open("txt");paging(true);settingsPanel();choose("翻页方向","从右向左");apply();long token=frame().getLong("accepted_token");gesture(.12f,.5f,.12f,.5f);changed(token);settingsPanel();choose("翻页方向","上下翻页");apply();token=frame().getLong("accepted_token");gesture(.5f,.85f,.5f,.85f);changed(token);});
                check("swipe_only_ignores_taps_and_turns_on_vertical_swipe",()->{settingsPanel();choose("翻页操作","滑动");apply();String page=stableFrame();gesture(.5f,.85f,.5f,.85f);need(stableFrame().equals(page),"tap ignored in swipe-only mode");long token=frame().getLong("accepted_token");gesture(.5f,.8f,.5f,.25f);changed(token);});
                check("hardware_input_ignores_touch_and_uses_actual_key_event",()->{settingsPanel();choose("翻页操作","方向键");apply();String page=stableFrame();gesture(.5f,.8f,.5f,.25f);need(stableFrame().equals(page),"touch does not turn in key-only mode");long token=frame().getLong("accepted_token");sendKeyDownUpSync(android.view.KeyEvent.KEYCODE_DPAD_DOWN);changed(token);});
                check("dark_page_gap_is_recorded_and_not_saved_as_success",()->{settingsPanel();choose("翻页操作","点击");choose("翻页方向","从左向右");apply();colorFailure=owner(store->themeGap());byte[] file=saved();String page=stableFrame();settingsPanel();choose("主题","深色（暂不可用）");click("应用");panelFailure("暂不可用");same(file,page);capture("dark-refused");click("取消");});
                check("system_resolver_and_saved_light_system_preference",()->{owner(store->{ReadingPreferences p=NativePreferences.defaults(),system=p.with(p.font,p.line,p.paragraph,p.margin,3,p.direction,p.input,p.zoom);need(NativePreferences.effectiveTheme(system,1)==1&&NativePreferences.effectiveTheme(system,2)==2&&NativePreferences.effectiveTheme(system,3)==1,"installed pure resolver and invalid-system fallback");return true;});settingsPanel();choose("主题","跟随系统");apply();need(new JSONObject(new String(saved(),StandardCharsets.UTF_8)).getString("theme").equals("system"),"explicit system preference saved by F3");});
                check("unknown_version_truncation_and_oversize_load_preserve_bytes",this::nativeReopenChecks);
                check("actual_rotation_cancels_unpublished_settings",()->{byte[] file=saved();Files.deleteIfExists(new File(context.getFilesDir(),"reading-preferences-gate-arrived").toPath());Files.write(new File(context.getFilesDir(),"reading-preferences-gate-arm").toPath(),new byte[]{1});settingsPanel();edit("字号 pt","38");click("应用");long end=SystemClock.elapsedRealtime()+60000;while(!new File(context.getFilesDir(),"reading-preferences-gate-arrived").isFile()&&SystemClock.elapsedRealtime()<end)SystemClock.sleep(40);need(new File(context.getFilesDir(),"reading-preferences-gate-arrived").isFile(),"actual settings candidate gate");long old=frame().getLong("view");getUiAutomation().setRotation(android.app.UiAutomation.ROTATION_FREEZE_90);long deadline=SystemClock.elapsedRealtime()+120000;while(SystemClock.elapsedRealtime()<deadline){try{if(frame().getLong("view")!=old)break;}catch(AssertionError absent){}SystemClock.sleep(60);}need(frame().getLong("view")!=old&&Arrays.equals(file,saved()),"rotation cancelled candidate and restored persisted settings");getUiAutomation().setRotation(android.app.UiAutomation.ROTATION_FREEZE_0);idle();});
                open("txt");idle();Files.write(new File(context.getFilesDir(),"preferences-reopen.json").toPath(),new JSONObject().put("file",android.util.Base64.encodeToString(saved(),android.util.Base64.NO_WRAP)).put("book",book("txt")).put("point",frame().getLong("start")).put("font",frame().getDouble("font")).put("line",frame().getDouble("line_spacing")).put("paragraph",frame().getDouble("paragraph_spacing")).put("margin",frame().getDouble("margin")).toString().getBytes(StandardCharsets.UTF_8));
            }else{
                books=new JSONObject(new String(Files.readAllBytes(new File(context.getFilesDir(),"preferences-books.json").toPath()),StandardCharsets.UTF_8));JSONObject baseline=new JSONObject(new String(Files.readAllBytes(new File(context.getFilesDir(),"preferences-reopen.json").toPath()),StandardCharsets.UTF_8));launch();waitFrame(baseline.getLong("book"));idle();
                check(phase.equals("reopen")?"fresh_process_loads_saved_f3_and_actual_layout":"actual_system_dark_resolves_but_does_not_fake_page_palette",()->{need(Arrays.equals(saved(),android.util.Base64.decode(baseline.getString("file"),android.util.Base64.NO_WRAP)),"fresh process never rewrites saved preferences");JSONObject page=frame();long point=baseline.getLong("point");need(page.getDouble("font")==baseline.getDouble("font")&&page.getDouble("line_spacing")==baseline.getDouble("line")&&page.getDouble("paragraph_spacing")==baseline.getDouble("paragraph")&&page.getDouble("margin")==baseline.getDouble("margin")&&page.getLong("start")<=point&&page.getLong("end")>point,"saved settings applied through SDK and point retained on process reopen");if(phase.equals("night")){until(node->id(node,"reader_status")&&text(node).contains("配色暂不支持"),null,"truthful system-dark refusal",30000);colorFailure=owner(store->themeGap());}capture(phase+"-settings");});
            }
        }catch(Throwable error){failure=error;try{capture("failure");}catch(Throwable captureError){error.addSuppressed(captureError);}}
        try{
            JSONObject report=new JSONObject().put("source_sha",arguments.getString("source_sha")).put("run_id",arguments.getString("run_id")).put("attempt",arguments.getString("attempt")).put("phase",phase).put("pid",android.os.Process.myPid()).put("passed",failure==null).put("checks",checks).put("count",checks.length()).put("observations",observations).put("page_colors_accepted",false);
            if(colorFailure!=null)report.put("retained_color_failure",colorFailure);
            if(failure!=null)report.put("failed_check",active).put("failure",failure.getMessage()).put("failure_trace",android.util.Log.getStackTraceString(failure));
            Files.write(new File(context.getFilesDir(),"preferences-ui-"+phase+".json").toPath(),report.toString(2).getBytes(StandardCharsets.UTF_8));result.putString("stream",failure==null?"PREFERENCES_UI_PASS "+phase:"PREFERENCES_UI_FAIL "+phase);finish(failure==null?Activity.RESULT_OK:Activity.RESULT_CANCELED,result);
        }catch(Exception error){result.putString("shortMsg","Preferences evidence unavailable");finish(Activity.RESULT_CANCELED,result);}
    }
}
