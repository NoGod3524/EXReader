// SPDX-License-Identifier: MIT
package org.exreader.sessionprobe;
import android.app.Activity;
import android.app.Instrumentation;
import android.os.Build;
import android.os.Bundle;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.json.JSONArray;
import org.json.JSONObject;
public final class SessionProbe extends Instrumentation {
    private Bundle args;
    @Override public void onCreate(Bundle input){super.onCreate(input);args=input;start();}
    private static String sha(byte[] bytes)throws Exception{StringBuilder out=new StringBuilder();for(byte b:MessageDigest.getInstance("SHA-256").digest(bytes))out.append(String.format("%02x",b&255));return out.toString();}
    @Override public void onStart(){
        Bundle result=new Bundle();ExecutorService owner=Executors.newSingleThreadExecutor();
        try{
            JSONObject report=owner.submit(()->{
                File folder=new File(getTargetContext().getFilesDir(),"export");folder.mkdirs();File source=new File(folder,"source.txt");byte[] bytes=new byte[1048576];for(int i=0;i<bytes.length;i++)bytes[i]=(byte)('a'+i%26);
                Files.write(source.toPath(),bytes);String expected=sha(bytes);long sdk=NativeSdk.open(new File(folder,"sdk.sqlite").getAbsolutePath());if(sdk==0)throw new AssertionError("SDK open failed");
                JSONArray checks=new JSONArray();try{
                    long[] imported=NativeSdk.importFile(sdk,source.getAbsolutePath(),1);if(imported[0]!=0||imported[1]<=0)throw new AssertionError("Public SDK import failed");
                    for(String name:new String[]{"fresh","existing","cancel-before","cancel-stream","limit"}){
                        File target=new File(folder,name+".txt");if(name.equals("existing"))Files.write(target.toPath(),"existing".getBytes(StandardCharsets.UTF_8));
                        int wanted=name.equals("fresh")?0:name.startsWith("cancel")?9:name.equals("limit")?6:3;
                        long cancel=name.equals("cancel-before")?0:name.equals("cancel-stream")?65536:-1;
                        String[] out=NativeSdk.exportOriginal(sdk,imported[1],target.getAbsolutePath(),cancel,name.equals("limit")?65536:0);
                        int code=Integer.parseInt(out[0]);long exported=Long.parseLong(out[1]);boolean ok=code==wanted;
                        if(code==0)ok&=exported==bytes.length&&sha(Files.readAllBytes(target.toPath())).equals(expected);
                        else ok&=exported==0;
                        if(name.equals("existing"))ok&=new String(Files.readAllBytes(target.toPath()),StandardCharsets.UTF_8).equals("existing");
                        else if(code!=0)ok&=!target.exists();
                        for(File file:folder.listFiles())if(file.getName().contains(".exr-export-"))ok=false;
                        checks.put(new JSONObject().put("name",name).put("ok",ok).put("status",code).put("expected",wanted).put("bytes",exported).put("message",out[2]));
                    }
                }finally{NativeSdk.close(sdk);}
                boolean ok=true;for(int i=0;i<checks.length();i++)ok&=checks.getJSONObject(i).getBoolean("ok");
                return new JSONObject().put("source_sha",args.getString("source_sha")).put("run_id",args.getString("run_id")).put("attempt",args.getString("attempt")).put("api",Build.VERSION.SDK_INT).put("abi",Build.SUPPORTED_ABIS[0]).put("sdk_owner",Thread.currentThread().getName()).put("sha256",expected).put("checks",checks).put("ok",ok);
            }).get();
            Files.write(new File(getTargetContext().getFilesDir(),"export-report.json").toPath(),report.toString(2).getBytes(StandardCharsets.UTF_8));
            result.putString("stream","EXR_SESSION_EXPORT_RECORDED\n");finish(report.getBoolean("ok")?Activity.RESULT_OK:Activity.RESULT_CANCELED,result);
        }catch(Throwable failure){result.putString("shortMsg","EXPORT_PROBE_FAILED "+failure.getClass().getName());finish(Activity.RESULT_CANCELED,result);}finally{owner.shutdown();}
    }
}
