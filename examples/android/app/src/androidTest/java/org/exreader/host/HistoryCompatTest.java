// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.os.Build;
import android.os.Bundle;
import android.util.Log;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.Arrays;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.json.JSONArray;
import org.json.JSONObject;

/** Separate diagnostics for the old empty-bootstrap contract in an installed API34 host. */
public final class HistoryCompatTest extends Instrumentation {
    private Bundle arguments;
    private final JSONArray observations=new JSONArray();
    private static HostTask task(){return new HostTask(()->false);}
    private static void need(boolean ok,String message){if(!ok)throw new AssertionError(message);}
    private void record(String name,NativeCatalog.Result result)throws Exception{
        JSONObject row=new JSONObject().put("name",name).put("pass",true);
        if(result!=null)row.put("status",result.status).put("revision_status",result.revisionStatus)
            .put("created",result.created).put("applied",result.applied).put("revision",result.revisionId).put("message",result.message);
        observations.put(row);
    }
    private static void refused(NativeCatalog.Result result){need(result.status==3&&result.revisionStatus==10&&!result.created&&!result.applied,"native stale history remains refused: "+result.status+"/"+result.revisionStatus);}
    @Override public void onCreate(Bundle args){super.onCreate(args);arguments=args;start();}
    @Override public void onStart(){
        Context context=getTargetContext();Throwable failure=null;
        try{
            File directory=new File(context.getCacheDir(),"history-compat-"+NativeCatalog.newId());need(directory.mkdirs(),"private directory");
            File original=new File(directory,"original.txt"),database=new File(directory,"library.db");
            Files.write(original.toPath(),("Original bootstrap identity "+directory.getName()+"\n").getBytes(StandardCharsets.UTF_8));
            NativeAdmission.initialize(context,database,NativeAdmission.CREATE);
            long book;String key,automatic;String[] observed;
            try(BookStore store=new BookStore(context,database)){
                book=store.importFile(original.getPath(),NativeLibrary.FORMAT_TXT,"Compatibility original").id;
                BookStore.VerifiedSource source=store.verifySource(book,null,0,task());key=source.key;
                need(NativeCatalog.heads(store.productOwner(),"book",key).length==0,"import before finalize has no history");
                store.finalizeImport(source);observed=NativeCatalog.heads(store.productOwner(),"book",key);
                automatic=context.getSharedPreferences("sync-requests",0).getString("book-"+key+".revision",null);
                need(observed.length==1&&observed[0].equals(automatic),"finalize creates persisted auto root before legacy bootstrap");record("actual_import_then_finalize_order",null);
                NativeCatalog.Result strict=NativeCatalog.applyBook(store.productOwner(),NativeCatalog.newId(),new String[0],0,key,source.format,source.sha256,source.bytes,source.book.title,source.book.author,source.book.title,false);
                refused(strict);record("native_empty_expected_reproduces_old_refusal",strict);
                String requested=NativeCatalog.newId();NativeCatalog.Result compatible=store.bootstrapBook(book,requested,new String[0],task());
                need(compatible.status==0&&!compatible.created&&!compatible.applied&&automatic.equals(compatible.revisionId),"compatibility is actual native idempotent replay");
                need(!NativeCatalog.retained(store.productOwner(),requested)&&Arrays.equals(observed,NativeCatalog.heads(store.productOwner(),"book",key)),"no phantom caller revision or history rewrite");record("legacy_bootstrap_reuses_exact_auto_fact",compatible);
            }
            try(BookStore store=new BookStore(context,database)){
                NativeCatalog.Result replay=store.bootstrapBook(book,NativeCatalog.newId(),new String[0],task());
                need(replay.status==0&&!replay.created&&!replay.applied&&automatic.equals(replay.revisionId),"reopen preserves no-op contract");record("reopen_keeps_auto_fact",replay);
                NativeCatalog.Result explicit=store.bootstrapBook(book,NativeCatalog.newId(),observed,task());
                need(explicit.status==0&&explicit.created&&explicit.applied,"explicit observed-head command remains a real edit");record("explicit_observed_head_still_commits",explicit);
                NativeCatalog.Result stale=store.bootstrapBook(book,NativeCatalog.newId(),new String[0],task());refused(stale);record("empty_expected_cannot_adopt_newer_history",stale);
                stale=store.bootstrapBook(book,NativeCatalog.newId(),observed,task());refused(stale);record("stale_explicit_head_stays_refused",stale);
                observed=NativeCatalog.heads(store.productOwner(),"book",key);
            }
            final long bookId=book;final String[] parents=observed;final String bookKey=key;
            CountDownLatch ready=new CountDownLatch(2),go=new CountDownLatch(1);
            AtomicReference<Throwable> error=new AtomicReference<>();NativeCatalog.Result[] results=new NativeCatalog.Result[2];Thread[] workers=new Thread[2];
            for(int i=0;i<2;i++){final int at=i;workers[i]=new Thread(()->{try(BookStore store=new BookStore(context,database)){
                ready.countDown();need(go.await(20,TimeUnit.SECONDS),"concurrent start");results[at]=store.bootstrapBook(bookId,NativeCatalog.newId(),parents,task());
            }catch(Throwable thrown){error.compareAndSet(null,thrown);}});workers[i].start();}
            need(ready.await(20,TimeUnit.SECONDS),"both actual owners opened");go.countDown();
            for(Thread worker:workers){worker.join(20000);need(!worker.isAlive(),"bounded concurrent owner completion");}
            if(error.get()!=null)throw new AssertionError(error.get());
            need(Arrays.stream(results).filter(r->r.status==0).count()==1,"only one concurrent owner wins");
            NativeCatalog.Result loser=results[0].status==0?results[1]:results[0];refused(loser);
            try(BookStore store=new BookStore(context,database)){need(NativeCatalog.heads(store.productOwner(),"book",bookKey).length==1,"concurrent history keeps one winning head");}
            record("two_real_owners_cannot_overwrite_observed_history",loser);
        }catch(Throwable error){failure=error;Log.e("HistoryCompatTest","Compatibility check failed",error);}
        try{
            JSONObject report=new JSONObject().put("source_sha",arguments.getString("source_sha")).put("run_id",arguments.getString("run_id"))
                .put("attempt",arguments.getString("attempt")).put("api",Build.VERSION.SDK_INT).put("physical_device",false)
                .put("passed",failure==null).put("observations",observations).put("failure",failure==null?"":Log.getStackTraceString(failure));
            Files.write(new File(context.getFilesDir(),"history-compat-report.json").toPath(),report.toString(2).getBytes(StandardCharsets.UTF_8));
        }catch(Exception error){failure=error;}
        Bundle result=new Bundle();result.putString("stream",failure==null?"OK (8 compatibility observations)":"FAILURES "+Log.getStackTraceString(failure));
        finish(failure==null?Activity.RESULT_OK:Activity.RESULT_CANCELED,result);
    }
}
