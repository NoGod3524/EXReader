// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.util.AtomicFile;
import android.util.Base64;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileNotFoundException;
import java.io.FileOutputStream;
import java.io.IOException;
import java.util.HashSet;
import java.util.UUID;
import org.json.JSONArray;
import org.json.JSONObject;

/** One private durable request; uncertain responses reuse its exact capture/IDs. */
final class ReadingRequests {
    private static final int MAX_BYTES=1048576;
    private final Thread owner=Thread.currentThread();private final AtomicFile file;
    static final class Pending {
        final long sdkBook;final String book,id,revision,bootstrap,body;final String[] expected;
        final int kind,operation,mode;final ReadingCapture capture;
        Pending(long sdkBook,String book,String id,String revision,String bootstrap,String[] expected,int kind,int operation,int mode,ReadingCapture capture,String body){
            if(sdkBook<=0||book==null||!book.matches("[a-z0-9]+:[0-9a-f]{64}")||id==null||expected==null||expected.length>32||kind<1||kind>4||operation<0||operation>2||mode<1||mode>3||body==null)throw new IllegalArgumentException("Invalid private reading request");
            requireId(revision);requireId(bootstrap);if(!id.isEmpty())requireId(id);HashSet<String> unique=new HashSet<>();for(String head:expected){requireId(head);if(!unique.add(head))throw new IllegalArgumentException("Duplicate observed reading head");}
            if(capture!=null&&(!book.equals(capture.bookKey)||mode!=capture.mode))throw new IllegalArgumentException("Private reading capture identity differs");
            if(operation!=NativeReadingProduct.DELETE&&kind!=NativeReadingProduct.NOTE_TEXT&&capture==null)throw new IllegalArgumentException("A real retained capture is required");
            if(operation==NativeReadingProduct.DELETE&&capture!=null)throw new IllegalArgumentException("Delete names only the reading mode");
            ReadingCapture.encode(body,65536);if(body.indexOf('\0')>=0)throw new IllegalArgumentException("Reading body contains NUL");this.sdkBook=sdkBook;this.book=book;this.id=id;this.revision=revision;this.bootstrap=bootstrap;this.expected=expected.clone();this.kind=kind;this.operation=operation;this.mode=mode;this.capture=capture;this.body=body;
        }
    }
    ReadingRequests(File directory){file=new AtomicFile(new File(directory,"reading-request.json"));}
    private void owned(){if(Thread.currentThread()!=owner)throw new IllegalStateException("Reading requests require their SDK worker");}
    static String newId(){return UUID.randomUUID().toString().replace("-","");}
    static void requireId(String id){if(id==null||!id.matches("[0-9a-f]{32}"))throw new IllegalArgumentException("Invalid reading revision ID");}
    private static JSONObject capture(ReadingCapture value)throws Exception {
        if(value==null)return null;JSONArray numbers=new JSONArray(),route=new JSONArray(),bytes=new JSONArray();for(long number:value.numbers())numbers.put(Long.toUnsignedString(number));for(String text:value.route())route.put(text==null?JSONObject.NULL:text);for(byte[] selected:value.bytes())bytes.put(selected==null?JSONObject.NULL:Base64.encodeToString(selected,Base64.NO_WRAP));return new JSONObject().put("numbers",numbers).put("route",route).put("selectors",bytes);
    }
    private static ReadingCapture capture(JSONObject value)throws Exception {
        if(value==null)return null;JSONArray fields=value.getJSONArray("numbers"),path=value.getJSONArray("route"),selectors=value.getJSONArray("selectors");if(fields.length()!=4||path.length()!=5||selectors.length()!=3)throw new IOException("Invalid retained reading capture");long[] numbers=new long[4];String[] route=new String[5];byte[][] bytes=new byte[3][];for(int i=0;i<4;i++)numbers[i]=Long.parseUnsignedLong(fields.getString(i));for(int i=0;i<5;i++)route[i]=path.isNull(i)?null:path.getString(i);for(int i=0;i<3;i++){bytes[i]=selectors.isNull(i)?null:Base64.decode(selectors.getString(i),Base64.NO_WRAP);if(bytes[i]!=null&&bytes[i].length>(i==0?65536:128))throw new IOException("Retained selector exceeds its byte bound");}return new ReadingCapture(numbers,route,bytes);
    }
    Pending read()throws Exception {
        owned();byte[] encoded;try(FileInputStream input=file.openRead();ByteArrayOutputStream output=new ByteArrayOutputStream()){byte[] chunk=new byte[8192];for(int count;(count=input.read(chunk))>0;){if(output.size()+count>MAX_BYTES)throw new IOException("Private reading request exceeds its bound");output.write(chunk,0,count);}encoded=output.toByteArray();}catch(FileNotFoundException absent){return null;}
        JSONObject value=new JSONObject(ReadingCapture.decode(encoded));if(value.getInt("version")!=1||value.length()!=13||value.getInt("reserved")!=0)throw new IOException("Unknown private reading request version");for(String key:new String[]{"version","sdk_book","book","annotation","revision","bootstrap","expected","kind","operation","mode","capture","body","reserved"})if(!value.has(key))throw new IOException("Incomplete private reading request");JSONArray heads=value.getJSONArray("expected");if(heads.length()>32)throw new IOException("Retained heads exceed their bound");String[] expected=new String[heads.length()];for(int i=0;i<expected.length;i++)expected[i]=heads.getString(i);
        return new Pending(value.getLong("sdk_book"),value.getString("book"),value.getString("annotation"),value.getString("revision"),value.getString("bootstrap"),expected,value.getInt("kind"),value.getInt("operation"),value.getInt("mode"),value.isNull("capture")?null:capture(value.getJSONObject("capture")),value.getString("body"));
    }
    void save(Pending request)throws Exception {
        owned();Pending existing=read();if(existing!=null)throw new IOException("A previous reading save still needs confirmation");JSONArray heads=new JSONArray();for(String head:request.expected)heads.put(head);JSONObject captured=capture(request.capture);
        JSONObject value=new JSONObject().put("version",1).put("sdk_book",request.sdkBook).put("book",request.book).put("annotation",request.id).put("revision",request.revision).put("bootstrap",request.bootstrap).put("expected",heads).put("kind",request.kind).put("operation",request.operation).put("mode",request.mode).put("capture",captured==null?JSONObject.NULL:captured).put("body",request.body).put("reserved",0);
        byte[] encoded=ReadingCapture.encode(value.toString(),MAX_BYTES);FileOutputStream output=null;try{output=file.startWrite();output.write(encoded);file.finishWrite(output);output=null;}finally{if(output!=null)file.failWrite(output);}
    }
    void clear()throws IOException {owned();file.delete();if(file.getBaseFile().exists())throw new IOException("Reading save confirmation could not be cleared");}
}
