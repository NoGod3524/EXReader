// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.app.Activity;
import android.app.AlertDialog;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import java.util.concurrent.atomic.AtomicLong;

/** One low-frequency modal panel. A stale callback after cancel, close, rotation or Activity exit is dropped. */
abstract class Wave3Dialog {
    final Activity activity;final Wave3Host host;private final AtomicLong epoch=new AtomicLong();
    AlertDialog dialog;HostTask task;TextView status;LinearLayout content;
    Wave3Dialog(Activity activity,Wave3Host host){this.activity=activity;this.host=host;}
    final int dp(int value){return (int)(value*activity.getResources().getDisplayMetrics().density);}
    final Button button(LinearLayout parent,String label,Runnable action){
        Button button=new Button(activity);button.setText(label);button.setOnClickListener(view->action.run());parent.addView(button,new LinearLayout.LayoutParams(0,-2,1));return button;
    }
    final LinearLayout row(){LinearLayout row=new LinearLayout(activity);row.setOrientation(LinearLayout.HORIZONTAL);content.addView(row);return row;}
    /** Subclasses fill {@link #content} with their controls. */
    abstract void build();
    void released() {}
    final void open(String title,String statusDescription) {
        close();
        content=new LinearLayout(activity);content.setOrientation(LinearLayout.VERTICAL);content.setPadding(dp(12),dp(12),dp(12),dp(12));
        status=new TextView(activity);status.setContentDescription(statusDescription);status.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);content.addView(status);
        build();
        ScrollView scroll=new ScrollView(activity);scroll.addView(content);
        AlertDialog opened=new AlertDialog.Builder(activity).setTitle(title).setView(scroll).setNegativeButton("关闭",null).create();
        dialog=opened;opened.setOnDismissListener(view->{if(dialog==opened)closed();});opened.show();
    }
    final long request() {
        if(task!=null)task.cancel();
        final long value=epoch.incrementAndGet();task=new HostTask(()->epoch.get()!=value);return value;
    }
    final boolean current(long value){return dialog!=null&&dialog.isShowing()&&epoch.get()==value;}
    final void post(long value,Runnable action){activity.runOnUiThread(()->{if(current(value))action.run();});}
    /** Resource-bearing results must release on rejection, even after a panel is closed. */
    final void post(long value,Runnable action,Runnable stale){activity.runOnUiThread(()->{if(current(value))action.run();else stale.run();});}
    final void message(String text){if(status!=null)status.setText(text);}
    final void cancelTask(){if(task!=null)task.cancel();}
    private void closed() {
        epoch.incrementAndGet();if(task!=null)task.cancel();task=null;dialog=null;status=null;content=null;released();
    }
    final boolean visible(){return dialog!=null&&dialog.isShowing();}
    final void close() {
        if(dialog==null&&task==null)return;
        AlertDialog closing=dialog;
        if(closing!=null){closing.setOnDismissListener(null);closing.dismiss();}
        closed();
    }
    static String reason(Throwable error) {
        if(error instanceof HostTask.Cancelled)return "已取消；已提交的内容保留";
        String text=error.getMessage();return text==null||text.isEmpty()?error.getClass().getSimpleName():text;
    }
}
