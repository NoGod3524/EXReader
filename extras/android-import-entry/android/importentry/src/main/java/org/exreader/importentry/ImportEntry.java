package org.exreader.importentry;

import android.content.ClipData;
import android.content.ContentResolver;
import android.content.Context;
import android.content.Intent;
import android.content.res.AssetFileDescriptor;
import android.database.Cursor;
import android.net.Uri;
import android.os.Handler;
import android.os.Looper;
import android.provider.OpenableColumns;
import android.system.ErrnoException;
import android.system.Os;
import android.system.OsConstants;
import android.system.StructPollfd;
import java.io.File;
import java.io.FileDescriptor;
import java.io.FileNotFoundException;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InterruptedIOException;
import java.io.RandomAccessFile;
import java.nio.channels.FileLock;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;

/**
 * Receives system open/share intents and Storage Access Framework results, copies each content URI into private
 * staging with a fixed 64 KiB buffer and hands a ready request to the host owner. It never parses a book, never
 * treats a provider name as a path and never runs host SDK code.
 *
 * <p>Hard limits: 64 KiB copy buffer; 32 MiB (TXT, HTML, FB2, DOCX, RTF, MOBI) or 128 MiB (EPUB, CBZ, PDF) per
 * file; 64 URIs per intent; 64 unfinished tickets; 32 unreleased ready requests; one copy at a time; a read that
 * makes no progress for {@code stallTimeoutMillis} fails with IO.
 *
 * <p>Threading: every method may be called from any thread. create/release do private filesystem I/O and should
 * run off the UI thread; submit/cancel/close only queue or change state. Copying runs on one private
 * thread. Owner callbacks run on the host executor. One entry per staging directory (enforced in-process and by
 * a file lock across processes).
 *
 * <p>Lifecycle: tickets are not tied to an Activity. Rotation or finishing the UI does not stop a copy; call
 * {@link #close()} to cancel everything. After the process dies, partial temporaries are deleted by the next
 * {@link #create} and published files are listed by {@link #pendingReady()}.
 *
 * <p>Grant lifetime: a read grant delivered with an Intent covers the receiving task; call
 * {@link #submit(Intent)} before finishing the Activity that received it. A grant revoked before the stream
 * opens ends in PERMISSION. A revocation after open does not close the descriptor (Android semantics) and the
 * copy completes; provider errors mid-stream end in IO.
 */
public final class ImportEntry {
    public static final int COPY_BUFFER_BYTES = 64 * 1024;
    public static final int MAX_URIS_PER_INTENT = 64;
    public static final int MAX_TICKETS = 64;
    public static final int MAX_READY = 32;
    public static final long DEFAULT_STALL_TIMEOUT_MILLIS = 30_000L;
    private static final int POLL_SLICE_MILLIS = 250;
    private static final Set<String> OPEN = new HashSet<>();

    private final ContentResolver resolver;
    private final File readyDir, tmpDir;
    private final Executor ownerExecutor;
    private final ImportOwner owner;
    private final long stallTimeoutMillis;
    private final ExecutorService worker = Executors.newSingleThreadExecutor(r -> {
        Thread t = new Thread(r, "exr-import-copy");
        t.setDaemon(true);
        return t;
    });
    private final Object lock = new Object();
    private final Map<ImportTicket, Boolean> tickets = new LinkedHashMap<>();
    private final Map<String, ReadyRequest> ready = new LinkedHashMap<>();
    private final Map<ReadyRequest, Boolean> leases = new LinkedHashMap<>();
    private final String registryKey;
    private final RandomAccessFile lockFile;
    private final FileLock fileLock;
    private boolean closed;
    private int sequence;
    private volatile int maxChunk;

    /**
     * Opens private staging below {@code stagingParent} and removes every leftover temporary from earlier runs.
     *
     * @param ownerExecutor where callbacks run; null selects the main looper
     * @throws IOException staging cannot be created, or another live entry (this or another process) uses it
     */
    public static ImportEntry create(Context context, File stagingParent, Executor ownerExecutor,
            ImportOwner owner) throws IOException {
        return create(context, stagingParent, ownerExecutor, owner, DEFAULT_STALL_TIMEOUT_MILLIS);
    }

    public static ImportEntry create(Context context, File stagingParent, Executor ownerExecutor,
            ImportOwner owner, long stallTimeoutMillis) throws IOException {
        if (context == null || stagingParent == null || owner == null || stallTimeoutMillis < 1)
            throw new IllegalArgumentException("context, stagingParent, owner and a positive timeout are required");
        Executor executor = ownerExecutor;
        if (executor == null) {
            Handler handler = new Handler(Looper.getMainLooper());
            executor = handler::post;
        }
        return new ImportEntry(context.getApplicationContext().getContentResolver(),
                new File(stagingParent, "exr-import"), executor, owner, stallTimeoutMillis);
    }

    private ImportEntry(ContentResolver resolver, File root, Executor executor, ImportOwner owner,
            long stallTimeoutMillis) throws IOException {
        this.resolver = resolver;
        this.ownerExecutor = executor;
        this.owner = owner;
        this.stallTimeoutMillis = stallTimeoutMillis;
        readyDir = new File(root, "ready");
        tmpDir = new File(root, "tmp");
        if (!(readyDir.isDirectory() || readyDir.mkdirs()) || !(tmpDir.isDirectory() || tmpDir.mkdirs()))
            throw new IOException("Cannot create private staging");
        registryKey = root.getCanonicalPath();
        synchronized (OPEN) {
            if (!OPEN.add(registryKey)) throw new IOException("Staging is already in use by an open entry");
        }
        RandomAccessFile file = null;
        FileLock acquired = null;
        try {
            file = new RandomAccessFile(new File(root, "lock"), "rw");
            acquired = file.getChannel().tryLock();
            if (acquired == null) throw new IOException("Staging is locked by another process");
            cleanStaging();
        } catch (IOException | RuntimeException e) {
            if (file != null) try { file.close(); } catch (IOException ignored) { }
            synchronized (OPEN) { OPEN.remove(registryKey); }
            worker.shutdownNow();
            throw e instanceof IOException ? (IOException) e : new IOException(e);
        }
        lockFile = file;
        fileLock = acquired;
    }

    /** Intent that opens the system document picker for supported book types. */
    public static Intent pickerIntent(boolean allowMultiple) {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("*/*");
        intent.putExtra(Intent.EXTRA_MIME_TYPES, new String[] {
            "application/epub+zip", "application/pdf", "application/x-cbz", "application/vnd.comicbook+zip",
            "text/plain", "text/html", "application/xhtml+xml", "application/x-fictionbook+xml",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/rtf",
            "text/rtf", "application/x-mobipocket-ebook", "application/octet-stream" });
        intent.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, allowMultiple);
        return intent;
    }

    /**
     * Queues every content URI in an ACTION_VIEW, ACTION_SEND, ACTION_SEND_MULTIPLE or document-picker result.
     * Returns one ticket per URI (at most {@value #MAX_URIS_PER_INTENT}; the rest end with BACKLOG). Returns an
     * empty list for an unrelated intent. Non-content schemes (for example file://) end with ARGUMENT.
     */
    @SuppressWarnings({"deprecation", "unchecked"})
    public List<ImportTicket> submit(Intent intent) {
        List<ImportTicket> out = new ArrayList<>();
        if (intent == null) return out;
        List<Uri> uris = new ArrayList<>();
        String action = intent.getAction();
        if (Intent.ACTION_SEND.equals(action)) {
            Object stream = intent.getParcelableExtra(Intent.EXTRA_STREAM);
            if (stream instanceof Uri) uris.add((Uri) stream);
        } else if (Intent.ACTION_SEND_MULTIPLE.equals(action)) {
            List<Object> streams = (List<Object>) (List<?>) intent.getParcelableArrayListExtra(Intent.EXTRA_STREAM);
            if (streams != null) for (Object s : streams) if (s instanceof Uri) uris.add((Uri) s);
        }
        if (intent.getData() != null) uris.add(intent.getData());
        ClipData clip = intent.getClipData();
        if (clip != null) for (int i = 0; i < clip.getItemCount(); i++)
            if (clip.getItemAt(i).getUri() != null) uris.add(clip.getItemAt(i).getUri());
        Set<Uri> seen = new HashSet<>();
        for (Uri uri : uris) {
            if (!seen.add(uri)) continue;
            out.add(out.size() >= MAX_URIS_PER_INTENT
                    ? rejected(uri, ImportError.Code.BACKLOG, "More than " + MAX_URIS_PER_INTENT + " URIs in one intent")
                    : submit(uri, intent.getType()));
        }
        return out;
    }

    /** Queues one URI. {@code mimeHint} is only a hint; content is sniffed and must agree. */
    public ImportTicket submit(Uri uri, String mimeHint) {
        if (uri == null) throw new IllegalArgumentException("uri");
        if (!ContentResolver.SCHEME_CONTENT.equals(uri.getScheme()))
            return rejected(uri, ImportError.Code.ARGUMENT, "Only content URIs are imported");
        ImportTicket ticket = new ImportTicket(uri);
        ImportError.Code refusal = null;
        synchronized (lock) {
            if (closed) refusal = ImportError.Code.CANCELLED;
            else if (tickets.size() >= MAX_TICKETS) refusal = ImportError.Code.BACKLOG;
            else {
                tickets.put(ticket, Boolean.TRUE);
                try {
                    worker.execute(() -> run(ticket, mimeHint));
                    return ticket;
                } catch (RejectedExecutionException e) {
                    tickets.remove(ticket);
                    refusal = ImportError.Code.CANCELLED;
                }
            }
        }
        return rejected(uri, refusal, refusal == ImportError.Code.BACKLOG ? "Too many unfinished tickets" : "Entry is closed");
    }

    /** Unreleased request leases, oldest first. Duplicate content has distinct leases sharing one file. */
    public List<ReadyRequest> pendingReady() {
        synchronized (lock) { return new ArrayList<>(leases.keySet()); }
    }

    /**
     * Releases this exact entry-owned lease; deletes its file only after the last lease. Foreign, stale and
     * repeated releases are ignored. Never call it
     * before the host SDK call that reads {@code request.file()} has returned.
     */
    public void release(ReadyRequest request) {
        if (request == null) return;
        synchronized (lock) {
            if (leases.remove(request) == null) return;
            for (ReadyRequest remaining : leases.keySet()) if (remaining.id().equals(request.id())) return;
            ready.remove(request.id());
            File owned = new File(readyDir, request.id());
            deleteQuietly(sidecar(owned));
            deleteQuietly(owned);
        }
    }

    /** Cancels every ticket (each still gets one CANCELLED callback unless already committed). Idempotent. */
    public void close() {
        List<ImportTicket> open;
        synchronized (lock) {
            if (closed) return;
            closed = true;
            open = new ArrayList<>(tickets.keySet());
        }
        for (ImportTicket t : open) t.cancel();
        worker.execute(() -> {
            synchronized (lock) {
                // Published files survive close for recovery. Old request objects
                // cannot delete files after a new entry takes ownership.
                leases.clear();
                ready.clear();
                try { fileLock.release(); } catch (IOException ignored) { }
                try { lockFile.close(); } catch (IOException ignored) { }
                synchronized (OPEN) { OPEN.remove(registryKey); }
            }
        });
        worker.shutdown();
    }

    /** Largest read the copier has issued so far; never exceeds {@link #COPY_BUFFER_BYTES}. */
    public int maxChunkBytes() { return maxChunk; }

    // ---- copy thread -------------------------------------------------------------------------------------

    private void run(ImportTicket ticket, String mimeHint) {
        if (!ticket.begin() || ticket.cancelRequested()) {
            finish(ticket, null, new ImportError(ImportError.Code.CANCELLED, "Cancelled before start"));
            return;
        }
        ReadyRequest copied;
        try {
            copied = copy(ticket, mimeHint);
        } catch (Failure f) {
            finish(ticket, null, new ImportError(f.code, f.getMessage()));
            return;
        } catch (RuntimeException e) {
            finish(ticket, null, new ImportError(ImportError.Code.IO, String.valueOf(e)));
            return;
        }
        // Owner/executor failures are not copy failures and cannot retract a
        // committed ticket or manufacture a second terminal notification.
        finish(ticket, copied, null);
    }

    private static final class Failure extends Exception {
        final ImportError.Code code;

        Failure(ImportError.Code code, String message) {
            super(message);
            this.code = code;
        }
    }

    private ReadyRequest copy(ImportTicket ticket, String mimeHint) throws Failure {
        Uri uri = ticket.uri();
        String displayName = null;
        long declared = -1;
        try (Cursor c = resolver.query(uri, new String[] {OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE},
                null, null, null)) {
            if (c != null && c.moveToFirst()) {
                int n = c.getColumnIndex(OpenableColumns.DISPLAY_NAME), s = c.getColumnIndex(OpenableColumns.SIZE);
                if (n >= 0 && !c.isNull(n)) displayName = c.getString(n);
                if (s >= 0 && !c.isNull(s)) declared = c.getLong(s);
            }
        } catch (SecurityException e) {
            throw new Failure(ImportError.Code.PERMISSION, "Read grant refused");
        } catch (RuntimeException ignored) {
            // The query is advisory; the stream decides.
        }
        String providerType = null;
        try { providerType = resolver.getType(uri); } catch (RuntimeException ignored) { }
        ImportFormat hint = hintFor(providerType, mimeHint, displayName);
        checkDeclared(declared, hint);
        if (ticket.cancelRequested()) throw new Failure(ImportError.Code.CANCELLED, "Cancelled");

        String title = titleFrom(displayName);
        File part = new File(tmpDir, (++sequence) + ".part");
        boolean published = false;
        MessageDigest digest;
        ImportFormat format = null;
        long total = 0;
        AssetFileDescriptor afd = null;
        try {
            afd = open(uri);
            long length = afd.getLength();
            if (length >= 0) declared = length;
            checkDeclared(declared, hint);
            FileDescriptor fd = afd.getFileDescriptor();
            long start = afd.getStartOffset();
            if (start > 0) try { Os.lseek(fd, start, OsConstants.SEEK_SET); } catch (ErrnoException e) {
                throw new Failure(ImportError.Code.IO, "Provider descriptor has an unsupported offset");
            }
            digest = MessageDigest.getInstance("SHA-256");
            byte[] buffer = new byte[COPY_BUFFER_BYTES];
            long idleSince = System.nanoTime();
            try (FileOutputStream out = new FileOutputStream(part)) {
                while (true) {
                    if (ticket.cancelRequested()) throw new Failure(ImportError.Code.CANCELLED, "Cancelled");
                    int want = COPY_BUFFER_BYTES;
                    // Only the descriptor's actual asset range bounds reads;
                    // advisory query SIZE must never silently truncate a pipe.
                    if (length >= 0) want = (int) Math.min(want, length - total);
                    if (want <= 0) break;
                    if (!waitReadable(fd)) {
                        if ((System.nanoTime() - idleSince) / 1_000_000L > stallTimeoutMillis)
                            throw new Failure(ImportError.Code.IO, "Provider stalled");
                        continue;
                    }
                    int got = readSome(fd, buffer, 0, want);
                    if (got == 0) break;
                    idleSince = System.nanoTime();
                    if (total == 0) {
                        // A short first read must not decide the sniff: refill toward the declared/buffer bound.
                        got = fillFirst(fd, buffer, got, want, ticket);
                        format = sniff(buffer, got, hint);
                    }
                    if (got > maxChunk) maxChunk = got;
                    total += got;
                    if (total > format.limitBytes())
                        throw new Failure(ImportError.Code.LIMIT, format + " exceeds " + format.limitBytes() + " bytes");
                    digest.update(buffer, 0, got);
                    out.write(buffer, 0, got);
                }
                if (total == 0) throw new Failure(ImportError.Code.EMPTY, "Provider returned no bytes");
                if (declared >= 0 && total != declared)
                    throw new Failure(ImportError.Code.IO, "Stream differs from its declared length");
                out.getFD().sync();
            }
            // Closing a reliable pipe reports a writer-side error; that must fail the copy before any publish.
            try (AssetFileDescriptor finished = afd) {
                afd = null;
                finished.getParcelFileDescriptor().checkError();
            } catch (IOException e) {
                throw new Failure(ImportError.Code.IO, "Provider reported a stream error");
            }
            String id = hex(digest.digest()) + "." + format.extension();
            File target = new File(readyDir, id);
            ReadyRequest request;
            synchronized (lock) {
                ReadyRequest existing = ready.get(id);
                if (leases.size() >= MAX_READY)
                    throw new Failure(ImportError.Code.BACKLOG, "Too many unreleased ready requests");
                if (!ticket.commit()) throw new Failure(ImportError.Code.CANCELLED, "Cancelled before publish");
                if (existing != null && target.length() == total) {
                    request = existing.asDuplicate();
                } else {
                    writeSidecar(target, title);
                    Files.move(part.toPath(), target.toPath(), StandardCopyOption.ATOMIC_MOVE,
                            StandardCopyOption.REPLACE_EXISTING);
                    request = new ReadyRequest(id, target, format, total, title, false);
                    ready.put(id, request);
                    published = true;
                }
                leases.put(request, Boolean.TRUE);
            }
            return request;
        } catch (FileNotFoundException e) {
            throw new Failure(ImportError.Code.NOT_FOUND, "Cannot open provider stream");
        } catch (SecurityException e) {
            throw new Failure(ImportError.Code.PERMISSION, "Read grant refused");
        } catch (IOException e) {
            throw new Failure(ImportError.Code.STAGING, "Private staging failed");
        } catch (NoSuchAlgorithmException e) {
            throw new Failure(ImportError.Code.STAGING, "SHA-256 unavailable");
        } finally {
            // Published files were moved away; everything else (failure, cancel, duplicate) leaves no temporary.
            if (!published) deleteQuietly(part);
            if (afd != null) try { afd.close(); } catch (IOException ignored) { }
        }
    }

    private static void checkDeclared(long declared, ImportFormat hint) throws Failure {
        if (declared > ImportFormat.MAX_BYTES || (hint != null && declared > hint.limitBytes()))
            throw new Failure(ImportError.Code.LIMIT, "Declared size exceeds the limit");
    }

    private AssetFileDescriptor open(Uri uri) throws FileNotFoundException, Failure {
        AssetFileDescriptor afd = resolver.openAssetFileDescriptor(uri, "r");
        if (afd == null) throw new Failure(ImportError.Code.NOT_FOUND, "Provider returned no stream");
        return afd;
    }

    private static int readSome(FileDescriptor fd, byte[] buffer, int offset, int count) throws Failure {
        try {
            int got = Os.read(fd, buffer, offset, count);
            return Math.max(got, 0);
        } catch (ErrnoException | InterruptedIOException e) {
            throw new Failure(ImportError.Code.IO, "Provider read failed");
        }
    }

    private int fillFirst(FileDescriptor fd, byte[] buffer, int have, int max, ImportTicket ticket) throws Failure {
        long idle = System.nanoTime();
        while (have < max) {
            if (ticket.cancelRequested()) throw new Failure(ImportError.Code.CANCELLED, "Cancelled");
            if (!waitReadable(fd)) {
                if ((System.nanoTime() - idle) / 1_000_000L > stallTimeoutMillis)
                    throw new Failure(ImportError.Code.IO, "Provider stalled");
                continue;
            }
            int got = readSome(fd, buffer, have, max - have);
            if (got == 0) break;
            have += got;
            idle = System.nanoTime();
        }
        return have;
    }

    /** Waits at most one slice for readable data or hang-up; regular files are always readable. */
    private static boolean waitReadable(FileDescriptor fd) throws Failure {
        StructPollfd p = new StructPollfd();
        p.fd = fd;
        p.events = (short) OsConstants.POLLIN;
        try {
            return Os.poll(new StructPollfd[] {p}, POLL_SLICE_MILLIS) > 0;
        } catch (ErrnoException e) {
            throw new Failure(ImportError.Code.IO, "Provider poll failed");
        }
    }

    // ---- classification (no parsing: magic bytes of the first chunk plus the hint) --------------------------

    private static ImportFormat sniff(byte[] b, int n, ImportFormat hint) throws Failure {
        if (indexOf(b, Math.min(n, 1024), "%PDF-") >= 0) return require(hint, ImportFormat.PDF);
        if (n >= 4 && b[0] == 'P' && b[1] == 'K' && b[2] == 3 && b[3] == 4) {
            if (indexOf(b, n, "mimetypeapplication/epub+zip") == 30) return require(hint, ImportFormat.EPUB);
            if (hint == ImportFormat.EPUB || hint == ImportFormat.CBZ || hint == ImportFormat.DOCX) return hint;
            throw new Failure(ImportError.Code.UNSUPPORTED_FORMAT, "ZIP container without a book type");
        }
        if (n >= 5 && b[0] == '{' && b[1] == '\\' && b[2] == 'r' && b[3] == 't' && b[4] == 'f')
            return require(hint, ImportFormat.RTF);
        if (n >= 68 && indexOf(b, 68, "BOOKMOBI") == 60) return require(hint, ImportFormat.MOBI);
        if (hint == ImportFormat.PDF || hint == ImportFormat.EPUB || hint == ImportFormat.CBZ
                || hint == ImportFormat.DOCX || hint == ImportFormat.RTF || hint == ImportFormat.MOBI)
            throw new Failure(ImportError.Code.UNSUPPORTED_FORMAT, "Content does not match " + hint);
        boolean utf16 = n >= 2 && ((b[0] & 0xff) == 0xff && (b[1] & 0xff) == 0xfe
                || (b[0] & 0xff) == 0xfe && (b[1] & 0xff) == 0xff);
        if (!utf16) for (int i = 0; i < n; i++)
            if (b[i] == 0) throw new Failure(ImportError.Code.UNSUPPORTED_FORMAT, "Binary content");
        if (hint == ImportFormat.HTML || hint == ImportFormat.FB2) return hint;
        if (indexOf(b, n, "<FictionBook") >= 0) return ImportFormat.FB2;
        return ImportFormat.TXT;
    }

    private static ImportFormat require(ImportFormat hint, ImportFormat actual) throws Failure {
        if (hint != null && hint != actual)
            throw new Failure(ImportError.Code.UNSUPPORTED_FORMAT, "Content is " + actual + ", not " + hint);
        return actual;
    }

    private static int indexOf(byte[] b, int n, String needle) {
        byte[] k = needle.getBytes(StandardCharsets.ISO_8859_1);
        for (int i = 0; i + k.length <= n; i++) {
            int j = 0;
            while (j < k.length && b[i + j] == k[j]) j++;
            if (j == k.length) return i;
        }
        return -1;
    }

    private static ImportFormat hintFor(String providerType, String intentType, String displayName) {
        ImportFormat f = fromMime(providerType);
        if (f == null) f = fromMime(intentType);
        if (f == null && displayName != null) {
            int dot = displayName.lastIndexOf('.');
            if (dot >= 0) {
                String ext = displayName.substring(dot + 1).toLowerCase(Locale.ROOT);
                if (ext.equals("htm") || ext.equals("xhtml")) ext = "html";
                f = ImportFormat.fromExtension(ext);
            }
        }
        return f;
    }

    private static ImportFormat fromMime(String mime) {
        if (mime == null) return null;
        switch (mime.toLowerCase(Locale.ROOT)) {
            case "application/epub+zip": return ImportFormat.EPUB;
            case "application/pdf": return ImportFormat.PDF;
            case "application/x-cbz": case "application/vnd.comicbook+zip": return ImportFormat.CBZ;
            case "text/plain": return ImportFormat.TXT;
            case "text/html": case "application/xhtml+xml": return ImportFormat.HTML;
            case "application/x-fictionbook+xml": case "application/x-fb2": return ImportFormat.FB2;
            case "application/vnd.openxmlformats-officedocument.wordprocessingml.document": return ImportFormat.DOCX;
            case "application/rtf": case "text/rtf": return ImportFormat.RTF;
            case "application/x-mobipocket-ebook": return ImportFormat.MOBI;
            default: return null;
        }
    }

    /** Display name without extension, control characters or separators, at most 256 UTF-8 bytes. */
    static String titleFrom(String displayName) {
        if (displayName == null) return "";
        int dot = displayName.lastIndexOf('.');
        String base = dot > 0 ? displayName.substring(0, dot) : displayName;
        StringBuilder sb = new StringBuilder();
        int bytes = 0;
        for (int i = 0; i < base.length(); ) {
            int cp = base.codePointAt(i);
            i += Character.charCount(cp);
            if (cp < 0x20 || cp == 0x7f || cp == '/' || cp == '\\' || cp == 0xfffd) continue;
            int len = cp < 0x80 ? 1 : cp < 0x800 ? 2 : cp < 0x10000 ? 3 : 4;
            if (bytes + len > 256) break;
            bytes += len;
            sb.appendCodePoint(cp);
        }
        return sb.toString().trim();
    }

    // ---- staging bookkeeping -------------------------------------------------------------------------------

    private void cleanStaging() {
        File[] tmps = tmpDir.listFiles();
        if (tmps != null) for (File f : tmps) deleteQuietly(f);
        File[] files = readyDir.listFiles();
        if (files == null) return;
        Arrays.sort(files, (a, b) -> Long.compare(a.lastModified(), b.lastModified()));
        for (File f : files) {
            String name = f.getName();
            if (name.endsWith(".title")) continue;
            ImportFormat format = formatOfId(name);
            if (format == null || !f.isFile() || f.length() == 0 || ready.size() >= MAX_READY) {
                deleteQuietly(f);
                continue;
            }
            ReadyRequest recovered = new ReadyRequest(name, f, format, f.length(), readSidecar(f), false);
            ready.put(name, recovered);
            leases.put(recovered, Boolean.TRUE);
        }
        File[] again = readyDir.listFiles();
        if (again != null) for (File f : again) {
            String name = f.getName();
            if (name.endsWith(".title") && !ready.containsKey(name.substring(0, name.length() - 6))) deleteQuietly(f);
        }
    }

    private static ImportFormat formatOfId(String name) {
        if (name.length() < 66 || name.charAt(64) != '.' || !name.substring(0, 64).matches("[0-9a-f]{64}")) return null;
        return ImportFormat.fromExtension(name.substring(65));
    }

    private static File sidecar(File data) { return new File(data.getParentFile(), data.getName() + ".title"); }

    private static void writeSidecar(File data, String title) throws IOException {
        File tmp = new File(data.getParentFile(), data.getName() + ".title.tmp");
        try (FileOutputStream out = new FileOutputStream(tmp)) {
            out.write(title.getBytes(StandardCharsets.UTF_8));
            out.getFD().sync();
        }
        Files.move(tmp.toPath(), sidecar(data).toPath(), StandardCopyOption.ATOMIC_MOVE,
                StandardCopyOption.REPLACE_EXISTING);
    }

    private static String readSidecar(File data) {
        File file = sidecar(data);
        if (!file.isFile() || file.length() > 1024) return "";
        try {
            return new String(Files.readAllBytes(file.toPath()), StandardCharsets.UTF_8);
        } catch (IOException e) {
            return "";
        }
    }

    private static void deleteQuietly(File f) { if (f != null && f.exists() && !f.delete()) f.deleteOnExit(); }

    private static String hex(byte[] bytes) {
        char[] digits = "0123456789abcdef".toCharArray();
        char[] out = new char[bytes.length * 2];
        for (int i = 0; i < bytes.length; i++) {
            out[2 * i] = digits[(bytes[i] >> 4) & 15];
            out[2 * i + 1] = digits[bytes[i] & 15];
        }
        return new String(out);
    }

    // ---- delivery ------------------------------------------------------------------------------------------

    private ImportTicket rejected(Uri uri, ImportError.Code code, String message) {
        ImportTicket ticket = new ImportTicket(uri);
        if (code == ImportError.Code.CANCELLED) ticket.cancelled(); else ticket.fail();
        deliver(ticket, null, new ImportError(code, message));
        return ticket;
    }

    private void finish(ImportTicket ticket, ReadyRequest request, ImportError error) {
        if (request == null) {
            if (error.code() == ImportError.Code.CANCELLED) ticket.cancelled(); else ticket.fail();
        }
        synchronized (lock) { tickets.remove(ticket); }
        deliver(ticket, request, error);
    }

    private void deliver(ImportTicket ticket, ReadyRequest request, ImportError error) {
        try {
            ownerExecutor.execute(() -> {
                try {
                    if (request != null) owner.onReady(ticket, request); else owner.onFailed(ticket, error);
                } catch (RuntimeException ignored) {
                    // Notification already happened. Keep a ready lease available
                    // for explicit cleanup/recovery; never call the owner twice.
                }
            });
        } catch (RejectedExecutionException ignored) {
            // The host closed its executor; nothing is left to notify. A ready file stays listed for pendingReady().
        }
    }
}
