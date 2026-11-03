// SPDX-License-Identifier: MIT
package org.exreader.host;
import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.database.Cursor;
import android.os.Build;
import android.os.Bundle;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.Map;

/** Real product commands plus public revision APIs, exclusively in isolated test catalogs. */
public final class ConflictBoundaryTest extends Instrumentation {
    static {System.loadLibrary("exreader_product");}
    static native byte[] readWire(long owner,String revision);
    static native String[] ingest(long owner,byte[] value,String expected,boolean remote);
    static native String[] probeIdentity(long owner);
    static final String[] NAMES={"concurrent_put_put","concurrent_delete_put","explicit_restore_all_heads",
        "history_4095_complete","history_4096_complete","history_4097_atomic_refusal","limit_exact_replay","limit_close_reopen_readonly"};
    interface Check {void run() throws Exception;}
    private Bundle args;
    private Context context;
    private File directory;
    private CatalogStore a,b;
    private final JSONArray checks=new JSONArray(),observations=new JSONArray();
    private final Map<String,byte[]> sourceWires=new LinkedHashMap<>();
    private final Map<String,String> requestedOperations=new LinkedHashMap<>();
    private final Map<String,String[]> requestedParents=new LinkedHashMap<>();
    private byte[] firstBoundary;
    private String[] sdk=new String[0],provider=new String[0];
    private int failed;
    @Override public void onCreate(Bundle value){super.onCreate(value);args=value;start();}
    private static void need(boolean ok,String why){if(!ok)throw new AssertionError(why);}
    private static String id(int n){return String.format(java.util.Locale.ROOT,"%032x",n);}
    private static String hash(byte[] bytes)throws Exception{
        byte[] value=MessageDigest.getInstance("SHA-256").digest(bytes);StringBuilder out=new StringBuilder();
        for(byte v:value)out.append(String.format(java.util.Locale.ROOT,"%02x",v&255));return out.toString();
    }
    private static void remove(File f)throws Exception{
        if(f==null||!f.exists())return;File[] all=f.listFiles();if(all!=null)for(File child:all)remove(child);
        need(f.delete(),"Remove isolated fixture");
    }
    private void closeOwners()throws Exception{
        Throwable first=null;
        try{ProductFixture.closeAll();}catch(Throwable error){first=error;}
        CatalogStore left=a,right=b;a=null;b=null;
        try{if(left!=null)left.close();}catch(Throwable error){if(first==null)first=error;else first.addSuppressed(error);}
        try{if(right!=null)right.close();}catch(Throwable error){if(first==null)first=error;else first.addSuppressed(error);}
        if(first instanceof Exception)throw (Exception)first;
        if(first instanceof Error)throw (Error)first;
        if(first!=null)throw new Exception(first);
    }
    private void fresh(String name)throws Exception{
        closeOwners();if(directory!=null)remove(directory);
        directory=new File(context.getCacheDir(),"f05-conflict-"+name);remove(directory);need(directory.mkdirs(),"Fixture directory");
        a=new CatalogStore(context,new File(directory,"a.db"));b=new CatalogStore(context,new File(directory,"b.db"));
        sourceWires.clear();requestedOperations.clear();requestedParents.clear();provider=probeIdentity(a.nativeOwner());
        need(provider.length==4&&provider[0].contains("libexreader_product.so")&&provider[0].equals(provider[1])&&provider[2].equals("4096"),"Actual bounded product provider");
    }
    private NativeCatalog.Result command(CatalogStore c,int revision,String[] heads,int op){
        requestedOperations.put(id(revision),op==1?"delete":op==2?"restore":"put");
        requestedParents.put(id(revision),heads.clone());
        return NativeCatalog.applyGroup(c.nativeOwner(),id(revision),heads,op,1,id(100),op==1?null:"Real product "+revision,null,0);
    }
    private byte[] remember(CatalogStore c,int revision)throws Exception{
        byte[] wire=readWire(c.nativeOwner(),id(revision));JSONObject body=new JSONObject(new String(wire,StandardCharsets.UTF_8));
        need(body.getString("id").equals(id(revision))&&body.getString("entity_key").equals(id(100)),"Original command wire identity");
        need(body.getString("entity_kind").equals("tag")&&body.getString("operation").equals(requestedOperations.get(id(revision))),"Wire operation equals independently recorded product request");
        JSONArray parents=body.getJSONArray("parents");String[] expected=requestedParents.get(id(revision));
        need(expected!=null&&parents.length()==expected.length,"Requested parent count");
        java.util.HashSet<String> actual=new java.util.HashSet<>();for(int i=0;i<parents.length();i++)need(actual.add(parents.getString(i)),"No duplicate actual parent");
        need(actual.equals(new java.util.HashSet<>(Arrays.asList(expected))),"Wire parents equal complete observed request");
        sourceWires.put(id(revision),wire);return wire;
    }
    private void receive(CatalogStore target,byte[] wire)throws Exception{
        String[] row=ingest(target.nativeOwner(),wire,hash(wire),true);
        need(row.length==5&&row[0].equals("0")&&row[1].equals("1")&&row[3].equals(hash(wire)),"Real receive commits exact transported bytes");
    }
    private void graph(CatalogStore c,int revisions,int... heads)throws Exception{
        NativeCatalog.HeadSnapshot snap=NativeCatalog.headDetails(c.nativeOwner(),"tag",id(100));
        need(snap.revisions==revisions&&snap.headCount==heads.length&&snap.heads.size()==heads.length,"Complete graph counts");
        need(snap.missingParents==0&&snap.foreignParents==0,"No missing/foreign parents");
        need(!snap.requiresRestore&&snap.projectionSafe==(heads.length==1)&&!snap.deleted,"Expected safe/concurrent state without implicit restoration");
        JSONArray rows=new JSONArray();
        for(int i=0;i<heads.length;i++){
            NativeCatalog.RevisionHead head=snap.heads.get(i);String rid=id(heads[i]);byte[] original=sourceWires.get(rid);
            need(head.revisionId.equals(rid)&&original!=null&&head.complete&&!head.requiresRestore,"All expected real heads, complete unblocked state and stable order");
            JSONObject wire=new JSONObject(new String(original,StandardCharsets.UTF_8));
            need(head.operation.equals(wire.getString("operation"))&&head.sha256.equals(hash(original)),"Head exact wire operation/hash");
            need(Arrays.equals(readWire(c.nativeOwner(),rid),original),"Retained transport bytes unchanged");
            try(Cursor cur=ProductFixture.of(c).rawQuery("SELECT body_json FROM reader_revisions WHERE revision_id=?",new String[]{rid})){
                need(cur.moveToFirst(),"Stored head exists");String raw=cur.getString(0);need(!cur.moveToNext(),"Unique stored head");
                need(head.sha256.equals(hash(raw.getBytes(StandardCharsets.UTF_8))),"Independent actual stored wire digest");
            }
            rows.put(new JSONObject().put("id",rid).put("operation",head.operation).put("sha256",head.sha256).put("complete",head.complete).put("requires_restore",head.requiresRestore).put("parents",wire.getJSONArray("parents")));
        }
        String[] ids=new String[heads.length];for(int i=0;i<heads.length;i++)ids[i]=id(heads[i]);
        need(Arrays.equals(NativeCatalog.heads(c.nativeOwner(),"tag",id(100)),ids),"Old heads API agrees");
        if(heads.length>1)need(!snap.projectionSafe&&!snap.deleted,"Concurrent set not automatically projected");
        observations.put(new JSONObject().put("revisions",snap.revisions).put("head_count",snap.headCount)
            .put("projection_safe",snap.projectionSafe).put("deleted",snap.deleted).put("requires_restore",snap.requiresRestore).put("heads",rows));
    }
    private void putPut()throws Exception{
        fresh("put-put");need(command(a,1,new String[0],0).status==0&&command(b,2,new String[0],0).status==0,"Independent real author commands");
        byte[] wa=remember(a,1),wb=remember(b,2);receive(a,wb);receive(b,wa);graph(a,2,1,2);graph(b,2,1,2);
    }
    private void makeDeletePut()throws Exception{
        need(command(a,1,new String[0],0).status==0,"Shared ancestor authored");receive(b,remember(a,1));
        need(command(a,2,new String[]{id(1)},1).status==0,"Actual delete child");
        need(command(b,3,new String[]{id(1)},0).status==0,"Actual concurrent put child");
        byte[] wd=remember(a,2),wp=remember(b,3);receive(a,wp);receive(b,wd);graph(a,3,2,3);graph(b,3,2,3);
    }
    private void deletePut()throws Exception{fresh("delete-put");makeDeletePut();}
    private void restore()throws Exception{
        fresh("restore");makeDeletePut();NativeCatalog.Result result=command(a,4,new String[]{id(2),id(3)},2);
        need(result.status==0&&result.created&&result.applied,"Explicit restore consumes complete observed head set");
        remember(a,4);graph(a,4,4);NativeCatalog.HeadSnapshot snap=NativeCatalog.headDetails(a.nativeOwner(),"tag",id(100));
        need(snap.projectionSafe&&!snap.deleted&&!snap.requiresRestore,"Explicit restore is safe and live");
    }
    private byte[] boundaryWire(int number)throws Exception{
        return new JSONObject().put("version",1).put("id",id(20000+number)).put("entity_kind","tag").put("entity_key",id(100))
            .put("operation","put").put("location_kind","none").put("parents",new JSONArray())
            .put("payload",new JSONObject().put("name","Bounded legal revision "+number)).toString().getBytes(StandardCharsets.UTF_8);
    }
    private void appendBoundary(int number)throws Exception{
        byte[] wire=boundaryWire(number);String[] row=ingest(a.nativeOwner(),wire,null,false);
        need(row.length==5&&row[0].equals("0")&&row[1].equals("1")&&row[2].equals(id(20000+number))&&row[3].equals(hash(wire)),"Public local revision accepted "+number);
        sourceWires.put(row[2],wire);if(number==1)firstBoundary=wire;
    }
    private String logicalState()throws Exception{
        JSONObject result=new JSONObject();
        for(String table:new String[]{"reader_revisions","reader_outbox","reader_tags"}){
            JSONArray rows=new JSONArray();try(Cursor c=ProductFixture.of(a).rawQuery("SELECT * FROM "+table+" ORDER BY 1",null)){
                while(c.moveToNext()){JSONArray row=new JSONArray();for(int j=0;j<c.getColumnCount();j++)row.put(c.isNull(j)?JSONObject.NULL:c.getString(j));rows.put(row);}
            }result.put(table,rows);
        }return hash(result.toString().getBytes(StandardCharsets.UTF_8));
    }
    private void boundaryGraph(int count)throws Exception{
        int[] ids=new int[count];for(int i=0;i<count;i++)ids[i]=20001+i;graph(a,count,ids);
    }
    private void firstLimit()throws Exception{
        fresh("limit");b.close();b=null;
        for(int i=1;i<=4095;i++){appendBoundary(i);if(i%256==0)System.out.println("F05 legal history committed "+i);}
        boundaryGraph(4095);
    }
    private void fullLimit()throws Exception{appendBoundary(4096);boundaryGraph(4096);}
    private void overflow()throws Exception{
        String before=logicalState();String[] row=ingest(a.nativeOwner(),boundaryWire(4097),null,false);
        need(row.length==5&&row[0].equals("5")&&row[1].equals("0"),"4097 returns READER_REV_LIMIT with created zero");
        need(!NativeCatalog.retained(a.nativeOwner(),id(24097))&&before.equals(logicalState()),"Overflow atomic rollback including outbox");
        boundaryGraph(4096);observations.put(new JSONObject().put("overflow_status",5).put("before",before).put("after",logicalState()));
    }
    private void replay()throws Exception{
        String before=logicalState();String[] row=ingest(a.nativeOwner(),firstBoundary,null,false);
        need(row[0].equals("0")&&row[1].equals("0")&&before.equals(logicalState()),"Exact replay at limit does not requeue or grow");
        boundaryGraph(4096);
    }
    private void reopen()throws Exception{
        String before=logicalState();ProductFixture.closeAll();a.close();a=null;
        a=new CatalogStore(context,new File(directory,"a.db"));boundaryGraph(4096);boundaryGraph(4096);
        need(before.equals(logicalState()),"Reopened complete graph and repeated reads unchanged");
        observations.put(new JSONObject().put("reopened",true).put("before",before).put("after",logicalState()));
    }
    private boolean check(int i,Check action,boolean prerequisite){
        Throwable failure=null;
        try{need(prerequisite,"Prior boundary checkpoint failed; dependent checkpoint not executed");action.run();}
        catch(Throwable error){failure=error;failed++;System.out.println("F05 "+NAMES[i]+" failed: "+android.util.Log.getStackTraceString(error));}
        try{JSONObject row=new JSONObject().put("name",NAMES[i]).put("pass",failure==null);
            if(failure!=null)row.put("failure",android.util.Log.getStackTraceString(failure));checks.put(row);}
        catch(Exception error){failed++;}
        return failure==null;
    }
    @Override public void onStart(){
        context=getTargetContext();String global=null;
        try{sdk=NativeLibrary.syncIdentity();need(sdk.length==4&&sdk[0].equals("3.42.0")&&sdk[1].equals(sdk[2]),"Actual installed SDK3.42");}
        catch(Throwable error){global=error.toString();failed++;}
        check(0,this::putPut,global==null);check(1,this::deletePut,global==null);check(2,this::restore,global==null);
        boolean ok=check(3,this::firstLimit,global==null);
        ok=check(4,this::fullLimit,ok);ok=check(5,this::overflow,ok);ok=check(6,this::replay,ok);check(7,this::reopen,ok);
        try{closeOwners();remove(directory);}catch(Throwable error){failed++;global=String.valueOf(global)+" cleanup: "+error;}
        Bundle result=new Bundle();
        try{
            JSONObject report=new JSONObject().put("source_sha",args.getString("source_sha")).put("run_id",args.getString("run_id")).put("attempt",args.getString("attempt"))
                .put("api",Build.VERSION.SDK_INT).put("abi",Build.SUPPORTED_ABIS[0]).put("sdk_identity",new JSONArray(Arrays.asList(sdk)))
                .put("provider",new JSONArray(Arrays.asList(provider))).put("count",checks.length()).put("failed",failed).put("accepted",failed==0)
                .put("checks",checks).put("observations",observations).put("f05_full_accepted",false).put("ui_accepted",false)
                .put("transport_end_to_end_accepted",false).put("multihead_product_commands",true).put("boundary_fixture","public revision API, not SQL writes");
            if(global!=null)report.put("global_failure",global);
            Files.write(new File(context.getFilesDir(),"f05-conflict-boundary-report.json").toPath(),report.toString(2).getBytes(StandardCharsets.UTF_8));
            result.putString("stream",failed==0?"F05_CONFLICT_BOUNDARY_PASS":"F05_CONFLICT_BOUNDARY_FAIL");
            finish(failed==0?Activity.RESULT_OK:Activity.RESULT_CANCELED,result);
        }catch(Exception error){result.putString("shortMsg","F05 conflict evidence write failed");finish(Activity.RESULT_CANCELED,result);}
    }
}
