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
imports a fixed 9 MB scanning TXT, starts real search, observes actual processing,
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
