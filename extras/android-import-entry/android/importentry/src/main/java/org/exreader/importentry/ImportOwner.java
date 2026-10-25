package org.exreader.importentry;

/**
 * Host callbacks. Each is invoked on the host-supplied executor (default: the main looper), never while the
 * entry holds a lock, exactly once per ticket, and may call back into the entry. The entry runs no host SDK
 * code on its copy thread; the host decides here which thread touches its SDK.
 * A host callback RuntimeException is contained after that one notification;
 * onReady's lease stays available to pendingReady/release, with no second onFailed.
 */
public interface ImportOwner {
    /** The ticket's bytes are staged. The host imports {@code request.file()} then calls {@code release}. */
    void onReady(ImportTicket ticket, ReadyRequest request);

    /** The ticket ended without a staged file. No file or temporary remains for it. */
    void onFailed(ImportTicket ticket, ImportError error);
}
