// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.database.Cursor;
import android.os.Bundle;
import android.os.Build;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.concurrent.atomic.AtomicReference;

/** Actual installed JNI only. Fresh isolated test catalogs; no SQL writers. */
public final class HeadBridgeTest extends Instrumentation {
    static final String[] NAMES={"empty_snapshot","put_identity","delete_state","explicit_restore_state",
        "stale_write_still_refused","repeat_read_preserves_product","immutable_snapshot",
        "wrong_thread_refused","closed_handle_refused","malformed_entity_refused","native_operation_detail_text_readonly"};
    interface Check { void run() throws Exception; }
    private Bundle args;
    private Context context;
    private CatalogStore catalog;
    private File directory;
    private final JSONArray checks=new JSONArray(), observations=new JSONArray();
    @Override public void onCreate(Bundle value){super.onCreate(value);args=value;start();}
    private static void need(boolean ok,String why){if(!ok)throw new AssertionError(why);}
    private static String id(int n){return String.format(java.util.Locale.ROOT,"%032x",n);}
    private long owner(){return catalog.nativeOwner();}
    private static void remove(File f)throws Exception{
        if(f==null||!f.exists())return;
        File[] children=f.listFiles();if(children!=null)for(File child:children)remove(child);
        need(f.delete(),"remove isolated test fixture");
    }
    private NativeCatalog.Result command(int n,String[] heads,int operation){
        return NativeCatalog.applyGroup(owner(),id(n),heads,operation,1,id(100),
            operation==1?null:"Bridge tag "+n,null,0);
    }
    private void put(){need(command(1,new String[0],0).status==0,"real native put");}
    private NativeCatalog.HeadSnapshot snapshot(){return NativeCatalog.headDetails(owner(),"tag",id(100));}
    private String digest(String value)throws Exception{
        byte[] bytes=MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8));
        StringBuilder s=new StringBuilder();for(byte b:bytes)s.append(String.format(java.util.Locale.ROOT,"%02x",b&255));return s.toString();
    }
    private String wireHash(String revision)throws Exception{
        try(Cursor c=ProductFixture.of(catalog).rawQuery("SELECT body_json FROM reader_revisions WHERE revision_id=?",new String[]{revision})){
            need(c.moveToFirst(),"real command wire missing");
            String raw=c.getString(0);need(raw!=null&&revision.equals(new JSONObject(raw).getString("id")),"wire identity");
            need(!c.moveToNext(),"duplicate revision body");
            return digest(raw);
        }
    }
    private void verify(int revision,String operation,int total)throws Exception{
        NativeCatalog.HeadSnapshot s=snapshot();
        need(s.revisions==total&&s.headCount==1&&s.heads.size()==1,"complete native graph count");
        need(s.missingParents==0&&s.foreignParents==0,"complete native graph ancestry");
        NativeCatalog.RevisionHead h=s.heads.get(0);
        need(h.revisionId.equals(id(revision))&&h.operation.equals(operation)&&h.complete,"native operation and revision");
        need(h.sha256.equals(wireHash(h.revisionId)),"wire hash from actual product provider");
        need(Arrays.equals(NativeCatalog.heads(owner(),"tag",id(100)),new String[]{h.revisionId}),"original heads agree");
        String[] selected=NativeCatalog.selection(owner(),"tag",id(100));
        need(s.deleted=="1".equals(selected[1])&&s.requiresRestore=="1".equals(selected[2]),"selection state agrees");
        observations.put(new JSONObject().put("revision",h.revisionId).put("operation",h.operation)
            .put("wire_sha256",h.sha256).put("revisions",s.revisions).put("heads",s.headCount)
            .put("deleted",s.deleted).put("requires_restore",s.requiresRestore));
    }
    private String logicalState()throws Exception{
        JSONObject value=new JSONObject();
        for(String table:new String[]{"reader_revisions","reader_outbox","reader_tags"}){
            JSONArray rows=new JSONArray();
            try(Cursor c=ProductFixture.of(catalog).rawQuery("SELECT * FROM "+table+" ORDER BY 1",null)){
                while(c.moveToNext()){JSONArray row=new JSONArray();for(int i=0;i<c.getColumnCount();i++)
                    row.put(c.isNull(i)?JSONObject.NULL:c.getString(i));rows.put(row);}
            }
            value.put(table,rows);
        }
        return value.toString();
    }
    private static void refuses(Class<? extends Throwable> type,Check action)throws Exception{
        try{action.run();}catch(Throwable error){if(type.isInstance(error))return;throw new AssertionError("Wrong exception",error);}
        throw new AssertionError("Expected refusal");
    }
    private void empty()throws Exception{
        NativeCatalog.HeadSnapshot s=snapshot();
        need(s.revisions==0&&s.headCount==0&&s.heads.isEmpty()&&s.missingParents==0&&s.foreignParents==0,"empty entity");
        need(NativeCatalog.heads(owner(),"tag",id(100)).length==0,"original empty heads");
    }
    private void putCase()throws Exception{put();verify(1,"put",1);}
    private void deleteCase()throws Exception{put();need(command(2,new String[]{id(1)},1).status==0,"delete");verify(2,"delete",2);need(snapshot().deleted,"deleted state");}
    private void restoreCase()throws Exception{deleteCase();need(command(3,new String[]{id(2)},2).status==0,"explicit restore");verify(3,"restore",3);need(!snapshot().deleted,"restored state");}
    private void stale()throws Exception{
        put();NativeCatalog.HeadSnapshot old=snapshot();need(command(2,new String[]{id(1)},0).status==0,"advance real history");
        String before=logicalState();NativeCatalog.Result r=command(3,new String[]{old.heads.get(0).revisionId},0);
        need(r.status==3&&r.revisionStatus==10&&!r.created&&!r.applied,"stale command still refused");
        need(before.equals(logicalState()),"refusal did not write");verify(2,"put",2);
    }
    private void readonly()throws Exception{
        put();String before=logicalState();for(int i=0;i<20;i++)verify(1,"put",1);
        need(before.equals(logicalState()),"bridge did not mutate history outbox or metadata");
        observations.put(new JSONObject().put("logical_before_sha256",digest(before)).put("logical_after_sha256",digest(logicalState())));
    }
    private void immutable()throws Exception{put();NativeCatalog.HeadSnapshot s=snapshot();refuses(UnsupportedOperationException.class,()->s.heads.clear());verify(1,"put",1);}
    private void wrongThread()throws Exception{
        put();long h=owner();AtomicReference<Throwable> caught=new AtomicReference<>();
        Thread t=new Thread(()->{try{NativeCatalog.headDetails(h,"tag",id(100));}catch(Throwable error){caught.set(error);}});
        t.start();t.join(10000);need(!t.isAlive()&&caught.get() instanceof IllegalStateException,"native owner refusal");verify(1,"put",1);
    }
    private void closed()throws Exception{put();long h=owner();ProductFixture.closeAll();catalog.close();catalog=null;refuses(IllegalStateException.class,()->NativeCatalog.headDetails(h,"tag",id(100)));}
    private void malformed()throws Exception{put();String before=logicalState();refuses(IllegalArgumentException.class,()->NativeCatalog.headDetails(owner(),"tag","\ud800"));need(before.equals(logicalState()),"bad entity unchanged");verify(1,"put",1);}
    private void detailText()throws Exception{
        put();
        String[] labels={"Edit retained","Deletion requested","Restoration requested"};
        for(int i=0;i<labels.length;i++){
            if(i>0)need(command(i+1,new String[]{id(i)},i).status==0,"real native operation for detail");
            NativeCatalog.HeadSnapshot detail=snapshot();String before=logicalState();
            String text=OrganizationPanel.groupConflictPage(detail,0);
            need(text.contains("Version 1: "+labels[i])&&text.contains("Versions 1–1 of 1"),"actual operation label");
            need(before.equals(logicalState()),"rendering detail must not write or restore");
            refuses(IllegalArgumentException.class,()->OrganizationPanel.groupConflictPage(detail,-1));
            refuses(IllegalArgumentException.class,()->OrganizationPanel.groupConflictPage(detail,1));
        }
        observations.put(new JSONObject().put("scope","Native operation text renderer only; no actual UI acceptance")
            .put("operation_labels",new JSONArray(Arrays.asList(labels))).put("readonly",true));
    }
    @Override public void onStart(){
        context=getTargetContext();Check[] actions={this::empty,this::putCase,this::deleteCase,this::restoreCase,this::stale,this::readonly,this::immutable,this::wrongThread,this::closed,this::malformed,this::detailText};
        int failed=0;String[] sdk=new String[0];String globalFailure=null;
        try{sdk=NativeLibrary.syncIdentity();need(sdk.length==4&&"3.42.0".equals(sdk[0])&&sdk[1].equals(sdk[2]),"actual installed shared SDK3.42");}
        catch(Throwable error){globalFailure=error.toString();failed++;}
        for(int i=0;i<actions.length;i++){
            Throwable failure=null;
            try{
                directory=new File(context.getCacheDir(),"f05-head-bridge-"+i);remove(directory);need(directory.mkdirs(),"fixture directory");
                catalog=new CatalogStore(context,new File(directory,"reader-catalog.db"));
                need(NativeCatalog.provider(owner())[3].contains("libexreader_product.so"),"actual product JNI");
                actions[i].run();
            }catch(Throwable error){failure=error;failed++;}
            finally{try{ProductFixture.closeAll();if(catalog!=null)catalog.close();catalog=null;remove(directory);}catch(Throwable error){if(failure==null){failure=error;failed++;}}}
            try{JSONObject row=new JSONObject().put("name",NAMES[i]).put("pass",failure==null);
                if(failure!=null)row.put("failure",android.util.Log.getStackTraceString(failure));checks.put(row);}
            catch(Exception error){failed++;}
        }
        Bundle result=new Bundle();
        try{
            JSONObject report=new JSONObject().put("source_sha",args.getString("source_sha")).put("run_id",args.getString("run_id")).put("attempt",args.getString("attempt"))
                .put("api",Build.VERSION.SDK_INT).put("abi",Build.SUPPORTED_ABIS[0]).put("sdk_identity",new JSONArray(Arrays.asList(sdk)))
                .put("count",checks.length()).put("failed",failed).put("accepted",failed==0).put("checks",checks).put("observations",observations)
                .put("f05_full_accepted",false).put("ui_accepted",false).put("real_multihead_conflict_accepted",false).put("limit_4096_runtime_accepted",false);
            if(globalFailure!=null)report.put("global_failure",globalFailure);
            Files.write(new File(context.getFilesDir(),"f05-head-bridge-report.json").toPath(),report.toString(2).getBytes(StandardCharsets.UTF_8));
            result.putString("stream",failed==0?"F05_HEAD_BRIDGE_PASS":"F05_HEAD_BRIDGE_FAIL");
            finish(failed==0?Activity.RESULT_OK:Activity.RESULT_CANCELED,result);
        }catch(Exception error){result.putString("shortMsg","F05 evidence write failed");finish(Activity.RESULT_CANCELED,result);}
    }
}
