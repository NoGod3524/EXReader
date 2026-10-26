// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.app.AlertDialog;
import android.net.Uri;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ListView;
import java.util.ArrayList;
import java.util.List;

/** Local fonts: SAF import into the reviewed library, explicit selection, explicit removal. */
final class FontPanel extends Wave3Dialog {
    static final int REQUEST=1101;
    static final long LIMIT=16L*1024*1024+1;
    private ListView list;private ArrayAdapter<String> adapter;private List<NativeFonts.Font> fonts=new ArrayList<>();private String selected="";private Button importButton,defaultButton,cancelButton;private boolean busy;
    private AlertDialog choice;
    FontPanel(android.app.Activity activity,Wave3Host host){super(activity,host);}
    @Override void build() {
        LinearLayout actions=row();
        importButton=button(actions,"导入字体…",this::pick);defaultButton=button(actions,"使用默认字体",this::useDefault);cancelButton=button(actions,"取消",()->{cancelTask();});
        list=new ListView(activity);list.setContentDescription("本地字体列表");adapter=new ArrayAdapter<>(activity,android.R.layout.simple_list_item_1,new ArrayList<>());list.setAdapter(adapter);
        content.addView(list,new LinearLayout.LayoutParams(-1,dp(220)));
        list.setOnItemClickListener((parent,view,position,id)->{if(!busy&&position>=0&&position<fonts.size())choose(fonts.get(position));});
    }
    void show(){open("本地字体","字体状态");controls(false);load("字体仅用于 EPUB 阅读排版；选择后下次打开书籍生效");}
    @Override void released(){if(choice!=null){choice.dismiss();choice=null;}}
    private void controls(boolean value){busy=value;if(importButton==null)return;importButton.setEnabled(!value);defaultButton.setEnabled(!value);cancelButton.setEnabled(value);list.setEnabled(!value);}
    private void load(String note) {
        long stamp=request();controls(true);message("正在读取字体库");
        host.fontList(task,state->post(stamp,()->{fonts=state.fonts;selected=state.selected;adapter.clear();for(NativeFonts.Font font:fonts)adapter.add((font.hash.equals(selected)?"✓ 使用中 · ":"")+font.label());adapter.notifyDataSetChanged();controls(false);message(fonts.isEmpty()?"尚未导入字体。"+note:fonts.size()+" 个本地字体。"+note);}),
            error->post(stamp,()->{controls(false);message("字体库不可用："+reason(error));}));
    }
    private void pick(){if(busy)return;host.pick(REQUEST);}
    /** The system picker returned while the panel was closed with the stopped Activity. */
    void picked(Uri uri) {
        show();long stamp=request();controls(true);message("正在复制所选字体");
        host.stage(uri,"fonts",LIMIT,task,staged->post(stamp,()->{
            host.fontImport(staged.file,Wave3Files.label(staged.name,"font",true),task,result->{host.discard(staged.file);post(stamp,()->{
                load(result.ok()?(result.created!=0?"已导入 ":"已存在 ")+result.name+"（"+result.hash.substring(0,8)+"）":"字体未导入："+result.reason()+"，原有字体保留");
            });},error->{host.discard(staged.file);post(stamp,()->{controls(false);message("字体未导入："+reason(error)+"，原有字体保留");});});
        },()->host.discard(staged.file)),error->post(stamp,()->{controls(false);message("无法读取所选文件："+reason(error));}));
    }
    private void choose(NativeFonts.Font font) {
        long stamp=request();
        choice=new AlertDialog.Builder(activity).setTitle(font.name).setItems(new String[]{"使用此字体","删除此字体"},(d,which)->{
            if(!current(stamp))return;
            if(which==0)select(font.hash,font.name);else confirmRemove(font);
        }).setNegativeButton("返回",null).show();
    }
    private void useDefault(){select("","默认字体");}
    private void select(String hash,String label) {
        long stamp=request();controls(true);
        host.fontSelect(hash,task,()->post(stamp,()->load(hash.isEmpty()?"已恢复默认字体，下次打开书籍生效":"已选择 "+label+"，下次打开书籍生效")),
            error->post(stamp,()->{controls(false);message("未能切换字体："+reason(error));}));
    }
    private void confirmRemove(NativeFonts.Font font) {
        long stamp=request();
        choice=new AlertDialog.Builder(activity).setTitle("删除字体？").setMessage(font.label()+"\n正在使用的书籍排版不受影响，之后恢复默认字体。").setPositiveButton("删除",(d,w)->{
            if(!current(stamp))return;
            controls(true);message("正在删除");
            host.fontRemove(font.hash,task,code->post(stamp,()->{
                if(code==NativeFonts.OK)load("已删除 "+font.name);
                else{controls(false);message(code==NativeFonts.BUSY?"字体正被阅读页借用，请先退出阅读再删除":code==NativeFonts.COMMIT_UNCERTAIN?"删除结果不确定，请重新打开本面板核对":"未能删除（"+code+"）");}
            }),error->post(stamp,()->{controls(false);message("未能删除："+reason(error));}));
        }).setNegativeButton("返回",null).show();
    }
}
