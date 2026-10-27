// SPDX-License-Identifier: MIT
package org.exreader.host;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/** Local font library on the existing SDK owner thread; leases belong to the paging path. */
final class NativeFonts {
    static {System.loadLibrary("exreader_host");}
    static final int OK=0,ARGUMENT=1,ENCODING=2,LIMIT=3,IO=4,FONT=5,CANCELLED=6,CHANGED=7,BUSY=8,THREAD=9,NOT_FOUND=10,CORRUPT=12,MISSING=13,UNSUPPORTED=14,COMMIT_UNCERTAIN=15;
    final long handle;
    private NativeFonts(long handle){this.handle=handle;}
    static NativeFonts open(String directory){return new NativeFonts(open0(directory));}
    static final class Font {
        final String hash,name;final long bytes;
        Font(String[] row){if(row.length!=3)throw new IllegalStateException("Incomplete font row");hash=row[0];name=row[1];bytes=Long.parseLong(row[2]);}
        String label(){return name+" · "+(bytes>=1048576?String.format(Locale.US,"%.1f MiB",bytes/1048576.0):Math.max(1,bytes/1024)+" KiB")+" · "+hash.substring(0,8);}
    }
    static final class Imported {
        final int status,created;final String hash,name,message;final long bytes;
        Imported(String[] row){if(row==null||row.length!=6)throw new IllegalStateException("Incomplete font import");status=Integer.parseInt(row[0]);created=Integer.parseInt(row[1]);hash=row[2];name=row[3];bytes=Long.parseLong(row[4]);message=row[5];}
        boolean ok(){return status==OK;}
        String reason(){
            switch(status){
                case ENCODING:return "名称不是有效的显示名称";
                case LIMIT:return "字体超过 16 MiB、64 个或总量上限";
                case FONT:return "文件不是 SDK 可用的字体";
                case CANCELLED:return "已取消，原有字体保留";
                case CHANGED:return "文件在导入时发生变化，未导入";
                case BUSY:return "字体库正忙，请稍后重试";
                case COMMIT_UNCERTAIN:return "提交状态不确定，请重新打开字体面板核对";
                case IO:return "读取或写入失败";
                default:return "导入未完成（"+status+"）";
            }
        }
    }
    List<Font> list(){String[][] rows=list(handle);ArrayList<Font> out=new ArrayList<>();for(String[] row:rows)out.add(new Font(row));return out;}
    Imported importFile(String path,String name,HostTask task){return new Imported(importFile(handle,path,name,task));}
    int remove(String hash){return Integer.parseInt(remove(handle,hash)[0]);}
    int probe(String hash){return probe(handle,hash);}
    /** Returns the module status; BUSY means a paging layout still borrows a font. */
    int close(){return close(handle);}
    static int live(){return liveLeases();}
    private static native long open0(String directory);
    private static native int close(long handle);
    private static native String[][] list(long handle);
    private static native String[] importFile(long handle,String path,String name,HostTask task);
    private static native String[] remove(long handle,String hash);
    private static native int probe(long handle,String hash);
    static native int liveLeases();
}
