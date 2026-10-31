# F07 Windows/macOS installed-provider evidence

## Authority and immutable inputs
User Sentinel_a00c036c474081919b4aff5834a818c3 explicitly approved exactly six new verification files, one workflow and this document; exclusive branch codex/dot-f07-desktop-provider-20261031. Product 044824f91ddae2ea49994350d308d079a69048ab and SDK 7271829a829bfa6aaa47b73077c493f71af27ad3 are fixed. No production, SDK, prior tests, F09, credentials tests, CDB or cleanup wiring is changed. One Windows240/mac120/audit20 minute run; no automatic correction round. At authoring: not run.

## Real recipes and platform-specific evidence
Windows follows installed module order and public targets from tests/windows_sdk342/build.py and its unchanged host_build/C09 constants, builds EXReaderWave3 and invokes tools/build_windows_host.py. The original headless --self-test (26 minimum checks,120 seconds) is retained; this is not a UIA suite. OPDSHash is installed first and its canonical prefix is supplied. The candidate uses static reading SDK; /VERBOSE:LIB is the only added host linker diagnostic. Actual MSVC MAP symbol-owner rows plus full-path verbose link evidence, archive symbols/members and PE imports bind the provider. We do not infer two linked SQLite providers merely because two archives were built.

macOS invokes unchanged build_apple_product and build_apple_host recipes with explicit 3.42/raw/wave3/page-theme options. It retains the shared SDK architecture, original Apple map/installed-product checks and ad-hoc local signing. No app launch, UI or account test is added. The wrapper records actual swiftc command and adds only -v/-why_load diagnostics. Mach-O map object indexes are joined to SQLite symbols, with nm/otool/install-name/architecture evidence. Installed SDK dylib bytes are compared with the copied bundle bytes BEFORE existing codesign; separately retained installed and final signed hashes are not falsely declared equal. The final host/package and package manifest/ZIP identities are checked.

Public installed codec and SDK consumers supply auxiliary source-id/compile-option observations, never live-host provider attribution. Core is an INTERFACE_LIBRARY and its real dependency EXReader::exr_render is recorded; base/render concrete files are bound separately. Private vendor target is inspected for archive identity only, never linked as a new public dependency.

## Independent audit and controls
Each original Actions artifact is pinned by same source/run/attempt, unique name/ID, API size and SHA256; original ZIP retained. Bounded ZIP validation rejects unsafe paths, aliases, encryption, links/special entries and excess counts/sizes before reading payloads. No downloaded executable is launched. Ubuntu LLVM independently reads archive symbols and host Mach-O symbols or PE imports.

Per platform: one positive and seven negatives with exact refusal reasons: missing_map, provider_ambiguous, target_prefix, sdk_version_abi, provider_owner, system_sqlite, file_hash. Semantic mutations recompute the internal hash seal so a stale outer hash cannot hide the intended rule; the archive-hash control intentionally tests integrity. A separate actual CMake configure rejects a relative SDK prefix. Missing evidence remains failed, not guessed.

All commands issued through the new wrapper have stdout/stderr captured and persisted; nonzero exits remain nonzero. Unchanged tools retain their own internal subprocess behavior, with outer output and propagated failure output preserved; no claim is made that every internal successful query emits a separate log. Dedicated evidence directory contains only generated build/inspection outputs, fixed-source headers/archives, synthetic package resources and binaries; no user files, account fixtures, TLS keys or tokens. The audit token is used only for GitHub metadata/download authorization and is not forwarded to the signed object URL.

## Acceptance boundary
This package establishes static link/package evidence for these two fixed host profiles. Shared SDK internals and two-level dynamic binding are not claimed to be the same as a live process-wide SQLite uniqueness proof. host_runtime_provider_observed=false; auxiliary source-id observations are separate. F07_accepted=false and formal95/108 remain unchanged; no six-platform completion, managed-cleanup integration or production-binary equality to unrelated builds is asserted. Original Linux F07 success and first failure remain independently sealed.


## Failed runs retained (2026-10-31)

Initial run41185541703/A1/source72ffabc68a864c83b47a9d10329f8799f4bdc6e4: macOS124491614240 success; Windows124491614131 failed at new dumpbin /? version probe returning1100, after successful host/package/IMPORTS/HEADERS commands. Help text and Dumper14.44.35229.0 were retained. Windows auxiliary consumers were not reached. Audit124492547104 failed closed at producer_job and authenticated neither platform. Artifacts: Windows13035913701/26538435B/SHA25622b7f5c4c56c9991441765a4800687b0e5d3c4666b3d344bf27b02e87eebe7c6; mac13036113313/59059033B/SHA2563fcdab3afd21778b23e6438f82d977282f00b9cfcb28cfe8d57c5d39c09a7768; audit13037060133/308B/SHA256958772843ca9176edabb836a89d2fc167fbd5036a813f5f74ee5bd464d783a42.

User Sentinel_c9dc79ba6e1c8191932b5a383c29ddfe separately approved only the HEADERS-based version correction and one additional Windows240/mac120/audit20 round. Source01ab528888f5c5be97e5824d69e2908e31e68e24 preserves nonzero failures, requires one exact Dumper version from successful HEADERS, and retains argv/returncode/output hash; it does not tolerate arbitrary1100.

Correction run41186261435/A1: Windows124493687007 and macOS124493687201 both succeeded. Audit124494459783 failed at installed_header, platforms empty. Original Windows artifact identity, internal hashes, package host, SDK/ABI/core and target-prefix checks preceded that failure; host provider judgment and semantic negative controls were not reached. macOS was not downloaded or independently authenticated. Ordinary logs lack the actual dependency path text: case/path-format mismatch is only a candidate, not a proven cause or proof that the system header was used.

Fixed correction artifacts: Windows13036129037/31654088B/SHA256c71801182be4188ad1fea84d2b5b2691e50735fbfa8763acbb7c1fe8d5efd9e4; mac13037275549/59058964B/SHA256eb77ff395cbbc907172ef709b5a7b3ed79fd4f21fa28a8b444099f4487e3b169; audit13037126061/31563172B/SHA2566dcd572421e60fca7784e6b8dbf984e9b89396e4aa699712c34e29a5976a9984.

Both run failures remain failures. host_runtime_provider_observed=false, F07_accepted=false and formal95/108 unchanged. No local ZIP/build/test or third full-build run. The first doc append was explicitly denied without execution; user Sentinel_068ef275ed308191ab5ca0de911c470b subsequently explicitly approved failure/diagnostic doc append and skip-ci sealing, plus one independent Ubuntu20min existing-artifact diagnostic. This paragraph records that new authority, not a bypass of the denial.


## Separately authorized fixed-artifact diagnosis

User Sentinel_068ef275ed308191ab5ca0de911c470b approved a single Ubuntu20min existing-artifact diagnosis and the original result-document append/seal. The previously denied original append was retried once on its original target with this new authority and succeeded; old failures were sealed on the original feature branch as d513c08d289692bbadb535beaca09f69c3d72269 [skip ci]. This diagnostic branch starts at fixed01ab528888f5c5be97e5824d69e2908e31e68e24; only new diagnostic script/workflow and this original document change.

Only original Windows artifact13036129037/31654088B/c71801182be4188ad1fea84d2b5b2691e50735fbfa8763acbb7c1fe8d5efd9e4 from run41186261435/A1 is downloaded in Actions. The unchanged original checker is source-byte-bound and its installed_header failure is reproduced. Raw Ninja sqlite dependency rows, compiler include command evidence, expected path, separator/case/lexical comparisons, installed-header inventory hash and SQLITE_SOURCE_ID/runtime comparison are reported separately. Header source comes from frozen product FetchContent recipe; no independent source-header byte copy was retained, so that hash comparison is explicitly unavailable, not filled by a new upstream download.

Original map/link rows and symbol-owner parser outputs may be exposed as diagnostic facts only. No original gate is modified, no artifact executable is run, no build/UI/consumer rerun occurs, no Mac artifact is downloaded. ZIP has fixed API/outer/internal hashes and bounded path/type/size checks; text is scanned for authentication secrets before original ZIP retention. One20min run, no automatic correction. diagnostic_completed does not imply original_audit_passed or F07 acceptance. At authoring, diagnosis has not run.


## Fixed-artifact diagnostic result

Run https://github.com/NoGod3524/EXReader/actions/runs/41187576237 / A1 at 8bb03c91c946a1a174d1c6452cf402a67d356ea9 succeeded (job124497517258). Only the fixed Windows artifact was authenticated/read. diagnostic_completed=true, errors empty; original_audit_passed=false, product_rebuilt=false, artifact_code_executed=false, gate_changed=false.

Actual Ninja dependency row: ../product/include/exreader-product/sqlite3.h. Original checker expected D:/a/EXReader/EXReader/build/f07-desktop/product/include/exreader-product/sqlite3.h. Both original separator-normalized substring and casefold-only diagnostic comparison are false. Diagnosis classified this as relative/lexical path representation using the recorded consumer command working directory; this is not a simple case-only mismatch. Installed header SHA256 cd20a2877bc82b94e36c1093b727dd87cfa3c1d581aac6e240925535cbd90166 matches its sealed inventory; SQLITE_SOURCE_ID matches the independent codec runtime. The upstream source-header bytes remain absent, so no independent source-header hash comparison is claimed.

Additional raw MAP fact: sqlite3_open_v2 and sqlite3_prepare_v2 each map to exr_vendor_exr_sqlite:sqlite3.c.obj, i.e. the SDK vendor archive basename, not the product archive assumed by the original checker. sqlite3_sourceid has no matched MAP row. These are diagnostic parser outputs, not complete provider adjudication. A header-path-only correction would not resolve the different provider expectation; Windows static-SDK linkage policy must be assessed before changing that gate. No production defect or acceptable-policy amendment is inferred merely from this difference, and no gate was relaxed.

Diagnostic artifact13038145693:31566370 bytes,SHA256 ec264351524561b43d94190dcaedbed68905aa8ffe647a5cfa93114192ab097d. It retains the original pinned Windows ZIP plus diagnostic/summary JSON. No Mac download or formal audit replay. The single20min diagnostic budget is consumed. Original two failed runs remain failed; F07_accepted=false and formal95/108 unchanged. Any checker correction or further certification requires separate authorization.


## Separately authorized certification correction and replay

User Sentinel_5d2fa874d8bc8191b98b8a23520ddbfa approved only two verifier corrections and one Ubuntu20min certification of the two existing run41186261435/A1 artifacts; no new Windows/macOS build or artifact-code execution. Producer source stays01ab528888f5c5be97e5824d69e2908e31e68e24; verifier source/run/attempt are recorded separately. Both original artifact IDs/sizes/digests above are hard-pinned. Original diagnostics8bb03c91 and sealc11c118f remain unchanged in history; the pure diagnostic script is untouched.

Header evidence resolves Ninja dependency entries against the recorded command cwd and -C consumer directory, checks that directory against the fixed installation sibling, and compares the complete installed header path. Windows uses Windows path semantics; Mac keeps its own case-sensitive comparison. Header inventory/hash and product SQLITE_SOURCE_ID match are checked; the absent independent upstream header bytes are not invented.

Windows host policy is aligned with the frozen product contract (tests/reader_catalog/check_desktop_sdk.py at044824 allows a sole product or SDK SQLite provider). This is not an unconstrained replacement of the expected archive: MAP sqlite API owners must all agree; full-path MSVC Searching/Loaded evidence must select one allowed archive/member; the exact installed target path, archive bytes/hash and SDK727 input remain bound. Direct SQLite objects, unknown/ambiguous owners and system fallback remain refused. Codec-only remains product-only; auxiliary SDK remains SDK-only; Mac host remains static product SQLite plus its existing shared SDK architecture.

All original seven negative controls remain. Wrong-owner now changes the actually selected owner to an unknown archive rather than assuming product was selected. Two additional resealed negatives cover foreign header and foreign consumer directory: one positive plus nine negatives per platform. Source-id equality is reported separately from complete compile-option sets and FTS5; equality of source-id never proves option equivalence or live-host behavior. Independent LLVM reads original binaries/archives without executing them. At authoring this new20min replay has not run; original audit failures remain failures and F07_accepted=false/formal95/108 remain unchanged.

## Fixed-artifact certification replay: preserved failure (2026-10-31)

- Verifier source: `26d94263a47f05788ba1444f2c250db8cf94d2c1`.
- Pure audit [run 41188947889 attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/41188947889), job `124501556150`, completed **failure**. The single authorized Ubuntu 20-minute replay is consumed; no automatic correction or rerun.
- Producer remains `01ab528888f5c5be97e5824d69e2908e31e68e24`, run `41186261435`, attempt 1. No product was rebuilt or artifact executable run.
- Actual summary: `audit_completed=false`, `audit_passed=false`, `errors=["provider_loaded_ambiguous"]`, `platforms=[]`, `F07_accepted=false`, formal `95/108`.
- Windows identity, sealed inventory and the corrected installed-header resolution were reached before the MSVC loaded-member parser refused. This error does **not** establish that the actual host has multiple SQLite providers: the parser's zero/multiple-match refusal has not yet been distinguished using retained raw evidence. Do not promote a parser refusal to a demonstrated product defect.
- No completed platform certification is claimed. The Windows semantic controls and macOS certification were not reached. Earlier failed audits and the successful narrow header diagnostic remain unchanged.
- Retained audit artifact: ID `13038275682`, `31563241` bytes, SHA-256 `db39164de434bb87f105a09bc75b50a31eeb371baacbc78ae37a263864d664e5`; includes the original Windows ZIP and failure summary. No local ZIP download or analysis was performed.
- Host live-runtime provider observation and full six-platform F07 acceptance remain unproved.


## Authorized fixed diagnostic JSON read

User Sentinel_aa4e9de0d5448191b923f54d8cccaea0 approved the preceding failure doc-only seal and one Ubuntu 20-minute read of fixed diagnostic artifact 13038145693 (31566370 bytes, SHA-256 ec264351524561b43d94190dcaedbed68905aa8ffe647a5cfa93114192ab097d), run 41187576237/A1, source 8bb03c91c946a1a174d1c6452cf402a67d356ea9. Only the existing pure diagnostic script, workflow and this document change. The certification checker remains byte-identical to 26d94263a.

The reader opens only the exact diagnostic.json ZIP member after identity and bounded ZIP checks; it does not recursively read the nested original Windows ZIP or execute artifact code. Every selected_link_rows value is printed with its array index and physical diagnostic.json line. The earlier JSON did not retain original host-build.log line numbers, so those are explicitly unavailable. Matching counts use the retained filtered projection, not a reconstructed full log: omitted intervening Searching rows may change context. This is format evidence only, not a corrected gate, product rebuild, or successful certification. Prior failures remain.
