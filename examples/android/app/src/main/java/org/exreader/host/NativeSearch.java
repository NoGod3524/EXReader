// SPDX-License-Identifier: MIT
package org.exreader.host;

import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

/** SDK-owner-only search. Only copied route/selector values leave this owner. */
final class NativeSearch implements AutoCloseable {
    static { System.loadLibrary("exreader_host"); }
    static final int REFLOW=1,EPUB=2,FIXED=3,FOUND=1,AMBIGUOUS=2;
    static final int UNSUPPORTED=8;
    static final class Control {
        final HostTask task;final java.io.File directory;final boolean gate;int polls;
        Control(HostTask task,java.io.File directory,boolean gate){this.task=task;this.directory=directory;this.gate=gate;}
        void check()throws Exception {
            task.check();++polls;
            if(!BuildConfig.DEBUG||!gate||polls<3)return;
            java.io.File armed=new java.io.File(directory,"search-gate-arm");if(!armed.isFile())return;
            if(!armed.delete())throw new java.io.IOException("Search review gate cannot be consumed");
            java.nio.file.Files.write(new java.io.File(directory,"search-gate-arrived").toPath(),new byte[]{1});
            java.io.File release=new java.io.File(directory,"search-gate-release");long deadline=android.os.SystemClock.elapsedRealtime()+20000;
            while(!release.isFile()){task.check();if(android.os.SystemClock.elapsedRealtime()>deadline)throw new java.io.IOException("Search review gate not released");Thread.sleep(10);}
            if(!release.delete())throw new java.io.IOException("Search review release cannot be consumed");task.check();
        }
    }
    static final class Failure extends RuntimeException {
        final int code,sdk;
        Failure(int code,int sdk){super(code==2?"请输入有效的搜索词":code==UNSUPPORTED?"此格式不支持文字搜索（CBZ）":"未能搜索，请重试");this.code=code;this.sdk=sdk;}
    }
    static final class Hit {
        final int mode;final long unit,start,end;
        final String key,partPath,pageId,chapter;
        private final byte[][] selectors;
        Hit(int mode,long unit,long start,long end,String[] route,byte[][] selectors){
            if(route.length!=4||selectors.length!=3)throw new IllegalArgumentException("Incomplete search selector");
            this.mode=mode;this.unit=unit;this.start=start;this.end=end;
            key=route[0];partPath=route[1];pageId=route[2];chapter=route[3];
            this.selectors=new byte[][]{selectors[0].clone(),selectors[1].clone(),selectors[2].clone()};
        }
        String[] route(){return new String[]{key,partPath,pageId,chapter};}
        byte[][] bytes(){return new byte[][]{selectors[0].clone(),selectors[1].clone(),selectors[2].clone()};}
        String text(int index){
            try{return StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT).onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(selectors[index])).toString();}
            catch(java.nio.charset.CharacterCodingException error){throw new IllegalArgumentException("Invalid UTF-8 selector",error);}
        }
        String label(){String value=(text(1)+text(0)+text(2)).replace('\0',' ').replace('\n',' ').replace('\r',' ').replace('\t',' ');int count=value.codePointCount(0,value.length());if(count>80)value=value.substring(0,value.offsetByCodePoints(0,80))+"…";return (mode==EPUB?"第 "+(unit+1)+" 章 · ":mode==FIXED?"第 "+(unit+1)+" 页 · ":"")+value;}
        String[] chapterLocation(){return new String[]{Long.toString(unit),partPath,Long.toString(start),Long.toString(end),text(0),text(1),text(2),chapter==null?"":chapter};}
    }
    static final class Batch {
        final Hit[] hits;final boolean complete;
        Batch(Hit[] hits,boolean complete){this.hits=hits;this.complete=complete;}
    }
    static final class Match {
        final int state;final long unit,start,end;
        Match(long[] values){if(values==null||values.length!=4)throw new IllegalStateException("Search resolution unavailable");state=(int)values[0];unit=values[1];start=values[2];end=values[3];}
    }
    private final Thread owner=Thread.currentThread();
    final long bookId;final String key;
    private long handle;
    NativeSearch(BookStore store,long bookId,String query,byte[] font,float size,HostTask task,Control control)throws Exception {
        store.searchOwner();validate(query);
        NativeLibrary.Book book=store.find(bookId);if(book==null)throw new IllegalStateException("书籍已不可用");
        if(book.format==NativeLibrary.FORMAT_CBZ)throw new Failure(UNSUPPORTED,0);
        BookStore.VerifiedSource source=store.verifySource(bookId,null,0,task);
        this.bookId=bookId;key=source.key+"|exreader-sdk-"+nativeVersion();
        int mode=book.fixed()?FIXED:source.location.equals("epub_chapter")?EPUB:REFLOW;
        handle=nativeOpen(store.nativeLibrary().checked(),bookId,mode,key,query,font,size,control);
        if(handle==0)throw new IllegalStateException("搜索暂不可用");
    }
    static void validate(String query){
        if(query==null||query.isEmpty()||query.length()>4096||query.indexOf('\0')>=0)throw new Failure(2,0);
        try{if(StandardCharsets.UTF_8.newEncoder().onMalformedInput(CodingErrorAction.REPORT).onUnmappableCharacter(CodingErrorAction.REPORT).encode(java.nio.CharBuffer.wrap(query)).remaining()>4096)throw new Failure(2,0);}
        catch(java.nio.charset.CharacterCodingException error){throw new Failure(2,0);}
    }
    private void owned(){if(Thread.currentThread()!=owner)throw new IllegalStateException("Search requires its SDK owner");if(handle==0)throw new IllegalStateException("Search is closed");}
    Batch next(Control control){owned();return nativeNext(handle,32,control);}
    static Match resolve(BookStore store,long book,Hit hit,byte[] font,float size,HostTask task)throws Exception {
        store.searchOwner();
        BookStore.VerifiedSource source=store.verifySource(book,null,0,task);
        String expected=source.key+"|exreader-sdk-"+nativeVersion();
        if(!expected.equals(hit.key))throw new IllegalStateException("书籍已改变，请重新搜索");
        int mode=source.book.fixed()?FIXED:source.location.equals("epub_chapter")?EPUB:REFLOW;
        if(source.book.format==NativeLibrary.FORMAT_CBZ||mode!=hit.mode)throw new IllegalStateException("搜索来源不匹配");
        return new Match(nativeResolve(store.nativeLibrary().checked(),book,hit.mode,hit.unit,hit.start,hit.end,hit.route(),hit.bytes(),font,size,task));
    }
    @Override public void close(){if(handle==0)return;owned();nativeClose(handle);handle=0;}
    private static native String nativeVersion();
    private static native long nativeOpen(long library,long book,int mode,String key,String query,byte[] font,float size,Control control);
    private static native Batch nativeNext(long handle,int limit,Control control);
    private static native void nativeClose(long handle);
    private static native long[] nativeResolve(long library,long book,int mode,long unit,long start,long end,String[] route,byte[][] selectors,byte[] font,float size,HostTask task);
}
