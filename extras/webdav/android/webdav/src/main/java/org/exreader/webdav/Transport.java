// SPDX-License-Identifier: MIT
package org.exreader.webdav;

import android.os.Looper;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.Proxy;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.concurrent.TimeUnit;
import javax.net.ssl.SSLException;
import okhttp3.Authenticator;
import okhttp3.ConnectionPool;
import okhttp3.CookieJar;
import okhttp3.Headers;
import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Protocol;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;
import okio.BufferedSink;
import org.xmlpull.v1.XmlPullParser;
import org.xmlpull.v1.XmlPullParserException;
import org.xmlpull.v1.XmlPullParserFactory;

/** Private JNI support for the C ABI. URL policy, DAV semantics and files remain native. */
public final class Transport {
    private Transport() { }
    private static final int IO=3,TLS=4,LIMIT=8,FORMAT=9,ARGUMENT=1,MEMORY=2;
    private static final byte[] PROPFIND=("<?xml version=\"1.0\"?><d:propfind xmlns:d=\"DAV:\"><d:prop><d:displayname/>"
        +"<d:resourcetype/><d:getcontentlength/><d:getetag/></d:prop></d:propfind>").getBytes(StandardCharsets.UTF_8);
    private static final class Failure extends IOException {
        final int code;
        Failure(int code){super("Android DAV operation refused");this.code=code;}
    }
    private static final class Client {
        // One native client is used serially; native code owns its thread/reentry guard.
        final OkHttpClient http=new OkHttpClient.Builder().proxy(Proxy.NO_PROXY)
            .protocols(Collections.singletonList(Protocol.HTTP_1_1)).followRedirects(false).followSslRedirects(false)
            .retryOnConnectionFailure(false).authenticator(Authenticator.NONE).proxyAuthenticator(Authenticator.NONE)
            .cookieJar(CookieJar.NO_COOKIES).connectionPool(new ConnectionPool(1,30,TimeUnit.SECONDS)).build();
        boolean closed;
    }
    private static final class Exchange {
        final Thread owner=Thread.currentThread();
        final Response response;
        final InputStream input;
        Exchange(Response response)throws IOException {
            this.response=response;
            this.input=response.body()==null?new ByteArrayInputStream(new byte[0]):response.body().byteStream();
        }
        void requireOwner()throws IOException {if(Thread.currentThread()!=owner)throw new Failure(ARGUMENT);}
    }
    private static native int readUpload(long token,byte[] bytes)throws IOException;

    static Object createClient()throws IOException {if(Looper.myLooper()==Looper.getMainLooper())throw new Failure(ARGUMENT);return new Client();}
    static Object execute(Object opaque,String target,String method,String authorization,int remainingMillis,long token,long length)throws IOException {
        Client client=(Client)opaque;
        if(client.closed||remainingMillis<=0||remainingMillis>120000||!target.startsWith("https://"))throw new Failure(ARGUMENT);
        OkHttpClient bounded=client.http.newBuilder().callTimeout(remainingMillis,TimeUnit.MILLISECONDS)
            .connectTimeout(remainingMillis,TimeUnit.MILLISECONDS).readTimeout(remainingMillis,TimeUnit.MILLISECONDS)
            .writeTimeout(remainingMillis,TimeUnit.MILLISECONDS).build();
        RequestBody body=null;
        Request.Builder request=new Request.Builder().url(target).header("Accept-Encoding","identity");
        if(authorization!=null&&!authorization.isEmpty())request.header("Authorization",authorization);
        if(method.equals("PROPFIND")){
            body=RequestBody.create(PROPFIND,MediaType.get("application/xml; charset=utf-8"));request.header("Depth","1");
        } else if(method.equals("PUT")) {
            request.header("If-None-Match","*");
            body=new RequestBody(){
                @Override public MediaType contentType(){return MediaType.get("application/octet-stream");}
                @Override public long contentLength(){return length;}
                @Override public void writeTo(BufferedSink sink)throws IOException{
                    byte[] chunk=new byte[65536];long sent=0;
                    while(sent<length){int got=readUpload(token,chunk);if(got<=0||got>chunk.length||got>length-sent)throw new Failure(IO);sink.write(chunk,0,got);sent+=got;}
                }
            };
        } else if(!method.equals("GET")&&!method.equals("MKCOL"))throw new Failure(ARGUMENT);
        Response response=bounded.newCall(request.method(method,body).build()).execute();
        try{return new Exchange(response);}catch(Throwable error){response.close();throw error;}
    }
    static int status(Object opaque)throws IOException {Exchange x=(Exchange)opaque;x.requireOwner();return x.response.code();}
    /** Preserve repeated values so native code can refuse conflicting lengths/locations. */
    static String[] headers(Object opaque)throws IOException {
        Exchange x=(Exchange)opaque;x.requireOwner();Headers headers=x.response.headers();long bytes=0;
        for(int i=0;i<headers.size();i++){
            bytes+=headers.name(i).getBytes(StandardCharsets.UTF_8).length+headers.value(i).getBytes(StandardCharsets.UTF_8).length+4;
            if(bytes>32768)throw new Failure(LIMIT);
        }
        String[] result=new String[headers.size()*2];for(int i=0;i<headers.size();i++){result[i*2]=headers.name(i);result[i*2+1]=headers.value(i);}return result;
    }
    static int read(Object opaque,byte[] bytes)throws IOException {Exchange x=(Exchange)opaque;x.requireOwner();return x.input.read(bytes);}
    static void closeExchange(Object opaque)throws IOException {if(opaque!=null){Exchange x=(Exchange)opaque;x.requireOwner();x.response.close();}}
    static void closeClient(Object opaque){
        if(opaque==null)return;Client client=(Client)opaque;if(client.closed)return;client.closed=true;
        client.http.connectionPool().evictAll();
        // Synchronous execute does not submit dispatcher tasks.
        client.http.dispatcher().executorService().shutdown();
    }
    static int errorCode(Throwable error,int fallback){
        if(error instanceof Failure)return ((Failure)error).code;
        if(error instanceof OutOfMemoryError)return MEMORY;
        if(error instanceof SSLException)return TLS;
        return fallback;
    }

    private static final class Parser {
        final Thread owner=Thread.currentThread();
        final XmlPullParser xml;
        String name="",namespace="",text="";
        Parser(byte[] bytes)throws XmlPullParserException{
            XmlPullParserFactory factory=XmlPullParserFactory.newInstance();factory.setNamespaceAware(true);xml=factory.newPullParser();
            xml.setFeature(XmlPullParser.FEATURE_PROCESS_NAMESPACES,true);
            xml.setFeature(XmlPullParser.FEATURE_PROCESS_DOCDECL,false);
            xml.setInput(new ByteArrayInputStream(bytes),null);
        }
        int next()throws IOException,XmlPullParserException{
            if(Thread.currentThread()!=owner)throw new Failure(ARGUMENT);
            name=namespace=text="";
            for(;;){
                int event=xml.nextToken();
                if(event==XmlPullParser.END_DOCUMENT)return 0;
                if(event==XmlPullParser.DOCDECL)throw new Failure(FORMAT);
                if(event==XmlPullParser.START_TAG){name=xml.getName();namespace=xml.getNamespace();return 1;}
                if(event==XmlPullParser.END_TAG)return 2;
                if(event==XmlPullParser.ENTITY_REF){
                    String entity=xml.getName();
                    if(entity==null||!(entity.equals("amp")||entity.equals("lt")||entity.equals("gt")||entity.equals("apos")||entity.equals("quot")||entity.startsWith("#"))||xml.getText()==null)
                        throw new Failure(FORMAT);
                    text=xml.getText();
                } else if(event==XmlPullParser.TEXT||event==XmlPullParser.CDSECT||event==XmlPullParser.IGNORABLE_WHITESPACE)text=xml.getText();
                else continue;
                if(text!=null&&text.length()>65536)throw new Failure(LIMIT);return 3;
            }
        }
    }
    static Object parser(byte[] bytes)throws XmlPullParserException{return new Parser(bytes);}
    static int next(Object opaque)throws IOException,XmlPullParserException{return ((Parser)opaque).next();}
    static String[] event(Object opaque){Parser p=(Parser)opaque;return new String[]{p.name,p.namespace,p.text};}
}
