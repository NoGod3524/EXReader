// SPDX-License-Identifier: MIT
package org.exreader.host;

import java.util.ArrayList;
import java.util.List;

/**
 * Thin JNI bridge over the installed SDK library/annotation API. Every call is
 * made from the single host worker thread; native work on a handle is serial.
 */
public final class NativeLibrary implements AutoCloseable {
    static { System.loadLibrary("exreader_host"); }

    public static final int FORMAT_TXT = 1;
    public static final int FORMAT_HTML = 2;
    public static final int FORMAT_FB2 = 3;
    public static final int FORMAT_EPUB = 4;
    public static final int FORMAT_DOCX = 5;
    public static final int FORMAT_RTF = 6;
    public static final int FORMAT_MOBI = 7;
    public static final int FORMAT_PDF = 8;
    public static final int FORMAT_CBZ = 9;

    public static final class Book {
        public final long id;
        public final int format;
        public final String title;
        public final String author;
        public final String tags;
        public final int favorite;
        public final int status;
        public final long position;

        Book(long id, int format, String title, String author, String tags,
             int favorite, int status, long position) {
            this.id = id;
            this.format = format;
            this.title = title;
            this.author = author;
            this.tags = tags;
            this.favorite = favorite;
            this.status = status;
            this.position = position;
        }

        public boolean fixed() {
            return format == FORMAT_PDF || format == FORMAT_CBZ;
        }
    }

    public static final class Note {
        public final long id;
        public final long start;
        public final long end;
        public final String comment;
        public final String selected;
        public String[] location;

        Note(long id, long start, long end, String comment, String selected) {
            this.id = id;
            this.start = start;
            this.end = end;
            this.comment = comment;
            this.selected = selected;
        }
    }

    public static final class FixedNote {
        public final long id;
        public final long page;
        public final long start;
        public final long end;
        public final String comment;
        public final String selected;

        FixedNote(long id, long page, long start, long end, String comment, String selected) {
            this.id = id;
            this.page = page;
            this.start = start;
            this.end = end;
            this.comment = comment;
            this.selected = selected;
        }
    }

    public static final class ImportResult {
        public final long id;
        public final boolean created;

        ImportResult(long id, boolean created) {
            this.id = id;
            this.created = created;
        }
    }

    private long handle;

    public NativeLibrary(String path) {
        handle = nativeOpen(path);
        if (handle == 0) throw new IllegalStateException("Cannot open the native library");
    }

    public static String identity() {
        return nativeIdentity();
    }

    public Book[] books() {
        String[][] rows = nativeBooks(checked());
        Book[] books = new Book[rows.length];
        for (int i = 0; i < rows.length; i++) {
            String[] row = rows[i];
            books[i] = new Book(parseLong(row[0]), parseInt(row[1]), row[2], row[3], row[4],
                    parseInt(row[5]), parseInt(row[6]), parseLong(row[7]));
        }
        return books;
    }

    public ImportResult importFile(String path, int format, String title) {
        long[] values = nativeImportFile(checked(), path, format, title);
        return new ImportResult(values[0], values[1] != 0);
    }

    public void setPosition(long bookId, long position) {
        nativeSetPosition(checked(), bookId, position);
    }

    public Note[] notes(long bookId) {
        String[][] rows = nativeNotes(checked(), bookId);
        Note[] notes = new Note[rows.length];
        for (int i = 0; i < rows.length; i++) {
            String[] row = rows[i];
            notes[i] = new Note(parseLong(row[0]), parseLong(row[1]), parseLong(row[2]), row[3], row[4]);
            if(row.length==13) notes[i].location=java.util.Arrays.copyOfRange(row,5,13);
        }
        return notes;
    }

    public long saveNote(long bookId, long noteId, long start, long end, String comment) {
        return nativeSaveNote(checked(), bookId, noteId, start, end, comment);
    }

    public void updateNoteText(long bookId, long noteId, String comment) {
        nativeUpdateNoteText(checked(), bookId, noteId, comment);
    }

    public void removeNote(long bookId, long noteId) {
        nativeRemoveNote(checked(), bookId, noteId);
    }

    public FixedNote[] fixedNotes(long bookId) {
        String[][] rows = nativeFixedNotes(checked(), bookId);
        FixedNote[] notes = new FixedNote[rows.length];
        for (int i = 0; i < rows.length; i++) {
            String[] row = rows[i];
            notes[i] = new FixedNote(parseLong(row[0]), parseLong(row[1]), parseLong(row[2]),
                    parseLong(row[3]), row[4], row[5]);
        }
        return notes;
    }

    public long saveFixedNote(long bookId, long noteId, long page, long start, long end, String comment) {
        return nativeSaveFixedNote(checked(), bookId, noteId, page, start, end, comment);
    }

    public void removeFixedNote(long bookId, long noteId) {
        nativeRemoveFixedNote(checked(), bookId, noteId);
    }

    /** {state, start offset}; start is -1 when the SDK has no usable range. */
    public long[] progress(long bookId) {
        return nativeProgress(checked(), bookId);
    }

    public void saveProgress(long bookId, long offset) {
        nativeSaveProgress(checked(), bookId, offset);
    }

    public void deleteBook(long bookId) {
        nativeDeleteBook(checked(), bookId);
    }

    boolean bounded(long bookId) { return nativeBounded(checked(),bookId); }

    long checked() {
        if (handle == 0) throw new IllegalStateException("Library is closed");
        return handle;
    }

    private static long parseLong(String value) {
        try {
            return Long.parseLong(value);
        } catch (NumberFormatException error) {
            return 0;
        }
    }

    private static int parseInt(String value) {
        try {
            return Integer.parseInt(value);
        } catch (NumberFormatException error) {
            return 0;
        }
    }

    @Override
    public void close() {
        if (handle != 0) {
            nativeClose(handle);
            handle = 0;
        }
    }

    private static native String nativeIdentity();
    private static native boolean nativeBounded(long handle,long bookId);
    private static native long nativeOpen(String path);
    private static native void nativeClose(long handle);
    private static native String[][] nativeBooks(long handle);
    private static native long[] nativeImportFile(long handle, String path, int format, String title);
    private static native void nativeSetPosition(long handle, long bookId, long position);
    private static native String[][] nativeNotes(long handle, long bookId);
    private static native long nativeSaveNote(long handle, long bookId, long noteId, long start, long end, String comment);
    private static native void nativeUpdateNoteText(long handle, long bookId, long noteId, String comment);
    private static native void nativeRemoveNote(long handle, long bookId, long noteId);
    private static native String[][] nativeFixedNotes(long handle, long bookId);
    private static native long nativeSaveFixedNote(long handle, long bookId, long noteId, long page, long start, long end, String comment);
    private static native void nativeRemoveFixedNote(long handle, long bookId, long noteId);
    private static native long[] nativeProgress(long handle, long bookId);
    private static native void nativeSaveProgress(long handle, long bookId, long offset);
    private static native void nativeDeleteBook(long handle, long bookId);
}
