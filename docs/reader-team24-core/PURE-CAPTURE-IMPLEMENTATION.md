# Independent pure raw capture implementation

The additive production candidate is `a911cd0e8405a362dae1bb489190de02c4c81d51`, whose sole parent is `c05a4c2c1782872c943b4179c55529bb343b3fbe`. It changes exactly three reading-state files:

| File | Candidate blob |
| --- | --- |
| `CMakeLists.txt` | `2b513deeb2681eb2e0c674fe447ddfee83cb3994` |
| `include/reader_reading_state_capture_raw_candidate.h` | `0cce3515dbcbed3c6b49356e1d6dc137b5a31aaa` |
| `src/reading_state.cpp` | `25de29dd59828371d7c35dc8a6295b9d74bc738d` |

The existing public header remains byte-identical. Existing production lines are retained; the wrapper reuses `encode(..., raw_api=true)` and adds no archive/provider. The package families remain legacy `0.1.0` and raw `0.2.0`. The new capability has its separate header version `0.1.0`, with `EXR_READER_PURE_CAPTURE_CANDIDATE` default OFF and ON requiring the raw family. Both capability macros must equal `1` for the new header and implementation to be usable. An existing raw `0.2.0` installation without this explicit capability cannot establish the new API from its package version alone.

The caller supplies actual anchor version 1/2/3. Version 3 is restricted to fixed pages; existing representability, byte limits, selector presence and point-progress restrictions stay in the shared encoder. The wrapper clears supplied output pointer/count before refusing invalid versions or modes and returns successful owned bytes for release with `reader_rs_free`.

Source review follows `encode` through `validate(..., true)` to `reader_revision_validate_raw_v3`. The unchanged revision guard requires a raw store owned by the current worker and rejects legacy-store mixing. That validation path parses and hashes the candidate wire and fills output information; it does not call revision insertion, history commit, head selection, observation or outbox mutation. This source reading is not a measured database no-write result. The focused consumer must compare actual before/after database/table state and separately exercise success and refusal paths.

`tests/reader_pure_capture/source.py` is Actions-only. It requires `PURE_CAPTURE_SOURCE` to name the exact production candidate above, checks its sole base parent and three blob identities, verifies the checked-out event source descends from it, and freezes every other production and existing test/guard path. Only the new test directory, dedicated workflow and this implementation note may differ from the candidate. It independently compares SDK source/header/build/binding/fixture objects to `9d3a3f8bfa06c099ebba0d9e1ba613d276c3af09`. The original seven-module guards are not edited or executed as if they accepted this independent production delta.

Its source receipt explicitly grants no runtime, option-OFF, old `0.1.0`/`0.2.0` behavior, or no-write acceptance. Those require the parent's one focused Actions run with installed C/C++ consumers, actual reflow/EPUB history resolution and fixed-page raw selectors. The two earlier core complete rounds and their failures remain recorded separately; no result from another source is combined with this candidate. This independent candidate is not merged into the protected core baseline, and physical-device/screen-reader/product-wide acceptance is not claimed.

Focused gate attempt 1, source `0b814698b442dce98732587eb0824ed91f8a4380`,
run `40279580785/1`, failed in the C++ consumer build: shared C-style `{0}`
initializers require an explicit C++ zero-initializer for enum-first structs.
The shared test header now selects `{}` for C++ and `{0}` for C. This is a
consumer-only repair; all three production blobs and the capability source
above are unchanged. The failed run and artifacts remain separate from the
following focused-gate repair attempt; no SDK/format full acceptance is rerun.
