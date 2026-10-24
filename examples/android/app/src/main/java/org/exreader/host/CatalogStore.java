// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.content.Context;
import android.os.CancellationSignal;
import android.util.JsonReader;
import android.util.JsonToken;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.io.StringReader;
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.text.Normalizer;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/** One host worker owns all product queries, attachment and typed native commands. */
final class CatalogStore implements AutoCloseable {
    static final String ASSET="reader-catalog-v1.json";
    static final int APPLICATION_ID=1163416144, SCHEMA_VERSION=1;
    private static final int MAX_ASSET_BYTES=128*1024, MAX_STATEMENTS=128;
    private final Thread owner=Thread.currentThread();
    private final File file;
    private long handle;
    CatalogStore(Context context,File file) throws IOException { this(file,readAsset(context)); }
    CatalogStore(File file,byte[] asset) throws IOException {
        Migration parsed=parseAsset(asset);
        StringBuilder source=new StringBuilder();
        for(String statement:parsed.statements)source.append(statement);
        if(!source.toString().equals(NativeCatalog.migration()))throw new IOException("Catalog asset differs from the installed product migration");
        this.file=file;
        handle=NativeCatalog.open(file.getAbsolutePath());
    }
    long nativeOwner() { requireOwner();return handle; }
    File file() { requireOwner();return file; }
    static final class ShelfKey {
        final String sortTitle,bookKey;
        ShelfKey(String sortTitle,String bookKey) {
            if(sortTitle==null || bookKey==null)throw new IllegalArgumentException("Shelf key is incomplete");
            this.sortTitle=sortTitle;this.bookKey=bookKey;
        }
    }
    static final class ShelfBook {
        final ShelfKey key;
        final long sdkBookId,sourceBytes;
        final String title,author,format;
        ShelfBook(String sort,String key,long sdkId,String title,String author,String format,long bytes) {
            this.key=new ShelfKey(sort,key);sdkBookId=sdkId;this.title=title;this.author=author;this.format=format;sourceBytes=bytes;
        }
    }
    List<ShelfBook> shelfPage(String query,ShelfKey anchor,boolean before,boolean inclusive,CancellationSignal cancellation) {
        requireOwner();
        if(query==null || query.length()>256 || query.indexOf('\0')>=0)throw new IllegalArgumentException("Invalid shelf search");
        cancellation.throwIfCanceled();
        List<ShelfBook> result=new ArrayList<>(Arrays.asList(NativeCatalog.page(handle,
                Normalizer.normalize(query,Normalizer.Form.NFC),Normalizer.normalize(query,Normalizer.Form.NFD),
                anchor==null ? null:anchor.sortTitle,anchor==null ? null:anchor.bookKey,before,inclusive,cancellation)));
        cancellation.throwIfCanceled();
        if(before)Collections.reverse(result);
        return result;
    }
    ShelfBook localShelfBook(long id) { requireOwner();return NativeCatalog.lookup(handle,id,null); }
    ShelfBook localShelfTitle(String title) { requireOwner();return NativeCatalog.lookup(handle,0,title); }
    boolean hasLocalBook(long id) { requireOwner();return NativeCatalog.hasLocal(handle,id); }
    void removeLocalBook(long id) { requireOwner();NativeCatalog.removeLocal(handle,id); }
    void attach(BookStore.VerifiedSource source) {
        requireOwner();
        NativeCatalog.attach(handle,source.format,source.sha256,source.bytes,source.book.id,source.location,
                source.book.title,source.book.author,Normalizer.normalize(source.book.title,Normalizer.Form.NFC),source.book.favorite);
    }
    /** Only a publicly verified retained SDK source may seed legacy book history. */
    NativeCatalog.Result bootstrap(BookStore.VerifiedSource source,String revision,String[] expected) {
        requireOwner();
        String[] current=NativeCatalog.metadata(handle,source.key);
        String title=source.book.title,author=source.book.author,sort=Normalizer.normalize(title,Normalizer.Form.NFC);
        boolean favorite=source.book.favorite;
        if(current!=null) {
            if(!source.format.equals(current[0]) || !source.sha256.equals(current[1]) || source.bytes!=Long.parseLong(current[2]))
                throw new IllegalStateException("Product source identity conflicts with verified SDK original");
            if("1".equals(current[7]))throw new IllegalStateException("Deleted product requires an explicit restore");
            title=current[3];author=current[4];sort=current[5];favorite="1".equals(current[6]);
        }
        return NativeCatalog.applyBook(handle,revision,expected,0,source.key,source.format,source.sha256,source.bytes,title,author,sort,favorite);
    }
    private void requireOwner() {
        if(Thread.currentThread()!=owner)throw new IllegalStateException("Catalog belongs to the host worker");
        if(handle==0)throw new IllegalStateException("Catalog is closed");
    }
    @Override public void close() { requireOwner();NativeCatalog.close(handle);handle=0; }
    static byte[] readAsset(Context context) throws IOException {
        try (InputStream input = context.getAssets().open(ASSET);
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[8192];
            int count;
            while ((count = input.read(buffer)) != -1) {
                if (output.size() + count > MAX_ASSET_BYTES) throw new IOException("Catalog asset too large");
                output.write(buffer, 0, count);
            }
            return output.toByteArray();
        }
    }

    private static final class Migration {
        final List<String> statements = new ArrayList<>();
    }

    private static Migration parseAsset(byte[] bytes) throws IOException {
        if (bytes == null || bytes.length == 0 || bytes.length > MAX_ASSET_BYTES)
            throw new IOException("Invalid catalog asset size");
        String text;
        try {
            text = StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(bytes)).toString();
        } catch (CharacterCodingException error) {
            throw new IOException("Catalog asset is not UTF-8", error);
        }
        Migration result = new Migration();
        Set<String> fields = new HashSet<>();
        long assetVersion = -1, applicationId = -1, schemaVersion = -1, sourceBytes = -1;
        String sourceHash = null;
        try (JsonReader reader = new JsonReader(new StringReader(text))) {
            reader.setLenient(false);
            reader.beginObject();
            while (reader.hasNext()) {
                String name = reader.nextName();
                if (!fields.add(name)) throw new IOException("Duplicate catalog asset field");
                switch (name) {
                    case "asset_version": assetVersion = readInteger(reader); break;
                    case "application_id": applicationId = readInteger(reader); break;
                    case "schema_version": schemaVersion = readInteger(reader); break;
                    case "source_bytes": sourceBytes = readInteger(reader); break;
                    case "source_sha256":
                        if (reader.peek() != JsonToken.STRING) throw new IOException("Invalid catalog source hash type");
                        sourceHash = reader.nextString();
                        break;
                    case "statements":
                        reader.beginArray();
                        while (reader.hasNext()) {
                            if (result.statements.size() == MAX_STATEMENTS || reader.peek() != JsonToken.STRING)
                                throw new IOException("Invalid catalog statement list");
                            String statement = reader.nextString();
                            if (statement.trim().isEmpty() || statement.indexOf('\0') >= 0)
                                throw new IOException("Empty or invalid catalog statement");
                            result.statements.add(statement);
                        }
                        reader.endArray();
                        break;
                    default: throw new IOException("Unknown catalog asset field");
                }
            }
            reader.endObject();
            if (reader.peek() != JsonToken.END_DOCUMENT) throw new IOException("Trailing catalog asset data");
        } catch (IllegalStateException | NumberFormatException error) {
            throw new IOException("Invalid catalog asset JSON", error);
        }
        if (fields.size() != 6 || assetVersion != 1 || applicationId != APPLICATION_ID
                || schemaVersion != SCHEMA_VERSION || result.statements.isEmpty()
                || sourceBytes <= 0 || sourceBytes > MAX_ASSET_BYTES || sourceHash == null
                || !sourceHash.matches("[0-9a-f]{64}")) throw new IOException("Catalog asset contract mismatch");
        StringBuilder source = new StringBuilder();
        for (String statement : result.statements) source.append(statement);
        byte[] reconstructed;
        try {
            ByteBuffer encoded = StandardCharsets.UTF_8.newEncoder().onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT).encode(CharBuffer.wrap(source));
            reconstructed = new byte[encoded.remaining()];
            encoded.get(reconstructed);
        } catch (CharacterCodingException error) {
            throw new IOException("Catalog source contains invalid Unicode", error);
        }
        if (sourceBytes != reconstructed.length || !sourceHash.equals(sha256(reconstructed)))
            throw new IOException("Catalog source size/hash mismatch");
        return result;
    }

    private static long readInteger(JsonReader reader) throws IOException {
        if (reader.peek() != JsonToken.NUMBER) throw new IOException("Catalog numeric field has wrong type");
        String number = reader.nextString();
        if (!number.matches("0|[1-9][0-9]*")) throw new IOException("Catalog numeric field is not an integer");
        return Long.parseLong(number);
    }

    private static String sha256(byte[] bytes) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(bytes);
            StringBuilder result = new StringBuilder(64);
            for (byte value : digest) {
                result.append(Character.forDigit((value >>> 4) & 15, 16));
                result.append(Character.forDigit(value & 15, 16));
            }
            return result.toString();
        } catch (NoSuchAlgorithmException impossible) {
            throw new AssertionError(impossible);
        }
    }
}

