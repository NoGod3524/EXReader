// SPDX-License-Identifier: MIT
package org.exreader.host;

import java.io.File;

/** Real public-SDK capture/resolve; used only by the existing SDK worker. */
final class NativeReadingSdk {
    static {System.loadLibrary("exreader_host");}
    static final int FOUND=1,AMBIGUOUS=2,LEGACY=3;
    static final class Unsupported extends java.io.IOException {Unsupported(){super("此格式不支持位置捕获（CBZ）");}}
    static final class Match {
        final int sdk,state;final long unit,start,end;final ReadingCapture recaptured;
        Match(long[] values,ReadingCapture capture){if(values==null||values.length!=5)throw new IllegalStateException("Incomplete reading resolution");sdk=(int)values[0];state=(int)values[1];unit=values[2];start=values[3];end=values[4];recaptured=capture;if(state==FOUND&&(sdk!=0||capture==null))throw new IllegalStateException("FOUND requires a genuine recapture");}
        boolean found(){return sdk==0&&state==FOUND&&recaptured!=null;}
    }
    static ReadingCapture capture(BookStore store,PageSnapshot frame,long start,long end,byte[] font,float size,File original,HostTask task,ReadingControl control)throws Exception {
        store.searchOwner();if(frame.sourceKey==null||frame.sourceKey.isEmpty())throw new IllegalStateException("Reading frame has no original identity");
        BookStore.VerifiedSource source=store.verifySource(frame.bookId,null,0,task);if(!source.key.equals(frame.sourceKey))throw new IllegalStateException("Reading original changed");
        if(source.book.format==NativeLibrary.FORMAT_CBZ)throw new Unsupported();
        if(!frame.bounded&&(original==null||original.length()!=source.bytes||!BookStore.syncFileHash(original,task).equals(source.sha256)))throw new IllegalStateException("Displayed original differs from the SDK source");
        int mode=frame.fixed?ReadingCapture.FIXED:frame.bounded?ReadingCapture.EPUB:ReadingCapture.REFLOW;long unit=frame.fixed?frame.index:frame.bounded?frame.part:0;
        if(start<frame.start||end<start||end>frame.end)throw new IllegalArgumentException("Selection is outside the actual page");
        control.check();control.check();ReadingCapture capture=nativeCapture(store.nativeLibrary().checked(),frame.bookId,mode,unit,frame.path,start,end,source.key,font,size,control);control.check();return capture;
    }
    static Match resolve(BookStore store,long book,ReadingCapture capture,byte[] font,float size,HostTask task,ReadingControl control)throws Exception {
        store.searchOwner();BookStore.VerifiedSource source=store.verifySource(book,null,0,task);
        if(!source.key.equals(capture.bookKey)||!("exreader-sdk-"+nativeVersion()).equals(capture.parser))throw new IllegalStateException("Reading original or parser differs");
        task.check();Match result=nativeResolve(store.nativeLibrary().checked(),book,capture.numbers(),capture.route(),capture.bytes(),font,size,control);task.check();return result;
    }
    static String parser(){return "exreader-sdk-"+nativeVersion();}
    private static native String nativeVersion();
    private static native ReadingCapture nativeCapture(long library,long book,int mode,long unit,String path,long start,long end,String key,byte[] font,float size,ReadingControl control);
    private static native Match nativeResolve(long library,long book,long[] numbers,String[] route,byte[][] selectors,byte[] font,float size,ReadingControl control);
}
