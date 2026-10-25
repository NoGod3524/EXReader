// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.content.Context;
import android.content.Intent;
import android.os.Handler;
import android.os.Looper;
import java.io.File;
import java.util.ArrayList;
import java.util.List;
import java.util.HashSet;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.exreader.importentry.ImportEntry;
import org.exreader.importentry.ImportError;
import org.exreader.importentry.ImportOwner;
import org.exreader.importentry.ImportTicket;
import org.exreader.importentry.ReadyRequest;

/** Process-scoped staging; the attached Activity remains the sole SDK owner. */
final class ImportController implements ImportOwner {
    private static ImportController instance;
    static synchronized ImportController get(Context context) {
        if (instance == null) instance = new ImportController(context.getApplicationContext());
        return instance;
    }
    private final Handler main = new Handler(Looper.getMainLooper());
    private final ExecutorService files = Executors.newSingleThreadExecutor(r -> new Thread(r,"exr-import-files"));
    private final List<Intent> waiting = new ArrayList<>();
    private final List<ReadyRequest> pending = new ArrayList<>();
    private final List<ImportTicket> tickets = new ArrayList<>();
    private final Set<ImportTicket> discardReady = new HashSet<>();
    private ImportEntry entry;
    private MainActivity owner, runningOwner;
    private ReadyRequest running;
    private boolean blocked;
    private String failure;

    private ImportController(Context context) {
        files.execute(() -> {
            try {
                ImportEntry opened = ImportEntry.create(context, new File(context.getFilesDir(),"incoming"), main::post, this);
                List<ReadyRequest> recovered = opened.pendingReady();
                main.post(() -> {
                    entry = opened; pending.addAll(recovered);
                    for (Intent intent : waiting) tickets.addAll(entry.submit(intent));
                    waiting.clear(); notifyCopying(); pump();
                });
            } catch (Exception error) {
                main.post(() -> { failure="Import staging unavailable"; waiting.clear(); notifyCopying(); notifyStatus(failure); });
            }
        });
    }
    void attach(MainActivity activity) { owner=activity; blocked=false; notifyCopying(); if(failure!=null)notifyStatus(failure); pump(); }
    void detach(MainActivity activity) { if(owner==activity)owner=null; }
    void submit(Intent intent) {
        if(failure!=null){notifyStatus(failure);return;}
        blocked=false;
        if(entry==null) {
            if(waiting.size()>=8){notifyStatus("Import queue is full");return;}
            waiting.add(new Intent(intent));
        } else tickets.addAll(entry.submit(intent));
        notifyCopying();
        notifyStatus("Copying selected books to private storage…");
        pump();
    }
    void cancelStaging() {
        for(ImportTicket ticket:tickets)if(!ticket.cancel()&&ticket.state()==ImportTicket.State.COMMITTED)discardReady.add(ticket);
        waiting.clear();
        for(ReadyRequest request:new ArrayList<>(pending))if(request!=running){
            pending.remove(request);files.execute(()->entry.release(request));
        }
        notifyCopying();
    }
    boolean isCopying() { return !waiting.isEmpty()||!tickets.isEmpty(); }
    void retry() { blocked=false; pump(); }
    void pump() {
        if(owner==null||entry==null||running!=null||blocked||pending.isEmpty())return;
        ReadyRequest next=pending.get(0);
        // Mark first: a fast owner may report completion before this call returns.
        running=next;runningOwner=owner;
        if(!owner.importReady(next)){running=null;runningOwner=null;}
    }
    /** Always posted independently of the old Activity's UI/lifecycle filter. */
    void completed(MainActivity activity,ReadyRequest request,boolean release,boolean retry) {
        main.post(() -> {
            if(running!=request||runningOwner!=activity)return;
            running=null;runningOwner=null;
            if(release){pending.remove(request);files.execute(()->entry.release(request));}
            else if(!retry)blocked=true;
            // A lifecycle cancellation waits for a different, live owner.
            if(retry&&owner==activity)return;
            pump();
        });
    }
    @Override public void onReady(ImportTicket ticket,ReadyRequest request) {
        tickets.remove(ticket);
        if(discardReady.remove(ticket)){files.execute(()->entry.release(request));notifyStatus("Import canceled");}
        else pending.add(request);
        notifyCopying();pump();
    }
    @Override public void onFailed(ImportTicket ticket,ImportError error) {
        tickets.remove(ticket);discardReady.remove(ticket);notifyCopying();
        notifyStatus(error.code()==ImportError.Code.CANCELLED?"Import canceled":"Import failed: "+error.code());pump();
    }
    private void notifyCopying(){if(owner!=null)owner.importCopying(isCopying());}
    private void notifyStatus(String text){if(owner!=null)owner.importStatus(text);}
}
