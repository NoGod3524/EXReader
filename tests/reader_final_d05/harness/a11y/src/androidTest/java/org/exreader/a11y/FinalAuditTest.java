package org.exreader.a11y;

import android.graphics.Rect;
import android.os.SystemClock;
import android.view.accessibility.AccessibilityNodeInfo;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.uiautomator.*;
import org.json.*;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

@RunWith(AndroidJUnit4.class)
public class FinalAuditTest {
    final String app="org.exreader.host";
    UiDevice d;
    File out;
    JSONArray cases=new JSONArray(), events=new JSONArray();
    String last="setup";
    int sequence=0;
    interface Action { void run() throws Exception; }
    void require(boolean ok,String why) { if(!ok)throw new AssertionError(why); }
    void write(String name,String value)throws Exception {try(FileOutputStream f=new FileOutputStream(new File(out,name))){f.write(value.getBytes(StandardCharsets.UTF_8));}}
    String shell(String cmd)throws Exception {String value=d.executeShellCommand(cmd);events.put(new JSONObject().put("command",cmd).put("output",value).put("elapsed_ms",SystemClock.elapsedRealtime()));return value;}
    void input(String what,Action a)throws Exception {events.put(new JSONObject().put("input",what).put("elapsed_ms",SystemClock.elapsedRealtime()));a.run();SystemClock.sleep(700);}
    void click(String id)throws Exception {UiObject2 n=d.wait(Until.findObject(By.res(app+":id/"+id)),12000);require(n!=null&&n.isEnabled(),"unreachable control: "+id);input("click "+id,()->n.click());}
    void back()throws Exception {input("KEYCODE_BACK",()->d.pressBack());}
    void launch()throws Exception {shell("am start -W -n "+app+"/.MainActivity");require(d.wait(Until.hasObject(By.pkg(app)),20000),"host launch failed");SystemClock.sleep(1800);}
    void shelf()throws Exception {if(d.hasObject(By.res(app+":id/back_button")))click("back_button");require(d.wait(Until.hasObject(By.res(app+":id/import_button")),12000),"shelf not reached");}
    String text(String id){UiObject2 n=d.findObject(By.res(app+":id/"+id));return n==null?"":String.valueOf(n.getText());}
    void open()throws Exception {if(d.hasObject(By.res(app+":id/reader_view")))return;UiObject2 n=d.wait(Until.findObject(By.textContains("Sample.epub")),12000);if(n==null)n=d.wait(Until.findObject(By.textStartsWith("EXReader Android Sample")),12000);require(n!=null,"imported book not reachable");UiObject2 row=n;input("click imported Sample row",()->row.click());require(d.wait(Until.hasObject(By.res(app+":id/reader_view")),30000),"reader not opened");SystemClock.sleep(2000);}
    String value(CharSequence s){return s==null?"":s.toString();}
    JSONObject node(AccessibilityNodeInfo n)throws Exception {
        Rect r=new Rect();n.getBoundsInScreen(r);JSONArray kids=new JSONArray(),actions=new JSONArray();
        for(AccessibilityNodeInfo.AccessibilityAction a:n.getActionList())actions.put(new JSONObject().put("id",a.getId()).put("label",value(a.getLabel())));
        for(int i=0;i<n.getChildCount();i++){AccessibilityNodeInfo c=n.getChild(i);if(c!=null)kids.put(node(c));}
        return new JSONObject().put("id",value(n.getViewIdResourceName())).put("text",value(n.getText())).put("description",value(n.getContentDescription())).put("class",value(n.getClassName())).put("hint",value(n.getHintText())).put("state",value(n.getStateDescription())).put("clickable",n.isClickable()).put("focusable",n.isFocusable()).put("focused",n.isFocused()).put("selected",n.isSelected()).put("enabled",n.isEnabled()).put("visible",n.isVisibleToUser()).put("scrollable",n.isScrollable()).put("bounds",new JSONArray(Arrays.asList(r.left,r.top,r.right,r.bottom))).put("actions",actions).put("children",kids);
    }
    JSONObject capture(String name)throws Exception {
        String base=String.format("%03d-%s",sequence++,name.replace('/','_'));last=base;
        require(d.takeScreenshot(new File(out,base+".png")),"screenshot missing");d.dumpWindowHierarchy(new File(out,base+".xml"));
        AccessibilityNodeInfo root=InstrumentationRegistry.getInstrumentation().getUiAutomation().getRootInActiveWindow();require(root!=null,"no active root");
        JSONObject j=new JSONObject().put("name",base).put("tree",node(root)).put("width",d.getDisplayWidth()).put("height",d.getDisplayHeight()).put("font_scale",shell("settings get system font_scale").trim()).put("density",shell("wm density")).put("pid",shell("pidof "+app).trim()).put("activity",shell("dumpsys activity activities"));write(base+".json",j.toString(2));return j;
    }
    void inspect(JSONObject n,int w,int h,Set<String> names,List<String> bad)throws Exception {
        if(n.getBoolean("visible")&&(n.getBoolean("clickable")||n.getBoolean("focusable"))){JSONArray b=n.getJSONArray("bounds");String label=n.getString("description");if(label.isEmpty())label=n.getString("text");if(label.isEmpty())label=n.getString("hint");
            // Containers can delegate naming to children; leaves cannot.
            if(label.isEmpty()&&n.getJSONArray("children").length()==0)bad.add("unnamed "+n.getString("id"));
            if(!label.isEmpty()&&!names.add(label))bad.add("duplicate label "+label);
            if(b.getInt(2)<=b.getInt(0)||b.getInt(3)<=b.getInt(1)||b.getInt(0)<0||b.getInt(1)<0||b.getInt(2)>w||b.getInt(3)>h)bad.add("invalid bounds "+n.getString("id")+b);
        }
        JSONArray children=n.getJSONArray("children");for(int i=0;i<children.length();i++)inspect(children.getJSONObject(i),w,h,names,bad);
    }
    void semantics(JSONObject c)throws Exception {List<String> bad=new ArrayList<>();inspect(c.getJSONObject("tree"),c.getInt("width"),c.getInt("height"),new HashSet<>(),bad);require(bad.isEmpty(),bad.toString());}
    void test(String id,Action a)throws Exception {JSONObject c=new JSONObject().put("id",id).put("start_ms",SystemClock.elapsedRealtime());try{a.run();c.put("verdict","pass");}catch(Throwable e){c.put("verdict","fail").put("error",e.toString());StringWriter s=new StringWriter();e.printStackTrace(new PrintWriter(s));c.put("stack",s.toString());try{capture(id+"-failure");}catch(Throwable cap){c.put("capture_error",cap.toString());}}c.put("last_capture",last).put("end_ms",SystemClock.elapsedRealtime());cases.put(c);write("cases.json",cases.toString(2));write("events.json",events.toString(2));}
    @Test public void audit()throws Exception {
        d=UiDevice.getInstance(InstrumentationRegistry.getInstrumentation());out=new File(InstrumentationRegistry.getInstrumentation().getTargetContext().getExternalFilesDir(null),"final-evidence");require(out.mkdirs(),"fresh evidence directory required");
        try {
            test("default_shelf",()->{launch();semantics(capture("default-shelf"));});
            test("import_cancel",()->{shelf();click("import_button");require(d.wait(Until.hasObject(By.pkg("com.android.documentsui")),15000),"picker missing");capture("picker-cancel-before");back();require(d.wait(Until.hasObject(By.res(app+":id/import_button")),10000),"cancel did not return shelf");capture("picker-cancel-after");});
            test("import_sample",()->{shelf();click("import_button");require(d.wait(Until.hasObject(By.pkg("com.android.documentsui")),15000),"picker missing");capture("picker-before-import");
                UiObject2 f=d.findObject(By.text("Sample.epub"));
                if(f==null){UiObject2 drawer=d.findObject(By.desc("Show roots"));if(drawer!=null){input("open picker roots",()->drawer.click());UiObject2 downloads=d.wait(Until.findObject(By.text("Downloads")),5000);if(downloads!=null)input("picker Downloads",()->downloads.click());}}
                for(int i=0;i<8 && (f=d.findObject(By.text("Sample.epub")))==null;i++){input("scroll document picker",()->d.swipe(d.getDisplayWidth()/2,d.getDisplayHeight()*3/4,d.getDisplayWidth()/2,d.getDisplayHeight()/3,25));}
                require(f!=null,"Sample.epub absent from document picker");UiObject2 file=f;input("select Sample.epub",()->file.click());require(d.wait(Until.hasObject(By.textContains("Imported Sample.epub")),45000),"import completion not reported");capture("import-completed");open();capture("opened");});
            test("touch_page",()->{open();String before=text("page_label");UiObject2 r=d.findObject(By.res(app+":id/reader_view"));Rect b=r.getVisibleBounds();input("reader right page zone",()->d.click(b.right-30,b.centerY()));SystemClock.sleep(2000);capture("page-after");require(!before.isEmpty()&&!before.equals(text("page_label")),"touch page did not advance");});
            for(String scale:new String[]{"1.0","1.3","2.0"}){
                test("font_"+scale,()->{shell("settings put system font_scale "+scale);SystemClock.sleep(2000);require(Math.abs(Float.parseFloat(shell("settings get system font_scale").trim())-Float.parseFloat(scale))<0.01,"font readback mismatch");launch();shelf();JSONObject s=capture("shelf-font"+scale);open();JSONObject r=capture("reader-font"+scale);semantics(s);semantics(r);});
                test("rotation_"+scale,()->{open();String book=text("book_title");capture("portrait-"+scale);input("setOrientationLeft",()->d.setOrientationLeft());SystemClock.sleep(2000);JSONObject c=capture("landscape-"+scale);require(d.getDisplayWidth()>d.getDisplayHeight(),"landscape not applied");require(!book.isEmpty()&&book.equals(text("book_title")),"rotation lost book");require(!text("page_label").isEmpty(),"rotation lost position label");semantics(c);});
                test("rebuild_"+scale,()->{input("setOrientationNatural",()->d.setOrientationNatural());SystemClock.sleep(1500);open();String book=text("book_title"),page=text("page_label");capture("before-rebuild-"+scale);click("rebuild_view");SystemClock.sleep(2500);capture("after-rebuild-"+scale);require(book.equals(text("book_title"))&&!page.isEmpty()&&page.equals(text("page_label")),"rebuild changed book/page");});
            }
            test("dpad_back",()->{shell("settings put system font_scale 1.0");SystemClock.sleep(1500);shelf();click("more_button");capture("more-before-keyboard");input("DPAD_DOWN",()->d.pressDPadDown());capture("more-dpad-focus");require(d.hasObject(By.focused(true)),"DPAD did not produce focus");back();require(d.hasObject(By.res(app+":id/import_button")),"Back failed to restore shelf");capture("more-after-back");});
            for(String label:new String[]{"书内搜索","目录 / 按页入口","阅读记录","阅读设置"})test("default_entry_"+label,()->{open();capture("entry-"+label);click("reader_more");UiObject2 n=d.wait(Until.findObject(By.text(label)),5000);require(n!=null,"default feature not reachable: "+label);input("open "+label,()->n.click());capture("panel-"+label);throw new AssertionError("panel opened but full operation remains unverified");});
            test("default_account",()->{shelf();click("more_button");capture("account-menu");require(d.hasObject(By.text("同步")),"default account/sync entry absent");throw new AssertionError("account operations remain unverified");});
        } finally {write("cases.json",cases.toString(2));write("events.json",events.toString(2));shell("settings put system font_scale 1.0");d.setOrientationNatural();}
    }
}
