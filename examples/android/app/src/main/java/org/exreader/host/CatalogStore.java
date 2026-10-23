// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteException;
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
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/** Separate product metadata database, confined to the existing host worker. */
final class CatalogStore implements AutoCloseable {
    static final String ASSET = "reader-catalog-v1.json";
    static final int APPLICATION_ID = 1163416144; // EXRP, never the SDK's EXRC.
    static final int SCHEMA_VERSION = 1;
    private static final int MAX_ASSET_BYTES = 128 * 1024;
    private static final int MAX_STATEMENTS = 128;
    private final Thread owner = Thread.currentThread();
    private final SQLiteDatabase database;

    CatalogStore(Context context, File file) throws IOException {
        this(file, readAsset(context));
    }

    /** The byte-array entry point also lets instrumentation exercise bad assets. */
    CatalogStore(File file, byte[] asset) throws IOException {
        Migration migration = parseAsset(asset); // Reject before opening any database.
        SQLiteDatabase opened = SQLiteDatabase.openDatabase(file.getAbsolutePath(), null,
                SQLiteDatabase.OPEN_READWRITE | SQLiteDatabase.CREATE_IF_NECESSARY
                        | SQLiteDatabase.NO_LOCALIZED_COLLATORS,
                corrupt -> { throw new SQLiteException("Catalog is corrupt; retained for recovery"); });
        try {
            opened.setForeignKeyConstraintsEnabled(true);
            // This PRAGMA returns a row even when setting the value.
            if (scalar(opened, "PRAGMA busy_timeout=5000") != 5000)
                throw new SQLiteException("Catalog busy timeout was not configured");
            opened.execSQL("PRAGMA trusted_schema=OFF");
            long identity = scalar(opened, "PRAGMA application_id");
            long version = scalar(opened, "PRAGMA user_version");
            if (identity != APPLICATION_ID || version != SCHEMA_VERSION) {
                if (identity != 0 || version != 0 || scalar(opened,
                        "SELECT count(*) FROM sqlite_master WHERE name NOT GLOB 'sqlite_*'") != 0) {
                    throw new SQLiteException("Refusing foreign or unsupported catalog identity/version");
                }
                // Keep each complete trigger and the migration's own transaction.
                // Android executes BEGIN/COMMIT through the same owning session.
                for (String statement : migration.statements) opened.execSQL(statement);
            }
            if (scalar(opened, "PRAGMA application_id") != APPLICATION_ID
                    || scalar(opened, "PRAGMA user_version") != SCHEMA_VERSION
                    || scalar(opened, "PRAGMA foreign_keys") != 1) {
                throw new SQLiteException("Catalog migration did not establish its contract");
            }
            database = opened;
        } catch (RuntimeException error) {
            try { opened.execSQL("ROLLBACK"); }
            catch (RuntimeException rollback) { error.addSuppressed(rollback); }
            opened.close();
            throw error;
        }
    }

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

    SQLiteDatabase database() {
        requireOwner();
        return database;
    }

    static final class ShelfKey {
        final String sortTitle, bookKey;
        ShelfKey(String sortTitle, String bookKey) {
            if (sortTitle == null || bookKey == null) throw new IllegalArgumentException("Shelf key is incomplete");
            this.sortTitle = sortTitle; this.bookKey = bookKey;
        }
    }

    static final class ShelfBook {
        final ShelfKey key;
        final long sdkBookId, sourceBytes;
        final String title, author, format;
        ShelfBook(Cursor row) {
            key = new ShelfKey(row.getString(0), row.getString(1));
            sdkBookId = row.getLong(2); title = row.getString(3); author = row.getString(4);
            format = row.getString(5); sourceBytes = row.getLong(6);
        }
    }

    private static final String SHELF_COLUMNS = "SELECT b.sort_title,b.book_key,l.sdk_book_id,b.title,b.author,b.format,b.source_bytes "
            + "FROM reader_books b JOIN reader_local_books l ON l.book_key=b.book_key WHERE b.deleted=0";

    /** A strict 50-row keyset; remote-only and tombstoned books have no runnable shelf row. */
    List<ShelfBook> shelfPage(String query, ShelfKey anchor, boolean before, boolean inclusive,
                              CancellationSignal cancellation) {
        requireOwner();
        if (query == null || query.length() > 256 || query.indexOf('\0') >= 0)
            throw new IllegalArgumentException("Invalid shelf search");
        cancellation.throwIfCanceled();
        StringBuilder sql = new StringBuilder(SHELF_COLUMNS);
        List<String> args = new ArrayList<>();
        if (!query.isEmpty()) {
            String composed = shelfLiteral(Normalizer.normalize(query, Normalizer.Form.NFC));
            String decomposed = shelfLiteral(Normalizer.normalize(query, Normalizer.Form.NFD));
            sql.append(" AND (b.sort_title LIKE ? ESCAPE '\\' OR b.author LIKE ? ESCAPE '\\' OR b.author LIKE ? ESCAPE '\\')");
            args.add(composed); args.add(composed); args.add(decomposed);
        }
        if (anchor != null) {
            sql.append(" AND (b.sort_title,b.book_key) ").append(before ? "<" : inclusive ? ">=" : ">")
                    .append(" (?,?)");
            args.add(anchor.sortTitle); args.add(anchor.bookKey);
        }
        sql.append(before ? " ORDER BY b.sort_title DESC,b.book_key DESC LIMIT 50"
                : " ORDER BY b.sort_title,b.book_key LIMIT 50");
        List<ShelfBook> books = new ArrayList<>();
        try (Cursor rows = database.rawQuery(sql.toString(), args.toArray(new String[0]), cancellation)) {
            while (rows.moveToNext()) {
                cancellation.throwIfCanceled();
                books.add(new ShelfBook(rows));
            }
        }
        if (before) Collections.reverse(books);
        return books;
    }

    private static String shelfLiteral(String value) {
        return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%";
    }

    ShelfBook localShelfBook(long sdkBookId) {
        requireOwner();
        try (Cursor row = database.rawQuery(SHELF_COLUMNS + " AND l.sdk_book_id=? LIMIT 1",
                new String[]{Long.toString(sdkBookId)})) { return row.moveToFirst() ? new ShelfBook(row) : null; }
    }

    ShelfBook localShelfTitle(String title) {
        requireOwner();
        try (Cursor row = database.rawQuery(SHELF_COLUMNS + " AND b.title=? ORDER BY b.sort_title,b.book_key LIMIT 1",
                new String[]{title})) { return row.moveToFirst() ? new ShelfBook(row) : null; }
    }

    boolean hasLocalBook(long id) {
        requireOwner();
        try (Cursor cursor = database.rawQuery("SELECT 1 FROM reader_local_books WHERE sdk_book_id=?",
                new String[]{Long.toString(id)})) { return cursor.moveToFirst(); }
    }

    void removeLocalBook(long id) {
        requireOwner();
        database.delete("reader_local_books", "sdk_book_id=?", new String[]{Long.toString(id)});
    }

    /** Only source identity is compared on reuse; product metadata/history stay intact. */
    void attach(BookStore.VerifiedSource source) {
        requireOwner();
        database.beginTransaction();
        try {
            boolean exists;
            try (Cursor row = database.rawQuery(
                    "SELECT format,source_sha256,source_bytes FROM reader_books WHERE book_key=?",
                    new String[]{source.key})) {
                exists = row.moveToFirst();
                if (exists && (!source.format.equals(row.getString(0))
                        || !source.sha256.equals(row.getString(1)) || source.bytes != row.getLong(2)))
                    throw new SQLiteException("Product source identity conflicts with the SDK original");
            }
            if (!exists) database.execSQL("INSERT INTO reader_books"
                    + "(book_key,format,source_sha256,source_bytes,title,author,sort_title,favorite) VALUES(?,?,?,?,?,?,?,?)",
                    new Object[]{source.key, source.format, source.sha256, source.bytes,
                            source.book.title, source.book.author,
                            Normalizer.normalize(source.book.title, Normalizer.Form.NFC), source.book.favorite});
            boolean mapped;
            try (Cursor row = database.rawQuery(
                    "SELECT book_key,location_kind FROM reader_local_books WHERE sdk_book_id=?",
                    new String[]{Long.toString(source.book.id)})) {
                mapped = row.moveToFirst();
                if (mapped && (!source.key.equals(row.getString(0)) || !source.location.equals(row.getString(1))))
                    throw new SQLiteException("Local SDK identity already maps to another source or mode");
            }
            if (!mapped) {
                long existingId = 0;
                try (Cursor row = database.rawQuery(
                        "SELECT sdk_book_id FROM reader_local_books WHERE book_key=?", new String[]{source.key})) {
                    if (row.moveToFirst()) existingId = row.getLong(0);
                }
                if (existingId == 0) database.execSQL(
                        "INSERT INTO reader_local_books(book_key,sdk_book_id,location_kind) VALUES(?,?,?)",
                        new Object[]{source.key, source.book.id, source.location});
                else if (source.book.id < existingId) database.execSQL(
                        "UPDATE reader_local_books SET sdk_book_id=?,location_kind=? WHERE book_key=?",
                        new Object[]{source.book.id, source.location, source.key});
                // Historical SDK duplicates keep their rows; one oldest local ID owns this key.
            }
            database.setTransactionSuccessful();
        } finally { database.endTransaction(); }
    }

    private void requireOwner() {
        if (Thread.currentThread() != owner) throw new IllegalStateException("Catalog belongs to the host worker");
    }

    @Override public void close() {
        requireOwner();
        database.close();
    }

    private static long scalar(SQLiteDatabase db, String sql) {
        try (Cursor cursor = db.rawQuery(sql, null)) {
            if (!cursor.moveToFirst()) throw new SQLiteException("Catalog contract query returned no row");
            return cursor.getLong(0);
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
