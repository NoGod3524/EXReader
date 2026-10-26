# Wave3 S18: joint default/raw install acceptance

The original full business replay passed source `4af92ba0`, run `40247961052/1`.
Its SDK binding gaps and generic mutations do not grant the stricter S16 binding
acceptance implemented here. The team24 entry runs only the focused S16 producer
and installed-path checks against the SDK adoption candidate `9d3a3f8b`.

`runtime.py --s16-only` and `strict.py --s16-only` keep
`full_joint_runtime_accepted=false`. The remaining four business modules retain
their original source/run identity and are not counted as this source's results.

## What runs (Actions only)

`runtime.py` installs, on Windows, Linux and macOS from the same source:

1. the SDK 3.41.0 adoption candidate (`9d3a3f8b`) and, in full scope only, the
   frozen SDK 3.40.0 (`9854061b`);
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
python tests/reader_wave3_s18/strict.py            # three runtime ZIPs, hashes, numbers, original 9+3+3 controls
python tests/reader_wave3_s18/runtime.py --s16-only # focused actual S16 business and installed paths
python tests/reader_wave3_s18/strict.py --s16-only  # same-source/run/attempt focused independent binding
```

Every phase is isolated: one failing phase is recorded and the independent
phases still produce their real evidence, so no result is ever inferred from a
previous run.

The imported-path proof resolves the known reading-state TARGET_PROPERTY through
the real SDK imported target, preserves that expression's source in each graph's
`genexpr-origins.txt`, and rejects unresolved expressions instead of skipping
them. Four real CMake configure controls exercise the accepted indirection,
foreign resolved prefix, unknown CONFIG expression, and a reference cycle.
