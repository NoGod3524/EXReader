# Linux C02 + managed WebDAV joint candidate

The fixed Linux combination passed its product regressions and separate raw-evidence audit.
C02 admission precedes SDK/catalog ownership and managed recovery. The reader retains its lease while recovery, networking and SDK borrowers are alive; final shutdown releases it after the workers join.
The candidate is ready for the overall owner's read-only acceptance review. Formal catalog remains **95/108**.

## Fixed identities and scope

- Exclusive branch: `codex/gpt-c02-webdav-joint-20261031`; this conversation is its implementation owner.
- **Tested source H: `b5e7fea87174f5e0baabfad97cf5cf7082f2d85e`**. Use H for CI acceptance; a later document-only seal is not a new tested product.
- Base: `8232e91cd7b9296dfcdd3096b96317eb3fa1008a`.
- Frozen C02 Linux dependency closure: `d32603dc65bccfd65901239d21cb65cd10bca168`.
- Frozen C02 audit decoders: `5d9fc903ab015c50c3ce25b57a2680218bb0d419`; upstream final seal `721188e553be4c8cffe9fbfb204f8a544a64bfe9`.
- Frozen WebDAV product: `044824f91ddae2ea49994350d308d079a69048ab`.
- Frozen cleanup core: `dba079b550f9ec83054e6b7b0b7475f43bc1739f`.
- Frozen SDK: `7271829a829bfa6aaa47b73077c493f71af27ad3`; version 3.42.0 / ABI 1.
- [Exact source manifest](https://github.com/NoGod3524/EXReader/blob/b5e7fea87174f5e0baabfad97cf5cf7082f2d85e/tests/c02_webdav_joint_20261031/manifest.json): 88 imported product/dependency entries, 45 runtime tester blobs, 11 new owned files.
- [Complete base-to-H diff](https://github.com/NoGod3524/EXReader/compare/8232e91cd7b9296dfcdd3096b96317eb3fa1008a...b5e7fea87174f5e0baabfad97cf5cf7082f2d85e): exactly 97 changed paths; two imported dependency entries already equal the base.
- Scope was first registered in `68c69dc03fbdb90acc2bfc732f3b95956494dd08`, before implementation.

Only `examples/linux/reader.c` is merged: the frozen WebDAV entry/close code is retained and its open-error formatting line is replaced with the frozen C02 line.
Merged blob: `7f0be835c87a3ce9dc694fb45291dac6d0264a45`.
C02 `reading.c`, Linux CMake, packaging tool, three POSIX C02 modules and coordinator/lm closure are exact imported blobs.
Desktop CMake keeps WebDAV's Linux changes; C02 Windows entry changes are excluded.
All other WebDAV paths, including its original tests/workflow, are exact frozen blobs.
No SDK, ABI layer, original assertion, external owner branch, shared worktree, formal catalog or other host entry was changed.

## Final Actions result

[Run 41223341504 / attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/41223341504), push event at H, completed/success at 2026-10-31 17:19:25 UTC.

| Job | ID | Result |
|---|---:|---|
| admission | 124602259668 | success |
| c02_linux | 124602314525 | success |
| Legacy macOS | 124602314573 | success |
| gtk | 124602314586 | success |
| Legacy Windows | 124602314638 | success |
| audit | 124604033138 | success |

Ordinary logs and the same-run independent summary agree:

- C02 native: 28 cases / 207 checks, scope 10 / 81, migration API 17 / 130; all failed=0.
- Original actual migration: 36 cases plus 20 repair cases, failed=0. The verifier also checked 56 retained raw process-death observations for SIGKILL=9, wait=-9 and actual owner/observer UID/PID fields; these are observations, not a claim of 56 unique processes.
- Original historical migration driver passed unchanged.
- C02 actual GTK/retained SDK borrower driver: 13 cases; four raw authority phases and eight resealed negative controls passed.
- WebDAV: original TLS 77/77 on Linux; original transport matrix 25/25, 11 observed process deaths; real installed GTK 21 records.
- Windows old API: TLS 76/76, asynchronous session 20/20; managed remains disabled by default.
- macOS old API: TLS 77/77, asynchronous session 20/20; managed remains disabled by default.
- New cross groups: 6/6.
- Separate audit job: `passed=true`, `errors=[]`; WebDAV `accepted=true`.
- Negative controls: original WebDAV 4, new joint 6, original GTK resealed 8, all rejected for their recorded semantics.
- Native audit explicitly retains `full_c02_complete=false` and `power_loss=false`.

The six cross groups exercise: refusal of an unregistered library before managed startup; an active GTK reader refusing an actual migrator; refusal while HTTPS work is blocked and after account close until final GTK shutdown; GTK refusal while a real migrator owns PENDING, including SIGKILL and explicit recovery; separation of WebDAV pending cleanup from C02 admission/CLEAN; and the frozen last-page/search/SDK-borrow regression.
The independent implementation decodes raw C02 binding/state bytes, native identities, generations and grants, and reuses frozen receipt/CRC/target and GTK snapshot decoders.
Independent means a separate Actions job and original-value recalculation; the new integration producer and joint verifier were authored in this conversation, not by a second author.
No complete-C02, six-host, full F10/F12 or power-loss label is transferred to H.

## Product bytes and evidence navigation

The running managed GTK and packaged binary are byte-identical:
`10457512` bytes, SHA-256 `4d11f83034a6e953b2d9a6733228f0509ffc1af3b8921bc5f88b6f585548497d`.
The product and installed ordinary consumers have no test hooks; fault workers are separate.

1. In the independent artifact, read `independent/summary.json`. Its `independent/c02-linux.zip`, `gtk.zip`, `Windows.zip` and `macOS.zip` preserve the original producer ZIPs authenticated against the API.
2. In the GTK artifact, read `c02-webdav-joint/cross/result.json`, `gtk-managed/build.json`, `gtk-managed/matrix/results.json` and `gtk-managed/ui/results.json`.
3. Native evidence is in the C02 artifact: `native/`, `native-independent/`, `migration/`, original process logs and retained fstat/bytes. Independent native checks consume the producer's original fstat observations, not identities created during extraction.
4. GTK borrower snapshots and actual link inputs are in `c02-webdav-joint/gtk-original/`; package and installed prefix are in `gtk-managed/package/` and `gtk-managed/prefix/`.
5. Manifest and recipe/fixture adaptation receipts identify every frozen tester blob and both original/derived script hashes.

All ZIP downloading, parsing, fixture generation, project syntax checks, builds and tests ran exclusively in Actions.
Local/VM work was source reading/editing and Git object operations only.

## Final artifacts

The four producer IDs/bytes/digests below also match the independent job's authenticated summary. All six API records are unexpired, expiring 2027-01-29.

| Artifact | ID | ZIP bytes | SHA-256 |
|---|---:|---:|---|
| [joint-independent-41223341504-1](https://github.com/NoGod3524/EXReader/actions/runs/41223341504/artifacts/13051270420) | 13051270420 | 131733349 | `20acdff2edd81ce5f23d8fe4bc5b31272d981f64f9eaaf3c7d23e536dd38e36e` |
| [joint-c02-linux-41223341504-1](https://github.com/NoGod3524/EXReader/actions/runs/41223341504/artifacts/13051095596) | 13051095596 | 29217047 | `fffb55dee23c0d34e2e3eb1dcbabc282f349c1e46298a31311c67a64c95cb03e` |
| [joint-gtk-41223341504-1](https://github.com/NoGod3524/EXReader/actions/runs/41223341504/artifacts/13050684346) | 13050684346 | 104497072 | `6b0f025e1e1eae5bf6ae45b88cf4e208f148645348e0842b780506787c30ba67` |
| [joint-macOS-41223341504-1](https://github.com/NoGod3524/EXReader/actions/runs/41223341504/artifacts/13050454617) | 13050454617 | 1338876 | `cf0d11aea888318a826bb705143cb89e0ba10cc761e3c3987eba26073bcf97b5` |
| [joint-Windows-41223341504-1](https://github.com/NoGod3524/EXReader/actions/runs/41223341504/artifacts/13050434639) | 13050434639 | 2356919 | `a78bf771e0db62f7caf276a22967434aa4947ccf2fe9dba20d412613fac40a34` |
| [joint-admission-41223341504-1](https://github.com/NoGod3524/EXReader/actions/runs/41223341504/artifacts/13050143952) | 13050143952 | 4423 | `65d37805827b4ee9c28841e143d3df916bcb42782248d7ee0ebd52939c2a95ef` |

## Tester adaptations and retained assertions

The original WebDAV build/assertion body is reused. Its adapter stages frozen C02/search/navigation dependencies, supplies the explicit C02 prefix and packages the actual combined binary.
CMake Unix Makefiles retain real `link.txt` for the managed host, enrollment CLI and GTK harness.
The frozen GTK driver's path-only mappings point its unchanged static-input assertions at this actual host and installed SDK/C02 layout; its SDK receipt names the approved fixed SDK.
The original WebDAV UI scenario/assertion body is unchanged; the fixture adapter explicitly creates/checks admission before launch with the installed CLI and the real non-root OS authority.
The native decoder's single feature-contract source lookup uses the pinned frozen tester commit, because those test paths are materialized inside Actions rather than committed as product paths at H.
Product/receipt source checks still require H/run/attempt. No original assertion is removed.
The native decoder's retained evidence limits remain in the independent summary; this package does not replace the upstream full qualification audit.

## Run history and budget

[Initial 41222658017 / attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/41222658017) at `ac6309d1e7dd00233a735ab3fa1b5084bf32cd49` is retained as completed/failure.
Admission, C02 Linux and both old-API jobs passed. GTK stopped before product compilation because the adapter's generic generator fragment also matched a mixed-prefix negative-control command.
The sole correction restricted that text match to the real build helper's build-type argument. The negative control and every original assertion stayed intact.
The independent job correctly rejected the failed producer with `producer job gtk`; no GTK or cross result is claimed for that initial round.
The correction changed only the new build adapter and this document. Final H reran every corresponding job; old green jobs were not spliced into acceptance.

| Initial artifact | ID | ZIP bytes | SHA-256 |
|---|---:|---:|---|
| [joint-gtk-41222658017-1](https://github.com/NoGod3524/EXReader/actions/runs/41222658017/artifacts/13050572710) | 13050572710 | 3597 | `0eefff31a7c0b9473738de7948ff7617219b480ba3944ea588903b7ba2b69e9a` |
| [joint-Windows-41222658017-1](https://github.com/NoGod3524/EXReader/actions/runs/41222658017/artifacts/13050493426) | 13050493426 | 2356353 | `2d23550e52dd46d2d9a9c97aca91da7dbd086696bae6851c4a1f26724c6c2c43` |
| [joint-independent-41222658017-1](https://github.com/NoGod3524/EXReader/actions/runs/41222658017/artifacts/13050458726) | 13050458726 | 309 | `48ec7f9dcc1c71d8559e6751cf2591869b04e9bdb9f2b7a5492a20c627090f08` |
| [joint-c02-linux-41222658017-1](https://github.com/NoGod3524/EXReader/actions/runs/41222658017/artifacts/13050279165) | 13050279165 | 29218427 | `862ba06d9f5f5522ab884adf803c1319539892a71e976550cec68155c45183a4` |
| [joint-macOS-41222658017-1](https://github.com/NoGod3524/EXReader/actions/runs/41222658017/artifacts/13050153344) | 13050153344 | 1339464 | `0ba93ebe8baf8c9f7e0dc7e33e8aaab134ab264a53d77310f998b23989f0eabb` |
| [joint-admission-41222658017-1](https://github.com/NoGod3524/EXReader/actions/runs/41222658017/artifacts/13049993890) | 13049993890 | 4422 | `131436ec598f0a908de64920b40caa155194148b2742b51559796bf78502f46b` |

Approved ceiling: admission10 + native60 + GTK120 + Windows30 + macOS30 + audit25 = 275 runner-minutes/round; initial + one targeted correction, maximum550.
Both round slots are consumed. No rerun/dispatch or third implementation run is authorized.
Job timestamp totals: initial688s + final1205s =1893s (31.55 elapsed runner-minutes; not a billing calculation).
This final document seal uses `[skip ci]` and changes only this file.

## Preserved boundaries and remaining work

- Current acceptance is the fixed Linux C02 + managed transport staging/alias combination. A new main-task source/SDK/install combination needs its own fixed identity and corresponding verification.
- Six-host C02 qualification, full F10/F12, hardware power loss/storage cache behavior and all other host managed integrations remain outside this package. Original ABI2 known-six Windows/Linux failures and their artifacts are retained, not repaired or rerun here.
- WebDAV `sync private_file`, upload snapshot and GTK import snapshot high-level lifetimes remain upstream gaps.
- WebDAV capacity remains 16 roots x64 lifetime transaction slots; failures may consume slots. No slot reuse, permanent-root retirement or unlimited-capacity contract is added.
- Cooperative same-UID/local-filesystem assumptions and the upstream historical approval-origin disclosure remain; no historical approval proof is invented.
- Formal `catalog.json` is unchanged at95/108. No main/shared-branch push, PR, tag or release occurred.
- Source/Git/docs used lap25002's user-approved native terminal -> saved official `instabox@0.8.52` -> existing `m_agqxv2s72g5vwdtsifu5cnmml4`. Desktop Commander remains quota-blocked and was not called on this route. No credentials or authentication settings were read/exported/changed.
- The single authorized resume completed, then running/ready and pwd exit0/timedOut=false were confirmed at2026-10-31 16:23:34 UTC (America/New_York12:23:34 EDT). No second resume/restart/new VM/resize or autoSuspend change occurred.
- VM continuation state: `/tmp/exreader-c02-webdav-joint-20261031/{inputs.json,state.json,drafts.json,diff-review.json,correction-diff-review.json}`. Shared worktrees were untouched.
- No pending CI, unknown native PID or active implementation blocker remains. Preserve both run histories and arrange any long-term archive before artifact expiry using the main-task process; future ZIP handling remains Actions-only.
