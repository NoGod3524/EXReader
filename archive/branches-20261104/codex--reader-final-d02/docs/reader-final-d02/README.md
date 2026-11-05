# D02 Windows compact DPI / keyboard / contrast audit

Status: automated audit completed and raw evidence verified in Actions run 40215441500; measured failures and pending scopes retained. `accepted=false`.

## Coverage inventory and reuse

* G12 `tests/reader_a11y_windows`: original named launch SH-01/02/04/06/07 assertions are called unchanged; UIA, SendInput and trace/session helpers reused. Original standalone runner hardcodes frozen SDK3.40 and is **not** misrepresented as a new run. Its broader 49-check audit is historical only.
* Windows host worker/metadata and preferences helpers: process launch, idle observation and raw BMP capture reused. `WM_COMMAND`, `BM_CLICK`, business callbacks and direct text replacement are not used to drive D02 interactions.
* Existing J/account, search/navigation/records/preferences checks already establish narrower module controls, persistence and four-format fixture construction. Existing compact 22-check suite uses command injection for some operations: its success is not keyboard evidence. D02 reuses its exact four original fixture files but drives genuine SendInput.
* New gaps: ON/OFF UIA name/role/state snapshots; forward/reverse Tab; native picker cancel and import; four-format keyboard open; no-mouse journey; More, search, directory, records, settings and account; baseline/small geometry; actual DPI/awareness/work area; high-contrast set/read/restore and system color palette.

## Immutable identity and no scope transfer

Harness base `0889f7d1e9a537c6c1b05456547e016b26e1cd85`; target `f355525b74ae261db536c56200e46643919ef323`. Producer source `eab342ef456be4a8a1811e5249e3c217d906ce8a`, run 40201283788 attempt 1, job 121192850915. The target differs from producer only in docs (guarded). D02 downloads raw artifact 12601764928 **inside Actions only**, authenticates exact ZIP byte count/SHA256/expiry/source/upstream job, then checks both actual executable hashes, CMake options and existing installed SDK identity file hashes. SDK `edddc463c06ed5731195cdb8f06b2df6dff7699e`, 3.41.0 / ABI1 / core3.40.0. This producer is statically linked: no separate SDK DSO hash exists; program and source/header/map identity are reported instead. No build, fixture or artifact operation runs locally.

## Interpretation

Audit completion is separate from product/keyboard/contrast/screen-reader acceptance. Real product failures produce `fail`; unavailable DPI scales produce `pending`; unexpected harness interruption produces `error` and fails Actions. No failures are changed to expected passes. A successful evidence verifier does not mean the reader passed accessibility acceptance.

DPI uses a session `SPI_SETLOGICALDPIOVERRIDE` request and reads actual window/system DPI. Relative override indices cannot force an absolute scale; only exact readback grants that one measured scale. Geometry never substitutes for DPI. Requests are reset; actual awareness is recorded. System high contrast is read, temporarily set, read back, captured and restored. GetSysColor WCAG ratios are palette evidence, not all-interface compliance. Text clipping and focus visibility require localized pixel/human review and remain pending rather than inferred from UIA rectangles or generic repaints.

Each real-keyboard failure includes the key trace, UIA tree, focus state and raw BMP. Later recovery uses Escape and is explicitly marked. No direct SetFocus recovery enters the no-mouse journey. NVDA, Narrator, real monitor changes, human reading and current unified production source remain unverified.

## Running / ownership

Only `.github/workflows/reader-final-d02.yml` on `codex/reader-final-d02` invokes D02. Native jobs run serially (one live workflow). Producer inputs in `contract.py` can be deliberately updated by the integrating owner together with their authenticated run/job/artifact identities. Original guards and product files are unchanged. The strict consumer rejects wrong run/attempt/source/program, duplicate/missing checks, tampered files and expired artifacts.

### Historical failures retained, not mixed with D02

G12 run 40084309431 measured unnamed search/note fields, missing page text provider, focus loss and Tab traps; no inference of persistence is made until D02 observations. Producer prior failed runs 40198400279 (dependency), 40199103895 (readiness), 40199849523 (fixed-page parser), 40200467006 (Ctrl+L conflict), and canceled 40197968923 (geometry) remain in target `docs/validation/reader-windows-compact.json` unchanged. These do not count as D02 retries and are never combined with D02 successes.

D02 first failed run: 40215115650 attempt 1, harness `01eae40b444c0414fca3e5256f1d188d709b5380`, native job 121234467615. Guard/syntax passed; producer raw ZIP redirect returned HTTP401 because urllib retained GitHub Authorization across hosts. No UI checks ran. Fix strips that header only on cross-host redirects to the already-authorized signed artifact URL; authentication, ZIP digest and expiration checks remain mandatory.

D02 second failed run: 40215226326 attempt 1, harness `8edd68c28d580dec5f6cc6d6c690839d58fadc98`, native 121234794426 / strict 121234975156. Producer identity authentication passed, actual OFF/ON host launch, DPI queries, layouts and initial G12 assertions executed. Native logging then failed on Chinese names under Windows cp1252 (`UnicodeEncodeError`); complete keyboard/contrast audit was not obtained. Raw artifact 12607680238, 216883 bytes, SHA256 `03bf27943e64b9fed86ba681862b4a8ec4f2350961e381bbe0f25d81811d77d7`, is retained. Fix configures only harness stdout/stderr UTF-8; product unchanged. Strict verification additionally scans current native job log and extracted current raw evidence for token/private-key/signed-query shapes and the ephemeral CI token without logging its value.

## Final evidence (docs-only seal)

[Run40215441500](https://github.com/NoGod3524/EXReader/actions/runs/40215441500), attempt1, harness `e8b5b1bd200202c06a7a22e5a4ed1f801eb47706`: native/strict jobs success. **Audit completed, not accepted.** OFF20pass/3fail/6pending;ON22pass/3fail/5pending;78BMPs. [FINDINGS.md](FINDINGS.md) gives precise observations/limitations; [validation.json](validation.json) contains complete source-bound strict output/file hashes. Earlier failed runs retained above. Current raw ZIP/source/job/expiry verified inside Actions; credential scan passed168inputs. Keyboard/contrast/screen-reader/product acceptance remains false.
