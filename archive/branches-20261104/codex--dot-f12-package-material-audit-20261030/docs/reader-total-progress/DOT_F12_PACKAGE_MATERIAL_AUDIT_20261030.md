# F12 retained six-package materials audit

This isolated candidate inventories retained development package bytes, not a release, legal opinion, product rebuild, full dependency proof or F12 acceptance. Formal ledger remains 95/108.

## Scope and identities

Base/source packages: 8f8acf3234cba747165f001c0c96efe1b911e6ad, run 40678657371 attempt 1, SDK 3.42.0. Exact six outer IDs, sizes, SHA256 and inner ZIP SHA256 are hard-pinned in the new script. Read the existing pinned handoff at f623a07f9034cb70e3429ecb235a52009ea2acc3:docs/validation/sdk342-six-platform-handoff-40678657371.md for program hashes and deployment limits.

Three new files only: this document, scripts/audit/dot_f12_package_material_audit_20261030.py and its matching workflow. One authorized Ubuntu22.04 Actions job, one run, maximum30min. All archive parsing and controls run only in Actions. No rebuilds, product execution, old tests or SDK changes. No dispatch or automatic rerun is provided.

## Checks and limitations

The auditor verifies GitHub identity before download, strips Authorization on HTTPS redirects, verifies original ZIP bytes/hash, retains originals, prechecks paths/types/duplicate entries and bounds before member reads, authenticates inner manifest/checksums and inventories nested APK only for the pinned Android entry. No extractall or payload execution.

Budgets: outer download exact pinned bytes (all below64MiB), archive/member128MiB, 20000 members per layer, cumulative512MiB per target and3GiB across six. No automatic budget increase. Canonical collisions, absolute/drive/traversal/backslash paths, symlinks and encrypted files refuse. Casefold collisions are reported separately.

The fixed-source SDK license registry supplies upstream hashes and repository-original text hashes. Unconditional components are required. Optional conditions not established from retained evidence stay unresolved, NEVER not_applicable merely because a file is absent. Matching original material is identified by expected path suffix plus content hash. Root MIT/NOTICE and host Noto OFL are separately inventoried, including Android APK assets. Unknown external/system dependency applicability is explicitly retained: this is not a full linked dependency/SBOM reconstruction.

Installation notes are bound to the exact source and hashed through the manifest. Topic matches only locate candidate paragraphs (installation/import/sync/conflict/backup/upgrade), not functional validation. Additional document paths are listed for human review. instructions_complete remains false until independently validated workflows exist. Repository-only documents do not count as bundled instructions.

Historical SDK3.40 G09 source93d2ad0d/run40095313750 excluded final hosts/mobile/font bundles. Its60-file path finding is historical, not a current count. This package does not fix or claim to retest old-library migration safety; H01/H05 ownership remains separate.

## Controls and interpretation

Six positive synthetic packages (one per target, Android nested APK) and24 named negatives:
5 identity;9 ZIP/nested namespace boundaries;4 manifest;4 license content;2 instruction identity/presence.
Semantic material/instruction mutations rebuild manifest/checksums and ZIP before testing the target rule. The control report records expected vs actual rejection. Original material gaps are not called control failures.

audit_completed means the audit process finished on all six authenticated packages. materials_complete and instructions_complete are separate; missing/unresolved obligations cannot grant release readiness. legal_compliance_assessed=false and F12_promoted=false always. Integrity/parser/control failures retain nonzero job result and always upload available evidence. A successful audit with incomplete materials is a gap report, not a passed product.

## Results

Not run at initial submission. Actual CI source/run/attempt and artifact identity must be appended by a separately authorized evidence handoff after terminal result; do not infer success from this document.

## Fixed recipe applicability review

Independent read-only source review at 8f8acf32 identifies flags via CMakeLists.txt:13-35, CMakePresets.json:13-38, tests/windows_sdk342/build.py:21, tests/reader_gtk_raw_wave3/run.py:98, tests/apple_sdk342_package/run.py:35 and .github/workflows/android-composition-candidate.yml:62-65. All target recipes enable PDF/library/ICC/JPX, disable AAC. Windows/GTK reading-library inherit AUDIO/MP3 OFF; Apple and Android retain AUDIO/MP3 ON. Android disables WEBP/TIFF/AVIF/PDF_CRYPTO; other recipes retain them. This is source-recipe classification, not a newly observed build cache or full binary dependency closure. The script records that distinction on every row. registered_materials_complete is separate; overall materials_complete remains false because full host/system dependency completeness is unresolved.

Do not classify wp7 test-font notice as a runtime dependency: it is an unconditional installed material in the fixed registry. Optional disabled license materials can still exist as supplemental notices; not_applicable here describes the recipe component, not a claim that no such text exists anywhere in the archive. All files remain in the inventory.
