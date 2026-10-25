# G09 offline distribution inventory

One install of a reading preset produces an evidence bundle that another job can
re-derive from the uploaded bytes alone:

| File | Role |
| --- | --- |
| `inventory.py` | Reads the installed stage, records every dependency tool invocation, writes `inventory.json`, `inventory.spdx.json` (SPDX 2.3) and `inventory.cdx.json` (CycloneDX 1.5). |
| `contract.py` | Pure parsers and checks shared by the generator, the fixtures and the aggregate: tool-output parsers, archive/symbol graph, installed-file and licence verification, artifact/ZIP identity. |
| `sbom.py` | SPDX 2.3 and CycloneDX 1.5 builders plus structural validators. Licence identifiers come from an explicit component table so an unregistered dependency cannot inherit one. |
| `aggregate.py` | Same-source collector: downloads the artifacts and producer logs, re-hashes every installed file, re-parses every recorded tool output, recomputes the static symbol graph, re-validates both SBOMs and optionally checks them against the published schemas. |
| `check_inventory.py` | Fixture regression: untouched installs must be granted, and each single mutation must be rejected with a named code. Runs without a compiler. |
| `check_scope.sh` | Cloud guard: this run's commit, fixed start ancestor, frozen SDK tree, unchanged product schema, package-only changes. |
| `probe/` | Installed public-API probe. It links `EXReader::exreader`, `EXReader::exr_pdf` and (when present) `EXReader::exr_library`, so its link command is the recorded dependency edge for every distributed archive. |

Re-derive a finished run without rebuilding:

```bash
python3 tests/reader_distribution_inventory/aggregate.py --downloads build/downloads \
  --output build/aggregate --spdx-schema spdx-schema.json --cdx-schema bom-1.5.schema.json \
  --run-id RUN --attempt 1 --source-sha SHA
```

Two verdicts are reported separately. `materials_complete` means the inventory,
licence materials and dependency evidence for every install are proven from the
uploaded bytes. `release_ready` additionally requires that no distributed file
carries a build-machine absolute path; those blockers name the file and are left
to the owner of that file, because fixing them changes files outside this package.
Mobile packaging, host bundles, signing and publication are outside this scope.
