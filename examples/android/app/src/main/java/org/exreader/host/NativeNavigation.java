// SPDX-License-Identifier: MIT
package org.exreader.host;

/** Owner-only optional navigation snapshot; only copied values reach the UI. */
final class NativeNavigation implements AutoCloseable {
    static {System.loadLibrary("exreader_host");}
    static final int OK=0,CANCELLED=4,AMBIGUOUS=10,NEEDS_HOST=12,PART_ONLY=13,UNMAPPABLE=20;
    static final int PUBLICATION=1,DOCUMENT=2,FIXED=3;
    static final class Failure extends RuntimeException {
        final int code,sdk;
        Failure(int code,int sdk){super("目录暂时不可用，请重试");this.code=code;this.sdk=sdk;}
    }
    static final class Control {
        final HostTask task;final java.io.File directory;final boolean gate;int polls;
        Control(HostTask task,java.io.File directory,boolean gate){this.task=task;this.directory=directory;this.gate=gate;}
        void check()throws Exception {
            task.check();++polls;if(!BuildConfig.DEBUG||!gate||polls<3)return;
            java.io.File arm=new java.io.File(directory,"navigation-gate-arm");if(!arm.isFile())return;
            if(!arm.delete())throw new java.io.IOException("Navigation review gate cannot be consumed");
            java.nio.file.Files.write(new java.io.File(directory,"navigation-gate-arrived").toPath(),new byte[]{1});
            java.io.File release=new java.io.File(directory,"navigation-gate-release");long end=android.os.SystemClock.elapsedRealtime()+20000;
            while(!release.isFile()){task.check();if(android.os.SystemClock.elapsedRealtime()>end)throw new java.io.IOException("Navigation review gate not released");Thread.sleep(10);}
            if(!release.delete())throw new java.io.IOException("Navigation review release cannot be consumed");task.check();
        }
    }
    static final class Info {
        final long kind,source,authorOutline,nodes,roots,levels,parts,textBytes;
        Info(long[] values){if(values==null||values.length!=8)throw new IllegalStateException("Incomplete navigation info");kind=values[0];source=values[1];authorOutline=values[2];nodes=values[3];roots=values[4];levels=values[5];parts=values[6];textBytes=values[7];}
    }
    static final class Row {
        final long index,parent,part,depth,children,targetClass;final String label,href,base,role,path,id;
        Row(String[] values){if(values==null||values.length!=12)throw new IllegalStateException("Incomplete navigation row");index=Long.parseLong(values[0]);parent=Long.parseLong(values[1]);part=Long.parseLong(values[2]);depth=Long.parseLong(values[3]);children=Long.parseLong(values[4]);targetClass=Long.parseLong(values[5]);label=values[6];href=values[7];base=values[8];role=values[9];path=values[10];id=values[11];}
        String display(){return (label.isEmpty()?"（无标题）":label)+(children>0?"  ›":"");}
    }
    static final class Page {
        final Row[] rows;final long next,total;
        Page(String[][] values){if(values==null||values.length==0||values[0].length!=2)throw new IllegalStateException("Incomplete navigation page");next=Long.parseLong(values[0][0]);total=Long.parseLong(values[0][1]);rows=new Row[values.length-1];for(int i=1;i<values.length;i++)rows[i-1]=new Row(values[i]);}
    }
    static final class Result {
        final int status,kind;final long row,part,node,cfiNode,cfiOffset,cfiSide,offset;final String path,id,fragment,cfi;final long[] candidates;
        Result(String[][] values){if(values==null||values.length!=2||values[0].length!=13)throw new IllegalStateException("Incomplete navigation target");String[] v=values[0];status=Integer.parseInt(v[0]);kind=Integer.parseInt(v[1]);row=Long.parseLong(v[2]);part=Long.parseLong(v[3]);path=v[4];id=v[5];fragment=v[6];node=Long.parseLong(v[7]);cfi=v[8];cfiNode=Long.parseLong(v[9]);cfiOffset=Long.parseLong(v[10]);cfiSide=Long.parseLong(v[11]);offset=Long.parseLong(v[12]);candidates=new long[values[1].length];for(int i=0;i<candidates.length;i++)candidates[i]=Long.parseLong(values[1][i]);}
    }
    static final class Destination {
        final long book;final String key;final int mode;final Result result;
        Destination(long book,String key,int mode,Result result){this.book=book;this.key=key;this.mode=mode;this.result=result;}
    }
    private final Thread owner=Thread.currentThread();final long book;final String key;final int mode;private long handle;
    private final NativeLibrary.Borrow borrow;
    NativeNavigation(BookStore store,long book,byte[] font,HostTask task,Control control)throws Exception {
        store.searchOwner();BookStore.VerifiedSource source=store.verifySource(book,null,0,task);this.book=book;
        key=source.key+"@exreader-sdk-"+nativeVersion();mode=source.book.fixed()?FIXED:source.location.equals("epub_chapter")?PUBLICATION:DOCUMENT;
        borrow=store.nativeLibrary().borrow();
        try {
            handle=nativeOpen(borrow.checked(),book,mode,key,font,control);
            if(handle==0)throw new IllegalStateException("目录暂时不可用");
        } catch(Exception|Error error) { borrow.close(); throw error; }
    }
    private void owned(){if(Thread.currentThread()!=owner||handle==0)throw new IllegalStateException("Navigation requires its live SDK owner");}
    Info info(){owned();return new Info(nativeInfo(handle));}
    Page page(long parent,long first){owned();return new Page(nativePage(handle,parent,first,32));}
    Destination resolve(BookStore store,long row,long explicitPart,String cfi,byte[] font,float size,HostTask task,Control control)throws Exception {
        owned();store.searchOwner();BookStore.VerifiedSource source=store.verifySource(book,null,0,task);String live=source.key+"@exreader-sdk-"+nativeVersion();
        if(!key.equals(live))throw new IllegalStateException("书籍已改变，请重新打开目录");
        return new Destination(book,key,mode,new Result(nativeResolve(handle,store.nativeLibrary().checked(),book,mode,live,row,explicitPart,cfi,font,size,control)));
    }
    @Override public void close(){if(handle!=0){owned();nativeClose(handle);handle=0;}borrow.close();}
    private static native String nativeVersion();
    static String nativeParser(){return nativeVersion();}
    private static native long nativeOpen(long library,long book,int mode,String key,byte[] font,Control control);
    private static native long[] nativeInfo(long handle);
    private static native String[][] nativePage(long handle,long parent,long first,int limit);
    private static native String[][] nativeResolve(long handle,long library,long book,int mode,String key,long row,long explicitPart,String cfi,byte[] font,float size,Control control);
    private static native void nativeClose(long handle);
}
