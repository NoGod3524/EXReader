// SPDX-License-Identifier: MIT
package org.exreader.host;

/** Typed access to the reviewed raw0.2 annotation and jump-history modules on the product owner. */
final class NativeWave3 {
    static {System.loadLibrary("exreader_product");}
    private NativeWave3() {}
    /** Resolves one copied capture on the SDK owner; true only for a genuine public FOUND. */
    interface FoundSink {boolean found(ReadingCapture capture);}
    static final int AI_OK=0,AI_FORMAT=4,AI_LIMIT=5,AI_REVISION=6,AI_CANCELLED=7,AI_IDENTITY=9,AI_UNRESOLVED=10,AI_UNCONFIRMED=11;
    static final int NEW=0,DUPLICATE=1,CONFLICT=2,MISSING_PARENT=3,BLOCKED_RESTORE=4,REJECTED=5;
    static final int FOUND_NOT_NEEDED=0,FOUND_YES=1,FOUND_NO=2,FOUND_NULL=3,FOUND_NOT_CHECKED=4;
    static final int JH_PAGE=1,JH_SEARCH=2,JH_TOC=3,BACK=1,FORWARD=2;
    static final int JH_OK=0,JH_EMPTY=9,JH_STALE=10,JH_UNREPRESENTABLE=100;

    static final class ImportItem {
        final long index;final int outcome,found,revision;final boolean committed,created,duplicate;final String kind,operation;
        ImportItem(String[] row){if(row.length!=9)throw new IllegalStateException("Incomplete annotation item");index=Long.parseLong(row[0]);outcome=Integer.parseInt(row[1]);found=Integer.parseInt(row[2]);
            committed="1".equals(row[3]);created="1".equals(row[4]);duplicate="1".equals(row[5]);revision=Integer.parseInt(row[6]);kind=row[7];operation=row[8];}
        String label(){
            String place=found==FOUND_YES?"位置已确认":found==FOUND_NULL?"空选择器保留，不可跳转":found==FOUND_NO?"位置未找到":found==FOUND_NOT_NEEDED?"删除记录":"位置未核对";
            String what=outcome==NEW?(committed?"已写入":"将写入"):outcome==DUPLICATE?"已存在":outcome==CONFLICT?"冲突":outcome==MISSING_PARENT?"缺少父版本":outcome==BLOCKED_RESTORE?"恢复被阻止":"被拒绝";
            return "#"+(index+1)+" "+("annotation".equals(kind)?"标注":"进度")+"（"+operation+"）· "+what+" · "+place;
        }
    }
    static final class ImportResult {
        final int status,revisionCode,rsCode,osError;final long line,itemIndex;final String message,fingerprint;
        final long inputBytes,annotations,heads,omitted,found,unresolved,nulls,wouldCreate,wouldDuplicate,created,duplicates,committed,nextIndex,sourceBytes,totalItems;
        final boolean validated,foundChecked,complete;final ImportItem[] items;
        ImportResult(String[][] rows){
            if(rows==null||rows.length<1||rows[0].length!=26)throw new IllegalStateException("Incomplete annotation result");String[] r=rows[0];
            status=Integer.parseInt(r[0]);revisionCode=Integer.parseInt(r[1]);rsCode=Integer.parseInt(r[2]);osError=Integer.parseInt(r[3]);line=Long.parseLong(r[4]);itemIndex=Long.parseLong(r[5]);message=r[6];
            inputBytes=Long.parseLong(r[7]);annotations=Long.parseLong(r[8]);heads=Long.parseLong(r[9]);omitted=Long.parseLong(r[10]);found=Long.parseLong(r[11]);unresolved=Long.parseLong(r[12]);nulls=Long.parseLong(r[13]);
            wouldCreate=Long.parseLong(r[14]);wouldDuplicate=Long.parseLong(r[15]);created=Long.parseLong(r[16]);duplicates=Long.parseLong(r[17]);committed=Long.parseLong(r[18]);nextIndex=Long.parseLong(r[19]);sourceBytes=Long.parseLong(r[20]);
            fingerprint=r[21];validated="1".equals(r[22]);foundChecked="1".equals(r[23]);complete="1".equals(r[24]);totalItems=Long.parseLong(r[25]);
            items=new ImportItem[rows.length-1];for(int i=1;i<rows.length;i++)items[i-1]=new ImportItem(rows[i]);
        }
        boolean ok(){return status==AI_OK;}
        String reason(){
            switch(status){
                case AI_FORMAT:return "文件不是本应用的标注导出文件，或内容已损坏（第 "+line+" 行）";
                case AI_LIMIT:return "文件超过大小或条目上限";
                case AI_REVISION:return "文件与当前书库的记录格式不兼容或存在冲突";
                case AI_CANCELLED:return "已取消；已提交的记录保留";
                case AI_IDENTITY:return "文件属于另一本书或原件长度不同";
                case AI_UNRESOLVED:return "有 "+unresolved+" 条位置在当前书中无法确认";
                case AI_UNCONFIRMED:return "预览指纹不一致，文件可能已变化";
                default:return "导入未完成（"+message+"）";
            }
        }
    }
    static final class ExportResult {
        final int status,revisionCode,rsCode,osError;final String message;final long annotations,current,tombstones,pending,concurrent,blocked,heads,jsonlBytes,markdownBytes;final boolean jsonl,markdown;
        ExportResult(String[] r){
            if(r==null||r.length!=16)throw new IllegalStateException("Incomplete annotation export result");
            status=Integer.parseInt(r[0]);revisionCode=Integer.parseInt(r[1]);rsCode=Integer.parseInt(r[2]);osError=Integer.parseInt(r[3]);message=r[4];annotations=Long.parseLong(r[5]);current=Long.parseLong(r[6]);
            tombstones=Long.parseLong(r[7]);pending=Long.parseLong(r[8]);concurrent=Long.parseLong(r[9]);blocked=Long.parseLong(r[10]);heads=Long.parseLong(r[11]);jsonlBytes=Long.parseLong(r[12]);markdownBytes=Long.parseLong(r[13]);
            jsonl="1".equals(r[14]);markdown="1".equals(r[15]);
        }
        boolean ok(){return status==0&&jsonl&&markdown;}
    }
    static final class Jump {
        final int status,outcome;final long count,cursor,generation;final boolean back,forward;final String message;
        Jump(String[] r){if(r==null||r.length!=10)throw new IllegalStateException("Incomplete jump result");status=Integer.parseInt(r[0]);outcome=Integer.parseInt(r[1]);count=Long.parseLong(r[2]);cursor=Long.parseLong(r[3]);back="1".equals(r[4]);forward="1".equals(r[5]);generation=Long.parseLong(r[6]);message=r[9];}
    }
    static final class State {
        final long count,cursor,generation,bytes,outstanding;final boolean back,forward;
        State(long[] v){if(v==null||v.length!=7)throw new IllegalStateException("Incomplete jump state");count=v[0];cursor=v[1];back=v[2]!=0;forward=v[3]!=0;generation=v[4];bytes=v[5];outstanding=v[6];}
        String label(){return count==0?"尚无位置历史":"第 "+(cursor+1)+" / "+count+" 个位置"+(back?"，可返回":"")+(forward?"，可前进":"");}
    }
    /** A peeked target: the cursor does not move until the host navigated to a public FOUND and completes it. */
    static final class Move {
        final int direction;final long token;final NativeReadingSdk.Match match;final int status;
        Move(int direction,int status,long token,NativeReadingSdk.Match match){this.direction=direction;this.status=status;this.token=token;this.match=match;}
        boolean navigable(){return status==JH_OK&&match!=null&&match.found();}
    }
    static native String[][] annotationImport(long owner,String book,String path,boolean commit,String fingerprint,HostTask task,FoundSink sink);
    static native String[] annotationExport(long owner,String book,String title,String jsonl,String markdown,HostTask task);
    static native String[] jumpCommit(long owner,int kind,int mode,long[] numeric,String[] route,byte[][] selectors,int version);
    static native ReadingCapture jumpPeek(long owner,int direction,long[] out);
    static native int jumpComplete(long owner,long token);
    static native void jumpDrop(long owner,long token);
    static native long[] jumpState(long owner,boolean clear);
    static ImportResult importFile(long owner,String book,String path,boolean commit,String fingerprint,HostTask task,FoundSink sink){return new ImportResult(annotationImport(owner,book,path,commit,fingerprint,task,sink));}
    static ExportResult export(long owner,String book,String title,String jsonl,String markdown,HostTask task){return new ExportResult(annotationExport(owner,book,title,jsonl,markdown,task));}
    static Jump commit(long owner,int kind,ReadingCapture capture,int version){return new Jump(jumpCommit(owner,kind,capture.mode,capture.numbers(),capture.route(),capture.bytes(),version));}
    static State state(long owner){return new State(jumpState(owner,false));}
    static State clear(long owner){return new State(jumpState(owner,true));}
}
