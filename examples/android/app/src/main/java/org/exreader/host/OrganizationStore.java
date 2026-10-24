// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.content.SharedPreferences;
import java.util.Arrays;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/** Worker-only organization snapshots and durable typed submissions. */
final class OrganizationStore {
    static final String[] KINDS={"shelf","tag","series"};
    static final class Selection {
        final int kind;final boolean deleted,restore;final String[] heads;
        Selection(String[] row) {
            kind=Integer.parseInt(row[0]);deleted="1".equals(row[1]);restore="1".equals(row[2]);heads=Arrays.copyOfRange(row,3,row.length);
            Arrays.sort(heads);
        }
        boolean editable() { return kind==0||kind==4; }
        void requireEditable() {
            if(!editable())throw new IllegalStateException("Unresolved revision state ("+kind+"); review conflicts before editing");
        }
        boolean same(Selection other) { return kind==other.kind&&deleted==other.deleted&&restore==other.restore&&Arrays.equals(heads,other.heads); }
    }
    static final class Group {
        final String id,name,parent;final long ordinal;final boolean deleted;
        Group(String[] row) { id=row[0];name=row[1];parent=row[2];ordinal=Long.parseLong(row[3]);deleted="1".equals(row[4]); }
        @Override public String toString() { return name+(deleted?" · removed":"")+(parent.isEmpty()?"":" · child shelf"); }
    }
    static final class Member {
        final CatalogStore.ShelfBook book;final long ordinal;
        Member(String[] r) { book=new CatalogStore.ShelfBook(r[1],r[0],Long.parseLong(r[2]),r[3],r[4],r[5],Long.parseLong(r[6]));ordinal=Long.parseLong(r[7]); }
        @Override public String toString() { return book.title+" · "+ordinal; }
    }
    static final class GroupEdit {
        final Group group;final Selection selection;
        GroupEdit(Group group,Selection selection) { this.group=group;this.selection=selection; }
    }
    static final class MemberEdit {
        final int kind;final String group,key;final Selection selection;final long ordinal;final boolean present;
        final IntentJournal.Command bootstrap;
        MemberEdit(int kind,String group,String key,Selection selection,long ordinal,boolean present,IntentJournal.Command bootstrap) {
            this.kind=kind;this.group=group;this.key=key;this.selection=selection;this.ordinal=ordinal;this.present=present;this.bootstrap=bootstrap;
        }
    }
    private final BookStore books;
    final IntentJournal journal;
    OrganizationStore(BookStore books,SharedPreferences preferences) { this.books=books;journal=new IntentJournal(preferences); }
    private long owner() { return books.productOwner(); }
    Selection selection(String kind,String key) { return new Selection(NativeCatalog.selection(owner(),kind,key)); }
    List<Group> groups(int kind,String parent,Group cursor,boolean before,boolean removed) {
        List<Group> result=new ArrayList<>();
        for(String[] row:NativeCatalog.groups(owner(),kind,parent,cursor==null?null:cursor.id,cursor==null?0:cursor.ordinal,before,removed))result.add(new Group(row));
        if(before)Collections.reverse(result);return result;
    }
    List<Member> members(int kind,String group,Member cursor,boolean before,String query) {
        List<Member> result=new ArrayList<>();
        for(String[] row:NativeCatalog.members(owner(),kind,group,cursor==null?null:cursor.book.key.bookKey,cursor==null?0:cursor.ordinal,before,query))result.add(new Member(row));
        if(before)Collections.reverse(result);return result;
    }
    GroupEdit group(int kind,String id) {
        Selection before=selection(KINDS[kind],id);String[][] rows=NativeCatalog.groupFind(owner(),kind,id);
        Selection after=selection(KINDS[kind],id);if(!before.same(after))throw new IllegalStateException("Group changed; refresh before editing");
        if(rows.length!=1)throw new IllegalStateException("Group no longer exists");
        return new GroupEdit(new Group(rows[0]),after);
    }
    MemberEdit member(int kind,String group,CatalogStore.ShelfBook book,HostTask task) throws Exception {
        String key=book.key.bookKey,entity=KINDS[kind]+":"+group+":"+key;
        Selection before=selection("membership",entity);before.requireEditable();
        String[][] rows=NativeCatalog.memberFind(owner(),kind,group,key);
        Selection bookBefore=selection("book",key);bookBefore.requireEditable();
        if(bookBefore.deleted)throw new IllegalStateException("Restore the removed book before adding it");
        IntentJournal.Command bootstrap=null;
        if(bookBefore.kind==0) {
            if(book.sdkBookId<=0)throw new IllegalStateException("Download the original before bootstrapping book history");
            BookStore.VerifiedSource source=books.verifySource(book.sdkBookId,null,0,task);
            if(!source.key.equals(key)||source.bytes!=book.sourceBytes)throw new IllegalStateException("Public SDK original differs from product identity");
            String[] metadata=NativeCatalog.metadata(owner(),key);
            if(metadata==null||!source.format.equals(metadata[0])||!source.sha256.equals(metadata[1])||source.bytes!=Long.parseLong(metadata[2])||"1".equals(metadata[7]))
                throw new IllegalStateException("Verified original does not match active product metadata");
            bootstrap=new IntentJournal.Command(2,0,0,NativeCatalog.newId(),"",key,"","",0,bookBefore.heads,source.format,source.sha256,source.bytes,
                    metadata[3],metadata[4],metadata[5],"1".equals(metadata[6]),source.book.id);
        }
        if(!bookBefore.same(selection("book",key))||!before.same(selection("membership",entity)))throw new IllegalStateException("Book or membership changed; reopen the edit");
        return new MemberEdit(kind,group,key,before,rows.length==0?0:Long.parseLong(rows[0][2]),rows.length!=0,bootstrap);
    }
    String submit(IntentJournal.Command command,IntentJournal.Command bootstrap,HostTask task) throws Exception {
        task.check();journal.create(command,bootstrap);return retry(task);
    }
    String retry(HostTask task) throws Exception {
        IntentJournal.Pending pending=journal.read();if(pending==null)return "No saved intent";
        if(pending.bootstrap!=null&&!pending.bootstrapDone) {
            IntentJournal.Command b=pending.bootstrap;
            BookStore.VerifiedSource verified=books.verifySource(b.sdkId,b.sha,b.bytes,task);
            if(!verified.key.equals(b.book))throw new IllegalStateException("Saved bootstrap original is unavailable");
        }
        final String[] outcome={"Saved; response uncertain"};
        // Catch inside publication: a committed bootstrap must never be reported canceled.
        task.commit(()->{
            IntentJournal.Pending state=pending;
            try {
                if(state.bootstrap!=null&&!state.bootstrapDone) {
                    IntentJournal.Command b=state.bootstrap;
                    // Exact retries may already have committed the saved book revision.
                    boolean alreadyCommitted=NativeCatalog.retained(owner(),b.revision);
                    if(!alreadyCommitted) {
                        String[] current=NativeCatalog.metadata(owner(),b.book);
                        if(current==null||!current[0].equals(b.format)||!current[1].equals(b.sha)||Long.parseLong(current[2])!=b.bytes||
                                !current[3].equals(b.title)||!current[4].equals(b.author)||!current[5].equals(b.sort)||
                                ("1".equals(current[6]))!=b.favorite||!"0".equals(current[7]))
                            throw new IllegalStateException("Product fields changed since bootstrap review; saved intent requires review");
                    }
                    NativeCatalog.Result boot=state.bootstrap.apply(owner());
                    if(boot.status!=NativeCatalog.Result.OK) {
                        outcome[0]=refusal("Book bootstrap",boot);journal.save(new IntentJournal.Pending(state.command,state.bootstrap,false,outcome[0]));return;
                    }
                    state=new IntentJournal.Pending(state.command,state.bootstrap,true,"Book history committed; membership pending");journal.save(state);
                }
                NativeCatalog.Result result=state.command.apply(owner());
                if(result.status==NativeCatalog.Result.OK) { journal.clear();outcome[0]="Change committed"; }
                else { outcome[0]=(state.bootstrapDone?"Book history committed. ":"")+refusal("Change",result);journal.save(new IntentJournal.Pending(state.command,state.bootstrap,state.bootstrapDone,outcome[0])); }
            } catch(Exception error) {
                outcome[0]=(state.bootstrapDone?"Book history committed. ":"")+"Response uncertain; retry saved intent: "+error.getMessage();
                try { journal.save(new IntentJournal.Pending(state.command,state.bootstrap,state.bootstrapDone,outcome[0])); }
                catch(Exception persistence) { outcome[0]+="; recovery state retained"; }
            }
        });
        return outcome[0];
    }
    private static String refusal(String step,NativeCatalog.Result result) {
        return step+" refused. Review the current item and its dependencies. The exact saved request is retained for retry.";
    }
}
