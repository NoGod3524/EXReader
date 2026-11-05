// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.app.Activity;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.widget.ArrayAdapter;
import android.widget.ListView;
import org.json.JSONObject;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;

/** Synthetic platform control. It has no EXReader engine, corpus, or product assertions. */
public final class F08Control extends Activity {
    private final Handler handler=new Handler(Looper.getMainLooper());
    private ShelfWindowMetrics metrics;
    private ListView list;
    private FileOutputStream phases;
    private boolean closed;

    private void record(String phase) {
        try {
            JSONObject value=new JSONObject().put("phase",phase)
                    .put("elapsed_ns",SystemClock.elapsedRealtimeNanos())
                    .put("first_visible",list.getFirstVisiblePosition())
                    .put("last_visible",list.getLastVisiblePosition())
                    .put("children",list.getChildCount());
            phases.write((value.toString()+"\n").getBytes(StandardCharsets.UTF_8));
            phases.flush();
        } catch(Exception error){throw new RuntimeException(error);}
    }
    @Override public void onCreate(Bundle state) {
        long created=SystemClock.elapsedRealtimeNanos();
        super.onCreate(state);
        try {phases=new FileOutputStream(new File(getExternalFilesDir(null),"phases.jsonl"));}
        catch(Exception error){throw new RuntimeException(error);}
        metrics=ShelfWindowMetrics.start(this,created);
        if(metrics==null)throw new IllegalStateException("Metrics must be enabled for the control");
        list=new ListView(this);
        String[] items=new String[2202];
        for(int i=0;i<items.length;i++)items[i]="Platform control row "+i;
        list.setAdapter(new ArrayAdapter<String>(this,android.R.layout.simple_list_item_1,items));
        setContentView(list);
        final int distance=Math.round(48*60*getResources().getDisplayMetrics().density);
        handler.postDelayed(()->{record("forward_start");list.smoothScrollBy(distance,10000);},2000);
        handler.postDelayed(()->{record("forward_end");record("reverse_start");list.smoothScrollBy(-distance,10000);},12500);
        handler.postDelayed(()->record("reverse_end"),23000);
        handler.postDelayed(()->{
            record("complete");
            metrics.close();closed=true;
            try {phases.close();}catch(Exception error){throw new RuntimeException(error);}
        },24500);
    }
    @Override protected void onDestroy() {
        handler.removeCallbacksAndMessages(null);
        if(metrics!=null&&!closed)metrics.close();
        super.onDestroy();
    }
}
