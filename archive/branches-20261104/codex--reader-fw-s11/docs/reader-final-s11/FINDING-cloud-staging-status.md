# S11 finding: a local staging failure is reported as READER_CLOUD_REMOTE

Affected owner: EXReaderCloudImport (apps/reader/cloud-import). This package did
**not** modify it, did not weaken the assertion, and did not re-run after the
finding was observed.

## Observation

Tested source: 56ffaf519e9b604a585a604025805935541b8077
Run: 40218428719, attempt 1, jobs 121244517770 (Windows), 121244517784 (Linux),
121244517614 (macOS).
Row: C2 (cloud.missing) — the private staging directory handed to
reader_cloud_download does not exist.

| field | observed | documented |
| --- | --- | --- |
| reader_cloud_download return | remote (READER_CLOUD_REMOTE) | io (READER_CLOUD_IO: "staging file unreadable, missing or unwritable") |
| *staged | NULL | NULL |
| staging directory created by the call | no | no |
| SDK row | none | none |
| staging file left behind | none | none |

The three invariant columns match the contract; only the status name differs, on
all three operating systems, deterministically.

## Code path

1. reader_cloud_import.h:34 defines READER_CLOUD_IO as "staging file unreadable,
   missing or unwritable"; :36 defines READER_CLOUD_REMOTE as "WebDAV failure:
   see webdav_code / http_status".
2. apps/reader/cloud-import/src/cloud_import.c:492 calls
   exr_webdav_download_file(client, resource, request->staging_dir, filename, ...).
3. extras/webdav/src/webdav.cpp:173 (Windows) / :184 (POSIX) rejects with
   EXR_DAV_IO "Private destination directory is unavailable" when the private
   directory cannot be opened; :201 rejects with EXR_DAV_IO when no temporary
   file can be created.
4. cloud_import.c:497-518 maps every remaining webdav status to
   READER_CLOUD_REMOTE (lines 516-517) and copies webdav_code into the error.
   EXR_DAV_IO is therefore reported as remote.

The failing call is entirely local (host-owned directory), but the published
status says it was a remote/transport failure.

## Why this matters for a reader

READER_CLOUD_REMOTE is the status a host retries as a network problem. A missing
staging directory, a read-only one, or a full volume never heals by retrying, so
that retry path is a loop that cannot succeed. The same mapping applies to rows C3
(read-only staging) and C4 (ENOSPC staging), which could not be executed in this
run because the judge stops at the first violated assertion.

## Two ways to close it (owner decides)

1. Map a local staging failure to READER_CLOUD_IO: in cloud_import.c, before the
   REMOTE fallback, treat status == EXR_DAV_IO (the webdav module already
   distinguishes it) as READER_CLOUD_IO. READER_CLOUD_REMOTE then keeps meaning
   "the server or transport failed".
2. Keep the current behaviour and say so in the header comment for
   READER_CLOUD_REMOTE ("includes a private staging directory that cannot be
   created; see webdav_code == EXR_DAV_IO"). With that text, S11 rows C2/C3/C4
   expect "remote" **for a documented reason**, which is a specification fix, not
   a lowered assertion.

## Reproduction (Actions only)

    python3 tests/reader_final_s11/check_s11.py --probe <s11-probe>
      --fixtures build/s11-fixtures --work build/s11-work
      --output build/s11-evidence --module-prefix build/s11-prefix

or at probe level, a spec file with:

    cmd=cloud
    root=https://127.0.0.1:<port>/dav/
    auth=Basic <fixture-only credentials>
    resource=books/book.epub
    name=book.epub
    format=EPUB
    staging=<a directory that does not exist>
    expected=<byte length of the fixture>
    library=<new sqlite file>

The probe prints the returned status name; the judge fails on the first
cloud.missing.download expectation.
