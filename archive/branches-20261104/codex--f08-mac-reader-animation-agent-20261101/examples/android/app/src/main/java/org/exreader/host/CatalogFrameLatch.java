// SPDX-License-Identifier: MIT
package org.exreader.host;

/** Capture-only UI-thread state. One real apply, one frame callback, no frame-request loop. */
final class CatalogFrameLatch {
    final Object window;
    long generation=-1,revision=-1,frameTimeNs=-1;
    boolean armed,pending,latched,active,readySeen,drawSeen,closed;
    String readyStatus="missing_first_ready",drawStatus="missing_tree_draw_begin";
    CatalogFrameLatch(Object window){this.window=window;}
    String arm(Object observed,long generation,long revision,boolean pending){
        if(closed)return "closed";
        if(observed!=window)return "wrong_window";
        if(armed)return "duplicate_apply";
        armed=true;this.generation=generation;this.revision=revision;this.pending=pending;
        return pending?"armed":"no_pending_draw";
    }
    String frame(Object observed,long frameTimeNs){
        if(closed)return "closed";
        if(observed!=window)return "wrong_window";
        if(!armed||!pending)return "unarmed";
        if(latched)return "duplicate_latch";
        if(frameTimeNs<=0)return "invalid_frame_time";
        latched=active=true;this.frameTimeNs=frameTimeNs;return "latched";
    }
    private String match(Object observed,long generation,long revision){
        if(closed)return "closed";
        if(observed!=window)return "wrong_window";
        if(!armed||!pending)return "unarmed";
        if(!active)return "outside_frame";
        if(generation!=this.generation||revision!=this.revision)return "wrong_revision";
        return "candidate";
    }
    String ready(Object observed,long generation,long revision){
        if(readySeen)return "duplicate_ready";
        readySeen=true;readyStatus=match(observed,generation,revision);return readyStatus;
    }
    String draw(Object observed,long generation,long revision){
        if(drawSeen)return "duplicate_tree_draw_begin";
        drawSeen=true;
        drawStatus=!readySeen||!"candidate".equals(readyStatus)?"missing_ready":match(observed,generation,revision);
        return drawStatus;
    }
    void clear(){active=false;}
    void close(){closed=true;active=false;}
}
