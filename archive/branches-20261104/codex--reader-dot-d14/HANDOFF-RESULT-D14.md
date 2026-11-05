# D14 final handoff — Windows bounded scope passed; GTK incomplete

Overall `accepted=false`. Three complete CI iterations exhausted; no fourth run,
product fix, SDK change, old-test change, main-branch change, PR or release.
Windows passed the final predeclared two-process sustained lifecycle plan. GTK
completed only stage-one cycles/dwells and failed its live-processing observation
precondition, then timed out in cleanup. Both final original ZIPs authenticated.

## Source, run and configuration identities

| Role | Full identity |
|---|---|
| Harness fixed base | `0889f7d1e9a537c6c1b05456547e016b26e1cd85` |
| Final tested harness | `b85046c37456ca8e33138ff19fa4fcfb2425bcdb` |
| Final tested tree | `b78f67ba5c47c84c3ad617f366e778423487513e` |
| Windows target | `9321de84eb9c8d3d57cafbeaa8b0a28fe2a26a08` |
| GTK target | `803098e9df1a365a9b8e206805c2d179aca8501f` |
| SDK candidate / actual version | `edddc463c06ed5731195cdb8f06b2df6dff7699e` / 3.41.0 |
| Installed SDK header SHA-256 | `461f33b1f17c4650229935630179d369b715b5a9a24d2181f3f653864bed47a0` |
| Read-only C02 contract | `169b0be3c1c8199be0211649412d23d9e34041e4` |
| Branch | `codex/reader-dot-d14` |

Final run [40226870656](https://github.com/NoGod3524/EXReader/actions/runs/40226870656),
attempt **1**, terminal **failure**. Jobs:
Windows `121269985432` success; GTK `121269985619` failure;
authenticator `121274207985` failure because full GTK lifecycle was incomplete,
not because ZIP authentication failed.

Both targets were independently checked out and built as actual compact hosts.
`build-d14.log` retains verbose compiler/link commands; `CMakeCache.txt` retains
ON/OFF configuration. No review-gate injection or forged GITHUB identity. SDK
protected source tree was compared against the fixed candidate. Old 3.40/raw-seven
modules, schemas, wire and C02 budgets remain untouched. `sdk-base.h`, actual
executables, fonts, fixture bytes, per-cycle captures and profile files are in the
original platform artifacts.

## Final same-run original ZIPs

| Platform | artifact ID | bytes | SHA-256 | expiry |
|---|---:|---:|---|---|
| Windows | 12612032207 | 18828408 | `54944f80d3c6c5b47a535d2ecf21fa8f9e58ef57655b96331c2097c87c71a4e8` | 2027-01-23T19:37:00Z |
| GTK | 12612330807 | 18981931 | `ba12e1f70741e4a0d63d814a9e5d921a16f2c67764e24ca1a6597948444616ae` | 2027-01-23T19:37:00Z |

Names: `d14-windows-40226870656-1`, `d14-gtk-40226870656-1`.
The Actions consumer independently downloaded both original ZIPs, checked unique
identity, exact run/attempt/source, service digest, byte count, expiry, member
inventory, every file hash, program/font/SDK-header hashes and report identities.
`artifact_authentication=true`; full acceptance remains false.

Summary artifact `12612730141`: 67802 bytes, upload digest
`dd48aca8b170386963f3aa3d57ea1354d69923992802697c933e85ac5dcb7500`.
This summary ZIP was not itself independently re-downloaded; only its two source
platform ZIPs receive the independent authentication grant.

Actual executable hashes:
- Windows `EXReaderProduct.exe`:
  `406b79cb1362e2344eda26123afa9a174e86128e8da9beb3384dad3b6a250d81`.
- GTK `exreader-linux`:
  `f1213d208a31f77f2444292488c8ce964d9ffb992d80bf19ebbd8a771c585adf`.
- Both `Reader.otf`:
  `2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b`.

Full initial original-file identities per platform are in
`docs/reader-dot-wave2/d14/final-evidence.json` and each original `report.json`.
Generators/content are fixed; EPUB/CBZ archive bytes can differ between target
helper/toolchain builds. No byte-identical cross-platform corpus claim is made.
Windows final original-byte check passed; GTK's final check was not reached.

## Complete named plan and counted execution

Closed-world IDs in `contract.expected()` expand:
`stage 1–2 / round 0–2 / txt,epub,pdf,cbz / open,forward,backward,library,resume,
search,directory,records,settings,import_cancel`, plus `1/close_processing`,
`2/no_replay`, `2/final_close`, `originals_unchanged` (244 checks).
Each of 24 complete cycles also has a separately identified **30-second live
reading dwell**, not an extra cycle. Per-platform total test ceiling is 45 minutes;
resource sampling is every 0.5 seconds. Dwell presence, real duration, cycle IDs,
resource coverage and distinct process identities are mandatory, not success flags.

Seven negatives passed on Actions: `missing_dwell`, `missing_stage`,
`fake_completed_count`, `pid_mismatch`, `lost_failure`, `missing_resources`,
`artifact_mismatch`. No old assertion was weakened.

### Windows — accepted bounded lifecycle/resource observation scope

- 24/24 complete cycles, 244/244 completed checks, 24/24 complete dwells.
- Stage 1 PID **7248**, stage 2 PID **6636**, both exit **0**.
- Stage dwell totals: **360.780 s**, **360.764 s**; sum **721.544 s**.
- Lifecycle test elapsed **794.266 s** (13 min 14.266 s), not CI build time.
- **1555** raw resource observations; real search busy controls were observed
  before closing stage one; stage two had no persisted/replayed query or results.
- Last stage still operated all four formats; original files unchanged. Read-only
  profile observations found no pending-file requests or annotation rows. Ordinary
  implicit progress saves/native imports were the only predeclared writes.

Raw observed ranges (not budgets/trends/leak claims): RSS 33,652,736–95,694,848
bytes; handles 175–661; GDI 10–166; threads 4–15. Cumulative user/system CPU seconds
are retained for every sample. No child processes were observed in these samples.

### GTK — failed/incomplete, not a passed second stage

- 12 complete cycles / 120 completed UI actions and all 12 stage-one dwells.
- PID **10086**; 873 resource samples. Dwell sum **360.481707 s**.
- Ordinary cycles/dwells completed by about **427.85 s**. Full failed session
  elapsed **476.466031 s**, including observation timeout and cleanup; do not call
  all of that successful sustained reading.
- `1/close_processing` failed. The actual search had reached `phase=3`,
  `running=0`, `complete=1`, `polls=1`, `code=0`, `count=0` before the observer
  captured phase 2. The strict in-flight precondition timed out after 10 seconds.
  This is an unobserved live interval, not evidence that the search never ran.
- Cleanup helper Alt+F4 did not retire the main host behind the modal; its 20-second
  wait timed out, then the harness killed the process, exit **-9**. Preserve this
  cleanup failure; it is neither a spontaneous product crash nor normal rejection.
- Stage two, no-replay, final four-format recovery and final unchanged-original
  check are **not executed**: 123 named planned checks remain missing, plus 12
  stage-two dwells. No failed loop was skipped to manufacture a pass.

GTK raw observed ranges: RSS 110,997,504–239,616,000 bytes; fd 16–20; threads 5–9.
Resource sampling ended near 440.805 s before cleanup; no complete cleanup-resource
coverage is claimed. `failure.png`, `failure-snapshot.json`, state, native tree,
application log, full tracebacks and attempted/completed action records are retained.

## Earlier iterations remain failed

1. Harness `5f76251e6ab906740151ed60ca5fc034ce050bbf`, run `40225172916`, attempt 1.
   Jobs Windows `121264892872`, GTK `121264892526`, auth `121266036593`.
   Windows 12 cycles/120 actions/67 samples then extra 9 MB TXT failed import:
   authenticated subsequent snapshot says
   `导入失败：超出宿主或SDK限制（Native parser failed (6)）`.
   No second stage; cleanup exit 0 was not a successful in-flight close.
   GTK driver `gtk` module collided with PyGObject before launch: zero cycles.
2. Harness `c466aa835b412555cadd5a3734ea766f366b925a`, run `40226184382`, attempt 1.
   Jobs Windows `121267939674`, GTK `121267939430`, auth `121269188892`.
   Windows passed short-cycle scope only: 24 cycles, PIDs 3328→828, 130 samples,
   **67.313 s**. GTK completed four cycles/52 samples then chose the same-named
   scroll pane instead of the list box. Neither old result is relabelled sustained.

Original ZIP identities for both older iterations are retained in
`final-evidence.json`. All were independently authenticated on their own Actions
runs. The extra processing fixture amendment from 180,000 lines/9 MB to 60,000
lines/3 MB was disclosed before CI2; the former capability remains ungranted.
The final 30-second-per-cycle sustained dwell plan was disclosed before CI3.

## Root integration and remaining scope

Integrate only this package's owned paths, not product/SDK changes. Entry points:
`.github/workflows/reader-dot-d14.yml`, `build.py`, `run.py`, `contract.py`, native
platform drivers and `authenticate.py`; actual raw values live in original ZIPs.
Final evidence/document SHA is the subsequent docs-only `[skip ci]` commit, not
another tested harness. Publication denial was resolved by explicit owner approval
`Sentinel_3fc8195067848191984aeea41256b99b` (19:26:24 UTC).

Next work requires a separately authorized validation round: GTK should observe
real scan state with a reliable event-driven observer or a separately predeclared
bounded heavier fixture, and use modal-aware host cleanup; it must then truly
complete two stages. Do not infer an unobserved in-flight close from phase 3 or
inject a review gate. No fourth CI was started under this task.

Unresolved/ungranted: complete cross-platform lifecycle, GTK second process and
recovery, the 9 MB line-heavy TXT import, physical devices, batteries, days-long
continuous reading, screen readers, frame timing, leak-freedom, formal performance
budgets, total-product regression and archive permission/link preservation.
