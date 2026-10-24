// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.app.Activity;
import android.app.AlertDialog;
import android.view.View;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.TextView;
import java.util.ArrayList;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Consumer;

/** Native, one-page directory browser. No SDK pointer or automatic external link. */
final class NavigationPanel {
    interface Host {
        void directory(long book,HostTask task,Consumer<NativeNavigation.Info> done,Consumer<Throwable> failed);
        void directoryPage(long book,long parent,long first,HostTask task,Consumer<NativeNavigation.Page> done,Consumer<Throwable> failed);
        void directoryResolve(long book,long row,long part,String cfi,HostTask task,Consumer<NativeNavigation.Destination> done,Consumer<Throwable> failed);
        void navigateDirectory(NativeNavigation.Destination destination);
        void releaseDirectory();
    }
    private final Activity activity;private final Host host;private final AtomicLong epoch=new AtomicLong();
    private AlertDialog dialog,choice;private HostTask task;private long book,parent=-1,next=-1;private boolean busy;private NativeNavigation.Info info;
    private TextView status;private Button up,more,cfiButton,cancel;private ListView list;private ArrayAdapter<String> adapter;private NativeNavigation.Row[] rows=new NativeNavigation.Row[0];
    private final ArrayList<Long> parents=new ArrayList<>();
    NavigationPanel(Activity activity,Host host){this.activity=activity;this.host=host;}
    private Button button(LinearLayout container,String label,Runnable action){Button button=new Button(activity);button.setText(label);button.setOnClickListener(v->action.run());container.addView(button,new LinearLayout.LayoutParams(-1,-2));return button;}
    void show(long book){
        close();this.book=book;parent=-1;next=-1;parents.clear();rows=new NativeNavigation.Row[0];info=null;
        LinearLayout content=new LinearLayout(activity);content.setOrientation(LinearLayout.VERTICAL);int pad=(int)(12*activity.getResources().getDisplayMetrics().density);content.setPadding(pad,pad,pad,pad);
        status=new TextView(activity);status.setContentDescription("目录状态");status.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);content.addView(status);
        list=new ListView(activity);list.setContentDescription("目录条目");adapter=new ArrayAdapter<>(activity,android.R.layout.simple_list_item_1,new ArrayList<>());list.setAdapter(adapter);content.addView(list,new LinearLayout.LayoutParams(-1,(int)(220*activity.getResources().getDisplayMetrics().density)));
        list.setOnItemClickListener((p,v,position,id)->{if(!busy&&position>=0&&position<rows.length)select(rows[position]);});
        up=button(content,"上一级",()->{if(!parents.isEmpty()){parent=parents.remove(parents.size()-1);page(0);}});
        more=button(content,"下一批条目",()->page(next));cfiButton=button(content,"CFI 位置",this::cfi);cancel=button(content,"取消读取",()->{if(task!=null)task.cancel();});
        AlertDialog opened=new AlertDialog.Builder(activity).setTitle("目录 / 按页入口").setView(content).setNegativeButton("关闭",null).create();dialog=opened;opened.setOnDismissListener(value->{if(dialog==opened)closed();});opened.show();
        long request=request();controls(true);message("正在读取目录");host.directory(book,task,value->activity.runOnUiThread(()->{if(!current(request))return;info=value;page(0);}),error->activity.runOnUiThread(()->failure(request,error)));
    }
    private void message(String value){if(status!=null)status.setText(value);}
    private void controls(boolean value){busy=value;if(list==null)return;list.setEnabled(!value);up.setEnabled(!value&&!parents.isEmpty());more.setEnabled(!value&&next>=0);cfiButton.setEnabled(!value&&info!=null&&info.source==NativeNavigation.PUBLICATION);cancel.setEnabled(value);}
    private long request(){if(task!=null)task.cancel();long value=epoch.incrementAndGet();task=new HostTask(()->epoch.get()!=value);return value;}
    private boolean current(long request){return dialog!=null&&dialog.isShowing()&&epoch.get()==request;}
    private void failure(long request,Throwable error){if(!current(request))return;controls(false);message(error instanceof HostTask.Cancelled?"已取消，可关闭后重新读取":"目录读取失败，请关闭后重试");}
    private void page(long first){
        if(first<0)return;long request=request();controls(true);message("正在读取条目");
        host.directoryPage(book,parent,first,task,value->activity.runOnUiThread(()->{if(!current(request))return;rows=value.rows;next=value.next;adapter.clear();for(NativeNavigation.Row row:rows)adapter.add(row.display());controls(false);message(info.kind==2?"按页入口 · 非作者大纲 · "+value.total+" 页":value.total==0?"此书没有自带目录":"目录 · "+value.total+" 项 · 本批 "+rows.length+" 项"+(next<0?" · 已列完":""));}),error->activity.runOnUiThread(()->failure(request,error)));
    }
    private void select(NativeNavigation.Row row){
        if(row.children==0){resolve(row.index,-1,null,false);return;}
        long stamp=epoch.get();choice=new AlertDialog.Builder(activity).setTitle(row.label.isEmpty()?"目录分组":row.label).setItems(new String[]{"查看子项","打开此目标"},(d,which)->{if(!current(stamp))return;choice=null;if(which==0){parents.add(parent);parent=row.index;page(0);}else resolve(row.index,-1,null,false);}).setNegativeButton("返回",(d,w)->{if(current(stamp))choice=null;}).show();
    }
    private void cfi(){
        EditText input=new EditText(activity);input.setSingleLine(true);input.setContentDescription("EPUB CFI");input.setHint("epubcfi(...)");input.setFilters(new android.text.InputFilter[]{new android.text.InputFilter.LengthFilter(4096)});
        long stamp=epoch.get();choice=new AlertDialog.Builder(activity).setTitle("CFI 位置").setView(input).setPositiveButton("定位",(d,w)->{if(!current(stamp))return;choice=null;resolve(-1,-1,input.getText().toString(),false);}).setNegativeButton("返回",(d,w)->{if(current(stamp))choice=null;}).show();
    }
    private void resolve(long row,long part,String cfi,boolean acceptPartOnly){
        long request=request();controls(true);message("正在核对目标");
        host.directoryResolve(book,row,part,cfi,task,destination->activity.runOnUiThread(()->{
            if(!current(request))return;controls(false);NativeNavigation.Result result=destination.result;
            if(result.status==NativeNavigation.OK||(result.status==NativeNavigation.PART_ONLY&&acceptPartOnly)){close();host.navigateDirectory(destination);return;}
            if(result.status==NativeNavigation.AMBIGUOUS){message("路径有多个章节，尚未跳转");String[] labels=new String[result.candidates.length];for(int i=0;i<labels.length;i++)labels[i]="第 "+(result.candidates[i]+1)+" 章";choice=new AlertDialog.Builder(activity).setTitle("明确选择章节").setItems(labels,(d,which)->{if(!current(request))return;choice=null;resolve(row,result.candidates[which],cfi,false);}).setNegativeButton("不跳转",(d,w)->{if(current(request))choice=null;}).show();return;}
            if(result.status==NativeNavigation.PART_ONLY){message("片段不存在，尚未跳转");choice=new AlertDialog.Builder(activity).setTitle("片段不存在").setMessage("仅此章节已确认，是否明确打开章节开头？").setPositiveButton("仅打开章节开头",(d,w)->{if(!current(request))return;choice=null;resolve(row,result.part,cfi,true);}).setNegativeButton("不跳转",(d,w)->{if(current(request))choice=null;}).show();return;}
            message(result.status==NativeNavigation.NEEDS_HOST?"外部目标，未打开":result.status==NativeNavigation.UNMAPPABLE?"无法精确映射此 CFI 位置，未跳转":"目标无法匹配，未跳转");
        }),error->activity.runOnUiThread(()->failure(request,error)));
    }
    private void closed(){epoch.incrementAndGet();if(task!=null)task.cancel();task=null;dialog=null;if(choice!=null){choice.dismiss();choice=null;}status=null;rows=new NativeNavigation.Row[0];host.releaseDirectory();}
    boolean visible(){return dialog!=null&&dialog.isShowing();}
    void close(){if(dialog==null&&task==null)return;AlertDialog closing=dialog;if(closing!=null){closing.setOnDismissListener(null);closing.dismiss();}closed();}
}
