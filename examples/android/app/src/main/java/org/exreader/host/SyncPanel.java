// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.app.Activity;
import android.app.AlertDialog;
import android.text.InputType;
import android.util.Base64;
import android.view.View;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.TextView;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/** A single More-menu panel; account details stay behind its settings button. */
final class SyncPanel implements SyncController.Listener {
    private final Activity activity;
    private final SyncController controller;
    private final SyncController.Host host;
    private AlertDialog dialog;
    private TextView summary,detail;
    private String[][] viewRows;
    private Button start,cancel,next,refresh;
    private ArrayAdapter<String> adapter;
    private List<NativeSync.RemoteBook> books=new ArrayList<>();
    private String root="",status="就绪";
    private boolean busy;
    SyncPanel(Activity activity,SyncController.Host host){this.activity=activity;this.host=host;controller=SyncController.get(activity);controller.attach(this);}
    private Button button(LinearLayout parent,String label,Runnable action){Button button=new Button(activity);button.setText(label);button.setOnClickListener(view->action.run());parent.addView(button);return button;}
    void show(){
        controller.attach(this);if(dialog!=null&&dialog.isShowing())return;
        LinearLayout panel=new LinearLayout(activity);panel.setOrientation(LinearLayout.VERTICAL);int pad=(int)(16*activity.getResources().getDisplayMetrics().density);panel.setPadding(pad,pad,pad,pad);
        summary=new TextView(activity);summary.setContentDescription("同步状态");summary.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);panel.addView(summary);
        if(BuildConfig.READER_WAVE3){detail=new TextView(activity);detail.setContentDescription("同步状态详情");detail.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);detail.setTextSize(12);panel.addView(detail);}
        button(panel,"云盘账号",this::configure);
        LinearLayout actions=new LinearLayout(activity);panel.addView(actions);
        start=button(actions,"立即同步",()->controller.start(host));cancel=button(actions,"取消同步",controller::cancel);button(actions,"断开",controller::close);
        refresh=button(panel,"刷新书目",()->controller.refresh(""));
        button(panel,"继续更新书架",controller::continueProjection);
        ListView list=new ListView(activity);list.setContentDescription("云盘书目");adapter=new ArrayAdapter<>(activity,android.R.layout.simple_list_item_1,new ArrayList<>());list.setAdapter(adapter);panel.addView(list,new LinearLayout.LayoutParams(-1,(int)(260*activity.getResources().getDisplayMetrics().density)));
        list.setOnItemClickListener((parent,view,position,id)->{if(position>=books.size()||busy)return;NativeSync.RemoteBook book=books.get(position);if(!book.receivable()){new AlertDialog.Builder(activity).setMessage("这本书的同步记录需要先解决冲突或恢复").setPositiveButton("知道了",null).show();return;}new AlertDialog.Builder(activity).setTitle(book.title).setMessage(book.localId>0?"核对原件并保留本机阅读位置":"接收后加入本机书架").setPositiveButton("接收",(value,which)->controller.receive(host,book)).setNegativeButton("取消",null).show();});
        next=button(panel,"下一页",()->{if(!books.isEmpty())controller.refresh(books.get(books.size()-1).key);});
        dialog=new AlertDialog.Builder(activity).setTitle("同步").setView(panel).setNegativeButton("关闭",null).create();dialog.setOnDismissListener(value->{dialog=null;summary=null;detail=null;adapter=null;});dialog.show();render();renderDetail();controller.refresh("");
    }
    private EditText field(LinearLayout panel,String hint,String description,int type){EditText input=new EditText(activity);input.setSingleLine(true);input.setHint(hint);input.setContentDescription(description);input.setInputType(type);input.setSaveEnabled(false);input.setImportantForAutofill(View.IMPORTANT_FOR_AUTOFILL_NO_EXCLUDE_DESCENDANTS);panel.addView(input);return input;}
    private void configure(){
        LinearLayout form=new LinearLayout(activity);form.setOrientation(LinearLayout.VERTICAL);
        EditText address=field(form,"HTTPS 云盘地址（以 / 结尾）","云盘地址",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_URI);address.setText(root);address.setEnabled(root.isEmpty());
        EditText user=field(form,"用户名","云盘用户名",InputType.TYPE_CLASS_TEXT),password=field(form,"密码或应用专用密码","云盘密码",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);
        java.util.function.Consumer<Boolean> save=remember->{String name=user.getText().toString(),value=password.getText().toString();if(name.indexOf(':')>=0||name.indexOf('\r')>=0||name.indexOf('\n')>=0){new AlertDialog.Builder(activity).setMessage("用户名包含不支持的字符").setPositiveButton("知道了",null).show();return;}byte[] pair=(name+":"+value).getBytes(StandardCharsets.UTF_8);byte[] authorization=("Basic "+Base64.encodeToString(pair,Base64.NO_WRAP)).getBytes(StandardCharsets.US_ASCII);Arrays.fill(pair,(byte)0);password.setText("");user.setText("");controller.configure(address.getText().toString().trim(),authorization,remember);Arrays.fill(authorization,(byte)0);};
        AlertDialog settings=new AlertDialog.Builder(activity).setTitle("云盘账号").setView(form).setPositiveButton("安全保存",(value,which)->save.accept(true)).setNeutralButton("仅本次使用",(value,which)->save.accept(false)).setNegativeButton("取消",null).create();settings.show();
        if(!root.isEmpty())button(form,"移除凭据",()->new AlertDialog.Builder(activity).setMessage("移除凭据后需重新输入；书籍和书库绑定保留").setPositiveButton("移除",(value,which)->{controller.forget();settings.dismiss();}).setNegativeButton("取消",null).show());
    }
    private void render(){if(summary==null)return;String message=status+(root.isEmpty()?"":"\n"+root);if(!message.contentEquals(summary.getText()))summary.setText(message);start.setEnabled(!busy);cancel.setEnabled(busy);refresh.setEnabled(!busy);next.setEnabled(!busy&&books.size()==50);adapter.clear();for(NativeSync.RemoteBook book:books)adapter.add(book.label());adapter.notifyDataSetChanged();}
    @Override public void update(String status,String root,List<NativeSync.RemoteBook> rows,boolean busy){this.status=status;this.root=root;this.books=new ArrayList<>(rows);this.busy=busy;render();}
    @Override public void projected(){host.projectionChanged();}
    @Override public void view(String[][] rows){viewRows=rows;renderDetail();}
    private static String phaseLabel(String token){
        switch(token){case "idle":return "就绪（idle）";case "syncing":return "同步中（syncing）";case "cancelling":return "正在取消（cancelling）";case "cancelled":return "已取消，可重试（cancelled）";case "sweep-complete":return "一轮完成（sweep-complete）";case "failed":return "失败，可重试（failed）";case "closing":return "正在关闭（closing）";case "closed":return "已关闭（closed）";default:return "未知（"+token+"）";}
    }
    private static String reasonLabel(String token){
        switch(token){case "none":return "无（none）";case "needs-credentials":return "需要重新输入凭据（needs-credentials）";case "offline":return "离线或无法连接（offline）";case "tls":return "证书校验失败（tls）";case "server":return "服务器返回错误（server）";case "account":return "书库与云盘账号不匹配（account）";case "storage":return "本机存储错误（storage）";case "conflict":return "记录冲突（conflict）";case "integrity":return "完整性校验失败（integrity）";case "limit":return "超出上限（limit）";case "internal":return "内部错误（internal）";default:return "未知（"+token+"）";}
    }
    private void renderDetail(){
        if(detail==null)return;String[][] rows=viewRows;String text;
        if(rows==null)text="同步详情：尚未开始同步，没有可读取的会话";
        else if(rows.length==0)text="同步详情：暂时无法读取，请稍后";
        else{
            String[] s=rows[0];StringBuilder out=new StringBuilder("阶段：").append(phaseLabel(s[0])).append(" · 原因：").append(reasonLabel(s[1]));
            out.append("\n分片 ").append(s[13]).append("/").append(s[14]).append(" · 已完成 ").append(s[7]).append(" 轮（一轮完成不等于整库已同步）");
            out.append("\n操作 ").append(s[8]).append("（上传 ").append(s[9]).append("，下载 ").append(s[10]).append("，原件核对 ").append(s[11]).append("）· 传输 ").append(s[12]).append(" 字节");
            out.append("\n").append("1".equals(s[18])?"待上传记录 "+s[19]+"（重试 "+s[20]+"，冲突 "+s[21]+"）"+("1".equals(s[22])?"，可能还有更多":""):"待上传记录：未读取").append("1".equals(s[17])?"\n可从保留的进度继续":"");
            for(int i=1;i<rows.length;i++)out.append("\n· ").append(rows[i][1]).append(" ").append(rows[i][2]).append(" · ").append(rows[i][3]).append(" 字节 · 尝试 ").append(rows[i][4]).append("1".equals(rows[i][7])?" · 有冲突":"");
            text=out.toString();
        }
        if(!text.contentEquals(detail.getText()))detail.setText(text);
    }
    void background(){if(dialog!=null)dialog.dismiss();controller.detach(this);}
    void close(){background();}
}
