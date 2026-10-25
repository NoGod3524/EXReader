# HANDOFF-RESULT-S15

## Identity

| Item | Value |
| --- | --- |
| Package | S15 — existing original export on the approved SDK 3.41 install graph |
| Branch | `codex/reader-next-s15` |
| Fixed start | `e67d87cbeabb2457e0852f681ef0b27b2c0da4d8` |
| Reused module (byte-identical source/header) | `25cd7b4b15d952e3f7a10e39ed80ae16a3d9a3ee` |
| Approved SDK 3.41 | `edddc463c06ed5731195cdb8f06b2df6dff7699e` |
| Frozen SDK 3.40 | `9854061be331fe603a1822d9b2b36ee357154927` |
| Tested source | `c1737e2a599d7d2cfc6d87569ab5e65093206a54` |
| Tested tree | `71bc03d1af030326c8d2645f00caf28ec4df9aa8` |
| Workflow | `.github/workflows/reader-next-s15.yml` |
| Run / attempt | [40227960455 / 1](https://github.com/NoGod3524/EXReader/actions/runs/40227960455) — **success** |

This round used three full CI rounds; all three are retained below.

## Owned paths (only these changed)

`apps/reader/original-export/` (module copied from the fixed commit, plus install
configuration and a README), `tests/reader_next_s15/`,
`.github/workflows/reader-next-s15.yml`, `docs/reader-next-s15/`,
`HANDOFF-RESULT-S15.md`. Nothing else in the tree differs from the fixed start:
every job runs
`git diff --exit-code <start> HEAD -- apps/reader/store apps/reader/revisions apps/reader/commands extras/sideload apps/reader/local-downloads apps/reader/session`
and the ownership allow-list over `git diff --name-only <start> HEAD`, and the
evidence job re-checks the SDK tree against the approved commit.

## What changed and what did not

* `apps/reader/original-export/include/` and `src/` are byte-identical to
  `25cd7b4b`, so the public C ABI, item layout, chunked read, staging,
  publication and cancellation behavior are unchanged; every job proves it with
  `git diff --exit-code 25cd7b4b HEAD -- apps/reader/original-export/include apps/reader/original-export/src`.
* `CMakeLists.txt` now takes `EXR_SDK_VERSION` (default `3.40.0`, only
  `3.40.0`/`3.41.0` accepted), `-DEXR_SDK=<prefix>`, and the installed config
  records `find_dependency(EXReader @EXR_SDK_VERSION@ EXACT ...)`.
* Approved SDK 3.41 differs from 3.40 only in the version macros, the added
  `exr_render_page_background` entry point and the canvas-fill refactor;
  `exr_library_source`, `exr_library_books` and the library header are
  untouched, so no source change was needed — only the explicit install graph.
* Originals still come only from the public SDK chunked source. The unchanged
  `extras/sideload` exporter is built and used as an independent byte oracle.

## Jobs and artifacts (same source, run 40227960455, attempt 1)

| Job | ID | Result |
| --- | --- | --- |
| original export 3.41 (ubuntu-22.04) | 121273316640 | success, 44 named checks |
| original export 3.41 (windows-2022) | 121273316691 | success, 44 named checks |
| original export 3.41 (macos-15) | 121273316467 | success, 44 named checks |
| frozen 3.40 default graph (ubuntu-22.04) | 121273316693 | success, 6 named checks |
| strict S15 evidence | 121274056739 | success |

| Artifact | ID | bytes | SHA-256 | expires |
| --- | --- | --- | --- | --- |
| reader-next-s15-Linux-40227960455-1 | 12611617179 | 8489753 | `ee5a5d22d81db7694d3360189d542d4c88c8b6e58eaccb4523b8d079befaaeb4` | 2027-01-23T19:50:49Z |
| reader-next-s15-Windows-40227960455-1 | 12612585832 | 7061984 | `f14555afe5e03287e8e95718bea0d3daa53958a18f8966ceedeee2a97af6a664` | 2027-01-23T19:50:49Z |
| reader-next-s15-macOS-40227960455-1 | 12612376433 | 7429078 | `6336225ba1a238c32eecf64ba49fc8d0debe95725593cacee94a66f5ce0a5b25` | 2027-01-23T19:50:49Z |
| reader-next-s15-frozen-340-40227960455-1 | 12612175886 | 4189173 | `2a8c1135d869368955d64825ad2c98df1c380bc138a49ab864998bdfe9526820` | 2027-01-23T19:50:49Z |
| reader-next-s15-evidence-40227960455-1 | 12612501126 | 1705 | `bbf485e1f0a8adb76fdbaf651f9dafa066f9074fdb7da296a4f8b7191acd79c9` | 2027-01-23T19:50:49Z (terminal evidence ZIP, API metadata only) |

Downloaded ZIP length and SHA-256 of the four producer artifacts were recomputed
in the evidence job and matched the API digest; the static module archive inside
each ZIP was bound to the installed `s15-stage/lib/` member.

## Program identities

| Platform | probe | C consumer | module archive |
| --- | --- | --- | --- |
| Linux | `c234d85f539442c11496dab9eb42de39df365f7bc102420c25e8e8d8cca57e0d` (8770936 B) | `54db9672c0f5b4cceb94a7f56673842225997728890e52101fe597b1d4348883` (8484528 B) | `fab1986129057b6a8564867e1d17206fb1e322e62444bb84afdd695f6c61780a` (45384 B) |
| Windows | `9853ef2871568fd89bb12b099b13704f3f29a9401fdf8b79a0a848b5b6984a27` (6329856 B) | `a52de4e2fcdfe66de548f8753f726326ac29bf8749e9cd70bd25f5d4a3bf4b9c` (6054912 B) | `127865c8850c79850a3c6f4d8fa38934de47b14002f2a4da68da76a14e6f8fba` (352494 B) |
| macOS | `e64d9d6027709f30ee3bd5ff1f1dc6bcbffcb0a7ed6610407e92493cb5e63c1c` (7157768 B) | `ff7388a8f1dbb17dd01c53fa5e402330d658e77445d0e5a48ff07e3e198bd9cc` (6913832 B) | `1ddbcafcd77b45a6288a4b50b236fe443b2b49290b3b1d7be62dd32edfe63bf7` (30096 B) |

SDK identity in every 3.41 job: header `EXR_VERSION "3.41.0"`,
`EXR_ABI_VERSION 1`, `EXReaderConfig.cmake` `EXReader_VERSION "3.41.0"`, installed
module config pinning `EXReader 3.41.0 EXACT`. Frozen job identity:
`3.40.0`/ABI1 with the module config pinning `3.40.0`.

## Result detail

Per platform (44 named checks each, exact sets): `installed_c_abi`,
`installed_c_abi_real_export`, `approved_sdk_341_abi1`,
`sdk_default_pin_refused_by_341_install`, `sdk_unsupported_pin_refused`,
`consumer_without_exact_sdk_refused`, `mixed_sdk_graph_refused`,
`owner_lease_balanced`, `source_handles_released_before_reuse`,
`stream_source_byte_identity`, `nonstream_memory_byte_identity`,
`sideload_exporter_byte_identity`, `valid_unicode_destination`,
`batch_preflight_atomic`, `process_kill_after_commit_retry`,
`nine_format_byte_roundtrips`, `selected_unselected_isolation`,
`duplicate_same_bytes`, `same_title_distinct_bytes`,
`existing_conflict_no_overwrite`, `display_name_restricted`, `bad_utf8`,
`traversal_rejected`, `device_name_rejected`, `directory_alias_rejected`,
`target_alias_rejected`, `count_101_rejected`, `count_100_accepted`,
`per_book_limit`, `batch_limit`, `hard_limit`, `owner_refusal`,
`wrong_thread`, `callback_reentry`, `missing_source`,
`source_invalidated_mid_read`, `cancel_before_start`, `cancel_after_commit`,
`temporary_readback_verified`, `cleanup_receipt`,
`process_kill_reopen_retry`, `sdk_original_notes_progress_unchanged`,
`product_history_outbox_unchanged`, plus `posix_real_midstream_write_failure`
on Linux/macOS or `windows_actual_locked_cleanup_failure` on Windows.

Frozen job (6 checks): real 3.40 install identity, default pin accepted and
built, explicit `3.41.0` pin refused by that graph, installed C consumer links
and reports `3.40.0`/ABI1, a real TXT original exported byte-exactly, and a
re-export leaves the existing target untouched.

Verifier: 17 mutations rejected per platform (51 total) — wrong source, wrong
attempt, missing case, duplicate case, false success, wrong platform, wrong SDK
version, missing module identity, tampered probe, tampered module archive,
tampered original fixture, downgraded install-graph report, changed history
snapshot, duplicate JSON key, duplicate ZIP member, missing report, unsafe ZIP
path. Actual original/final bytes were bound to the frozen repository fixtures
for all nine formats, for the three streamed storage paths and for the sideload
oracle.

## Retained failures (not rewritten)

1. Run `40227126835` attempt 1, source `fd71d1d5`: all three matrix jobs failed
   in the mixed-SDK control with
   `TypeError: unsupported operand type(s) for +: 'PosixPath'/'WindowsPath' and 'str'`.
   The three other refusals and the relabelled 3.40 control had already passed
   in that run. Fixed by building the prefix list from both path strings.
2. Run `40227526450` attempt 1, source `a6671285`: the installed consumers
   compiled and every install-graph control refused as intended, but the C
   consumer exported from the database it had just created empty
   (`AssertionError('C ABI export: ')`). Fixed by seeding through the public SDK
   first and adding explicit status diagnostics to the C consumer.

The frozen-3.40 job passed in all three rounds.

## Unverified / boundaries

* Windows mid-stream disk-full/fsync fault injection stays **UNAVAILABLE**; only
  the real locked-temporary cleanup failure and publication-conflict failure are
  exercised there. No mock pass is claimed.
* On each platform the mixed-SDK negative relabels only the package metadata of
  the approved 3.41 install (shipped archives are hashed before and after and
  must be equal); the authentic frozen-3.40 refusal is the separate ubuntu job.
* Orphan discovery after process death remains host-owned through the
  STAGED/COPYING receipt; no unattended crash cleanup, share registration,
  six-device or power-loss claim is made.
* This module build is an **unadopted candidate**. It is not merged into a host,
  not wired to any selector or UI, does not touch the existing sideload exporter
  and does not adopt the SDK. Real acceptance and same-source verification stay
  with root.
* No real user library, account or credential is used anywhere; TLS verification
  is not disabled.

## Evidence files

`docs/reader-next-s15/README.md` (design, install graph, scope, limitations) and
`docs/reader-next-s15/evidence.json` (machine-readable identities above,
including retained failures and limitations). Code and recorded evidence are
separate commits; this handoff file is committed with `[skip ci]`.
