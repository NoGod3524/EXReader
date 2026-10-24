// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.content.SharedPreferences;
import android.os.CancellationSignal;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

/** Typed native product owner. No wire JSON or SQL crosses this production boundary. */
final class NativeCatalog {
    static { System.loadLibrary("exreader_product"); }
    private NativeCatalog() { }
    static String decode(byte[] bytes) {
        try { return StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(bytes)).toString(); }
        catch (java.nio.charset.CharacterCodingException error) { throw new IllegalStateException("Invalid native product UTF-8", error); }
    }
    static native String migration();
    static native long open(String path);
    static native void close(long owner);
    static native String[] provider(long owner);
    static native CatalogStore.ShelfBook[] page(long owner, String nfc, String nfd, String sort, String key,
                                               boolean before, boolean inclusive, CancellationSignal cancellation);
    static native CatalogStore.ShelfBook lookup(long owner, long sdkId, String exactTitle);
    static native boolean hasLocal(long owner, long sdkId);
    static native void removeLocal(long owner, long sdkId);
    static native void attach(long owner, String format, String sha, long bytes, long sdkId, String mode,
                              String title, String author, String sort, boolean favorite);
    static native String newId();
    /** Current product metadata, including deleted state; null only if absent. */
    static native String[] metadata(long owner, String bookKey);
    static native String[] heads(long owner, String kind, String key);
    private static native String[] book(long owner, String revision, String[] expected, int operation,
                                       String key, String format, String sha, long bytes, String title,
                                       String author, String sort, boolean favorite);
    private static native String[] group(long owner, String revision, String[] expected, int operation,
                                        int kind, String id, String name, String parent, long ordinal);
    private static native String[] membership(long owner, String revision, String[] expected, int operation,
                                             int kind, String groupId, String bookKey, long ordinal);
    static final class Result {
        static final int OK=0, ARGUMENT=1, NEEDS_BOOK_BOOTSTRAP=2, REVISION=3;
        final int status, revisionStatus, sqliteCode;
        final String entityKey, revisionId, message;
        final boolean created, applied;
        Result(String[] row) {
            if (row.length!=8) throw new IllegalStateException("Incomplete command result");
            status=Integer.parseInt(row[0]); revisionStatus=Integer.parseInt(row[1]); sqliteCode=Integer.parseInt(row[2]);
            entityKey=row[3]; revisionId=row[4]; created="1".equals(row[5]); applied="1".equals(row[6]); message=row[7];
        }
    }
    static Result applyBook(long owner,String revision,String[] expected,int op,String key,String format,String sha,
                            long bytes,String title,String author,String sort,boolean favorite) {
        requireRevision(revision);return new Result(book(owner,revision,expected,op,key,format,sha,bytes,title,author,sort,favorite));
    }
    static Result applyGroup(long owner,String revision,String[] expected,int op,int kind,String id,String name,String parent,long ordinal) {
        requireRevision(revision);
        if(id==null || !id.matches("[0-9a-f]{32}")) throw new IllegalArgumentException("Preallocate and persist the group ID before submission");
        return new Result(group(owner,revision,expected,op,kind,id,name,parent,ordinal));
    }
    static Result applyMembership(long owner,String revision,String[] expected,int op,int kind,String groupId,String bookKey,long ordinal) {
        requireRevision(revision);return new Result(membership(owner,revision,expected,op,kind,groupId,bookKey,ordinal));
    }
    private static void requireRevision(String revision) {
        if(revision==null || !revision.matches("[0-9a-f]{32}"))throw new IllegalArgumentException("Persist a stable native revision ID before submission");
    }
    /** Retain until the command has a certain response; includes both IDs for creates. */
    static String[] prepareCreate(SharedPreferences preferences,String request) {
        String revision=preferences.getString(request+".revision",null), entity=preferences.getString(request+".entity",null);
        if(revision==null || entity==null) {
            revision=newId(); entity=newId();
            if(!preferences.edit().putString(request+".revision",revision).putString(request+".entity",entity).commit())
                throw new IllegalStateException("Could not persist the command identity");
        }
        return new String[]{revision,entity};
    }
}
