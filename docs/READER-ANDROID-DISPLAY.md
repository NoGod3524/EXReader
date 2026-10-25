# D05 Android reader display

Independent native Android AAR and installed-app probe. Public API, examples,
ownership, lifecycle/generation behavior and limits are in
[`extras/android-reader-display/README.md`](../extras/android-reader-display/README.md).
The existing Android host, frozen SDK, product schema and non-D05 tree are unchanged.

## Verified result — 2026-10-25

**API34 Window-property scope passed; full-product and physical-effect acceptance
are not granted.**

- Branch: `codex/dot-reader-android-display`.
- Fixed start: `a826a65c9c66e43620eff61b49cb79f941a3c953`.
- Frozen SDK: `9854061be331fe603a1822d9b2b36ee357154927`, 3.40 / ABI1 unchanged.
- Tested source: `bb6442cd6a8f9a16da853e4abd5d70451a291aa0`.
- Tested tree: `82c93c98fd8a1605eb7c3c1d1e358caab7d5a6ad`.
- Original module tree: `0215f0441e7dce8053209094af1f46f3fe4483af`.
- [Run 40171106759, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40171106759): completed **success**.
- Native job [121101933695](https://github.com/NoGod3524/EXReader/actions/runs/40171106759/job/121101933695): success.
- Strict verifier job [121102692474](https://github.com/NoGod3524/EXReader/actions/runs/40171106759/job/121102692474): success.

The separate evidence-only `[skip ci]` commit changes exactly this document and
`docs/validation/reader-android-display.json`. Its exact HEAD is returned in the
handoff; source/tests/workflow remain byte-identical to the tested source.

## Native acceptance

AGP 8.6.1 / Gradle 8.9 / Java 17 built and linted the native Android library.
A fresh directory compiled an independent consumer against the **installed AAR**,
not a Gradle source-project dependency. Its actual APK was installed, pulled back
and byte-compared; the running probe also hashed its own installed APK and bound
the installed AAR identity.

**23 / 23 named UI cases passed**, in this fixed order:

1. `normal_numeric_switch`
2. `follows_system_exact`
3. `rejects_nonfinite_atomic`
4. `rejects_out_of_range_atomic`
5. `wrong_thread_no_effect`
6. `reentrant_no_effect`
7. `duplicate_attach_no_effect`
8. `null_window_rejected`
9. `preexisting_keep_preserved`
10. `external_brightness_preserved`
11. `external_keep_preserved`
12. `unrelated_flags_preserved`
13. `cancel_restore_retry`
14. `close_and_after_close`
15. `exclusive_same_window`
16. `independent_windows`
17. `focus_loss_restore_no_autoactivate`
18. `pause_background_restore`
19. `rotation_old_token_rejected`
20. `window_recreation_releases_old`
21. `destroyed_window_rejected`
22. `hidden_window_activate_rejected`
23. `detach_old_callbacks_rejected`

**5 / 5 process/manifest/global-property cases passed**:
`actual_process_terminated`, `fresh_process_new_pid`, `reopen_default_window`,
`no_permissions_or_services`, `global_brightness_unchanged`.
The active process PID **2733** was force-stopped and absent; a fresh process
**2779** reopened with system-following brightness `-1` and no keep-screen-on.
Global brightness stayed **102**, mode **0**, before and after. The APK manifest
has no permissions or services. These are emulator Window/property observations,
not measurements of physical backlight or energy use.

## Authenticated evidence

The strict job authenticated same-source/run/attempt completed-success upstream
job and unique artifact name/ID, expiry, API digest and upload log. Within Actions
it downloaded actual ZIP bytes and recomputed size/hash; rejected duplicate
ZIP/JSON members; required exact named raw instrumentation results; and bound
module Git tree, AAR/classes.jar, packaged/pulled APK and runtime identities.

**46 / 46 verifier checks passed**: one actual authenticated baseline plus
**45 rejection mutations** of that real artifact/metadata, with no native-platform
credit for verifier fixtures. Exact names are in the validation JSON and report
artifact. They include wrong source/run/attempt/job, unfinished/failed producer,
artifact/ZIP/digest/expiry errors, duplicate JSON/ZIP/case members, tampered binaries,
wrong runtime identities, raw Window mismatch, wrong thread, process still alive,
permission/service injection, global-setting change and physical-effect overclaim.

| Artifact | ID | Bytes | SHA-256 | Expires UTC |
|---|---:|---:|---|---|
| [reader-android-display-native-40171106759-1](https://github.com/NoGod3524/EXReader/actions/runs/40171106759/artifacts/12590516044) | 12590516044 | 534416 | `b98567b6832b92a06b93326af06e61e5d99948761dc1bbb7aefe6c2b50a3d0c9` | 2026-11-24 07:03:43 |
| [reader-android-display-report-40171106759-1](https://github.com/NoGod3524/EXReader/actions/runs/40171106759/artifacts/12590715221) | 12590715221 | 2217 | `7570f61f4ba18e2c94c9818af9d472d6e892212ca94b60173ee259d0f2018f27` | 2026-11-24 07:03:57 |

| Actual binary | Bytes | SHA-256 |
|---|---:|---|
| Packaged **and pulled installed** `probe-debug.apk` | 31223 | `6fa5794af37721f847ae080a1ab9308772be5a8a3aa6857d5084a4817c15e60d` |
| `exreader-android-display-0.1.0.aar` | 7952 | `0cc2b45d1365cb5b3d79255016f81e2a313103567d4457d6fe54ce8135d4a3f4` |
| Original AAR `classes.jar` | 7651 | `7614d93e989d758b35a06e100ad0b15d3ae6c7d03677229f6642813189c8fe1a` |

Raw report SHA-256: `0422fd28095fdb8e9e827da13886b11513d11bbd981c96260aa3fc80360c568b`.
Authenticated native producer-log SHA-256:
`66bbc21900a99d0afe6af44e68bab2d1d0a7119ec1ec7a554acd5624472d1142`.

## Retained failure

[Initial run 40170886028 / 1](https://github.com/NoGod3524/EXReader/actions/runs/40170886028),
source `9b86c23a4324497c7ac93e3c33b60611c94b1285`, failed before native execution:
public compileSdk35 stubs do not expose `Window.isDestroyed()`; javac rejected two
calls. Native job `121101293253` failed and strict job `121101582945` rejected the
unsuccessful producer. The fix removed those two unavailable calls while retaining
public Activity destruction/finishing and exact owner-Window identity guards.
All named cases, original expectations and assertions were retained unchanged.

- Native log artifact `12590196035`, `reader-android-display-native-40170886028-1`,
  3317 bytes, SHA-256 `3bc3f482ea95c40970781a039f8d1f1870dcf73121875d4cb017a835436ca1e7`,
  expires 2026-11-24 06:57:41 UTC.
- Failed verifier artifact `12590515408`, `reader-android-display-report-40170886028-1`,
  219 bytes, SHA-256 `a09f7bd23a6796bfa906f3bba9824e6d972118edd708f824423d6443fcac5598`,
  expires 2026-11-24 06:57:54 UTC.

Actions deprecation and emulator startup/shutdown diagnostic warnings remain in
original logs; every required step in the corrected run succeeded.

## Deliberate limits and integration requirements

The library owns only current Activity Window properties. Android does not expose
an authorship stamp for identical external writes: cooperating host code must
release before same-value edits, including unobserved away-and-back changes.
No global policy, setting or persistence is claimed. Window callbacks must not
throw. Hosts must deactivate when the reader pane is hidden inside a still-visible
Activity. Automatic focus-loss/pause/destruction restoration and stale-window
rejection were exercised; formal host integration remains root's responsibility.

Physical backlight, battery/power behavior, OEM real-device behavior and
accessibility are **UNAVAILABLE**, not inferred from emulator properties.
Only the debug-signed CI probe was installed; no release was signed or published.
All compilation, lint/syntax checks, native execution, fixtures and artifact
processing occurred only in GitHub Actions. Local work was source/docs/Git plus
read-only GitHub metadata and decoded logs; no Codex tasks or user-computer actions.
