// SPDX-License-Identifier: MIT
package org.exreader.host.uitest;

import static org.junit.Assert.*;
import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Rect;
import android.os.Bundle;
import android.os.ParcelFileDescriptor;
import android.os.SystemClock;
import android.util.Log;
import android.view.accessibility.AccessibilityNodeInfo;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.uiautomator.By;
import androidx.test.uiautomator.StaleObjectException;
import androidx.test.uiautomator.UiDevice;
import androidx.test.uiautomator.UiObject2;
import androidx.test.uiautomator.Until;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Public input and labels only. Native generation/draw completion is audited separately. */
@RunWith(AndroidJUnit4.class)
public final class ReaderF08UiTest {
    private static final String APP="org.exreader.host", FILE="Sample.epub", TITLE="Sample.epub";
    private static final String FIXTURE_PATH="/sdcard/Download/Sample.epub", QUERY="Chapter three";
    private static final long CAP_NS=180_000_000_000L, CLEANUP_NS=10_000_000_000L;
    private static final String[] PLAN={"open","page_forward","page_backward","font_increase","font_decrease",
            "search_found_select","body_applicability","return_shelf"};
    private static final String[] SCALES={"window_animation_scale","transition_animation_scale","animator_duration_scale"};
    private UiDevice device;
    private Bundle args;
    private File output;
    private long deadline,actionDeadline;
    private int initialPid=-1;
    private JSONArray activeInputs;
    private boolean preflight,importCompleted;
    private final JSONArray cases=new JSONArray();
    private final JSONObject fixture=new JSONObject(),animation=new JSONObject(),animationRaw=new JSONObject();
    private interface Action { void run(JSONObject detail)throws Exception; }
    private interface Condition { boolean ready()throws Exception; }
    private interface Input { void run()throws Exception; }

    @Test public void reader()throws Exception {
        device=UiDevice.getInstance(InstrumentationRegistry.getInstrumentation());
        args=InstrumentationRegistry.getArguments();
        Context context=InstrumentationRegistry.getInstrumentation().getTargetContext();
        output=new File(context.getExternalFilesDir(null),"reader-evidence");
        assertFalse("earlier reader evidence must not be reused",output.exists());
        assertTrue(new File(output,"cases").mkdirs());assertTrue(new File(output,"shots").mkdirs());
        long started=SystemClock.elapsedRealtimeNanos();deadline=started+CAP_NS;
        JSONObject validation=new JSONObject().put("identity",identity()).put("schema","reader-f08-public-ui-v1")
                .put("started_elapsed_ns",started).put("cohort_cap_ms",CAP_NS/1_000_000)
                .put("plan",plan()).put("attempts_per_action",1).put("warmups_excluded",0)
                .put("first_and_outliers_retained",true).put("public_state_is_draw_completion",false)
                .put("fixture",fixture).put("animation",animation).put("animation_raw",animationRaw).put("cases",cases)
                .put("image_contract",new JSONObject().put("region","public visible reader_view bounds")
                        .put("pixel_algorithm","argb8888-be-v1").put("same_bounds_required_for_equality",true)
                        .put("changed",new JSONArray().put("page_forward").put("page_backward").put("font_increase").put("font_decrease"))
                        .put("restored",new JSONArray().put(new JSONArray().put("page_forward.before").put("page_backward.after"))
                                .put(new JSONArray().put("font_increase.before").put("font_decrease.after"))))
                .put("input_clock_scope","elapsedRealtimeNanos and nanoTime enclosing each public input API call");
        write(new File(output,"validation.json"),validation);
        try {
            run("open",65_000,detail->{
                validateInputs();verifyAnimations();verifySeed(detail);verifyFixture();preflight=true;
                assertNotNull(waitId("import_button",10_000));
                pick();
                until(()->("Imported "+FILE).equals(text("status_text")),"actual new picker import",30_000);
                importCompleted=true;detail.put("import_status",text("status_text"));searchShelf(TITLE);
                UiObject2 row=device.wait(Until.findObject(By.pkg(APP).textStartsWith(TITLE+"\n")),remaining(10_000));
                assertNotNull("actual imported Sample row",row);detail.put("selected_public_row",row.getText());clickObject("tap imported Sample.epub shelf row",row);
                readerReady();assertEquals(TITLE,text("book_title"));
                detail.put("source_counts",sourceCounts()).put("fixture",fixture);
            });
            run("page_forward",15_000,detail->{
                requireReader();int before=pageNumber();assertTrue("positive public page number",before>0);detail.put("input","public ACTION_SCROLL_FORWARD");pageAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD);
                until(()->readerSettled()&&pageNumber()==before+1,"increased public page number",15_000);
                detail.put("expected_page_delta",1);
            });
            run("page_backward",15_000,detail->{
                requireReader();int before=pageNumber();assertTrue("positive public page number",before>0);detail.put("input","public ACTION_SCROLL_BACKWARD");pageAction(AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD);
                until(()->readerSettled()&&pageNumber()==before-1,"decreased public page number",15_000);
                detail.put("expected_page_delta",-1);
            });
            run("font_increase",15_000,detail->{
                requireReader();int before=fontSize();clickId("font_up");
                until(()->readerSettled()&&fontSize()==before+4,"increased public font label",15_000);
            });
            run("font_decrease",15_000,detail->{
                requireReader();int before=fontSize();clickId("font_down");
                until(()->readerSettled()&&fontSize()==before-4,"decreased public font label",15_000);
            });
            run("search_found_select",25_000,detail->{
                requireReader();clickId("reader_more");clickText("书内搜索");
                UiObject2 input=device.wait(Until.findObject(By.pkg(APP).desc("书内搜索词")),remaining(10_000));
                assertNotNull(input);perform("setText real in-book search",()->input.setText(QUERY));hideIme();clickText("搜索");
                until(()->{UiObject2 status=device.findObject(By.pkg(APP).desc("搜索状态"));return status!=null&&status.getText()!=null&&status.getText().matches("[1-9][0-9]* 个结果.*");},"real search results",15_000);
                UiObject2 list=device.findObject(By.pkg(APP).desc("搜索结果"));assertNotNull(list);
                List<UiObject2> rows=list.findObjects(By.res("android:id/text1"));UiObject2 selected=null;
                JSONArray labels=new JSONArray();
                for(UiObject2 row:rows){String label=row.getText();labels.put(label);if(selected==null&&label!=null&&label.contains(QUERY)&&row.isEnabled())selected=row;}
                assertNotNull("explicit matching search result",selected);
                detail.put("query",QUERY).put("result_labels",labels).put("selected_result",selected.getText())
                        .put("search_status_before_click",device.findObject(By.pkg(APP).desc("搜索状态")).getText())
                        .put("explicit_result_click",true).put("found_requires_native_replay",true);
                clickObject("tap real FOUND search result",selected);
                until(()->device.findObject(By.pkg(APP).desc("书内搜索词"))==null&&readerSettled()
                        &&"已跳转到搜索结果".equals(text("reader_status")),"public search selection response",15_000);
            });
            run("body_applicability",10_000,detail->{
                requireReader();JSONObject view=readerView();assertFalse("reader view unavailable",view.isNull("bounds"));
                assertEquals("unexpected real directional pan requires a different predeclared cohort",0,view.getJSONArray("directional_pan_action_ids").length());
                detail.put("reader_view",view).put("body_scroll_applicable",false)
                        .put("reason","paged_bitmap_without_directional_body_pan")
                        .put("native_pan_limit",JSONObject.NULL).put("requires_native_pan_limit_confirmation",true);
            });
            run("return_shelf",15_000,detail->{
                requireReader();clickId("back_button");assertNotNull(waitId("shelf_search",10_000));searchShelf("");
                until(()->"On this device".equals(text("shelf_summary")),"public shelf returned",10_000);
                detail.put("source_counts",sourceCounts()).put("no_clear_or_delete_performed",true);
            });
        } finally {
            activeInputs=null;
            JSONObject cleanup;
            try{cleanup=closeOwnedActivity();}
            catch(Throwable error){cleanup=new JSONObject().put("activity_left",false).put("error",Log.getStackTraceString(error))
                    .put("finished_elapsed_ns",SystemClock.elapsedRealtimeNanos()).put("actual_pid_after",pid());}
            int failures=0,passed=0,notApplicable=0;
            Set<String> observed=new HashSet<>();
            for(int i=0;i<cases.length();i++){
                JSONObject item=cases.getJSONObject(i);observed.add(item.getString("id"));
                switch(item.getString("status")){case "pass":passed++;break;case "n/a":notApplicable++;break;default:failures++;}
            }
            JSONArray missing=new JSONArray();for(String id:PLAN)if(!observed.contains(id))missing.put(id);
            validation.put("cleanup",cleanup).put("finished_elapsed_ns",SystemClock.elapsedRealtimeNanos())
                    .put("complete",cases.length()==PLAN.length&&missing.length()==0).put("f08_accepted",false)
                    .put("cohort_cap_exceeded",SystemClock.elapsedRealtimeNanos()>deadline)
                    .put("failed",failures).put("passed",passed).put("not_applicable",notApplicable).put("missing_case_ids",missing);
            write(new File(output,"validation.json"),validation);
        }
        assertTrue("complete fixed reader cohort",validation.getBoolean("complete"));
        assertFalse("reader cohort cap",validation.getBoolean("cohort_cap_exceeded"));
        assertEquals("reader cohort failures",0,validation.getInt("failed"));
    }

    private void run(String id,long maxMs,Action action)throws Exception {
        long started=SystemClock.elapsedRealtimeNanos();
        actionDeadline=Math.min(deadline-CLEANUP_NS,started+maxMs*1_000_000L);
        activeInputs=new JSONArray();JSONObject detail=new JSONObject().put("inputs",activeInputs);
        JSONObject item=identity().put("id",id).put("kind",id).put("iteration",0).put("pid",-1)
                .put("started_elapsed_ns",started).put("started_mono_ns",System.nanoTime()).put("detail",detail);
        JSONArray errors=new JSONArray();int beforePid=pid();item.put("pid",beforePid);
        JSONObject before=snapshot(id,true);detail.put("before",before);
        try {
            assertTrue("actual reader PID",beforePid>0);if(initialPid<0)initialPid=beforePid;assertEquals("same product process",initialPid,beforePid);
            requireSnapshot(before,!"open".equals(id));
            remaining(1);if(!"open".equals(id))assertTrue("open preflight did not complete",preflight);
            action.run(detail);
        } catch(Throwable error){errors.put(new JSONObject().put("stage","action").put("error",Log.getStackTraceString(error)));}
        JSONObject after=snapshot(id,false);detail.put("after",after);int afterPid=pid();item.put("pid_after",afterPid);
        try{requireSnapshot(after,!"return_shelf".equals(id));assertEquals("product PID during action",beforePid,afterPid);
            assertTrue("action cap including screenshot observer work",SystemClock.elapsedRealtimeNanos()<=actionDeadline);}
        catch(Throwable error){errors.put(new JSONObject().put("stage","after").put("error",Log.getStackTraceString(error)));}
        item.put("status",errors.length()==0?("body_applicability".equals(id)?"n/a":"pass"):"fail").put("errors",errors);
        if(errors.length()>0)item.put("error",errors.toString());
        item.put("screenshot_captured",after.getJSONObject("reader_image").optBoolean("screenshot_captured"))
                .put("finished_elapsed_ns",SystemClock.elapsedRealtimeNanos()).put("finished_mono_ns",System.nanoTime());
        cases.put(item);
        try{write(new File(output,"cases/"+id+".json"),item);}
        catch(Throwable error){item.put("status","fail").put("case_file_error",Log.getStackTraceString(error));}
        activeInputs=null;
    }
    private void requireSnapshot(JSONObject value,boolean readerRequired)throws Exception {
        assertFalse("public snapshot failed",value.has("snapshot_error"));
        JSONObject image=value.getJSONObject("reader_image");assertTrue("actual screenshot",image.optBoolean("screenshot_captured"));
        if(readerRequired){assertEquals("reader screenshot region","captured",image.getString("status"));
            assertTrue("reader image must be nonuniform",image.getJSONObject("pixel_summary").getBoolean("distinct_at_least_two"));}
    }
    private JSONObject identity()throws Exception {return new JSONObject().put("source_sha",args.getString("source_sha",""))
            .put("run_id",args.getString("run_id","")).put("attempt",args.getString("attempt",""));}
    private JSONArray plan()throws Exception {JSONArray result=new JSONArray();for(String id:PLAN)result.put(new JSONObject().put("id",id).put("kind",id).put("iteration",0));return result;}
    private void validateInputs(){
        assertTrue(args.getString("source_sha","").matches("[0-9a-f]{40}"));assertFalse(args.getString("run_id","").isEmpty());
        assertTrue(args.getString("attempt","").matches("[1-9][0-9]*"));
        assertEquals(FILE,args.getString("exr_fixture_name"));assertEquals(FIXTURE_PATH,args.getString("exr_fixture_path"));assertEquals(QUERY,args.getString("exr_query"));
    }
    private void verifyAnimations()throws Exception {for(String key:SCALES){String raw=device.executeShellCommand("settings get global "+key).trim();animationRaw.put(key,raw);double value=Double.parseDouble(raw);animation.put(key,value);assertEquals("fixed animation scale "+key,1.0,value,0.0);}}
    private void verifySeed(JSONObject detail)throws Exception {
        JSONObject seed=new JSONObject(device.executeShellCommand("cat /sdcard/Android/data/"+APP+"/files/shelf-tests/seed.json"));
        JSONObject ident=identity();for(String key:new String[]{"source_sha","run_id","attempt"})assertEquals(ident.getString(key),seed.getString(key));
        assertEquals(2202,seed.getInt("books"));assertTrue(seed.getBoolean("production_mapping_complete"));
        Set<String> keys=new HashSet<>();JSONArray sources=seed.getJSONArray("source_keys");for(int i=0;i<sources.length();i++)assertTrue(keys.add(sources.getString(i)));assertEquals(2202,keys.size());
        detail.put("seed",seed);fixture.put("distinct_from_seed",!keys.contains("epub:"+args.getString("exr_fixture_sha256","")));
        assertTrue("supplemental EPUB must be independent of original corpus",fixture.getBoolean("distinct_from_seed"));
    }
    private void verifyFixture()throws Exception {
        String expected=args.getString("exr_fixture_sha256","");long expectedBytes=Long.parseLong(args.getString("exr_fixture_bytes","0"));
        assertTrue(expected.matches("[0-9a-f]{64}"));assertTrue(expectedBytes>0&&expectedBytes<=32*1024*1024);
        MessageDigest digest=MessageDigest.getInstance("SHA-256");long count=0;
        ParcelFileDescriptor descriptor=InstrumentationRegistry.getInstrumentation().getUiAutomation().executeShellCommand("cat "+FIXTURE_PATH);
        assertNotNull(descriptor);try(InputStream in=new ParcelFileDescriptor.AutoCloseInputStream(descriptor)){
            byte[] bytes=new byte[8192];int n;while((n=in.read(bytes))!=-1){remaining(1);count+=n;assertTrue("fixture byte limit",count<=32*1024*1024);digest.update(bytes,0,n);}
        }
        StringBuilder hex=new StringBuilder();for(byte b:digest.digest())hex.append(String.format(java.util.Locale.ROOT,"%02x",b&255));
        fixture.put("name",FILE).put("public_title",TITLE).put("path",FIXTURE_PATH).put("query",QUERY)
                .put("sha256",hex.toString()).put("bytes",count).put("expected_sha256",expected).put("expected_bytes",expectedBytes);
        assertEquals(expected,hex.toString());assertEquals(expectedBytes,count);
    }
    private JSONObject sourceCounts()throws Exception {return new JSONObject().put("seed_observed",2202).put("supplemental_expected",2203)
            .put("supplemental_observed",JSONObject.NULL).put("distinct_import_confirmed",importCompleted)
            .put("derived_after_one_distinct_import",importCompleted?2203:JSONObject.NULL).put("independent_complete_directory_audit",false);}
    private void pick()throws Exception {
        clickId("import_button");until(()->{String name=device.getCurrentPackageName();return name!=null&&name.endsWith(".documentsui");},"real system document picker",10_000);
        long end=Math.min(actionDeadline,SystemClock.elapsedRealtimeNanos()+25_000_000_000L);
        while(SystemClock.elapsedRealtimeNanos()<end){
            UiObject2 file=device.findObject(By.text(FILE));if(file!=null&&file.isEnabled()){clickObject("tap DocumentsUI Sample.epub",file);until(()->APP.equals(device.getCurrentPackageName()),"system picker returns to product",10_000);return;}
            UiObject2 downloads=device.findObject(By.text("Download"));if(downloads==null)downloads=device.findObject(By.text("Downloads"));
            if(downloads!=null&&downloads.isEnabled())clickObject("tap DocumentsUI Download",downloads);else {UiObject2 roots=device.findObject(By.descContains("Show roots"));if(roots!=null)clickObject("tap DocumentsUI roots",roots);}
            SystemClock.sleep(100);
        }
        throw new AssertionError("system picker did not expose "+FILE);
    }
    private void searchShelf(String query)throws Exception {UiObject2 field=waitId("shelf_search",10_000);assertNotNull(field);perform("setText public shelf search: "+query,()->field.setText(query));hideIme();}
    private void hideIme()throws Exception {if(device.executeShellCommand("dumpsys input_method").contains("mInputShown=true"))perform("Back to dismiss actual IME",()->{assertTrue(device.pressBack());});}
    private void requireReader()throws Exception {readerReady();assertEquals(TITLE,text("book_title"));}
    private void readerReady()throws Exception {until(this::readerSettled,"enabled public reader controls",20_000);}
    private boolean readerSettled(){return device.findObject(By.res(APP+":id/reader_view"))!=null
            &&device.findObject(By.res(APP+":id/loading_overlay"))==null&&enabled("font_up")&&enabled("font_down")
            &&text("page_label").startsWith("p.")&&!text("font_label").isEmpty();}
    private int pageNumber(){Matcher value=Pattern.compile("p\\.([0-9]+)(?: .*)?").matcher(text("page_label"));return value.matches()?Integer.parseInt(value.group(1)):-1;}
    private int fontSize(){Matcher value=Pattern.compile("Size ([0-9]+)").matcher(text("font_label"));assertTrue("public font label",value.matches());return Integer.parseInt(value.group(1));}
    private UiObject2 waitId(String id,long timeout)throws Exception {return device.wait(Until.findObject(By.res(APP+":id/"+id)),remaining(timeout));}
    private void clickId(String id)throws Exception {UiObject2 value=waitId(id,10_000);assertNotNull("public control "+id,value);assertTrue(value.isEnabled());clickObject("tap public control "+id,value);}
    private void clickText(String text)throws Exception {UiObject2 value=device.wait(Until.findObject(By.pkg(APP).text(text)),remaining(10_000));assertNotNull(text,value);assertTrue(value.isEnabled());clickObject("tap public text "+text,value);}
    private String text(String id){try{UiObject2 value=device.findObject(By.res(APP+":id/"+id));return value==null||value.getText()==null?"":value.getText();}catch(StaleObjectException stale){return "";}}
    private boolean enabled(String id){try{UiObject2 value=device.findObject(By.res(APP+":id/"+id));return value!=null&&value.isEnabled();}catch(StaleObjectException stale){return false;}}
    private void until(Condition condition,String message,long timeout)throws Exception {
        long end=Math.min(actionDeadline,SystemClock.elapsedRealtimeNanos()+timeout*1_000_000L);
        while(SystemClock.elapsedRealtimeNanos()<end){try{if(condition.ready())return;}catch(StaleObjectException stale){}SystemClock.sleep(50);}
        throw new AssertionError(message+"; public state="+publicState());
    }
    private long remaining(long limit){long ms=(actionDeadline-SystemClock.elapsedRealtimeNanos())/1_000_000;assertTrue("reader cohort/action timeout",ms>0);return Math.min(ms,limit);}
    private int pid(){try{String value=device.executeShellCommand("pidof "+APP).trim();return value.matches("[1-9][0-9]*")?Integer.parseInt(value):-1;}catch(Exception error){return -1;}}
    private JSONObject publicState()throws Exception {return new JSONObject().put("page_label",text("page_label")).put("font_label",text("font_label"))
            .put("book_title",text("book_title")).put("reader_status",text("reader_status")).put("shelf_status",text("shelf_summary"))
            .put("public_observed_elapsed_ns",SystemClock.elapsedRealtimeNanos()).put("public_observed_mono_ns",System.nanoTime()).put("reader_view",readerView());}
    private JSONObject readerView()throws Exception {
        JSONObject value=new JSONObject().put("bounds",JSONObject.NULL).put("directional_pan_action_ids",new JSONArray());
        AccessibilityNodeInfo root=InstrumentationRegistry.getInstrumentation().getUiAutomation().getRootInActiveWindow();if(root==null)return value;
        List<AccessibilityNodeInfo> nodes=root.findAccessibilityNodeInfosByViewId(APP+":id/reader_view");
        try{if(!nodes.isEmpty()){AccessibilityNodeInfo node=nodes.get(0);Rect box=new Rect();node.getBoundsInScreen(box);JSONArray actions=new JSONArray();
            for(AccessibilityNodeInfo.AccessibilityAction action:node.getActionList())if(action.getId()==AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_UP.getId()
                    ||action.getId()==AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_DOWN.getId()||action.getId()==AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_LEFT.getId()
                    ||action.getId()==AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_RIGHT.getId())actions.put(action.getId());
            value.put("bounds",new JSONObject().put("left",box.left).put("top",box.top).put("right",box.right).put("bottom",box.bottom).put("width",box.width()).put("height",box.height()))
                    .put("visible",node.isVisibleToUser()).put("enabled",node.isEnabled())
                    .put("description",String.valueOf(node.getContentDescription())).put("class_name",String.valueOf(node.getClassName())).put("directional_pan_action_ids",actions);
        }}finally{for(AccessibilityNodeInfo node:nodes)node.recycle();root.recycle();}return value;
    }
    private void pageAction(int action)throws Exception {
        AccessibilityNodeInfo root=InstrumentationRegistry.getInstrumentation().getUiAutomation().getRootInActiveWindow();assertNotNull(root);
        List<AccessibilityNodeInfo> nodes=root.findAccessibilityNodeInfosByViewId(APP+":id/reader_view");
        try{assertEquals("one public reader view",1,nodes.size());AccessibilityNodeInfo node=nodes.get(0);assertTrue(node.isVisibleToUser()&&node.isEnabled());perform("public reader accessibility action "+action,()->{assertTrue("public page action accepted",node.performAction(action));});}
        finally{for(AccessibilityNodeInfo node:nodes)node.recycle();root.recycle();}
    }
    private void clickObject(String label,UiObject2 value)throws Exception {perform(label,value::click);}
    private void perform(String label,Input input)throws Exception {
        JSONObject event=new JSONObject().put("action",label).put("timing_scope","public input API call")
                .put("started_elapsed_ns",SystemClock.elapsedRealtimeNanos()).put("started_mono_ns",System.nanoTime()).put("dispatched",false);
        if(activeInputs!=null)activeInputs.put(event);
        try{remaining(1);event.put("dispatched",true);input.run();event.put("returned",true);}
        catch(Throwable error){event.put("returned",false).put("error",Log.getStackTraceString(error));throw error;}
        finally{event.put("finished_elapsed_ns",SystemClock.elapsedRealtimeNanos()).put("finished_mono_ns",System.nanoTime());}
    }
    private JSONObject snapshot(String id,boolean before)throws Exception {
        JSONObject state;
        try{state=publicState();}
        catch(Throwable error){state=new JSONObject().put("page_label","").put("font_label","").put("book_title","")
                .put("reader_view",new JSONObject().put("bounds",JSONObject.NULL)).put("snapshot_error",Log.getStackTraceString(error));}
        String suffix=before?"-before":"";
        JSONObject image=new JSONObject().put("status","missing").put("screenshot_captured",false)
                .put("screenshot_path","shots/"+id+suffix+".png").put("crop_path","shots/"+id+suffix+"-reader.png");
        state.put("reader_image",image);
        Bitmap full=null,crop=null;
        try{
            if(SystemClock.elapsedRealtimeNanos()<actionDeadline){
                try{device.waitForIdle(Math.max(1,Math.min(1000,(actionDeadline-SystemClock.elapsedRealtimeNanos())/1_000_000)));}
                catch(Throwable error){image.put("idle_wait_error",Log.getStackTraceString(error));}
            }
            File shot=new File(output,image.getString("screenshot_path"));
            image.put("capture_started_elapsed_ns",SystemClock.elapsedRealtimeNanos()).put("capture_started_mono_ns",System.nanoTime());
            boolean captured;
            try{captured=device.takeScreenshot(shot);}
            finally{image.put("capture_finished_elapsed_ns",SystemClock.elapsedRealtimeNanos()).put("capture_finished_mono_ns",System.nanoTime());}
            image.put("screenshot_captured",captured);assertTrue("UiDevice.takeScreenshot",captured);
            image.put("screenshot_sha256",fileSha(shot)).put("screenshot_bytes",shot.length());
            BitmapFactory.Options options=new BitmapFactory.Options();options.inPreferredConfig=Bitmap.Config.ARGB_8888;options.inScaled=false;
            full=BitmapFactory.decodeFile(shot.getAbsolutePath(),options);assertNotNull("PNG screenshot decode",full);
            image.put("screenshot_width",full.getWidth()).put("screenshot_height",full.getHeight());
            JSONObject view=state.getJSONObject("reader_view"),afterView=readerView();
            image.put("bounds_after_capture",afterView.opt("bounds"));
            if(view.isNull("bounds")||!view.optBoolean("visible")){
                image.put("reason","public reader_view not visible");return state;
            }
            JSONObject bounds=view.getJSONObject("bounds");image.put("bounds",bounds);
            if(afterView.isNull("bounds")||!afterView.optBoolean("visible")||!sameBounds(bounds,afterView.getJSONObject("bounds"))){
                image.put("reason","public reader bounds changed during screenshot");return state;
            }
            int left=bounds.getInt("left"),top=bounds.getInt("top"),right=bounds.getInt("right"),bottom=bounds.getInt("bottom");
            assertTrue("reader bounds within actual screenshot",left>=0&&top>=0&&right<=full.getWidth()&&bottom<=full.getHeight()&&right>left&&bottom>top);
            crop=Bitmap.createBitmap(full,left,top,right-left,bottom-top);
            File cropFile=new File(output,image.getString("crop_path"));
            try(FileOutputStream out=new FileOutputStream(cropFile)){assertTrue("reader crop PNG",crop.compress(Bitmap.CompressFormat.PNG,100,out));}
            image.put("crop_sha256",fileSha(cropFile)).put("crop_bytes",cropFile.length()).put("width",crop.getWidth()).put("height",crop.getHeight())
                    .put("pixel_summary",pixels(crop)).put("status","captured");
        }catch(Throwable error){image.put("status","missing").put("error",Log.getStackTraceString(error));}
        finally{
            if(crop!=null&&crop!=full)crop.recycle();if(full!=null)full.recycle();
            image.put("processing_finished_elapsed_ns",SystemClock.elapsedRealtimeNanos());
            try{state.put("public_after_capture",publicState());}catch(Throwable error){state.put("snapshot_error",Log.getStackTraceString(error));}
        }
        return state;
    }
    private static boolean sameBounds(JSONObject a,JSONObject b)throws Exception {
        for(String key:new String[]{"left","top","right","bottom"})if(a.getInt(key)!=b.getInt(key))return false;return true;
    }
    private static JSONObject pixels(Bitmap bitmap)throws Exception {
        MessageDigest digest=MessageDigest.getInstance("SHA-256");int width=bitmap.getWidth(),height=bitmap.getHeight();
        int[] row=new int[width];byte[] encoded=new byte[width*4];long first=-1,min=0xffffffffL,max=0;boolean different=false;
        for(int y=0;y<height;y++){
            bitmap.getPixels(row,0,width,0,y,width,1);
            for(int x=0;x<width;x++){
                int pixel=row[x];long unsigned=pixel&0xffffffffL;if(first<0)first=unsigned;else if(first!=unsigned)different=true;
                min=Math.min(min,unsigned);max=Math.max(max,unsigned);
                int at=x*4;encoded[at]=(byte)(pixel>>>24);encoded[at+1]=(byte)(pixel>>>16);encoded[at+2]=(byte)(pixel>>>8);encoded[at+3]=(byte)pixel;
            }
            digest.update(encoded);
        }
        return new JSONObject().put("algorithm","argb8888-be-v1").put("sha256",hex(digest.digest()))
                .put("distinct_at_least_two",different).put("min_argb",min).put("max_argb",max).put("pixels",(long)width*height);
    }
    private static String fileSha(File file)throws Exception {
        MessageDigest digest=MessageDigest.getInstance("SHA-256");
        try(InputStream in=new FileInputStream(file)){byte[] buffer=new byte[8192];int n;while((n=in.read(buffer))!=-1)digest.update(buffer,0,n);}
        return hex(digest.digest());
    }
    private static String hex(byte[] bytes){StringBuilder out=new StringBuilder();for(byte value:bytes)out.append(String.format(java.util.Locale.ROOT,"%02x",value&255));return out.toString();}
    private JSONObject closeOwnedActivity()throws Exception {
        JSONArray events=new JSONArray();JSONObject value=new JSONObject().put("events",events);
        long end=Math.min(deadline,SystemClock.elapsedRealtimeNanos()+CLEANUP_NS);int productBacks=0;String after=null;
        value.put("started_elapsed_ns",SystemClock.elapsedRealtimeNanos());
        try{
            value.put("package_at_start",device.getCurrentPackageName());
            for(int i=0;i<4&&SystemClock.elapsedRealtimeNanos()<end;i++){
                String before=device.getCurrentPackageName();if(!APP.equals(before)&&(before==null||!before.endsWith(".documentsui")))break;
                JSONObject event=new JSONObject().put("package_before",before).put("started_elapsed_ns",SystemClock.elapsedRealtimeNanos());events.put(event);
                try{assertTrue("Back input accepted",device.pressBack());if(APP.equals(before))productBacks++;
                    device.waitForIdle(Math.max(1,Math.min(1000,(end-SystemClock.elapsedRealtimeNanos())/1_000_000)));}
                catch(Throwable error){event.put("error",Log.getStackTraceString(error));}
                finally{event.put("finished_elapsed_ns",SystemClock.elapsedRealtimeNanos()).put("package_after",device.getCurrentPackageName());}
            }
            after=device.getCurrentPackageName();
        }catch(Throwable error){value.put("error",Log.getStackTraceString(error));}
        return value.put("product_back_inputs",productBacks).put("package_at_end",after==null?JSONObject.NULL:after)
                .put("activity_left",productBacks>0&&after!=null&&!APP.equals(after)&&!after.endsWith(".documentsui"))
                .put("finished_elapsed_ns",SystemClock.elapsedRealtimeNanos()).put("actual_pid_after",pid())
                .put("native_stop_requires_independent_verification",true);
    }
    private static void write(File file,JSONObject value)throws Exception {try(FileOutputStream out=new FileOutputStream(file)){out.write((value.toString(2)+"\n").getBytes(StandardCharsets.UTF_8));}}
}
