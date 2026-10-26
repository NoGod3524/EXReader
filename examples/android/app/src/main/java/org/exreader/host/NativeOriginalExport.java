// SPDX-License-Identifier: MIT
package org.exreader.host;

/** Public original export into app-private storage, on the existing SDK owner. */
final class NativeOriginalExport {
    static {System.loadLibrary("exreader_host");}
    static final int OK=0,ARGUMENT=1,LIMIT=2,OWNER=3,MEMORY=4,SOURCE=5,IO=6,CONFLICT=7,CANCELLED=8,PENDING=9,CLEANUP=10;
    private NativeOriginalExport() {}
    static final class Item {
        final long book;final int status,sdk,format;final boolean committed,created,durable,cleanup;final long bytes;final String sha,path,cleanupPath;
        Item(String[] r){if(r.length!=12)throw new IllegalStateException("Incomplete original receipt");book=Long.parseLong(r[0]);status=Integer.parseInt(r[1]);sdk=Integer.parseInt(r[2]);committed="1".equals(r[3]);created="1".equals(r[4]);
            durable="1".equals(r[5]);cleanup="1".equals(r[6]);format=Integer.parseInt(r[7]);bytes=Long.parseLong(r[8]);sha=r[9];path=r[10];cleanupPath=r[11];}
        boolean saved(){return committed&&durable&&!path.isEmpty()&&(status==OK||status==CLEANUP);}
        String reason(){
            switch(status){
                case OK:return durable?"已完整形成并同步到存储":"已形成，等待存储确认";
                case LIMIT:return "超过单本 128 MiB 或批量上限";
                case SOURCE:return "原件读取失败，未导出";
                case IO:return "写入私有目录失败";
                case CONFLICT:return "已有同名但内容不同的文件，未覆盖";
                case CANCELLED:return "已取消";
                case PENDING:return "写入未完成，已保留清理记录";
                case CLEANUP:return "已写入，但临时文件需要清理";
                default:return "未完成（"+status+"）";
            }
        }
    }
    static final class Result {
        final int status;final Item[] items;
        Result(String[][] rows){if(rows==null||rows.length<1||rows[0].length!=2)throw new IllegalStateException("Incomplete original export result");status=Integer.parseInt(rows[0][0]);items=new Item[rows.length-1];for(int i=1;i<rows.length;i++)items[i-1]=new Item(rows[i]);}
    }
    static Result export(long library,long[] books,String directory,HostTask task){return new Result(run(library,books,directory,task));}
    private static native String[][] run(long library,long[] books,String directory,HostTask task);
}
