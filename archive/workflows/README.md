# Workflow archive preparation

Base: `26dac7335b844127c38d4084e7c5cc081e464ee5`. Prepared on 2026-11-05 America/New_York. Main is frozen pending PR #42. No PR or CI run has been created.

256 workflow files before preparation; 10 retained; 246 moved with git mv. All retained and archived workflow blob IDs match the base.

## Retained workflows

- `ledger-authority.yml`
- `ledger-evidence-custody.yml`
- `native.yml`
- `r2-reading-corpus.yml`
- `reader-total-progress.yml`
- `reading-core.yml`
- `reading-platforms.yml`
- `reading-required-core.yml`
- `reading-required.yml`
- `reliability.yml`

## Manifest

`MANIFEST.csv` maps original_path, archive_path, last_run_id, archive_reason. The last-run IDs were read across all branches from the GitHub workflow API; none means the registered workflow has zero runs. Snapshot details are kept with the external preparation evidence.

Archived workflows without a registered run: 3.

## Unresolved preparation dependencies

- Retained reading-required.yml calls ./.github/workflows/reading-real.yml, which is outside the selected retained set. Its performance reusable workflow reference would be missing. The required reading-required-core.yml call graph is complete.
- CI hygiene baseline contains 531 content-identity entries (533 rule bindings). 512 entries (514 rule bindings) belong to archived files; deletion coupling requires removing these stale bindings in the same PR. The other 19 remain in retained workflows. No baseline or checker is changed in this mechanical preparation.
- tests/check_ci_hygiene.py:167 reads .github/workflows/acroform.yml. The archived copy retains the exact bytes; the test path needs a coordinated update without changing its assertion.
- Version-literal registration has 144 frozen_baseline entries for archived workflows and 7 migration_compat proofs pointing to reader-apple-record-compatibility.yml. The latter require an active workflow. sdk-version-consistency.yml is also outside the selected retained set. Resolve these references before treating the preparation as merge-ready; no exception, literal, guard or assertion was changed here.

native.yml and reliability.yml are retained byte-for-byte. No protected-tree object, catalog state, rule or SDK identity changes.
