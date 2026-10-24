// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.database.Cursor;

import android.database.sqlite.SQLiteException;
import android.os.Bundle;
import android.os.Process;
import android.os.SystemClock;
import android.util.Log;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Arrays;

/** Real SDK and installed product SQLite; independent killed-process probes. */
public final class ImportMappingTest extends Instrumentation {
    private Context context;
    private File directory;
    private String phase;
    private BookStore phaseStore;
    private CatalogStore phaseCatalog;
    private interface Check { void run() throws Exception; }
    private static final String[] NAMES = {
            "hashesStoredOriginalInChunks", "registersAtomicallyAndIdempotently",
            "preservesDuplicateMetadataAndHistory", "keepsLegacyAndBoundedEpubModes",
            "rejectsWrongCopyHashAndLength", "rejectsInvalidatedSourceReads",
            "repairsSdkCommitBeforeCatalog", "rollsBackSqlFailureAndRepairsOnReopen",
            "cancelsBeforePublicationWithoutDeletingDuplicate", "retainsPublishedBookOnCatalogFailure",
            "clearsLocalMappingBeforeSdkDelete", "rejectsConflictingLocalIdentity",
            "keepsOldestHistoricalDuplicateAndActualMode", "normalizesSortTitleWithoutChangingDisplayTitle"
    };

    @Override public void onCreate(Bundle arguments) {
        super.onCreate(arguments);
        phase = arguments == null ? null : arguments.getString("phase");
        start();
    }

    @Override public void onStart() {
        context = getTargetContext();
        if (phase != null) { runPhase(); return; }
        Check[] checks = {
                this::hashesStoredOriginalInChunks, this::registersAtomicallyAndIdempotently,
                this::preservesDuplicateMetadataAndHistory, this::keepsLegacyAndBoundedEpubModes,
                this::rejectsWrongCopyHashAndLength, this::rejectsInvalidatedSourceReads,
                this::repairsSdkCommitBeforeCatalog, this::rollsBackSqlFailureAndRepairsOnReopen,
                this::cancelsBeforePublicationWithoutDeletingDuplicate, this::retainsPublishedBookOnCatalogFailure,
                this::clearsLocalMappingBeforeSdkDelete, this::rejectsConflictingLocalIdentity,
                this::keepsOldestHistoricalDuplicateAndActualMode, this::normalizesSortTitleWithoutChangingDisplayTitle
        };
        int failures = 0;
        long start = SystemClock.elapsedRealtime();
        for (int index = 0; index < checks.length; index++) {
            Bundle status = status(NAMES[index], index + 1);
            sendStatus(1, status);
            Throwable failed = null;
            try {
                directory = new File(context.getCacheDir(), "import-mapping-" + index);
                remove(directory); require(directory.mkdirs(), "test directory");
                checks[index].run();
            } catch (Throwable error) { failed = error; }
            finally { try { ProductFixture.closeAll(); remove(directory); } catch (Throwable error) { if (failed == null) failed = error; } }
            Bundle completed = status(NAMES[index], index + 1);
            if (failed == null) { completed.putString("stream", "."); sendStatus(0, completed); }
            else {
                failures++; completed.putString("stack", Log.getStackTraceString(failed));
                completed.putString("stream", "Failure in " + NAMES[index] + ": " + failed);
                sendStatus(-2, completed);
            }
        }
        Bundle result = new Bundle();
        result.putString("stream", "\nTime: " + (SystemClock.elapsedRealtime() - start)/1000.0 + "\n\n"
                + (failures == 0 ? "OK (" + NAMES.length + " tests)\n" : "FAILURES!!! Tests run: " + NAMES.length + ", Failures: " + failures));
        finish(failures == 0 ? Activity.RESULT_OK : Activity.RESULT_CANCELED, result);
    }

    private Bundle status(String name, int index) {
        Bundle result = new Bundle();
        result.putString("id", "InstrumentationTestRunner");
        result.putString("class", getClass().getName()); result.putString("test", name);
        result.putInt("numtests", NAMES.length); result.putInt("current", index);
        return result;
    }
    private BookStore open() throws Exception { return new BookStore(context, new File(directory, "library.db")); }
    private static HostTask task() { return new HostTask(() -> false); }
    private CatalogStore catalog() throws Exception { return new CatalogStore(context, new File(directory, "reader-catalog.db")); }
    private File text(String name, int count) throws Exception {
        File file = new File(directory, name);
        try (FileOutputStream out = new FileOutputStream(file)) {
            byte[] bytes = ("Source " + name + ": original text for persistent reading.\n").getBytes(StandardCharsets.UTF_8);
            for (int index = 0; index < count; index++) out.write(bytes);
        }
        return file;
    }
    private File epub() throws Exception {
        File file = new File(directory, "Sample.epub");
        try (InputStream in = getContext().getAssets().open("mapping/Sample.epub");
             FileOutputStream out = new FileOutputStream(file)) {
            byte[] chunk = new byte[65536]; int count;
            while ((count = in.read(chunk)) != -1) out.write(chunk, 0, count);
        }
        return file;
    }
    private static String hash(File file) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (InputStream in = new java.io.FileInputStream(file)) {
            byte[] chunk = new byte[65536]; int count;
            while ((count = in.read(chunk)) != -1) digest.update(chunk, 0, count);
        }
        StringBuilder value = new StringBuilder(64);
        for (byte b : digest.digest()) value.append(String.format(java.util.Locale.ROOT, "%02x", b));
        return value.toString();
    }
    private static long number(ProductFixture db, String sql, String... args) {
        try (Cursor row = db.rawQuery(sql, args)) { require(row.moveToFirst(), "number row"); return row.getLong(0); }
    }
    private static String value(ProductFixture db, String sql, String... args) {
        try (Cursor row = db.rawQuery(sql, args)) { require(row.moveToFirst(), "text row"); return row.getString(0); }
    }
    private static void equal(Object expected, Object actual) { require(expected.equals(actual), expected + " != " + actual); }
    private static void require(boolean value, String why) { if (!value) throw new AssertionError(why); }
    private static void rejects(Class<? extends Throwable> expected, Check check) throws Exception {
        try { check.run(); } catch (Throwable error) {
            if (expected.isInstance(error)) return;
            throw new AssertionError("Expected " + expected.getName() + ", got " + error, error);
        }
        throw new AssertionError("Expected " + expected.getName());
    }
    private static void remove(File file) {
        if (file == null || !file.exists()) return;
        File[] children = file.listFiles();
        if (children != null) for (File child : children) remove(child);
        require(file.delete(), "test cleanup: " + file);
    }
    private BookStore.VerifiedSource imported(BookStore store, File file) throws Exception {
        NativeLibrary.ImportResult result = store.importFile(file.getPath(), NativeLibrary.FORMAT_TXT, file.getName());
        return store.verifySource(result.id, hash(file), file.length(), task());
    }

    private void hashesStoredOriginalInChunks() throws Exception {
        File source = text("multi-chunk.txt", 6000);
        try (BookStore store = open()) {
            BookStore.VerifiedSource verified = imported(store, source);
            equal(hash(source), verified.sha256); equal(source.length(), verified.bytes);
            require(source.length() > 65536 * 2, "multiple SDK reads");
            require(source.delete(), "remove copied path");
            BookStore.VerifiedSource original = store.verifySource(verified.book.id, verified.sha256, verified.bytes, task());
            equal(verified.key, original.key); // No prefs path or external source participates.
        }
    }
    private void registersAtomicallyAndIdempotently() throws Exception {
        try (BookStore store = open()) {
            BookStore.VerifiedSource source = imported(store, text("one.txt", 2));
            store.finalizeImport(source); store.finalizeImport(source);
            try (CatalogStore catalog = catalog()) {
                equal(1L, number(ProductFixture.of(catalog), "SELECT count(*) FROM reader_books"));
                equal(source.book.id, number(ProductFixture.of(catalog), "SELECT sdk_book_id FROM reader_local_books"));
                equal("reflow_global", value(ProductFixture.of(catalog), "SELECT location_kind FROM reader_local_books"));
                equal(source.key, value(ProductFixture.of(catalog), "SELECT book_key FROM reader_books"));
                equal(0L, number(ProductFixture.of(catalog), "SELECT count(*) FROM reader_revisions"));
            }
        }
    }
    private void preservesDuplicateMetadataAndHistory() throws Exception {
        File source = text("duplicate.txt", 2);
        try (BookStore store = open()) {
            BookStore.VerifiedSource first = imported(store, source); store.finalizeImport(first);
            store.saveNote(first.book.id, 0, 0, 6, "Keep SDK note");
            try (CatalogStore catalog = catalog()) {
                ProductFixture.of(catalog).execSQL("UPDATE reader_books SET title='User title',favorite=1,deleted=1");
                ProductFixture.of(catalog).execSQL("INSERT INTO reader_revisions VALUES(?,?,?,?,?,?)", new Object[]{
                        "00000000000000000000000000000001", "book", first.key, "delete", "{}", "0".repeat(64)});
                ProductFixture.of(catalog).execSQL("INSERT INTO reader_outbox(revision_id) VALUES(?)",
                        new Object[]{"00000000000000000000000000000001"});
            }
            NativeLibrary.ImportResult duplicate = store.importFile(source.getPath(), 1, "Wrong replacement title");
            require(!duplicate.created, "must reuse SDK original"); equal(first.book.id, duplicate.id);
            store.finalizeImport(store.verifySource(duplicate.id, hash(source), source.length(), task()));
            equal(1, store.notes(first.book.id).size());
            try (CatalogStore catalog = catalog()) {
                equal("User title", value(ProductFixture.of(catalog), "SELECT title FROM reader_books"));
                equal(1L, number(ProductFixture.of(catalog), "SELECT deleted FROM reader_books"));
                equal(1L, number(ProductFixture.of(catalog), "SELECT count(*) FROM reader_tombstones"));
                equal(1L, number(ProductFixture.of(catalog), "SELECT count(*) FROM reader_outbox"));
            }
        }
    }
    private void keepsLegacyAndBoundedEpubModes() throws Exception {
        File file = epub();
        try (BookStore store = open()) {
            NativeLibrary.ImportResult legacy = store.nativeLibrary().importLegacyFile(file.getPath(), 4, "Legacy");
            BookStore.VerifiedSource source = store.verifySource(legacy.id, hash(file), file.length(), task());
            equal("reflow_global", source.location); store.finalizeImport(source);
            NativeLibrary.ImportResult duplicate = store.importFile(file.getPath(), 4, "Bounded request");
            require(!duplicate.created, "legacy duplicate"); equal(legacy.id, duplicate.id);
            equal("reflow_global", store.verifySource(duplicate.id, hash(file), file.length(), task()).location);
            store.deleteBook(legacy.id);
            NativeLibrary.ImportResult bounded = store.importFile(file.getPath(), 4, "Bounded");
            BookStore.VerifiedSource newSource = store.verifySource(bounded.id, hash(file), file.length(), task());
            equal("epub_chapter", newSource.location); store.finalizeImport(newSource);
        }
    }
    private void rejectsWrongCopyHashAndLength() throws Exception {
        File file = text("mismatch.txt", 2);
        try (BookStore store = open()) {
            long id = store.importFile(file.getPath(), 1, "Mismatch").id;
            rejects(java.io.IOException.class, () -> store.verifySource(id, "0".repeat(64), file.length(), task()));
            rejects(java.io.IOException.class, () -> store.verifySource(id, hash(file), file.length() + 1, task()));
            try (CatalogStore catalog = catalog()) { equal(0L, number(ProductFixture.of(catalog), "SELECT count(*) FROM reader_books")); }
            equal(1, store.books().size());
        }
    }
    private void rejectsInvalidatedSourceReads() throws Exception {
        try (BookStore store = open()) {
            BookStore.VerifiedSource book = imported(store, text("invalidated.txt", 2));
            try (NativeLibrary.Source source = store.nativeLibrary().source(book.book.id)) {
                store.deleteBook(book.book.id);
                rejects(RuntimeException.class, () -> source.read(0, new byte[64], 64));
            }
            rejects(RuntimeException.class, () -> store.nativeLibrary().source(book.book.id));
        }
    }
    private void repairsSdkCommitBeforeCatalog() throws Exception {
        long id; String key;
        try (BookStore store = open()) {
            BookStore.VerifiedSource source = imported(store, text("committed.txt", 2));
            id = source.book.id; key = source.key;
            HostTask commit = task(); commit.commit(() -> {}); commit.cancel(); commit.check();
            try (CatalogStore catalog = catalog()) { equal(0L, number(ProductFixture.of(catalog), "SELECT count(*) FROM reader_books")); }
        }
        try (BookStore reopened = open(); CatalogStore catalog = catalog()) {
            equal(1, reopened.books().size()); require(!reopened.metadataRepairPending(), "repair succeeded");
            equal(key, value(ProductFixture.of(catalog), "SELECT book_key FROM reader_local_books WHERE sdk_book_id=?", Long.toString(id)));
            reopened.repairMissingMappings(); equal(1L, number(ProductFixture.of(catalog), "SELECT count(*) FROM reader_books"));
        }
    }
    private void rejectLocalInsert(CatalogStore catalog) {
        ProductFixture.of(catalog).execSQL("CREATE TRIGGER mapping_failure BEFORE INSERT ON reader_local_books BEGIN SELECT RAISE(ABORT,'injected local mapping rejection'); END");
    }
    private void rollsBackSqlFailureAndRepairsOnReopen() throws Exception {
        long id;
        try (BookStore store = open(); CatalogStore catalog = catalog()) {
            BookStore.VerifiedSource source = imported(store, text("rollback.txt", 2)); id = source.book.id;
            rejectLocalInsert(catalog); rejects(SQLiteException.class, () -> store.finalizeImport(source));
            require(store.metadataRepairPending(), "repair pending");
            equal(0L, number(ProductFixture.of(catalog), "SELECT count(*) FROM reader_books"));
            equal(0L, number(ProductFixture.of(catalog), "SELECT count(*) FROM reader_local_books"));
            equal(1, store.books().size());
            ProductFixture.of(catalog).execSQL("DROP TRIGGER mapping_failure");
        }
        try (BookStore reopened = open(); CatalogStore catalog = catalog()) {
            equal(id, number(ProductFixture.of(catalog), "SELECT sdk_book_id FROM reader_local_books"));
            require(!reopened.metadataRepairPending(), "reopened repair");
        }
    }
    private void cancelsBeforePublicationWithoutDeletingDuplicate() throws Exception {
        File file = text("cancel.txt", 3000);
        try (BookStore store = open()) {
            BookStore.VerifiedSource first = imported(store, file); store.finalizeImport(first);
            NativeLibrary.ImportResult duplicate = store.importFile(file.getPath(), 1, "duplicate");
            require(!duplicate.created, "duplicate retained");
            HostTask cancelled = task(); cancelled.cancel();
            rejects(HostTask.Cancelled.class, () -> store.verifySource(duplicate.id, hash(file), file.length(), cancelled));
            equal(first.book.id, store.books().get(0).id);
            NativeLibrary.ImportResult created = store.importFile(text("new-cancel.txt", 3).getPath(), 1, "new");
            require(created.created, "created compensation"); store.deleteBook(created.id);
            equal(1, store.books().size()); require(file.isFile(), "duplicate original retained");
        }
    }
    private void retainsPublishedBookOnCatalogFailure() throws Exception {
        File file = text("published.txt", 3);
        try (BookStore store = open(); CatalogStore catalog = catalog()) {
            BookStore.VerifiedSource source = imported(store, file);
            HostTask commit = task(); commit.commit(() -> {}); commit.cancel(); commit.check();
            rejectLocalInsert(catalog); rejects(SQLiteException.class, () -> store.finalizeImport(source));
            require(file.isFile(), "published original retained"); equal(1, store.books().size());
            equal(source.sha256, store.verifySource(source.book.id, hash(file), file.length(), commit).sha256);
        }
    }
    private void clearsLocalMappingBeforeSdkDelete() throws Exception {
        try (BookStore store = open(); CatalogStore catalog = catalog()) {
            BookStore.VerifiedSource source = imported(store, text("removed.txt", 2)); store.finalizeImport(source);
            store.deleteBook(source.book.id);
            equal(0L, number(ProductFixture.of(catalog), "SELECT count(*) FROM reader_local_books"));
            equal(1L, number(ProductFixture.of(catalog), "SELECT count(*) FROM reader_books"));
            equal(0, store.books().size());
            BookStore.VerifiedSource other = imported(store, text("replacement.txt", 2)); store.finalizeImport(other);
            equal(other.key, value(ProductFixture.of(catalog), "SELECT book_key FROM reader_local_books"));
            // Simulated interruption after mapping delete and before SDK delete is repairable.
            catalog.removeLocalBook(other.book.id); store.repairMissingMappings();
            equal(other.key, value(ProductFixture.of(catalog), "SELECT book_key FROM reader_local_books"));
        }
    }
    private void rejectsConflictingLocalIdentity() throws Exception {
        try (BookStore store = open(); CatalogStore catalog = catalog()) {
            BookStore.VerifiedSource first = imported(store, text("first.txt", 2)); store.finalizeImport(first);
            BookStore.VerifiedSource second = imported(store, text("second.txt", 2));
            ProductFixture.of(catalog).execSQL("UPDATE reader_local_books SET sdk_book_id=?", new Object[]{second.book.id});
            rejects(SQLiteException.class, () -> store.finalizeImport(second));
            equal(first.key, value(ProductFixture.of(catalog), "SELECT book_key FROM reader_local_books"));
            equal(1L, number(ProductFixture.of(catalog), "SELECT count(*) FROM reader_books"));
            equal(2, store.books().size());
        }
    }

    private void keepsOldestHistoricalDuplicateAndActualMode() throws Exception {
        File file = epub();
        for (boolean legacyOldest : new boolean[]{false, true}) {
            File folder = new File(directory, legacyOldest ? "legacy-oldest" : "bounded-oldest");
            require(folder.mkdirs(), "historical database directory");
            long firstId;
            String key;
            try (BookStore store = new BookStore(context, new File(folder, "library.db"))) {
                NativeLibrary library = store.nativeLibrary();
                NativeLibrary.ImportResult first = library.importHistoricalFile(file.getPath(), 4, "Oldest", legacyOldest);
                NativeLibrary.ImportResult second = library.importHistoricalFile(file.getPath(), 4, "Middle", !legacyOldest);
                NativeLibrary.ImportResult third = library.importHistoricalFile(file.getPath(), 4, "Newest", !legacyOldest);
                require(first.created && second.created && third.created, "public non-unique SDK imports created actual historical rows");
                require(first.id < second.id && second.id < third.id, "historical SDK IDs");
                firstId = first.id;
                BookStore.VerifiedSource newest = store.verifySource(third.id, hash(file), file.length(), task());
                key = newest.key;
                store.finalizeImport(newest);
                try (CatalogStore catalog = new CatalogStore(context, new File(folder, "reader-catalog.db"))) {
                    ProductFixture.of(catalog).execSQL("UPDATE reader_books SET title='Keep product title',favorite=1");
                }
                // Reverse source order proves canonical choice does not depend on enumeration.
                store.finalizeImport(store.verifySource(second.id, hash(file), file.length(), task()));
                store.finalizeImport(store.verifySource(first.id, hash(file), file.length(), task()));
                store.finalizeImport(newest);
                store.repairMissingMappings(); require(!store.metadataRepairPending(), "historical duplicates are repairable");
                equal(3, store.books().size());
            }
            try (BookStore reopened = new BookStore(context, new File(folder, "library.db"));
                 CatalogStore catalog = new CatalogStore(context, new File(folder, "reader-catalog.db"))) {
                require(!reopened.metadataRepairPending(), "restarted canonical mapping");
                equal(3, reopened.books().size());
                equal(1L, number(ProductFixture.of(catalog), "SELECT count(*) FROM reader_books"));
                equal(1L, number(ProductFixture.of(catalog), "SELECT count(*) FROM reader_local_books"));
                equal(firstId, number(ProductFixture.of(catalog), "SELECT sdk_book_id FROM reader_local_books"));
                equal(legacyOldest ? "reflow_global" : "epub_chapter",
                        value(ProductFixture.of(catalog), "SELECT location_kind FROM reader_local_books"));
                equal(key, value(ProductFixture.of(catalog), "SELECT book_key FROM reader_local_books"));
                equal("Keep product title", value(ProductFixture.of(catalog), "SELECT title FROM reader_books"));
                equal(1L, number(ProductFixture.of(catalog), "SELECT favorite FROM reader_books"));
            }
        }
    }

    private void normalizesSortTitleWithoutChangingDisplayTitle() throws Exception {
        File file = text("unicode.txt", 2);
        String displayTitle = "Cafe\u0301 \u212b";
        try (BookStore store = open(); CatalogStore catalog = catalog()) {
            NativeLibrary.ImportResult result = store.importFile(file.getPath(), 1, displayTitle);
            store.finalizeImport(store.verifySource(result.id, hash(file), file.length(), task()));
            equal(displayTitle, value(ProductFixture.of(catalog), "SELECT title FROM reader_books"));
            equal("Caf\u00e9 \u00c5", value(ProductFixture.of(catalog), "SELECT sort_title FROM reader_books"));
            equal(displayTitle, store.books().get(0).title);
        }
    }

    private void runPhase() {
        Bundle result = new Bundle();
        try {
            boolean during = phase.endsWith("during");
            directory = new File(context.getFilesDir(), "mapping-process-" + (during ? "during" : "before"));
            if (phase.startsWith("seed-")) {
                remove(directory); require(directory.mkdirs(), "phase directory");
                BookStore store = phaseStore = open();
                File file = text("published.txt", 2000);
                BookStore.VerifiedSource source = imported(store, file);
                HostTask commit = task(); commit.commit(() -> {});
                if (during) {
                    CatalogStore catalog = phaseCatalog = catalog();
                    ProductFixture db = ProductFixture.of(catalog);
                    db.beginTransaction();
                    db.execSQL("INSERT INTO reader_books(book_key,format,source_sha256,source_bytes,title,sort_title) VALUES(?,?,?,?,?,?)",
                            new Object[]{source.key, source.format, source.sha256, source.bytes, source.book.title, source.book.title});
                    // Kill with a live, uncommitted product write after the real SDK commit.
                }
                File marker = new File(directory, "seed-ready");
                try (FileOutputStream out = new FileOutputStream(marker)) { out.write(source.key.getBytes(StandardCharsets.UTF_8)); out.getFD().sync(); }
                Log.i("EXRMapping", "killing seed " + phase);
                Process.killProcess(Process.myPid());
                throw new AssertionError("Process kill returned");
            }
            require(phase.startsWith("recover-"), "known phase");
            require(new File(directory, "seed-ready").isFile(), "seed process reached committed SDK state");
            try (CatalogStore before = catalog()) {
                equal(0L, number(ProductFixture.of(before), "SELECT count(*) FROM reader_books"));
                equal(0L, number(ProductFixture.of(before), "SELECT count(*) FROM reader_local_books"));
            }
            try (BookStore reopened = open(); CatalogStore catalog = catalog()) {
                require(!reopened.metadataRepairPending(), "recovered mapping"); equal(1, reopened.books().size());
                equal(1L, number(ProductFixture.of(catalog), "SELECT count(*) FROM reader_local_books"));
                BookStore.VerifiedSource source = reopened.verifySource(reopened.books().get(0).id,
                        hash(new File(directory, "published.txt")), new File(directory, "published.txt").length(), task());
                equal(source.key, value(ProductFixture.of(catalog), "SELECT book_key FROM reader_local_books"));
                reopened.repairMissingMappings(); equal(1L, number(ProductFixture.of(catalog), "SELECT count(*) FROM reader_books"));
                equal("ok", value(ProductFixture.of(catalog), "PRAGMA integrity_check"));
            }
            result.putString("stream", "EXR_MAPPING_RECOVERED " + phase + "\n");
            finish(Activity.RESULT_OK, result);
        } catch (Throwable error) {
            result.putString("stream", "EXR_MAPPING_PHASE_FAILED " + phase + " " + error);
            result.putString("shortMsg", Log.getStackTraceString(error)); finish(Activity.RESULT_CANCELED, result);
        }
    }
}

