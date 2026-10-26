# Core handoff: integrated candidate, acceptance held

Latest update: `STATUS.md` records the independently accepted public pure
capture capability, accepted S18 strict bindings, and the remaining S19 UUID
caller repair. The initial handoff below is retained as historical context.

Branch `codex/team24-core` starts at `d263ce5228838ac90c0a0dc13a5193d4a7739681`.
Code/proposal HEAD is `5ddd1c9bbd023d6b42a3475107c70cc33b1353d6`; subsequent
handoff-only documentation does not change its implementation. Worktree:
`C:/Users/Oscar/exreader-team24-20261026/core`.

## Urgent Windows public pure-capture contract

Review `PURE-CAPTURE-CANDIDATE.md` and `pure-capture-candidate.patch`. The exact
symbol is `reader_rs_encode_capture_raw_candidate(store, envelope, capture,
anchor_version, part, wire, bytes, error)`, public C linkage in the existing
`EXReaderReadingState::reader_reading_state_codec` target. A new separate
candidate header has capability version 0.1.0; an OFF-by-default
`EXR_READER_PURE_CAPTURE_CANDIDATE` option requires the existing raw option.

The unapplied patch changes only a new header, conditional implementation
wrapper and conditional CMake capability/install plumbing. It preserves the
old public header bytes, package versions, existing API bodies and SDK. It
reuses `encode(..., true)` without a second serializer, explicitly retains
anchor 1/2 and restricts 3 to fixed_page. It never inserts a revision/outbox.
This candidate needs root review and independent behavior acceptance; Windows
must not keep declaring the internal command-only symbol.

## Actual verification and failures

| Kind | Source | Run/attempt | Result |
| --- | --- | --- | --- |
| New complete round 1 | `91cc13f3c3e31817d7263c7f4be527ac6b185519` | `40276177912/1` | Failed source object reachability; no business producer |
| Bounded source-only repair | `6e2d4b09e8fcfb78acbd9afa3f246d6930fa371f` | `40276347409/1` | Passed source and original receipt ZIP binding only |
| New complete round 2 | `6e2d4b09e8fcfb78acbd9afa3f246d6930fa371f` | `40276498769/1` | Failed; three concrete caller/judge roots below |
| Read-only failed ZIP/patch structure | `5ddd1c9bbd023d6b42a3475107c70cc33b1353d6` | `40277596634/1` | Passed inspection and unapplied patch applicability only; accepted=false |

The two complete-round allowance is exhausted; no third complete run or
physical-device/screen-reader acceptance is claimed. The readonly run did not
build or execute programs. Caller repairs in 5ddd1c9b have not been revalidated.

All three S18 original 149+149+149 and raw/default 162/21 suites ran successfully
on the round-2 source, but our generated-expression assertion named
`reader_reading_state` instead of the actual `reader_reading_state_codec`.
The graph stopped before the second graph/program and strict correctly refused
failed producers, so original 9+3+3 mutation acceptance is still pending.

Linux/macOS S19 actually built/linked the shared DSO and host, passed six mixed
graph refusals, then returned history step 44. The caller wrongly supplied a
nonempty range for v2 progress, which must be a point. Windows actually built
`EXReaderProduct.exe`, then its private-store negative hit Ninja's 260-character
FetchContent path limit; GUI runtime was not reached. Exact codec-owner
assertions, two true progress points with preserved diagnostics and a short
FetchContent base are now repaired without changing protected modules.

## Original ZIPs and actual program identities

[Read-only inspection artifact](https://github.com/NoGod3524/EXReader/actions/runs/40277596634/artifacts/12630718235)
contains all nine original round-2 API ZIPs and `inspection.json`, with their
API size/digest/expiry and recomputed bytes. Its size is 134786645;
SHA-256 `2d26dcf431f36e6dc47469832fb6d697c699e5a780eca453414ad1bb5a02f5d0`;
expires `2027-01-24T06:03:12Z`.

| Actual program from failed round 2 | Bytes | SHA-256 |
| --- | ---: | --- |
| Windows `EXReaderProduct.exe` | 7758848 | `c7d95011618cc92449f58ba2c505944b13be10a8812063c090738d36d74489a4` |
| Linux `reader-host-probe` | 36432 | `01cdbe01ccfbc025d27bd4bc9cabe8d8f21d9209a5fd8efe459bb526e0ad3e1f` |
| macOS `reader-host-probe` | 57456 | `37705dffbdc2925387316e309a0357b104a9f013471632b6c0ed0104d0d9b4da` |

The Windows original partial ZIP is artifact `12630821598`, size 8022139,
SHA-256 `22c68e656e6a3560c8cb820cd4e1c9eff662192ea69d9082516e4179bea26190`.
It is a failed partial artifact, not an accepted portable package; its EXE can
use the frozen repository font via the existing `--font` option. The source's
successful packaging path includes Reader.otf, relative shared-loader paths and
SDK aliases, but was not reached in this failed run.

Original S18/S19 histories and SDK adoption evidence remain in their source
documents. No default branch, PR, tag or Release was created. SDK, old judges,
seven protected modules, cloud import, WebDAV and sideload retain their declared
exact boundaries. Minimum implementation merge boundary is the two SDK blobs,
the restored S18 subtree with binding repairs, restored S19 host-link paths,
eight macro-gated lines in the native drive entry and the combined workflow.
The pure-capture patch is a separate, unapplied proposal, not part of that
implemented boundary. This is one core line of the six-platform reader.
