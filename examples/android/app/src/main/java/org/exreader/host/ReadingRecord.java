// SPDX-License-Identifier: MIT
package org.exreader.host;

/** One copied product graph snapshot. Only SAFE content is present. */
final class ReadingRecord {
    static final int MISSING=0,SAFE=1,CONCURRENT=2,PENDING=3,BLOCKED=4;
    static final int BOOKMARK=1,HIGHLIGHT=2,NOTE=3,TOMBSTONE=4,PROGRESS=5;
    final int state,kind,mode;final long revisions,heads,missingParents,foreignParents,wireBytes,anchorVersion;
    final boolean deleted,requiresRestore,legacy;
    final String id,head,operation,sha,body,bookKey;final ReadingCapture capture;
    ReadingRecord(long[] values,String[] strings,ReadingCapture capture){
        if(values==null||values.length!=12||strings==null||strings.length!=6)throw new IllegalStateException("Incomplete reading graph");
        state=(int)values[0];kind=(int)values[1];revisions=values[2];heads=values[3];missingParents=values[4];foreignParents=values[5];deleted=values[6]!=0;requiresRestore=values[7]!=0;wireBytes=values[8];mode=(int)values[9];anchorVersion=values[10];legacy=values[11]!=0;
        id=strings[0];head=strings[1];operation=strings[2];sha=strings[3];body=strings[4];bookKey=strings[5];this.capture=capture;
        if(state!=SAFE&&(!head.isEmpty()||capture!=null||!body.isEmpty()))throw new IllegalStateException("Unsafe graph exposed content");
    }
    boolean readable(){return state==SAFE&&!deleted&&capture!=null;}
    static String preview(String value){if(value==null)return "";String visible=value.replace('\0','␀').replace('\r',' ').replace('\n',' ').replace('\t',' ');int count=visible.codePointCount(0,visible.length());return count<=80?visible:visible.substring(0,visible.offsetByCodePoints(0,80))+"…";}
    String label(){
        if(state!=SAFE)return (state==CONCURRENT?"版本有冲突":state==PENDING?"等待父版本":state==BLOCKED?"需要明确恢复":"记录不可用")+" · "+heads+" 个头 / "+revisions+" 个版本";
        if(deleted||kind==TOMBSTONE)return "已删除 · 可选择保留版本恢复";
        if(kind==PROGRESS)return "已保存阅读进度";
        String text=kind==BOOKMARK?body:kind==NOTE?body:capture==null?"":capture.text(0);
        return (kind==BOOKMARK?"书签":kind==NOTE?"笔记":"高亮")+(text==null||text.isEmpty()?"":" · "+preview(text));
    }
}
