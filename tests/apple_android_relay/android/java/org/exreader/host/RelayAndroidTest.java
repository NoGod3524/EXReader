// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.app.Activity;
import android.app.Instrumentation;
import android.accessibilityservice.AccessibilityServiceInfo;
import android.content.Context;
import android.content.Intent;
import android.graphics.Rect;
import android.os.Bundle;
import android.os.SystemClock;
import android.view.accessibility.AccessibilityNodeInfo;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.function.Predicate;
import org.json.JSONArray;
import org.json.JSONObject;

/** Only actual app UI mutates originals, accounts and reading records. */
public final class RelayAndroidTest extends Instrumentation {
    private Bundle arguments; private Context context; private JSONObject input;
    private final JSONArray checks=new JSONArray(); private final JSONObject evidence=new JSONObject();
    private String active="initialization";
    interface Work { void run() throws Exception; }
    @Override public void onCreate(Bundle args){super.onCreate(args);arguments=args;start();}
    static void need(boolean value,String label){if(!value)throw new AssertionError(label);}
    private void check(String name,Work work)throws Exception{active=name;work.run();checks.put(new JSONObject().put("name",name).put("pass",true));}
    private static String text(AccessibilityNodeInfo node){return node.getText()==null?"":node.getText().toString();}
    private static boolean id(AccessibilityNodeInfo node,String name){String value=node.getViewIdResourceName();return value!=null&&value.endsWith("/"+name);}
    private static boolean desc(AccessibilityNodeInfo node,String name){return name.contentEquals(node.getContentDescription()==null?"":node.getContentDescription());}
    private AccessibilityNodeInfo find(AccessibilityNodeInfo node,Predicate<AccessibilityNodeInfo> test){
        if(node==null)return null;if(test.test(node))return node;
        for(int n=0;n<node.getChildCount();n++){AccessibilityNodeInfo child=node.getChild(n),found=find(child,test);if(found!=null){if(found!=child&&child!=null)child.recycle();return found;}if(child!=null)child.recycle();}return null;
    }
    private void until(Predicate<AccessibilityNodeInfo> test,java.util.function.Consumer<AccessibilityNodeInfo> action,String label,long timeout){
        long end=SystemClock.elapsedRealtime()+timeout;
        while(SystemClock.elapsedRealtime()<end){AccessibilityNodeInfo root=getUiAutomation().getRootInActiveWindow(),node=null;
            try{node=find(root,test);if(node!=null){if(action!=null)action.accept(node);return;}}
            finally{if(node!=null&&node!=root)node.recycle();if(root!=null)root.recycle();}SystemClock.sleep(100);}
        throw new AssertionError("UI timeout: "+label);
    }
    private void tap(AccessibilityNodeInfo node){Rect bounds=new Rect();node.getBoundsInScreen(bounds);need(bounds.width()>0&&bounds.height()>0,"visible UI control");if(node.performAction(AccessibilityNodeInfo.ACTION_CLICK))return;long now=SystemClock.uptimeMillis();sendPointerSync(android.view.MotionEvent.obtain(now,now,android.view.MotionEvent.ACTION_DOWN,bounds.centerX(),bounds.centerY(),0));sendPointerSync(android.view.MotionEvent.obtain(now,now+30,android.view.MotionEvent.ACTION_UP,bounds.centerX(),bounds.centerY(),0));}
    private void click(String name){until(n->n.isEnabled()&&text(n).equalsIgnoreCase(name),this::tap,name,30000);}
    private JSONObject tree(AccessibilityNodeInfo node)throws Exception{
        if(node==null)return new JSONObject();JSONArray children=new JSONArray();for(int i=0;i<node.getChildCount();i++){AccessibilityNodeInfo child=node.getChild(i);if(child!=null){try{children.put(tree(child));}finally{child.recycle();}}}
        return new JSONObject().put("id",node.getViewIdResourceName()).put("text",text(node)).put("description",String.valueOf(node.getContentDescription())).put("class",String.valueOf(node.getClassName())).put("enabled",node.isEnabled()).put("frame",node.getExtras().getString("exreader.frame","")).put("children",children);
    }
    private void field(String name,String value){until(n->desc(n,name),n->{Bundle b=new Bundle();b.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,value);need(n.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,b),"account UI field");},name,30000);}
    private void status(String value){until(n->desc(n,"同步状态")&&text(n).contains(value),null,value,120000);}
    private void panel(){click("More");click("同步");}
    private void records(){until(n->desc(n,"阅读更多操作")&&n.isEnabled(),this::tap,"reader More",30000);click("阅读记录");}
    private JSONObject frame()throws Exception{String[] raw={null};until(n->id(n,"reader_view")&&n.getExtras().containsKey("exreader.frame"),n->raw[0]=n.getExtras().getString("exreader.frame"),"rendered frame",30000);return new JSONObject(raw[0]);}
    private JSONObject settled()throws Exception{long end=SystemClock.elapsedRealtime()+30000;while(SystemClock.elapsedRealtime()<end){JSONObject f=frame();if(f.optLong("settled_token")>0&&f.optLong("settled_token")==f.optLong("accepted_token")&&f.optLong("settled_revision")==f.optLong("revision")&&f.optLong("bitmap_width")>0&&f.optLong("bitmap_height")>0&&(f.optLong("end")>f.optLong("start")||f.optLong("bounded_visual_boxes")>0))return f;SystemClock.sleep(100);}throw new AssertionError("native frame did not settle");}
    private void chapterBoundaries(File original)throws Exception {
        // Independent public-owner boundary fixture, never the application's
        // library.db. The actual relay still receives/reads/saves solely by UI.
        need(!FontSelection.active()&&NativeFonts.live()==0,"no app font lease before boundary fixture");
        File folder=new File(context.getFilesDir(),"relay-boundary");need(folder.mkdirs()||folder.isDirectory(),"isolated boundary folder");
        File fontFile=new File(folder,"Reader.otf");byte[] font;
        try(java.io.InputStream stream=context.getAssets().open("Reader.otf")){font=stream.readAllBytes();}Files.write(fontFile.toPath(),font);
        File empty=new File(folder,"all-empty.epub");
        try(java.util.zip.ZipOutputStream zip=new java.util.zip.ZipOutputStream(new java.io.FileOutputStream(empty))){
            String[][] entries={{"mimetype","application/epub+zip"},{"META-INF/container.xml","<?xml version=\"1.0\"?><container version=\"1.0\" xmlns=\"urn:oasis:names:tc:opendocument:xmlns:container\"><rootfiles><rootfile full-path=\"book.opf\" media-type=\"application/oebps-package+xml\"/></rootfiles></container>"},{"book.opf","<?xml version=\"1.0\"?><package version=\"3.0\" unique-identifier=\"id\" xmlns=\"http://www.idpf.org/2007/opf\"><metadata xmlns:dc=\"http://purl.org/dc/elements/1.1/\"><dc:identifier id=\"id\">relay-empty</dc:identifier><dc:title>Empty boundary</dc:title><dc:language>en</dc:language></metadata><manifest><item id=\"a\" href=\"a.xhtml\" media-type=\"application/xhtml+xml\"/><item id=\"b\" href=\"b.xhtml\" media-type=\"application/xhtml+xml\"/></manifest><spine><itemref idref=\"a\"/><itemref idref=\"b\"/></spine></package>"},{"a.xhtml","<html xmlns=\"http://www.w3.org/1999/xhtml\"><head><title>Empty</title></head><body></body></html>"},{"b.xhtml","<html xmlns=\"http://www.w3.org/1999/xhtml\"><head><title>Empty</title></head><body></body></html>"}};
            for(String[] entry:entries){
                String body=entry[1];if(entry[0].equals("book.opf"))body=body.replace("</metadata>","<meta property=\"dcterms:modified\">2026-10-27T00:00:00Z</meta></metadata>").replace("</manifest>","<item id=\"nav\" href=\"nav.xhtml\" media-type=\"application/xhtml+xml\" properties=\"nav\"/></manifest>");
                byte[] bytes=body.getBytes(StandardCharsets.UTF_8);java.util.zip.ZipEntry item=new java.util.zip.ZipEntry(entry[0]);item.setTime(315532800000L);
                if(entry[0].equals("mimetype")){java.util.zip.CRC32 crc=new java.util.zip.CRC32();crc.update(bytes);item.setMethod(java.util.zip.ZipEntry.STORED);item.setSize(bytes.length);item.setCompressedSize(bytes.length);item.setCrc(crc.getValue());}
                zip.putNextEntry(item);zip.write(bytes);zip.closeEntry();
            }
            zip.putNextEntry(new java.util.zip.ZipEntry("nav.xhtml"));zip.write(("<html xmlns=\"http://www.w3.org/1999/xhtml\" xmlns:epub=\"http://www.idpf.org/2007/ops\"><head><title>Contents</title></head><body><nav epub:type=\"toc\"><ol><li><a href=\"a.xhtml\">Empty A</a></li><li><a href=\"b.xhtml\">Empty B</a></li></ol></nav></body></html>").getBytes(StandardCharsets.UTF_8));zip.closeEntry();
        }
        long priorFontLibrary=FontSelection.library();String priorFontHash=FontSelection.hash();
        NativeFonts fonts=NativeFonts.open(new File(folder,"fonts").getPath());JSONObject bounds=new JSONObject();
        try(NativeLibrary library=new NativeLibrary(new File(folder,"library.db").getPath())){
            HostTask task=new HostTask(()->false);NativeFonts.Imported imported=fonts.importFile(fontFile.getPath(),"Boundary font",task);need(imported.ok(),"boundary local font imported by production module");FontSelection.attach(fonts.handle,imported.hash);
            long emptyBook=library.importFile(empty.getPath(),NativeLibrary.FORMAT_EPUB,"All empty").id;long began=SystemClock.elapsedRealtime();boolean rejected=false;
            try(BoundedEpub pager=new BoundedEpub(library,emptyBook,font,20)){try(PageLoad page=pager.restore(0,task)){throw new AssertionError("all-empty chapter unexpectedly rendered");}catch(IllegalArgumentException error){need(error.getMessage().equals("Empty reading chapter is not supported"),"retained precise empty error");rejected=true;}}
            need(rejected&&SystemClock.elapsedRealtime()-began<20000,"all-empty bounded failure without skipping or loop");need(NativeFonts.live()==0,"failed native candidate freed its actual font lease");bounds.put("all_empty_failed_ms",SystemClock.elapsedRealtime()-began).put("leases_after_empty_failure",NativeFonts.live());
            long imageBook=library.importFile(original.getPath(),NativeLibrary.FORMAT_EPUB,"Real Alice cover").id;
            try(BoundedEpub pager=new BoundedEpub(library,imageBook,font,20);PageLoad page=pager.restore(0,task)){
                int first=0;while(first<pager.parts.length&&!"1".equals(pager.parts[first][1]))first++;
                need(page.snapshot.start==0&&page.snapshot.end==0&&page.snapshot.part==first,"image-only original first reading-order part is retained");need(page.snapshot.boundedVisualBoxes>0&&page.snapshot.bitmap.getWidth()>0&&page.snapshot.bitmap.getHeight()>0,"decoded image actually rendered");need(NativeFonts.live()>0,"image pager holds actual selected font lease");bounds.put("image_part",page.snapshot.part).put("image_boxes",page.snapshot.boundedVisualBoxes).put("image_leases_live",NativeFonts.live());
            }
            need(NativeFonts.live()==0,"discarded real image candidate releases native lease");bounds.put("leases_after_image_discard",NativeFonts.live());
        } finally {FontSelection.attach(priorFontLibrary,priorFontHash);need(fonts.close()==NativeFonts.OK,"isolated font library closes without BUSY leases");}
        evidence.put("independent_boundary_tests",bounds.put("passed",true).put("app_database_seeded",false));
    }
    private JSONObject location()throws Exception{
        // Read-only evidence from the existing product owner; never seed or apply a record here.
        try(BookStore store=new BookStore(context,new File(context.getFilesDir(),"library.db"))){
            HostTask task=new HostTask(()->false);ReadingRecord record=NativeReadingProduct.list(store,input.getString("book_identity"),"",false,new ReadingControl(task,null,"relay-evidence",false)).progress;
            need(record.readable()&&record.capture.mode==ReadingCapture.EPUB,"safe application EPUB progress");ReadingCapture c=record.capture;
            return new JSONObject().put("part",c.unit).put("path",c.partPath).put("start",c.start).put("end",c.end).put("exact",c.text(0)).put("prefix",c.text(1)).put("suffix",c.text(2)).put("parser",c.parser).put("head",record.head).put("book_identity",c.bookKey);
        }
    }
    private void onTarget(JSONObject f,JSONObject loc)throws Exception{
        need(f.getString("source_key").equals(input.getString("book_identity")),"actual frame original identity");
        need(f.getLong("part")==loc.getLong("part")&&f.getString("path").equals(loc.getString("path")),"public parser part identity");
        need(f.getLong("start")<=loc.getLong("start")&&f.getLong("end")>loc.getLong("start"),"target lies in actual rendered page; no equal-page assumption across reflow");
    }
    @Override public void onStart(){context=getTargetContext();Throwable failure=null;Bundle result=new Bundle();
        try{
            AccessibilityServiceInfo service=getUiAutomation().getServiceInfo();service.flags|=AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS;getUiAutomation().setServiceInfo(service);
            File incoming=new File(context.getFilesDir(),"relay-input.json");input=new JSONObject(new String(Files.readAllBytes(incoming.toPath()),StandardCharsets.UTF_8));Files.delete(incoming.toPath());
            need(BuildConfig.READER_SYNC&&BuildConfig.READER_READING&&BuildConfig.READER_SELECTOR_BYTES_CANDIDATE,"real candidate product features");
            check("empty_library_real_account_and_sync",()->{
                context.startActivity(new Intent(context,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TOP));panel();click("云盘账号");
                field("云盘地址",input.getString("root"));field("云盘用户名",input.getString("user"));field("云盘密码",input.getString("password"));click("仅本次使用");status("仅本次使用凭据");click("立即同步");status("本轮同步结束");
            });
            check("explicit_application_receive_original",()->{until(n->n.isEnabled()&&text(n).contains(input.optString("remote_title")),this::tap,"remote book",30000);click("接收");status("书籍已接收");
                File original=new File(new File(context.getFilesDir(),"sync-cache"),input.getString("original_sha256")+".epub");need(original.length()==input.getLong("original_bytes"),"received exact byte length");need(BookStore.syncFileHash(original,new HostTask(()->false)).equals(input.getString("original_sha256")),"received SHA256 from Apple original");
                try(NativeLibrary library=new NativeLibrary(new File(context.getFilesDir(),"library.db").getPath())){
                    NativeLibrary.Book[] books=library.books();need(books.length==1,"exactly one app-received original");
                    java.security.MessageDigest digest=java.security.MessageDigest.getInstance("SHA-256");
                    try(NativeLibrary.Source source=library.source(books[0].id)){
                        need(source.size==input.getLong("original_bytes"),"public SDK original byte length");byte[] chunk=new byte[65536];
                        for(long offset=0;offset<source.size;){int count=source.read(offset,chunk,(int)Math.min(chunk.length,source.size-offset));need(count>0,"public SDK source bytes");digest.update(chunk,0,count);offset+=count;}
                    }
                    StringBuilder hash=new StringBuilder();for(byte value:digest.digest())hash.append(String.format(java.util.Locale.ROOT,"%02x",value&255));
                    need(hash.toString().equals(input.getString("original_sha256")),"public SDK original SHA256 matches Apple");evidence.put("public_source_sha256",hash.toString());
                }
                chapterBoundaries(original);
                click("关闭");until(n->n.isEnabled()&&id(n,"text1")&&text(n).startsWith(input.optString("remote_title")+"\n"),n->{try{evidence.put("selected_shelf_control",tree(n));}catch(Exception error){throw new IllegalStateException(error);}tap(n);},"local received shelf row",30000);JSONObject first=settled();need(first.getLong("part")==evidence.getJSONObject("independent_boundary_tests").getLong("image_part")&&first.getLong("start")==0&&first.getLong("end")==0&&first.getLong("bounded_visual_boxes")>0,"real received cover retained, not silently skipped");evidence.put("initial_frame",first);
            });
            check("apple_progress_public_parse_real_jump",()->{
                JSONObject incomingLocation=location(),expected=input.getJSONObject("location");for(String key:new String[]{"part","path","start","end","exact","prefix","suffix"})need(String.valueOf(incomingLocation.opt(key)).equals(String.valueOf(expected.opt(key))),"Apple wire location matches "+key);
                evidence.put("incoming_location",incomingLocation);records();until(n->desc(n,"已保存进度")&&n.isEnabled(),this::tap,"saved progress",30000);click("跳转到此处");
                until(n->id(n,"reader_status")&&text(n).contains("已跳转到阅读记录"),null,"public resolver jump",30000);JSONObject restored=settled();onTarget(restored,incomingLocation);evidence.put("restored_frame",restored);
            });
            check("real_forward_pages_and_application_save",()->{
                JSONObject before=settled();for(int i=0;i<3;i++){JSONObject old=settled();until(n->id(n,"reader_view"),n->need(n.performAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD),"native forward action"),"page forward",30000);
                    long end=SystemClock.elapsedRealtime()+30000;boolean moved=false;while(SystemClock.elapsedRealtime()<end){JSONObject now=settled();if(now.getLong("part")!=old.getLong("part")||now.getLong("start")!=old.getLong("start")){moved=true;break;}SystemClock.sleep(100);}need(moved,"real EPUB page advanced");}
                JSONObject after=settled();need(after.getLong("part")>before.getLong("part")||after.getLong("start")>before.getLong("start"),"later reading position");evidence.put("outgoing_frame",after);records();click("保存进度");until(n->desc(n,"阅读记录状态")&&text(n).contains("已保存"),null,"application progress saved",30000);
                JSONObject saved=location();onTarget(after,saved);need(!saved.getString("head").equals(evidence.getJSONObject("incoming_location").getString("head")),"new app revision");evidence.put("location",saved);click("关闭");
            });
            check("application_sync_outgoing_position",()->{click("Shelf");panel();click("立即同步");status("本轮同步结束");click("断开");});
        }catch(Throwable error){failure=error;AccessibilityNodeInfo root=getUiAutomation().getRootInActiveWindow();try{evidence.put("failure_ui",tree(root));}catch(Exception capture){error.addSuppressed(capture);}finally{if(root!=null)root.recycle();}}
        try{
            evidence.put("source_sha",arguments.getString("source_sha")).put("run_id",arguments.getString("run_id")).put("attempt",arguments.getString("attempt")).put("passed",failure==null).put("checks",checks).put("phase","android").put("api",android.os.Build.VERSION.SDK_INT).put("abi",android.os.Build.SUPPORTED_ABIS[0]).put("physical_device",false).put("picker_used",false).put("pid",android.os.Process.myPid());
            if(input!=null)for(String key:new String[]{"original_sha256","original_bytes","book_identity","remote_title"})evidence.put(key,input.get(key));
            if(failure!=null)evidence.put("failed_check",active).put("failure",failure.toString());
            Files.write(new File(context.getFilesDir(),"relay-android-report.json").toPath(),evidence.toString(2).getBytes(StandardCharsets.UTF_8));result.putString("stream",failure==null?"RELAY_ANDROID_PASS":"RELAY_ANDROID_FAIL "+active);finish(failure==null?Activity.RESULT_OK:Activity.RESULT_CANCELED,result);
        }catch(Throwable error){result.putString("shortMsg","relay evidence unavailable");finish(Activity.RESULT_CANCELED,result);}
    }
}
