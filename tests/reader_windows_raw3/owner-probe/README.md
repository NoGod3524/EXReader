# Actual Windows records owner consumer

Build only in Windows Actions, with the installed SDK **3.41.0** and one complete
installed module family. This target compiles the production
`apps/reader/desktop/windows_records_owner.cpp` directly. It does not copy its
implementation and does not modify production sources.

Configure with `-DPROBE_RAW=ON` for revisions 0.4.0 / seven companion modules
0.2.0; `OFF` requires revisions 0.3.0 / companion modules 0.1.0. Pass
`-DEXR_SDK=<SDK install>` and `-DCMAKE_PREFIX_PATH=<family;product;SDK>`.
The installed product provider supplies all consumer SQLite calls. The link map
is `windows-owner-probe.map`.

All invocations require `GITHUB_ACTIONS=true`. `WORK` must be a fresh isolated
directory for a first invocation. `PDF` is the existing real 8845-byte
`tests/fixtures/pdf-public-text.pdf`, whose public SDK normalized text contains
NUL. The consumer imports original bytes with the public library API, reads them
back, computes their actual hash and attaches the real public product mapping.
Reflow compatibility cases import an actual TXT source through the same SDK.

| Command | Profile and purpose |
| --- | --- |
| `windows-owner-probe suite WORK PDF` | ON: NUL point/range, LIST/READ, independent new SDK handles and FOUND/recapture, NOTE_TEXT, mode-only deletion, source versions 1/2/3 restore, unsupported parser admission, explicit NULL transport. OFF: real legacy TXT owner and unchanged NUL refusal. |
| `windows-owner-probe fresh WORK PDF` | ON, after ON suite: another OS process reopens the real SDK and product databases and reads/resolves stored fixed3 progress. |
| `windows-owner-probe child WORK PDF 2 MARKER` | ON: real owner publishes pending bytes, flushes MARKER at phase 2 before apply, and waits for the external driver to terminate it. |
| `windows-owner-probe child WORK PDF 3 MARKER` | ON: phase 3 is after the actual public RC commit returned, before owner deletes this pending file. |
| `windows-owner-probe verify-child WORK PDF 2` | ON after killing phase 2 child: reopen independently, verify original RID is absent, retry actual retained request, require created=1. |
| `windows-owner-probe verify-child WORK PDF 3` | ON after killing phase 3 child: verify original RID is durable, receive a genuine newer public-capture progress head, retry original RID with created=0, require no rollback, requeue or retained-wire rewrite. |
| `windows-owner-probe legacy-child WORK PDF MARKER` | **OFF executable**: actual legacy owner captures a TXT range and publishes original EXRRD001 bytes. MARKER is flushed at phase 2; external driver kills it. |
| `windows-owner-probe legacy-retry WORK PDF` | **ON executable**, same WORK: consume that genuine OFF-generated EXRRD001 unchanged; source remains anchor2. |
| `windows-owner-probe reject-private WORK PDF` | OFF executable while a raw PDF child pending file exists: a second save must fail without changing any pending bytes or product rows. Run before the ON verifier consumes it. |
| `windows-owner-probe reject-legacy-private WORK PDF` | ON executable while the OFF TXT pending file exists: a new save must fail without rewriting/migrating the old intent. |

The driver waits for a complete flushed marker, checks the marker PID, calls
Windows `TerminateProcess` on that actual child, waits for its exit, and then
launches the verifier as a new process. This program does not return a simulated
commit result and does not simulate a process death inside the owner.

Each completed invocation writes `WORK/report-MODE.json` and emits the same one
JSON object on stdout; failure returns 1. Reports include named assertions,
consumer source, production owner file SHA-256, executable SHA-256, actual SDK
version and all eight module header versions. Kill children instead emit a phase
marker and never emit a successful completion report. Original pending bytes and
the committed original request wire are saved by the verifier for root evidence.

The NULL case is explicitly a codec-generated **retained transport expression**,
not a claimed SDK capture or a Mac interoperability grant. Its route comes from
the actual public SDK original; its NULL selector fields must never grant FOUND,
navigation, note editing or restore. Real NUL point/range cases and every positive
restore use only actual public SDK capture/resolve results.

Product write assertions compare all rows of all product tables through a
read-only connection, including retained history and outbox. SDK assertions use
only public original/book/progress/note APIs; they never query SDK SQL tables.
UI execution, SDK freezing and product acceptance remain with the root workflow.
