// SPDX-License-Identifier: MIT
package org.exreader.host;

import java.io.IOException;
import java.util.function.BooleanSupplier;

/** One request; cancellation ends at publication, never waits for database I/O. */
final class HostTask {
    interface Action { void run() throws Exception; }
    static final class Cancelled extends IOException { Cancelled() { super("Operation canceled"); } }
    private final BooleanSupplier obsolete;
    private boolean cancelled, committing, committed;
    HostTask(BooleanSupplier obsolete) { this.obsolete = obsolete; }
    synchronized void cancel() { if (!committing && !committed) cancelled = true; }
    synchronized void check() throws Cancelled {
        if (!committing && !committed && (cancelled || obsolete.getAsBoolean())) {
            cancelled = true;
            throw new Cancelled();
        }
    }
    void commit(Action action) throws Exception {
        synchronized (this) {
            check();
            if (committing) throw new IllegalStateException("Publication is already in progress");
            committing = true;
        }
        try {
            action.run();
            synchronized (this) { committed = true; committing = false; }
        } catch (Exception | Error error) {
            synchronized (this) { committing = false; }
            throw error;
        }
    }
}
