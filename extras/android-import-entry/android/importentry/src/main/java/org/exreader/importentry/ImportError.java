package org.exreader.importentry;

/** Terminal failure of one {@link ImportTicket}. */
public final class ImportError {
    public enum Code {
        /** The URI or intent cannot be imported (not a content URI, no stream). */
        ARGUMENT,
        /** The provider refused the read grant, or it was revoked before the stream opened. */
        PERMISSION,
        /** The provider has no such document. */
        NOT_FOUND,
        /** The stream failed, stalled past the timeout, or ended before its declared length. */
        IO,
        /** Zero bytes. */
        EMPTY,
        /** Declared or actual size exceeds the format ceiling. */
        LIMIT,
        /** Content is not a supported book container. */
        UNSUPPORTED_FORMAT,
        /** Too many queued tickets or unreleased ready requests. */
        BACKLOG,
        /** Private staging could not be written. */
        STAGING,
        /** Cancelled by the host, or the entry was closed, before the commit point. */
        CANCELLED
    }

    private final Code code;
    private final String message;

    ImportError(Code code, String message) {
        this.code = code;
        this.message = message;
    }

    public Code code() { return code; }

    public String message() { return message; }

    @Override public String toString() { return code + ": " + message; }
}
