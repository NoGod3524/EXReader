# J20 · Reader localization resources and strict formatting

SPDX-License-Identifier: MIT

Status: module implemented and cloud-verified in Actions only (see
[validation/reader-localization.json](validation/reader-localization.json)).
Host wiring is still root's work: this package changes no host string and adds
no dependency to an existing host target.

- Fixed start: `f43baf9182d75907c0cb5d6f77048f27bca8c950`
- Branch: `codex/reader-localization`
- Package: `EXReaderLocalization 0.1.0` (static C library `reader_localization`, C ABI,
  installed CMake package, ABI 1)
- Sources: `apps/reader/localization/`; consumers and checker: `tests/reader_localization/`;
  workflow: `.github/workflows/reader-localization.yml`

## What this package is

A fixed zh-CN/en-US user-facing text pack plus a strict renderer, for the seven
reader surfaces that need new strings: shelf, import, organize, reading, sync,
error and accessible names. It owns its own message ids; it never reads,
replaces, shadows or diffs a host string table, a platform resource bundle or an
ICU/NSLocalizedString/Gettext catalog. Existing host strings stay untouched.

It is deliberately not an i18n framework: no ICU, no WebView, no JS UI, no
global language list, no plural-rule engine, no runtime resource parser, no
translation of user data, no server, no file, no database, no sidecar.

## Contract

### Message ids and slots

Ids are ASCII, stable, at most 96 bytes (`READER_LOCALIZATION_MAX_MESSAGE_ID`),
and belong to this package (`reader.<surface>.<name>`). A message declares a
slot layout of at most 8 slots (`READER_LOCALIZATION_MAX_SLOTS`), one of:

| kind | meaning | accepted value |
| --- | --- | --- |
| `s` | string | borrowed NUL-terminated UTF-8, at most 1024 bytes |
| `d` | signed decimal | `int64_t`, ASCII digits, `-` for negatives, no grouping |
| `u` | unsigned decimal | `uint64_t`, ASCII digits, no grouping |

The slot layout is locale independent: zh-CN and en-US rows of the same id must
use exactly the indices `{0}`..`{n-1}` once each, in any order. Word order may
differ; the index set may not.

```
reader_localization_message_count()          -> 62
reader_localization_template_count()         -> 124 (62 ids x 2 locales)
reader_localization_message_at(index, out)   id, group, kinds, slots
reader_localization_template_at(index, out)  shipped row: id, locale, text, slots, fallback=0
reader_localization_resolve(context, id, out)  requested row, or en-US with fallback=1
```

Groups and their ids are enumerated in `tests/reader_localization/localization_fixtures.py`
(the acceptance oracle) and in `apps/reader/localization/src/catalog.c`
(the shipped table). The two must agree; a change to one without the other fails
`catalog-coverage-zh-en`.

### Rendering

```c
reader_localization_status reader_localization_measure(
    const reader_localization_context *, const char *message_id,
    const reader_localization_param *params, size_t param_count,
    reader_localization_measurement *out);

reader_localization_status reader_localization_format(
    const reader_localization_context *, const char *message_id,
    const reader_localization_param *params, size_t param_count,
    char *out_text, size_t out_bytes, reader_localization_measurement *out_measurement);
```

`measurement.bytes` includes the terminating NUL. Checked in this order:

1. context (`ARGUMENT`): `struct_size`, locale value, zeroed reserved words
2. message id (`ARGUMENT` for null/empty/over 96 bytes, then `UNKNOWN_MESSAGE`)
3. parameter count (`PARAMETER_COUNT`: `param_count` must equal the declared slots)
4. parameter struct and kind (`ARGUMENT` for an unset `struct_size` or an unknown
   kind enum, `PARAMETER_TYPE` for a declared-kind mismatch)
5. string values (`ARGUMENT` for a null value, `VALUE_INVALID` for malformed UTF-8,
   `VALUE_TOO_LONG` beyond 1024 bytes)
6. template self-consistency (`CATALOG`; the shipped catalog never triggers it,
   the hook build proves it is enforced)
7. rendered length (`LIMIT` above 2048 bytes, `READER_LOCALIZATION_MAX_OUTPUT_BYTES`)
8. capacity (`CAPACITY`)

**Buffer rule.** Every refusal except `CAPACITY` leaves the output buffer and the
measurement byte-for-byte untouched. `CAPACITY` is the one failure that reports:
`out_measurement.bytes` is filled with the required size so the caller can
retry, and `out_text` keeps its previous bytes. `out_text == NULL` is
`ARGUMENT` whatever the capacity; a successful call writes the whole string plus
NUL and leaves bytes beyond the NUL as they were. A refused call can never leave
a partially written string, because the length is computed and validated before
the first output byte is stored.

### Data is data

Titles, author names, paths, notes and account labels are copied verbatim in one
pass. A value containing `{0}`, `{1}`, `%s`, `%n`, `$1`, `{{0}}`, quotes, tabs,
newlines, bidi controls, combining marks, CJK or emoji is emitted byte for byte
and is never re-scanned, re-substituted, truncated or interpreted as markup.
Templates come only from the shipped catalog, so a caller cannot inject a
template. Values must be well-formed UTF-8; malformed sequences are refused
(`VALUE_INVALID`) rather than repaired or copied through, because a broken byte
sequence in a native UI string is a defect the caller must fix.

### Locale

`reader_localization_parse_locale` accepts, case-insensitively, `zh`, `zh-CN`,
`zh_CN`, `zh-Hans`, `zh-Hans-CN`, `zh_Hans`, `zh_Hans_CN`, `en`, `en-US`,
`en_US`. Everything else, including `de-DE`, `zh-CN-x-bogus` and `en-GB`, is
`UNKNOWN_LOCALE`; there is no silent default locale.

The library never calls `setlocale`, reads `LC_*`/`LANG`, `NSLocale` or a
platform locale API, and never inspects the process locale. Numbers are rendered
as plain ASCII digits without grouping, so the same call produces the same bytes
under `de_DE.UTF-8` or `ja_JP.UTF-8` (checked in the installed consumer).

**Fallback.** The requested row wins. A missing requested row falls back to
en-US with `fallback = 1` and `OK`. A missing en-US row is `UNKNOWN_MESSAGE`,
never an empty string. The shipped catalog has no missing row in either locale,
so fallback is only reachable through the test-hook build.

### Memory, threads, cancellation, commit boundary

- Ownership: ids, groups, kinds and templates are static storage owned by the
  library for the process lifetime; never freed, never modified. Parameters are
  borrowed for one call. Output is caller-owned.
- Threads: the production build has no mutable global state, so every entry
  point is reentrant and safe from any thread with distinct output buffers. The
  installed C++ consumer renders from four threads and compares every byte with
  a single-threaded reference plus the digest.
- Cancellation: there is no cancellation point and none is needed. Every call is
  pure, non-blocking, allocation-free, I/O-free and lock-free, bounded by 8
  values of at most 1024 bytes and two passes over a template of at most 256
  bytes.
- Commit boundary: the library owns no durable state — no file, no product
  schema table, no SDK table, no wire entity, no sidecar. Nothing is
  transactional with the product database; the only write is the caller's
  output buffer after full validation.

### Resource digest

`reader_localization_catalog_digest(char out[65])` returns lowercase SHA-256 over
the canonical serialization of the **shipped** catalog:

```
reader-localization-catalog<TAB>1<LF>
per message, ascending byte order of id:
  M<TAB><id><TAB><group><TAB><kinds><LF>
then per message, zh-CN before en-US (absent rows omitted):
  T<TAB><id><TAB><locale><TAB><template><LF>
```

Templates never contain a tab or a line break. The digest covers ids, groups,
slot layouts and both locales, ignores test hooks and process state, and is
byte-identical on Linux, Windows and macOS — the aggregation job refuses a run
where the three platforms disagree. `tests/reader_localization/localization_fixtures.py`
recomputes the same digest from the oracle table, so a resource edit that skips
one of the two tables fails `catalog-digest-cross-implementation`.

## Host wiring example (root's step, not done here)

```cmake
find_package(EXReaderLocalization 0.1.0 EXACT CONFIG REQUIRED)
add_executable(reader_host ...)
target_link_libraries(reader_host PRIVATE EXReaderLocalization::reader_localization)
```

```c
reader_localization_context context;
reader_localization_param params[1];
reader_localization_measurement measurement;
char label[256];

memset(&context, 0, sizeof(context));
context.struct_size = (uint32_t)sizeof(context);
if (reader_localization_open(host_locale_tag, &context) != READER_LOCALIZATION_OK) {
  context.locale = READER_LOCALIZATION_LOCALE_EN_US;   /* explicit host choice */
}
params[0].struct_size = (uint32_t)sizeof(params[0]);
params[0].kind = READER_LOCALIZATION_PARAM_INT;
params[0].string = NULL;
params[0].integer = book_count;
params[0].unsigned_integer = 0;
if (reader_localization_format(&context, "reader.shelf.count", params, 1, label, sizeof(label),
                               &measurement) != READER_LOCALIZATION_OK) {
  /* keep the host's own string; never render a half-filled buffer */
}
```

The host keeps its existing strings and its existing accessibility names. This
package supplies only new surfaces and the strict renderer; adopting it is a
per-surface decision root makes when it wires the four native hosts.

## Cloud acceptance

`.github/workflows/reader-localization.yml` runs three jobs plus one aggregation
job, all on GitHub Actions; nothing in this package is built, tested, generated
or parsed locally.

1. `Pin source, fixed start, protected SDK, schema and path ownership`:
   `HEAD == GITHUB_SHA`, the fixed start is an ancestor, `src include cmake
   CMakeLists.txt tests/fixtures bindings` and both protected workflows are
   byte-identical to SDK `9854061be331fe603a1822d9b2b36ee357154927`,
   `apps/reader/store/001_catalog.sql` is unchanged from the fixed start, and
   every changed path is inside the J20 whitelist.
2. Windows enters the MSVC environment; all three platforms build and install
   the package with CMake+Ninja, then compile the C and C++ consumers from the
   installed prefix only (`CMAKE_PREFIX_PATH`), plus the test-hook worker from
   source.
3. `make_localization_fixtures.py` freezes the expectations and the fixture
   tables **before** any consumer renders; `check_localization.py` then runs the
   20 named cases below.
4. The aggregation job downloads all three ZIPs, verifies artifact id, name,
   non-empty byte count, `sha256` digest, expiry and `head_sha`, re-reads
   `localization-evidence/result.json` out of the archive, and requires the three
   platform case sets, the case verdicts and the catalog digests to be identical.

Named cases (identical on every platform):

`installed-package-layout`, `installed-c-consumer`, `installed-cpp-consumer`,
`installed-consumer-binding`, `abi-and-version`, `limits-match-header`,
`hook-worker-manifest-parity`,
`catalog-coverage-zh-en`, `catalog-template-parity`,
`catalog-digest-cross-implementation`, `format-matrix-zh`, `format-matrix-en`,
`refusal-arity-and-kind`, `refusal-malformed-utf8`, `value-limit-boundary`,
`capacity-atomicity`, `output-limit`, `fallback-missing-translation`,
`missing-base-translation`, `catalog-corruption-refusal`,
`no-internal-diagnostics`.

Reproduce: push to `codex/reader-localization` (or dispatch the workflow), then
read the three `reader-localization-<platform>-<run>-<attempt>` artifacts and the
`reader-localization-summary-<run>-<attempt>` artifact. The summary JSON is the
same-source record; `docs/validation/reader-localization.json` records the
accepted run.

## Limits and uncovered scope

Pinned in the header and checked by `limits-match-header`:

| limit | value |
| --- | --- |
| message id bytes | 96 |
| slots per message | 8 |
| string value bytes | 1024 |
| rendered text bytes (excluding NUL) | 2048 |

Not claimed by this package:

- host wiring, host UI, host string migration or any host-side accessibility
  tree change (root owns the four native hosts);
- plural rules beyond the shipped wordings, additional locales, locale
  negotiation, translation memory, RTL layout mirroring or bidi isolation (the
  renderer passes bidi controls through unchanged; isolation stays the host's
  job);
- performance, memory or CPU budgets beyond the stated constant bounds;
- real-device, simulator, audio or text-to-speech behaviour — this package has
  no runtime surface beyond string rendering;
- any change to the SDK, the product schema, the revision wire, the reading
  anchor, the protected trees or the six SDK release packages.

## Runs and retained failures

Accepted run: **40127576739 / attempt 1**, tested source
`6e7ba4b64fc3a05fbd6a960e81df1bb7ef58d42c`, 21/21 named checks green on
Linux, Windows and macOS, identical case sets, one identical catalog digest
`41040fcc8a162eeecea1415dbee3710f708d3f0ffef0071aedb8bd291b5f4285`, and the
installed library, both installed consumers, the hook worker and the frozen
fixtures bound by `sha256` on each platform. Every artifact id, byte count,
`sha256`, expiry date and binary digest is in
`docs/validation/reader-localization.json`.

An earlier accepted run (40126739701, source `aafb8fd0`) covered the first 20
checks; it is recorded as superseded because it does not carry the binary
digests, and its artifacts stay available until 2027-01-22.

Earlier failed runs on this branch are kept as evidence, with their jobs,
artifacts, digests and the exact case that failed. None of them was repaired by
editing an expectation:

| run | source | failed cases | cause |
| --- | --- | --- | --- |
| 40124943805 | 147e509f | installed consumers, both format matrices, all refusal cases, fallback, corruption | `parse_locale` rejected the `-` separator, so no tag resolved; the Windows job also failed before configuring, so it produced no artifact |
| 40125641428 | a6ac730d | installed C++ consumer, matrices, refusal cases, fallback | fixture hex decoding ran past the token separator, the C++ consumer passed pointers into destroyed temporaries, MSVC C4310 on a `char` cast, and the fallback fixture used a different argument than its expectation |
| 40126019743 | 67ced03d | refusal-arity-and-kind, refusal-malformed-utf8, value-limit-boundary, capacity-atomicity, output-limit | the fixture buffer was exactly the value limit, so an over-long value could not reach the library and the fixture run aborted |
| 40126404054 | ae8a9caa | capacity-atomicity | the exact-capacity fixture was sized in characters instead of UTF-8 bytes, so CJK rows were one byte short |

The two later commits on the branch after `aafb8fd0` are documentation-only and
carry `[skip ci]`; the tested source is `aafb8fd0`, not the documentation HEAD.
