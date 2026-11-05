// SPDX-License-Identifier: MIT
package org.exreader.host;
import android.app.Activity;
import android.app.Instrumentation;
import android.os.Bundle;
import android.os.Debug;
import android.os.SystemClock;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.Arrays;

/** Diagnostic costs on the original 2202-source seed. No UI performance acceptance. */
public final class StartupCostTest extends Instrumentation {
    private Bundle arguments;
    @Override public void onCreate(Bundle args){super.onCreate(args);arguments=args;start();}
    private static void require(boolean value,String message){if(!value)throw new AssertionError(message);}
    private static long now(){return SystemClock.elapsedRealtimeNanos();}
    @Override public void onStart(){
        Bundle result=new Bundle();
        try{
            File directory=getTargetContext().getFilesDir(), database=new File(directory,"library.db");
            require(database.isFile(),"Original UI seed is required");
            JSONObject report=new JSONObject().put("source_sha",arguments.getString("source_sha"))
                .put("run_id",arguments.getString("run_id")).put("attempt",arguments.getString("attempt"))
                .put("slot",Integer.parseInt(arguments.getString("slot")))
                .put("api",android.os.Build.VERSION.SDK_INT).put("abi",android.os.Build.SUPPORTED_ABIS[0])
                .put("f08_accepted",false).put("filesystem_cache_cold",false);
            long started=now(),cpu=Debug.threadCpuTimeNanos();
            try(BookStore store=new BookStore(getTargetContext(),database)){
                report.put("bookstore_open_wall_ns",now()-started).put("bookstore_open_cpu_ns",Debug.threadCpuTimeNanos()-cpu);
                require(!store.metadataRepairPending()&&store.books().size()==2202,"Complete original seed");
            }
            started=now();
            try(CatalogStore catalog=new CatalogStore(getTargetContext(),new File(directory,"reader-catalog.db"));
                NativeLibrary library=new NativeLibrary(database.getPath())){
                report.put("warm_owner_open_wall_ns",now()-started);
                started=now();NativeLibrary.Book[] books=library.books();report.put("sdk_books_wall_ns",now()-started);
                require(books.length==2202,"Exact original book count");
                String[] keys=new String[books.length];String[][] expected=new String[books.length][];
                JSONArray rows=new JSONArray();long[] sums=new long[3];
                for(int i=0;i<books.length;i++){
                    long a=now();boolean exists=catalog.hasLocalBook(books[i].id);long b=now();
                    CatalogStore.ShelfBook book=catalog.localShelfBook(books[i].id);long c=now();
                    require(exists&&book!=null,"Original mapping retained");
                    keys[i]=book.key.bookKey;expected[i]=NativeCatalog.heads(catalog.nativeOwner(),"book",keys[i]);long d=now();
                    require(expected[i].length>0,"Original history retained");
                    long[] costs={b-a,c-b,d-c};for(int j=0;j<3;j++)sums[j]+=costs[j];
                    rows.put(new JSONObject().put("sdk_id",books[i].id).put("has_local_ns",costs[0])
                        .put("lookup_ns",costs[1]).put("heads_ns",costs[2]));
                }
                report.put("query_rows",rows).put("has_local_wall_ns",sums[0]).put("lookup_wall_ns",sums[1]).put("heads_wall_ns",sums[2]);
                JSONArray comparisons=new JSONArray();
                for(String kind:new String[]{"selection","heads","heads","selection"}){
                    started=now();cpu=Debug.threadCpuTimeNanos();int verified=0,heads=0;
                    for(int i=0;i<keys.length;i++){
                        String[] values="heads".equals(kind)?NativeCatalog.heads(catalog.nativeOwner(),"book",keys[i]):
                            NativeCatalog.selection(catalog.nativeOwner(),"book",keys[i]);
                        if("selection".equals(kind)){
                            require(!"0".equals(values[0]),"Selection retained");
                            values=Arrays.copyOfRange(values,3,values.length);
                        }
                        require(Arrays.equals(values,expected[i]),"Exactly the same observed heads");verified++;heads+=values.length;
                    }
                    comparisons.put(new JSONObject().put("query",kind).put("wall_ns",now()-started)
                        .put("cpu_ns",Debug.threadCpuTimeNanos()-cpu).put("verified_books",verified).put("heads",heads));
                }
                JSONArray keyComparisons=new JSONArray();
                require(NativeCatalog.localKey(catalog.nativeOwner(),Long.MAX_VALUE)==null,"Missing local mapping stays absent");
                for(String kind:new String[]{"lookup","local_key","local_key","lookup"}){
                    started=now();cpu=Debug.threadCpuTimeNanos();int verified=0;
                    for(int i=0;i<books.length;i++){
                        String value="local_key".equals(kind)?NativeCatalog.localKey(catalog.nativeOwner(),books[i].id):
                            catalog.localShelfBook(books[i].id).key.bookKey;
                        require(keys[i].equals(value),"Exactly the same visible local key");verified++;
                    }
                    keyComparisons.put(new JSONObject().put("query",kind).put("wall_ns",now()-started)
                        .put("cpu_ns",Debug.threadCpuTimeNanos()-cpu).put("verified_books",verified));
                }
                report.put("key_comparisons",keyComparisons);
                report.put("comparisons",comparisons).put("books",books.length);
            }
            Files.write(new File(directory,"f08-startup-cost.json").toPath(),report.toString(2).getBytes(StandardCharsets.UTF_8));
            result.putString("stream","F08_STARTUP_COST_OK\n");finish(Activity.RESULT_OK,result);
        }catch(Throwable error){
            result.putString("stream","F08_STARTUP_COST_FAILED "+android.util.Log.getStackTraceString(error));
            finish(Activity.RESULT_CANCELED,result);
        }
    }
}
