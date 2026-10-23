// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.content.Context;

import java.io.File;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

/** Worker-thread facade over the SDK library; no call is made from the UI thread. */
final class BookStore implements AutoCloseable {
    private final NativeLibrary library;
    private final CatalogStore catalog;
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
        library.deleteBook(bookId);
    }

    @Override
    public void close() {
        try { library.close(); }
        finally { catalog.close(); }
    }
}
