// SPDX-License-Identifier: MIT
package org.exreader.host;

/** Typed modules over the existing product owner; no second store or SDK. */
final class NativeReadingProduct {
    static {System.loadLibrary("exreader_product");}
    static final int PROGRESS=1,BOOKMARK=2,HIGHLIGHT=3,NOTE_TEXT=4,PUT=0,DELETE=1,RESTORE=2;
    static final class Page {
        final ReadingRecord[] rows;final ReadingRecord progress;final String next,before;final boolean complete,budgetStopped;
        final long wireBytes,outputBytes,polls;
        Page(ReadingRecord[] rows,ReadingRecord progress,String[] cursor,long[] stats){if(rows==null||rows.length>32||cursor==null||cursor.length!=2||stats==null||stats.length!=5)throw new IllegalStateException("Incomplete reading list page");this.rows=rows;this.progress=progress;next=cursor[0];before=cursor[1];complete=stats[0]!=0;budgetStopped=stats[1]!=0;wireBytes=stats[2];outputBytes=stats[3];polls=stats[4];}
    }
    static final class Result {
        final int status,gap,revision;final String entity,id,request,sha;final long bytes;final boolean created;
        Result(String[] values){if(values==null||values.length!=9)throw new IllegalStateException("Incomplete reading command result");status=Integer.parseInt(values[0]);gap=Integer.parseInt(values[1]);revision=Integer.parseInt(values[2]);entity=values[3];id=values[4];request=values[5];sha=values[6];bytes=Long.parseLong(values[7]);created="1".equals(values[8]);}
        boolean saved(){return status==0;}
    }
    static Page list(BookStore store,String book,String after,boolean before,ReadingControl control){store.searchOwner();return nativePage(store.productOwner(),book,after,before,control);}
    static ReadingRecord selected(BookStore store,String book,String id,String expected,boolean progress,ReadingControl control){store.searchOwner();return nativeSelected(store.productOwner(),book,id,expected,progress,control);}
    static byte[] retained(BookStore store,String book,String id,String revision,boolean progress,ReadingControl control){store.searchOwner();return nativeRetained(store.productOwner(),book,id,revision,progress,control);}
    static ReadingVersion version(BookStore store,String book,String id,String revision,boolean progress,ReadingControl control){store.searchOwner();return nativeVersion(store.productOwner(),book,id,revision,progress,control);}
    static Result apply(BookStore store,String request,String[] expected,int kind,int operation,String book,String id,int mode,ReadingCapture capture,String body){
        store.searchOwner();byte[] text=kind==PROGRESS||operation==DELETE?null:ReadingCapture.encode(body,65536);
        return new Result(nativeApply(store.productOwner(),request,expected,kind,operation,book,id,mode,capture==null?null:capture.numbers(),capture==null?null:capture.route(),capture==null?null:capture.bytes(),text));
    }
    private static native Page nativePage(long owner,String book,String after,boolean before,ReadingControl control);
    private static native ReadingRecord nativeSelected(long owner,String book,String id,String expected,boolean progress,ReadingControl control);
    private static native byte[] nativeRetained(long owner,String book,String id,String revision,boolean progress,ReadingControl control);
    private static native ReadingVersion nativeVersion(long owner,String book,String id,String revision,boolean progress,ReadingControl control);
    private static native String[] nativeApply(long owner,String request,String[] expected,int kind,int operation,String book,String id,int mode,long[] numbers,String[] route,byte[][] selectors,byte[] body);
}
