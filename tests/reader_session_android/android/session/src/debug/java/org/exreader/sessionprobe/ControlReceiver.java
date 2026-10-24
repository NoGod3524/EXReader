// SPDX-License-Identifier: MIT
package org.exreader.sessionprobe;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
public final class ControlReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context,Intent intent){SessionController.get(context).request(intent.getIntExtra("request_id",0),goAsync());}
}
