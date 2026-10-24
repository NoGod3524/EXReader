// SPDX-License-Identifier: MIT
package org.exreader.webdav.probe;
import android.app.Activity;
import android.app.Instrumentation;
import android.content.Intent;
import android.os.Build;
import android.os.Bundle;
import android.os.SystemClock;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.MessageDigest;
import org.json.JSONArray;
import org.json.JSONObject;

public final class BackendProbe extends Instrumentation {
    private Bundle args;
    @Override public void onCreate(Bundle input){super.onCreate(input);args=input;start();}
    static JSONObject input(File files)throws Exception{return new JSONObject(new String(Files.readAllBytes(new File(files,"input.json").toPath()),StandardCharsets.UTF_8));}
    static JSONObject invoke(JSONObject input,JSONObject test,File directory)throws Exception {
        directory.mkdirs();
        if(test.has("source_bytes")){
            int length=test.getInt("source_bytes");byte[] bytes=new byte[length];for(int i=0;i<length;i++)bytes[i]=(byte)(i%251);
            Files.write(new File(directory,"source.bin").toPath(),bytes);
        }
        if(test.optBoolean("existing"))Files.write(new File(directory,"download.bin").toPath(),"existing".getBytes(StandardCharsets.UTF_8));
        long[] limits={test.optLong("maximum"),test.optLong("listing_bytes"),test.optLong("entries"),test.optLong("timeout",4000),test.optLong("cancel",-1),test.optLong("source_bytes")};
        byte[] raw=NativeDav.request(test.optString("root",input.getString("root")),test.optBoolean("no_auth")?"":input.getString("authorization"),directory.getAbsolutePath(),
            test.optString("action","get"),test.optString("resource","book.bin"),test.optString("filename","download.bin"),limits,!test.optBoolean("attached"));
        if(raw==null)throw new AssertionError("Native consumer did not return");
        JSONObject result=new JSONObject(new String(raw,StandardCharsets.UTF_8));
        if(result.getInt("status")!=test.optInt("expected"))throw new AssertionError(test.getString("name")+" status="+result.getInt("status"));
        for(String field:new String[]{"count","title","reentry","wrong_owner","http"})
            if(test.has(field)&&!test.get(field).toString().equals(result.get(field).toString()))throw new AssertionError(test.getString("name")+" field="+field);
        if(test.has("first_resource")&&!test.getString("first_resource").equals(result.getString("resource")))throw new AssertionError("Encoded first resource differs");
        if(result.getLong("clients")!=0||result.getLong("uploads")!=0||result.getLong("attached")!=result.getLong("detached"))throw new AssertionError("Native cleanup counters failed");
        for(File file:directory.listFiles())if(file.getName().startsWith(".exr-webdav-"))throw new AssertionError("Temporary download leaked");
        File download=new File(directory,"download.bin");
        if(test.optBoolean("existing")){if(!new String(Files.readAllBytes(download.toPath()),StandardCharsets.UTF_8).equals("existing"))throw new AssertionError("Destination replaced");}
        else if(result.getInt("status")!=0&&download.exists())throw new AssertionError("Failed transfer published");
        if(download.exists()&&!test.optBoolean("existing")){
            byte[] bytes=Files.readAllBytes(download.toPath());
            if(result.getInt("published")!=1||bytes.length!=test.optInt("download_bytes",524288))throw new AssertionError("Downloaded bytes differ");
            for(int i=0;i<bytes.length;i++)if(bytes[i]!=(byte)(i%251))throw new AssertionError("Downloaded content differs");
            result.put("sha256",hex(MessageDigest.getInstance("SHA-256").digest(bytes)));
        }
        return result.put("name",test.getString("name"));
    }
    static String hex(byte[] bytes){StringBuilder out=new StringBuilder();for(byte b:bytes)out.append(String.format("%02x",b&255));return out.toString();}
    @Override public void onStart(){
        Bundle result=new Bundle();try{
            File files=getTargetContext().getFilesDir();JSONObject input=input(files);JSONArray tests=input.getJSONArray("cases"),checks=new JSONArray();
            checks.put(invoke(input,new JSONObject().put("name","support_initialization_required").put("expected",3),new File(files,"before-bind")));
            if(NativeDav.bind()!=0)throw new AssertionError("Android support binding failed");
            if(NativeDav.bind()!=0)throw new AssertionError("Repeated Android binding failed");
            final Throwable[] uiFailure={null};final JSONObject[] uiResult={null};
            runOnMainSync(()->{try{uiResult[0]=invoke(input,new JSONObject().put("name","ui_thread_refused").put("expected",1).put("attached",true),new File(files,"ui"));}catch(Throwable error){uiFailure[0]=error;}});
            if(uiFailure[0]!=null)throw new AssertionError("UI owner guard failed");checks.put(uiResult[0]);
            for(int i=0;i<tests.length();i++){
                JSONObject test=tests.getJSONObject(i);long started=SystemClock.elapsedRealtime();
                JSONObject row=invoke(input,test,new File(files,"case-"+test.getString("name")));row.put("elapsed_ms",SystemClock.elapsedRealtime()-started);
                if(test.has("max_elapsed")&&row.getLong("elapsed_ms")>test.getLong("max_elapsed"))throw new AssertionError("Deadline not bounded");
                checks.put(row);
            }
            if(input.optBoolean("activity_exit")){
                ExitActivity.input=input;ExitActivity.directory=new File(files,"activity");ExitActivity.failure=null;ExitActivity.done=false;
                ExitActivity.task=()->{try{invoke(input,new JSONObject().put("name","activity-exit").put("resource","delayed.bin"),ExitActivity.directory);}
                    catch(Throwable error){ExitActivity.failure=error;}finally{ExitActivity.done=true;}};
                startActivitySync(new Intent(getTargetContext(),ExitActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
                long deadline=SystemClock.elapsedRealtime()+10000;while(!ExitActivity.done&&SystemClock.elapsedRealtime()<deadline)SystemClock.sleep(20);
                if(!ExitActivity.done||ExitActivity.failure!=null||!ExitActivity.destroyed)throw new AssertionError("Activity exit cleanup failed");
                checks.put(new JSONObject().put("name","activity_exit_worker_cleanup").put("status",0));
            }
            JSONObject report=new JSONObject().put("source_sha",args.getString("source_sha")).put("run_id",args.getString("run_id")).put("attempt",args.getString("attempt"))
                .put("api",Build.VERSION.SDK_INT).put("abi",Build.SUPPORTED_ABIS[0]).put("cases",checks).put("count",checks.length()).put("accepted",true);
            Files.write(new File(files,"backend-report.json").toPath(),report.toString(2).getBytes(StandardCharsets.UTF_8));result.putString("stream","EXR_ANDROID_DAV_ACCEPTED\n");finish(Activity.RESULT_OK,result);
        }catch(Throwable failure){result.putString("shortMsg","ANDROID_DAV_FAILED "+failure.getClass().getName()+" "+(failure instanceof AssertionError?failure.getMessage():""));finish(Activity.RESULT_CANCELED,result);}
    }
}
