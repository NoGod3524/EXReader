# Reviewed modules: installed composition (T05)

## Independent review follow-up: accepted on 27 package configs

Review branch `codex/reader-reviewed-composition-review` starts at the sealed
Dot delivery `386b2cdf5071ccde299c04f5941eaee69c9b77bd`. The historical tested
source, run and 22-package result below remain unchanged.

The current common G1 suite at `a826a65c9c66e43620eff61b49cb79f941a3c953`
identifies the five omitted packages: EXReaderThumbnails,
EXReaderReadingCommands, EXReaderAnnotationView, EXReaderAnnotationExport and
EXReaderLocalDownloads. Their implementation trees and original test trees
already match the sealed Dot source byte for byte; no production repair is
needed. The original G08 baseline is 13 optional packages plus the SDK. G1 is
18 optional packages plus the SDK. Keeping that complete baseline and adding
the eight reviewed packages produces **26 optional packages, or 27 installed
package configs including EXReader**.

This review adds only T05's existing allowed test/workflow/document paths. It
installs those five packages into the same prefix, links their public targets
and compiles their headers in both original C11/C++17 consumers, extends default
SDK isolation to cover them, and executes the unchanged complete G1 suite before
and after physical prefix relocation. Both runs use the original runner's full
mode, including its original five module judges and old-build failure control;
the runner and all original judges remain unchanged. Raw original reports,
maps, actual binaries and installed header/archive proofs are authenticated in
the T05 ZIP. The old 22-package consumer criteria, all 11 negative gates and
both 37-check shared-owner chains remain required. The original G1 aggregate's
9 base and 6 extension refusal controls run unchanged alongside the extended
T05 protocol controls. The following new-source evidence grants this follow-up
only its tested three-desktop installed-package scope.

Tested source `0b03cb6a1e94d799a8f30efa9a8cd3d9121c14d2` (tree
`a884a2ef6909f578761f7247321476a28a91adbb`),
[run 40172066797, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40172066797):
Linux `121104816169`, Windows `121104816444`, macOS `121104816370`, and strict
aggregate `121107433138` all completed/success. The aggregate accepted all
27 configs, with `task_wide_accepted=true` for T05 and `complete_product=false`.
It downloaded and hashed each real platform ZIP, authenticated every retained
raw report, original consumer and installed proof, and checked matching
platform/phase cases and the original export byte outcomes.

Each of the two physical prefix phases passed:

| Original G1 criterion | Linux | Windows | macOS |
| --- | ---: | ---: | ---: |
| shared G1 chain | 20 | 20 | 20 |
| thumbnail probe | 179 | 178 | 179 |
| thumbnail regression / allocation fault | 11 / 3 | 11 / 3 | 11 / 3 |
| reading commands | 1413 | 1413 | 1413 |
| annotation view | 56 | 56 | 56 |
| annotation export | 25 | 25 | 25 |
| local downloads / old-build controls | 54 / 7 | 54 / 7 | 54 / 7 |

Windows keeps the original unavailable thread-count measurement; no check is
invented for it. The original 36 composition items, all 11 negative gates,
both 37-check reviewed shared-owner flows, and cloud 47 / bulk 21 / link 37 /
history 149 / keyboard 41 / book-information 22 cases with 795 assertions /
status 22 / profiles 42 all passed on each platform. The original Linux
account-profile ASan/UBSan suite remains required. The early and strict stages
also passed T05's 41 protocol refusals and the unchanged G1 9+6 controls.
IME, Windows injected auto-repeat and macOS deactivate-cancels retain their
documented hosted-runner skips. No host UI, performance, mobile or physical
device acceptance is added.

All final artifacts expire `2027-01-23T07:15:06Z`:

| Artifact | ID | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| Linux | 12590588059 | 168758857 | `a3be1afb2949b313c37fbf732436fb6aa986b2d02f265fe4973d30b4824bdc62` |
| Windows | 12591321183 | 130176439 | `b7e16ca633d32ce7dff026854c27aea05470fee1a778d5dbe7e2b6044c45dcec` |
| macOS | 12590758141 | 145852214 | `3ed0878002e30a2168d1e4ceb1ff0dadd65f605faad593116b278bb30c77f8e8` |
| Strict report | 12590728818 | 12622 | `d17e266a82e50292d6156c006184a8a927d06c424b9dabed4537cf37c8a51f19` |

The strict report artifact's own identity comes from the API, without a
self-authentication claim. The complete strict JSON, including every bound
binary/raw-map/header/archive digest, is copied verbatim from its cloud log
into `docs/validation/reader-reviewed-composition.json`. This evidence-only
commit changes only those two documents and carries `[skip ci]`.

The first review source `a7a4e96e66b2823c9816ff3ab45fb4c219d675a4`, run
`40171264203`, retained the actual 27-package prefix, both original G1 full
runs and both shared-owner flows. Its T05 bundle checker refused original
passing raw checks because it added a global check-name uniqueness rule that
the original judges do not impose. The follow-up keeps uniqueness exactly
where the original judges require it (G1 chain and thumbnail regressions),
and preserves their complete raw arrays elsewhere. Source review also restored
the annotation-export judge's original platform-specific Windows locked-target
versus POSIX RLIMIT failure cases, skip rules and cross-platform output digest
comparison. These are checker corrections; no original judge, test fixture or
production module changes.

## Historical Dot delivery: boundaries and exact ordinary merges

Fixed start: `e4356a6e13223469fdf3b2f3d5171a6e99ab10a6`.
Ordinary merge point: `b143a861ef951a90c99e9c136cec47395aa700d2`.
All eight delivery SHAs are recorded and independently checked in
`tests/reader_reviewed_composition/guards.py`. Their trees are unchanged.
The eight merge commits have two parents in delivery order; Git Data publication
preserved each ordinary merge's exact tree and both parents (local merge point
`901e3d96e67a14dae381163441c11670d29e6080`, identical tree
`bf9bd1a572f4a5ef215285a4701c9fcdf996bbf8`). No conflict resolution occurred.

Only the four T05 path prefixes change after that merge point. Frozen SDK,
product schema, all production modules/hosts, and all original tests/workflows
remain unchanged. No local build/test/syntax check/fixture/service/artifact
processing has been performed. Every acceptance check runs in Actions.

## Installed acceptance

The original composition's C11/C++ consumers, named results, default-prefix
isolation, relocatable install, per-header probes and duplicate-SQLite/include
leak/dependency gates are retained. The eight reviewed packages are installed
into the same prefix and linked by both fresh-directory consumers. All original
reviewed-package consumers and judges run without editing their code or
reducing their counts, including the native keyboard probe's documented skips.
Supplemental fault-injection binaries retain their original explicit source
hooks; the actual composition binaries only consume installed public packages.

A new installed C++ consumer demonstrates:

1. Real TLS cloud download on a separate worker that never receives an SDK handle.
2. SDK-owner import through the cloud adapter and immutable original export/readback.
3. Existing typed book command and public catalog attach, without hand-written SQL.
4. Favorite mutation through the actual borrowed metadata owner and bulk package.
5. Read-only book information and sync status from that same product/session.
6. Real SDK captures retained by jump history; keyboard dispatch calls public
   decode/resolve and completes Back only after FOUND.
7. Actual external-link classification without opening an external site.
8. A bounded 256-shard session sweep publishes that same product's favorite history.

The exact scenario runs again after physically moving the prefix and rebuilding
in another fresh directory. Its fixture independently observes downloads,
immutable-original bytes and revision identities.

The strict aggregate requires three completed/success jobs from the same
source/run/attempt, unique artifact identity, non-empty unexpired ZIPs and API
digests; it downloads and hashes ZIPs in Actions, rejects duplicate members and
reports, verifies every required report and binds actual consumer binary bytes.
Original cloud, link-policy and history installed headers/archives are retained
and hashed after relocation; link/history report hashes bind those exact bytes.
The original cloud adapter semantic guard and its negative controls run on this
checkout alongside T05's stronger immutable merge/path boundary. Artifact and
job IDs, not just their names, must be unique.
All original reports and new named results are retained. A missing public API
would keep overall accepted=false with the exact missing signature; no fallback
mapping or private SQL is permitted.

## Historical 22-package scope and verified cloud evidence

No production host UI, physical-keyboard/IME, performance, Android or iOS credit
is granted. No complete-product or complete-library-sync claim is made.
Tested source: `616a9bf85240f860bf5f8fa395b31c0954db703b` (tree
`af62b2f63e03083c40711fe2ed789ece634350f0`).
[Run 40166639576, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40166639576)
completed successfully on the exact source. Linux job `121088941869`, Windows
`121088941876`, macOS `121088941754`, and strict aggregate `121090754742` all
completed/success. This evidence-only `[skip ci]` commit changes only this file
and `docs/validation/reader-reviewed-composition.json`; it does not inherit
runtime acceptance for different code.

Each platform passed 36 original composition items, all 11 original negative
gates and both 37-check shared-owner runs. Original reports retained cloud 47,
bulk 21, link 37, history 149, keyboard 41, book-information 22 cases/795
assertions, status 22 and profiles 42. Linux also passed the unchanged original
account-profile ASan/UBSan commands, including the heap nonterminated-plan
regression. The strict aggregate passed 32 tampering/identity controls and
authenticated all three platform ZIPs, reports, installed proofs and actual
consumer binaries. No missing public API or SQL fallback was needed.

**Verified composition: accepted. Task-wide acceptance: withheld** only for the
frozen-baseline discrepancy below. The aggregate explicitly names the exact
22-package scope and keeps `task_wide_accepted=false`.

Native keyboard gaps remain explicit: IME skipped on every hosted runner;
Windows also skipped injected auto-repeat; macOS skipped deactivate-cancels.
Those skips retain the original documented limitations, not extra input/IME
credit. Complete named results, actual binary hashes and historical failure
artifacts are recorded in the validation JSON.

### Final artifact identities

All expire `2027-01-23T05:44:49Z`. Platform archives were downloaded and their
size/SHA-256 recomputed in the strict Actions job. The aggregate artifact's
metadata is recorded from the API; it does not authenticate itself.

| Artifact | ID | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| Linux | 12588673235 | 61617137 | `77ed469beb4c39bfbd488c9b90078b13f146c83e98988d2a391aac7d091e3603` |
| Windows | 12588678367 | 49612704 | `e2e9c87cd74b14a225a2bdbdc32ea7a171d11cef2f1a8c0d3e65603ce796b7d8` |
| macOS | 12587829512 | 53528510 | `ba53f302953e839dcb9924ef05a43e983d06d0ccd9dac85dfa4b2183feea4371` |
| Strict report | 12588069191 | 8130 | `40463428f6f139bc182f6e20371b5f803e88f0935f2af4336a3aa1198b06ff96` |

## Historical frozen-baseline discrepancy (resolved by the follow-up above)

The handoff calls the prior suite “18 packages”. At fixed start
`e4356a6e13223469fdf3b2f3d5171a6e99ab10a6`,
`docs/READER-MODULE-COMPOSITION.md:32-42` explicitly says thirteen independent
optional packages; `tests/reader_module_composition/consumer/CMakeLists.txt:29-43`
finds those thirteen plus the SDK. The exact existing suite is preserved, not
replaced with five guessed packages. Its unique package identities are:

- EXReader (SDK)
- EXReaderProductCatalog, EXReaderRevisions, EXReaderWebDAV, EXReaderSideload
- EXReaderCredentials, EXReaderSearch, EXReaderPreferences, EXReaderBatchImport
- EXReaderSync, EXReaderCommands, EXReaderDesktopMetadata, EXReaderSession,
  EXReaderReadingState

The eight authorized additions are EXReaderCloudImport,
EXReaderBulkOrganization, EXReaderLinkPolicy, EXReaderJumpHistory,
EXReaderKeyboardActions, EXReaderBookInformation, EXReaderSyncView and
EXReaderAccountProfiles. Actual combined scope is **22 unique package configs**,
not an invented “18 + 8” count. Task-wide acceptance stays withheld pending
root's resolution of that discrepancy; independently verified cloud results
will be reported for this exact graph only. No missing public API was found in
the requested shared flow.

## Preserved first-run failure

Source `258f0c36a40f1bd0cc65091a70317d7cb489d81d`, run `40165114855`,
Linux job `121084469699`: the original cloud allocator probe failed to compile
because its line 19 includes `../../../../apps/reader/cloud-import/src/cloud_import.c`.
Its source file actually sits three levels below the root. The standalone SDK
prefix's deeper include-search path had accidentally made that path resolve;
a single prefix exposes the error. Original tests are immutable here. The
T05-only `cloud_consumer` wrapper compiles the original C/C++ consumers unchanged,
uses the same allocation interception and original `cloud_probe.c`, and changes
only the supplemental source include to the actual root. No case is removed.
The Linux run separately passed both 37-check shared-owner flows, original
composition, prefix relocation, and all 11 original negative gates.

The same first-run Windows job `121084469476` also rejected the T05
orchestrator's native backslashes in the link-policy/account-profile CMake
`-D` source paths (`Invalid character escape '\a'`). T05 now passes those
values as forward-slash paths, matching the original standalone workflows.
Original test sources and expectations are unchanged. Windows separately
passed both shared-owner flows and all original composition negative gates.

Repair source `ad2d94af43410e7ed63eb874dac81911916bddb6`, run `40165661710`,
Linux job `121086065595` passed all eight original suites, including all cloud
cases and the unchanged J13 ASan/UBSan commands. A newly added relocated-prefix
audit was incorrectly given an environment variable written to `GITHUB_ENV`
earlier in that same step (available only to later steps). The audit correctly
refused the resulting empty path. T05 now supplies the explicit relocated path;
no audit or acceptance rule is removed. Later scenario steps were not run on
that source; the failed attempt remains preserved.

Those two failed runs ultimately failed their strict aggregates too; no failed
producer was accepted. Their macOS jobs later reproduced the same respective
include/audit failures. Intermediate source
`607fdb53e01173e13c9299ba4caf5fd555e03bc1`, run `40166164464`, passed all three
producers and its aggregate, then was superseded by the final candidate to bind
installed archive/header bytes and explicit unique IDs. Final-source evidence
above supersedes that intermediate pass, rather than borrowing it.
