# PDF JPX dependency

`EXR_ENABLE_PDF_JPX` defaults to `ON`; the reading presets state it explicitly.
OpenJPEG is fetched only when both PDF and JPX are enabled. An explicit JPX
`OFF` build keeps the decoder entry point as an unsupported-feature stub.

The pinned OpenJPEG 2.5.4 HTTPS archive and unchanged BSD-2-Clause LICENSE were
hashed in Actions run `39896013624`, before integrating the dependency. Archive
SHA-256: `a695fbe19c0165f295a8531b1e4e855cd94d0875d2f88ec4b61080677e27188a`.
LICENSE SHA-256: `a6af136f3e15038a666b61f376612a07d9a4e48cb7c01adbf3e33b3f14ab49b6`.

The internal static target is `exr_jpx`. It propagates `<openjpeg.h>`, generated
configuration headers, and `OPJ_STATIC`; mutex/thread functions use the upstream
stub implementation. The PDF object target receives `EXR_ENABLE_PDF_JPX=1`
only for enabled builds. The existing private-dependency installation produces
`lib/exreader/{lib}exr_vendor_exr_jpx.{a|lib}` and reconstructs its static link
interface for installed consumers. OpenJPEG headers are internal to the build.
