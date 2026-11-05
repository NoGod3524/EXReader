# Cloud import: source review

Source reviewed: 9f6bc74b. This is a static review, not a security acceptance run.
Scope: shared cloud-import module and Windows Wave 3 build selection.

* cloud_import.c:619-682: the content-bound build compares a hash observed
  during WebDAV download with the published staging file. The legacy build
  records the staging file hash without an independent download-stream hash.
* cloud_import.c:802-856: import opens a regular file and rechecks its length
  and SHA-256. Non-PDF formats read from the opened source. POSIX PDF reopens
  the live descriptor; Windows PDF reopens the path while file and checked
  parent handles remain held.
* cloud_import.c:138-216: POSIX opens the final component with O_NOFOLLOW.
  Windows checks file and parent attributes and holds handles during import.
  This source review does not establish behavior under untested races.
* cloud_import.c:875-879: cleanup removes the stored path and relies on the
  documented private, host-stable staging directory; it is not an atomic
  identity-checked unlink.
* windows_feature_integration.cmake:19-26 selects the separate content-bound
  package when explicitly enabled. Reviewed Windows composition workflows set
  EXR_COMPOSITION_CONTENT_BOUND=1; tests/reader_wave3_c09/build.py passes the
  selection into the build.

The D13 path-replacement experiment was stopped before execution by a platform
safety check. No such experiment was run in this review. D13 and complete F10
remain unverified; final-host package selection and supported filesystem
assumptions require permitted acceptance evidence.
