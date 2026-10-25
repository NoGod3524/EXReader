package org.exreader.hostimportsource;

import android.content.res.AssetManager;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.os.CancellationSignal;
import android.os.ParcelFileDescriptor;
import android.provider.DocumentsContract.Document;
import android.provider.DocumentsContract.Root;
import android.provider.DocumentsProvider;
import java.io.File;
import java.io.FileNotFoundException;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

/**
 * A real DocumentsProvider guarded by MANAGE_DOCUMENTS: other apps read it only through URI grants. Its documents
 * model the awkward cases: non-seekable pipes with tiny writes, unknown or lying lengths, stalls, mid-stream
 * errors, oversized streams and hostile display names.
 */
public final class SourceProvider extends DocumentsProvider {
    static final String AUTHORITY = "org.exreader.hostimportsource.docs";
    static final long MIB = 1024L * 1024L;
    /** id, display name, mime type, declared size (-1 = absent). */
    static final String[][] DOCS = {
        {"epub", "Fixture Book.epub", "application/epub+zip", "asset"},
        {"pdf", "Fixture.pdf", "application/pdf", "asset"},
        {"pdf-33m", "StagedNotReadable.pdf", "application/pdf", "-1"},
        {"txt-seekable", "Seekable.txt", "text/plain", "70000"},
        {"txt-cancel", "Cancel.txt", "text/plain", "7000"},
        {"txt-rotating", "Rotating.txt", "text/plain", "11000"},
        {"txt-ready", "Ready.txt", "text/plain", "8000"},
        {"txt-stable", "StablePartial.txt", "text/plain", "12000"},
        {"txt-published", "Published.txt", "text/plain", "9000"},
        {"txt-short", "Short Reads.txt", "text/plain", "-1"},
        {"txt-short-b", "Copy of Short.txt", "text/plain", "-1"},
        {"evil-name", "../../../evil/..\\name.txt", "text/plain", "-1"},
        {"txt-slow", "Slow.txt", "text/plain", "-1"},
        {"txt-gated", "Gated.txt", "text/plain", "5000"},
        {"txt-error", "Error.txt", "text/plain", "-1"},
        {"txt-truncated", "Truncated.txt", "text/plain", "300000"},
        {"txt-overlong", "Underreported.txt", "text/plain", "1000"},
        {"txt-32m", "Exact32.txt", "text/plain", "-1"},
        {"txt-33m", "Over32.txt", "text/plain", "-1"},
        {"epub-129m", "Over128.epub", "application/epub+zip", "-1"},
        {"epub-declared-big", "Declared.epub", "application/epub+zip", String.valueOf(128 * MIB + 1)},
        {"zip-unknown", "blob.bin", "application/octet-stream", "-1"},
        {"pdf-lie", "lie.pdf", "application/pdf", "-1"},
        {"empty", "Empty.txt", "text/plain", "-1"},
    };
    static final Object GATE = new Object();
    static boolean gateOpen;

    static String[] find(String id) {
        for (String[] d : DOCS) if (d[0].equals(id)) return d;
        return null;
    }

    @Override public boolean onCreate() { return true; }

    @Override public Cursor queryRoots(String[] projection) {
        MatrixCursor c = new MatrixCursor(new String[] {Root.COLUMN_ROOT_ID, Root.COLUMN_FLAGS, Root.COLUMN_TITLE,
            Root.COLUMN_DOCUMENT_ID, Root.COLUMN_ICON});
        c.addRow(new Object[] {"probe", 0, "HostImport", "root", android.R.drawable.ic_menu_agenda});
        return c;
    }

    @Override public Cursor queryDocument(String documentId, String[] projection) throws FileNotFoundException {
        MatrixCursor c = new MatrixCursor(new String[] {Document.COLUMN_DOCUMENT_ID, Document.COLUMN_DISPLAY_NAME,
            Document.COLUMN_SIZE, Document.COLUMN_MIME_TYPE, Document.COLUMN_FLAGS});
        if ("root".equals(documentId)) {
            c.addRow(new Object[] {"root", "root", null, Document.MIME_TYPE_DIR, 0});
            return c;
        }
        String[] d = find(documentId);
        if (d == null) throw new FileNotFoundException(documentId);
        if (documentId.equals("txt-gated")) awaitGate();
        c.addRow(new Object[] {d[0], d[1], declaredSize(d), d[2], 0});
        return c;
    }

    @Override public Cursor queryChildDocuments(String parentDocumentId, String[] projection, String sortOrder)
            throws FileNotFoundException {
        MatrixCursor c = new MatrixCursor(new String[] {Document.COLUMN_DOCUMENT_ID, Document.COLUMN_DISPLAY_NAME,
            Document.COLUMN_SIZE, Document.COLUMN_MIME_TYPE, Document.COLUMN_FLAGS});
        for (String[] d : DOCS) c.addRow(new Object[] {d[0], d[1], declaredSize(d), d[2], 0});
        return c;
    }

    private Long declaredSize(String[] d) {
        if (d[3].equals("asset")) return assetLength(d[0].equals("epub") ? "cover-import.epub" : "pdf-public.pdf");
        long n = Long.parseLong(d[3]);
        return n < 0 ? null : Long.valueOf(n);
    }

    private long assetLength(String name) {
        try (InputStream in = getContext().getAssets().open(name, AssetManager.ACCESS_STREAMING)) {
            long n = 0;
            byte[] b = new byte[8192];
            for (int r; (r = in.read(b)) > 0; ) n += r;
            return n;
        } catch (IOException e) {
            return -1;
        }
    }

    static void awaitGate() {
        synchronized (GATE) {
            long end = System.currentTimeMillis() + 120_000;
            while (!gateOpen && System.currentTimeMillis() < end) {
                try { GATE.wait(500); } catch (InterruptedException e) { return; }
            }
        }
    }

    private void noteOpen(String id) {
        try (FileOutputStream out = new FileOutputStream(new File(getContext().getFilesDir(), "opens.log"), true)) {
            out.write(("open " + id + "\n").getBytes());
        } catch (IOException ignored) { }
    }

    @Override public ParcelFileDescriptor openDocument(String documentId, String mode, CancellationSignal signal)
            throws FileNotFoundException {
        String[] d = find(documentId);
        if (d == null) throw new FileNotFoundException(documentId);
        noteOpen(documentId);
        switch (documentId) {
            case "epub": return assetFile("cover-import.epub");
            case "pdf": return assetFile("pdf-public.pdf");
            case "txt-seekable": return generatedFile(documentId, 70_000);
            case "txt-cancel": return generatedFile(documentId, 7000);
            case "txt-rotating": return generatedFile(documentId, 11000);
            case "txt-ready": return generatedFile(documentId, 8000);
            case "txt-stable": return generatedFile(documentId, 12000);
            case "txt-published": return generatedFile(documentId, 9000);
            case "epub-declared-big": throw new FileNotFoundException("a declared-oversize document must never be opened");
            default: return pipe(documentId);
        }
    }

    private ParcelFileDescriptor assetFile(String name) throws FileNotFoundException {
        File file = new File(getContext().getCacheDir(), name);
        if (!file.exists()) try (InputStream in = getContext().getAssets().open(name); OutputStream out = new FileOutputStream(file)) {
            byte[] b = new byte[8192];
            for (int r; (r = in.read(b)) > 0; ) out.write(b, 0, r);
        } catch (IOException e) {
            throw new FileNotFoundException(name);
        }
        return ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY);
    }

    private ParcelFileDescriptor generatedFile(String id, int length) throws FileNotFoundException {
        File file = new File(getContext().getCacheDir(), id + ".txt");
        try (OutputStream out = new FileOutputStream(file)) {
            Streams.text(out, length, 65536, false);
        } catch (IOException e) {
            throw new FileNotFoundException(id);
        }
        return ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY);
    }

    private ParcelFileDescriptor pipe(String id) throws FileNotFoundException {
        final ParcelFileDescriptor[] fds;
        try {
            fds = ParcelFileDescriptor.createReliablePipe();
        } catch (IOException e) {
            throw new FileNotFoundException(id);
        }
        new Thread(() -> {
            try (OutputStream out = new ParcelFileDescriptor.AutoCloseOutputStream(fds[1])) {
                switch (id) {
                    case "pdf-33m":
                        out.write("%PDF-1.7\n".getBytes());
                        byte[] padding=new byte[65536];long remaining=33*MIB-9;
                        while(remaining>0){int count=(int)Math.min(remaining,padding.length);out.write(padding,0,count);remaining-=count;}
                        break;
                    case "txt-short": case "txt-short-b": Streams.text(out, 300_000, 37, true); break;
                    case "evil-name": Streams.text(out, 1000, 1000, false); break;
                    case "txt-slow":
                        Streams.text(out, (int) MIB, 65536, false);
                        awaitGate();
                        Streams.text(out, (int) MIB, 65536, false, MIB);
                        break;
                    case "txt-gated": Streams.text(out, 5000, 5000, false); break;
                    case "txt-error":
                        Streams.text(out, 200_000, 65536, false);
                        out.flush();
                        fds[1].closeWithError("provider failed mid-stream");
                        break;
                    case "txt-truncated": Streams.text(out, 100_000, 65536, false); break;
                    case "txt-overlong": Streams.text(out, 2000, 65536, false); break;
                    case "txt-32m": Streams.text(out, (int) (32 * MIB), 65536, false); break;
                    case "txt-33m": Streams.text(out, (int) (32 * MIB) + 1, 65536, false); break;
                    case "epub-129m": Streams.epubLike(out, 128 * MIB + 1); break;
                    case "zip-unknown": Streams.raw(out, new byte[] {'P', 'K', 3, 4}, 1000); break;
                    case "pdf-lie": Streams.text(out, 4000, 4000, false); break;
                    case "empty": break;
                    default: break;
                }
            } catch (IOException ignored) {
                // The importer closed its end (cancel, limit or kill): nothing more to write.
            }
        }, "source-writer-" + id).start();
        return fds[0];
    }
}
