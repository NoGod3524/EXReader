// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.content.SharedPreferences;
import org.json.JSONArray;
import org.json.JSONObject;
import java.nio.CharBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

/** One complete local intent. This is host recovery state, never revision wire. */
final class IntentJournal {
    private static final Object LOCK=new Object();
    static final class Command {
        final int type,kind,operation;
        final String revision,id,book,name,parent,format,sha,title,author,sort;
        final String[] heads;
        final long ordinal,bytes,sdkId;
        final boolean favorite;
        Command(int type,int kind,int operation,String revision,String id,String book,String name,String parent,
                long ordinal,String[] heads,String format,String sha,long bytes,String title,String author,String sort,boolean favorite,long sdkId) {
            this.type=type;this.kind=kind;this.operation=operation;this.revision=text(revision);this.id=text(id);this.book=text(book);
            this.name=text(name);this.parent=text(parent);this.ordinal=ordinal;this.heads=heads.clone();
            for(String head:this.heads)if(!text(head).matches("[0-9a-f]{32}"))throw new IllegalArgumentException("Invalid observed head");
            this.format=text(format);this.sha=text(sha);this.bytes=bytes;this.title=text(title);this.author=text(author);this.sort=text(sort);
            this.favorite=favorite;this.sdkId=sdkId;
            if(!revision.matches("[0-9a-f]{32}")||type<0||type>2||kind<0||kind>2||operation<0||operation>2||ordinal<0||heads.length>32)
                throw new IllegalArgumentException("Invalid durable intent");
            if(type<2&&!id.matches("[0-9a-f]{32}"))throw new IllegalArgumentException("Invalid organization identity");
            if(type==0&&operation!=1&&(name.isEmpty()||name.codePointCount(0,name.length())>256||name.getBytes(StandardCharsets.UTF_8).length>1024))
                throw new IllegalArgumentException("Name must contain at most 256 characters and 1024 UTF-8 bytes");
        }
        static Command group(int kind,int op,String id,String name,String parent,long ordinal,String[] heads) {
            return new Command(0,kind,op,NativeCatalog.newId(),id,"",name,parent,ordinal,heads,"","",0,"","","",false,0);
        }
        static Command member(int kind,int op,String group,String book,long ordinal,String[] heads) {
            return new Command(1,kind,op,NativeCatalog.newId(),group,book,"","",ordinal,heads,"","",0,"","","",false,0);
        }
        JSONObject json() throws Exception {
            return new JSONObject().put("type",type).put("kind",kind).put("operation",operation).put("revision",revision)
                .put("id",id).put("book",book).put("name",name).put("parent",parent).put("ordinal",ordinal)
                .put("heads",new JSONArray(heads)).put("format",format).put("sha",sha).put("bytes",bytes)
                .put("title",title).put("author",author).put("sort",sort).put("favorite",favorite).put("sdk",sdkId);
        }
        static Command read(JSONObject j) throws Exception {
            if(j.length()!=18)throw new IllegalStateException("Incomplete persisted command");
            JSONArray a=j.getJSONArray("heads");String[] heads=new String[a.length()];for(int i=0;i<heads.length;i++)heads[i]=a.getString(i);
            return new Command(j.getInt("type"),j.getInt("kind"),j.getInt("operation"),j.getString("revision"),j.getString("id"),
                j.getString("book"),j.getString("name"),j.getString("parent"),j.getLong("ordinal"),heads,j.getString("format"),j.getString("sha"),
                j.getLong("bytes"),j.getString("title"),j.getString("author"),j.getString("sort"),j.getBoolean("favorite"),j.getLong("sdk"));
        }
        NativeCatalog.Result apply(long owner) {
            if(type==0)return NativeCatalog.applyGroup(owner,revision,heads,operation,kind,id,name,parent,ordinal);
            if(type==1)return NativeCatalog.applyMembership(owner,revision,heads,operation,kind,id,book,ordinal);
            return NativeCatalog.applyBook(owner,revision,heads,operation,book,format,sha,bytes,title,author,sort,favorite);
        }
    }
    static final class Pending {
        final Command command,bootstrap;
        final boolean bootstrapDone;
        final String outcome;
        Pending(Command command,Command bootstrap,boolean done,String outcome) {
            this.command=command;this.bootstrap=bootstrap;bootstrapDone=done;this.outcome=text(outcome);
        }
    }
    private final SharedPreferences preferences;
    IntentJournal(SharedPreferences preferences) { this.preferences=preferences; }
    Pending read() throws Exception {
        String raw=preferences.getString("pending",null);if(raw==null)return null;
        if(raw.length()>131072)throw new IllegalStateException("Persisted intent exceeds its bound");
        JSONObject j=new JSONObject(raw);
        if(j.length()!=5||j.getInt("version")!=1)throw new IllegalStateException("Unknown persisted intent");
        return new Pending(Command.read(j.getJSONObject("command")),j.isNull("bootstrap")?null:Command.read(j.getJSONObject("bootstrap")),
                j.getBoolean("bootstrap_done"),j.getString("outcome"));
    }
    void create(Command command,Command bootstrap) throws Exception {
        synchronized(LOCK) {
            if(read()!=null)throw new IllegalStateException("Review the saved intent before another change");
            save(new Pending(command,bootstrap,false,"Saved before submission"));
        }
    }
    void save(Pending pending) throws Exception {
        JSONObject j=new JSONObject().put("version",1).put("command",pending.command.json())
            .put("bootstrap",pending.bootstrap==null?JSONObject.NULL:pending.bootstrap.json()).put("bootstrap_done",pending.bootstrapDone).put("outcome",pending.outcome);
        if(!preferences.edit().putString("pending",j.toString()).commit())throw new IllegalStateException("Could not persist the complete intent");
    }
    void clear() { if(!preferences.edit().remove("pending").commit())throw new IllegalStateException("Could not finish intent recovery"); }
    static String text(String value) {
        if(value==null||value.indexOf('\0')>=0||value.length()>16384)throw new IllegalArgumentException("Invalid command text");
        try {
            if(StandardCharsets.UTF_8.newEncoder().onMalformedInput(CodingErrorAction.REPORT).onUnmappableCharacter(CodingErrorAction.REPORT)
                    .encode(CharBuffer.wrap(value)).remaining()>16384)throw new IllegalArgumentException("Command text is too long");
        } catch(java.nio.charset.CharacterCodingException error) { throw new IllegalArgumentException("Invalid Unicode in command",error); }
        return value;
    }
}
