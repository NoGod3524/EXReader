package org.exreader.importentry;

/** Book formats the sideload module accepts, with the native {@code exr_format} value and byte ceiling. */
public enum ImportFormat {
    TXT(1, "txt", 32L << 20), HTML(2, "html", 32L << 20), FB2(3, "fb2", 32L << 20),
    EPUB(4, "epub", 128L << 20), DOCX(5, "docx", 32L << 20), RTF(6, "rtf", 32L << 20),
    MOBI(7, "mobi", 32L << 20), PDF(8, "pdf", 128L << 20), CBZ(9, "cbz", 128L << 20);

    /** Largest limit of any format; the ceiling used until the format is known. */
    public static final long MAX_BYTES = 128L << 20;

    private final int exrCode;
    private final String extension;
    private final long limitBytes;

    ImportFormat(int exrCode, String extension, long limitBytes) {
        this.exrCode = exrCode;
        this.extension = extension;
        this.limitBytes = limitBytes;
    }

    /** The value of the native {@code exr_format} enumerator. */
    public int exrCode() { return exrCode; }

    /** Lower-case extension used for the staged file name. */
    public String extension() { return extension; }

    /** Import byte ceiling: 32 MiB for reflow formats, 128 MiB for EPUB, CBZ and PDF. */
    public long limitBytes() { return limitBytes; }

    static ImportFormat fromExtension(String extension) {
        for (ImportFormat format : values()) if (format.extension.equals(extension)) return format;
        return null;
    }
}
