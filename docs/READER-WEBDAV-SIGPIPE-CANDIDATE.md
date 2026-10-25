# WebDAV reset-peer SIGPIPE candidate

The original C03 run `40219386136` on source `1c7e0a5c` recorded a genuine
Linux process exit `-13` while the unchanged installed cloud consumer downloaded
from a TLS peer that closed with an abortive reset. That crash remains a failure.

The libcurl backend sets `CURLOPT_NOSIGNAL=1`, as a worker-thread client should.
That setting does not suppress every socket/TLS SIGPIPE; libcurl explicitly
documents that it stops installing a process-wide SIGPIPE disposition. TLS
cleanup can also send to an already reset socket.

This candidate retains NOSIGNAL and places a POSIX signal-mask owner before the
curl handle. It masks SIGPIPE only on the calling thread for the complete handle
lifetime, including `curl_easy_cleanup`, then consumes a newly pending signal
and restores the original thread mask. An already pending SIGPIPE stays pending.
The module never changes a process-wide signal handler. Installed curl consumers
receive the required Threads dependency through the existing package export.
No SDK, wire, product schema, module ABI/version, budget or original assertion
changes.

Linux uses zero-timeout `sigtimedwait`; Darwin uses `sigwait` only after a pending
signal is observed. Socket-generated SIGPIPE is directed at the blocked calling
thread, so another worker cannot consume that directed signal. This guard is
compiled only for the POSIX libcurl backend. Windows WinHTTP, Apple URLSession,
and Android Java transport source paths are unchanged.

The dedicated Actions workflow builds and installs Linux curl, macOS curl,
macOS URLSession and Windows WinHTTP profiles, and retains both original TLS
and parser-compatibility suites. New independent public-ABI consumers exercise
the unchanged abortive TLS reset with the default signal disposition; POSIX
profiles additionally verify original masks, caller-blocked masks, existing
pending signals and unchanged handlers. Curl profiles signal another thread
while a public cancellation callback observes the caller's guard, proving that
the process-wide handler remains live. Linux also builds the original module
from fixed source `0889f7d1` and requires its real SIGPIPE regression to reproduce.

The first candidate run `40220267962` on `3e80195c` is retained. Its Linux default
reset cases and original suites passed before a new test's callback trigger
failed to fire when the reset arrived before body delivery. Windows compilation
also exposed a missing CRT-warning define in the new consumer. Those are
consumer issues; the second candidate uses a cancellation-callback mask witness
and the CRT define. No first-run fragments are combined with later results.

## Same-source candidate result

Run **40220541331 / attempt 1**, source
`8cc57c078f50c7e81bd2a75620a4acf9b23bb456`, completed **success** for all four
jobs. Each row below is one entire job from that same run/source/attempt.

| Profile | Original TLS | Original compatibility | New reset/signal cases | Job |
| --- | ---: | ---: | ---: | ---: |
| Linux curl | 77 | 12 | 15 | 121250959510 |
| Windows WinHTTP | 76 | 12 | 6 | 121250959790 |
| macOS curl | 77 | 12 | 15 | 121250959620 |
| macOS URLSession | 77 | 12 | 12 | 121250959707 |

Linux's separately compiled **original 0889 WebDAV module** terminated with
SIGPIPE in all **8/8** abortive-reset controls. The candidate survived every
reset, returned a normal failure status, published no output, removed temporary
files, preserved the caller's thread signal mask and preexisting pending signal,
and kept the process-wide handler active on another thread during the guarded
curl call. macOS curl also passed that independent-thread test. The unchanged
Windows and Apple native paths passed their original suites and reset cases.

The exact program hashes, artifact IDs/bytes/digests/expiry, scope and earlier
failure are recorded in
`docs/validation/reader-webdav-sigpipe-candidate.json`. Artifact identity comes
from the GitHub API; check counts and consumer hashes come from same-run job
logs. A following documentation-only commit seals these observations.

C03 must combine this candidate and rerun its original reset/stall/cancel case.
The candidate grants only the tested installed transport scopes. It grants no
SDK, host UI, Android/iOS, real-device, performance or complete-product acceptance.
