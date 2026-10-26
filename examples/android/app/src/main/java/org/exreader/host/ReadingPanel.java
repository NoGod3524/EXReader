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

/** Low-frequency product reading records. SDK notes remain a separate feature. */
final class ReadingPanel {
    static final class State {final NativeReadingProduct.Page page;final ReadingRequests.Pending pending;final boolean pendingError;State(NativeReadingProduct.Page page,ReadingRequests.Pending pending,boolean pendingError){this.page=page;this.pending=pending;this.pendingError=pendingError;}}
    static final class Action {final int kind,operation;final ReadingRecord target;final ReadingVersion version;final String body;Action(int kind,int operation,ReadingRecord target,ReadingVersion version,String body){this.kind=kind;this.operation=operation;this.target=target;this.version=version;this.body=body;}}
    interface Host {
        void readingList(long book,String after,HostTask task,Consumer<State> done,Consumer<Throwable> failed);
        void readingWrite(long book,Action action,HostTask task,Consumer<NativeReadingProduct.Result> done,Consumer<Throwable> failed);
        void readingResolve(long book,ReadingRecord record,HostTask task,Consumer<NativeReadingSdk.Match> done,Consumer<Throwable> failed);
        void readingHistory(long book,ReadingRecord record,boolean first,HostTask task,Consumer<ReadingHistory.Page> done,Consumer<Throwable> failed);
        void readingRetry(long book,HostTask task,Consumer<NativeReadingProduct.Result> done,Consumer<Throwable> failed);
        void readingDiscard(HostTask task,Runnable done,Consumer<Throwable> failed);
        void navigateReading(long book,NativeReadingSdk.Match match);
        void releaseReading();
    }
    private final Activity activity;private final Host host;private final AtomicLong epoch=new AtomicLong();
    private AlertDialog dialog,choice;private HostTask task;private long book;private boolean busy,hasRange;private String after="";private State state;
    private TextView status;private Button saveProgress,progress,bookmark,highlight,more,previous,cancel,pending;private ListView list;private ArrayAdapter<String> adapter;private ReadingRecord[] rows=new ReadingRecord[0];
    private final ArrayList<String> prior=new ArrayList<>();
    ReadingPanel(Activity activity,Host host){this.activity=activity;this.host=host;}
    private Button button(LinearLayout row,String title,Runnable action){Button button=new Button(activity);button.setText(title);button.setOnClickListener(v->action.run());row.addView(button,new LinearLayout.LayoutParams(0,-2,1));return button;}
    private LinearLayout row(LinearLayout parent){LinearLayout row=new LinearLayout(activity);row.setOrientation(LinearLayout.HORIZONTAL);parent.addView(row);return row;}
    void show(long book,boolean hasRange){
        close();this.book=book;this.hasRange=hasRange;after="";prior.clear();state=null;
        LinearLayout content=new LinearLayout(activity);content.setOrientation(LinearLayout.VERTICAL);int pad=(int)(12*activity.getResources().getDisplayMetrics().density);content.setPadding(pad,pad,pad,pad);
        status=new TextView(activity);status.setContentDescription("阅读记录状态");status.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);content.addView(status);
        LinearLayout save=row(content);saveProgress=button(save,"保存进度",()->write(new Action(NativeReadingProduct.PROGRESS,NativeReadingProduct.PUT,state==null?null:state.page.progress,null,"")));bookmark=button(save,"添加书签",()->edit(null,NativeReadingProduct.BOOKMARK));highlight=button(row(content),"标注选中文本",()->edit(null,NativeReadingProduct.HIGHLIGHT));
        progress=new Button(activity);progress.setContentDescription("已保存进度");progress.setOnClickListener(v->{if(state!=null)detail(state.page.progress);});content.addView(progress,new LinearLayout.LayoutParams(-1,-2));
        list=new ListView(activity);list.setContentDescription("书签与标注列表");adapter=new ArrayAdapter<>(activity,android.R.layout.simple_list_item_1,new ArrayList<>());list.setAdapter(adapter);content.addView(list,new LinearLayout.LayoutParams(-1,(int)(200*activity.getResources().getDisplayMetrics().density)));list.setOnItemClickListener((p,v,position,id)->{if(!busy&&position>=0&&position<rows.length)detail(rows[position]);});
        LinearLayout pages=row(content);previous=button(pages,"上一批",()->{if(!prior.isEmpty()){after=prior.remove(prior.size()-1);load(after);}});more=button(pages,"下一批",()->{if(state!=null&&!state.page.complete){prior.add(after);after=state.page.next;load(after);}});button(row(content),"刷新",()->{after="";prior.clear();load(after);});
        LinearLayout tasks=row(content);cancel=button(tasks,"取消读取",()->{if(task!=null)task.cancel();});pending=button(tasks,"上次保存待确认",this::pending);
        AlertDialog opened=new AlertDialog.Builder(activity).setTitle("阅读记录").setView(content).setNegativeButton("关闭",null).create();dialog=opened;opened.setOnDismissListener(v->{if(dialog==opened)closed();});opened.show();load("");
    }
    private long request(){if(task!=null)task.cancel();long value=epoch.incrementAndGet();task=new HostTask(()->epoch.get()!=value);return value;}
    private boolean current(long request){return dialog!=null&&dialog.isShowing()&&epoch.get()==request;}
    private void message(String text){if(status!=null)status.setText(text);}
    private boolean writable(){return state!=null&&state.pending==null&&!state.pendingError;}
    private void controls(boolean value){busy=value;if(list==null)return;list.setEnabled(!value);boolean safeProgress=state!=null&&!state.page.progress.deleted&&(state.page.progress.state==ReadingRecord.MISSING||state.page.progress.state==ReadingRecord.SAFE);saveProgress.setEnabled(!value&&writable()&&safeProgress);bookmark.setEnabled(!value&&writable());highlight.setEnabled(!value&&writable()&&hasRange);progress.setEnabled(!value&&state!=null);previous.setEnabled(!value&&!prior.isEmpty());more.setEnabled(!value&&state!=null&&!state.page.complete);cancel.setEnabled(value);pending.setVisibility(state!=null&&(state.pending!=null||state.pendingError)?View.VISIBLE:View.GONE);pending.setEnabled(!value);}
    private void failure(long request,Throwable error){if(!current(request))return;controls(false);message(error instanceof HostTask.Cancelled?"已取消，已提交的记录仍保留":error instanceof NativeReadingSdk.Unsupported||error instanceof NativeReadingSdk.Projection?error.getMessage():"未能完成，请刷新或处理上次确认");}
    private void load(String cursor){load(cursor,"");}
    private void load(String cursor,String confirmation){long request=request();controls(true);message("正在读取阅读记录");host.readingList(book,cursor,task,result->activity.runOnUiThread(()->{if(!current(request))return;state=result;rows=result.page.rows;adapter.clear();for(ReadingRecord item:rows)adapter.add(item.label());progress.setText(result.page.progress.label());controls(false);message(confirmation+rows.length+" 条记录"+(result.page.complete?" · 本方向已列完":" · 可继续")+(result.pending!=null||result.pendingError?" · 有待确认保存":""));}),error->activity.runOnUiThread(()->{if(confirmation.isEmpty())failure(request,error);else if(current(request)){controls(false);message(confirmation+(error instanceof HostTask.Cancelled?"列表刷新已取消":"列表刷新失败，请刷新查看"));}}));}
    private void write(Action action){
        if(busy||!writable()){message("请先处理上次保存确认");return;}
        if(action.kind==NativeReadingProduct.PROGRESS&&action.operation==NativeReadingProduct.PUT&&(action.target==null||(action.target.state!=ReadingRecord.MISSING&&action.target.state!=ReadingRecord.SAFE)||action.target.deleted)){message("进度存在冲突或已删除，请明确选择记录处理");return;}
        long request=request();controls(true);message("正在保存阅读记录");host.readingWrite(book,action,task,result->activity.runOnUiThread(()->{if(!current(request))return;controls(false);if(result.saved()){after="";prior.clear();load(after,result.created?"已保存 · ":"已确认保存，没有重复记录 · ");}else message(result.status==4?"记录已变化，请刷新后重新选择":"未能保存，阅读记录未改变");}),error->activity.runOnUiThread(()->failure(request,error)));
    }
    private void edit(ReadingRecord target,int kind){
        if(!writable()){message("请先处理上次保存确认");return;}long stamp=epoch.get();EditText input=new EditText(activity);input.setContentDescription("阅读记录文字");input.setMinLines(2);input.setText(target==null?"":target.body);input.setHint(kind==NativeReadingProduct.BOOKMARK?"书签名称（可选）":"笔记（可选）");input.setFilters(new android.text.InputFilter[]{new android.text.InputFilter.LengthFilter(65536)});
        AlertDialog editor=new AlertDialog.Builder(activity).setTitle(target!=null?"编辑记录文字":kind==NativeReadingProduct.BOOKMARK?"添加书签":"标注选中文本").setView(input).setPositiveButton("保存",null).setNegativeButton("返回",(d,w)->{if(current(stamp))choice=null;}).create();choice=editor;editor.setOnShowListener(d->editor.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v->{if(!current(stamp))return;String text=input.getText().toString();try{ReadingCapture.encode(text,65536);if(text.indexOf('\0')>=0)throw new IllegalArgumentException();}catch(IllegalArgumentException invalid){input.setError("文字太长或包含无法保存的字符");return;}choice=null;editor.dismiss();write(new Action(target==null?kind:NativeReadingProduct.NOTE_TEXT,NativeReadingProduct.PUT,target,null,text));}));editor.show();
    }
    private void detail(ReadingRecord item){
        if(item==null||busy)return;long stamp=epoch.get();if(item.state!=ReadingRecord.SAFE){choice=new AlertDialog.Builder(activity).setTitle(item.label()).setMessage("未选择任何版本，请同步后刷新。").setPositiveButton("返回",null).show();return;}
        if(item.deleted){choice=new AlertDialog.Builder(activity).setTitle("已删除的记录").setItems(new String[]{"选择保留版本恢复"},(d,w)->{if(!current(stamp))return;choice=null;history(item,true);}).setNegativeButton("返回",null).show();return;}
        String[] options=item.kind==ReadingRecord.PROGRESS?new String[]{"跳转到此处","删除"}:new String[]{"跳转到此处","编辑文字","删除"};
        choice=new AlertDialog.Builder(activity).setTitle(item.label()).setItems(options,(d,which)->{if(!current(stamp))return;choice=null;if(which==0)resolve(item);else if(options[which].equals("编辑文字"))edit(item,NativeReadingProduct.NOTE_TEXT);else confirmDelete(item);}).setNegativeButton("返回",null).show();
    }
    private void confirmDelete(ReadingRecord item){long stamp=epoch.get();choice=new AlertDialog.Builder(activity).setTitle("删除此记录？").setMessage("保留版本，可明确选择恢复。").setPositiveButton("删除",(d,w)->{if(!current(stamp))return;choice=null;write(new Action(item.kind==ReadingRecord.PROGRESS?NativeReadingProduct.PROGRESS:item.capture!=null&&item.capture.start==item.capture.end?NativeReadingProduct.BOOKMARK:NativeReadingProduct.HIGHLIGHT,NativeReadingProduct.DELETE,item,null,""));}).setNegativeButton("返回",null).show();}
    private void resolve(ReadingRecord item){
        long request=request();controls(true);message("正在核对记录位置");host.readingResolve(book,item,task,match->activity.runOnUiThread(()->{if(!current(request))return;controls(false);if(!match.found()){message(match.state==NativeReadingSdk.AMBIGUOUS?"位置有歧义，未跳转":match.state==NativeReadingSdk.LEGACY?"旧位置没有可确认选择，未跳转":"位置无法匹配，未跳转");return;}long selected=book;close();host.navigateReading(selected,match);}),error->activity.runOnUiThread(()->failure(request,error)));
    }
    private void history(ReadingRecord item,boolean first){
        long request=request();controls(true);message("正在读取保留版本");host.readingHistory(book,item,first,task,page->activity.runOnUiThread(()->{if(!current(request))return;controls(false);ArrayList<String> labels=new ArrayList<>();for(int i=0;i<page.rows.length;i++)labels.add("版本 "+(i+1)+" · "+page.rows[i].label());if(!page.complete)labels.add("下一批保留版本");if(labels.isEmpty()){message("没有可恢复的保留位置");return;}
            choice=new AlertDialog.Builder(activity).setTitle("明确选择恢复版本").setItems(labels.toArray(new String[0]),(d,which)->{if(!current(request))return;choice=null;if(which==page.rows.length){history(item,false);return;}ReadingVersion version=page.rows[which];long stamp=epoch.get();choice=new AlertDialog.Builder(activity).setTitle("恢复此版本？").setMessage(version.label()).setPositiveButton("恢复",(a,b)->{if(!current(stamp))return;choice=null;int kind=item.kind==ReadingRecord.PROGRESS?NativeReadingProduct.PROGRESS:version.capture.start==version.capture.end?NativeReadingProduct.BOOKMARK:NativeReadingProduct.HIGHLIGHT;write(new Action(kind,NativeReadingProduct.RESTORE,item,version,version.body));}).setNegativeButton("返回",null).show();}).setNegativeButton("返回",null).show();
        }),error->activity.runOnUiThread(()->failure(request,error)));
    }
    private void pending(){
        if(state==null)return;long stamp=epoch.get();String[] actions=state.pendingError?new String[]{"结束确认，不删除已保存记录"}:new String[]{"继续确认保存","结束确认，不删除已保存记录"};choice=new AlertDialog.Builder(activity).setTitle("上次保存待确认").setItems(actions,(d,which)->{if(!current(stamp))return;choice=null;if(!state.pendingError&&which==0){long request=request();controls(true);message("正在确认原请求");host.readingRetry(book,task,result->activity.runOnUiThread(()->{if(!current(request))return;controls(false);if(result.saved())load("","已确认保存 · ");else message("原请求未能保存，请刷新检查记录");}),error->activity.runOnUiThread(()->failure(request,error)));}else{choice=new AlertDialog.Builder(activity).setTitle("结束这次保存确认？").setMessage("已提交的记录会保留。尚未提交的这次请求将不再重试，请刷新检查后再保存。").setPositiveButton("结束确认",(a,b)->{if(!current(stamp))return;choice=null;long request=request();controls(true);host.readingDiscard(task,()->activity.runOnUiThread(()->{if(current(request))load("");}),error->activity.runOnUiThread(()->failure(request,error)));}).setNegativeButton("返回",null).show();}}).setNegativeButton("返回",null).show();
    }
    private void closed(){epoch.incrementAndGet();if(task!=null)task.cancel();task=null;dialog=null;if(choice!=null){choice.dismiss();choice=null;}state=null;rows=new ReadingRecord[0];status=null;host.releaseReading();}
    boolean visible(){return dialog!=null&&dialog.isShowing();}
    void close(){if(dialog==null&&task==null)return;AlertDialog closing=dialog;if(closing!=null){closing.setOnDismissListener(null);closing.dismiss();}closed();}
}
