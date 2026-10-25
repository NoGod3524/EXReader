package org.exreader.importentry;

import java.io.File;

/**
 * A fully copied, fsynced and atomically published private file waiting for the host owner.
 * The entry keeps the file until {@link ImportEntry#release(ReadyRequest)}; it never imports or deletes it otherwise.
 */
public final class ReadyRequest {
    private final String id;
    private final File file;
    private final ImportFormat format;
    private final long size;
    private final String title;
    private final boolean alreadyStaged;

    ReadyRequest(String id, File file, ImportFormat format, long size, String title, boolean alreadyStaged) {
        this.id = id;
        this.file = file;
        this.format = format;
        this.size = size;
        this.title = title;
        this.alreadyStaged = alreadyStaged;
    }

    /** Content identity: lower-case SHA-256 of the copied bytes plus '.' and the format extension. */
    public String id() { return id; }

    /** Immutable, app-private file. Its name is derived from the content, never from the provider. */
    public File file() { return file; }

    public ImportFormat format() { return format; }

    public long size() { return size; }

    /** Sanitized display-name hint (UTF-8, at most 256 bytes, no path separators); may be empty. */
    public String title() { return title; }

    /** True when an identical request was already staged and unreleased; no second file exists. */
    public boolean alreadyStaged() { return alreadyStaged; }

    /** Same request, flagged as a re-delivery. */
    ReadyRequest asDuplicate() { return new ReadyRequest(id, file, format, size, title, true); }
}
