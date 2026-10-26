// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.content.ContentResolver;
import android.database.Cursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.UUID;

/** Bounded, cancellable SAF copies. Selected documents are never opened by the native modules directly. */
final class Wave3Files {
    private Wave3Files() {}
    static final class Staged {
        final File file;final String name;final long bytes;
        Staged(File file,String name,long bytes){this.file=file;this.name=name;this.bytes=bytes;}
    }
    static String displayName(ContentResolver resolver,Uri uri) {
        String name=null;
        try(Cursor cursor=resolver.query(uri,new String[]{OpenableColumns.DISPLAY_NAME},null,null,null)) {
            if(cursor!=null&&cursor.moveToFirst()&&!cursor.isNull(0))name=cursor.getString(0);
        } catch(RuntimeException unavailable) { name=null; }
        if(name==null||name.isEmpty())name=uri.getLastPathSegment();
        return name==null?"":name;
    }
    /** A UTF-8 label for the native modules: no controls or separators, at most 200 bytes, extension removed. */
    static String label(String raw,String fallback,boolean dropExtension) {
        String name=raw==null?"":raw;
        int slash=Math.max(name.lastIndexOf('/'),name.lastIndexOf('\\'));
        if(slash>=0)name=name.substring(slash+1);
        int dot=name.lastIndexOf('.');
        if(dropExtension&&dot>0)name=name.substring(0,dot);
        StringBuilder out=new StringBuilder();
        for(int i=0;i<name.length();) {
            int cp=name.codePointAt(i);i+=Character.charCount(cp);
            if(cp<0x20||cp==0x7f||cp=='/'||cp=='\\'||Character.getType(cp)==Character.SURROGATE)out.append('_');else out.appendCodePoint(cp);
        }
        String value=out.toString().trim();
        while(value.getBytes(StandardCharsets.UTF_8).length>200)value=value.substring(0,value.offsetByCodePoints(value.length(),-1));
        return value.isEmpty()?fallback:value;
    }
    static Staged stage(ContentResolver resolver,Uri uri,File directory,String suffix,long limit,HostTask task) throws IOException {
        if(!directory.isDirectory()&&!directory.mkdirs())throw new IOException("无法创建暂存目录");
        String name=displayName(resolver,uri);
        File part=new File(directory,UUID.randomUUID().toString().replace("-","")+suffix+".part"),done=new File(part.getPath().substring(0,part.getPath().length()-5));
        long total=0;boolean ok=false;
        try(InputStream in=resolver.openInputStream(uri);FileOutputStream out=new FileOutputStream(part)) {
            if(in==null)throw new IOException("所选文档无法读取");
            byte[] chunk=new byte[65536];int count;
            while((count=in.read(chunk))>0) {
                task.check();total+=count;
                if(total>limit)throw new IOException("文件超过 "+(limit/1048576)+" MiB 上限");
                out.write(chunk,0,count);
            }
            out.getFD().sync();ok=true;
        } finally { if(!ok)part.delete(); }
        task.check();
        if(!part.renameTo(done)) { part.delete();throw new IOException("无法保存暂存文件"); }
        return new Staged(done,name,total);
    }
    /** Streams a private result to the document the user chose; the source is never moved or altered. */
    static long copyOut(File source,ContentResolver resolver,Uri destination,HostTask task) throws IOException {
        long total=0;
        try(FileInputStream in=new FileInputStream(source);ParcelFileDescriptor target=resolver.openFileDescriptor(destination,"wt")) {
            if(target==null)throw new IOException("目标文档无法写入");
            try(FileOutputStream out=new FileOutputStream(target.getFileDescriptor())) {
                byte[] chunk=new byte[65536];int count;
                while((count=in.read(chunk))>0) { task.check();out.write(chunk,0,count);total+=count; }
                out.flush();
                try { out.getFD().sync(); } catch(IOException unsupported) { /* some providers cannot sync */ }
            }
        }
        if(total!=source.length())throw new IOException("保存的字节数与私有结果不一致");
        return total;
    }
}
