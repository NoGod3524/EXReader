# Explicit pure raw capture candidate for Windows owner review

This is a proposed, unapplied app-module additive patch. It supersedes the
earlier 0.3.0 package-version suggestion in WINDOWS-RAW-CODEC.md. The coordinator
requested a separate capability with the old public header bytes and existing
0.1.0/0.2.0 behavior preserved.

| Boundary | Exact proposal |
| --- | --- |
| New header | `apps/reader/reading-state/include/reader_reading_state_capture_raw_candidate.h` |
| Capability version | `READER_RS_PURE_CAPTURE_CANDIDATE_VERSION "0.1.0"` |
| Opt-in | `EXR_READER_PURE_CAPTURE_CANDIDATE=OFF` by default; ON requires `EXR_READER_SELECTOR_BYTES_CANDIDATE=ON` |
| Installed target | Existing `EXReaderReadingState::reader_reading_state_codec`; no second archive/provider |
| Symbol linkage | Public C symbol, declared only by the new candidate header |
| Source body | One conditional wrapper in `src/reading_state.cpp`, reusing its existing `encode(..., true)` |
| Other changed source | Only reading-state `CMakeLists.txt` for explicit flag, condition, compile definition and new header installation |
| Unchanged | Old public header bytes, package versions 0.1/0.2, old API bodies, internal command-only entry, all SDK files and seven-module guards |

```c
reader_rs_status reader_rs_encode_capture_raw_candidate(
  reader_revisions *store,
  const reader_rs_envelope *envelope,
  const reader_rs_capture *capture,
  unsigned anchor_version,
  size_t part,
  char **wire,
  size_t *bytes,
  reader_rs_error *error);
```

The caller supplies actual anchor version 1/2/3; the wrapper rejects any other
value and restricts 3 to fixed_page. It never relabels a v1/v2 capture. The
existing encoder retains all representability, size, nullable-selector and
raw-store validation. It allocates an owned copy released with `reader_rs_free`,
clears output pointer/count on failure, and inserts nothing into revision,
history, head, observation or outbox tables. The host separately calls its
existing public jump-history commit after successful encoding.

The new header rejects consumption without both explicit capability macros.
The existing installed codec target propagates the new macro only when this
capability is built; an old install therefore cannot silently claim it. The
candidate header/version and actual symbol still need same-source installation
and consumer validation before adoption.

The reviewable diff is `pure-capture-candidate.patch` beside this document. It is
**not applied** to the protected reading-state files in the core combination.
It adds one header and guarded code in two files. No old guard or package
EXACT-version requirement is edited. Root must retain it as an independent
capability source, and the Windows owner must remove its private declaration
and include/call this public header only after adoption.

Required independent acceptance is bounded: C and C++ consumers through the
installed target, exact v1/v2 reflow/EPUB capture preservation and actual history
resolve, v3 fixed-page raw bytes including nullable/NUL selectors, wrong
version/mode/store refusal, before/after table and database no-write checks, and
old option-OFF installed headers/API behavior. These are not executed by this
proposal and are not credited to the two core complete rounds.
