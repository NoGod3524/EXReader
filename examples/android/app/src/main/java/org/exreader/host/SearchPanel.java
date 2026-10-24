// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.app.Activity;
import android.app.AlertDialog;
import android.text.InputFilter;
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

/** A modal, one-batch view. It never stores an SDK/native handle. */
final class SearchPanel {
    interface Host {
        void scan(long book,String query,boolean next,HostTask task,Consumer<NativeSearch.Batch> done,Consumer<Throwable> failed);
        void resolve(long book,NativeSearch.Hit hit,HostTask task,Consumer<NativeSearch.Match> done,Consumer<Throwable> failed);
        void navigate(long book,NativeSearch.Hit hit,NativeSearch.Match match);
        void releaseSearch();
    }
    private final Activity activity;private final Host host;private final AtomicLong epoch=new AtomicLong();
    private AlertDialog dialog;private EditText input;private TextView status;private Button start,cancel,more;private ListView list;
    private ArrayAdapter<String> adapter;private NativeSearch.Hit[] hits=new NativeSearch.Hit[0];private HostTask task;
    private long book;private String query="";private boolean busy,complete=true;
    SearchPanel(Activity activity,Host host){this.activity=activity;this.host=host;}
    private Button button(LinearLayout row,String label,Runnable action){Button view=new Button(activity);view.setText(label);view.setOnClickListener(v->action.run());row.addView(view,new LinearLayout.LayoutParams(0,-2,1));return view;}
    void show(long book){
        close();this.book=book;query="";complete=true;busy=false;
        LinearLayout content=new LinearLayout(activity);content.setOrientation(LinearLayout.VERTICAL);int pad=(int)(12*activity.getResources().getDisplayMetrics().density);content.setPadding(pad,pad,pad,pad);
        input=new EditText(activity);input.setSingleLine(true);input.setHint("输入要查找的文字");input.setContentDescription("书内搜索词");input.setFilters(new InputFilter[]{new InputFilter.LengthFilter(4096)});content.addView(input);
        LinearLayout actions=new LinearLayout(activity);content.addView(actions);
        start=button(actions,"搜索",()->scan(false));cancel=button(actions,"取消搜索",()->{if(task!=null)task.cancel();});
        status=new TextView(activity);status.setContentDescription("搜索状态");status.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);content.addView(status);
        list=new ListView(activity);list.setContentDescription("搜索结果");adapter=new ArrayAdapter<>(activity,android.R.layout.simple_list_item_1,new ArrayList<>());list.setAdapter(adapter);content.addView(list,new LinearLayout.LayoutParams(-1,(int)(260*activity.getResources().getDisplayMetrics().density)));
        list.setOnItemClickListener((parent,view,position,id)->{if(!busy&&position>=0&&position<hits.length)choose(hits[position]);});
        more=new Button(activity);more.setText("更多结果");more.setOnClickListener(v->scan(true));content.addView(more,new LinearLayout.LayoutParams(-1,-2));
        input.addTextChangedListener(new android.text.TextWatcher(){
            public void beforeTextChanged(CharSequence value,int start,int count,int after){}
            public void onTextChanged(CharSequence value,int start,int before,int count){}
            public void afterTextChanged(android.text.Editable value){if(busy||query.equals(value.toString()))return;epoch.incrementAndGet();if(task!=null)task.cancel();task=null;host.releaseSearch();hits=new NativeSearch.Hit[0];adapter.clear();complete=true;controls(false);message("输入文字后搜索；区分大小写");}
        });
        AlertDialog opened=new AlertDialog.Builder(activity).setTitle("书内搜索").setView(content).setNegativeButton("关闭",null).create();dialog=opened;opened.setOnDismissListener(value->{if(dialog==opened)closed();});opened.show();message("输入文字后搜索；区分大小写");controls(false);
    }
    private void message(String value){if(status!=null&&!value.contentEquals(status.getText()))status.setText(value);}
    private void controls(boolean value){busy=value;if(start==null)return;start.setEnabled(!value);cancel.setEnabled(value);more.setEnabled(!value&&!complete);list.setEnabled(!value);input.setEnabled(!value);}
    private long request(){if(task!=null)task.cancel();long request=epoch.incrementAndGet();task=new HostTask(()->epoch.get()!=request);return request;}
    private boolean current(long request){return dialog!=null&&dialog.isShowing()&&epoch.get()==request;}
    private void failure(long request,Throwable error){if(!current(request))return;controls(false);complete=true;more.setEnabled(false);message(error instanceof HostTask.Cancelled?"已取消，可重新搜索":error instanceof NativeSearch.Failure?error.getMessage():"未能搜索，请重试");}
    private void scan(boolean next){
        if(busy)return;if(!next){query=input.getText().toString();hits=new NativeSearch.Hit[0];adapter.clear();complete=true;}
        long request=request();controls(true);message("正在搜索");HostTask active=task;
        host.scan(book,query,next,active,batch->activity.runOnUiThread(()->{
            if(!current(request))return;hits=batch.hits;complete=batch.complete;adapter.clear();for(NativeSearch.Hit hit:hits)adapter.add(hit.label());controls(false);message(hits.length==0?"没有找到匹配文字":hits.length+" 个结果"+(complete?" · 已搜索完毕":" · 可继续查看"));
        }),error->activity.runOnUiThread(()->failure(request,error)));
    }
    private void choose(NativeSearch.Hit hit){
        long request=request();controls(true);message("正在定位");
        host.resolve(book,hit,task,match->activity.runOnUiThread(()->{
            if(!current(request))return;controls(false);
            if(match.state!=NativeSearch.FOUND){message(match.state==NativeSearch.AMBIGUOUS?"位置有歧义，未跳转":"位置已无法匹配，未跳转");return;}
            long selected=book;close();host.navigate(selected,hit,match);
        }),error->activity.runOnUiThread(()->failure(request,error)));
    }
    private void closed(){epoch.incrementAndGet();if(task!=null)task.cancel();task=null;dialog=null;status=null;hits=new NativeSearch.Hit[0];host.releaseSearch();}
    boolean visible(){return dialog!=null&&dialog.isShowing();}
    void close(){if(dialog==null&&task==null)return;AlertDialog closing=dialog;if(closing!=null){closing.setOnDismissListener(null);closing.dismiss();}closed();}
}
