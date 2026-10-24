# Android native WebDAV backend

The optional WebDAV C ABI now has an Android implementation. Its accepted source
is `7c27efec9bd5438f8869550dde0872c1f88782da`, based on
`4d4e2be80f6dd103e4b39e739ef3813974acdf00`. The standalone native module targets
Android API 26; actual device acceptance ran on API 34 x86_64. The default reader
and SDK build, existing `exr_webdav.h`, reader account UI, sync/session/revision
packages, and original desktop source tests are unchanged.

Build and host integration instructions are in
[the Android package README](../extras/webdav/android/README.md). Machine-readable
source/run/job/artifact identities and retained failures are in
[the validation record](validation/reader-webdav-android.json).

## Implementation

The platform seam reuses native URL/path validation, configured HTTPS origin and
root containment, redirects, DAV interpretation, XML tree budgets, limits,
upload-file validation and streaming sinks. Android HTTPS uses the pinned
OkHttp 4.12.0 dependency with the platform TLS trust and hostname verifier.
Namespace-aware platform `XmlPullParser` events feed the common native XML
interpreter; DTD declarations and custom/external entities are refused.

The independent support AAR retains no Activity or Context. A Java-origin JNI
entry binds the VM/class once. Each C client belongs to its creating native
worker; cross-thread calls and callback reentry return `EXR_DAV_ARGUMENT`.
Wrong-thread/reentrant free does nothing and leaves disposal to that owner.
Native-created workers attach only around Java operations and detach on every
return/error path. All client and upload-context registries were empty after
each acceptance case, and attach/detach counts balanced.

The 2000-entry, 4 MiB listing and 128 MiB transfer ceilings remain enforced.
PROPFIND uses Depth 1. Reads follow only bounded same-origin/root redirects;
writes never follow redirects. PUT streams exact-length private files with
`If-None-Match: *`; 412 returns `EXR_DAV_EXISTS` and requires a subsequent GET and
identity verification before application acknowledgement. Cancellation retains
the public ABI's I/O-boundary semantics, and the remaining total deadline also
bounds OkHttp connection, writes and reads.

Android's app SELinux rules refused the desktop hard-link publication operation.
The Android branch therefore publishes with `syscall(SYS_renameat2, ...,
RENAME_NOREPLACE)`: complete download publication remains atomic and refuses an
existing destination. The public NDK syscall entry supports the Android 26
kernel baseline; the named Bionic wrapper is API 30+. Unsupported operations or
filesystems return I/O failure and clean up the temporary file. Desktop
publication paths are unchanged.

## Actual platform evidence

The public API probe ran again on the accepted source. Android's
`com.android.okhttp.internal.huc.HttpsURLConnectionImpl` accepted GET/PUT and
rejected PROPFIND/MKCOL with `java.net.ProtocolException`. A trusted fixture TLS
GET succeeded. A configured 150 ms read timeout fired after 162 ms, while a
16 MiB write completed after 2133 ms with the same read-timeout setting. The
public URLConnection API therefore does not supply the required DAV verbs or a
total write deadline. The implementation uses the maintained HTTP dependency
without reflection, hidden APIs, verb spoofing or a custom HTTP/TLS stack.

## Accepted Actions run

[Run 40066284731, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40066284731)
completed successfully on the exact accepted source:

| Job | Result |
| --- | --- |
| Android `120790124702` | API26 Debug/Release native builds; optional AAR; installed-archive C11 consumer; API34 x86_64 device acceptance; package audits |
| Linux `120790124807` | Original source suite 77 checks and compatibility suite 12 checks |
| Windows `120790124808` | Original source suite 76 checks and compatibility suite 12 checks |

The device completed 91 backend checks, including root/nested/redirected
listings, namespaces, non-BMP XML text, encoded Unicode/percent resources,
2000-entry two-propstat listings, overflow/tree/byte limits, malformed XML and
DTD/entities, TLS trust and hostname failures, credential isolation, status
errors, stream cancellation/deadlines/truncation, no-overwrite publication,
owner/reentry, same-client error recovery, immutable MKCOL/PUT/GET, cleanup
cycles and a worker completing after its Activity was destroyed.

Four restart checks then ran after a real `am force-stop` killed PID 2595 after
the server committed an immutable PUT and before its response. The fresh process
retried the identical PUT, received 412, downloaded the existing bytes and
verified the payload SHA-256:
`61d1d9c5745bdaa4fab39240651bc242a5186b15393fd475082fcf6e84f400ab`.

Request traces retain raw request lines, headers with Authorization replaced by
its SHA-256, and PUT body hashes/lengths. No request reached the foreign-origin
server. Credentials entered the test app through stdin into private storage;
they were absent from saved device reports and traces. Generated TLS private
keys were excluded from artifacts.

## Package and dependency measurements

Release audits passed: no fixture CA/debug network configuration/acceptance
counter symbol in Release packages; no curl/libxml/OpenSSL/WebView dependency in
the native consumer; the Android Release configuration refused test hooks.
The fixture CA exists only in the acceptance app's Debug overlay. The support
AAR always uses normal Android TLS trust.

| Measurement | Bytes or references |
| --- | ---: |
| Support Release AAR, without external Maven runtimes | 8793 bytes |
| Installed Release static archive | 1602576 bytes |
| Minimal baseline Release APK | 1808 bytes |
| Release C-consumer APK with backend and runtimes | 1521720 bytes |
| APK increment | 1519912 bytes |
| Baseline / backend DEX method references | 2 / 16585 |
| DEX method-reference increment | 16583 |

This APK increment includes the C consumer and native C++ runtime as well as
the WebDAV support and HTTP dependencies. The accepted Maven artifacts were
OkHttp 4.12.0, Okio JVM 3.6.0, Kotlin stdlib/common/jdk7/jdk8 1.9.10 and JetBrains
annotations 13.0. Their artifact/POM hashes and declared Apache 2.0 licenses are
recorded in `build/webdav-android/packages/packages.json` inside the artifact.
EXReader's own source remains MIT-licensed.

## Artifacts and retained failures

The Android artifact is
[12549174247](https://github.com/NoGod3524/EXReader/actions/runs/40066284731/artifacts/12549174247),
3721895 bytes, ZIP SHA-256
`ede65868492085ed347d3db41f2a5942e2f95751dd3b3301f4c8779782abf462`.
It contains source identity, build logs, safe partial/final reports, request
traces, public certificates, package audits, Debug/Release installed archives,
APKs and support AARs. Linux/Windows artifacts and all earlier failure identities
are listed in the validation record.

Retained failures explain the delivered changes: the first probe checkout was
shallow; the first native configuration read the NDK system version instead of
its API level; the installed-package consumer initially searched only the NDK
sysroot; then two runs recorded and diagnosed Android's hard-link refusal. No
failed run was replaced or counted as acceptance.

This acceptance covers the Android WebDAV backend and immutable transport
primitives. Android account UI and full reader sync-session integration remain
separate work. All compilation, syntax checks, emulator execution, fixtures and
package inspection ran on Actions.
