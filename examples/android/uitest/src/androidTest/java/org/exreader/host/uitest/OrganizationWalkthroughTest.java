// SPDX-License-Identifier: MIT
package org.exreader.host.uitest;

import static org.junit.Assert.*;
import android.content.Context;
import android.os.Bundle;
import android.os.SystemClock;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.uiautomator.By;
import androidx.test.uiautomator.UiDevice;
import androidx.test.uiautomator.UiObject2;
import androidx.test.uiautomator.Until;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.List;

/** Drives the actual native Android organization controls over real SDK books. */
@RunWith(AndroidJUnit4.class)
public final class OrganizationWalkthroughTest {
    private static final String APP="org.exreader.host";
    private final JSONArray cases=new JSONArray();
    private UiDevice device;private Context context;private Bundle args;private File output;
    interface Body { void run(JSONObject detail)throws Exception; }
    @Test public void organize()throws Exception{
        device=UiDevice.getInstance(InstrumentationRegistry.getInstrumentation());context=InstrumentationRegistry.getInstrumentation().getTargetContext();args=InstrumentationRegistry.getArguments();
        output=new File(context.getExternalFilesDir(null),"organization-evidence");assertFalse(output.exists());assertTrue(new File(output,"shots").mkdirs());device.setOrientationNatural();
        JSONObject seed=new JSONObject(device.executeShellCommand("cat /sdcard/Android/data/"+APP+"/files/organization-tests/seed.json"));
        assertEquals(args.getString("exr_source_sha"),seed.getString("source_sha"));assertEquals(2,seed.getInt("books"));
        try {
            run("more_create_edit_and_nested_shelves",detail->{
                launch();open();create("UI Shelf","0");item("UI Shelf");clickText("Edit");field("Name","UI Shelf edited");clickText("Save");waitItem("UI Shelf edited");
                item("UI Shelf edited");clickText("Children");ready();create("UI Child","0");waitItem("UI Child");
                detail.put("entry","More → Organize").put("nested_parent_retained",true);
            });
            run("add_books_via_public_original_bootstrap",detail->{
                item("UI Child");clickText("Books");ready();addBook("Org One edited 😀","0");addBook("Org Two","3");
                assertTrue(items().get(0).getText().startsWith("Org One edited 😀"));detail.put("real_sdk_books",2).put("user_title_visible",true);
            });
            run("remove_and_explicitly_restore_membership",detail->{
                item("Org One edited 😀");clickText("Remove");committed();assertFalse(hasItem("Org One edited 😀"));
                clickText("Add book");ready();item("Org One edited 😀");assertNotNull(device.wait(Until.findObject(By.textContains("Previously removed")),10000));
                clickText("Restore");committed();waitItem("Org One edited 😀");detail.put("explicit_restore",true);
            });
            run("series_ordinal_changes_visible_order",detail->{
                kind("Series");create("UI Series",null);item("UI Series");clickText("Books");ready();
                addBook("Org One edited 😀","20");addBook("Org Two","10");assertTrue(items().get(0).getText().startsWith("Org Two"));
                item("Org One edited 😀");field("Order — smaller first","1");clickText("Save order");committed();
                assertTrue(items().get(0).getText().startsWith("Org One edited 😀"));detail.put("before_first","Org Two").put("after_first","Org One edited 😀");
            });
            run("group_delete_and_full_removed_restore",detail->{
                kind("Series");item("UI Series");clickText("Delete");clickText("Delete");committed();assertFalse(hasItem("UI Series"));
                clickText("Removed");ready();item("UI Series");clickText("Restore");clickText("Restore");committed();assertFalse(hasItem("UI Series"));
                clickText("Active");ready();waitItem("UI Series");detail.put("removed_view",true).put("restored_to_active",true);
            });
            run("bounded_forward_reverse_and_removed_pages",detail->{
                kind("Shelves");List<UiObject2> first=items();String original=first.get(0).getText();
                assertTrue(first.size()<=50);clickText("Next");ready();String second=items().get(0).getText();assertNotEquals(original,second);
                clickText("Previous");ready();assertEquals(original,items().get(0).getText());
                kind("Tags");clickText("Removed");ready();assertTrue(items().get(0).getText().startsWith("Trash 200"));
                clickText("Next");ready();assertTrue(items().get(0).getText().startsWith("Trash 250"));
                clickText("Previous");ready();assertTrue(items().get(0).getText().startsWith("Trash 200"));
                detail.put("page_limit",50).put("retained_pages",1).put("removed_items_from_previous_process",105);
            });
            run("book_long_press_organize_entry",detail->{
                clickText("Close");UiObject2 book=device.wait(Until.findObject(By.textContains("Org One edited 😀")),10000);assertNotNull(book);book.longClick();
                clickText("Organize book");ready();assertNotNull(device.findObject(By.textContains("choose for Org One edited 😀")));detail.put("stable_book_choice",true);
            });
            run("refused_intent_kill_and_exact_ui_retry",detail->{
                phase("fault");launch();open();kind("Tags");createRefused("Killed retry");
                clickText("Saved intent");assertNotNull(device.wait(Until.findObject(By.textContains("Save tag: Killed retry")),10000));clickText("Close");
                String oldPid=device.executeShellCommand("pidof "+APP).trim();assertTrue(oldPid.matches("[0-9]+"));
                device.executeShellCommand("am force-stop "+APP);assertTrue(device.executeShellCommand("pidof "+APP).trim().isEmpty());
                phase("release-fault");device.executeShellCommand("am force-stop "+APP);launch();open();
                clickText("Saved intent");clickText("Retry exact intent");committed();
                phase("verify-ui");String newPid=device.executeShellCommand("pidof "+APP).trim();assertNotEquals(oldPid,newPid);
                JSONObject verified=new JSONObject(device.executeShellCommand("cat /sdcard/Android/data/"+APP+"/files/organization-tests/verified.json"));
                assertTrue(verified.getBoolean("exact_retry"));assertTrue(verified.getBoolean("product_fields_preserved"));
                detail.put("old_pid",oldPid).put("new_pid",newPid).put("verified",verified);
            });
        } finally {
            JSONObject report=identity().put("cases",cases).put("count",8).put("passed",cases.length()).put("failed",cases.length()==8?0:1).put("skipped",0);
            Files.write(new File(output,"validation.json").toPath(),report.toString(2).getBytes(StandardCharsets.UTF_8));
        }
    }
    private JSONObject identity()throws Exception{return new JSONObject().put("source_sha",args.getString("exr_source_sha")).put("run_id",args.getString("exr_run_id")).put("attempt",args.getString("exr_attempt"));}
    private void run(String name,Body body)throws Exception{
        JSONObject detail=new JSONObject();body.run(detail);JSONObject row=identity().put("id",name).put("status","pass").put("detail",detail);
        assertTrue(device.takeScreenshot(new File(output,"shots/"+name+".png")));Files.write(new File(output,name+".json").toPath(),row.toString(2).getBytes(StandardCharsets.UTF_8));cases.put(row);
    }
    private void phase(String name)throws Exception{
        String result=device.executeShellCommand("am instrument -w -r -e phase "+name+" -e source_sha "+args.getString("exr_source_sha")+
            " -e run_id "+args.getString("exr_run_id")+" -e attempt "+args.getString("exr_attempt")+" "+APP+".test/org.exreader.host.OrganizationTest");
        Files.write(new File(output,"phase-"+name+".txt").toPath(),result.getBytes(StandardCharsets.UTF_8));
        assertTrue(result,result.contains("EXR_ORGANIZATION_PHASE "+name));
    }
    private void launch()throws Exception{device.executeShellCommand("am start -W -n "+APP+"/.MainActivity");assertNotNull(device.wait(Until.findObject(By.res(APP+":id/more_button")),20000));}
    private void open(){UiObject2 panel=device.findObject(By.desc("Organize panel"));if(panel!=null)return;clickText("More");clickText("Organize");ready();}
    private void kind(String name){clickText("Kind");clickText(name);ready();}
    private void clickText(String text){UiObject2 view=device.wait(Until.findObject(By.text(text)),15000);assertNotNull("Missing "+text,view);assertTrue("Disabled "+text,view.isEnabled());view.click();}
    private void field(String hint,String text){UiObject2 view=device.wait(Until.findObject(By.desc(hint)),10000);assertNotNull(hint,view);view.setText(text);}
    private void ready(){
        long deadline=SystemClock.uptimeMillis()+20000;while(SystemClock.uptimeMillis()<deadline){
            UiObject2 value=device.findObject(By.desc("Organization status"));if(value!=null&&value.getText()!=null&&value.getText().contains("items"))return;SystemClock.sleep(100);
        }fail("Organization page did not settle");
    }
    private void committed(){
        assertNotNull(device.wait(Until.findObject(By.textContains("Change committed")),20000));ready();
    }
    private List<UiObject2> items(){UiObject2 list=device.wait(Until.findObject(By.desc("Organization items")),10000);assertNotNull(list);return list.getChildren();}
    private boolean hasItem(String prefix){for(UiObject2 row:items())if(row.getText()!=null&&row.getText().startsWith(prefix))return true;return false;}
    private void waitItem(String prefix){assertNotNull(device.wait(Until.findObject(By.textStartsWith(prefix)),15000));}
    private void item(String prefix){UiObject2 row=device.wait(Until.findObject(By.textStartsWith(prefix)),15000);assertNotNull("Missing item "+prefix,row);row.click();}
    private void create(String name,String order){clickText("New");field("Name",name);if(order!=null)field("Order — smaller first",order);clickText("Save");committed();waitItem(name);}
    private void addBook(String title,String order){clickText("Add book");ready();item(title);if(order!=null&&device.wait(Until.hasObject(By.desc("Order — smaller first")),3000))field("Order — smaller first",order);clickText("Add");committed();waitItem(title);}
    private void createRefused(String name){clickText("New");field("Name",name);clickText("Save");assertNotNull(device.wait(Until.findObject(By.textContains("Change refused")),20000));}
}
