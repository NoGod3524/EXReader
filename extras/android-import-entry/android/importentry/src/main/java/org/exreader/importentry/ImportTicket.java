package org.exreader.importentry;

import android.net.Uri;
import java.util.concurrent.atomic.AtomicInteger;

/** Handle for one URI submitted to {@link ImportEntry}. Thread-safe. */
public final class ImportTicket {
    public enum State { QUEUED, COPYING, COMMITTED, FAILED, CANCELLED }

    private static final int QUEUED = 0, COPYING = 1, COMMITTED = 2, FAILED = 3, CANCELLED = 4;
    private final Uri uri;
    private final AtomicInteger state = new AtomicInteger(QUEUED);
    private volatile boolean cancelRequested;

    ImportTicket(Uri uri) { this.uri = uri; }

    /** The submitted content URI (only an input; never used as a path). */
    public Uri uri() { return uri; }

    public State state() { return State.values()[state.get()]; }

    /** True once the ticket has reached COMMITTED, FAILED or CANCELLED. */
    public boolean isDone() { return state.get() >= COMMITTED; }

    /**
     * Requests cancellation. Effective until the atomic publish: the copy stops within about 250 ms even when the
     * provider stalls, and the temporary is removed. Returns false when the ticket is already committed or done;
     * a committed file is never withdrawn, the host releases it instead.
     */
    public boolean cancel() {
        cancelRequested = true;
        return state.get() < COMMITTED;
    }

    boolean cancelRequested() { return cancelRequested; }

    boolean begin() { return state.compareAndSet(QUEUED, COPYING); }

    /** The commit boundary: after this returns true cancellation can no longer win. */
    boolean commit() { return !cancelRequested && state.compareAndSet(COPYING, COMMITTED); }

    void fail() { state.set(FAILED); }

    void cancelled() { state.set(CANCELLED); }
}
