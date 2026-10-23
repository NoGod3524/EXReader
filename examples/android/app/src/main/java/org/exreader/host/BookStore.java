// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.content.Context;
import android.util.Log;

import java.io.File;
import java.io.IOException;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.List;

/** Worker-thread facade over the SDK library; no call is made from the UI thread. */
final class BookStore implements AutoCloseable {
    private final NativeLibrary library;
    private final CatalogStore catalog;
    private boolean metadataRepairPending;
    NativeLibrary nativeLibrary() { return library; }
    boolean bounded(long bookId) { return library.bounded(bookId); }

    BookStore(Context context, File database) throws IOException {
        CatalogStore openedCatalog = new CatalogStore(context,
                new File(database.getParentFile(), "reader-catalog.db"));
        NativeLibrary openedLibrary;
        try {
            openedLibrary = new NativeLibrary(database.getAbsolutePath());
        } catch (RuntimeException | Error error) {
            openedCatalog.close();
            throw error;
        }
        catalog = openedCatalog;
        library = openedLibrary;
        repairMissingMappings();
    }

    boolean metadataRepairPending() { return metadataRepairPending; }

    static final class VerifiedSource {
        final NativeLibrary.Book book;
        final String format, sha256, key, location;
        final long bytes;
        VerifiedSource(NativeLibrary.Book book, String sha256, long bytes, String location) {
            this.book = book;
            this.format = MainActivity.formatName(book.format).toLowerCase(java.util.Locale.ROOT);
            this.sha256 = sha256; this.bytes = bytes; this.key = format + ":" + sha256;
            this.location = location;
        }
    }

    VerifiedSource verifySource(long id, String expectedSha256, long expectedBytes, HostTask task)
            throws IOException {
        NativeLibrary.Book book = find(id);
        if (book == null) throw new IOException("Imported SDK book is missing");
        MessageDigest digest;
        try { digest = MessageDigest.getInstance("SHA-256"); }
        catch (NoSuchAlgorithmException impossible) { throw new AssertionError(impossible); }
        long bytes;
        try (NativeLibrary.Source source = library.source(id)) {
            bytes = source.size;
            if (expectedSha256 != null && bytes != expectedBytes)
                throw new IOException("Copied and SDK source lengths differ");
            byte[] chunk = new byte[65536];
            for (long offset = 0; offset < bytes;) {
                task.check();
                int count = (int)Math.min(chunk.length, bytes - offset);
                int read = source.read(offset, chunk, count);
                if (read <= 0 || read > count) throw new IOException("Invalid SDK source read");
                digest.update(chunk, 0, read); offset += read;
            }
        }
        task.check();
        StringBuilder hash = new StringBuilder(64);
        for (byte value : digest.digest()) {
            hash.append(Character.forDigit((value >>> 4) & 15, 16));
            hash.append(Character.forDigit(value & 15, 16));
        }
        if (expectedSha256 != null && !expectedSha256.equals(hash.toString()))
            throw new IOException("Copied and SDK original hashes differ");
        String location = book.fixed() ? "fixed_page" : book.format == NativeLibrary.FORMAT_EPUB
                && library.bounded(id) ? "epub_chapter" : "reflow_global";
        return new VerifiedSource(book, hash.toString(), bytes, location);
    }

    void finalizeImport(VerifiedSource source) {
        try { catalog.attach(source); }
        catch (RuntimeException error) { metadataRepairPending = true; throw error; }
    }

    /** SDK is authoritative for bytes; retry only IDs absent from the local mapping. */
    void repairMissingMappings() {
        metadataRepairPending = false;
        NativeLibrary.Book[] books;
        try { books = library.books(); }
        catch (RuntimeException error) {
            metadataRepairPending = true;
            Log.w("EXRHost", "Metadata repair pending; SDK book scan failed", error);
            return;
        }
        for (NativeLibrary.Book book : books) {
            try {
                if (!catalog.hasLocalBook(book.id))
                    catalog.attach(verifySource(book.id, null, 0, new HostTask(() -> false)));
            } catch (IOException | RuntimeException error) {
                metadataRepairPending = true;
                Log.w("EXRHost", "Metadata repair pending for SDK book " + book.id, error);
            }
        }
    }

    List<NativeLibrary.Book> books() {
        List<NativeLibrary.Book> result = new ArrayList<>();
        for (NativeLibrary.Book book : library.books()) result.add(book);
        return result;
    }

    NativeLibrary.Book find(long id) {
        for (NativeLibrary.Book book : library.books()) {
            if (book.id == id) return book;
        }
        return null;
    }

    NativeLibrary.ImportResult importFile(String path, int format, String title) {
        return library.importFile(path, format, title);
    }

    void setPosition(long bookId, long position) {
        library.setPosition(bookId, position);
    }

    long[] progress(long bookId) {
        return library.progress(bookId);
    }

    void saveProgress(long bookId, long offset) {
        library.saveProgress(bookId, offset);
    }

    List<NativeLibrary.Note> notes(long bookId) {
        List<NativeLibrary.Note> result = new ArrayList<>();
        for (NativeLibrary.Note note : library.notes(bookId)) result.add(note);
        return result;
    }

    long saveNote(long bookId, long noteId, long start, long end, String comment) {
        return library.saveNote(bookId, noteId, start, end, comment);
    }

    void updateNoteText(long bookId, long noteId, String comment) {
        library.updateNoteText(bookId, noteId, comment);
    }

    void removeNote(long bookId, long noteId) {
        library.removeNote(bookId, noteId);
    }

    List<NativeLibrary.FixedNote> fixedNotes(long bookId) {
        List<NativeLibrary.FixedNote> result = new ArrayList<>();
        for (NativeLibrary.FixedNote note : library.fixedNotes(bookId)) result.add(note);
        return result;
    }

    long saveFixedNote(long bookId, long noteId, long page, long start, long end, String comment) {
        return library.saveFixedNote(bookId, noteId, page, start, end, comment);
    }

    void removeFixedNote(long bookId, long noteId) {
        library.removeFixedNote(bookId, noteId);
    }

    void deleteBook(long bookId) {
        // Remove first: a failed/interrupted SDK delete leaves a recoverable missing mapping.
        catalog.removeLocalBook(bookId);
        library.deleteBook(bookId);
    }

    @Override
    public void close() {
        try { library.close(); }
        finally { catalog.close(); }
    }
}
