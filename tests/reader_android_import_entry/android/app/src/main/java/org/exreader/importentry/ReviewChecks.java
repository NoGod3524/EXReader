package org.exreader.importentry;

import android.net.Uri;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import org.json.JSONObject;

/** Actual concurrent callers; no SDK, provider or production test hook. */
public final class ReviewChecks {
    public static JSONObject ticketRaces() throws Exception {
        final int iterations = 20000;
        CyclicBarrier gate = new CyclicBarrier(3);
        AtomicReference<ImportTicket> current = new AtomicReference<>();
        AtomicReference<Throwable> failure = new AtomicReference<>();
        AtomicBoolean cancelled = new AtomicBoolean(), committed = new AtomicBoolean();
        Runnable cancel = () -> race(gate, current, failure, cancelled, true, iterations);
        Runnable commit = () -> race(gate, current, failure, committed, false, iterations);
        Thread canceller = new Thread(cancel, "entry-cancel-review"), publisher = new Thread(commit, "entry-publish-review");
        int cancelWins = 0, commitWins = 0;
        canceller.start(); publisher.start();
        try {
            for (int i = 0; i < iterations; i++) {
                ImportTicket ticket = new ImportTicket(Uri.parse("content://review/ticket"));
                if (!ticket.begin()) throw new AssertionError("begin");
                current.set(ticket); gate.await(10, TimeUnit.SECONDS); gate.await(10, TimeUnit.SECONDS);
                if (failure.get() != null) throw new AssertionError(failure.get());
                if (cancelled.get() == committed.get()) throw new AssertionError("cancel success and commit must have exactly one winner");
                if (cancelled.get()) {
                    cancelWins++;
                    if (ticket.state() == ImportTicket.State.COMMITTED || ticket.commit()) throw new AssertionError("accepted cancel published");
                } else {
                    commitWins++;
                    if (ticket.state() != ImportTicket.State.COMMITTED || ticket.cancel()) throw new AssertionError("publication was withdrawn");
                }
            }
        } finally {
            gate.reset(); canceller.interrupt(); publisher.interrupt(); canceller.join(5000); publisher.join(5000);
        }
        if (canceller.isAlive() || publisher.isAlive()) throw new AssertionError("race workers not joined");
        return new JSONObject().put("ok", true).put("iterations", iterations).put("cancel_wins", cancelWins).put("commit_wins", commitWins);
    }

    private static void race(CyclicBarrier gate, AtomicReference<ImportTicket> current,
            AtomicReference<Throwable> failure, AtomicBoolean result, boolean cancel, int iterations) {
        try {
            for (int i = 0; i < iterations; i++) {
                gate.await(10, TimeUnit.SECONDS);
                result.set(cancel ? current.get().cancel() : current.get().commit());
                gate.await(10, TimeUnit.SECONDS);
            }
        } catch (Throwable error) { failure.compareAndSet(null, error); gate.reset(); }
    }
}
