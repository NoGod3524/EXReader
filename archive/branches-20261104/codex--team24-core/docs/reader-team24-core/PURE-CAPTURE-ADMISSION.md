# Separate public pure capture admission

Production source `a911cd0e8405a362dae1bb489190de02c4c81d51` on
`codex/team24-core-pure-capture` has passed the installed capability gate. Its
sole parent is core `c05a4c2c1782872c943b4179c55529bb343b3fbe` and it changes
exactly these three production blobs:

| Path inside apps/reader/reading-state | Blob |
| --- | --- |
| CMakeLists.txt | `2b513deeb2681eb2e0c674fe447ddfee83cb3994` |
| include/reader_reading_state_capture_raw_candidate.h | `0cce3515dbcbed3c6b49356e1d6dc137b5a31aaa` |
| src/reading_state.cpp | `25de29dd59828371d7c35dc8a6295b9d74bc738d` |

Actual acceptance source `347165fe601f1bdb0cd3bb1da4c672f696195a4e`,
[40348964690/1](https://github.com/NoGod3524/EXReader/actions/runs/40348964690),
passed all three platform producers and original API ZIP/program binding. Six
actual installed C/C++ programs per platform covered default 0.1.0, raw 0.2.0
pure OFF and raw 0.2.0 pure ON; v1/v2 real TXT/EPUB capture, exact legacy wire
and resolve; v3 fixed NUL and nullable/empty selectors; output-clearing refusals;
no revision/history/outbox row writes; old public header equality; and both
capability macros zero/undefined. Prior focused failures `40279580785/1` and
`40279921298/1` remain failures for their respective sources.

[Strict original ZIP/program evidence](https://github.com/NoGod3524/EXReader/actions/runs/40348964690/artifacts/12662907379):
69132640 bytes, SHA-256
`bdf5dfc7110fb2d25c68ab0eda71d7d456198d35e18de3d5b48d6703d83a2ee9`.
Full implementation/adoption record is in the candidate branch at commit
`13ad401d` (`docs/reader-team24-core/PURE-CAPTURE-IMPLEMENTATION.md`).

Windows should consume the exact candidate, enable the existing raw option and
`EXR_READER_PURE_CAPTURE_CANDIDATE=ON`, include the new public header and link
the existing installed codec target. The header requires both macros defined
and equal to 1. The public function is
`reader_rs_encode_capture_raw_candidate(store, envelope, capture, version,
part, wire, bytes, error)`; retain real versions and remove the private extern.

The core branch keeps its original protected seven-module tree for its S18/S19
targeted round; this separate three-file capability is not silently merged into
that evidence source. Root authorized that additional targeted round after
this independent installed result, with all previous complete failures retained.
Neither admission grants GUI, physical-device, screen-reader or full-product
acceptance, and it introduces no SDK change or additional package.
