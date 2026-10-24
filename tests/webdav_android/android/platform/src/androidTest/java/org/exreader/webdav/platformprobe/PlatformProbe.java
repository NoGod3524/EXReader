// SPDX-License-Identifier: MIT
package org.exreader.webdav.platformprobe;

import android.app.Activity;
import android.app.Instrumentation;
import android.os.Build;
import android.os.Bundle;
import android.os.SystemClock;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.File;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.Proxy;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import javax.net.ssl.HttpsURLConnection;

/** Public API capability measurement; never an Android DAV backend acceptance. */
public final class PlatformProbe extends Instrumentation {
    private Bundle args;
    @Override public void onCreate(Bundle arguments){super.onCreate(arguments);args=arguments;start();}
    private HttpsURLConnection connection(String resource,int timeout)throws Exception{
        HttpsURLConnection c=(HttpsURLConnection)new URL(args.getString("root")+resource).openConnection(Proxy.NO_PROXY);
        c.setInstanceFollowRedirects(false);c.setConnectTimeout(timeout);c.setReadTimeout(timeout);c.setUseCaches(false);
        c.setRequestProperty("Accept-Encoding","identity");return c;
    }
    @Override public void onStart(){
        Bundle result=new Bundle();try {
            JSONObject report=new JSONObject().put("source_sha",args.getString("source_sha")).put("run_id",args.getString("run_id"))
                .put("attempt",args.getString("attempt")).put("api",Build.VERSION.SDK_INT).put("abi",Build.SUPPORTED_ABIS[0])
                .put("backend_accepted",false).put("platform_probe_recorded",true);
            JSONArray methods=new JSONArray();
            for(String method:new String[]{"GET","PUT","PROPFIND","MKCOL"}){
                HttpsURLConnection c=connection("ok",2000);JSONObject row=new JSONObject().put("method",method);
                try {c.setRequestMethod(method);row.put("accepted",true);}
                catch(java.net.ProtocolException unsupported){row.put("accepted",false).put("exception",unsupported.getClass().getName());}
                finally {c.disconnect();}methods.put(row);
            }
            report.put("methods",methods);
            HttpsURLConnection positive=connection("ok",2000);
            try(InputStream input=positive.getInputStream()){
                if(positive.getResponseCode()!=200||input.read()!=69)throw new AssertionError("Fixture TLS positive failed");
                report.put("platform_class",positive.getClass().getName()).put("trusted_fixture_tls_verified",true);
            }finally{positive.disconnect();}
            HttpsURLConnection read=connection("slow",150);long started=SystemClock.elapsedRealtime();
            try {read.getInputStream().close();throw new AssertionError("Delayed read unexpectedly completed");}
            catch(java.net.SocketTimeoutException expected){report.put("read_timeout_observed",true).put("read_elapsed_ms",SystemClock.elapsedRealtime()-started);}
            finally{read.disconnect();}
            HttpsURLConnection write=connection("write-block",150);write.setRequestMethod("PUT");write.setDoOutput(true);
            write.setFixedLengthStreamingMode(16L*1024*1024);write.setConnectTimeout(2000);started=SystemClock.elapsedRealtime();long sent=0;
            try(OutputStream output=write.getOutputStream()){
                report.put("write_output_opened",true);byte[] chunk=new byte[65536];for(int n=0;n<256;n++){output.write(chunk);sent+=chunk.length;}output.flush();
                report.put("write_result","completed");
            }catch(java.io.IOException expected){report.put("write_result",expected.getClass().getName());}
            finally{report.put("write_elapsed_ms",SystemClock.elapsedRealtime()-started).put("write_bytes_sent",sent).put("configured_read_timeout_ms",150);write.disconnect();}
            Files.write(new File(getTargetContext().getFilesDir(),"platform-report.json").toPath(),report.toString(2).getBytes(StandardCharsets.UTF_8));
            result.putString("stream","EXR_WEBDAV_PLATFORM_PROBE_RECORDED\n");finish(Activity.RESULT_OK,result);
        }catch(Throwable error){result.putString("shortMsg","PLATFORM_PROBE_FAILED "+error.getClass().getName());finish(Activity.RESULT_CANCELED,result);}
    }
}
