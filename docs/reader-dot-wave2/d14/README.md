# D14 bounded native lifecycle observations

Not yet executed: `accepted=false`. This package owns only new D14 paths.

## Frozen identities

Harness base: `0889f7d1e9a537c6c1b05456547e016b26e1cd85`.
Windows target: `9321de84eb9c8d3d57cafbeaa8b0a28fe2a26a08`.
GTK target: `803098e9df1a365a9b8e206805c2d179aca8501f`.
SDK candidate: `edddc463c06ed5731195cdb8f06b2df6dff7699e`.
Read-only C02 contract: `169b0be3c1c8199be0211649412d23d9e34041e4`.
No C02 cold/warm/500/5000 measurements, budgets or existing results are changed.

## Predeclared plan

Per platform: two independent processes sharing only their runner-temporary profile;
three rounds per stage; TXT, EPUB, PDF and CBZ each round. Each cycle must complete
open, forward, backward, library, resume, search open/close, directory open/close,
records open/close, settings open/close and native picker cancel, in that order.
24 completed cycles (240 cycle actions), never attempted cycles. Stage one then
imports a fixed 3 MB scanning TXT, starts real search, observes actual processing,
and closes the host; stage two must be a distinct PID and prove no query replay.
Final stage must still complete all four formats and cleanly exit. Originals must
remain byte-identical. Only native import and ordinary implicit progress saves are
allowed; no annotation/settings commits, injection or review-gate substitutes.

Test ceiling is 45 minutes total per platform, separate from build time. Native
actions have finite deadlines; the runner also enforces 45 minutes. Any failure
stops subsequent cycles, preserves attempted/failed/completed actions and missing
scope, captures native windows/screenshot, and records cleanup/exit separately.

Every half-second while each product lives: RSS bytes, cumulative user/system CPU
seconds, threads, Windows handles/GDI or Linux fd count, PID/create time, timestamp,
and live child identities. These are resource observations, not leak-freedom,
frame-time, battery, multi-day, physical hardware or performance-budget claims.

All builds, fixtures, syntax checks, tests, screenshots and artifact byte parsing
are Actions-only. Same-run original ZIP verification checks unique artifact name,
ID, source/run/attempt, bytes, service SHA-256, expiry, every member hash, actual
program and font hash, and the complete explicit action/stage/resource contract.
Negative controls reject missing stages, fabricated counts, wrong PIDs, lost
failed actions, absent samples and identity mismatch. A green build is not a
lifecycle or artifact-authentication pass.

Entry points: `reader-dot-d14.yml`, `build.py`, `run.py`, platform drivers,
`contract.py`, `authenticate.py`. Existing target helper code is read-only.

## Retained iteration 1 / explicit fixture amendment

Run `40225172916`, attempt 1, harness `5f76251e6ab906740151ed60ca5fc034ce050bbf`
was terminal failure. Windows 12 completed cycles / 120 cycle actions, 67 resource
samples, PID 5148, clean cleanup exit 0, but the extra line-heavy 9 MB TXT did not
appear and the close-processing action failed; stage 2 did not run. The original
9 MB processing fixture and its failure remain in the original authenticated ZIP.
It is not retrospectively accepted. Prior frozen Windows perf documentation
records line-heavy >=7 MiB TXT as EXR_LIMIT. Iteration 2 changes this extra workload
to 60,000 lines / 3 MB, retaining the exact ordinary four-format cycle plan, and
waits for an observed shelf row rather than assuming import-idle means row-ready.
The original 9 MB import capability remains ungranted; original ZIP diagnosis is
printed early in Actions. GTK built correctly but its driver module name collided
with PyGObject's legacy `gtk` sentinel before launch (zero cycles). The fix loads
our platform modules under explicit unique names. No product edits.

Iteration 2 also records actual installed SDK header identity, corrects GDI query
handle rights, forces authored TXT LF bytes, binds each launched executable hash,
and records read-only absence of pending files and annotation rows per cycle.

## Retained iteration 2 and final selector repair

Run `40226184382` attempt 1, harness `c466aa835b412555cadd5a3734ea766f366b925a`:
Windows passed all 24 cycles and four lifecycle checks using two real PIDs
3328 and 828, with 130 resource observations over 67.313 seconds. Original
Windows ZIP ID 12611541837 and GTK ZIP ID 12610978837 were both independently
authenticated in Actions; the overall run still failed. GTK completed its first
four-format round (4 cycles, 52 resource samples), then the tool selected a
same-named `Bookshelf` scroll pane instead of the contained list box. Fixed target
source `examples/linux/reader.c:1055–1058` explicitly copies the child's accessible
name to the scroll wrapper. Final iteration constrains the exact native list-box
role and walks its visible rows, with one actual single click (the product's
single-click activation is enabled); it does not inject opening or skip the
failed loop. CI2 failure and raw native tree remain preserved and authenticated.
The CI2 early snapshot also confirmed the CI1 9 MB TXT failure verbatim:
`导入失败：超出宿主或SDK限制（Native parser failed (6)）`.

Explicit owner approval to continue D14 feature commits, pushes, remaining
Actions and final evidence seal was verified from room message
`Sentinel_3fc8195067848191984aeea41256b99b` at 19:26:24 UTC, answering the exact
scope request `Sentinel_38496d4b9f6881918e3a697844de0d02`.

## Predeclared final-iteration sustained dwell

The 67.313-second CI2 Windows result is **short-cycle coverage only**, not a
long-duration stability conclusion. Final iteration adds a fixed 30-second live
reading dwell after each of the same 24 completed cycles: at least 720 seconds
(12 minutes) of actual product dwell across two independent process stages, plus
UI-action time, still within the 45-minute overall test ceiling. RSS/CPU/handles
or fd/thread sampling continues every 0.5 seconds during every dwell. Product
exit/deadline is checked every 0.25 seconds; the next native action and screenshot
must still complete. Dwell has separate running/completed status, cycle identity
and measured duration; it never increments cycle counts. The contract rejects
missing/short/interrupted dwells and total runtime below 720 seconds. This is an
explicit plan amendment before the final run, not padding prior elapsed results,
CI build time, or introducing any performance/resource budget. The old short
iteration and its failures remain preserved.
