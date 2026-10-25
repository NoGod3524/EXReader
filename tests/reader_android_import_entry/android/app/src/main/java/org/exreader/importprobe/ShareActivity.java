package org.exreader.importprobe;

import android.app.Activity;
import android.content.ComponentName;
import android.content.Intent;
import android.os.Bundle;
import android.widget.TextView;
import org.exreader.importentry.ImportEntry;

/** Receives VIEW / SEND / SEND_MULTIPLE and picker results exactly as a host Activity would. */
public final class ShareActivity extends Activity {
    private static final int PICK = 7;

    @Override protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        TextView view = new TextView(this);
        view.setText("importprobe");
        setContentView(view);
        ProbeHost host = ProbeHost.get(this);
        host.log("activity-create", "orientation", getResources().getConfiguration().orientation,
                "restored", saved != null, "action", String.valueOf(getIntent().getAction()));
        // A recreated Activity (rotation) must not resubmit the intent it already handed over.
        if (saved == null) dispatch(getIntent(), host);
    }

    @Override protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        dispatch(intent, ProbeHost.get(this));
    }

    private void dispatch(Intent intent, ProbeHost host) {
        if (intent.getBooleanExtra("pick", false)) {
            Intent picker = ImportEntry.pickerIntent(true)
                    .setComponent(new ComponentName("org.exreader.importprobe.source", "org.exreader.importprobe.source.PickerActivity"));
            startActivityForResult(picker, PICK);
        } else host.submit(intent);
    }

    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        ProbeHost host = ProbeHost.get(this);
        host.log("picker-result", "ok", result == RESULT_OK);
        if (request == PICK && result == RESULT_OK && data != null) host.submit(data);
    }

    @Override protected void onDestroy() {
        ProbeHost.get(this).log("activity-destroy", "changingConfig", isChangingConfigurations());
        super.onDestroy();
    }
}
