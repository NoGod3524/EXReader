// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.graphics.Bitmap;
import java.nio.ByteBuffer;
import java.security.MessageDigest;
import java.util.Locale;

/** The actual CBZ renderer and its public anchor resolver share one SDK doc. */
final class NativeCbz implements AutoCloseable {
    static {System.loadLibrary("exreader_host");}
    private final Thread owner=Thread.currentThread();
    final String sourceKey;
    private long handle;
    private final String[] pages;
    static final class Frame {
        final int[] meta;final byte[] pixels,text;final String pageId;
        Frame(int[] meta,byte[] pixels,byte[] text,String id){
            if(meta==null||meta.length!=7||meta[3]!=4||meta[4]!=1||text==null||text.length!=meta[5]||meta[6]!=0||pixels==null||(long)meta[2]*meta[1]!=pixels.length||id==null||id.isEmpty())throw new IllegalStateException("Incomplete real CBZ SDK frame");
            this.meta=meta;this.pixels=pixels;this.text=text;pageId=id;
        }
        Bitmap bitmap(){
            Bitmap bitmap=Bitmap.createBitmap(meta[0],meta[1],Bitmap.Config.ARGB_8888);
            try{
                if(meta[2]==meta[0]*4)bitmap.copyPixelsFromBuffer(ByteBuffer.wrap(pixels));
                else{byte[] packed=new byte[meta[0]*meta[1]*4];for(int y=0;y<meta[1];y++)System.arraycopy(pixels,y*meta[2],packed,y*meta[0]*4,meta[0]*4);bitmap.copyPixelsFromBuffer(ByteBuffer.wrap(packed));}
                return bitmap;
            }catch(RuntimeException|Error error){bitmap.recycle();throw error;}
        }
    }
    NativeCbz(byte[] bytes,HostTask task)throws Exception{
        MessageDigest sha=MessageDigest.getInstance("SHA-256");StringBuilder key=new StringBuilder("cbz:");for(byte value:sha.digest(bytes))key.append(String.format(Locale.ROOT,"%02x",value&255));sourceKey=key.toString();
        task.check();handle=nativeOpen(bytes,sourceKey,task);if(handle==0)throw new IllegalStateException("CBZ renderer did not open");
        try{pages=nativePages(handle);if(pages==null||pages.length==0)throw new IllegalStateException("CBZ has no actual SDK pages");}
        catch(Exception|Error error){nativeClose(handle);handle=0;throw error;}
    }
    private long checked(){if(Thread.currentThread()!=owner)throw new IllegalStateException("CBZ belongs to its SDK worker");if(handle==0)throw new IllegalStateException("CBZ renderer closed");return handle;}
    int count(){checked();return pages.length;}
    String pageId(int at){checked();if(at<0||at>=pages.length)throw new IllegalArgumentException("CBZ page outside real directory");return pages[at];}
    int identity(){return System.identityHashCode(this);}
    Frame render(int page,double scale,HostTask task)throws Exception{task.check();Frame frame=nativeRender(checked(),page,scale,task);task.check();if(!pageId(page).equals(frame.pageId))throw new IllegalStateException("CBZ renderer page identity changed");return frame;}
    NativeReadingSdk.Match resolve(ReadingCapture capture,HostTask task)throws Exception{
        checked();task.check();if(capture==null||capture.mode!=ReadingCapture.FIXED||!sourceKey.equals(capture.bookKey)||!NativeReadingSdk.acceptsParser(capture.parser))throw new IllegalArgumentException("CBZ source or parser identity differs");
        NativeReadingSdk.Match match=nativeResolve(handle,capture.pageId,capture.start,capture.end,capture.bytes(),task);task.check();
        if(match.found()&&(!sourceKey.equals(match.recaptured.bookKey)||!pageId((int)match.unit).equals(match.recaptured.pageId)))throw new IllegalStateException("Current CBZ renderer returned another source/page");return match;
    }
    @Override public void close(){if(handle==0)return;checked();nativeClose(handle);handle=0;}
    private static native long nativeOpen(byte[] bytes,String key,HostTask task);
    private static native String[] nativePages(long handle);
    private static native Frame nativeRender(long handle,int page,double scale,HostTask task);
    private static native NativeReadingSdk.Match nativeResolve(long handle,String pageId,long start,long end,byte[][] selectors,HostTask task);
    private static native void nativeClose(long handle);
}
