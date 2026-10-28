// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.content.Context;
import android.os.CancellationSignal;
import android.util.Log;

import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.List;

/** Worker-thread facade over the SDK library; no call is made from the UI thread. */
final class BookStore implements AutoCloseable {
    private final Thread sdkOwner=Thread.currentThread();
    void searchOwner(){if(Thread.currentThread()!=sdkOwner)throw new IllegalStateException("Search requires the existing SDK owner");}
    private final NativeLibrary library;
    private final CatalogStore catalog;
    private final android.content.SharedPreferences bookRequests;
    private boolean metadataRepairPending;
    private final OrganizationStore organization;
    OrganizationStore organization() { return organization; }
    long productOwner() { return catalog.nativeOwner(); }
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
        bookRequests = context.getSharedPreferences("sync-requests", Context.MODE_PRIVATE);
        organization = new OrganizationStore(this,context.getSharedPreferences("organization",Context.MODE_PRIVATE));
        try { repairMissingMappings(); }
        catch (RuntimeException | Error error) {
            try { library.close(); } catch (RuntimeException cleanup) { error.addSuppressed(cleanup); }
            try { catalog.close(); } catch (RuntimeException cleanup) { error.addSuppressed(cleanup); }
            throw error;
        }
    }

    boolean metadataRepairPending() { return metadataRepairPending; }

    List<CatalogStore.ShelfBook> shelfPage(String query, CatalogStore.ShelfKey anchor,
                                          boolean before, boolean inclusive, CancellationSignal cancellation) {
        return catalog.shelfPage(query, anchor, before, inclusive, cancellation);
    }

    CatalogStore.ShelfBook localShelfBook(long id) { return catalog.localShelfBook(id); }
    CatalogStore.ShelfBook localShelfTitle(String title) { return catalog.localShelfTitle(title); }

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
        return verifySource(book, expectedSha256, expectedBytes, task);
    }

    private VerifiedSource verifySource(NativeLibrary.Book book, String expectedSha256,
                                        long expectedBytes, HostTask task) throws IOException {
        long id = book.id;
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
        try { catalog.attach(source); ensureOriginalRevision(source); }
        catch (RuntimeException error) { metadataRepairPending = true; throw error; }
    }

    private void ensureOriginalRevision(VerifiedSource source) {
        if (!"0".equals(NativeCatalog.selection(catalog.nativeOwner(),"book",source.key)[0])) return;
        String[] ids=NativeCatalog.prepareCreate(bookRequests,"book-"+source.key);
        if(catalog.bootstrap(source,ids[0],new String[0]).status!=NativeCatalog.Result.OK)
            throw new IllegalStateException("Book original identity could not be prepared");
    }

    NativeCatalog.Result bootstrapBook(long id,String revision,String[] expected,HostTask task) throws IOException {
        if(revision==null||!revision.matches("[0-9a-f]{32}"))
            throw new IllegalArgumentException("Persist a stable native revision ID before submission");
        VerifiedSource source=verifySource(id,null,0,task);
        if(expected!=null&&expected.length==0){
            // Older callers explicitly bootstrap after import. Import now already commits
            // a stable original fact. Replay only that exact native command: never adopt
            // arbitrary current heads or turn a stale request into a new edit.
            String automatic=bookRequests.getString("book-"+source.key+".revision",null);
            String[] selection=NativeCatalog.selection(catalog.nativeOwner(),"book",source.key);
            if(automatic!=null&&selection.length==4&&"4".equals(selection[0])
                    &&"0".equals(selection[1])&&automatic.equals(selection[3]))
                return catalog.bootstrap(source,automatic,expected);
        }
        return catalog.bootstrap(source,revision,expected);
    }

    /** Finish every SDK source borrow before the network session can start. */
    void stageSyncOriginals(File directory,android.content.SharedPreferences pending,HostTask task)throws IOException {
        if(!directory.isDirectory()&&!directory.mkdirs())throw new IOException("同步目录创建失败");
        for(NativeLibrary.Book book:library.books()){
            task.check();VerifiedSource verified=verifySource(book,null,0,task);
            String[] selection=NativeCatalog.selection(catalog.nativeOwner(),"book",verified.key);
            if("0".equals(selection[0])){
                String request="book-"+verified.key;String[] ids=NativeCatalog.prepareCreate(pending,request);
                NativeCatalog.Result committed=catalog.bootstrap(verified,ids[0],new String[0]);
                if(committed.status!=NativeCatalog.Result.OK)throw new IOException("书籍信息尚不能同步");
            }
            File staged=new File(directory,verified.sha256+"."+verified.format);
            if(staged.exists()){
                if(staged.length()!=verified.bytes||!verified.sha256.equals(syncFileHash(staged,task)))throw new IOException("同步原件校验失败");
            }else if(library.exportOriginal(book.id,staged.getAbsolutePath(),task)!=verified.bytes)throw new IOException("同步原件导出不完整");
        }
    }
    static String syncFileHash(File file,HostTask task)throws IOException {
        MessageDigest digest;try{digest=MessageDigest.getInstance("SHA-256");}catch(NoSuchAlgorithmException error){throw new AssertionError(error);}
        byte[] bytes=new byte[65536];try(FileInputStream input=new FileInputStream(file)){int count;while((count=input.read(bytes))!=-1){task.check();digest.update(bytes,0,count);}}
        StringBuilder result=new StringBuilder();for(byte value:digest.digest())result.append(String.format(java.util.Locale.ROOT,"%02x",value&255));return result.toString();
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
                boolean missing=!catalog.hasLocalBook(book.id);
                CatalogStore.ShelfBook local=missing?null:catalog.localShelfBook(book.id);
                if(missing||(local!=null&&"0".equals(NativeCatalog.selection(catalog.nativeOwner(),"book",local.key.bookKey)[0]))) {
                    VerifiedSource source=verifySource(book, null, 0, new HostTask(() -> false));
                    if(missing)catalog.attach(source);
                    ensureOriginalRevision(source);
                }
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
