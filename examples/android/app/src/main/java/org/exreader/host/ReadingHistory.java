// SPDX-License-Identifier: MIT
package org.exreader.host;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.HashSet;

/** Bounded public-wire parent walk. Never picks a historical version itself. */
final class ReadingHistory {
    private final Thread owner=Thread.currentThread();private final String book,id;private final boolean progress;
    private final ArrayDeque<String> queue=new ArrayDeque<>();private final HashSet<String> queued=new HashSet<>(),visited=new HashSet<>();
    static final class Page {final ReadingVersion[] rows;final boolean complete;Page(ArrayList<ReadingVersion> rows,boolean complete){this.rows=rows.toArray(new ReadingVersion[0]);this.complete=complete;}}
    ReadingHistory(String book,String id,String deletedHead,boolean progress){ReadingRequests.requireId(deletedHead);this.book=book;this.id=id;this.progress=progress;enqueue(deletedHead);}
    private void enqueue(String revision){if(visited.contains(revision)||queued.contains(revision))return;if(visited.size()+queued.size()>=4096)throw new IllegalStateException("Reading history exceeds its public bound");queued.add(revision);queue.add(revision);}
    Page next(BookStore store,ReadingControl control)throws Exception {
        if(Thread.currentThread()!=owner)throw new IllegalStateException("Reading history belongs to its SDK worker");
        ArrayDeque<String> originalQueue=new ArrayDeque<>(queue);HashSet<String> originalQueued=new HashSet<>(queued),originalVisited=new HashSet<>(visited);
        ArrayList<ReadingVersion> rows=new ArrayList<>();int bytes=0;
        try{while(!queue.isEmpty()&&rows.size()<32){control.check();String revision=queue.peek();ReadingVersion version=NativeReadingProduct.version(store,book,id,revision,progress,control);if(!version.id.equals(revision))throw new IllegalStateException("Retained reading identity differs");if(version.restorable()&&bytes+version.wireBytes>2097152)break;
            queue.remove();queued.remove(revision);visited.add(revision);for(String parent:version.parents)enqueue(parent);if(version.restorable()){rows.add(version);bytes+=version.wireBytes;}}
        control.check();return new Page(rows,queue.isEmpty());}catch(Exception|Error failure){queue.clear();queue.addAll(originalQueue);queued.clear();queued.addAll(originalQueued);visited.clear();visited.addAll(originalVisited);throw failure;}
    }
}
