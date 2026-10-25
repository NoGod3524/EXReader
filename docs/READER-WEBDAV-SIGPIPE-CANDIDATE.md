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

Only an entire passing later run grants this transport candidate. C03 must
combine the resulting candidate source and rerun its original reset/stall/cancel
case. This document grants no SDK, host UI, Android/iOS, real-device, performance
or complete-product acceptance.
