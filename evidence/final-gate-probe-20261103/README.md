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
