# Android SDK 3.42 F07 closure capture — source-only packet

This is **unexecuted source preparation**, not an F07 acceptance or progress
increment. No build, syntax check, test, fixture, APK/ELF/artifact parsing, remote
write or Actions launch has been performed for this packet.

## Source and exact scope

- Workspace: `/workspace/shared/exreader-android-f07-capture-20261028`.
- Common base: `8f8acf3234cba747165f001c0c96efe1b911e6ad`.
- Proposed exclusive branch: `codex/android-f07-capture-20261028`.
- Only five added paths:
  1. `tests/reader_android_f07_capture_20261028/contract.py`
  2. `tests/reader_android_f07_capture_20261028/run.py`
  3. `tests/reader_android_f07_capture_20261028/test_contract.py`
  4. `.github/workflows/android-f07-capture-20261028.yml`
  5. this document.

SDK, production owners, Android/Gradle/native source, old tests/workflows,
assertions and budgets are untouched. No source commit or feature branch push
is authorized by this document. Remote publication and its automatic push run
need package-specific approval immediately beforehand; do not retry through
another route or add an overlapping manual dispatch.

## Why new evidence is needed

Original [F06 run 40678657371/1](https://github.com/NoGod3524/EXReader/actions/runs/40678657371)
proved six common-source development package identities. The independent F07
audit source package records that the Android upload does not retain installed
module archives/public headers/exports and final SDK-host/product link maps.
An APK dynamic import list cannot prove absence of private imports resolved
inside static modules. New capture cannot retroactively repair that original
run; it must earn new same-SHA/run/attempt F06 identity and separately undergo
F07 closure review.

## Reuse the actual common producer, not a legacy reconstruction

The proposed workflow invokes unchanged
`python3 tests/android_sdk342_package/run.py build` from the common base.
That is the producer used by `android-sdk342-package.yml` in the original common
run. Its existing exact 3.42 SDK selection and three Gradle version selections
remain exactly as committed. It selects five original composition build steps;
the legacy text in an old step name is not treated as the actual SDK version.
No new SDK-version substitution, Gradle init script or host CMake override is
introduced here. The capture reads the actual installed 3.42 headers and caches.

The old producer's branch-scope guard rejects additive packages by design.
The new guard replaces **only that admission scope** with exactly these five
added paths and byte-identical old trees/producer/tests. It retains the frozen
SDK comparison to `8357eafa28423a7ab93ba08b823af80f01ad1505` and creates the
empty `build/f06` output directory originally initialized by that guard.
It does not monkeypatch or suppress any builder assertion.

The original F06 `identity.py android` runs unchanged: actual API34 x86_64
install, APK pull-back byte identity, launch and live process observation.
Original Java17/Gradle8.9/NDK27.0.12077973/API34 image/emulator options and
**210-minute job ceiling** are retained. The ceiling is not a completion ETA.
This does not run or grant the complete Android behavioral suites omitted by
the original F06 producer.

## Proposed retained evidence

All processing below happens only in GitHub Actions, after actual F06 succeeds:

- Actual `build/wave3/sdk-stage` and `build/wave3/stage`: installed SDK/optional
  and product archives, shared libraries, public headers, CMake package exports
  and versions. Installed SDK header inventory and bytes must equal common-source
  public headers; symbolic links retain link metadata and resolved byte hashes.
- Actual producer scripts/logs, CMake cache/install manifests, Ninja graphs,
  `ninja -t commands` and `ninja -t compdb` output from the recorded Ninja tool.
  Those inspection subcommands do not rebuild. Named local link inputs and
  available response files are retained; unavailable ones fail capture.
- Exact SDK/shared and Android host/product link outputs, original
  `sdk-host-link.map` and `product-link.map`, and named archive/object inputs.
  NDK tools, version and explicit external input identities are recorded.
- APK bytes from producer, final Gradle output, F06 extraction and actual installed
  pull-back must match. APK-native x86_64 ELF images are retained and inspected
  with the actual pinned NDK `llvm-readelf`/`llvm-nm`.
- Stripped APK host/product images must match all allocated section bytes plus
  PT_LOAD virtual layout of actual map-bound link outputs. This is deliberately
  distinct from whole-file equality; both raw hashes remain in evidence.
  SDK-native APK images must match actual installed SDK images. Any pre-install
  link-output difference is reported as an unresolved install-transform gap,
  never silently equated or normalized away.
- Source SHA, run ID, attempt, every copied byte hash, command argv/cwd/exit and
  outputs are retained. `capture_complete` is an evidence-collection result;
  `full_f07_accepted` is always false in this collector.

The source includes six additive parser tests and a seventh source-settings
test for unchanged producer/toolchain/emulator/budget selection. They construct
synthetic fixture bytes only inside Actions. They are not original product
acceptance tests.

## Remaining verification / first-run risks

No syntax/runtime/platform result exists yet. Independent source review on
2026-10-28 at 21:32 UTC cleared this as **capture only**, retaining the separate
authentication and F07 audit gaps. Actual Ninja/AGP layouts, archive symbol output and ELF strip
behavior may expose collector assumptions. Fix only this additive packet after
retaining the failed evidence; never change original flags/assertions to pass.

A later independent audit must rehash the retained bytes, replay native
inspection, resolve exact installed CMake export/archive ownership, determine
public API declarations and cross-package private/weak/C++ helper imports, and
prove the final ELF dependency graph's single SDK/product-SQLite ownership.
The collector does not infer these from producer booleans or successful linking.
System `-l` inputs and implicit toolchain defaults need independent resolution
against recorded commands and the pinned NDK. Any SDK install-transform gap
also remains an explicit blocker to a complete lineage claim.

Only Android API34 x86_64 emulator/debug output is in scope. Six-platform F07,
full behavioral regression, physical devices, signing, deployment and release
remain separate. No formal 108-item count changes from this source packet.
