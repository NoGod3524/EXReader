# Wave3 S18: joint default/raw install acceptance

This package completes the shared-install acceptance that the reviewed
production-foundation runner did not reach. It is **not** a product BASE and does
not adopt anything.

## What runs (Actions only)

`runtime.py` installs, on Windows, Linux and macOS from the same source:

1. the approved SDK 3.41.0 (`edddc463`) and the frozen SDK 3.40.0 (`9854061b`);
2. the unchanged product catalog, WebDAV and sideload packages;
3. two complete optional-package families into separate prefixes — the default
   0.1.0 family and the explicit raw 0.2.0 family (revisions, reading-state,
   commands, sync, session, annotation-export, annotation-import, font-library,
   original-export, jump-history, sync-status-view);
4. one CMake graph per family that imports all five reviewed packages plus the
   one SDK provider, and proves every resolved imported path lives inside the
   declared family/shared/SDK prefix (`consumer/`).

It then replays the **unchanged original judges** of the reviewed waves:

| wave | reused judge | required numbers |
| --- | --- | --- |
| C06 | `tests/reader_next_c06/run.py` phases | baseline/default/raw legacy bytes equal, raw3 phase, certified Mac records (`found_checked=0`, ALREADY_VERIFIED, no FOUND) |
| S14 | `tests/reader_next_s14/run.py`, `preloaded.py`, `verify.py --self-test` | 60/61 named cases, 4 existing-target controls, 42 negative contracts |
| S15 | `check_install_graph.py`, `check_export.py`, `check_frozen_sdk.py`, `check_existing_targets.py` | 44 checks, frozen 3.40 graph, 16 target controls |
| S16 | `check_jump_history.py`, `check_raw.py` | 149 original on baseline/default/raw, raw 162, default 21, nine programs, three archives, default equals baseline |
| S17 | `check_status_view.py`, `check_raw_view.py` | 22 legacy checks, 20 raw checks, five mixed-install refusals |

The original branch/ownership guards of those waves are **not** executed (they
assert their own package-only diffs). `guard.py` here declares the fixed seed
`d263ce52` and the exact owned paths of this package, then proves every other
path in the pushed tree is byte-identical to the seed with eight real mutation
refusals and one positive control.

## Commands

```
python tests/reader_wave3_s18/guard.py preflight   # source receipt
python tests/reader_wave3_s18/runtime.py           # per-platform joint install and replay
python tests/reader_wave3_s18/guard.py strict      # same-attempt source receipt
python tests/reader_wave3_s18/strict.py            # three runtime ZIPs, hashes, numbers, 15 mutations
```

Every phase is isolated: one failing phase is recorded and the independent
phases still produce their real evidence, so no result is ever inferred from a
previous run.
