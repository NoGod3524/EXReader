package org.exreader.hostimportsource;

import android.app.Activity;
import android.content.ClipData;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.provider.DocumentsContract;
import java.util.ArrayList;

/**
 * {@code am start -n org.exreader.hostimportsource/.SenderActivity --es mode view|send|multi --es docs a,b}.
 * Delivers a real ACTION_VIEW / SEND / SEND_MULTIPLE with a read grant to the probe importer.
 */
public final class SenderActivity extends Activity {
    static final String TARGET_PACKAGE = "org.exreader.host";
    static final String TARGET_CLASS = "org.exreader.host.MainActivity";

    static Uri uriOf(String id) { return DocumentsContract.buildDocumentUri(SourceProvider.AUTHORITY, id); }

    @Override protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        String mode = getIntent().getStringExtra("mode");
        String[] ids = String.valueOf(getIntent().getStringExtra("docs")).split(",");
        String[] first = SourceProvider.find(ids[0]);
        Intent out;
        if ("multi".equals(mode)) {
            ArrayList<Uri> uris = new ArrayList<>();
            for (String id : ids) uris.add(uriOf(id));
            out = new Intent(Intent.ACTION_SEND_MULTIPLE).setType("*/*");
            out.putParcelableArrayListExtra(Intent.EXTRA_STREAM, uris);
            out.setClipData(clip(ids));
        } else if ("send".equals(mode)) {
            out = new Intent(Intent.ACTION_SEND).setType(first[2]);
            out.putExtra(Intent.EXTRA_STREAM, uriOf(ids[0]));
            out.setClipData(clip(ids));
        } else {
            out = new Intent(Intent.ACTION_VIEW).setDataAndType(uriOf(ids[0]), first[2]);
        }
        out.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK)
                .setClassName(TARGET_PACKAGE, TARGET_CLASS);
        if(getIntent().hasExtra("pause"))out.putExtra("exr_review",true).putExtra("review_pause",getIntent().getStringExtra("pause"));
        startActivity(out);
        finish();
    }

    private static ClipData clip(String[] ids) {
        ClipData clip = ClipData.newRawUri("docs", uriOf(ids[0]));
        for (int i = 1; i < ids.length; i++) clip.addItem(new ClipData.Item(uriOf(ids[i])));
        return clip;
    }
}
