# READER-DIAGNOSTIC-REPORT

User-triggered, bounded diagnostic export for import/sync/reading failures:
`apps/reader/diagnostic-report/` (package), `tests/reader_diagnostic_report/`
(installed consumers, test-hook worker, cloud checker),
`.github/workflows/reader-diagnostic-report.yml` (three-platform acceptance).

Status: **T06 cloud-accepted for the module and installed-consumer scope only.** The
package does not wire itself into any host. Reports, module behaviour, host
behaviour, performance, accessibility and real-device coverage are granted
separately; nothing here is a host or product acceptance.

## 1. Contract

Public header: `apps/reader/diagnostic-report/include/reader_diagnostic_report.h`
(installed to `<prefix>/include`). ABI version 1, format version 1, static C ABI
library `EXReaderDiagnosticReport::reader_diagnostic_report`.

Input (`reader_diag_input`, start from `reader_diag_input_defaults()`):

| field | type | bound |
| --- | --- | --- |
| `app_version` | strict ASCII grammar | <= 32 bytes |
| `platform` | enumerator windows/linux/macos/ios/android/other | 1..6 |
| `operation` | enumerator import/sync/reading/search/other | 1..5 |
| `sdk_abi` | integer | 0..65535 |
| `sdk_major/minor/patch` | integer each | 0..9999 |
| `schema_version`, `wire_version` | integer | 0..65535 |
| `generated_at_unix` | host clock | 0 (unknown) or <= 4102444800 |
| `account_configured`, `sync_enabled`, `offline_mode` | tri-state | 0/1/2 |
| `counters[]` | (id, value) | <= 16 entries, ids unique, value <= 2^53-1 |
| `errors[]` | (domain, kind, count) | <= 32 entries, (domain, kind) unique, count 1..2^53-1 |

Output: immutable report with canonical pretty-printed JSON (`format`
exreader-diagnostic-report, `format_version` 1, LF line ends, trailing newline,
<= 8192 bytes) and a plain-text summary (<= 4096 bytes). Entry order in the input
does not matter: errors are ordered by domain then kind, counters by id, so equal
content yields equal bytes.

### Privacy set (closed)

Only the fields above exist. Book and annotation text, titles, absolute paths,
account root URLs, credentials, server bodies, raw logs and private databases have
no input field, so they cannot reach the output. The one text field,
`app_version`, must match MAJOR.MINOR.PATCH followed optionally by -alpha,
-beta or -rc and optionally .N, with 1..6 digit parts, no leading zeros and no
build metadata; anything else is FIELD. Rejected input is never echoed:
`reader_diag_error.message` names the field, never its value. The library never
reads a file, environment variable, clock, account, log or database, and never
uploads anything.

### Ownership, threads, errors, cancellation

- Every input pointer is borrowed for the single call and not retained. The
  report owns its two strings; they are ASCII, NUL-terminated, valid until
  `reader_diag_report_free()`, and their size excludes the NUL.
- No global mutable state. Distinct builds and distinct reports are thread-safe;
  a report is immutable and can be read by many threads at once, but must not be
  freed under a reader.
- Cancel callbacks run synchronously on the calling thread. Cancellation during
  build returns CANCELLED with no allocation; during publish it returns CANCELLED,
  removes the temporary and leaves the filesystem as it was.
- Statuses: OK, ARGUMENT, FIELD, DUPLICATE, LIMIT, IO, EXISTS, CANCELLED, MEMORY.
  `error.system_error` carries errno/GetLastError for IO only.

### Commit boundary

`reader_diag_report_write()` writes the bytes to a same-directory temporary,
flushes it, and only then commits with one primitive that fails when the target
exists: MoveFileExW without MOVEFILE_REPLACE_EXISTING on Windows (UTF-8 path
converted to UTF-16, invalid UTF-8 is ARGUMENT), link(2) on POSIX. Consequences:

- an existing target (file, directory or dangling link) yields EXISTS and is never
  opened for write, truncated or removed;
- concurrent writers to one path: exactly one OK, the rest EXISTS;
- a process killed before the commit leaves no target and at most one orphan
  <target>.reader-diagnostic.tmp-<pid>-<attempt>; killed after the commit it
  leaves the whole report;
- temporary names carry the process id and an attempt index, so an orphan never
  blocks a later writer, and no clock or global counter is needed.

Limits on the mechanism: Windows paths are limited to MAX_PATH because no extended
prefix is added; a filesystem that does not support hard links makes the POSIX
commit fail with IO rather than risk a replacing rename.

## 2. Reproduce

Everything below runs only on GitHub Actions; the local checkout holds source,
docs and Git only.

    cmake -S apps/reader/diagnostic-report -B build/diag -G Ninja \
      -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$PWD/build/diag-stage"
    cmake --build build/diag --parallel 4
    cmake --install build/diag
    cmake -S tests/reader_diagnostic_report/consumer -B build/diag-consumer -G Ninja \
      -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH="$PWD/build/diag-stage" \
      -DEXR_DIAGNOSTIC_SOURCE="$PWD/apps/reader/diagnostic-report/src" \
      -DEXR_DIAGNOSTIC_INCLUDE="$PWD/apps/reader/diagnostic-report/include"
    cmake --build build/diag-consumer --verbose
    python3 tests/reader_diagnostic_report/check_diagnostic_report.py \
      --consumer-dir build/diag-consumer --installed build/diag-stage \
      --build-log build/diag-logs/consumer-build.log \
      --output build/diag-evidence --platform Linux

The workflow runs that sequence on ubuntu-22.04, windows-2022 and macos-15, then a
fourth job downloads the three ZIPs from the same run, recomputes each digest,
re-reads `diag-evidence/result.json` from inside the ZIP and requires the exact
per-platform case set.

## 3. Named acceptance cases

Guards (each job): HEAD equals GITHUB_SHA, the fixed start is an ancestor, the
protected SDK tree is byte-identical to
9854061be331fe603a1822d9b2b36ee357154927, product `001_catalog.sql` is unchanged
since the start, and every changed path is inside the J21 ownership list.

Installed C consumer, installed C++ consumer, then 32 named cases:

installed-header-contract, c-consumer, cpp-consumer,
installed-consumers-compile, abi-and-status-names, defaults, minimal-report,
typical-report-bytes, canonical-order, max-entries-fit, entry-limits, output-limits,
app-version-grammar, refusal-no-echo, field-closed-set, duplicate-entries,
struct-and-abi-guards, output-bytes-secret-scan, publish-new-file,
publish-exists-not-replaced, publish-directory-target, dangling-symlink-target
(Linux/macOS), invalid-utf8-target (Windows), publish-io-failure, cancelled-build,
cancelled-write, kill-before-commit, kill-after-commit, concurrent-writers,
unicode-target, thread-safety, output-lifetime.

The positive/negative planted material is sk-live-9f2c8a1b7d,
https://reader:pa55w0rd@example.invalid/dav, /home/alice/books/secret.epub,
C:\Users\alice\Desktop\private.epub, -----BEGIN PRIVATE KEY-----,
Bearer eyJhbGciOiJIUzI1NiJ9 and example.invalid. They are planted into
`app_version`, refused with FIELD, and each refusal output is checked for the
planted bytes. Independently, every produced JSON and summary file is scanned byte
by byte: printable ASCII plus LF only, no slash, no backslash, no scheme, no at
sign, no planted secret. The scanner reads the files, not a library flag.

## 4. What is not covered

- Host wiring on Windows, GTK, Android and Apple, and the product UI: owned by
  root and the three main-line hosts. This package ships the module plus an
  installed-consumer example only.
- Automatic upload: explicitly out of scope; the library never sends anything.
- Real-device, desktop, audio and screen-reader acceptance: not claimed.
- Performance: no budget is claimed or measured; the report is bounded by the
  entry limits and the two output buffers.
- output-limits exercises the overflow guard through the test-hook build only.
  Contract-valid input cannot overflow (proved by max-entries-fit: the full closed
  counter set and 32 errors stay inside 8192/4096 bytes), so the guard exists to keep a future
  limit change from silently truncating.
- Windows path length beyond MAX_PATH; POSIX filesystems without hard links.


## 5. Cloud acceptance

Tested source: 7ee7ab8050fca0f471cc2321c3ccc2c1aaca2e6d. Run 40126181997 attempt 1
(https://github.com/NoGod3524/EXReader/actions/runs/40126181997), all four jobs
success. Evidence JSON: docs/validation/reader-diagnostic-report.json.

| platform | job | applicable cases | artifact id | bytes |
| --- | --- | --- | --- | --- |
| Linux | 120967980675 | 31 | 12573551615 | 78939 |
| Windows | 120967980931 | 31 | 12573481634 | 333053 |
| macOS | 120967980928 | 31 | 12573296755 | 73644 |
| strict evidence | 120968142793 | summary | 12573102080 | 963 |

The strict evidence job authenticated the three platform ZIPs against the Actions
API in the same run, recomputed each sha256 digest, re-read
diag-evidence/result.json from inside every ZIP and required the exact
per-platform case set. The union of the three platforms covers all 32 contract
cases, and the aggregator refused every cross-source, missing or edited artifact
path it knows about.

Retained original failures (kept as evidence, not rewritten):

- run 40125336749 attempt 1 at 132968f7: the installed-header scan refused the
  ull suffix, the max preset filled 16 counter slots while only 10 ids exist,
  the before-commit hook was armed on every publish so the after-commit test
  waited on the wrong marker, io.c ended without a newline and failed
  -Wnewline-eof on macOS, and a live paused worker held a temporary file so the
  Windows artifact upload failed with EBUSY.
- run 40125859530 attempt 1 at 72cc1b65: the checker compared enumerator names
  alphabetically instead of by id and refused a correct report on all three
  platforms.

The original evidence commit `4793224343950b279a3591c8398f5a2a8514d754`
changed documentation only relative to tested source `7ee7ab80`.

## 6. T06 independent review

The review starts at `4793224343950b279a3591c8398f5a2a8514d754`, on
`codex/dot-diagnostic-report-review`. Section 5 remains the original, historical
acceptance, not evidence for subsequent review changes. Its four jobs and four
artifact metadata records were independently re-read through the GitHub API;
the start differs from the original tested source only in the two evidence docs.

Directed inspection followed validation, canonical rendering, error construction,
build cancellation, immutable report lifetime, both publish backends and cleanup.
No caller text is accepted except the bounded version grammar; domain/kind pairs
cannot carry nested error messages. No production rendering defect was found.
Borrowed input must remain alive and stable throughout a call, as with other C
ABI pointer inputs; the header now makes that synchronization responsibility
explicit. The module does not take a lock on mutable host data. The installed
audit consumer verifies post-build input independence, concurrent immutable
reads and builds from a stable shared snapshot, and cancellation callback reentry.

Confirmed acceptance gaps and narrow fixes:

- The prior secret corpus omitted Authorization header names, URL query tokens,
  titles, body/annotation text and nested error messages. New generated vectors
  inject those bytes into the actual installed module, plus malformed UTF-8,
  controls, an over-limit version and an embedded-NUL C-string boundary case.
  All produced files and captured consumer stdout/stderr are scanned at the end,
  including files produced after the original `output-bytes-secret-scan` case.
- The old IO failure case only used an absent directory. Test-only hooks now
  inject failure after 17 actual written bytes, before flush and before commit,
  for absent and existing targets. They preserve size/mtime/hash of existing
  targets and require no temporary or new destination on refusal. No hook is
  compiled into or exposed by the installed library.
- Strict evidence now authenticates completed successful producer jobs against
  source/run/attempt, artifact creation interval, unique ID/name, expiry, ZIP
  size and API SHA256; rejects duplicate ZIP/report/JSON members; recomputes
  identities of every installed package file and four actual consumer binaries;
  and exercises negative mutations through the real verifier in Actions.

All original 32 named cases and historical failures remain. Four additional cases
bring the union to 36 (35 applicable per platform). Windows/macOS/Linux module
coverage only: no host/UI/device/accessibility/performance acceptance, no host
adapter for nested-error mapping, and no concurrent mutation of borrowed input.
Fault hooks test cleanup branches, not physical disk failure or power-loss
durability; original process termination and publication races remain exercised.

### T06 cloud evidence

Tested source: `da86e2107249801a97f39d47ec6ea047b624c594`.
[Run 40164861121, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40164861121)
completed successfully at 2026-10-25T05:29:58Z. All three platform logs report
35 applicable checks and zero failures; their union covers the original 32
cases and the four new review cases. Strict evidence passed all 26 negative
mutations against its actual authenticated Linux bundle. No review run failed;
the original two J21 failed runs remain recorded, unchanged.

| platform | successful job | artifact ID | ZIP bytes | API/recomputed ZIP SHA256 |
| --- | --- | --- | --- | --- |
| Linux | 121083721392 | 12587966373 | 98161 | `3d051eab43332fd748b755b3decb577e9474fd566995b81f3f388990ef972cf1` |
| Windows | 121083721389 | 12587329752 | 436444 | `cfffd26a1734ce0a2689ee645ef55eb709c0cbf2ce0b488a7ae18872f66a7acf` |
| macOS | 121083721192 | 12588316564 | 90334 | `785c413a5e46df922417420a970d24d1f3fb0cb6348c07d378c6797906a1e59f` |
| strict summary | 121086275459 | 12588596093 | 1927 | `2053e9831dd84953d59e5348e2eaf56dba599018015e368c5bdd49923302a105` |

All four artifacts expire at `2027-01-23T05:15:21Z`. Platform ZIP hashes were
recomputed inside the strict Actions job; the summary ZIP identity is the
uploader/API identity (the summary does not authenticate its own enclosing ZIP).
The complete emitted cloud summary, including all 12 consumer binary sizes and
SHA256s, is transcribed into `docs/validation/reader-diagnostic-report.json`.
No ZIP was downloaded, unpacked or parsed outside Actions.

The final `[skip ci]` evidence commit changes only this Markdown and that JSON
relative to the tested source. Its exact SHA is reported in the handoff; the JSON
identifies it as its containing commit to avoid a self-referential Git hash.
Root still owns integration and any host-level acceptance.
