// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.widget.Button;
import android.widget.LinearLayout;

/** Back/forward over real landings. A target is peeked, resolved to a public FOUND, navigated, and only then completed. */
final class JumpPanel extends Wave3Dialog {
    private long book;private Button back,forward,cancel;private boolean busy;
    JumpPanel(android.app.Activity activity,Wave3Host host){super(activity,host);}
    @Override void build() {
        LinearLayout actions=row();
        back=button(actions,"返回上一位置",()->move(NativeWave3.BACK));forward=button(actions,"前进到下一位置",()->move(NativeWave3.FORWARD));
        cancel=button(row(),"取消",this::cancelTask);
    }
    private void controls(boolean value,NativeWave3.State state) {
        busy=value;if(back==null)return;
        back.setEnabled(!value&&state!=null&&state.back);forward.setEnabled(!value&&state!=null&&state.forward);cancel.setEnabled(value);
    }
    void show(long selected) {
        book=selected;open("位置历史","位置历史状态");controls(true,null);message("正在读取位置历史");refresh("");
    }
    private void refresh(String note) {
        long stamp=request();
        host.jumpState(task,state->post(stamp,()->{controls(false,state);message(state.label()+(note.isEmpty()?"":"。"+note));}),
            error->post(stamp,()->{controls(false,null);message("位置历史暂不可用："+reason(error));}));
    }
    private void move(int direction) {
        if(busy)return;
        long stamp=request();controls(true,null);message(direction==NativeWave3.BACK?"正在核对上一位置":"正在核对下一位置");
        host.jumpMove(book,direction,task,result->post(stamp,()->{
            if(result.status==NativeWave3.JH_EMPTY){refresh(direction==NativeWave3.BACK?"没有更早的位置":"没有更晚的位置");return;}
            if(!result.navigable()) {
                host.dropJump(result);
                String why=result.match==null?"位置历史条目不可用":result.match.state==NativeReadingSdk.AMBIGUOUS?"位置有歧义，未移动":"位置无法确认，未移动";
                refresh(why);return;
            }
            long selected=book;close();host.navigateJump(selected,result);
        },()->host.dropJump(result)),error->post(stamp,()->{controls(false,null);message(error instanceof HostTask.Cancelled?"已取消，位置未移动":"未能移动，位置未改变："+reason(error));}));
    }
}
