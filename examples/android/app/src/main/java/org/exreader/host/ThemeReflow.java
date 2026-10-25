// SPDX-License-Identifier: MIT
package org.exreader.host;

/** App-local SDK3.41 owner; all handles stay on the existing serial SDK worker. */
final class ThemeReflow implements AutoCloseable {
    static {System.loadLibrary("exreader_host");}
    private long document;
    ThemeReflow(String path,byte[] font){document=nativeOpen(path,font);if(document==0)throw new IllegalStateException("No themed document");}
    byte[] text(){return nativeText(document);}
    String title(){return nativeTitle(document);}
    long pager(float size,ReadingPreferences value,PageTheme theme,HostTask task){return nativePager(document,size,value==null?1.6f:value.line,value==null?12f:value.paragraph,value==null?32f:value.margin,theme.foreground,theme.background,task);}
    static BoundedEpub.Frame next(long handle,HostTask task,boolean render){return nativeFrame(handle,task,true,render);}
    static BoundedEpub.Frame render(long handle,HostTask task){return nativeFrame(handle,task,false,true);}
    static void close(long handle){nativeClosePager(handle);}
    @Override public void close(){if(document!=0){nativeClose(document);document=0;}}
    private static native long nativeOpen(String path,byte[] font);
    private static native byte[] nativeText(long document);
    private static native String nativeTitle(long document);
    private static native long nativePager(long document,float size,float line,float paragraph,float margin,int foreground,int background,HostTask task);
    private static native BoundedEpub.Frame nativeFrame(long handle,HostTask task,boolean advance,boolean render);
    private static native void nativeClosePager(long handle);
    private static native void nativeClose(long document);
}
