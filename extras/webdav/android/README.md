# Optional Android WebDAV support

This package implements the existing `exr_webdav.h` C ABI on Android API 26 and
newer. It consists of an installed native static library and a separate Java
support AAR. It is independent of the default reader/SDK build.

The native module keeps URL validation, origin and root containment, redirect
policy, DAV interpretation, XML budgets, stream limits, upload-file validation,
and temporary-file publication. Android uses OkHttp **4.12.0** for HTTPS and the
platform namespace-aware `XmlPullParser` for XML events. The AAR has no native
cryptography and installs no custom trust manager or hostname verifier.

## Build and consume

Build the AAR with Java 17, Gradle 8.9 and Android Gradle Plugin 8.7.3:

```sh
gradle -p extras/webdav/android :webdav:assembleRelease
```

Either include this Gradle library module in the host, or supply its AAR together
with `com.squareup.okhttp3:okhttp:4.12.0` and its resolved runtime dependencies.
An AAR supplied as a local file does not supply Maven dependency metadata. Keep
the included consumer rules when shrinking the host.

Build/install the independent native module with the Android NDK toolchain:

```sh
cmake -S extras/webdav -B build/android-dav -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE="$ANDROID_NDK_HOME/build/cmake/android.toolchain.cmake" \
  -DANDROID_PLATFORM=android-26 -DANDROID_ABI=arm64-v8a \
  -DANDROID_STL=c++_static -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$PWD/build/android-dav-stage"
cmake --build build/android-dav
cmake --install build/android-dav
```

The host uses `find_package(EXReaderWebDAV CONFIG REQUIRED)` and links
`EXReaderWebDAV::exr_webdav`. It links the C++ runtime according to its own NDK
packaging policy. No libcurl, libxml2, OpenSSL or system curl installation is
required on Android.

Call `exr_webdav_android_initialize(env)` once from a Java-origin JNI entry, on a
thread whose loader can resolve `org.exreader.webdav.Transport`. Initialization
retains the VM and support class, without an Activity or Context. It returns
`EXR_DAV_IO` if the support class is unavailable and is idempotent after success.
Create, use and free each client on the same worker. The UI thread cannot create
a client. Calls from another native thread and callback reentry return
`EXR_DAV_ARGUMENT`; a wrong-thread/reentrant `free` does nothing, so the owner
must free the client once its current call returns. Native-created workers
attach to the VM only around Java operations and detach on return, including
error paths.

Host cancellation/progress callbacks run synchronously on that native owner.
Cancellation follows the existing ABI's I/O-boundary semantics. OkHttp's total
call timeout bounds connection, request writing and response reading by the
remaining common deadline; redirects consume the same native deadline. Dispose
of clients on their worker when closing a screen/session. Process termination
releases process resources; immutable writes interrupted after remote commit
must be retried conditionally and verified by GET before an application ack.

## Protocol and trust

Requests use HTTP/1.1, no proxy, no cookies, no automatic authentication, no
transport redirects and no connection-failure retry. Native code follows at
most four safe read redirects within the configured HTTPS origin and root.
Writes never follow redirects. PUT uses a fixed length, 64 KiB streaming chunks
and `If-None-Match: *`. A 412 returns `EXR_DAV_EXISTS`; the host must verify remote
identity. GET publishes only a complete bounded file and never replaces an
existing local destination.

Android publishes with the public NDK `syscall(SYS_renameat2, ...,
RENAME_NOREPLACE)` entry. Android application SELinux rules permit rename while
the desktop hard-link publication operation is refused. The kernel operation
exists in Android 26's kernel baseline; Bionic's named libc wrapper starts at
API 30. `ENOSYS`, unsupported filesystem flags and other publication failures
return I/O failure and remove the temporary file. There is no replacing-rename
fallback. Windows and Linux retain their existing publication paths.

The unchanged hard limits are 2000 entries, 4 MiB listing bytes and 128 MiB
transfer bytes. XML forbids DTD declarations and custom/external entities, and
feeds the common depth, per-response element and text limits. Predefined and
numeric XML character references, namespaces and UTF-8 metadata are supported.

Production uses Android's default TLS trust and hostname verification. The
acceptance app alone has a debug resource overlay for an Actions-generated CA.
Neither the AAR nor the Release app/static library contains that CA, the debug
network configuration or acceptance counters. CMake refuses
`EXR_WEBDAV_ANDROID_TESTING=ON` outside Debug.

## Dependencies and verification

OkHttp and Okio use Apache License 2.0; Kotlin uses Apache License 2.0; JetBrains
annotations use Apache License 2.0. The workflow records each resolved artifact's
version, byte size, SHA-256, Maven license declaration and POM hash. These
licenses remain separate from the MIT-licensed EXReader module.

The API34 x86_64 Actions consumer compiles `consumer.c` as C11 against only the
installed headers/archive. It exercises actual HTTPS DAV, limits, refusal paths,
owner/reentry cleanup, Activity exit and a process kill after remote PUT commit,
then verifies the conditional retry by GET. Release audits record AAR/APK/native
bytes, DEX method references, native dependencies, and forbidden fixture/hook
scans. Original Windows/Linux source and compatibility suites run from the same
source when shared platform dispatch changes.

Sources: [OkHttp 4.12.0](https://github.com/lysine-dev/okhttp/tree/parent-4.12.0),
[OkHttp license](https://github.com/lysine-dev/okhttp/blob/parent-4.12.0/LICENSE.txt),
[Android XML pull API](https://developer.android.com/reference/org/xmlpull/v1/XmlPullParser).
