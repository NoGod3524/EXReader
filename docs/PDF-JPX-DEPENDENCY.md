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

Actions run `39896466417` at `e6ae14e1c1e3fbb6ac191f3459a01fd3ba6580cc`
completed all five dependency jobs. Core/library installed consumers passed
3/3 and 5/5; both stages passed strict release-license materials, retained the
31 license negative cases plus 1 mandatory-material check and 3 source-material
positives, and retained all 7 composition rejection cases. A separate installed
consumer linked `EXReader::exr_pdf`, forced `opj_version` from the private archive,
and executed successfully. Explicit JPX-OFF and PDF-OFF builds fetched no
OpenJPEG and installed no OpenJPEG archive, imported dependency or license.

`native-pdf-jpx` is registered whenever tests, PDF and JPX are enabled, independent
of `EXR_FULL_TESTS`. It links the decoder through `exr_pdf`, plus `exr_jpx` for the
test's lossless fixture encoder; it does not define the standalone helper stubs.
That combined decoder regression must run after the decoder source and layer
registration are integrated; the five dependency jobs above do not claim it.
