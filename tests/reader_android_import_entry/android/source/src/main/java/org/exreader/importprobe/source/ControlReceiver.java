package org.exreader.importprobe.source;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import java.io.File;

/** {@code am broadcast -n org.exreader.importprobe.source/.ControlReceiver --es cmd open-gate|close-gate|revoke|reset-log}. */
public final class ControlReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent intent) {
        String cmd = String.valueOf(intent.getStringExtra("cmd"));
        switch (cmd) {
            case "open-gate":
                synchronized (SourceProvider.GATE) { SourceProvider.gateOpen = true; SourceProvider.GATE.notifyAll(); }
                break;
            case "close-gate":
                synchronized (SourceProvider.GATE) { SourceProvider.gateOpen = false; }
                break;
            case "revoke":
                context.revokeUriPermission(SenderActivity.TARGET_PACKAGE,
                        SenderActivity.uriOf(String.valueOf(intent.getStringExtra("doc"))),
                        Intent.FLAG_GRANT_READ_URI_PERMISSION);
                break;
            case "reset-log":
                new File(context.getFilesDir(), "opens.log").delete();
                break;
            default:
                break;
        }
    }
}
