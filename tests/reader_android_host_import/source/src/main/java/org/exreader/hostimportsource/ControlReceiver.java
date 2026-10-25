package org.exreader.hostimportsource;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import java.io.File;

/** {@code am broadcast -n org.exreader.hostimportsource/.ControlReceiver --es cmd open-gate|close-gate|revoke|reset-log}. */
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
                android.net.Uri target = SenderActivity.uriOf(String.valueOf(intent.getStringExtra("doc")));
                context.revokeUriPermission(SenderActivity.TARGET_PACKAGE, target,
                        Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
                context.revokeUriPermission(target, Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
                try (java.io.FileOutputStream out = new java.io.FileOutputStream(new File(context.getFilesDir(), "revoke.log"), true)) {
                    out.write(("revoked " + target + " check="
                            + context.checkUriPermission(target, -1, -1, Intent.FLAG_GRANT_READ_URI_PERMISSION) + "\n").getBytes());
                } catch (java.io.IOException ignored) { }
                break;
            case "reset-log":
                new File(context.getFilesDir(), "opens.log").delete();
                break;
            default:
                break;
        }
    }
}
