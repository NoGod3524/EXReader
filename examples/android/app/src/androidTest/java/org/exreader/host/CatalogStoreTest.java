// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteException;
import android.os.Bundle;
import android.os.SystemClock;
import android.util.Log;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicReference;

/** Executes the packaged migration with Android's own SQLite, including triggers. */
public final class CatalogStoreTest extends Instrumentation {
    private Context context;
    private byte[] asset;
    private final List<File> files = new ArrayList<>();

    @Override public void onCreate(Bundle arguments) {
        super.onCreate(arguments);
        String selected = arguments == null ? null : arguments.getString("class");
        if (selected != null && !getClass().getName().equals(selected)) {
            Bundle result = new Bundle();
            result.putString("shortMsg", "Unexpected catalog instrumentation class");
            finish(Activity.RESULT_CANCELED, result);
            return;
        }
        start();
    }

    @Override public void onStart() {
        super.onStart();
        String[] names = {
                "createsAndReopensCatalog",
                "rejectsForeignDatabasesWithoutChangingData",
                "keepsCompleteShelfTriggers",
                "retainsImmutableRevisionsAndTombstones",
                "rollsBackInterruptedMigrationAndAllowsRetry",
                "rejectsTamperedAssetFieldsAndSource",
                "rejectsOversizedAndMalformedAssets",
                "enforcesWorkerOwnership"
        };
        Attempt[] tests = {
                this::createsAndReopensCatalog,
                this::rejectsForeignDatabasesWithoutChangingData,
                this::keepsCompleteShelfTriggers,
                this::retainsImmutableRevisionsAndTombstones,
                this::rollsBackInterruptedMigrationAndAllowsRetry,
                this::rejectsTamperedAssetFieldsAndSource,
                this::rejectsOversizedAndMalformedAssets,
                this::enforcesWorkerOwnership
        };
        long started = SystemClock.elapsedRealtime();
        int failures = 0;
        for (int index = 0; index < tests.length; index++) {
            Bundle status = testStatus(names[index], index + 1, tests.length);
            status.putString("stream", "\n" + getClass().getName() + ":" + names[index]);
            sendStatus(1, status);
            Throwable failure = null;
            try {
                prepare();
                tests[index].run();
            } catch (Throwable error) {
                failure = error;
            } finally {
                try { cleanUp(); }
                catch (Throwable cleanupError) {
                    if (failure == null) failure = cleanupError;
                    else failure.addSuppressed(cleanupError);
                }
            }
            Bundle completed = testStatus(names[index], index + 1, tests.length);
            if (failure == null) {
                completed.putString("stream", ".");
                sendStatus(0, completed);
            } else {
                failures++;
                completed.putString("stack", Log.getStackTraceString(failure));
                completed.putString("stream", "\nFailure in " + names[index] + ": " + failure + "\n");
                sendStatus(-2, completed);
            }
        }
        Bundle result = new Bundle();
        String elapsed = "\nTime: " + ((SystemClock.elapsedRealtime() - started) / 1000.0) + "\n\n";
        result.putString("stream", elapsed + (failures == 0 ? "OK (8 tests)\n"
                : "FAILURES!!!\nTests run: 8, Failures: " + failures + "\n"));
        if (failures != 0) result.putString("shortMsg", failures + " catalog tests failed");
        finish(failures == 0 ? Activity.RESULT_OK : Activity.RESULT_CANCELED, result);
    }

    private Bundle testStatus(String name, int current, int total) {
        Bundle status = new Bundle();
        status.putString("id", "InstrumentationTestRunner");
        status.putString("class", getClass().getName());
        status.putString("test", name);
        status.putInt("numtests", total);
        status.putInt("current", current);
        return status;
    }

    public void prepare() throws Exception {
        context = getTargetContext();
        asset = CatalogStore.readAsset(context);
    }

    public void cleanUp() {
        try {
            for (File file : files) SQLiteDatabase.deleteDatabase(file);
        } finally {
            files.clear();
        }
    }

    public void createsAndReopensCatalog() throws Exception {
        File file = newFile();
        try (CatalogStore catalog = new CatalogStore(context, file)) {
            SQLiteDatabase db = catalog.database();
            assertEquals(CatalogStore.APPLICATION_ID, scalar(db, "PRAGMA application_id"));
            assertEquals(1, scalar(db, "PRAGMA user_version"));
            assertEquals(1, scalar(db, "PRAGMA foreign_keys"));
            assertEquals(5000, scalar(db, "PRAGMA busy_timeout"));
            assertEquals(0, scalar(db, "PRAGMA trusted_schema"));
            assertEquals(10, scalar(db, "SELECT count(*) FROM sqlite_master WHERE type='table'"));
            insertShelf(db, 1, null);
        }
        try (CatalogStore reopened = new CatalogStore(context, file)) {
            assertEquals(1, scalar(reopened.database(), "SELECT count(*) FROM reader_shelves"));
            assertEquals(1, scalar(reopened.database(), "PRAGMA foreign_keys"));
            assertEquals("Shelf 1", text(reopened.database(), "SELECT name FROM reader_shelves"));
            assertEquals("ok", text(reopened.database(), "PRAGMA integrity_check"));
        }
    }

    public void rejectsForeignDatabasesWithoutChangingData() throws Exception {
        long[][] identities = {
                {1163416131, 7}, {999, 1}, {0, 0}, {0, 0},
                {CatalogStore.APPLICATION_ID, 2}, {0, 2}
        };
        for (int i = 0; i < identities.length; i++) {
            File file = newFile();
            String table = i == 3 ? "sqliteXbooks" : "retained";
            try (SQLiteDatabase db = openRaw(file)) {
                db.execSQL("CREATE TABLE " + table + "(value TEXT NOT NULL)");
                db.execSQL("INSERT INTO " + table + " VALUES(?)", new Object[]{"keep " + i});
                db.execSQL("PRAGMA application_id=" + identities[i][0]);
                db.execSQL("PRAGMA user_version=" + identities[i][1]);
            }
            rejects(SQLiteException.class, () -> { try (CatalogStore ignored = new CatalogStore(file, asset)) {} });
            try (SQLiteDatabase db = openRaw(file)) {
                assertEquals(identities[i][0], scalar(db, "PRAGMA application_id"));
                assertEquals(identities[i][1], scalar(db, "PRAGMA user_version"));
                assertEquals("keep " + i, text(db, "SELECT value FROM " + table));
                assertEquals(1, scalar(db, "SELECT count(*) FROM sqlite_master WHERE type='table'"));
                assertEquals(table, text(db, "SELECT name FROM sqlite_master WHERE type='table'"));
                assertEquals("ok", text(db, "PRAGMA integrity_check"));
            }
        }
    }

    public void keepsCompleteShelfTriggers() throws Exception {
        try (CatalogStore catalog = new CatalogStore(context, newFile())) {
            SQLiteDatabase db = catalog.database();
            for (int i = 1; i <= 8; i++) insertShelf(db, i, i == 1 ? null : id(i - 1));
            rejects(SQLiteException.class, () -> insertShelf(db, 9, id(8)));
            rejects(SQLiteException.class, () -> db.execSQL(
                    "UPDATE reader_shelves SET parent_id=? WHERE shelf_id=?", new Object[]{id(8), id(1)}));
            rejects(SQLiteException.class, () -> db.execSQL(
                    "UPDATE reader_shelves SET parent_id=shelf_id WHERE shelf_id=?", new Object[]{id(1)}));
            insertShelf(db, 20, null);
            insertShelf(db, 21, id(20));
            rejects(SQLiteException.class, () -> db.execSQL(
                    "UPDATE reader_shelves SET parent_id=? WHERE shelf_id=?", new Object[]{id(7), id(20)}));
            db.execSQL("UPDATE reader_shelves SET parent_id=? WHERE shelf_id=?", new Object[]{id(6), id(20)});
            assertEquals(id(6), text(db, "SELECT parent_id FROM reader_shelves WHERE shelf_id=?", id(20)));
            rejects(SQLiteException.class, () -> db.execSQL(
                    "UPDATE reader_shelves SET parent_id=? WHERE shelf_id=?", new Object[]{id(999), id(21)}));
            assertEquals(10, scalar(db, "SELECT count(*) FROM reader_shelves"));
            try (Cursor cursor = db.rawQuery("PRAGMA foreign_key_check", null)) {
                assertFalse(cursor.moveToFirst());
            }
        }
    }

    public void retainsImmutableRevisionsAndTombstones() throws Exception {
        File file = newFile();
        String revision = id(1);
        String body = "{\"operation\":\"delete\"}";
        String bodyHash = sha256(body.getBytes(StandardCharsets.UTF_8));
        try (CatalogStore catalog = new CatalogStore(context, file)) {
            SQLiteDatabase db = catalog.database();
            Object[] values = {revision, "book", "epub:" + zeros(64), "delete", body, bodyHash};
            db.execSQL("INSERT INTO reader_revisions VALUES(?,?,?,?,?,?)", values);
            db.execSQL("INSERT INTO reader_outbox(revision_id) VALUES(?)", new Object[]{revision});
            rejects(SQLiteException.class, () -> db.execSQL("INSERT OR REPLACE INTO reader_revisions VALUES(?,?,?,?,?,?)", values));
            rejects(SQLiteException.class, () -> db.execSQL("UPDATE reader_revisions SET body_json='{}'"));
            rejects(SQLiteException.class, () -> db.execSQL("DELETE FROM reader_revisions"));
            db.execSQL("DELETE FROM reader_outbox WHERE revision_id=?", new Object[]{revision});
            assertEquals(0, scalar(db, "SELECT count(*) FROM reader_outbox"));
            assertEquals(1, scalar(db, "SELECT count(*) FROM reader_tombstones"));
        }
        try (CatalogStore reopened = new CatalogStore(context, file)) {
            assertEquals(body, text(reopened.database(), "SELECT body_json FROM reader_tombstones"));
            assertEquals(bodyHash, text(reopened.database(), "SELECT body_sha256 FROM reader_revisions"));
            assertEquals(revision, text(reopened.database(), "SELECT revision_id FROM reader_tombstones"));
        }
    }

    public void rollsBackInterruptedMigrationAndAllowsRetry() throws Exception {
        File file = newFile();
        JSONObject broken = object();
        JSONArray original = broken.getJSONArray("statements");
        JSONArray statements = new JSONArray();
        for (int i = 0; i < original.length(); i++) {
            if (i == original.length() - 1) {
                statements.put("CREATE TABLE reader_failure_probe(value INTEGER);\n");
                statements.put("INSERT INTO missing_catalog_table VALUES(1);\n");
            }
            statements.put(original.getString(i));
        }
        broken.put("statements", statements);
        byte[] brokenAsset = recomputeSourceIdentity(broken);
        rejects(SQLiteException.class, () -> { try (CatalogStore ignored = new CatalogStore(file, brokenAsset)) {} });
        try (SQLiteDatabase db = openRaw(file)) {
            assertEquals(0, scalar(db, "PRAGMA application_id"));
            assertEquals(0, scalar(db, "PRAGMA user_version"));
            assertEquals(0, scalar(db, "SELECT count(*) FROM sqlite_master WHERE name NOT GLOB 'sqlite_*'"));
            assertEquals("ok", text(db, "PRAGMA integrity_check"));
        }
        try (CatalogStore retried = new CatalogStore(context, file)) {
            assertEquals(CatalogStore.APPLICATION_ID, scalar(retried.database(), "PRAGMA application_id"));
            assertEquals(10, scalar(retried.database(), "SELECT count(*) FROM sqlite_master WHERE type='table'"));
        }
    }

    public void rejectsTamperedAssetFieldsAndSource() throws Exception {
        List<byte[]> bad = new ArrayList<>();
        bad.add(encoded(object().put("source_sha256", zeros(64))));
        bad.add(encoded(object().put("source_bytes", object().getLong("source_bytes") + 1)));
        bad.add(encoded(object().put("source_bytes", "123")));
        bad.add(encoded(object().put("asset_version", "1")));
        bad.add(encoded(object().put("application_id", 1163416131)));
        bad.add(encoded(object().put("schema_version", 2)));
        bad.add(encoded(object().put("extra", true)));
        JSONObject missing = object();
        missing.remove("source_sha256");
        bad.add(encoded(missing));
        JSONObject sourceChange = object();
        sourceChange.getJSONArray("statements").put(0, sourceChange.getJSONArray("statements").getString(0) + "\n-- changed");
        bad.add(encoded(sourceChange));
        JSONObject wrongStatement = object();
        wrongStatement.getJSONArray("statements").put(0, 7);
        bad.add(encoded(wrongStatement));
        String raw = new String(asset, StandardCharsets.UTF_8);
        bad.add(("{\"asset_version\":1," + raw.substring(raw.indexOf('{') + 1)).getBytes(StandardCharsets.UTF_8));
        bad.add((raw + " true").getBytes(StandardCharsets.UTF_8));
        bad.add(raw.replaceFirst("\"asset_version\"\\s*:\\s*1", "\"asset_version\":1.0").getBytes(StandardCharsets.UTF_8));
        for (byte[] bytes : bad) {
            File file = absentFile();
            rejects(IOException.class, () -> { try (CatalogStore ignored = new CatalogStore(file, bytes)) {} });
            assertFalse("Asset was rejected after a database had already been created", file.exists());
        }
    }

    public void rejectsOversizedAndMalformedAssets() throws Exception {
        List<byte[]> bad = new ArrayList<>();
        bad.add(new byte[0]);
        bad.add(new byte[128 * 1024 + 1]);
        bad.add(new byte[]{(byte) 0xc3, 0x28});
        bad.add("[]".getBytes(StandardCharsets.UTF_8));
        JSONObject tooMany = object();
        JSONArray statements = new JSONArray();
        for (int i = 0; i < 129; i++) statements.put("SELECT 1;\n");
        tooMany.put("statements", statements);
        bad.add(recomputeSourceIdentity(tooMany));
        for (byte[] bytes : bad) {
            File file = absentFile();
            rejects(IOException.class, () -> { try (CatalogStore ignored = new CatalogStore(file, bytes)) {} });
            assertFalse(file.exists());
        }
    }

    public void enforcesWorkerOwnership() throws Exception {
        try (CatalogStore catalog = new CatalogStore(context, newFile())) {
            AtomicReference<Throwable> queryError = new AtomicReference<>();
            AtomicReference<Throwable> closeError = new AtomicReference<>();
            Thread other = new Thread(() -> {
                try { catalog.database(); } catch (Throwable error) { queryError.set(error); }
                try { catalog.close(); } catch (Throwable error) { closeError.set(error); }
            }, "catalog-wrong-owner");
            other.start();
            other.join(5000);
            assertFalse("Owner test thread did not finish", other.isAlive());
            assertNotNull(queryError.get());
            assertTrue(queryError.get() instanceof IllegalStateException);
            assertNotNull(closeError.get());
            assertTrue(closeError.get() instanceof IllegalStateException);
            assertEquals(1, scalar(catalog.database(), "PRAGMA user_version"));
        }
    }

    private File newFile() throws IOException {
        File file = File.createTempFile("reader-catalog-test-", ".db", context.getCacheDir());
        files.add(file);
        return file;
    }

    private File absentFile() throws IOException {
        File file = newFile();
        assertTrue(file.delete());
        return file;
    }

    private JSONObject object() throws Exception {
        return new JSONObject(new String(asset, StandardCharsets.UTF_8));
    }

    private static byte[] encoded(JSONObject object) {
        return object.toString().getBytes(StandardCharsets.UTF_8);
    }

    private static byte[] recomputeSourceIdentity(JSONObject object) throws Exception {
        StringBuilder source = new StringBuilder();
        JSONArray statements = object.getJSONArray("statements");
        for (int i = 0; i < statements.length(); i++) source.append(statements.getString(i));
        byte[] bytes = source.toString().getBytes(StandardCharsets.UTF_8);
        object.put("source_bytes", bytes.length);
        object.put("source_sha256", sha256(bytes));
        return encoded(object);
    }

    private static String sha256(byte[] bytes) throws Exception {
        StringBuilder result = new StringBuilder();
        for (byte value : MessageDigest.getInstance("SHA-256").digest(bytes))
            result.append(String.format(Locale.ROOT, "%02x", value & 255));
        return result.toString();
    }

    private static String zeros(int length) {
        char[] chars = new char[length];
        Arrays.fill(chars, '0');
        return new String(chars);
    }

    private static String id(int number) { return String.format(Locale.ROOT, "%032x", number); }

    private static SQLiteDatabase openRaw(File file) {
        return SQLiteDatabase.openDatabase(file.getAbsolutePath(), null,
                SQLiteDatabase.OPEN_READWRITE | SQLiteDatabase.CREATE_IF_NECESSARY
                        | SQLiteDatabase.NO_LOCALIZED_COLLATORS);
    }

    private static void insertShelf(SQLiteDatabase db, int number, String parent) {
        db.execSQL("INSERT INTO reader_shelves(shelf_id,parent_id,name) VALUES(?,?,?)",
                new Object[]{id(number), parent, "Shelf " + number});
    }

    private static long scalar(SQLiteDatabase db, String sql) {
        try (Cursor cursor = db.rawQuery(sql, null)) {
            assertTrue(cursor.moveToFirst());
            return cursor.getLong(0);
        }
    }

    private static String text(SQLiteDatabase db, String sql, String... args) {
        try (Cursor cursor = db.rawQuery(sql, args)) {
            assertTrue(cursor.moveToFirst());
            return cursor.getString(0);
        }
    }

    private interface Attempt { void run() throws Exception; }

    private static void assertEquals(long expected, long actual) {
        if (expected != actual) fail("Expected " + expected + ", got " + actual);
    }

    private static void assertEquals(String expected, String actual) {
        if (expected == null ? actual != null : !expected.equals(actual))
            fail("Expected " + expected + ", got " + actual);
    }

    private static void assertTrue(boolean value) {
        if (!value) fail("Expected true");
    }

    private static void assertFalse(boolean value) { assertFalse("Expected false", value); }

    private static void assertFalse(String message, boolean value) {
        if (value) fail(message);
    }

    private static void assertNotNull(Object value) {
        if (value == null) fail("Expected a non-null value");
    }

    private static void fail(String message) { throw new AssertionError(message); }

    private static void rejects(Class<? extends Throwable> expected, Attempt attempt) throws Exception {
        try { attempt.run(); }
        catch (Throwable error) {
            if (expected.isInstance(error)) return;
            throw new AssertionError("Expected " + expected.getName() + ", got " + error, error);
        }
        fail("Expected " + expected.getName());
    }
}
