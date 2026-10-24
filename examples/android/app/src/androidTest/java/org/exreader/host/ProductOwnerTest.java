// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteException;
import android.os.Build;
import android.os.Bundle;
import android.os.Process;
import android.util.Log;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.Arrays;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

/** Actual API34 installed-provider/owner and typed command boundaries. */
public final class ProductOwnerTest extends Instrumentation {
    private static final String[] NAMES={"actualInstalledProviderAndJson", "persistedNativeCreateIds",
            "strictUtf16AndEmoji", "staleObservedHeadsAreAtomic", "explicitDeleteAndRestore",
            "metadataFailureRollsBackAndRetries", "outboxFailureRollsBackAndRetries",
            "membershipNeedsExplicitBookBootstrap", "publicSdkBootstrapKeepsCurrentProductTitle",
            "shelfAndSeriesMembershipOrder", "missingAndDeletedDependenciesRefused",
            "mapFailureKeepsSdkAndCommittedBookCommand", "nativeRejectsWrongOwner",
            "nativeRejectsClosedHandle", "twoNativeOwnersCompeteOnOneObservedHead",
            "sdkDatabaseRefusedWithoutModification", "opensClosedLegacySystemCatalog"};
    private interface Check { void run() throws Exception; }
    private Context context;private Bundle arguments;private File directory;private CatalogStore catalog;
    private final JSONArray reports=new JSONArray();private String[] provider;
    @Override public void onCreate(Bundle args){super.onCreate(args);arguments=args;start();}
    @Override public void onStart(){
        context=getTargetContext();String phase=arguments==null?null:arguments.getString("phase");
        if(phase!=null){phase(phase);return;}
        Check[] checks={this::actualInstalledProviderAndJson,this::persistedNativeCreateIds,this::strictUtf16AndEmoji,
                this::staleObservedHeadsAreAtomic,this::explicitDeleteAndRestore,this::metadataFailureRollsBackAndRetries,
                this::outboxFailureRollsBackAndRetries,this::membershipNeedsExplicitBookBootstrap,this::publicSdkBootstrapKeepsCurrentProductTitle,
                this::shelfAndSeriesMembershipOrder,this::missingAndDeletedDependenciesRefused,this::mapFailureKeepsSdkAndCommittedBookCommand,
                this::nativeRejectsWrongOwner,this::nativeRejectsClosedHandle,this::twoNativeOwnersCompeteOnOneObservedHead,
                this::sdkDatabaseRefusedWithoutModification,this::opensClosedLegacySystemCatalog};
        int failed=0;
        for(int i=0;i<checks.length;i++){
            sendStatus(1,status(NAMES[i],i+1));Bundle result=status(NAMES[i],i+1);Throwable failure=null;
            try{directory=new File(context.getCacheDir(),"product-owner-"+i);remove(directory);require(directory.mkdirs(),"owner directory");
                catalog=new CatalogStore(context,new File(directory,"reader-catalog.db"));checks[i].run();}
            catch(Throwable error){failure=error;}
            finally{try{ProductFixture.closeAll();if(catalog!=null)catalog.close();catalog=null;remove(directory);}catch(Throwable error){if(failure==null)failure=error;}}
            if(failure==null){result.putString("stream",".");sendStatus(0,result);}
            else{failed++;result.putString("stack",Log.getStackTraceString(failure));sendStatus(-2,result);}
            try{reports.put(new JSONObject().put("id",NAMES[i]).put("pass",failure==null));}catch(Exception error){failed++;}
        }
        try{
            JSONObject report=new JSONObject().put("source_sha",arguments.getString("source_sha")).put("run_id",arguments.getString("run_id"))
                    .put("attempt",arguments.getString("attempt")).put("api",Build.VERSION.SDK_INT).put("abi",Build.SUPPORTED_ABIS[0])
                    .put("count",checks.length).put("failed",failed).put("checks",reports).put("provider",new JSONArray(Arrays.asList(provider==null?new String[0]:provider)));
            Files.write(new File(context.getFilesDir(),"product-owner-report.json").toPath(),report.toString(2).getBytes(StandardCharsets.UTF_8));
        }catch(Exception error){failed++;Log.e("ProductOwnerTest","Cannot retain owner evidence",error);}
        Bundle result=new Bundle();result.putString("stream",failed==0?"\nOK ("+checks.length+" tests)\n":"\nFAILURES!!! Failures: "+failed);
        finish(failed==0?Activity.RESULT_OK:Activity.RESULT_CANCELED,result);
    }
    private Bundle status(String name,int index){Bundle b=new Bundle();b.putString("id","InstrumentationTestRunner");b.putString("class",getClass().getName());b.putString("test",name);b.putInt("current",index);b.putInt("numtests",NAMES.length);return b;}
    private long owner(){return catalog.nativeOwner();}
    private ProductFixture db(){return ProductFixture.of(catalog);}
    private static String id(int number){return String.format(java.util.Locale.ROOT,"%032x",number);}
    private NativeCatalog.Result group(int revision,String[] heads,int operation,int kind,String key,String name,String parent,long ordinal){
        return NativeCatalog.applyGroup(owner(),id(revision),heads,operation,kind,key,name,parent,ordinal);
    }
    private NativeCatalog.Result tag(int revision,String[] heads,String name){return group(revision,heads,0,1,id(100),name,null,0);}
    private static String[] empty(){return new String[0];}
    private long scalar(String sql){try(Cursor row=db().rawQuery(sql,null)){require(row.moveToFirst(),"scalar row");return row.getLong(0);}}
    private String text(String sql){try(Cursor row=db().rawQuery(sql,null)){require(row.moveToFirst(),"text row");return row.getString(0);}}
    private void counts(long history,long queue,long tags){equal(history,scalar("SELECT count(*) FROM reader_revisions"));equal(queue,scalar("SELECT count(*) FROM reader_outbox"));equal(tags,scalar("SELECT count(*) FROM reader_tags"));}
    private static void ok(NativeCatalog.Result result){equal(0,result.status);}
    private static void refused(NativeCatalog.Result result,int status,int revision){equal(status,result.status);equal(revision,result.revisionStatus);require(!result.created&&!result.applied,"no failed writes");}
    private static void require(boolean value,String reason){if(!value)throw new AssertionError(reason);}
    private static void equal(Object expected,Object actual){require(expected.equals(actual),expected+" != "+actual);}
    private static void equal(long expected,long actual){require(expected==actual,expected+" != "+actual);}
    private static void rejects(Class<? extends Throwable> type,Check check)throws Exception{
        try{check.run();}catch(Throwable error){if(type.isInstance(error))return;throw new AssertionError("Unexpected refusal",error);}throw new AssertionError("Expected "+type.getName());
    }
    private static void remove(File file)throws Exception{if(file==null||!file.exists())return;File[] children=file.listFiles();if(children!=null)for(File child:children)remove(child);require(file.delete(),"delete test file");}
    private void actualInstalledProviderAndJson(){
        provider=NativeCatalog.provider(owner());equal("3.54.0",provider[0]);equal(provider[1],provider[2]);
        require(provider[3].contains("libexreader_product.so"),"actual function belongs to product JNI");
        for(String option:new String[]{"THREADSAFE=1","DQS=0","OMIT_LOAD_EXTENSION","MAX_LENGTH=2147483647"})require(Arrays.asList(provider[4].split(";")).contains(option),"provider option "+option);
        equal(1,scalar("SELECT json_valid('{\"v\":1}',1)"));equal(2,scalar("SELECT count(*) FROM json_tree('[1]')"));
    }
    private void persistedNativeCreateIds(){
        android.content.SharedPreferences prefs=context.getSharedPreferences("owner-create-test",0);require(prefs.edit().clear().commit(),"clear pending IDs");
        String[] first=NativeCatalog.prepareCreate(prefs,"request"),again=NativeCatalog.prepareCreate(prefs,"request");
        require(Arrays.equals(first,again)&&first[0].matches("[0-9a-f]{32}")&&first[1].matches("[0-9a-f]{32}"),"durable native IDs");
        ok(NativeCatalog.applyGroup(owner(),first[0],empty(),0,1,first[1],"Persistent",null,0));
        NativeCatalog.Result retry=NativeCatalog.applyGroup(owner(),first[0],empty(),0,1,first[1],"Persistent",null,0);ok(retry);require(!retry.created&&!retry.applied,"stable no-op");counts(1,1,1);
    }
    private void strictUtf16AndEmoji()throws Exception{
        String value="书架😀E\u0301";ok(tag(1,empty(),value));equal(value,text("SELECT name FROM reader_tags"));
        for(String bad:new String[]{"\ud800","\udc00","\ud800A","A\udc00","A\0B"})rejects(IllegalArgumentException.class,()->tag(2,new String[]{id(1)},bad));
        refused(NativeCatalog.applyBook(owner(),id(2),empty(),0,"txt:"+"a".repeat(64),"txt","a".repeat(64),123,null,"","",false),1,0);
        counts(1,1,1);
    }
    private void staleObservedHeadsAreAtomic(){ok(tag(1,empty(),"First"));ok(tag(2,new String[]{id(1)},"Second"));refused(tag(3,new String[]{id(1)},"Stale"),3,10);counts(2,2,1);equal("Second",text("SELECT name FROM reader_tags"));}
    private void explicitDeleteAndRestore(){
        ok(tag(1,empty(),"First"));ok(group(2,new String[]{id(1)},1,1,id(100),null,null,0));
        refused(tag(3,new String[]{id(2)},"Implicit"),3,10);ok(group(3,new String[]{id(2)},2,1,id(100),"Restored",null,0));equal(0,scalar("SELECT deleted FROM reader_tags"));counts(3,3,1);
    }
    private void fault(String table){
        db().execSQL("CREATE TRIGGER fault BEFORE INSERT ON "+table+" BEGIN SELECT RAISE(ABORT,'owner fault');END");
        refused(tag(1,empty(),"Retry"),3,3);counts(0,0,0);db().execSQL("DROP TRIGGER fault");ok(tag(1,empty(),"Retry"));counts(1,1,1);
    }
    private void metadataFailureRollsBackAndRetries(){fault("reader_tags");}
    private void outboxFailureRollsBackAndRetries(){fault("reader_outbox");}
    private BookStore.VerifiedSource realBook(boolean bootstrap)throws Exception{
        File original=new File(directory,"original.txt");Files.write(original.toPath(),"Public SDK original. Retain bytes and identity.\n".getBytes(StandardCharsets.UTF_8));
        try(BookStore sdk=new BookStore(context,new File(directory,"library.db"))){
            NativeLibrary.ImportResult imported=sdk.importFile(original.getPath(),NativeLibrary.FORMAT_TXT,"SDK original title");
            BookStore.VerifiedSource source=sdk.verifySource(imported.id,null,0,new HostTask(()->false));sdk.finalizeImport(source);
            if(bootstrap)ok(sdk.bootstrapBook(imported.id,id(50),empty(),new HostTask(()->false)));return source;
        }
    }
    private void membershipNeedsExplicitBookBootstrap()throws Exception{
        ok(tag(1,empty(),"Tag"));BookStore.VerifiedSource source=realBook(false);
        refused(NativeCatalog.applyMembership(owner(),id(2),empty(),0,1,id(100),source.key,0),2,12);counts(1,1,1);equal(0,scalar("SELECT count(*) FROM reader_book_tags"));
    }
    private void publicSdkBootstrapKeepsCurrentProductTitle()throws Exception{
        BookStore.VerifiedSource source=realBook(false);db().execSQL("UPDATE reader_books SET title=?,author=?,sort_title=?,favorite=1",new Object[]{"用户 edited 😀","Product author","用户 edited 😀"});
        try(BookStore sdk=new BookStore(context,new File(directory,"library.db"))){ok(sdk.bootstrapBook(source.book.id,id(50),empty(),new HostTask(()->false)));}
        String[] current=NativeCatalog.metadata(owner(),source.key);equal("用户 edited 😀",current[3]);equal("Product author",current[4]);equal("1",current[6]);
        JSONObject payload=new JSONObject(text("SELECT body_json FROM reader_revisions" )).getJSONObject("payload");equal("用户 edited 😀",payload.getString("title"));require(!payload.has("sdk_book_id"),"no device-local ID in wire");
        ok(tag(1,empty(),"Tag"));ok(NativeCatalog.applyMembership(owner(),id(2),empty(),0,1,id(100),source.key,0));equal(1,scalar("SELECT count(*) FROM reader_book_tags"));
    }
    private void shelfAndSeriesMembershipOrder()throws Exception{
        BookStore.VerifiedSource source=realBook(true);
        ok(group(1,empty(),0,0,id(101),"Shelf",null,0));ok(group(2,empty(),0,0,id(102),"Child",id(101),1));ok(group(3,empty(),0,2,id(103),"Series",null,0));
        ok(NativeCatalog.applyMembership(owner(),id(4),empty(),0,0,id(102),source.key,7));ok(NativeCatalog.applyMembership(owner(),id(5),empty(),0,2,id(103),source.key,9));
        equal(7,scalar("SELECT ordinal FROM reader_book_shelves"));equal(9,scalar("SELECT ordinal FROM reader_book_series"));
        refused(group(6,new String[]{id(1)},0,0,id(101),"Cycle",id(102),0),3,3);
    }
    private void missingAndDeletedDependenciesRefused()throws Exception{
        BookStore.VerifiedSource source=realBook(true);ok(tag(1,empty(),"Tag"));ok(group(2,new String[]{id(1)},1,1,id(100),null,null,0));
        refused(NativeCatalog.applyMembership(owner(),id(3),empty(),0,1,id(100),source.key,0),3,10);
        refused(NativeCatalog.applyMembership(owner(),id(3),empty(),0,2,id(103),source.key,0),3,10);equal(3,scalar("SELECT count(*) FROM reader_revisions"));
    }
    private void mapFailureKeepsSdkAndCommittedBookCommand()throws Exception{
        File original=new File(directory,"published.txt");Files.write(original.toPath(),"Committed SDK bytes survive failed product map.".getBytes(StandardCharsets.UTF_8));long sdkId;
        try(BookStore sdk=new BookStore(context,new File(directory,"library.db"))){
            sdkId=sdk.importFile(original.getPath(),NativeLibrary.FORMAT_TXT,"Original").id;
            BookStore.VerifiedSource verified=sdk.verifySource(sdkId,null,0,new HostTask(()->false));ok(sdk.bootstrapBook(sdkId,id(50),empty(),new HostTask(()->false)));
            db().execSQL("CREATE TRIGGER map_fault BEFORE INSERT ON reader_local_books BEGIN SELECT RAISE(ABORT,'map fault');END");
            rejects(SQLiteException.class,()->sdk.finalizeImport(verified));equal(1,sdk.books().size());equal(1,scalar("SELECT count(*) FROM reader_books"));equal(0,scalar("SELECT count(*) FROM reader_local_books"));counts(1,1,0);db().execSQL("DROP TRIGGER map_fault");
        }
        try(BookStore reopened=new BookStore(context,new File(directory,"library.db"))){require(!reopened.metadataRepairPending(),"mapping retry succeeded");equal(sdkId,catalog.localShelfBook(sdkId).sdkBookId);counts(1,1,0);}
    }
    private void nativeRejectsWrongOwner()throws Exception{
        long handle=owner();AtomicReference<Throwable> failure=new AtomicReference<>();Thread other=new Thread(()->{try{NativeCatalog.provider(handle);}catch(Throwable error){failure.set(error);}});
        other.start();other.join(10000);require(!other.isAlive()&&failure.get() instanceof IllegalStateException,"native owner checks bypassing Java facade");NativeCatalog.provider(handle);
    }
    private void nativeRejectsClosedHandle()throws Exception{long handle=owner();catalog.close();catalog=null;rejects(IllegalStateException.class,()->NativeCatalog.provider(handle));rejects(IllegalStateException.class,()->NativeCatalog.close(handle));}
    private void twoNativeOwnersCompeteOnOneObservedHead()throws Exception{
        ok(tag(1,empty(),"First"));CountDownLatch ready=new CountDownLatch(2),go=new CountDownLatch(1);AtomicReference<Throwable> error=new AtomicReference<>();NativeCatalog.Result[] results=new NativeCatalog.Result[2];Thread[] workers=new Thread[2];
        for(int i=0;i<2;i++){final int at=i;workers[i]=new Thread(()->{try(CatalogStore worker=new CatalogStore(context,new File(directory,"reader-catalog.db"))){ready.countDown();require(go.await(20,java.util.concurrent.TimeUnit.SECONDS),"start writer");results[at]=NativeCatalog.applyGroup(worker.nativeOwner(),id(2+at),new String[]{id(1)},0,1,id(100),"Writer "+at,null,0);}catch(Throwable failure){error.compareAndSet(null,failure);}});workers[i].start();}
        require(ready.await(20,java.util.concurrent.TimeUnit.SECONDS),"both native owners opened");go.countDown();for(Thread worker:workers){worker.join(20000);require(!worker.isAlive(),"writer finished");}
        if(error.get()!=null)throw new AssertionError(error.get());equal(1,Arrays.stream(results).filter(v->v.status==0).count());NativeCatalog.Result loser=results[0].status==0?results[1]:results[0];refused(loser,3,10);counts(2,2,1);
    }
    private void sdkDatabaseRefusedWithoutModification()throws Exception{
        realBook(false);File sdk=new File(directory,"library.db");byte[] before=Files.readAllBytes(sdk.toPath());rejects(SQLiteException.class,()->NativeCatalog.open(sdk.getAbsolutePath()));require(Arrays.equals(before,Files.readAllBytes(sdk.toPath())),"SDK bytes unchanged");
    }
    private void opensClosedLegacySystemCatalog()throws Exception{
        BookStore.VerifiedSource source=realBook(false);File file=new File(directory,"closed-legacy.db");
        // This is an offline migration fixture: close the former provider fully
        // before any native product connection touches this particular file.
        try(android.database.sqlite.SQLiteDatabase old=android.database.sqlite.SQLiteDatabase.openDatabase(file.getAbsolutePath(),null,
                android.database.sqlite.SQLiteDatabase.OPEN_READWRITE | android.database.sqlite.SQLiteDatabase.CREATE_IF_NECESSARY
                        | android.database.sqlite.SQLiteDatabase.NO_LOCALIZED_COLLATORS)){
            JSONArray migration=new JSONObject(new String(CatalogStore.readAsset(context),StandardCharsets.UTF_8)).getJSONArray("statements");
            for(int i=0;i<migration.length();i++)old.execSQL(migration.getString(i));
            old.execSQL("INSERT INTO reader_books(book_key,format,source_sha256,source_bytes,title,author,sort_title,favorite) VALUES(?,?,?,?,?,?,?,1)",
                    new Object[]{source.key,source.format,source.sha256,source.bytes,"Legacy user title","Legacy author","Legacy user title"});
            old.execSQL("INSERT INTO reader_local_books VALUES(?,?,?)",new Object[]{source.key,source.book.id,source.location});
        }
        try(CatalogStore migrated=new CatalogStore(context,file)){
            equal("Legacy user title",migrated.localShelfBook(source.book.id).title);
            equal("1",NativeCatalog.metadata(migrated.nativeOwner(),source.key)[6]);
            ok(NativeCatalog.applyGroup(migrated.nativeOwner(),id(900),empty(),0,1,id(901),"After migration 😀",null,0));
            equal(1,NativeCatalog.heads(migrated.nativeOwner(),"tag",id(901)).length);
        }
    }
    private void phase(String phase){
        Bundle result=new Bundle();try{
            boolean before=phase.endsWith("before");directory=new File(context.getFilesDir(),"owner-kill-"+(before?"before":"after"));
            if(phase.startsWith("seed-")){ProductFixture.closeAll();remove(directory);require(directory.mkdirs(),"phase directory");}
            File witness=new File(directory,"witness.txt");if(before&&phase.startsWith("seed-"))ProductFixture.installKill(witness.getAbsolutePath());
            catalog=new CatalogStore(context,new File(directory,"reader-catalog.db"));
            String[] ids=NativeCatalog.prepareCreate(context.getSharedPreferences("owner-kill-ids",0),before?"before":"after");
            if(phase.startsWith("seed-")){
                if(before)db().execSQL("CREATE TRIGGER kill_metadata BEFORE INSERT ON reader_tags BEGIN SELECT reader_test_kill();END");
                ok(NativeCatalog.applyGroup(owner(),ids[0],empty(),0,1,ids[1],"Killed 😀",null,0));
                require(!before,"before-commit boundary actually killed");counts(1,1,1);Files.write(witness.toPath(),"1,1,1".getBytes(StandardCharsets.UTF_8));Process.killProcess(Process.myPid());throw new AssertionError("real kill required");
            }
            require(phase.startsWith("recover-"),"known phase");equal(before?"1,1,0":"1,1,1",new String(Files.readAllBytes(witness.toPath()),StandardCharsets.UTF_8));
            if(before){db().execSQL("DROP TRIGGER kill_metadata");counts(0,0,0);}else counts(1,1,1);
            NativeCatalog.Result retried=NativeCatalog.applyGroup(owner(),ids[0],empty(),0,1,ids[1],"Killed 😀",null,0);ok(retried);require(retried.created==before&&retried.applied==before,"exact retry result");counts(1,1,1);equal("Killed 😀",text("SELECT name FROM reader_tags"));
            ProductFixture.closeAll();catalog.close();catalog=null;result.putString("stream","EXR_OWNER_RECOVERED "+phase+"\n");finish(Activity.RESULT_OK,result);
        }catch(Throwable error){result.putString("shortMsg","EXR_OWNER_PHASE_FAILED "+error);finish(Activity.RESULT_CANCELED,result);}
    }
}
