// SPDX-License-Identifier: MIT
package org.exreader.webdav.probe;
import android.app.Activity;
import android.os.Bundle;
import java.io.File;
import java.nio.file.Files;
import java.nio.charset.StandardCharsets;
import org.json.JSONObject;

/** Fixture host: the worker owns all clients and survives this Activity's exit. */
public final class ExitActivity extends Activity {
    static volatile JSONObject input;
    static volatile File directory;
    static volatile boolean done,destroyed;
    static volatile Throwable failure;
    @Override public void onCreate(Bundle saved){
        super.onCreate(saved);destroyed=false;
        // The instrumentation class is loaded by its own loader; invoke its helper through
        // an injected Runnable for the normal exit case. The process-kill case has a main helper.
        if(task!=null){new Thread(task,"dav-exit-worker").start();finish();}
        else {new Thread(()->{try{ProcessProbe.run(getFilesDir());}catch(Throwable error){failure=error;}finally{done=true;}},"dav-process-worker").start();finish();}
    }
    static volatile Runnable task;
    @Override public void onDestroy(){super.onDestroy();destroyed=true;}
}
