package org.exreader.s10docs;

import android.content.Context;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.os.CancellationSignal;
import android.os.ParcelFileDescriptor;
import android.provider.DocumentsContract.Document;
import android.provider.DocumentsContract.Root;
import android.provider.DocumentsProvider;

import java.io.File;
import java.io.FileNotFoundException;

/**
 * A real Storage Access Framework document provider for the S10 transfer check.
 * It exposes exactly the files the computer delivered into this app's private
 * inbox directory and nothing else: no recursion, no write access, no search.
 */
public final class S10Provider extends DocumentsProvider {
    static final String AUTHORITY = "org.exreader.s10docs.docs";
    static final String ROOT_ID = "s10-inbox";
    static final String INBOX = "inbox";
    private static final String[] COLUMNS = {
        Document.COLUMN_DOCUMENT_ID, Document.COLUMN_DISPLAY_NAME, Document.COLUMN_MIME_TYPE,
        Document.COLUMN_SIZE, Document.COLUMN_LAST_MODIFIED, Document.COLUMN_FLAGS,
    };

    static File inboxDir(Context context) {
        return new File(context.getFilesDir(), INBOX);
    }

    static File document(Context context, String documentId) throws FileNotFoundException {
        if (documentId == null || documentId.isEmpty() || documentId.startsWith(".")
                || documentId.indexOf('/') >= 0 || documentId.indexOf('\\') >= 0) {
            throw new FileNotFoundException(String.valueOf(documentId));
        }
        return new File(inboxDir(context), documentId);
    }

    @Override public boolean onCreate() { return true; }

    @Override public Cursor queryRoots(String[] projection) {
        MatrixCursor cursor = new MatrixCursor(new String[] {
            Root.COLUMN_ROOT_ID, Root.COLUMN_DOCUMENT_ID, Root.COLUMN_TITLE, Root.COLUMN_FLAGS,
            Root.COLUMN_ICON, Root.COLUMN_MIME_TYPES,
        });
        cursor.addRow(new Object[] {ROOT_ID, ROOT_ID, "EXReader S10 inbox",
            Root.FLAG_LOCAL_ONLY | Root.FLAG_SUPPORTS_IS_CHILD, android.R.drawable.ic_menu_agenda, "*/*"});
        return cursor;
    }

    @Override public Cursor queryDocument(String documentId, String[] projection) throws FileNotFoundException {
        MatrixCursor cursor = new MatrixCursor(COLUMNS);
        addRow(cursor, documentId);
        return cursor;
    }

    @Override public Cursor queryChildDocuments(String parentDocumentId, String[] projection, String sortOrder)
            throws FileNotFoundException {
        if (!ROOT_ID.equals(parentDocumentId)) throw new FileNotFoundException(parentDocumentId);
        MatrixCursor cursor = new MatrixCursor(COLUMNS);
        File[] entries = inboxDir(getContext()).listFiles();
        if (entries != null) {
            for (File entry : entries) if (entry.isFile()) addRow(cursor, entry.getName());
        }
        return cursor;
    }

    @Override public boolean isChildDocument(String parentDocumentId, String documentId) {
        return ROOT_ID.equals(parentDocumentId) && documentId != null && !documentId.isEmpty();
    }

    @Override public ParcelFileDescriptor openDocument(String documentId, String mode, CancellationSignal signal)
            throws FileNotFoundException {
        if (!"r".equals(mode)) throw new FileNotFoundException("read-only provider: " + mode);
        File file = document(getContext(), documentId);
        if (!file.isFile()) throw new FileNotFoundException(documentId);
        return ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY);
    }

    private void addRow(MatrixCursor cursor, String documentId) throws FileNotFoundException {
        if (ROOT_ID.equals(documentId)) {
            cursor.addRow(new Object[] {ROOT_ID, "inbox", Document.MIME_TYPE_DIR, null, null, 0});
            return;
        }
        File file = document(getContext(), documentId);
        if (!file.isFile()) throw new FileNotFoundException(documentId);
        cursor.addRow(new Object[] {documentId, documentId, mimeType(documentId),
            Long.valueOf(file.length()), Long.valueOf(file.lastModified()), Integer.valueOf(0)});
    }

    private static String mimeType(String name) {
        String lower = name.toLowerCase(java.util.Locale.ROOT);
        if (lower.endsWith(".epub")) return "application/epub+zip";
        if (lower.endsWith(".pdf")) return "application/pdf";
        if (lower.endsWith(".cbz")) return "application/x-cbz";
        if (lower.endsWith(".txt")) return "text/plain";
        return "application/octet-stream";
    }
}
