// SPDX-License-Identifier: MIT
package org.exreader.host;

/** Product/session JNI only; SDK handles stay on the existing host worker. */
final class NativeSync {
    static {System.loadLibrary("exreader_product");}
    static native int bind();
    static native int fetchOriginal(String root,byte[] authorization,String resource,String directory,String name,HostTask task);
    static native boolean validRoot(String root);
    static native long create(String product,String cache,String originals,String account,String root,byte[] authorization);
    static native long[] command(long session,int action);
    static native String[][] books(String product,String after);
    /** Read-only status view of the owned session; present only in the wave3 native library. */
    static native String[][] view(long session,String product);
    static native String[] project(String product,String key,String revision,String sortTitle);
    static native int projectBook(String product,String key,String revision,String sortTitle);
    static native String[][] projectOrganization(String product,String kind,String after);
    static final int IDLE=0,RUNNING=1,CANCELLING=2,CANCELLED=3,FINISHED=4,FAILED=5,CLOSING=6,CLOSED=7;
    static final class Snapshot {
        final int code,state,status,davCode,httpStatus,completedShards;
        final long pushed,pulled;
        Snapshot(long[] values){if(values==null||values.length!=9)throw new IllegalStateException("同步状态读取失败");code=(int)values[0];state=(int)values[1];status=(int)values[2];davCode=(int)values[3];httpStatus=(int)values[4];completedShards=(int)values[5];pushed=values[6];pulled=values[7];if(values[8]!=0)throw new IllegalStateException("未知同步完成状态");}
        String label(){switch(state){case IDLE:return "就绪";case RUNNING:return "同步中";case CANCELLING:return "正在取消";case CANCELLED:return "已取消，可重试";case FINISHED:return "本轮同步结束";case CLOSING:return "正在关闭";case CLOSED:return "已关闭";default:return httpStatus==401?"凭据无效，请重新输入":status==4?"此书库与云盘账号不匹配":"同步失败，可重试";}}
    }
    static final class RemoteBook {
        final String key,revision,title,format,sha;
        final long bytes,localId;
        final int selection;
        final boolean deleted;
        RemoteBook(String[] row){if(row.length!=9)throw new IllegalStateException("远端书目不完整");key=row[0];revision=row[1];title=row[2];format=row[3];sha=row[4];bytes=Long.parseLong(row[5]);selection=Integer.parseInt(row[6]);deleted="1".equals(row[7]);localId=Long.parseLong(row[8]);}
        boolean receivable(){return selection==4&&!deleted&&!revision.isEmpty()&&bytes>0;}
        String label(){return (title.equals(key)?"待确认书籍":title)+(localId>0?" · 已在本机":selection!=4?" · 待解决冲突":deleted?" · 已移除":"");}
    }
}
