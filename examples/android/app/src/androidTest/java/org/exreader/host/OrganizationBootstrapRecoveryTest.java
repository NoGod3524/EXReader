// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.content.ContextWrapper;
import android.content.SharedPreferences;
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
import java.text.Normalizer;
import java.util.Arrays;

/** Real original bytes and typed commands; historical-state compatibility, not old-APK upgrade. */
public final class OrganizationBootstrapRecoveryTest extends Instrumentation {
    private static final String[] NAMES={"currentAutomatic","legacyDirect","legacyReopen",
        "legacyReopenSyncDeferred","unrelatedBookStillBootstraps","damagedPendingRetained",
        "mismatchedSourceRetained","changedMetadataRetained","foreignHeadRefused",
        "committedBootstrapReplay","partialMembershipRefusal","explicitDiscardAllowsAutomatic"};
    private Bundle arguments;
    private final JSONArray cases=new JSONArray();
    @Override public void onCreate(Bundle args){super.onCreate(args);arguments=args;start();}
    private static void require(boolean value,String message){if(!value)throw new AssertionError(message);}
    private static HostTask task(){return new HostTask(()->false);}
    private static String hash(String text)throws Exception{
        StringBuilder out=new StringBuilder();
        for(byte b:MessageDigest.getInstance("SHA-256").digest(text.getBytes(StandardCharsets.UTF_8)))
            out.append(String.format(java.util.Locale.ROOT,"%02x",b&255));
        return out.toString();
    }
    private Bundle status(int index){Bundle b=new Bundle();b.putString("id","InstrumentationTestRunner");
        b.putString("class",getClass().getName());b.putString("test",NAMES[index]);
        b.putInt("numtests",NAMES.length);b.putInt("current",index+1);return b;}
    @Override public void onStart(){
        int failed=0;
        for(int i=0;i<NAMES.length;i++){
            sendStatus(1,status(i));JSONObject result=new JSONObject();Throwable failure=null;
            try{result.put("id",NAMES[i]);runCase(i,result);}
            catch(Throwable error){failure=error;failed++;try{result.put("error",Log.getStackTraceString(error));}catch(Exception ignored){}}
            try{result.put("passed",failure==null);cases.put(result);}catch(Exception error){failed++;}
            Bundle b=status(i);b.putString("stream",failure==null?".":"recovery assertion failed");
            if(failure!=null)b.putString("stack",Log.getStackTraceString(failure));
            sendStatus(failure==null?0:-2,b);
        }
        try{
            JSONObject report=new JSONObject().put("source_sha",arguments.getString("source_sha"))
                .put("run_id",arguments.getString("run_id")).put("attempt",arguments.getString("attempt"))
                .put("api",Build.VERSION.SDK_INT).put("abi",Build.SUPPORTED_ABIS[0])
                .put("count",NAMES.length).put("failed",failed).put("checks",cases)
                .put("historical_state_recovery",true).put("full_f03_accepted",false)
                .put("old_apk_upgrade_accepted",false);
            Files.write(new File(getTargetContext().getFilesDir(),"f03-bootstrap-recovery.json").toPath(),
                report.toString(2).getBytes(StandardCharsets.UTF_8));
        }catch(Exception error){failed++;}
        Bundle b=new Bundle();b.putString("stream",failed==0?"\nOK ("+NAMES.length+" tests)\n":"\nFAILURES!!! "+failed);
        finish(failed==0?Activity.RESULT_OK:Activity.RESULT_CANCELED,b);
    }
    private static final class CaseContext extends ContextWrapper{
        final String prefix;
        CaseContext(Context base,String prefix){super(base);this.prefix=prefix;}
        @Override public SharedPreferences getSharedPreferences(String name,int mode){
            return super.getSharedPreferences((name.equals("organization")||name.equals("sync-requests"))?prefix+name:name,mode);
        }
        void clear(){for(String name:new String[]{"organization","sync-requests"})
            require(getSharedPreferences(name,0).edit().clear().commit(),"clear dedicated recovery preferences");}
    }
    private static long count(File directory,String table){
        try(Cursor c=ProductFixture.open(new File(directory,"reader-catalog.db")).rawQuery("SELECT count(*) FROM "+table,null)){
            require(c.moveToFirst(),"table count");return c.getLong(0);
        }
    }
    private static String rowsHash(File directory,String table,String order)throws Exception{
        JSONArray rows=new JSONArray();
        try(Cursor c=ProductFixture.open(new File(directory,"reader-catalog.db")).rawQuery("SELECT * FROM "+table+" ORDER BY "+order,null)){
            while(c.moveToNext()){JSONArray row=new JSONArray();for(int i=0;i<c.getColumnCount();i++)
                row.put(c.isNull(i)?JSONObject.NULL:c.getString(i));rows.put(row);}
        }
        return hash(rows.toString());
    }
    private static String pending(CaseContext context){return context.getSharedPreferences("organization",0).getString("pending",null);}
    private static JSONArray array(String[] values){JSONArray out=new JSONArray();if(values!=null)for(String value:values)out.put(value);return out;}
    private static JSONObject state(BookStore books,CaseContext context,File directory,String key)throws Exception{
        String raw=pending(context);
        return new JSONObject().put("revisions",count(directory,"reader_revisions")).put("outbox",count(directory,"reader_outbox"))
            .put("local_books",count(directory,"reader_local_books")).put("members",count(directory,"reader_book_tags"))
            .put("revisions_sha256",rowsHash(directory,"reader_revisions","revision_id"))
            .put("outbox_sha256",rowsHash(directory,"reader_outbox","revision_id"))
            .put("mapping_sha256",rowsHash(directory,"reader_local_books","sdk_book_id"))
            .put("heads",array(NativeCatalog.heads(books.productOwner(),"book",key)))
            .put("metadata",array(NativeCatalog.metadata(books.productOwner(),key)))
            .put("pending_sha256",raw==null?JSONObject.NULL:hash(raw));
    }
    private static void unchanged(JSONObject before,JSONObject after){
        require(before.toString().equals(after.toString()),"pending bytes, original heads, metadata, mappings, revisions and outbox unchanged");
    }
    private static void attach(BookStore books,BookStore.VerifiedSource source){
        NativeCatalog.attach(books.productOwner(),source.format,source.sha256,source.bytes,source.book.id,source.location,
            source.book.title,source.book.author,Normalizer.normalize(source.book.title,Normalizer.Form.NFC),source.book.favorite!=0);
        require(books.localShelfBook(source.book.id)!=null,"real local source attached");
    }
    private static void group(BookStore books,String id){
        NativeCatalog.Result made=NativeCatalog.applyGroup(books.productOwner(),NativeCatalog.newId(),new String[0],0,1,id,"Tag","",0);
        require(made.status==NativeCatalog.Result.OK&&made.created&&made.applied,"real typed group command");
    }
    private static IntentJournal.Command withSdk(IntentJournal.Command bootstrap,long sdk)throws Exception{
        JSONObject value=bootstrap.json();value.put("sdk",sdk);return IntentJournal.Command.read(value);
    }
    private void runCase(int index,JSONObject result)throws Exception{
        String run=arguments.getString("run_id");require(run!=null&&run.matches("[0-9]+"),"run identity");
        CaseContext context=new CaseContext(getTargetContext(),"f03-recovery-"+run+"-"+index+"-");
        File directory=new File(getTargetContext().getCacheDir(),"f03-recovery-"+run+"-"+index);
        require(!directory.exists()&&directory.mkdirs(),"exclusive recovery directory");
        context.clear();BookStore books=null;
        try{
            books=new BookStore(context,new File(directory,"library.db"));
            File source=new File(directory,"original.txt");String content="Public bootstrap recovery original.\n";
            Files.write(source.toPath(),content.getBytes(StandardCharsets.UTF_8));
            long sdk=books.importFile(source.getPath(),NativeLibrary.FORMAT_TXT,"Verified original").id;
            BookStore.VerifiedSource verified=books.verifySource(sdk,hash(content),content.getBytes(StandardCharsets.UTF_8).length,task());
            if(index==0)books.finalizeImport(verified);else attach(books,verified);
            String group="00000000000000000000000000000001";group(books,group);
            CatalogStore.ShelfBook local=books.localShelfBook(sdk);
            OrganizationStore.MemberEdit edit=books.organization().member(1,group,local,task());
            require((edit.bootstrap==null)==(index==0),"actual current or historical bootstrap precondition");
            String target=index==10?"00000000000000000000000000000002":group;
            IntentJournal.Command command=IntentJournal.Command.member(1,0,target,verified.key,0,edit.selection.heads);
            IntentJournal.Command bootstrap=index==6?withSdk(edit.bootstrap,Long.MAX_VALUE):edit.bootstrap;
            books.organization().journal.create(command,bootstrap);
            String originalRaw=pending(context);
            result.put("source_sha256",verified.sha256).put("source_bytes",verified.bytes)
                .put("before",state(books,context,directory,verified.key));
            boolean expectCommitted=true;
            if(index==4){
                File other=new File(directory,"other.txt");Files.write(other.toPath(),"Another real source.\n".getBytes(StandardCharsets.UTF_8));
                long otherId=books.importFile(other.getPath(),NativeLibrary.FORMAT_TXT,"Other book").id;
                BookStore.VerifiedSource otherSource=books.verifySource(otherId,null,0,task());books.finalizeImport(otherSource);
                require("4".equals(NativeCatalog.selection(books.productOwner(),"book",otherSource.key)[0]),"unrelated source automatically bootstrapped");
                require("0".equals(NativeCatalog.selection(books.productOwner(),"book",verified.key)[0])&&originalRaw.equals(pending(context)),"target intent and empty head retained");
            }
            if(index==5){
                String damaged=originalRaw+" ";
                require(context.getSharedPreferences("organization",0).edit().putString("pending",damaged).commit(),"store damaged test journal");
                originalRaw=damaged;expectCommitted=false;
            }
            if(index==6)expectCommitted=false;
            if(index==7){
                ProductFixture.open(new File(directory,"reader-catalog.db")).execSQL(
                    "UPDATE reader_books SET title=? WHERE book_key=?",new Object[]{"Changed after review",verified.key});
                expectCommitted=false;
            }
            if(index==8){
                NativeCatalog.Result foreign=NativeCatalog.applyBook(books.productOwner(),NativeCatalog.newId(),new String[0],0,
                    verified.key,verified.format,verified.sha256,verified.bytes,bootstrap.title,bootstrap.author,bootstrap.sort,bootstrap.favorite);
                require(foreign.status==NativeCatalog.Result.OK&&foreign.created,"genuine competing book revision");
                expectCommitted=false;
            }
            if(index==9){
                NativeCatalog.Result committed=bootstrap.apply(books.productOwner());
                require(committed.status==NativeCatalog.Result.OK&&committed.created,"bootstrap committed before recovery checkpoint");
                require(!books.organization().journal.read().bootstrapDone,"simulate interruption before checkpoint, not before commit");
            }
            if(index==10){
                require(books.organization().retry(task()).contains("Book history committed"),"partial success saved before dependency repair");
                IntentJournal.Pending p=books.organization().journal.read();
                require(p!=null&&p.bootstrapDone&&p.bootstrap.revision.equals(bootstrap.revision),"original partial checkpoint retained");
                originalRaw=pending(context);
            }
            if(index==11){
                books.organization().journal.clear();originalRaw=null;expectCommitted=false;
            }
            if(index>=2&&index!=4){
                JSONObject beforeReopen=state(books,context,directory,verified.key);
                ProductFixture.closeAll();books.close();books=null;
                books=new BookStore(context,new File(directory,"library.db"));
                JSONObject afterReopen=state(books,context,directory,verified.key);
                result.put("before_reopen",beforeReopen).put("after_reopen",afterReopen);
                if(index!=11)unchanged(beforeReopen,afterReopen);
                else{
                    require("4".equals(NativeCatalog.selection(books.productOwner(),"book",verified.key)[0]),"explicit discard releases automatic history");
                    require(count(directory,"reader_revisions")==beforeReopen.getLong("revisions")+1&&
                        count(directory,"reader_outbox")==beforeReopen.getLong("outbox")+1,"exactly one automatic revision after explicit discard");
                }
            }
            if(index==3){
                JSONObject beforeSync=state(books,context,directory,verified.key);boolean refused=false;
                try{books.stageSyncOriginals(new File(directory,"sync-originals"),context.getSharedPreferences("sync-requests",0),task());}
                catch(java.io.IOException expected){refused=expected.getMessage().contains("saved organization intent");}
                require(refused,"sync automatic bootstrap respects saved intent");
                unchanged(beforeSync,state(books,context,directory,verified.key));
            }
            if(index==5||index==6){
                boolean refused=false;
                try{books.organization().retry(task());}catch(Exception expected){refused=true;}
                require(refused&&originalRaw.equals(pending(context)),"invalid pending refused with original bytes retained");
                require("0".equals(NativeCatalog.selection(books.productOwner(),"book",verified.key)[0]),"invalid intent never authorizes automatic history");
            }else if(index!=11){
                if(index==10)group(books,target);
                String outcome=books.organization().retry(task());result.put("retry_return",outcome);
                if(expectCommitted){
                    require("Change committed".equals(outcome)&&books.organization().journal.read()==null,"exact saved request committed");
                    require(NativeCatalog.memberFind(books.productOwner(),1,target,verified.key).length==1,"exactly one membership");
                    long revisions=count(directory,"reader_revisions"),outbox=count(directory,"reader_outbox");
                    require("No saved intent".equals(books.organization().retry(task())),"completed retry is a no-op");
                    require(revisions==count(directory,"reader_revisions")&&outbox==count(directory,"reader_outbox"),"no duplicate revision or outbox");
                }else{
                    require(books.organization().journal.read()!=null&&NativeCatalog.memberFind(books.productOwner(),1,target,verified.key).length==0,"conflict remains pending without membership");
                    IntentJournal.Pending retained=books.organization().journal.read();
                    require(retained.command.json().toString().equals(command.json().toString())&&
                        retained.bootstrap.json().toString().equals(bootstrap.json().toString()),"refusal preserves original command and heads");
                    if(index==7)require(outcome.contains("changed since bootstrap review")&&
                        NativeCatalog.metadata(books.productOwner(),verified.key)[3].equals("Changed after review"),"user metadata edit preserved");
                    if(index==8)require(outcome.contains("Book bootstrap refused"),"foreign head is never adopted");
                }
            }
            BookStore.VerifiedSource after=books.verifySource(sdk,verified.sha256,verified.bytes,task());
            require(after.key.equals(verified.key),"original identity preserved");
            result.put("after",state(books,context,directory,verified.key)).put("source_preserved",true);
        }finally{
            ProductFixture.closeAll();if(books!=null)books.close();context.clear();
        }
    }
}
