// SPDX-License-Identifier: MIT
package org.exreader.sessionprobe;
import android.content.Context;
import android.content.BroadcastReceiver;
import android.os.Process;
import java.io.File;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.text.Normalizer;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.json.JSONObject;

/** Debug command harness. Production session/SDK/product behavior stays native. */
final class SessionController {
    private static SessionController instance;
    static synchronized SessionController get(Context context){if(instance==null)instance=new SessionController(context.getApplicationContext());return instance;}
    private final Context context;
    private final File files;
    private final ExecutorService controls=Executors.newSingleThreadExecutor(r->new Thread(r,"session-controls"));
    private final ExecutorService sdkOwner=Executors.newSingleThreadExecutor(r->new Thread(r,"sdk-owner"));
    private final ExecutorService productOwner=Executors.newSingleThreadExecutor(r->new Thread(r,"product-owner"));
    private final Map<String,Long> sessions=new HashMap<>();
    private SessionController(Context context){this.context=context;files=context.getFilesDir();if(NativeProduct.bind()!=0)throw new IllegalStateException("Android DAV binding refused");}
    static JSONObject decode(byte[] bytes)throws Exception{if(bytes==null)throw new IllegalStateException("Native result missing");JSONObject out=new JSONObject(new String(bytes,StandardCharsets.UTF_8));if(out.optBoolean("error"))throw new IllegalStateException("Native code "+out.optInt("code"));return out;}
    private <T>T sdk(Callable<T> action)throws Exception{return sdkOwner.submit(action).get();}
    private <T>T product(Callable<T> action)throws Exception{return productOwner.submit(action).get();}
    static String hash(File file)throws Exception{
        MessageDigest digest=MessageDigest.getInstance("SHA-256");byte[] bytes=new byte[65536];try(InputStream input=Files.newInputStream(file.toPath())){int got;while((got=input.read(bytes))!=-1)digest.update(bytes,0,got);}
        StringBuilder result=new StringBuilder();for(byte value:digest.digest())result.append(String.format("%02x",value&255));return result.toString();
    }
    private File profile(String name){if(!name.matches("[A-Za-z][A-Za-z0-9_-]{0,31}"))throw new IllegalArgumentException("Profile refused");File folder=new File(files,name);folder.mkdirs();new File(folder,"cache").mkdirs();new File(folder,"originals").mkdirs();return folder;}
    private JSONObject state(File profile)throws Exception{return new JSONObject(new String(Files.readAllBytes(new File(profile,"state.json").toPath()),StandardCharsets.UTF_8));}
    private void save(File profile,JSONObject state)throws Exception{Files.write(new File(profile,"state.json").toPath(),state.toString(2).getBytes(StandardCharsets.UTF_8));}
    private String productPath(File folder){return new File(folder,"product.sqlite").getAbsolutePath();}
    private JSONObject sdkState(long owner,long id)throws Exception{
        byte[][] raw=NativeSdk.inspect(owner,id);if(raw==null||raw.length!=8)throw new IllegalStateException("SDK inspection failed");String[] value=new String[8];for(int i=0;i<8;i++)value[i]=new String(raw[i],StandardCharsets.UTF_8);
        return new JSONObject().put("title",value[0]).put("author",value[1]).put("position",Long.parseLong(value[2])).put("favorite",Integer.parseInt(value[3])).put("format",Integer.parseInt(value[4])).put("bounded",Integer.parseInt(value[5])).put("books",Integer.parseInt(value[6])).put("bytes",Long.parseLong(value[7]));
    }
    private JSONObject prepare(File folder,JSONObject command)throws Exception{
        JSONObject original=sdk(()->{
            File source=new File(folder,"source.epub");try(InputStream asset=context.getAssets().open("source.epub")){Files.copy(asset,source.toPath());}
            String sha=hash(source);File staged=new File(folder,"originals/"+sha+".epub");long owner=NativeSdk.open(new File(folder,"sdk.sqlite").getAbsolutePath());if(owner==0)throw new IllegalStateException("SDK open failed");
            try{
                long[] imported=NativeSdk.importFile(owner,source.getAbsolutePath(),4);if(imported==null||imported[0]!=0||imported[1]<=0)throw new IllegalStateException("SDK import failed");
                String[] exported=NativeSdk.exportOriginal(owner,imported[1],staged.getAbsolutePath(),-1,0);
                if(Integer.parseInt(exported[0])!=0||Long.parseLong(exported[1])!=source.length()||!hash(staged).equals(sha))throw new IllegalStateException("SDK original export differs");
                JSONObject inspected=sdkState(owner,imported[1]);return new JSONObject().put("sha",sha).put("bytes",source.length()).put("format","epub").put("sdk_id",imported[1]).put("location",inspected.getInt("bounded")==1?"epub_chapter":"reflow_global").put("sdk",inspected);
            }finally{NativeSdk.close(owner);}
        });
        String title=command.getString("title"),author=command.getString("author"),sort=Normalizer.normalize(title,Normalizer.Form.NFC);
        JSONObject prepared=product(()->decode(NativeProduct.prepareBook(productPath(folder),new File(folder,"metadata.pending").getAbsolutePath(),"epub",original.getString("sha"),original.getLong("bytes"),title,author,sort)));
        original.put("key",prepared.getString("key")).put("head",prepared.getString("head")).put("bootstrap",prepared.getString("bootstrap")).put("metadata_committed",prepared.getInt("metadata_committed")).put("pending",prepared.getInt("pending"));
        JSONObject attached=product(()->decode(NativeProduct.attach(productPath(folder),"epub",original.getString("sha"),original.getLong("bytes"),original.getLong("sdk_id"),original.getString("location"),original.getJSONObject("sdk").getString("title"),original.getJSONObject("sdk").getString("author"),Normalizer.normalize(original.getJSONObject("sdk").getString("title"),Normalizer.Form.NFC))));
        if(attached.getInt("status")!=0)throw new IllegalStateException("Initial local mapping refused");save(folder,original);return original;
    }
    private JSONObject restore(File folder,JSONObject command)throws Exception{
        String sha=command.getString("sha"),key="epub:"+sha;long expected=command.getLong("bytes");File cached=new File(folder,"cache/"+sha+".epub");
        if(cached.length()!=expected||!hash(cached).equals(sha))throw new IllegalStateException("Verified remote cache differs");
        JSONObject imported=sdk(()->{
            long owner=NativeSdk.open(new File(folder,"sdk.sqlite").getAbsolutePath());if(owner==0)throw new IllegalStateException("SDK restore open failed");
            try{
                long[] value=NativeSdk.importFile(owner,cached.getAbsolutePath(),4);if(value==null||value[0]!=0||value[1]<=0)throw new IllegalStateException("SDK restore import failed");
                File verify=new File(folder,"sdk-verify-"+command.getInt("id")+".epub");String[] exported=NativeSdk.exportOriginal(owner,value[1],verify.getAbsolutePath(),-1,0);
                if(Integer.parseInt(exported[0])!=0||Long.parseLong(exported[1])!=expected||!hash(verify).equals(sha))throw new IllegalStateException("Restored SDK bytes differ");
                JSONObject inspected=sdkState(owner,value[1]);return new JSONObject().put("sdk_id",value[1]).put("created",value[2]).put("sdk",inspected).put("sha",sha).put("bytes",expected).put("key",key).put("location",inspected.getInt("bounded")==1?"epub_chapter":"reflow_global");
            }finally{NativeSdk.close(owner);}
        });
        JSONObject attached=product(()->decode(NativeProduct.attach(productPath(folder),"epub",sha,expected,imported.getLong("sdk_id"),imported.getString("location"),imported.getJSONObject("sdk").getString("title"),imported.getJSONObject("sdk").getString("author"),Normalizer.normalize(imported.getJSONObject("sdk").getString("title"),Normalizer.Form.NFC))));
        if(attached.getInt("status")!=0)throw new IllegalStateException("Restored local mapping refused");save(folder,imported);return imported;
    }
    private void cleanup(File folder)throws Exception{
        for(File entry:new File(folder,"cache").listFiles())if(entry.isFile()&&(entry.getName().startsWith(".reader-sync-")||entry.getName().startsWith(".exr-webdav-")))Files.delete(entry.toPath());
    }
    private JSONObject execute(JSONObject command)throws Exception{
        String action=command.getString("action"),name=command.optString("profile","A");File folder=profile(name);
        if(action.equals("prepare"))return prepare(folder,command);
        if(action.equals("restore"))return restore(folder,command);
        if(action.equals("inspect"))return product(()->decode(NativeProduct.inspectBook(productPath(folder),command.getString("key"))));
        if(action.equals("outbox"))return product(()->decode(NativeProduct.outbox(productPath(folder))));
        if(action.equals("project"))return product(()->decode(NativeProduct.projectBook(productPath(folder),command.getString("key"),command.getString("head"),Normalizer.normalize(command.getString("title"),Normalizer.Form.NFC))));
        if(action.equals("state"))return state(folder);
        if(action.equals("stats"))return product(()->decode(NativeProduct.stats()));
        if(action.equals("provider"))return product(()->decode(NativeProduct.provider()));
        if(action.equals("create")){
            if(sessions.containsKey(name))throw new IllegalStateException("Session already exists");cleanup(folder);
            long session=product(()->NativeProduct.create(productPath(folder),new File(folder,"cache").getAbsolutePath(),new File(folder,"originals").getAbsolutePath(),command.getString("account"),command.getString("root"),command.getString("authorization"),command.optInt("timeout",5000)));
            if(session==0)throw new IllegalStateException("Session create refused");sessions.put(name,session);return new JSONObject().put("created",true).put("pid",Process.myPid());
        }
        int code=action.equals("start")?1:action.equals("cancel")?2:action.equals("close")?3:action.equals("destroy")?4:action.equals("observe")?0:-1;
        if(code<0||!sessions.containsKey(name))throw new IllegalArgumentException("Session command refused");long token=sessions.get(name);
        JSONObject value=product(()->decode(NativeProduct.command(token,code)));if(!value.getBoolean("alive"))sessions.remove(name);return value;
    }
    void request(int id,BroadcastReceiver.PendingResult pending){controls.execute(()->{
        File input=new File(files,"request-"+id+".json");JSONObject response;
        try{JSONObject command=new JSONObject(new String(Files.readAllBytes(input.toPath()),StandardCharsets.UTF_8));Files.delete(input.toPath());command.put("id",id);response=execute(command).put("ok",true);}
        catch(Throwable failure){response=new JSONObject();while(failure.getCause()!=null)failure=failure.getCause();try{response.put("ok",false).put("failure",failure.getClass().getName()).put("message",failure.getMessage());}catch(Exception ignored){}}
        try{response.put("pid",Process.myPid());Files.write(new File(files,"reply-"+id+".json").toPath(),response.toString(2).getBytes(StandardCharsets.UTF_8));}catch(Exception ignored){}
        finally{pending.finish();}
    });}
}
