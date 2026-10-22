// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.graphics.Bitmap;
import android.graphics.RectF;
import android.util.Log;
import java.nio.ByteBuffer;

/** Worker-owned chapter pager over the library original. No document snapshot. */
final class BoundedEpub implements AutoCloseable {
    static { System.loadLibrary("exreader_host"); }
    static final class Frame {
        final long[] meta, spans;
        final float[] geometry;
        final byte[] text, pixels;
        Frame(long[] meta, long[] spans, float[] geometry, byte[] text, byte[] pixels) {
            this.meta=meta; this.spans=spans; this.geometry=geometry; this.text=text; this.pixels=pixels;
        }
    }
    final NativeLibrary library;
    final long book;
    final byte[] font;
    final String[][] parts;
    long handle;
    int part, index=-1, chapterPage=-1;
    long start, nextCalls, recoveryCalls;
    float size;
    boolean closed;
    boolean unresolvedProgress;
    String unresolvedNotice;

    BoundedEpub(NativeLibrary library,long book,byte[] font,float size) {
        this.library=library; this.book=book; this.font=font; this.size=size;
        parts=nativeParts(library.checked(),book);
        part=readingPart(0,1);
        if(part<0) throw new IllegalStateException("EPUB has no reading chapters");
    }
    private int readingPart(int from,int direction) {
        for(int p=from;p>=0 && p<parts.length;p+=direction) if("1".equals(parts[p][1])) return p;
        return -1;
    }
    private long open(int target,float fontSize,HostTask task) throws Exception {
        task.check();
        return nativeOpen(library.checked(),book,target,font,fontSize,task);
    }
    private Frame next(long pager,HostTask task,boolean recovery,boolean render) throws Exception {
        task.check(); long before=nativeCalls(pager);
        try { return nativeNext(pager,task,render); }
        finally { long calls=nativeCalls(pager)-before; nextCalls+=calls; if(recovery) recoveryCalls+=calls; }
    }
    private void log() {
        Log.i("EXRHost","paging {\"book\":"+book+",\"index\":"+index+",\"part\":"+part+
                ",\"local_start\":"+start+",\"native_next_calls\":"+nextCalls+",\"recovery_calls\":"+recoveryCalls+"}");
    }
    PageLoad restore(int displayIndex,HostTask task) throws Exception {
        String[] location=nativeProgress(library.checked(),book);
        if(location==null) return prepare(part,0,0,-1,size,task);
        int target=Integer.parseInt(location[0]);
        long resolver=open(target,size,task); long[] match;
        try { match=nativeResolve(resolver,location,task); } finally { nativeClose(resolver); }
        boolean exact=match[0]==1;
        long offset=exact?match[1]:Math.max(0,Long.parseLong(location[2]));
        PageLoad load=prepare(target,Math.max(0,displayIndex),-1,offset,size,task);
        if(!exact) {
            load.snapshot.preserveProgress=true;
            load.snapshot.restoreNotice="Saved position is not exact (state "+match[0]+"); opened at stored chapter offset "+offset+". Original selector retained.";
        }
        return load;
    }
    PageLoad seek(NativeLibrary.Note note,HostTask task) throws Exception {
        if(note.location==null) throw new IllegalArgumentException("Missing chapter annotation route");
        int target=Integer.parseInt(note.location[0]);
        long[] match=resolve(target,note.location,task);
        PageLoad load=prepare(target,0,-1,match[1],size,task);
        load.snapshot.highlightStart=match[1]; load.snapshot.highlightEnd=match[2]; return load;
    }
    private long[] resolve(int target,String[] location,HostTask task) throws Exception {
        long candidate=open(target,size,task);
        try {
            long[] match=nativeResolve(candidate,location,task);
            if(match[0]!=1) throw new IllegalArgumentException("Saved position is not exact (state "+match[0]+")");
            return match;
        } finally { nativeClose(candidate); }
    }
    PageLoad next(HostTask task) throws Exception {
        if(handle==0) return prepare(part,index+1,chapterPage+1,-1,size,task);
        long began=System.nanoTime();
        try {
            Frame frame=next(handle,task,false,true);
            if(frame==null) {
                int target=readingPart(part+1,1);
                return target<0?null:prepare(target,index+1,0,-1,size,task);
            }
            PageSnapshot page=snapshot(frame,index+1,part,handle);
            page.layoutFont=size;
            page.boundedHandle=handle;
            return new PageLoad(page,(System.nanoTime()-began)/1000000L,
                    ()->{ index=page.index; chapterPage++; start=page.start; unresolvedProgress=false; log(); }, this::recover);
        } catch(Exception|Error error) { recover(); throw error; }
    }
    PageLoad previous(HostTask task) throws Exception {
        if(index<=0) return null;
        if(chapterPage>0) return prepare(part,index-1,chapterPage-1,-1,size,task);
        int previous=readingPart(part-1,-1);
        return previous<0?null:prepare(previous,index-1,-2,-1,size,task);
    }
    PageLoad font(float value,HostTask task) throws Exception {
        PageLoad load=prepare(part,index,-1,start,value,task);
        if(unresolvedProgress) { load.snapshot.preserveProgress=true; load.snapshot.restoreNotice=unresolvedNotice; }
        return load;
    }
    private PageLoad prepare(int target,int display,int pageTarget,long offset,float value,HostTask task) throws Exception {
        return prepare(target,display,pageTarget,offset,value,task,false);
    }
    private PageLoad prepare(int target,int display,int pageTarget,long offset,float value,HostTask task,boolean recovery) throws Exception {
        if(closed) throw new IllegalStateException("Reader is closed");
        long candidate=open(target,value,task),began=System.nanoTime();
        boolean transferred=false;
        try {
            Frame selected=null; int selectedPage=-1;
            for(int p=0;p<20000;p++) {
                Frame frame=next(candidate,task,recovery,false);
                if(frame==null) break;
                if(pageTarget==-2) { selected=frame; selectedPage=p; continue; }
                if(pageTarget>=0?p!=pageTarget:!(offset>=frame.meta[0] && offset<frame.meta[1])) continue;
                selected=frame; selectedPage=p; break;
            }
            if(selected==null) throw new IllegalArgumentException("Chapter position has no page");
            selected=nativeRender(candidate,task);
            PageSnapshot snapshot=snapshot(selected,Math.max(0,display),target,candidate);
            snapshot.layoutFont=value;
            snapshot.boundedHandle=candidate;
            final long accepted=candidate; final int at=selectedPage;
            PageLoad result=new PageLoad(snapshot,(System.nanoTime()-began)/1000000L,()->{
                if(handle!=0) nativeClose(handle);
                handle=accepted; part=target; index=snapshot.index; chapterPage=at; start=snapshot.start; size=value; log();
                unresolvedProgress=snapshot.preserveProgress; unresolvedNotice=snapshot.restoreNotice;
            },()->nativeClose(accepted));
            transferred=true; return result;
        } finally { if(!transferred) nativeClose(candidate); }
    }
    /** A discarded sequential page must return to the last accepted cursor. */
    private void recover() {
        if(handle!=0) nativeClose(handle); handle=0;
        if(closed || chapterPage<0) return;
        HostTask task=new HostTask(()->false);
        long restored=0;
        try {
            restored=open(part,size,task);
            for(int p=0;p<=chapterPage;p++) if(next(restored,task,true,false)==null) throw new IllegalStateException("Recovery page missing");
            handle=restored; restored=0;
        } catch(Exception error) { Log.w("EXRHost","Bounded cursor recovery: "+error.getMessage()); }
        finally { if(restored!=0) nativeClose(restored); }
    }
    void refresh() { recover(); }
    PageLoad retryFrame(PageSnapshot previous,HostTask task) throws Exception {
        float value=previous.layoutFont;
        long resolver=open(previous.part,value,task); long[] match;
        try { match=nativeResolve(resolver,previous.boundedLocation,task); } finally { nativeClose(resolver); }
        boolean exact=match[0]==1;
        PageLoad load=prepare(previous.part,previous.index,-1,exact?match[1]:previous.start,value,task,true);
        if(!exact) {
            load.snapshot.preserveProgress=true;
            load.snapshot.restoreNotice="Saved position is not exact (state "+match[0]+"); rebuilt at stored chapter offset. Original selector retained.";
        }
        return load;
    }
    void saveProgress(PageSnapshot page) {
        nativeSaveProgress(page.boundedHandle,library.checked(),book,page.part,page.start);
    }
    static void storeProgress(NativeLibrary library,PageSnapshot page) {
        nativeSaveProgress(page.boundedHandle,library.checked(),page.bookId,page.part,page.start);
    }
    void saveNote(long id,long begin,long end,String text) {
        nativeSaveNote(handle,library.checked(),book,part,id,begin,end,text);
    }
    private PageSnapshot snapshot(Frame frame,int display,int target,long pager) {
        int glyphs=(int)frame.meta[5],lines=(int)frame.meta[6],width=(int)frame.meta[2],height=(int)frame.meta[3];
        Bitmap bitmap=Bitmap.createBitmap(width,height,Bitmap.Config.ARGB_8888);
        try {
            if(frame.meta[4]!=(long)width*4) throw new IllegalStateException("Unexpected bitmap stride");
            bitmap.copyPixelsFromBuffer(ByteBuffer.wrap(frame.pixels));
            long[] starts=new long[glyphs],ends=new long[glyphs];
            float[] x=new float[glyphs],baseline=new float[glyphs],advance=new float[glyphs],sizes=new float[glyphs];
            for(int i=0;i<glyphs;i++) { starts[i]=frame.spans[i*2]; ends[i]=frame.spans[i*2+1];
                x[i]=frame.geometry[i*4]; baseline[i]=frame.geometry[i*4+1]; advance[i]=frame.geometry[i*4+2]; sizes[i]=frame.geometry[i*4+3]; }
            String[] text=new String[lines]; RectF[] bounds=new RectF[lines];
            for(int i=0;i<lines;i++) { int n=glyphs+i;
                text[i]=ReflowSession.slice(frame.text,frame.spans[n*2]-frame.meta[0],frame.spans[n*2+1]-frame.meta[0]).trim();
                bounds[i]=new RectF(frame.geometry[n*4],frame.geometry[n*4+1],frame.geometry[n*4]+frame.geometry[n*4+2],frame.geometry[n*4+1]+frame.geometry[n*4+3]); }
            PageSnapshot result=new PageSnapshot(bitmap,false,display,-1,frame.meta[0],frame.meta[1],frame.text,1f,width,height,
                    starts,ends,null,x,baseline,advance,sizes,text,bounds,0,book);
            result.part=target; result.path=parts[target][0]; result.textBase=frame.meta[0]; result.bounded=true;
            result.boundedOwner=this; result.boundedLocation=nativeCapture(pager,target,frame.meta[0]);
            Log.i("EXRHost","bounded page {\"book\":"+book+",\"part\":"+target+",\"text_bytes\":"+frame.text.length+
                    ",\"workspace_peak\":"+frame.meta[7]+",\"projection_bytes\":"+frame.meta[8]+"}");
            return result;
        } catch(RuntimeException|Error error) { bitmap.recycle(); throw error; }
    }
    @Override public void close() { closed=true; if(handle!=0) nativeClose(handle); handle=0; }
    private static native String[][] nativeParts(long library,long book);
    private static native long nativeOpen(long library,long book,int part,byte[] font,float size,HostTask task);
    private static native Frame nativeNext(long handle,HostTask task,boolean render);
    private static native Frame nativeRender(long handle,HostTask task);
    private static native long nativeCalls(long handle);
    private static native String[] nativeCapture(long handle,int part,long offset);
    private static native void nativeClose(long handle);
    private static native String[] nativeProgress(long library,long book);
    private static native long[] nativeResolve(long handle,String[] location,HostTask task);
    private static native void nativeSaveProgress(long handle,long library,long book,int part,long offset);
    private static native void nativeSaveNote(long handle,long library,long book,int part,long id,long start,long end,String text);
}
