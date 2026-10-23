// SPDX-License-Identifier: MIT
package org.exreader.host.uitest;

import static org.junit.Assert.*;
import android.content.Context;
import android.graphics.Rect;
import android.os.Bundle;
import android.os.SystemClock;
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
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/** Black-box production shelf walkthrough over 2202 real SDK imports; no synthetic adapter data. */
@RunWith(AndroidJUnit4.class)
public final class ShelfWalkthroughTest {
    private static final String APP="org.exreader.host";
    private UiDevice device;
    private Context context;
    private Bundle args;
    private File output;
    private final JSONArray cases=new JSONArray();
    private final JSONArray intervals=new JSONArray();
    private interface Body { void run(JSONObject detail)throws Exception; }

    @Before public void setup()throws Exception {
        device=UiDevice.getInstance(InstrumentationRegistry.getInstrumentation());
        context=InstrumentationRegistry.getInstrumentation().getTargetContext();
        args=InstrumentationRegistry.getArguments();
        output=new File(context.getExternalFilesDir(null),"shelf-evidence");
        assertFalse("earlier shelf evidence must not be reused",output.exists());
        assertTrue(new File(output,"shots").mkdirs()); device.setOrientationNatural();
    }

    @Test public void shelf()throws Exception {
        String seedText=device.executeShellCommand("cat /sdcard/Android/data/"+APP+"/files/shelf-tests/seed.json");
        JSONObject seed=new JSONObject(seedText);
        assertEquals(args.getString("exr_source_sha"),seed.getString("source_sha"));
        assertEquals(args.getString("exr_run_id"),seed.getString("run_id"));
        assertEquals(args.getString("exr_attempt"),seed.getString("attempt"));
        assertEquals(2202,seed.getInt("books")); assertTrue(seed.getBoolean("production_mapping_complete"));
        Set<String> expected=keys(seed.getJSONArray("source_keys")); assertEquals(2202,expected.size());
        run("first_interactive_real_catalog",detail->{
            launch(); JSONObject value=ready("");
            assertTrue(value.getLong("first_interactive_elapsed_ns")>value.getLong("activity_started_elapsed_ns"));
            assertTrue(value.getDouble("first_interactive_ms")>0); bounds(value);
            detail.put("observation",value).put("seeded_books",seed.getInt("books"));
        });
        run("forward_scroll_visits_all_real_sources",detail->{
            long start=SystemClock.elapsedRealtimeNanos();
            Set<String> loaded=new HashSet<>(),visible=new HashSet<>(); int gestures=0;
            JSONObject value=ready("");
            while(true) {
                bounds(value); loaded.addAll(keys(value.getJSONArray("keys"))); visible.addAll(keys(value.getJSONArray("visible_keys")));
                JSONArray page=value.getJSONArray("keys"), shown=value.getJSONArray("visible_keys");
                if(!value.getBoolean("has_after") && page.length()>0 && shown.length()>0
                        && page.getString(page.length()-1).equals(shown.getString(shown.length()-1)))break;
                assertTrue("forward scrolling must make bounded progress",++gestures<=600);
                scroll(false); value=ready("");
            }
            assertEquals(expected,loaded); assertEquals("actual visible rows cover every real source",expected,visible);
            detail.put("loaded_sources",loaded.size()).put("visible_sources",visible.size()).put("gestures",gestures).put("last",value);
            interval("forward_scroll",start,SystemClock.elapsedRealtimeNanos());
        });
        run("reverse_scroll_preserves_keyset_and_recycles_views",detail->{
            long start=SystemClock.elapsedRealtimeNanos(); Set<String> observed=new HashSet<>(); int gestures=0;
            UiObject2 scroller=device.wait(Until.findObject(By.res(APP+":id/book_list")),10000);assertNotNull(scroller);
            Rect box=scroller.getVisibleBounds();
            for(int turn=0;turn<3;turn++){
                device.swipe(box.centerX(),box.top+box.height()/4,box.centerX(),box.bottom-box.height()/4,12);
                device.swipe(box.centerX(),box.bottom-box.height()/4,box.centerX(),box.top+box.height()/4,12);
            }
            JSONObject value=ready("");
            while(true) {
                bounds(value); observed.addAll(keys(value.getJSONArray("keys")));
                if(!value.getBoolean("has_before") && value.getJSONArray("visible_keys").getString(0)
                        .equals(value.getJSONArray("keys").getString(0)))break;
                assertTrue("reverse scrolling must make bounded progress",++gestures<=600);
                scroll(true); value=ready("");
            }
            assertEquals(expected,observed); assertTrue("ListView actually reused row Views",value.getInt("recycled_views")>0);
            detail.put("sources",observed.size()).put("gestures",gestures).put("first",value);
            interval("reverse_scroll",start,SystemClock.elapsedRealtimeNanos());
        });
        run("same_title_has_130_stable_source_keys",detail->{
            search("Tie title"); Set<String> found=new HashSet<>(); JSONObject value=ready("Tie title");
            int gestures=0;
            while(true){found.addAll(keys(value.getJSONArray("keys")));bounds(value);if(!value.getBoolean("has_after"))break;
                assertTrue(++gestures<80);scroll(false);value=ready("Tie title");}
            assertEquals(130,found.size());detail.put("unique_sources",found.size()).put("last",value);
        });
        run("title_author_literal_and_empty_search",detail->{
            for(String query:new String[]{"BOOK 0200","Shelf Author","100%_","missing shelf title"}){
                search(query);JSONObject value=ready(query);assertEquals(query.startsWith("missing")?0:1,value.getInt("cached_rows"));
                bounds(value);detail.put(query,value);
            }
        });
        run("rapid_search_keeps_only_latest_query",detail->{
            search("Tie title"); search("Book 0300"); search("Book 0200");
            JSONObject value=ready("Book 0200");assertEquals(1,value.getInt("cached_rows"));
            SystemClock.sleep(700);JSONObject settled=ready("Book 0200");
            assertEquals(value.getJSONArray("keys").toString(),settled.getJSONArray("keys").toString());
            detail.put("latest",settled);
        });
        run("refresh_preserves_scrolled_source_anchor",detail->{
            search("");ready("");for(int at=0;at<12;at++)scroll(false);
            JSONObject before=ready("");click("refresh_button");JSONObject after=ready("");
            assertEquals(before.getString("top_key"),after.getString("top_key"));
            assertTrue(Math.abs(before.getInt("top_y")-after.getInt("top_y"))<=2);
            detail.put("before",before).put("after",after);
        });
        run("rotation_background_and_process_restore_anchor",detail->{
            JSONObject before=ready("");device.setOrientationLeft();JSONObject rotated=ready("");
            assertEquals(before.getString("top_key"),rotated.getString("top_key"));
            device.setOrientationNatural();JSONObject portrait=ready("");
            assertEquals(before.getString("top_key"),portrait.getString("top_key"));
            device.pressHome();SystemClock.sleep(400);launch();JSONObject resumed=ready("");
            assertEquals(portrait.getString("top_key"),resumed.getString("top_key"));
            String oldPid=device.executeShellCommand("pidof "+APP).trim();
            device.executeShellCommand("am force-stop "+APP);launch();JSONObject reopened=ready("");
            String newPid=device.executeShellCommand("pidof "+APP).trim();
            assertFalse(oldPid.isEmpty());assertFalse(newPid.isEmpty());assertNotEquals(oldPid,newPid);
            assertEquals(before.getString("top_key"),reopened.getString("top_key"));
            detail.put("before",before).put("rotated",rotated).put("reopened",reopened).put("old_pid",oldPid).put("new_pid",newPid);
        });
        run("offline_read_and_return_to_filtered_shelf",detail->{
            device.executeShellCommand("svc wifi disable");device.executeShellCommand("svc data disable");
            search("Book 0200");JSONObject before=ready("Book 0200");
            UiObject2 row=device.wait(Until.findObject(By.textStartsWith("Book 0200\n")),10000);assertNotNull(row);row.click();
            assertNotNull(device.wait(Until.findObject(By.res(APP+":id/reader_view")),30000));
            assertTrue(device.wait(Until.hasObject(By.res(APP+":id/page_label").textContains("1")),30000));
            click("back_button");JSONObject after=ready("Book 0200");
            assertEquals(before.getJSONArray("keys").toString(),after.getJSONArray("keys").toString());
            detail.put("before",before).put("after",after).put("network_disabled",true);
        });
        run("system_picker_import_appears_in_product_search",detail->{
            pick("NewReview.txt");
            assertTrue(device.wait(Until.hasObject(By.textContains("Imported NewReview.txt")),30000));
            search("NewReview.txt");JSONObject value=ready("NewReview.txt");assertEquals(1,value.getInt("cached_rows"));
            detail.put("imported",value);
        });
        int failures=0;for(int at=0;at<cases.length();at++)if(!cases.getJSONObject(at).getString("status").equals("pass"))failures++;
        JSONObject result=identity().put("cases",cases).put("intervals",intervals).put("passed",cases.length()-failures)
                .put("failed",failures).put("skipped",0).put("physical_device_execution",false)
                .put("scope","API34 x86_64 production catalog shelf candidate");
        write(new File(output,"validation.json"),result.toString(2));
        device.pressHome();SystemClock.sleep(250);device.executeShellCommand("am force-stop "+APP);
        assertEquals("shelf walkthrough failures",0,failures);
    }

    private void run(String id,Body body)throws Exception {
        JSONObject item=identity().put("id",id).put("started_elapsed_ns",SystemClock.elapsedRealtimeNanos());
        try{JSONObject detail=new JSONObject();body.run(detail);item.put("status","pass").put("detail",detail);}
        catch(Throwable error){
            item.put("status","fail").put("error",error.toString());
            for(StackTraceElement frame:error.getStackTrace())if(frame.getClassName().equals(getClass().getName())){
                item.put("test_source_line",frame.getLineNumber());break;
            }
        }
        item.put("finished_elapsed_ns",SystemClock.elapsedRealtimeNanos());cases.put(item);
        device.takeScreenshot(new File(output,"shots/"+id+".png"));
        write(new File(output,id+".json"),item.toString(2));
    }
    private JSONObject identity()throws Exception {
        return new JSONObject().put("source_sha",args.getString("exr_source_sha")).put("run_id",args.getString("exr_run_id"))
                .put("attempt",args.getString("exr_attempt")).put("sdk",android.os.Build.VERSION.SDK_INT)
                .put("abi",android.os.Build.SUPPORTED_ABIS[0]);
    }
    private void interval(String name,long from,long to)throws Exception {intervals.put(new JSONObject().put("name",name).put("started_elapsed_ns",from).put("finished_elapsed_ns",to));}
    private static Set<String> keys(JSONArray array)throws Exception {Set<String> out=new HashSet<>();for(int at=0;at<array.length();at++)assertTrue("duplicate source in a page/window",out.add(array.getString(at)));return out;}
    private void bounds(JSONObject value)throws Exception {
        assertEquals(50,value.getInt("page_limit"));assertEquals(150,value.getInt("cache_limit"));
        assertTrue(value.getInt("cached_rows")<=150);assertTrue(value.getInt("max_cached_rows")<=150);
        assertTrue("attached rows bounded by a page",value.getInt("visible_children")<=50);
        assertTrue("created row Views bounded by two pages",value.getInt("created_views")<=100);
    }
    private void launch()throws Exception {device.executeShellCommand("am start -n "+APP+"/.MainActivity --ez shelf_metrics true");}
    private void click(String id)throws Exception {
        long end=SystemClock.uptimeMillis()+10000;
        while(SystemClock.uptimeMillis()<end)try{
            UiObject2 value=device.findObject(By.res(APP+":id/"+id));
            if(value!=null && value.isEnabled()){value.click();return;}
            SystemClock.sleep(100);
        }catch(StaleObjectException stale){SystemClock.sleep(100);}
        throw new AssertionError("control missing or not ready: "+id);
    }
    private void pick(String name)throws Exception {
        click("import_button");long end=SystemClock.uptimeMillis()+30000;
        while(SystemClock.uptimeMillis()<end)try{
            UiObject2 file=device.findObject(By.text(name));
            if(file!=null && file.isEnabled()){
                file.click();assertTrue("system picker returns to actual app",device.wait(Until.hasObject(By.pkg(APP)),10000));return;
            }
            UiObject2 folder=device.findObject(By.text("Download"));if(folder==null)folder=device.findObject(By.text("Downloads"));
            if(folder!=null)folder.click();
            else{
                UiObject2 roots=device.findObject(By.descContains("Show roots"));
                if(roots!=null)roots.click();
                else device.swipe(device.getDisplayWidth()/2,device.getDisplayHeight()*3/4,
                        device.getDisplayWidth()/2,device.getDisplayHeight()/4,25);
            }
            SystemClock.sleep(150);
        }catch(StaleObjectException stale){SystemClock.sleep(100);}
        throw new AssertionError("system file picker did not list "+name);
    }
    private void search(String query)throws Exception {
        for(int retry=0;retry<4;retry++)try{
            UiObject2 field=device.wait(Until.findObject(By.res(APP+":id/shelf_search")),10000);assertNotNull(field);field.setText(query);
            // Hide only an actually visible IME; an unconditional Back can finish the shelf Activity.
            if(device.executeShellCommand("dumpsys input_method").contains("mInputShown=true"))device.pressBack();return;
        }catch(StaleObjectException stale){if(retry==3)throw stale;}
    }
    private void scroll(boolean previous)throws Exception {
        // ListView's real accessibility scroll advances one viewport with a bounded smooth scroll.
        // A high-velocity injected fling can skip unseen rows between observations.
        AccessibilityNodeInfo root=InstrumentationRegistry.getInstrumentation().getUiAutomation().getRootInActiveWindow();
        assertNotNull(root);List<AccessibilityNodeInfo> nodes=root.findAccessibilityNodeInfosByViewId(APP+":id/book_list");
        assertFalse(nodes.isEmpty());assertTrue(nodes.get(0).performAction(previous
                ? AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD : AccessibilityNodeInfo.ACTION_SCROLL_FORWARD));
        SystemClock.sleep(260);
    }
    private JSONObject ready(String query)throws Exception {
        long end=SystemClock.uptimeMillis()+30000;JSONObject last=null;
        while(SystemClock.uptimeMillis()<end){
            AccessibilityNodeInfo root=InstrumentationRegistry.getInstrumentation().getUiAutomation().getRootInActiveWindow();
            if(root!=null){
                List<AccessibilityNodeInfo> nodes=root.findAccessibilityNodeInfosByViewId(APP+":id/shelf_summary");
                for(AccessibilityNodeInfo node:nodes){String raw=node.getExtras().getString("exreader.shelf");
                    if(raw!=null){last=new JSONObject(raw);if(last.getString("query").equals(query) && !last.getBoolean("loading")
                            && last.getLong("generation")==last.getLong("applied_generation")
                            && (last.getInt("cached_rows")==0 || last.getInt("visible_children")>0)
                            && last.getLong("first_interactive_elapsed_ns")>0){SystemClock.sleep(60);return last;}}
                }
            }
            SystemClock.sleep(90);
        }
        throw new AssertionError("shelf did not settle for "+query+": "+last);
    }
    private static void write(File file,String text)throws Exception {try(FileOutputStream out=new FileOutputStream(file)){out.write((text+"\n").getBytes(StandardCharsets.UTF_8));}}
}
