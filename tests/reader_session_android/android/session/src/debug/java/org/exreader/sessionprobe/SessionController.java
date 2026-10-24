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
import org.json.JSONArray;

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
    private static long[] readingIds(JSONObject saved)throws Exception{JSONArray rows=saved.getJSONArray("books");long[] ids=new long[5];for(int i=0;i<4;i++)ids[i]=rows.getJSONObject(i).getLong("sdk_id");ids[4]=saved.getLong("global_epub_id");return ids;}
    private File readingFont(File folder)throws Exception{
        File font=new File(folder,"primary.ttf");if(!font.exists())try(InputStream in=context.getAssets().open("reading/primary.ttf")){Files.copy(in,font.toPath());}return font;
    }
    private JSONObject readingInstall(File folder,boolean sender)throws Exception{
        String[] roles={"txt","epub","pdf","cbz"};int[] formats={1,4,8,9};
        JSONObject manifest;try(InputStream in=context.getAssets().open("reading/manifest.json")){manifest=new JSONObject(new String(in.readAllBytes(),StandardCharsets.UTF_8));}
        JSONArray books=new JSONArray();String database=new File(folder,"sdk.sqlite").getAbsolutePath();
        sdk(()->{
            long owner=NativeSdk.open(database);if(owner==0)throw new IllegalStateException("Reading SDK open failed");
            try{
                if(!sender){File spacer=new File(folder,"spacer.txt");try(InputStream in=context.getAssets().open("reading/spacer.txt")){Files.copy(in,spacer.toPath());}long[] imported=NativeSdk.importFile(owner,spacer.getAbsolutePath(),1);if(imported[0]!=0)throw new IllegalStateException("Reading spacer refused");}
                for(int n=0;n<4;n++){
                    JSONObject entry=manifest.getJSONObject(roles[n]);String sha=entry.getString("sha256");long bytes=entry.getLong("bytes");File source;
                    if(sender){source=new File(folder,entry.getString("file"));try(InputStream in=context.getAssets().open("reading/"+entry.getString("file"))){Files.copy(in,source.toPath());}}
                    else source=new File(folder,"cache/"+sha+"."+roles[n]);
                    if(source.length()!=bytes||!hash(source).equals(sha))throw new IllegalStateException("Reading original identity differs");
                    long[] imported=NativeSdk.importFile(owner,source.getAbsolutePath(),formats[n]);if(imported==null||imported[0]!=0||imported[1]<=0)throw new IllegalStateException("Reading SDK import refused");
                    if(sender){File original=new File(folder,"originals/"+sha+"."+roles[n]);String[] exported=NativeSdk.exportOriginal(owner,imported[1],original.getAbsolutePath(),-1,0);if(Integer.parseInt(exported[0])!=0||original.length()!=bytes||!hash(original).equals(sha))throw new IllegalStateException("Reading SDK export differs");}
                    books.put(new JSONObject().put("role",roles[n]).put("format",roles[n]).put("sha",sha).put("bytes",bytes).put("key",roles[n]+":"+sha).put("sdk_id",imported[1]).put("path",source.getAbsolutePath()).put("location",n==1?"epub_chapter":n>1?"fixed_page":"reflow_global"));
                }
            }finally{NativeSdk.close(owner);}return true;
        });
        long global=sdk(()->NativeSdk.readingGlobalImport(database,books.getJSONObject(1).getString("path")));if(global<=0)throw new IllegalStateException("Global EPUB import refused");
        JSONObject saved=new JSONObject().put("books",books).put("global_epub_id",global);
        for(int n=0;n<4;n++){
            JSONObject book=books.getJSONObject(n);String title="Remote "+book.getString("role");
            if(sender)product(()->decode(NativeProduct.prepareBook(productPath(folder),new File(folder,"reading-metadata-"+book.getString("role")+".pending").getAbsolutePath(),book.getString("format"),book.getString("sha"),book.getLong("bytes"),title,"云端作者",title)));
            else{
                JSONObject selected=product(()->decode(NativeProduct.inspectBook(productPath(folder),book.getString("key"))));if(selected.getInt("selection")!=4||selected.getInt("heads")!=1)throw new IllegalStateException("Unsafe reading metadata");
                JSONObject projected=product(()->decode(NativeProduct.projectBook(productPath(folder),book.getString("key"),selected.getString("head"),selected.getString("selected_title"))));if(projected.getInt("status")!=0)throw new IllegalStateException("Reading metadata projection refused");
            }
            JSONObject attached=product(()->decode(NativeProduct.attach(productPath(folder),book.getString("format"),book.getString("sha"),book.getLong("bytes"),book.getLong("sdk_id"),book.getString("location"),title,"云端作者",title)));if(attached.getInt("status")!=0)throw new IllegalStateException("Reading mapping refused");
        }
        readingFont(folder);Files.write(new File(folder,"reading-books.json").toPath(),saved.toString(2).getBytes(StandardCharsets.UTF_8));
        if(!sender){long[] audit=sdk(()->NativeSdk.readingAudit(database,readingIds(saved),true));if(audit[0]!=0||audit[1]!=audit[2])throw new IllegalStateException("Reading local progress setup refused");saved.put("initial_audit",new JSONArray(audit));}
        return saved;
    }
    private JSONObject readingPrepare(File folder)throws Exception{
        JSONObject saved=readingInstall(folder,true);String database=new File(folder,"sdk.sqlite").getAbsolutePath();
        JSONObject captured=sdk(()->decode(NativeSdk.readingCapture(database,readingIds(saved),readingFont(folder).getAbsolutePath())));JSONArray rows=captured.getJSONArray("captures");
        if(rows.length()!=18)throw new IllegalStateException("Eighteen real captures required");
        for(int n=0;n<rows.length();n++){
            JSONObject c=rows.getJSONObject(n);JSONObject book=saved.getJSONArray("books").getJSONObject(Math.min(c.getInt("route"),3));if(c.getInt("route")==4)book=saved.getJSONArray("books").getJSONObject(1);
            c.put("key",book.getString("key"));String[] fields={c.getString("kind"),c.getString("key"),c.getString("exact"),c.getString("prefix"),c.getString("suffix"),c.isNull("chapter")?null:c.optString("chapter",null),c.getInt("mode")==3?c.getString("page_id"):c.optString("part_path",""),c.getString("id"),captured.getString("parser_version")};
            long[] numbers={c.getInt("mode"),c.getInt("mode")==3?c.getLong("page"):c.optLong("part",0),c.getLong("start"),c.getLong("end")};JSONObject committed=product(()->decode(NativeProduct.readingAppend(productPath(folder),fields,numbers)));c.put("retained",committed);
        }
        captured.put("books",saved.getJSONArray("books")).put("global_epub_id",saved.getLong("global_epub_id"));return captured;
    }
    private JSONObject readingResolve(File folder,JSONObject command)throws Exception{
        JSONObject saved=new JSONObject(new String(Files.readAllBytes(new File(folder,"reading-books.json").toPath()),StandardCharsets.UTF_8));long[] ids=readingIds(saved);String database=new File(folder,"sdk.sqlite").getAbsolutePath();JSONArray rows=command.getJSONArray("captures"),results=new JSONArray();
        for(int n=0;n<rows.length();n++){
            JSONObject capture=rows.getJSONObject(n),retained=capture.getJSONObject("retained");JSONObject decoded=product(()->decode(NativeProduct.readingDecode(productPath(folder),retained.getString("revision"))));
            if(!decoded.getString("wire").equals(retained.getString("wire"))||!decoded.getString("sha256").equals(retained.getString("sha256"))||decoded.getInt("anchor_version")!=2||!decoded.getString("book_key").equals(capture.getString("key")))throw new IllegalStateException("Reading retained bytes differ");
            if(capture.getString("kind").equals("annotation")&&!decoded.getBoolean("safe_selected"))throw new IllegalStateException("Reading annotation is not safe selected");
            for(String field:new String[]{"mode","start","end","exact","prefix","suffix"})if(!String.valueOf(decoded.get(field)).equals(String.valueOf(capture.get(field))))throw new IllegalStateException("Reading selector differs: "+field);
            int mode=decoded.getInt("mode");String[] selector={decoded.getString("exact"),decoded.getString("prefix"),decoded.getString("suffix"),decoded.isNull("chapter")?null:decoded.getString("chapter"),mode==3?decoded.getString("page_id"):decoded.getString("part_path")};long unit=mode==3?decoded.getLong("page"):decoded.getLong("part");
            long[] match=sdk(()->NativeSdk.readingResolve(database,ids[capture.getInt("route")],mode,unit,decoded.getLong("start"),decoded.getLong("end"),selector,readingFont(folder).getAbsolutePath()));
            results.put(new JSONObject().put("id",capture.getString("id")).put("mode",mode).put("sdk_status",match[0]).put("state",match[1]).put("start",match[2]).put("end",match[3]).put("expected_start",capture.getLong("start")).put("expected_end",capture.getLong("end")).put("wire_sha256",decoded.getString("sha256")).put("safe_selected",decoded.getBoolean("safe_selected")));
        }
        long[] audit=sdk(()->NativeSdk.readingAudit(database,ids,false));return new JSONObject().put("cases",results).put("audit",new JSONArray(audit)).put("books",saved.getJSONArray("books"));
    }
    private JSONObject execute(JSONObject command)throws Exception{
        String action=command.getString("action"),name=command.optString("profile","A");File folder=profile(name);
        if(action.equals("prepare"))return prepare(folder,command);
        if(action.equals("restore"))return restore(folder,command);
        if(action.equals("prepare-reading"))return readingPrepare(folder);
        if(action.equals("restore-reading"))return readingInstall(folder,false);
        if(action.equals("resolve-reading"))return readingResolve(folder,command);
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
