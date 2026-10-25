package org.exreader.importprobe.source;

import android.app.Activity;
import android.content.ClipData;
import android.content.Intent;
import android.os.Bundle;

/** A self-built OPEN_DOCUMENT picker: returns three documents with read grants through the activity result. */
public final class PickerActivity extends Activity {
    @Override protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        ClipData clip = ClipData.newRawUri("picked", SenderActivity.uriOf("txt-seekable"));
        clip.addItem(new ClipData.Item(SenderActivity.uriOf("epub")));
        clip.addItem(new ClipData.Item(SenderActivity.uriOf("pdf")));
        Intent data = new Intent().setData(SenderActivity.uriOf("txt-seekable"));
        data.setClipData(clip);
        data.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        setResult(RESULT_OK, data);
        finish();
    }
}
