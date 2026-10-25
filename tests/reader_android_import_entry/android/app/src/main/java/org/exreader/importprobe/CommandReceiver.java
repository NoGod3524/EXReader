package org.exreader.importprobe;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** adb-driven control: {@code am broadcast -n org.exreader.importprobe/.CommandReceiver --es cmd status}. */
public final class CommandReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent intent) {
        ProbeHost host = ProbeHost.get(context);
        String cmd = intent.getStringExtra("cmd");
        if (cmd == null) return;
        if ("wrong-thread".equals(cmd)) host.wrongThread();
        else host.command(cmd, intent.getStringExtra("arg"));
    }
}
