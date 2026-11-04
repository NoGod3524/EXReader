# Final gate probe · 2026-11-03

Source: `12f40f8a61adf0376035db54642fca60c0aa2ff3` (`ledger/base-20261103`).

Native run [41726208700](https://github.com/NoGod3524/EXReader/actions/runs/41726208700), attempt **1**, result **failure**. No rerun.

```sh
gh workflow run native.yml --ref ledger/base-20261103
```

Stop condition met; **reading-required-core was not dispatched**. No patches, catalog state changes, Settings changes or default-branch switch. Evidence is retained on its own branch; the tested ref was not advanced by this probe.

| Native job | Result |
|---|---|
| desktop (windows-latest) | failure |
| desktop (macos-15) | failure |
| desktop (ubuntu-22.04) | failure |
| apple-mobile | success |
| android | success |
| sanitizers | failure |
| fuzz | success |

Additional jobs included by native.yml (no extra workflow dispatch):

| Job | Result |
|---|---|
| ci-hygiene (packaging) | success |
| ci-hygiene (failfast) | failure |
| ci-hygiene (negative) | failure |
| ci-hygiene (diagnostic) | success |

Dispatch-only apple-packaging and windows-packaging were skipped.

## First errors (original text, maximum five lines per failed job)

### ci-hygiene (failfast)

Failed step: Check changed CI and exercise the rule. [Job log](https://github.com/NoGod3524/EXReader/actions/runs/41726208700/job/126231531592).

```text
ERROR: .github/workflows/acroform.yml:46 [failfast] expected=unchanged live exact baseline; actual=moved baseline line cannot acquire a new waiver; candidate=tools/ci_hygiene_baseline.json
```

### ci-hygiene (negative)

Failed step: Check changed CI and exercise the rule. [Job log](https://github.com/NoGod3524/EXReader/actions/runs/41726208700/job/126231531668).

```text
ERROR: .github/workflows/reader-desktop-drop.yml:68 [negative] expected=unchanged live exact baseline; actual=moved baseline line cannot acquire a new waiver; candidate=tools/ci_hygiene_baseline.json
```

### desktop (macos-15)

Failed step: Native parsing, pagination, rendering and bookshelf tests. [Job log](https://github.com/NoGod3524/EXReader/actions/runs/41726208700/job/126231531571).

```text
  File "/Users/runner/work/EXReader/EXReader/tests/check_benchmark.py", line 134, in main
    assert summary["passed"] and summary["identities_unchanged"]
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError
```

### desktop (ubuntu-22.04)

Failed step: Native parsing, pagination, rendering and bookshelf tests. [Job log](https://github.com/NoGod3524/EXReader/actions/runs/41726208700/job/126231531699).

```text
  File "/home/runner/work/EXReader/EXReader/tests/check_benchmark.py", line 134, in main
    assert summary["passed"] and summary["identities_unchanged"]
AssertionError
```

### desktop (windows-latest)

Failed step: Native parsing, pagination, rendering and bookshelf tests. [Job log](https://github.com/NoGod3524/EXReader/actions/runs/41726208700/job/126231531549).

```text
  File "D:\a\EXReader\EXReader\tests\check_benchmark.py", line 134, in main
    assert summary["passed"] and summary["identities_unchanged"]
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError
```

### sanitizers

Failed step: Run ctest --test-dir build/asan --output-on-failure. [Job log](https://github.com/NoGod3524/EXReader/actions/runs/41726208700/job/126231531348).

```text
  File "/home/runner/work/EXReader/EXReader/tests/check_benchmark.py", line 134, in main
    assert summary["passed"] and summary["identities_unchanged"]
AssertionError
```

Full run/job conclusions are in probe.json; exact first-error blocks, job IDs and original log SHA-256 are in failure-details.json. Runtime timestamps/ANSI transport formatting are omitted from excerpts; diagnostic text is retained. No errors were repaired or assertions changed in this probe.


## Owner-authorized P self-defect repairs after run 41726208700

1. Producer-only E3 fix: tools/run_benchmarks.py keeps passed equal to measurement validity. advisory=true and accepted=false remain independent. Removed the forced passed=false assignment; tests/check_benchmark.py is byte-for-byte unchanged. The unchanged benchmark test passed locally with the existing native benchmark producer, and its timeout/invalid-report assertions remain intact.
2. CI baseline identity is now (file, content_sha256, k-th occurrence in file), not a line number. Movement preserves identity; content edits and extra duplicates are new debt. Existing same-content duplicates are distinguished by occurrence. Exact-file scope and shrinking-only rule obligations remain enforced.

Only the existing 533 entries were mapped: 531 content identities, 533 retained rule bindings, difference -2 identities because two physical lines each had both failfast and negative. Pattern counts remain failfast507 / negative15 / diagnostic7 / packaging4. Unmappable entries: **none**. No new waiver was generated. The two combined identities and mapping metadata are in baseline-remap.json.

Local checks cover movement, repeated-content ordinals, new debt, changed content, stale entries and refusal to grow the baseline. No original benchmark assertion was changed or relaxed. A new native dispatch is authorized only after these repairs are integrated; core remains conditional on that native run being all green.

## Repair verification: native rerun 41732293021

- Fix PR: [#35](https://github.com/NoGod3524/EXReader/pull/35), merged as f19788b7449f03a2cefac7a59a24727c1674b81c.
- Native: [run 41732293021](https://github.com/NoGod3524/EXReader/actions/runs/41732293021), workflow_dispatch, attempt 1; source f19788b7449f03a2cefac7a59a24727c1674b81c; overall **success**. Exactly one rerun was dispatched.

| Job | Conclusion | First error |
| --- | --- | --- |
| [apple-mobile](https://github.com/NoGod3524/EXReader/actions/runs/41732293021/job/126252461052) | success | none |
| [desktop (ubuntu-22.04)](https://github.com/NoGod3524/EXReader/actions/runs/41732293021/job/126252461490) | success | none |
| [fuzz](https://github.com/NoGod3524/EXReader/actions/runs/41732293021/job/126252461528) | success | none |
| [ci-hygiene (negative)](https://github.com/NoGod3524/EXReader/actions/runs/41732293021/job/126252461562) | success | none |
| [desktop (windows-latest)](https://github.com/NoGod3524/EXReader/actions/runs/41732293021/job/126252461581) | success | none |
| [sanitizers](https://github.com/NoGod3524/EXReader/actions/runs/41732293021/job/126252461583) | success | none |
| [ci-hygiene (diagnostic)](https://github.com/NoGod3524/EXReader/actions/runs/41732293021/job/126252461605) | success | none |
| [ci-hygiene (failfast)](https://github.com/NoGod3524/EXReader/actions/runs/41732293021/job/126252461651) | success | none |
| [android](https://github.com/NoGod3524/EXReader/actions/runs/41732293021/job/126252461655) | success | none |
| [ci-hygiene (packaging)](https://github.com/NoGod3524/EXReader/actions/runs/41732293021/job/126252461757) | success | none |
| [desktop (macos-15)](https://github.com/NoGod3524/EXReader/actions/runs/41732293021/job/126252461853) | success | none |
| [windows-packaging](https://github.com/NoGod3524/EXReader/actions/runs/41732293021/job/126252463384) | skipped | none |
| [apple-packaging](https://github.com/NoGod3524/EXReader/actions/runs/41732293021/job/126252520047) | skipped | none |

The two packaging-only jobs were skipped by the full-scope workflow conditions. All seven requested native jobs and all four CI hygiene jobs passed. The four previously failing benchmark jobs passed without changing tests/check_benchmark.py; both previously failing CI hygiene jobs passed with content-defined identities. Full step conclusions are preserved in native-rerun-41732293021.json. Local checks and the unchanged test Git blob IDs are in local-repair-validation.json.

## Conditional core dispatch: not started

After native succeeded, exactly one core dispatch was attempted:

```text
gh workflow run reading-required-core.yml --ref ledger/base-20261103
HTTP 404: workflow reading-required-core.yml not found on the default branch (https://api.github.com/repos/NoGod3524/EXReader/actions/workflows/reading-required-core.yml)
```

Exit code: 1. No run ID was created; protocol/native/profiles/platforms/corpus have no result for this attempt. GitHub requires the workflow to exist on the current default branch for dispatch. No retry, branch-filter workaround, Settings edit or default-branch switch was performed. Machine-readable result: core-dispatch-result.json.

Conclusion: native passes on f19788b7; core remains unverified because dispatch was rejected. Both gates have therefore not been demonstrated green, and default-branch decisions remain pending.

## Milestone accepted by owner

Native run **41732293021** is the first end-to-end validated ledger/base milestone, on f19788b7449f03a2cefac7a59a24727c1674b81c. All seven requested jobs and four hygiene checks pass; the complete per-job table above is the milestone record. This native milestone does not claim core acceptance.

## One-time PR core probe: registered, failed, cleaned up

[Draft PR #36](https://github.com/NoGod3524/EXReader/pull/36) targeted ledger/base-20261103 at f19788b7. Its head 160ed1dd added one HTML comment to README.md, with no other change. GitHub tested the PR merge tree bc19505315e5a00aebfb1d15b5b596ef57631a0b. No dispatch was retried.

The pull_request trigger registered **Required native reading SDK core** ([run 41774219995](https://github.com/NoGod3524/EXReader/actions/runs/41774219995), attempt 1), including final check **reading-required-core**. This verifies check registration on ledger/base, not a ruleset/settings change.

| Group | Final result |
| --- | --- |
| protocol | success |
| native | success |
| profiles | success |
| platforms | success |
| corpus | failure |

### Every job conclusion

| Job | Conclusion |
| --- | --- |
| [protocol](https://github.com/NoGod3524/EXReader/actions/runs/41774219995/job/126390679427) | success |
| [platforms / reading windows-2022 (reading-core)](https://github.com/NoGod3524/EXReader/actions/runs/41774219995/job/126390679600) | success |
| [native / android](https://github.com/NoGod3524/EXReader/actions/runs/41774219995/job/126390679635) | success |
| [platforms / reading windows-2022 (reading-library)](https://github.com/NoGod3524/EXReader/actions/runs/41774219995/job/126390679671) | success |
| [native / sanitizers](https://github.com/NoGod3524/EXReader/actions/runs/41774219995/job/126390679673) | success |
| [platforms / reading macos-15 (reading-core)](https://github.com/NoGod3524/EXReader/actions/runs/41774219995/job/126390679686) | success |
| [platforms / reading macos-15 (reading-library)](https://github.com/NoGod3524/EXReader/actions/runs/41774219995/job/126390679717) | success |
| [native / ci-hygiene (negative)](https://github.com/NoGod3524/EXReader/actions/runs/41774219995/job/126390679718) | success |
| [native / fuzz](https://github.com/NoGod3524/EXReader/actions/runs/41774219995/job/126390679743) | success |
| [native / desktop (ubuntu-22.04)](https://github.com/NoGod3524/EXReader/actions/runs/41774219995/job/126390679753) | success |
| [native / apple-mobile](https://github.com/NoGod3524/EXReader/actions/runs/41774219995/job/126390679758) | success |
| [native / desktop (macos-15)](https://github.com/NoGod3524/EXReader/actions/runs/41774219995/job/126390679767) | success |
| [native / ci-hygiene (packaging)](https://github.com/NoGod3524/EXReader/actions/runs/41774219995/job/126390679788) | success |
| [native / ci-hygiene (failfast)](https://github.com/NoGod3524/EXReader/actions/runs/41774219995/job/126390679814) | success |
| [native / desktop (windows-latest)](https://github.com/NoGod3524/EXReader/actions/runs/41774219995/job/126390679867) | success |
| [native / ci-hygiene (diagnostic)](https://github.com/NoGod3524/EXReader/actions/runs/41774219995/job/126390679912) | success |
| [profiles / reading (reading-library)](https://github.com/NoGod3524/EXReader/actions/runs/41774219995/job/126390679999) | success |
| [profiles / reading (reading-core)](https://github.com/NoGod3524/EXReader/actions/runs/41774219995/job/126390680182) | success |
| [corpus / R2 real document acceptance](https://github.com/NoGod3524/EXReader/actions/runs/41774219995/job/126390680248) | failure |
| [native / windows-packaging](https://github.com/NoGod3524/EXReader/actions/runs/41774219995/job/126390681302) | skipped |
| [native / apple-packaging](https://github.com/NoGod3524/EXReader/actions/runs/41774219995/job/126390681486) | skipped |
| [reading-required-core](https://github.com/NoGod3524/EXReader/actions/runs/41774219995/job/126396873731) | failure |

### First errors

**corpus / R2 real document acceptance** — Build and install current native reading SDK:

```text
CMake Error at CMakeLists.txt:3 (find_package):
  Could not find a configuration file for package "EXReader" that exactly
  matches requested version "3.41.0".
  The following configuration files were considered but not accepted:
    /home/runner/work/EXReader/EXReader/build/reading-core/stage/lib/cmake/EXReader/EXReaderConfig.cmake, version: 3.42.0
```

**reading-required-core** — aggregate accepted=false because corpus=failure; protocol/native/profiles/platforms=success:

```text
##[error]Process completed with exit code 1.
```

The corpus consumer requested exact 3.41.0; the installed package reported 3.42.0. No code, assertion or version was changed during this probe. Full machine-readable job/step conclusions, registration, five-line error excerpt and log hashes are recorded in core-pr-run-41774219995.json, core-pr-registration.json and core-pr-first-errors.json.

### Cleanup and final decision

PR #36 is **CLOSED, not merged**. Its remote and local temporary branches are deleted, verified via an empty git ls-remote result. Cleanup metadata: core-pr-cleanup.json. The PR also automatically launched four independent workflows (Bounded library source, Native C engine, SDK version consistency, Native reading profiles); those extra runs were cancelled, retaining only the single core run and its reusable sub-workflows. IDs and final states: core-pr-related-runs.json.

**Final result: core registered on ledger/base but failed in corpus; stop.** The prior native milestone remains valid. No rerun, second PR, Settings edit, default switch, catalog state change or F03/F05/F07 product edit was made.
