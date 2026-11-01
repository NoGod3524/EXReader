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
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.text.Normalizer;

/** Historical-state reconstruction only, not old-APK upgrade acceptance. */
public final class OrganizationBootstrapDiagnosticTest extends Instrumentation {
    private static final String[] NAMES={"currentAutomatic","legacyDirect","legacyReopen"};
    private Bundle arguments;
    private final JSONArray arms=new JSONArray();
    @Override public void onCreate(Bundle args){super.onCreate(args);arguments=args;start();}
    private static void require(boolean value,String message){if(!value)throw new AssertionError(message);}
    private static String hash(String text)throws Exception{
        StringBuilder out=new StringBuilder();
        for(byte b:MessageDigest.getInstance("SHA-256").digest(text.getBytes(StandardCharsets.UTF_8)))
            out.append(String.format(java.util.Locale.ROOT,"%02x",b&255));
        return out.toString();
    }
    private Bundle status(int index){Bundle b=new Bundle();b.putString("id","InstrumentationTestRunner");
        b.putString("class",getClass().getName());b.putString("test",NAMES[index]);b.putInt("numtests",3);b.putInt("current",index+1);return b;}
    @Override public void onStart(){
        int failed=0;
        for(int i=0;i<3;i++){
            sendStatus(1,status(i));JSONObject result=new JSONObject();boolean ok=false;
            try{result.put("id",NAMES[i]);runArm(i,result);ok=true;}
            catch(Throwable error){failed++;try{result.put("error_type",error.getClass().getName());}catch(Exception ignored){}}
            try{result.put("diagnostic_completed",ok);arms.put(result);}catch(Exception error){failed++;}
            Bundle b=status(i);b.putString("stream",ok?".":"diagnostic collection failed");
            if(!ok)b.putString("stack","Diagnostic collection failed; inspect fixed report");
            sendStatus(ok?0:-2,b);
        }
        try{
            JSONObject report=new JSONObject().put("source_sha",arguments.getString("source_sha"))
                .put("run_id",arguments.getString("run_id")).put("attempt",arguments.getString("attempt"))
                .put("api",Build.VERSION.SDK_INT).put("abi",Build.SUPPORTED_ABIS[0])
                .put("count",3).put("failed",failed).put("arms",arms)
                .put("diagnostic_only",true).put("product_accepted",false).put("old_apk_upgrade_accepted",false);
            Files.write(new File(getTargetContext().getFilesDir(),"f03-bootstrap-diagnostic.json").toPath(),
                        report.toString(2).getBytes(StandardCharsets.UTF_8));
        }catch(Exception error){failed++;}
        Bundle b=new Bundle();b.putString("stream",failed==0?"\nOK (3 tests)\n":"\nFAILURES!!! "+failed);
        finish(failed==0?Activity.RESULT_OK:Activity.RESULT_CANCELED,b);
    }
    private static final class ArmContext extends ContextWrapper {
        final String prefix;
        ArmContext(Context base,String prefix){super(base);this.prefix=prefix;}
        @Override public SharedPreferences getSharedPreferences(String name,int mode){
            return super.getSharedPreferences((name.equals("organization")||name.equals("sync-requests"))?prefix+name:name,mode);
        }
        void clear(){for(String name:new String[]{"organization","sync-requests"})
            require(getSharedPreferences(name,0).edit().clear().commit(),"clear dedicated diagnostic preferences");}
    }
    private static JSONArray array(String[] values){JSONArray out=new JSONArray();if(values!=null)for(String s:values)out.put(s==null?JSONObject.NULL:s);return out;}
    private static JSONObject rows(File directory,String table,String order)throws Exception{
        JSONArray rows=new JSONArray();
        try(Cursor c=ProductFixture.open(new File(directory,"reader-catalog.db")).rawQuery("SELECT * FROM "+table+" ORDER BY "+order,null)){
            while(c.moveToNext()){JSONArray row=new JSONArray();for(int i=0;i<c.getColumnCount();i++){
                if(c.isNull(i))row.put(JSONObject.NULL);
                else if(c.getType(i)==Cursor.FIELD_TYPE_INTEGER)row.put(c.getLong(i));
                else if(c.getType(i)==Cursor.FIELD_TYPE_FLOAT)row.put(c.getDouble(i));
                else if(c.getType(i)==Cursor.FIELD_TYPE_BLOB)throw new IllegalStateException("unexpected fixture blob");
                else row.put(c.getString(i));}
                rows.put(row);
            }
        }
        return new JSONObject().put("count",rows.length()).put("sha256",hash(rows.toString())).put("rows",rows);
    }
    private static JSONObject snapshot(BookStore books,ArmContext context,File directory,String key,String group)throws Exception{
        IntentJournal.Pending pending=books.organization().journal.read();
        String raw=context.getSharedPreferences("organization",0).getString("pending",null);
        JSONObject p=new JSONObject().put("present",pending!=null).put("raw_sha256",raw==null?JSONObject.NULL:hash(raw));
        if(pending!=null){
            p.put("command_sha256",hash(pending.command.json().toString())).put("command_revision",pending.command.revision)
             .put("command_heads",array(pending.command.heads)).put("bootstrap_present",pending.bootstrap!=null)
             .put("bootstrap_done",pending.bootstrapDone).put("outcome",pending.outcome);
            if(pending.bootstrap!=null)p.put("bootstrap_sha256",hash(pending.bootstrap.json().toString()))
                .put("bootstrap_revision",pending.bootstrap.revision).put("bootstrap_heads",array(pending.bootstrap.heads))
                .put("bootstrap_retained",NativeCatalog.retained(books.productOwner(),pending.bootstrap.revision));
        }
        JSONArray members=new JSONArray();for(String[] row:NativeCatalog.memberFind(books.productOwner(),1,group,key))members.put(array(row));
        return new JSONObject().put("metadata",array(NativeCatalog.metadata(books.productOwner(),key)))
            .put("book_heads",array(NativeCatalog.heads(books.productOwner(),"book",key)))
            .put("selection",array(NativeCatalog.selection(books.productOwner(),"book",key)))
            .put("revisions",rows(directory,"reader_revisions","revision_id"))
            .put("outbox",rows(directory,"reader_outbox","revision_id"))
            .put("local_mapping",rows(directory,"reader_local_books","sdk_book_id"))
            .put("membership",members).put("pending",p);
    }
    private void runArm(int index,JSONObject result)throws Exception{
        String run=arguments.getString("run_id");require(run!=null&&run.matches("[0-9]+"),"run identity");
        ArmContext context=new ArmContext(getTargetContext(),"f03-bootstrap-"+run+"-"+index+"-");
        File directory=new File(getTargetContext().getCacheDir(),"f03-bootstrap-"+run+"-"+index);
        require(!directory.exists()&&directory.mkdirs(),"exclusive diagnostic directory");
        context.clear();BookStore books=null;
        try{
            result.put("stage","open");
            books=new BookStore(context,new File(directory,"library.db"));
            File source=new File(directory,"original.txt");String content="Public bootstrap diagnostic original.\n";
            Files.write(source.toPath(),content.getBytes(StandardCharsets.UTF_8));
            result.put("stage","import");
            long sdk=books.importFile(source.getPath(),NativeLibrary.FORMAT_TXT,"Verified original").id;
            result.put("stage","verify_seed");
            BookStore.VerifiedSource verified=books.verifySource(sdk,null,0,new HostTask(()->false));
            require(verified.sha256.equals(hash(content))&&verified.bytes==content.getBytes(StandardCharsets.UTF_8).length,"real source verified");
            result.put("stage","attach_or_finalize");
            if(index==0)books.finalizeImport(verified);
            else NativeCatalog.attach(books.productOwner(),verified.format,verified.sha256,verified.bytes,verified.book.id,
                verified.location,verified.book.title,verified.book.author,
                Normalizer.normalize(verified.book.title,Normalizer.Form.NFC),verified.book.favorite!=0);
            String group="00000000000000000000000000000001";
            NativeCatalog.Result made=NativeCatalog.applyGroup(books.productOwner(),NativeCatalog.newId(),new String[0],0,1,group,"Tag","",0);
            require(made.status==NativeCatalog.Result.OK&&made.created&&made.applied,"actual group seeded");
            CatalogStore.ShelfBook local=books.localShelfBook(sdk);require(local!=null,"real local mapping");
            result.put("stage","plan");
            OrganizationStore.MemberEdit edit=books.organization().member(1,group,local,new HostTask(()->false));
            require((edit.bootstrap==null)==(index==0),"distinguishing automatic versus legacy precondition");
            IntentJournal.Command command=IntentJournal.Command.member(1,0,group,verified.key,0,edit.selection.heads);
            result.put("stage","persist");
            books.organization().journal.create(command,edit.bootstrap);
            result.put("source_sha256",verified.sha256).put("source_bytes",verified.bytes)
                .put("historical_state_reconstruction",index!=0)
                .put("before",snapshot(books,context,directory,verified.key,group));
            if(index==2){
                result.put("stage","close");
                ProductFixture.closeAll();books.close();books=null;
                result.put("stage","reopen");
                books=new BookStore(context,new File(directory,"library.db"));
                result.put("after_reopen",snapshot(books,context,directory,verified.key,group));
            }
            result.put("stage","retry");
            String outcome=books.organization().retry(new HostTask(()->false));
            result.put("retry_return",outcome).put("after_retry",snapshot(books,context,directory,verified.key,group));
            result.put("stage","verify_after");
            BookStore.VerifiedSource after=books.verifySource(sdk,verified.sha256,verified.bytes,new HostTask(()->false));
            require(after.key.equals(verified.key)&&after.sha256.equals(verified.sha256)&&after.bytes==verified.bytes,"source bytes preserved");
            result.put("source_preserved",true).put("committed","Change committed".equals(outcome));
            if(index<2)require("Change committed".equals(outcome)&&books.organization().journal.read()==null,"positive control committed");
            result.put("stage","completed");
            // C records actual refusal or commit, without substituting heads or declaring product acceptance.
        }finally{
            ProductFixture.closeAll();if(books!=null)books.close();context.clear();
        }
    }
}
