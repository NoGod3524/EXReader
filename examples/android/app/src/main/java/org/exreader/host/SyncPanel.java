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
    private TextView summary;
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
        summary=new TextView(activity);summary.setContentDescription("同步状态");panel.addView(summary);
        button(panel,"云盘账号",this::configure);
        LinearLayout actions=new LinearLayout(activity);panel.addView(actions);
        start=button(actions,"立即同步",()->controller.start(host));cancel=button(actions,"取消同步",controller::cancel);button(actions,"断开",controller::close);
        refresh=button(panel,"刷新书目",()->controller.refresh(""));
        ListView list=new ListView(activity);list.setContentDescription("云盘书目");adapter=new ArrayAdapter<>(activity,android.R.layout.simple_list_item_1,new ArrayList<>());list.setAdapter(adapter);panel.addView(list,new LinearLayout.LayoutParams(-1,(int)(260*activity.getResources().getDisplayMetrics().density)));
        list.setOnItemClickListener((parent,view,position,id)->{if(position>=books.size()||busy)return;NativeSync.RemoteBook book=books.get(position);if(!book.receivable()){new AlertDialog.Builder(activity).setMessage("这本书的同步记录需要先解决冲突或恢复").setPositiveButton("知道了",null).show();return;}new AlertDialog.Builder(activity).setTitle(book.title).setMessage(book.localId>0?"核对原件并保留本机阅读位置":"接收后加入本机书架").setPositiveButton("接收",(value,which)->controller.receive(host,book)).setNegativeButton("取消",null).show();});
        next=button(panel,"下一页",()->{if(!books.isEmpty())controller.refresh(books.get(books.size()-1).key);});
        dialog=new AlertDialog.Builder(activity).setTitle("同步").setView(panel).setNegativeButton("关闭",null).create();dialog.setOnDismissListener(value->{dialog=null;summary=null;adapter=null;});dialog.show();render();controller.refresh("");
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
    private void render(){if(summary==null)return;summary.setText(status+(root.isEmpty()?"":"\n"+root));start.setEnabled(!busy);cancel.setEnabled(busy);refresh.setEnabled(!busy);next.setEnabled(!busy&&books.size()==50);adapter.clear();for(NativeSync.RemoteBook book:books)adapter.add(book.label());adapter.notifyDataSetChanged();}
    @Override public void update(String status,String root,List<NativeSync.RemoteBook> rows,boolean busy){this.status=status;this.root=root;this.books=new ArrayList<>(rows);this.busy=busy;render();}
    void background(){if(dialog!=null)dialog.dismiss();controller.detach(this);}
    void close(){background();}
}
