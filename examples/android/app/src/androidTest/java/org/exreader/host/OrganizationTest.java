// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.database.Cursor;
import android.os.Build;
import android.os.Bundle;
import android.util.Log;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

/** Installed-provider snapshots, exact durable intents and UI fixture phases. */
public final class OrganizationTest extends Instrumentation {
    static final String[] NAMES={"completeUnicodeIntentBeforeWrite","staleRefusalRetainsExactRequest","bootstrapKeepsCurrentUserFields",
        "partialBootstrapSurvivesMembershipRefusal","legacyMetadataChangeRefusesBootstrap","lateCancelPreservesCommittedOutcome",
        "groupAndRemovedKeysetsStayBounded","membershipDeleteRequiresExplicitRestore"};
    interface Check { void run() throws Exception; }
    private Context context;private Bundle arguments;private File directory;private BookStore books;
    private final JSONArray reports=new JSONArray();
    @Override public void onCreate(Bundle args){super.onCreate(args);arguments=args;start();}
    @Override public void onStart(){
        context=getTargetContext();String phase=arguments==null?null:arguments.getString("phase");if(phase!=null){phase(phase);return;}
        Check[] checks={this::completeUnicodeIntentBeforeWrite,this::staleRefusalRetainsExactRequest,this::bootstrapKeepsCurrentUserFields,
            this::partialBootstrapSurvivesMembershipRefusal,this::legacyMetadataChangeRefusesBootstrap,this::lateCancelPreservesCommittedOutcome,
            this::groupAndRemovedKeysetsStayBounded,this::membershipDeleteRequiresExplicitRestore};
        int failed=0;
        for(int i=0;i<checks.length;i++){
            sendStatus(1,status(i));Throwable failure=null;
            try { clearJournal();directory=new File(context.getCacheDir(),"organization-"+i);remove(directory);require(directory.mkdirs(),"directory");
                books=new BookStore(context,new File(directory,"library.db"));checks[i].run(); }
            catch(Throwable error){failure=error;}
            finally { try { ProductFixture.closeAll();if(books!=null)books.close();books=null;remove(directory);clearJournal(); }
                catch(Throwable error){if(failure==null)failure=error;} }
            Bundle result=status(i);
            if(failure==null){result.putString("stream",".");sendStatus(0,result);}else{failed++;result.putString("stack",Log.getStackTraceString(failure));sendStatus(-2,result);}
            try{reports.put(new JSONObject().put("id",NAMES[i]).put("pass",failure==null));}catch(Exception error){failed++;}
        }
        try { write(new File(context.getFilesDir(),"organization-report.json"),identity().put("count",checks.length).put("failed",failed).put("checks",reports)
            .put("api",Build.VERSION.SDK_INT).put("abi",Build.SUPPORTED_ABIS[0])); }catch(Exception error){failed++;}
        Bundle result=new Bundle();result.putString("stream",failed==0?"\nOK (8 tests)\n":"\nFAILURES!!! "+failed);
        finish(failed==0?Activity.RESULT_OK:Activity.RESULT_CANCELED,result);
    }
    private Bundle status(int index){Bundle b=new Bundle();b.putString("id","InstrumentationTestRunner");b.putString("class",getClass().getName());b.putString("test",NAMES[index]);b.putInt("numtests",NAMES.length);b.putInt("current",index+1);return b;}
    private JSONObject identity()throws Exception{return new JSONObject().put("source_sha",arguments.getString("source_sha")).put("run_id",arguments.getString("run_id")).put("attempt",arguments.getString("attempt"));}
    private void clearJournal(){require(context.getSharedPreferences("organization",0).edit().clear().commit(),"clear journal");}
    private static void require(boolean value,String message){if(!value)throw new AssertionError(message);}
    private static String id(int n){return String.format(java.util.Locale.ROOT,"%032x",n);}
    private HostTask task(){return new HostTask(()->false);}
    private long owner(){return books.productOwner();}
    private OrganizationStore store(){return books.organization();}
    private ProductFixture db(){return ProductFixture.open(new File(directory,"reader-catalog.db"));}
    private long count(String table){try(Cursor c=db().rawQuery("SELECT count(*) FROM "+table,null)){require(c.moveToFirst(),"count");return c.getLong(0);}}
    private void group(int n,int kind,String name,String parent,long ordinal){NativeCatalog.Result r=NativeCatalog.applyGroup(owner(),id(10000+n),new String[0],0,kind,id(n),name,parent,ordinal);require(r.status==0,"group command");}
    private CatalogStore.ShelfBook book(String title)throws Exception{
        File source=new File(directory,title+".txt");Files.write(source.toPath(),("Public original "+title).getBytes(StandardCharsets.UTF_8));
        long sdk=books.importFile(source.getPath(),NativeLibrary.FORMAT_TXT,title).id;
        books.finalizeImport(books.verifySource(sdk,null,0,task()));return books.localShelfBook(sdk);
    }
    private void completeUnicodeIntentBeforeWrite()throws Exception{
        IntentJournal.Command c=IntentJournal.Command.group(0,0,NativeCatalog.newId(),"书架😀E\u0301",id(90),19,new String[]{id(8),id(7)});
        store().journal.create(c,null);IntentJournal.Pending p=store().journal.read();
        require(p.command.json().toString().equals(c.json().toString()),"complete fields and exact heads persisted");
        require(count("reader_revisions")==0,"persist precedes any command");
        for(String bad:new String[]{"\ud800","\udc00","a\0b"}){boolean refused=false;try{IntentJournal.Command.group(1,0,id(1),bad,"",0,new String[0]);}catch(IllegalArgumentException error){refused=true;}require(refused,"invalid Unicode refused before journal");}
        store().journal.clear();String large=String.valueOf((char)1).repeat(4096),sha="a".repeat(64),key="txt:"+sha;
        IntentJournal.Command bootstrap=new IntentJournal.Command(2,0,0,NativeCatalog.newId(),"",key,"","",0,new String[0],"txt",sha,1,large,large,large,false,1);
        store().journal.create(IntentJournal.Command.member(1,0,id(1),key,0,new String[0]),bootstrap);
        require(store().journal.read().bootstrap.title.equals(large)&&store().journal.read().bootstrap.sort.equals(large),"maximum escaped metadata remains recoverable");
        android.content.SharedPreferences prefs=context.getSharedPreferences("organization",0);String raw=prefs.getString("pending",null),checksum=prefs.getString("pending_sha256",null);
        try {
            damaged(raw+" ",checksum);damaged(raw.substring(0,raw.length()/2),checksum);damaged("x".repeat(131073),checksum);
            JSONObject wrongType=new JSONObject(raw);wrongType.getJSONObject("command").put("ordinal","0");String typed=wrongType.toString();damaged(typed,hash(typed));
            JSONObject wrongPlan=new JSONObject(raw);wrongPlan.getJSONObject("bootstrap").put("book","txt:"+"b".repeat(64)).put("sha","b".repeat(64));String plan=wrongPlan.toString();damaged(plan,hash(plan));
            JSONObject manyHeads=new JSONObject(raw);JSONArray heads=new JSONArray();for(int i=1;i<=33;i++)heads.put(id(i));manyHeads.getJSONObject("command").put("heads",heads);String excessive=manyHeads.toString();damaged(excessive,hash(excessive));
            JSONObject incomplete=new JSONObject(raw);incomplete.remove("bootstrap");incomplete.put("unknown",JSONObject.NULL);String missing=incomplete.toString();damaged(missing,hash(missing));
            require(count("reader_revisions")==0,"damaged recovery never publishes");
        } finally { require(prefs.edit().putString("pending",raw).putString("pending_sha256",checksum).commit(),"restore original journal"); }
        require(store().journal.read().bootstrap.author.equals(large),"valid large original remains recoverable after refusals");
    }
    private static String hash(String raw)throws Exception{StringBuilder result=new StringBuilder();for(byte value:MessageDigest.getInstance("SHA-256").digest(raw.getBytes(StandardCharsets.UTF_8)))result.append(String.format(java.util.Locale.ROOT,"%02x",value&255));return result.toString();}
    private void damaged(String raw,String checksum)throws Exception{
        android.content.SharedPreferences prefs=context.getSharedPreferences("organization",0);require(prefs.edit().putString("pending",raw).putString("pending_sha256",checksum).commit(),"persist damaged fixture");
        boolean refused=false;try{store().journal.read();}catch(Exception expected){refused=true;}
        require(refused&&raw.equals(prefs.getString("pending",null))&&checksum.equals(prefs.getString("pending_sha256",null)),"damaged intent refused without deleting pending");
    }
    private void staleRefusalRetainsExactRequest()throws Exception{
        group(1,1,"Before","",0);OrganizationStore.GroupEdit edit=store().group(1,id(1));
        IntentJournal.Command stale=IntentJournal.Command.group(1,0,id(1),"Stale","",0,edit.selection.heads);
        require(NativeCatalog.applyGroup(owner(),id(3),edit.selection.heads,0,1,id(1),"Newer","",0).status==0,"concurrent writer");
        String outcome=store().submit(stale,null,task());require(outcome.contains("refused"),"stale refused");
        String saved=store().journal.read().command.json().toString();require(saved.equals(stale.json().toString()),"stale identity/payload/heads unchanged");
        require(store().retry(task()).contains("refused")&&saved.equals(store().journal.read().command.json().toString()),"exact stale retry");
        require(count("reader_revisions")==2&&store().group(1,id(1)).group.name.equals("Newer"),"no stale metadata/history/outbox");
        store().journal.clear();IntentJournal.Command[] competing={IntentJournal.Command.group(1,0,id(2),"First pending","",0,new String[0]),IntentJournal.Command.group(1,0,id(3),"Second pending","",0,new String[0])};
        CountDownLatch start=new CountDownLatch(1);AtomicInteger savedCount=new AtomicInteger(),refusedCount=new AtomicInteger();AtomicReference<Throwable> failure=new AtomicReference<>();Thread[] workers=new Thread[2];
        for(int i=0;i<2;i++){final int at=i;workers[i]=new Thread(()->{try{start.await();new IntentJournal(context.getSharedPreferences("organization",0)).create(competing[at],null);savedCount.incrementAndGet();}
            catch(IllegalStateException expected){refusedCount.incrementAndGet();}catch(Throwable error){failure.set(error);}});workers[i].start();}
        start.countDown();for(Thread worker:workers){worker.join(10000);require(!worker.isAlive(),"journal contender finished");}
        require(failure.get()==null&&savedCount.get()==1&&refusedCount.get()==1,"overlapping Activity owners retain exactly one full intent");
        IntentJournal.Pending retained=store().journal.read();require(retained.command.json().toString().equals(competing[0].json().toString())||retained.command.json().toString().equals(competing[1].json().toString()),"complete winning request remains");
    }
    private void bootstrapKeepsCurrentUserFields()throws Exception{
        group(1,1,"Tag","",0);CatalogStore.ShelfBook b=book("SDK title");
        String large=String.valueOf((char)1).repeat(4096);
        db().execSQL("UPDATE reader_books SET title=?,author=?,sort_title=?,favorite=1",new Object[]{"用户😀",large,large});
        OrganizationStore.MemberEdit edit=store().member(1,id(1),b,task());require(edit.bootstrap!=null,"explicit bootstrap plan");
        store().journal.create(IntentJournal.Command.member(1,0,id(1),b.key.bookKey,0,edit.selection.heads),edit.bootstrap);
        books.close();books=new BookStore(context,new File(directory,"library.db"));
        require(store().journal.read().bootstrap.author.equals(large)&&store().journal.read().bootstrap.sort.equals(large),"actual large product fields recovered after owner reopen");
        require(store().retry(task()).equals("Change committed"),"membership committed");
        String[] m=NativeCatalog.metadata(owner(),b.key.bookKey);require(m[3].equals("用户😀")&&m[4].equals(large)&&m[5].equals(large)&&m[6].equals("1"),"product fields preserved");
        require(count("reader_revisions")==3&&count("reader_book_tags")==1&&store().journal.read()==null,"one book and membership revision");
    }
    private void partialBootstrapSurvivesMembershipRefusal()throws Exception{
        CatalogStore.ShelfBook b=book("Partial");OrganizationStore.MemberEdit edit=store().member(1,id(999),b,task());
        IntentJournal.Command c=IntentJournal.Command.member(1,0,id(999),b.key.bookKey,0,edit.selection.heads);
        require(store().submit(c,edit.bootstrap,task()).contains("Book history committed"),"partial success explicit");
        IntentJournal.Pending saved=store().journal.read();require(saved.bootstrapDone&&count("reader_revisions")==1,"bootstrap checkpoint durable");
        group(999,1,"Dependency repaired","",0);require(store().retry(task()).equals("Change committed"),"same plan after dependency repair");
        require(count("reader_revisions")==3&&count("reader_book_tags")==1,"no duplicate bootstrap");
    }
    private void legacyMetadataChangeRefusesBootstrap()throws Exception{
        group(1,1,"Tag","",0);CatalogStore.ShelfBook b=book("Legacy");OrganizationStore.MemberEdit edit=store().member(1,id(1),b,task());
        db().execSQL("UPDATE reader_books SET title='New user edit'");
        require(store().submit(IntentJournal.Command.member(1,0,id(1),b.key.bookKey,0,edit.selection.heads),edit.bootstrap,task()).contains("changed since bootstrap review"),"legacy product changed refused");
        require(count("reader_revisions")==1&&count("reader_book_tags")==0&&!store().journal.read().bootstrapDone,"no changed-field overwrite");
    }
    private void lateCancelPreservesCommittedOutcome()throws Exception{
        HostTask t=task();IntentJournal.Command c=IntentJournal.Command.group(1,0,id(1),"Commit","",0,new String[0]);store().journal.create(c,null);
        t.commit(()->{require(c.apply(owner()).status==0,"commit");t.cancel();});t.check();
        require(store().retry(task()).equals("Change committed")&&count("reader_revisions")==1,"committed exact retry after late cancel");
        HostTask early=task();early.cancel();boolean canceled=false;try{store().submit(IntentJournal.Command.group(1,0,id(2),"No write","",0,new String[0]),null,early);}catch(HostTask.Cancelled expected){canceled=true;}
        require(canceled&&count("reader_revisions")==1&&store().journal.read()==null,"early cancellation leaves no submission");
    }
    private void groupAndRemovedKeysetsStayBounded()throws Exception{
        for(int i=1;i<=105;i++){group(i,0,"Shelf "+i,"",i);NativeCatalog.Result r=NativeCatalog.applyGroup(owner(),id(20000+i),new String[]{id(10000+i)},1,0,id(i),null,null,0);require(r.status==0,"remove");}
        List<OrganizationStore.Group> first=store().groups(0,"",null,false,true),second=store().groups(0,"",first.get(49),false,true),last=store().groups(0,"",second.get(49),false,true);
        require(first.size()==50&&second.size()==50&&last.size()==5,"bounded Removed pages");
        List<OrganizationStore.Group> back=store().groups(0,"",second.get(0),true,true);require(back.size()==50&&back.get(0).id.equals(first.get(0).id),"reverse keyset");
        require(store().groups(0,"",null,false,false).isEmpty(),"active page excludes removed");
    }
    private void membershipDeleteRequiresExplicitRestore()throws Exception{
        group(1,2,"Series","",0);CatalogStore.ShelfBook b=book("Series book");OrganizationStore.MemberEdit e=store().member(2,id(1),b,task());
        store().submit(IntentJournal.Command.member(2,0,id(1),b.key.bookKey,9,e.selection.heads),e.bootstrap,task());
        e=store().member(2,id(1),b,task());store().submit(IntentJournal.Command.member(2,1,id(1),b.key.bookKey,9,e.selection.heads),null,task());
        e=store().member(2,id(1),b,task());require(e.selection.deleted&&!e.present,"deleted membership snapshot");
        require(store().submit(IntentJournal.Command.member(2,0,id(1),b.key.bookKey,1,e.selection.heads),null,task()).contains("refused"),"implicit restore refused");store().journal.clear();
        require(store().submit(IntentJournal.Command.member(2,2,id(1),b.key.bookKey,1,e.selection.heads),null,task()).equals("Change committed"),"explicit restore");
        require(store().members(2,id(1),null,false,"").get(0).ordinal==1,"series order projected");
    }
    private void phase(String phase){Bundle result=new Bundle();try{
        directory=context.getFilesDir();File evidence=new File(context.getExternalFilesDir(null),"organization-tests");require(evidence.exists()||evidence.mkdirs(),"phase evidence");
        if(phase.equals("seed-ui")) {
            clearJournal();books=new BookStore(context,new File(directory,"library.db"));
            CatalogStore.ShelfBook first=book("Org One"),second=book("Org Two");
            db().execSQL("UPDATE reader_books SET title=?,author=?,sort_title=?,favorite=1 WHERE book_key=?",new Object[]{"Org One edited 😀","User Author","Org One edited 😀",first.key.bookKey});
            for(int i=1;i<=105;i++)group(i,0,String.format(java.util.Locale.ROOT,"Page %03d",i),"",1000+i);
            for(int i=200;i<305;i++){group(i,1,"Trash "+i,"",0);require(NativeCatalog.applyGroup(owner(),id(20000+i),new String[]{id(10000+i)},1,1,id(i),null,null,0).status==0,"trash seed");}
            write(new File(evidence,"seed.json"),identity().put("books",2).put("shelves",105).put("removed_tags",105).put("first_key",first.key.bookKey).put("second_key",second.key.bookKey));
        } else {
            books=new BookStore(context,new File(directory,"library.db"));
            if(phase.equals("fault")){db().execSQL("CREATE TRIGGER organization_fault BEFORE INSERT ON reader_tags BEGIN SELECT RAISE(ABORT,'organization UI fault');END");}
            else if(phase.equals("release-fault")){
                IntentJournal.Pending pending=store().journal.read();require(pending!=null&&pending.outcome.contains("refused")&&pending.command.name.equals("Killed retry"),"actual refused UI intent saved");
                write(new File(evidence,"refused.json"),identity().put("intent",pending.command.json()).put("outcome",pending.outcome));db().execSQL("DROP TRIGGER organization_fault");
            } else if(phase.equals("verify-ui")) {
                JSONObject refused=new JSONObject(new String(Files.readAllBytes(new File(evidence,"refused.json").toPath()),StandardCharsets.UTF_8));
                IntentJournal.Command command=IntentJournal.Command.read(refused.getJSONObject("intent"));
                require(store().journal.read()==null&&NativeCatalog.retained(owner(),command.revision),"same refused revision committed after restart");
                require(store().group(1,command.id).group.name.equals("Killed retry"),"same entity and payload");
                try(Cursor retained=db().rawQuery("SELECT body_json FROM reader_revisions WHERE revision_id=?",new String[]{command.revision})) {
                    require(retained.moveToFirst(),"retained retry wire");JSONObject wire=new JSONObject(retained.getString(0));
                    require(wire.getString("id").equals(command.revision)&&wire.getString("entity_key").equals(command.id)&&
                        wire.getJSONObject("payload").getString("name").equals(command.name)&&wire.getJSONArray("parents").length()==command.heads.length,"same persisted command fields and heads");
                    require(!retained.moveToNext(),"one retry revision");
                }
                String[] m=NativeCatalog.metadata(owner(),new JSONObject(new String(Files.readAllBytes(new File(evidence,"seed.json").toPath()),StandardCharsets.UTF_8)).getString("first_key"));
                require(m[3].equals("Org One edited 😀")&&m[4].equals("User Author")&&m[6].equals("1"),"UI bootstrap preserved current product fields");
                write(new File(evidence,"verified.json"),identity().put("revision",command.revision).put("entity",command.id).put("exact_retry",true).put("product_fields_preserved",true));
            } else throw new IllegalArgumentException("Unknown organization phase");
        }
        ProductFixture.closeAll();books.close();books=null;result.putString("stream","EXR_ORGANIZATION_PHASE "+phase+"\n");finish(Activity.RESULT_OK,result);
    }catch(Throwable error){result.putString("shortMsg","EXR_ORGANIZATION_FAILED "+Log.getStackTraceString(error));finish(Activity.RESULT_CANCELED,result);}}
    private static void write(File file,JSONObject value)throws Exception{Files.write(file.toPath(),value.toString(2).getBytes(StandardCharsets.UTF_8));}
    private static void remove(File file)throws Exception{if(file==null||!file.exists())return;File[] children=file.listFiles();if(children!=null)for(File child:children)remove(child);require(file.delete(),"remove fixture");}
}
