# Corpus consumer version repair — 2026-11-04

Previous core run 41774219995 failed only in corpus: the active consumer required exact 3.41.0 while the installed package was 3.42.0. Native/protocol/profiles/platforms passed.

- tests/reading_corpus/CMakeLists.txt:3 now uses find_package(EXReader CONFIG REQUIRED COMPONENTS core pdf), consuming the installed package without a version pin.
- tools/check_version_consistency.py scans all CMakeLists.txt, .cmake and .cmake.in files for numeric find_package(EXReader <literal>) versions, including multiline/quoted values. A mismatched literal must match an existing exact, validated evidence exception; otherwise it reports file:line, actual and source version, with the instruction “改为读取安装包 version file，或登记豁免”.
- The same new rule found one unregistered sibling pin in extras/ocr/CMakeLists.txt:3 (3.40.0 EXACT); it now also consumes the installed package without a version pin. No component version or SDK version changed.
- Removed only the now-stale corpus line-3 waiver from tools/version_literal_exceptions.json. No retained historical fixture literal was upgraded or modified; no new frozen exception was created. The valid exception count is 587 (previously 588).
- The existing CI --self-test now deliberately restores the consumer to the previous SDK minor version (currently 3.41.0), requires exit 1 with the exact location/source version/guidance, and restores source bytes in finally.

Local validation: tools/check_version_consistency.py --self-test passed (including original project-version control and new consumer-version control); tests/check_version_consistency.py passed all seven evidence refusal cases and generated-byte drift checks. Full output: version-negative.txt and version-regression.txt. Existing tests/check_benchmark.py remains unchanged.

The previous native milestone and one-time core probe evidence are integrated from evidence commit 6db1181a in the same repair PR. Repair commits use [skip ci]; after integration, exactly one temporary comment PR will trigger the only new core run. It will be closed without merging and its branch deleted after the terminal results are recorded.

## Single PR core rerun: PASS

Repair [PR #37](https://github.com/NoGod3524/EXReader/pull/37) merged as **1e709837cb8a50816e94bf611ca4404f19f80abf**. Disposable draft [PR #38](https://github.com/NoGod3524/EXReader/pull/38) added one HTML comment only, head fc394ad31349b3c64fd7f715f587961c1930246e, tested merge tree 9fcf1270403d0cfd7011bf6351bfda6beddbc870.

**Core 在 ledger/base 上通过。** [Run 41782427456](https://github.com/NoGod3524/EXReader/actions/runs/41782427456), pull_request, attempt 1, overall success. Required native reading SDK core registered and its final reading-required-core check passed. All protocol/native/profiles/platforms/corpus results are success; performance remains outside this workflow.

| Job | Conclusion | First error |
| --- | --- | --- |
| [platforms / reading windows-2022 (reading-core)](https://github.com/NoGod3524/EXReader/actions/runs/41782427456/job/126416820939) | success | none |
| [native / fuzz](https://github.com/NoGod3524/EXReader/actions/runs/41782427456/job/126416821000) | success | none |
| [protocol](https://github.com/NoGod3524/EXReader/actions/runs/41782427456/job/126416821019) | success | none |
| [native / desktop (macos-15)](https://github.com/NoGod3524/EXReader/actions/runs/41782427456/job/126416821080) | success | none |
| [native / desktop (windows-latest)](https://github.com/NoGod3524/EXReader/actions/runs/41782427456/job/126416821084) | success | none |
| [profiles / reading (reading-core)](https://github.com/NoGod3524/EXReader/actions/runs/41782427456/job/126416821095) | success | none |
| [profiles / reading (reading-library)](https://github.com/NoGod3524/EXReader/actions/runs/41782427456/job/126416821116) | success | none |
| [native / sanitizers](https://github.com/NoGod3524/EXReader/actions/runs/41782427456/job/126416821119) | success | none |
| [platforms / reading windows-2022 (reading-library)](https://github.com/NoGod3524/EXReader/actions/runs/41782427456/job/126416821120) | success | none |
| [native / android](https://github.com/NoGod3524/EXReader/actions/runs/41782427456/job/126416821125) | success | none |
| [native / ci-hygiene (packaging)](https://github.com/NoGod3524/EXReader/actions/runs/41782427456/job/126416821155) | success | none |
| [native / apple-mobile](https://github.com/NoGod3524/EXReader/actions/runs/41782427456/job/126416821183) | success | none |
| [platforms / reading macos-15 (reading-core)](https://github.com/NoGod3524/EXReader/actions/runs/41782427456/job/126416821195) | success | none |
| [native / ci-hygiene (diagnostic)](https://github.com/NoGod3524/EXReader/actions/runs/41782427456/job/126416821209) | success | none |
| [native / desktop (ubuntu-22.04)](https://github.com/NoGod3524/EXReader/actions/runs/41782427456/job/126416821226) | success | none |
| [platforms / reading macos-15 (reading-library)](https://github.com/NoGod3524/EXReader/actions/runs/41782427456/job/126416821262) | success | none |
| [native / ci-hygiene (failfast)](https://github.com/NoGod3524/EXReader/actions/runs/41782427456/job/126416821291) | success | none |
| [native / ci-hygiene (negative)](https://github.com/NoGod3524/EXReader/actions/runs/41782427456/job/126416821344) | success | none |
| [corpus / R2 real document acceptance](https://github.com/NoGod3524/EXReader/actions/runs/41782427456/job/126416821543) | success | none |
| [native / apple-packaging](https://github.com/NoGod3524/EXReader/actions/runs/41782427456/job/126416822061) | skipped | none |
| [native / windows-packaging](https://github.com/NoGod3524/EXReader/actions/runs/41782427456/job/126416822296) | skipped | none |
| [reading-required-core](https://github.com/NoGod3524/EXReader/actions/runs/41782427456/job/126423228426) | success | none |

The two packaging-only jobs are skipped by normal full-run conditions. All remaining jobs pass. Full step results and the accepted=true final aggregation are in core-run-41782427456.json and aggregate.json. No failure excerpt exists because no job failed.

PR #38 is CLOSED without merge; remote/local temporary branches are deleted. Cleanup verified and recorded in cleanup.json. This was the only core round: no dispatch and no rerun. Four automatically triggered independent workflows were cancelled to retain only this core round; related-runs.json records each final state.

## Default-branch transition: pending owner authorization

No Settings or default branch was changed. Four items remain for owner confirmation:

1. Use ledger/base-20261103 directly as default, or create main pointing to the validated tip.
2. Staging cleanup: read-only ruleset inventory confirms exactly one existing active ruleset, ID 25700819, and no staging ruleset residue.
3. Branch filters: reading-required.yml push/pull_request currently name codex/framework; native.yml push names codex/framework while pull_request has no branch filter. Confirm which filters should name the chosen default. If main is chosen, reading-required-core.yml pull_request must also include main (currently codex/framework + ledger/base-20261103).
4. Decide retention/archive and protection handling for codex/framework when ~DEFAULT_BRANCH protection follows the new default.

Ruleset facts are in ruleset-readonly-inventory.json. The SDK stays 3.42.0; catalog state, assertions, Settings and F03/F05/F07 product paths are unchanged.
