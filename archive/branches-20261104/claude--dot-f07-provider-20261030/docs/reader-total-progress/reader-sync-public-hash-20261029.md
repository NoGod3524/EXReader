# Same-source public boundaries and Android Sync public hash

This is the new, bounded integration packet: exactly 28 changed/added paths from
`cbaece83b65adb94115e861e519e0147e0e0786f`, including the unchanged 16-path hash
packet from `9413782c1f2b8109faec066606de7f28a32a1a95`, three Android Sync owner
edits, and nine new validation/documentation paths. `source_lock.json` pins both
predecessor trees and all 41 predecessor file hashes. A separate new union guard
admits the exact status/path delta and binds all 53 current named files. The old
25/16-path source guards and aggregate identities are explicitly excluded, not
monkeypatched or reported as passed. SDK, old suites and budgets remain unchanged.

## What changes

Only Android Sync replaces its private OPDS context/helper dependency with the
installed opaque `EXReaderOPDSHash::opds_sha256_stream` owner. A noncopyable,
nonmovable RAII adapter releases successful and partially failed allocations,
maps all non-OK stream statuses to the existing IO status, and checks exact
64-character lowercase/NUL output. The original 128 MiB limit, 65,536-byte chunks,
cancellation sites, original-file identity checks and non-Android crypto branches
remain. Raw ON and legacy OFF API versions and dependencies stay separate.

## One build and bounded execution

The exact explicit hash prefix is installed first, then passed only to that
producer's process/descendants through the existing canonical selector. Each
platform invokes its unchanged SDK342/F06 producer once. The old public native
tests, old hash probes, catalog/original-import behavior, and new Sync probes
reuse the actual SDK/product/module prefixes. No second SDK/product build is
performed for another suite. Standalone legacy owners and test-only controls are
separate fresh builds, as declared in the approved plan.

The first push is the sole configured run: protocol 15, Linux 150, Windows 100,
Android 210, macOS 110, paired iPhone/iPad producer 110, authentication 30 minutes:
**725 runner minutes maximum**. No workflow-dispatch trigger or repair round is
granted here. All execution, fixture generation and artifact parsing is Actions
only; source review does not constitute a test result.

## Evidence gates

- Actual install manifests and generated imported target paths select the exact
  hash/importer and Android Sync archives, with source-equal installed public
  hash headers and the exported private `LINK_ONLY` public hash dependency.
- Actual build/archive equality (the adopted strict first-BSD-index timestamp
  exception only on macOS/simulator), archive member bytes, linked compilation
  object, source edge and current dependency rows are joined. Consumers may not
  retain the old private OPDS/selector/header or OriginalExport implementation.
- Installed/relocated hash probes and both normal OPDS/Revisions coexistence link
  orders bind one actual final command, map, response closure and defining member.
  Complete original and relocated hash/product prefix inventories remain equal.
- Android RAW ON/OFF installed probes force actual Sync and hash linkage. The
  actual product `.so` separately binds its alias, final driver, map, image,
  installed Sync/hash defining members and final symbol addresses. A test probe
  is never relabeled as that product image.
- Android executes an exact-production-source digest adapter and unchanged stream
  internal fixture on the already provisioned emulator. It tests vectors, padding
  and chunk boundaries, overflow/nonmutation, null/final-twice cases, allocation,
  failed-return-with-owner, update/final/malformed-output errors and exact cleanup.
  Remote SHA256 and actual executable command records bind each runtime output.
- Package rejection controls include missing, foreign, cached, pre-created,
  redirected, conflicting, mutated, config-injected and wrong-ABI dependencies.
  Coherent actual-evidence mutations must fail at named semantic guards, then
  restore all original bytes; they are independently repeated by authentication.
- The Linux authenticator checks exact same-source/run/attempt successful jobs,
  original upload ID/size/digest/time, safe archive inventory, all retained hashes,
  old delivered F06 entry identity, old public archive comparisons and all six
  native retained-wire parity. It replays the new contract and mutations without
  executing any artifact binary. JSON summary is distinct from original evidence.

## Acceptance is deliberately narrow

`combined_named_boundaries`, `sync_public_link_boundary`,
`original_behavior_checks` and `original_uploads_verified` become true only after
all corresponding gates pass on this common source. Earlier successful source
trees are immutable prerequisites, not new same-source evidence.

Android's adapter and argument probes are **not** installed Sync/WebDAV hash-path
runtime. That transport requires a registered JavaVM/class and an actual JNI
scenario with the original account-session prerequisites; no fake `__ANDROID__`
or host TLS substitute is accepted. iPhone/iPad are two simulator form factors,
not a physical iOS device or the predecessor's device-target link lane.
`original_behavior_checks` names the reused public/selector/C06/F06, Linux GUI,
desktop catalog/original-import and hash-control suites only. The unchanged
`reader_sync/check_sync.py` and resilience/account-session network suites remain
unrun prerequisites; that flag does not grant original installed Sync behavior.

Full F07, all-module/source/private-import closure, all delivered image/provider
closure, original proprietary Windows MSVC/SDK/CRT/DLL provenance and whole-product
runtime remain false/separate. The proposed additive full-F07 collector is not
implemented by these 28 paths. No formal-108 item is granted by packet creation.

Status: source implementation under independent review; no new Actions result
is asserted in this document. Preserve all predecessor successes and failures.
