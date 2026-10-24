// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.content.SharedPreferences;
import org.json.JSONArray;
import org.json.JSONObject;
import java.nio.CharBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HashSet;
import java.util.Arrays;

/** One complete local intent. This is host recovery state, never revision wire. */
final class IntentJournal {
    // Activity replacement can briefly leave two owner workers alive.
    static final Object LOCK=new Object();
    private static final int MAX_CHARS=131072;
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
            if(new HashSet<>(Arrays.asList(heads)).size()!=heads.length)throw new IllegalArgumentException("Repeated observed head");
            if(type<2&&!id.matches("[0-9a-f]{32}"))throw new IllegalArgumentException("Invalid organization identity");
            if(type==0&&operation!=1&&(name.isEmpty()||name.codePointCount(0,name.length())>256||name.getBytes(StandardCharsets.UTF_8).length>1024))
                throw new IllegalArgumentException("Name must contain at most 256 characters and 1024 UTF-8 bytes");
            if(type==0&&(!parent.isEmpty()&&!parent.matches("[0-9a-f]{32}")||kind!=0&&(!parent.isEmpty()||ordinal!=0)))
                throw new IllegalArgumentException("Invalid parent or group order");
            if(type>0&&!book.matches("(epub|pdf|cbz|txt|html|fb2|docx|rtf|mobi):[0-9a-f]{64}"))throw new IllegalArgumentException("Invalid original book identity");
            if(type==1&&kind==1&&ordinal!=0)throw new IllegalArgumentException("Tags have no membership order");
            if(type==2&&(operation!=0||!book.equals(format+":"+sha)||bytes<=0||sdkId<=0))throw new IllegalArgumentException("Incomplete public original bootstrap plan");
            if(type==2&&(title.codePointCount(0,title.length())>4096||author.codePointCount(0,author.length())>4096||sort.codePointCount(0,sort.length())>4096))
                throw new IllegalArgumentException("Book fields exceed the product catalog bound");
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
            JSONArray a=j.getJSONArray("heads");if(a.length()>32)throw new IllegalStateException("Too many persisted heads");
            String[] heads=new String[a.length()];for(int i=0;i<heads.length;i++){
                Object value=a.get(i);if(!(value instanceof String))throw new IllegalStateException("Invalid persisted head type");heads[i]=(String)value;
            }
            long type=integer(j,"type"),kind=integer(j,"kind"),operation=integer(j,"operation");
            if(type<0||type>2||kind<0||kind>2||operation<0||operation>2)throw new IllegalStateException("Invalid persisted command type");
            return new Command((int)type,(int)kind,(int)operation,string(j,"revision"),string(j,"id"),
                string(j,"book"),string(j,"name"),string(j,"parent"),integer(j,"ordinal"),heads,string(j,"format"),string(j,"sha"),
                integer(j,"bytes"),string(j,"title"),string(j,"author"),string(j,"sort"),bool(j,"favorite"),integer(j,"sdk"));
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
            if(command.type>1||done&&bootstrap==null||bootstrap!=null&&(command.type!=1||bootstrap.type!=2||!command.book.equals(bootstrap.book)))
                throw new IllegalArgumentException("Mismatched bootstrap recovery state");
            this.command=command;this.bootstrap=bootstrap;bootstrapDone=done;this.outcome=text(outcome);
        }
    }
    private final SharedPreferences preferences;
    IntentJournal(SharedPreferences preferences) { this.preferences=preferences; }
    Pending read() throws Exception {
        synchronized(LOCK) {
        String raw=preferences.getString("pending",null);if(raw==null)return null;
        if(raw.length()>MAX_CHARS)throw new IllegalStateException("Persisted intent exceeds its bound");
        if(!hash(raw).equals(preferences.getString("pending_sha256",null)))throw new IllegalStateException("Saved intent is damaged; recovery state retained");
        JSONObject j=new JSONObject(raw);
        if(j.length()!=5||!j.has("bootstrap")||integer(j,"version")!=1)throw new IllegalStateException("Unknown persisted intent");
        return new Pending(Command.read(j.getJSONObject("command")),j.isNull("bootstrap")?null:Command.read(j.getJSONObject("bootstrap")),
                bool(j,"bootstrap_done"),string(j,"outcome"));
        }
    }
    void create(Command command,Command bootstrap) throws Exception {
        synchronized(LOCK) {
            if(read()!=null)throw new IllegalStateException("Review the saved intent before another change");
            save(new Pending(command,bootstrap,false,"Saved before submission"));
        }
    }
    void save(Pending pending) throws Exception {
        synchronized(LOCK) {
        JSONObject j=new JSONObject().put("version",1).put("command",pending.command.json())
            .put("bootstrap",pending.bootstrap==null?JSONObject.NULL:pending.bootstrap.json()).put("bootstrap_done",pending.bootstrapDone).put("outcome",pending.outcome);
        String serialized=j.toString();
        if(serialized.length()>MAX_CHARS)throw new IllegalArgumentException("Complete intent exceeds its recovery bound");
        if(!preferences.edit().putString("pending",serialized).putString("pending_sha256",hash(serialized)).commit())throw new IllegalStateException("Could not persist the complete intent");
        }
    }
    void clear() { synchronized(LOCK) { if(!preferences.edit().remove("pending").remove("pending_sha256").commit())throw new IllegalStateException("Could not finish intent recovery"); } }
    private static String string(JSONObject j,String key)throws Exception {
        Object value=j.get(key);if(!(value instanceof String))throw new IllegalStateException("Invalid persisted text type");return (String)value;
    }
    private static long integer(JSONObject j,String key)throws Exception {
        Object value=j.get(key);if(!(value instanceof Integer)&&!(value instanceof Long))throw new IllegalStateException("Invalid persisted integer type");return ((Number)value).longValue();
    }
    private static boolean bool(JSONObject j,String key)throws Exception {
        Object value=j.get(key);if(!(value instanceof Boolean))throw new IllegalStateException("Invalid persisted boolean type");return (Boolean)value;
    }
    private static String hash(String raw) {
        try {
            StringBuilder result=new StringBuilder(64);for(byte value:MessageDigest.getInstance("SHA-256").digest(raw.getBytes(StandardCharsets.UTF_8)))
                result.append(Character.forDigit((value>>>4)&15,16)).append(Character.forDigit(value&15,16));return result.toString();
        } catch(java.security.NoSuchAlgorithmException impossible){throw new AssertionError(impossible);}
    }
    static String text(String value) {
        if(value==null||value.indexOf('\0')>=0||value.length()>16384)throw new IllegalArgumentException("Invalid command text");
        try {
            if(StandardCharsets.UTF_8.newEncoder().onMalformedInput(CodingErrorAction.REPORT).onUnmappableCharacter(CodingErrorAction.REPORT)
                    .encode(CharBuffer.wrap(value)).remaining()>16384)throw new IllegalArgumentException("Command text is too long");
        } catch(java.nio.charset.CharacterCodingException error) { throw new IllegalArgumentException("Invalid Unicode in command",error); }
        return value;
    }
}
