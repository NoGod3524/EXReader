package org.exreader.s10docs;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.provider.DocumentsContract;

/**
 * Hands the delivered file to the existing import owner exactly as a computer
 * transfer would: an ACTION_VIEW with a granted content URI from this app's
 * real DocumentsProvider. Nothing else is granted and no path is exposed.
 */
public final class S10Sender extends Activity {
    static final String TARGET_PACKAGE = "org.exreader.importprobe";
    static final String TARGET_CLASS = "org.exreader.importprobe.ShareActivity";
    static final String DEFAULT_NAME = "S10-Transfer.epub";

    @Override protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        if (saved != null) { finish(); return; }
        Intent received = getIntent();
        String name = received.getStringExtra("name");
        if (name == null || name.isEmpty()) name = DEFAULT_NAME;
        String type = received.getStringExtra("type");
        if (type == null || type.isEmpty()) type = "application/epub+zip";
        Uri uri = DocumentsContract.buildDocumentUri(S10Provider.AUTHORITY, name);
        Intent out = new Intent(Intent.ACTION_VIEW);
        out.setDataAndType(uri, type);
        out.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
        out.setClassName(TARGET_PACKAGE, TARGET_CLASS);
        startActivity(out);
        finish();
    }
}
