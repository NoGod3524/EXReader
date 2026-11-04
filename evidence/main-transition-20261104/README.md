# Main transition S1–S3 — 2026-11-04

## S1: pointer created

main was created without a new commit, equal to ledger/base-20261103 at **1e709837cb8a50816e94bf611ca4404f19f80abf**. Both remote refs were read back and matched.

## S2: one-line trigger change

Commit **682e1ab5a62229ee477b2b192de81d34e8ab37fe** (`ci(gate): include main in required core triggers`) was pushed to main. Its only file change is .github/workflows/reading-required-core.yml:5, replacing the branches list with `[codex/framework, ledger/base-20261103, main]` (one insertion / one deletion). No jobs or required status check set changed. main now points to 682e1ab5; ledger/base remains at the S1 source 1e709837.

## S3: PR registration and execution verified

Disposable draft [PR #39](https://github.com/NoGod3524/EXReader/pull/39) targeted main and added one HTML comment to README.md only. Head: 5bdfc4dd919b52cc14a030dde0c78a10dd977a9f; base: 682e1ab5; tested merge tree: 6c9c27a4def3d6d621ae2a445ee21332a05efee9.

**Required native reading SDK core** appeared in the check list and actually executed as [run 41786091768](https://github.com/NoGod3524/EXReader/actions/runs/41786091768), attempt 1, pull_request. Overall: **success**; final **reading-required-core**: **success**, accepted=true. All protocol/native/profiles/platforms/corpus groups passed.

| Job | Conclusion | First error |
| --- | --- | --- |
| [protocol](https://github.com/NoGod3524/EXReader/actions/runs/41786091768/job/126428447638) | success | none |
| [corpus / R2 real document acceptance](https://github.com/NoGod3524/EXReader/actions/runs/41786091768/job/126428447864) | success | none |
| [platforms / reading windows-2022 (reading-library)](https://github.com/NoGod3524/EXReader/actions/runs/41786091768/job/126428447875) | success | none |
| [native / apple-mobile](https://github.com/NoGod3524/EXReader/actions/runs/41786091768/job/126428447969) | success | none |
| [native / desktop (macos-15)](https://github.com/NoGod3524/EXReader/actions/runs/41786091768/job/126428448003) | success | none |
| [native / sanitizers](https://github.com/NoGod3524/EXReader/actions/runs/41786091768/job/126428448010) | success | none |
| [platforms / reading macos-15 (reading-library)](https://github.com/NoGod3524/EXReader/actions/runs/41786091768/job/126428448092) | success | none |
| [native / ci-hygiene (failfast)](https://github.com/NoGod3524/EXReader/actions/runs/41786091768/job/126428448117) | success | none |
| [native / fuzz](https://github.com/NoGod3524/EXReader/actions/runs/41786091768/job/126428448120) | success | none |
| [platforms / reading windows-2022 (reading-core)](https://github.com/NoGod3524/EXReader/actions/runs/41786091768/job/126428448133) | success | none |
| [native / android](https://github.com/NoGod3524/EXReader/actions/runs/41786091768/job/126428448144) | success | none |
| [profiles / reading (reading-core)](https://github.com/NoGod3524/EXReader/actions/runs/41786091768/job/126428448149) | success | none |
| [profiles / reading (reading-library)](https://github.com/NoGod3524/EXReader/actions/runs/41786091768/job/126428448158) | success | none |
| [native / ci-hygiene (diagnostic)](https://github.com/NoGod3524/EXReader/actions/runs/41786091768/job/126428448180) | success | none |
| [platforms / reading macos-15 (reading-core)](https://github.com/NoGod3524/EXReader/actions/runs/41786091768/job/126428448278) | success | none |
| [native / desktop (ubuntu-22.04)](https://github.com/NoGod3524/EXReader/actions/runs/41786091768/job/126428448291) | success | none |
| [native / ci-hygiene (negative)](https://github.com/NoGod3524/EXReader/actions/runs/41786091768/job/126428448329) | success | none |
| [native / desktop (windows-latest)](https://github.com/NoGod3524/EXReader/actions/runs/41786091768/job/126428448367) | success | none |
| [native / ci-hygiene (packaging)](https://github.com/NoGod3524/EXReader/actions/runs/41786091768/job/126428448429) | success | none |
| [native / windows-packaging](https://github.com/NoGod3524/EXReader/actions/runs/41786091768/job/126428449441) | skipped | none |
| [native / apple-packaging](https://github.com/NoGod3524/EXReader/actions/runs/41786091768/job/126428449767) | skipped | none |
| [reading-required-core](https://github.com/NoGod3524/EXReader/actions/runs/41786091768/job/126433764618) | success | none |

The two packaging-only jobs were skipped by the normal full-run conditions; all other jobs passed. PR #39 is CLOSED without merge. Its remote and local temporary branches are deleted and absence was verified. The one comment never entered main. Four auto-triggered independent workflows were cancelled, retaining only this core round and its reusable sub-workflows; related-runs.json records all final states.

## S4/S5 boundary

S4 was **not executed**; no Settings edit was made. Readback default_branch is still **codex/framework**. S4 requires the owner’s separate “执行”. S5 has not begun: ledger/base remains in the core branches list, the archive tag was not created, and no README/docs default-branch declaration was added.

Machine-readable evidence: steps.json, core-registration.json, core-run-41786091768.json, aggregate.json and cleanup.json. All final evidence is held on a separate evidence branch; main has exactly the single S2 commit after the S1 pointer.

## S4 owner-confirmed switch and S5 closure

S4 switched default_branch from codex/framework to main. PATCH returned HTTP502 but readback was main; the owner confirmed success. The PATCH was not retried. The previous S4/S5 pending record above describes the earlier S1–S3 checkpoint and is superseded by this section.

S5.1: standalone commit23404809 changes only the core pull_request branches line to [codex/framework, main]. S5.2: archive/codex-framework-20261031 points to8ca964fc4adc572cf2da303f5d88100a5e844ccb; archive/ledger-base-20261103 points to1e709837cb8a50816e94bf611ca4404f19f80abf. Both tags were pushed explicitly and both original branches remain. S5.3: README paragraph at line3, commit80bd7d65, identifies main and archived framework history and links ledger/evidence entry points.

S5.5: [negative draft PR #40](https://github.com/NoGod3524/EXReader/pull/40), [run41902048351](https://github.com/NoGod3524/EXReader/actions/runs/41902048351): reading-required-core isRequired=true and FAILURE; GraphQL mergeStateStatus=BLOCKED, REST mergeable_state=blocked, while mergeable=true confirms no conflict. [API and restoration evidence](s5-guard-negative/README.md). The workflow was restored; PR closed without merge; temporary branch deleted. No ruleset field or catalog state changed.

The S5 workflow and documentation changes are submitted through a normal PR because main inherits required PR/status-check rules. They are not pushed directly to protected main.
