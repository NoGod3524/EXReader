# F07 offline binary evidence — 2026-11-02

## Authority and immutable scope
User 18:17:42 UTC Sentinel_86017b7dd0048191b1d558cd0339a5f5 approved the explicitly proposed three new files, one commit/push and one Ubuntu job <=10 minutes.
Branch audit/f07-sixhost-binary-evidence-20261102; parent fb67403e042890d75bc28b48c00d20e83d1c90e8.
Read only six historical peer artifacts plus completed audit artifact13167080517: seven fixed IDs,40127329 compressed bytes.
This is distinct from completed B run41495920766; no repetition of its workflow or rebuild.
No installation, product execution, build, relink, retry, default-branch changes, PR or release.

## Reads and tools
Authenticate both historical runs, source/attempt/success and all seven artifact names/sizes/SHA256, plus six exact program hashes established by B. Consumer HEAD/parent/three added paths/marker/A1 are checked separately.
All ZIP/APK parsing takes place only in Actions, with <=20000 members, <=128MiB/member, <=512MiB declared uncompressed size, rejected traversal/control/NUL/canonical aliases/nonregular/encrypted/mode mismatch.
Android program.bin is an APK: only lib/<abi>/*.so are selected, at most64; other peers provide PE/ELF/Mach-O host bytes. Extracted bytes use controlled numeric temporary names; no executable permissions or payload execution.
Only a preinstalled matching llvm-nm/llvm-readobj pair is allowed, recording versions; missing pair fails closed without installation. Defined/undefined symbols, object symbol/import/needed-library tables are observations, not product runtime.
Each native reader gets <=30s, stdout capped16MiB/stderr1MiB; retained text capped8MiB/1MiB with truncation flags. Script total540s/job10min. No fallback build or retry.
Eight parser/format controls are audit safeguards, not product acceptance controls. Tool errors, no-symbol diagnostics, unsupported formats and truncation remain explicit.

## Interpretation
Unique static archive origin, private-entry absence and dynamic runtime loading are not automatically proven. A visible symbol or a successful reader is not sufficient for F07 acceptance; absent/stripped symbols do not prove absence of dependencies.
Module scope and public/private contract must be mapped separately. Existing artifacts are not replaced or modified.
Full textual observations stay in the authorized output artifact; stdout is bounded to hashes, statuses and symbol/dependency identifiers. No raw arbitrary report or connection strings are printed.
Reference commands: https://llvm.org/docs/CommandGuide/llvm-nm.html and https://llvm.org/docs/CommandGuide/llvm-readobj.html.

## Results
Output f07-binary-evidence/summary.json and per-command escaped JSON are uploaded even on failure. Run/artifact identities and exact residual gaps are reported without a second commit or automatic rerun.

## Independent review refinements
LLVM pair must return version rc0 with identical parsed versions, and --help must advertise every planned option before any payload read. Mach-O option is --macho-dsymtab. Expected formats: Windows PE; GTK/Android native objects ELF; Apple Mach-O. Mismatch stops that payload reader. Summary separately counts nonzero/timeout/launch/output/truncation/no-symbol observations; binary_observations_complete stays false on any such gap. Audit reading completion is not binary evidence completeness or formal acceptance.
