// SPDX-License-Identifier: MIT
package org.exreader.host;

/** One rendered page plus its measured worker time. */
final class PageLoad implements AutoCloseable {
    final PageSnapshot snapshot;
    final long millis;
    private final Runnable accept;
    private final Runnable discard;
    private boolean finished;

    PageLoad(PageSnapshot snapshot, long millis) {
        this(snapshot, millis, () -> {}, () -> {});
    }

    PageLoad(PageSnapshot snapshot, long millis, Runnable accept, Runnable discard) {
        this.snapshot = snapshot;
        this.millis = millis;
        this.accept = accept;
        this.discard = discard;
    }

    void accept() { if (!finished) { accept.run(); finished = true; } }
    @Override public void close() {
        if (!finished) {
            finished = true;
            try { discard.run(); }
            finally { if (snapshot.bitmap != null) snapshot.bitmap.recycle(); }
        }
    }
}
