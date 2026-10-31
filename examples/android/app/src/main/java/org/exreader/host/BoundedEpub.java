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
        final String sdk;
        final long[] boxes;
        Frame(long[] meta, long[] spans, float[] geometry, byte[] text, byte[] pixels,String sdk,long[] boxes) {
            this.meta=meta; this.spans=spans; this.geometry=geometry; this.text=text; this.pixels=pixels;this.sdk=sdk;this.boxes=boxes;
        }
    }
    final NativeLibrary library;
    final long book;
    final byte[] font;
    final String[][] parts;
    long handle;
    private final java.util.Map<Long,NativeLibrary.Borrow> pagerBorrows=new java.util.HashMap<>();
    int part, index=-1, chapterPage=-1;
    long start, nextCalls, recoveryCalls;
    float size;
    boolean closed;
    boolean unresolvedProgress;
    String unresolvedNotice;
    long chapterBudget=8*1024*1024;
    ReadingPreferences appearance;
    PageTheme theme=PageTheme.ORIGINAL;

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
        if(closed) throw new IllegalStateException("Reader is closed");
        task.check();
        long began=System.nanoTime(),opened=0;
        NativeLibrary.Borrow borrow=library.borrow();
        try {
            // The borrow belongs to this native pager, including an uncommitted PageLoad.
            opened=BuildConfig.READER_WAVE3&&FontSelection.active()?nativeOpenLeased(borrow.checked(),book,target,FontSelection.library(),FontSelection.hash(),fontSize,
                    appearance==null?1.6f:appearance.line,appearance==null?12f:appearance.paragraph,appearance==null?32f:appearance.margin,chapterBudget,theme.enabled,theme.foreground,theme.background,task)
                    :nativeOpen(borrow.checked(),book,target,font,fontSize,
                    appearance==null?1.6f:appearance.line,appearance==null?12f:appearance.paragraph,appearance==null?32f:appearance.margin,chapterBudget,theme.enabled,theme.foreground,theme.background,task);
            if(opened==0) throw new IllegalStateException("Chapter pager is unavailable");
            Log.i("EXRHost","bounded open part="+target+" elapsed_ms="+((System.nanoTime()-began)/1000000L));
            pagerBorrows.put(opened,borrow);
            return opened;
        } catch(Exception|Error error) {
            if(opened!=0) nativeClose(opened);
            borrow.close();
            throw error;
        }
    }
    private void closePager(long pager) {
        NativeLibrary.Borrow borrow=pagerBorrows.get(pager);
        if(borrow==null) return;
        nativeClose(pager);
        pagerBorrows.remove(pager);
        borrow.close();
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
        return resolvedPage(location,Math.max(0,displayIndex),size,task,true,false);
    }
    PageLoad seek(NativeLibrary.Note note,HostTask task) throws Exception {
        if(note.location==null) throw new IllegalArgumentException("Missing chapter annotation route");
        return resolvedPage(note.location,0,size,task,false,false);
    }
    PageLoad seekSearch(NativeSearch.Hit hit,HostTask task)throws Exception {
        if(hit.mode!=NativeSearch.EPUB)throw new IllegalArgumentException("Search chapter route mismatch");
        return resolvedPage(hit.chapterLocation(),0,size,task,false,false);
    }
    PageLoad seekNavigation(NativeNavigation.Destination destination,HostTask task)throws Exception {
        NativeNavigation.Result route=destination.result;int target=(int)route.part;
        if(target<0||target>=parts.length||!parts[target][0].equals(route.path))throw new IllegalArgumentException("Navigation spine identity mismatch");
        long candidate=open(target,size,task);
        try{nativeCapture(candidate,target,route.offset);}catch(Exception|Error error){closePager(candidate);throw error;}
        return prepareOn(candidate,target,0,-1,route.offset,size,task,false);
    }
    PageLoad seekReading(NativeReadingSdk.Match match,HostTask task)throws Exception {
        if(!match.found()||match.recaptured.mode!=ReadingCapture.EPUB)throw new IllegalArgumentException("Reading chapter is not FOUND");
        return resolvedPage(match.recaptured.chapterLocation(match.unit),0,size,task,false,false);
    }
    private PageLoad resolvedPage(String[] location,int display,float value,HostTask task,boolean fallback,boolean recovery) throws Exception {
        int target=Integer.parseInt(location[0]); long candidate=open(target,value,task);
        try {
            long resolveBegan=System.nanoTime();
            long[] match=nativeResolve(candidate,location,fallback?5000:0,task);
            Log.i("EXRHost","bounded progress resolve elapsed_ms="+((System.nanoTime()-resolveBegan)/1000000L)+" state="+match[0]);
            task.check();
            boolean timedOut=match[0]==-2;
            if(timedOut) {
                closePager(candidate); candidate=0;
                candidate=open(target,value,task);
                Log.i("EXRHost","bounded progress resolution budget exhausted; original selector retained");
            }
            boolean exact=match[0]==1;
            if(!exact && !fallback) throw new IllegalArgumentException("Annotation is not exact (state "+match[0]+")");
            long offset=exact?match[1]:Math.max(0,Long.parseLong(location[2]));
            if(!exact && offset>=nativeExtent(candidate)) offset=0;
            if(!exact) nativeCapture(candidate,target,offset); // Validate actual UTF-8 point without replacing the saved selector.
            long ready=candidate; candidate=0;
            PageLoad load=prepareOn(ready,target,display,-1,offset,value,task,recovery);
            if(!exact) {
                load.snapshot.preserveProgress=true;
                load.snapshot.restoreNotice=(timedOut?"Saved position unresolved (query budget exceeded)":"Saved position is not exact (state "+match[0]+")")+
                    "; opened at stored chapter offset "+offset+". Original selector retained.";
            } else if(!fallback) { load.snapshot.highlightStart=match[1]; load.snapshot.highlightEnd=match[2]; }
            return load;
        } finally { if(candidate!=0) closePager(candidate); }
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
        return prepareOn(open(target,value,task),target,display,pageTarget,offset,value,task,recovery);
    }
    private PageLoad prepareOn(long candidate,int target,int display,int pageTarget,long offset,float value,HostTask task,boolean recovery) throws Exception {
        long began=System.nanoTime(),extent=nativeExtent(candidate);
        boolean transferred=false;
        try {
            Frame selected=null; int selectedPage=-1;
            for(int p=0;p<20000;p++) {
                Frame frame=next(candidate,task,recovery,false);
                // projection_bytes counts text, not visual content. Keep an
                // image-only cover, but retain the strict empty-chapter error.
                if(extent==0 && (frame==null ? selected==null : frame.meta[9]==0)) throw new IllegalArgumentException("Empty reading chapter is not supported");
                if(frame==null) break;
                if(p>0 && p%16==0) Log.i("EXRHost","bounded scan part="+target+" pages="+(p+1));
                if(pageTarget==-2) { selected=frame; selectedPage=p; continue; }
                if(pageTarget>=0?p!=pageTarget:!(offset>=frame.meta[0] && (offset<frame.meta[1] || (offset==frame.meta[1] && offset==extent)))) continue;
                selected=frame; selectedPage=p; break;
            }
            if(selected==null) throw new IllegalArgumentException("Chapter position has no page");
            selected=nativeRender(candidate,task);
            PageSnapshot snapshot=snapshot(selected,Math.max(0,display),target,candidate);
            snapshot.layoutFont=value;
            snapshot.boundedHandle=candidate;
            final long accepted=candidate; final int at=selectedPage;
            PageLoad result=new PageLoad(snapshot,(System.nanoTime()-began)/1000000L,()->{
                if(closed){closePager(accepted);throw new IllegalStateException("Reader is closed");}
                if(handle!=0) closePager(handle);
                handle=accepted; part=target; index=snapshot.index; chapterPage=at; start=snapshot.start; size=value; log();
                unresolvedProgress=snapshot.preserveProgress; unresolvedNotice=snapshot.restoreNotice;
            },()->closePager(accepted));
            transferred=true; return result;
        } finally { if(!transferred) closePager(candidate); }
    }
    /** A discarded sequential page must return to the last accepted cursor. */
    private void recover() {
        if(handle!=0) closePager(handle); handle=0;
        if(closed || chapterPage<0) return;
        HostTask task=new HostTask(()->false);
        long restored=0;
        try {
            restored=open(part,size,task);
            for(int p=0;p<=chapterPage;p++) if(next(restored,task,true,false)==null) throw new IllegalStateException("Recovery page missing");
            handle=restored; restored=0;
        } catch(Exception error) { Log.w("EXRHost","Bounded cursor recovery: "+error.getMessage()); }
        finally { if(restored!=0) closePager(restored); }
    }
    void refresh() { recover(); }
    PageLoad retryFrame(PageSnapshot previous,HostTask task) throws Exception {
        return resolvedPage(previous.boundedLocation,previous.index,previous.layoutFont,task,true,true);
    }
    void saveProgress(PageSnapshot page) {
        nativeSaveProgress(page.boundedHandle,library.checked(),book,page.part,page.start);
    }
    static void storeProgress(NativeLibrary library,PageSnapshot page) {
        nativeSaveProgress(page.boundedHandle,library.checked(),page.bookId,page.part,page.start);
    }
    static void checkSource(PageSnapshot page) { nativeCapture(page.boundedHandle,page.part,page.start); }
    static String progressIdentity(NativeLibrary library,long book) {
        String[] location=nativeProgress(library.checked(),book);
        return location==null?"null":new org.json.JSONArray(java.util.Arrays.asList(location)).toString();
    }
    void saveNote(long id,long begin,long end,String text) {
        nativeSaveNote(handle,library.checked(),book,part,id,begin,end,text);
    }
    private PageSnapshot snapshot(Frame frame,int display,int target,long pager) {
        int glyphs=(int)frame.meta[5],lines=(int)frame.meta[6],width=(int)frame.meta[2],height=(int)frame.meta[3];
        Bitmap bitmap=theme.enabled?ReflowSession.themeBitmap(width,height,frame.pixels):Bitmap.createBitmap(width,height,Bitmap.Config.ARGB_8888);
        try {
            if(frame.meta[4]!=(long)width*4) throw new IllegalStateException("Unexpected bitmap stride");
            if(!theme.enabled)bitmap.copyPixelsFromBuffer(ByteBuffer.wrap(frame.pixels));
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
            result.boundedVisualBoxes=frame.meta[9];
            result.boundedOwner=this; result.boundedLocation=nativeCapture(pager,target,frame.meta[0]);
            result.pageTheme=theme;
            result.themeSdk=frame.sdk;
            result.themeBoxes=frame.boxes;
            if(appearance!=null){result.layoutLine=appearance.line;result.layoutParagraph=appearance.paragraph;result.layoutMargin=appearance.margin;}
            Log.i("EXRHost","bounded page {\"book\":"+book+",\"part\":"+target+",\"text_bytes\":"+frame.text.length+
                    ",\"workspace_peak\":"+frame.meta[7]+",\"projection_bytes\":"+frame.meta[8]+"}");
            return result;
        } catch(RuntimeException|Error error) { bitmap.recycle(); throw error; }
    }
    @Override public void close() { closed=true; if(handle!=0) closePager(handle); handle=0; }
    private static native String[][] nativeParts(long library,long book);
    private static native long nativeOpen(long library,long book,int part,byte[] font,float size,float line,float paragraph,float margin,long budget,boolean themed,int foreground,int background,HostTask task);
    /** Present only in the wave3 native library; reached only when a local font is selected. */
    private static native long nativeOpenLeased(long library,long book,int part,long fontLibrary,String fontHash,float size,float line,float paragraph,float margin,long budget,boolean themed,int foreground,int background,HostTask task);
    private static native Frame nativeNext(long handle,HostTask task,boolean render);
    private static native Frame nativeRender(long handle,HostTask task);
    private static native long nativeCalls(long handle);
    private static native long nativeExtent(long handle);
    private static native String[] nativeCapture(long handle,int part,long offset);
    private static native void nativeClose(long handle);
    private static native String[] nativeProgress(long library,long book);
    private static native long[] nativeResolve(long handle,String[] location,long budgetMs,HostTask task);
    private static native void nativeSaveProgress(long handle,long library,long book,int part,long offset);
    private static native void nativeSaveNote(long handle,long library,long book,int part,long id,long start,long end,String text);
}
