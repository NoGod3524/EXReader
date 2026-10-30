# Windows private supervised observer engine, 2026-10-30

Status: source implementation; Actions acceptance pending. Default OFF.
This package implements an actual installed worker and supervisor, not a mock
or a replacement for frozen SDK/public ABI, POSIX recovery or legacy formats.

The supervisor pins the actual worker image with write/delete sharing denied,
hashes that held image, and opens a separate read-only/no-write/no-delete target
custody handle bound to the caller's complete volume64/FileID128 identity.
A bounded binary request binds configured source SHA, caller nonce, private
root/parent/full target IDs and worker image SHA. The worker inherits only the
request/output and reduced-read target handles, hashes the target twice and
returns the exact request plus observed bytes/hash. Parent rehashes the held
target and validates exact result size, identity and request equality.

The existing qualified adapter launches suspended, assigns a bounded kill-on-close
job before resume, and restricts inherited handles. Worker completion alone is
insufficient: active job descendants must be zero. Timeout/descendant failure
terminates the owned job and boundedly verifies quiescence; unconfirmed cleanup
is LM_WE_UNCERTAIN. Output is exclusive-created and retained on every outcome.
The caller must keep its wr_context alive throughout; no target path is accepted
from a worker response.

**LM_WE_OBSERVED is only a stable-byte observation.** It is not semantic database
validation, a COMMIT receipt, migration admission or permission to reopen.
The full migration importer/state machine, readonly SQLite logical snapshot,
crash recovery records, shared lifetime host-admission lease, cross-directory
publication integration and independent admit_reopen are still required.
No fake implementation of these gates is supplied and no lr_* stub is enabled.
Private Windows publisher and host-controller packages remain separate work.

Build via extras/migration with EXR_MIGRATION_WINDOWS_ENGINE_CANDIDATE=ON and
EXR_WINDOWS_ENGINE_SOURCE=<full current SHA>; the ordinary default is OFF.
Installed outputs: exreader-migration-windows-engine.lib,
exreader-migration-windows-observer.exe and private tool headers.
No changes to lm_main.c are necessary for this observation-only slice.

Actions builds the frozen SDK, installs the engine/worker, compiles a separate
installed consumer, checks actual image hash, full identities, exact output,
write-custody refusal, duplicate output, wrong worker hash, invalid nonce and
timeout bounds. Provider maps and raw bytes are retained, but full F07 provider
closure is not inferred from those files' mere existence. Full P0 stays false.

First Actions run 41019391474 at c57f6bb8c1a753dd21afcb5c9d8d3bbc24098f7e built and installed the actual engine/worker and external consumer. Native checks: 14/21 passed; positive observation failed with six dependent receipt assertions. The retained output file existed and was readable. Reason was not logged; diagnostic-only follow-up preserves every assertion. Failed artifact 12961181839, 238731 bytes, SHA256 6d561b7cf6c1f0054f7de49af86ae3995093e7b4221cc41e6252586c4058c767 remains failed.

Diagnostic run 41022244832 at 9bdb7452 failed the same 14/21 boundary: observer-live-descendants, worker exit0, worker terminal, eventual cleanup confirmed. Native122 was not yet attributable because the query boolean conflated query errors and active counts. Follow-up records actual query error/count and at most1s of observations within the original overall timeout; initial nonzero/query error still fails even if later zero. No acceptance or timeout relaxation.

Run 41022763085 at ac2ee136 confirmed successful query, initial_active=1, last_active=0 after one10ms sample; worker exit0. It remains a failed diagnostic run. The authorized fix waits for actual zero within the original overall deadline, subtracting setup time from worker wait. Query failures and remaining active processes at deadline still refuse. New real Event-handle query-error and live sleeping-process deadline controls supplement every original assertion; cleanup is confirmed, retained empty deadline output is evidence, not success.

Bounded-wait run41023412188 source060c7a5d passed27/28 checks: all original21, real query-error control and real live-process deadline refusal passed. New terminal/cleanup conjunction failed. Retain artifact12963120268/242266B/SHA256d40b1084dfc8c8a3bc6d864032b8688ba6955de7b36c124860f0da86822d9eb9. Add exact cleanup-state diagnostics; do not infer clean containment or relax the assertion.

Run41023948573/source871a0bc5 measured process-deadline1460 with job-zero flags but cleanup-unconfirmed from the subsequent process-handle check. The cleanup branch had treated zero accounting as process signaling. Repair requires both the actual process handle signaled and zero job count, plus a terminal exit code, within the unchanged10s termination-cleanup budget. Failure remains UNCERTAIN; original observation deadline and all28 checks remain unchanged.

The final negative control additionally requires actual forced-exit125 with the original ERROR_TIMEOUT, and independently checks the retained deadline output is empty. All prior28 checks remain; final count29. No sleeping-process timeout is relabeled observation success.


## 2026-10-30 safety repair candidate (not yet accepted)
Retains every original 29-check assertion and prior failed runs. Added final
same-deadline acceptance gate after parent readback; synchronous I/O remains
potentially blocking and the independent cleanup budget remains 10 seconds.
Worker input is drive-absolute; launch uses a revalidated Volume-GUID path with
non-reparse ancestor pins retained alongside the hashed leaf. A process-wide
atomic gate serializes calls. Unconfirmed cleanup permanently quarantines the
job/process/image/target/output and duplicate root/namespace pins; no reset API.
A separately compiled native boundary harness injects delayed final hashing and
query/termination refusal, with an actual main-exits/child-lives executable.
Those injections are not compiled into the installed engine. These are observer
safety prerequisites, never migration COMMIT, SDK reopen, F07 or full P0 admission.


### Retained first repair failure and launch correction
Source 7b26bf301b9a658633f11a52b781d9fd5b7ec874, run41085547489 attempt1,
job124165630772 compiled and installed successfully but the original consumer
failed10/29: the GUID executable path was refused before resume (native87).
Artifact12992405490,245108 bytes,SHA256
a2dd6e12789717b64c8dd3551a9ab1a767bc724c65f66312825153ef24b5d1d0.
No assertion was relaxed. New private launcher uses canonical DOS only to create
a suspended process. Before any ResumeThread it requires strict native pathname
equality and a full-ID reopen through GLOBALROOT against the pinned image, plus
verified job membership. GUID namespace pins remain held throughout. The frozen
adapter is unchanged and its wr_cleanup_uncertain latch is respected.
The new boundary suite additionally rejects an injected launched-image mismatch
before execution; gate2 now returns UNCERTAIN, not a clean refusal.

## Qualified observer safety repair evidence (2026-10-30 16:13 UTC)

Tested source: `83b0bd1c1d2d697973ef43272d42b34cc58baa7f`.
GitHub Actions run `41087206035`, attempt1, job `124171372303`: success.
Original installed-consumer assertions: **29/29 unchanged**. Separate native
fault-boundary suite: **21/21**. Installed worker/archive byte parity passed.
The boundary suite uses test-only call wrappers and a real main-exits/child-lives
fixture, not production fault switches. It covers relative, drive-relative and
root-relative worker refusals; wrong launched-image refusal before resume with
empty output; delayed final hash rejected by the original absolute deadline;
query and termination failure with a live descendant, retained image custody,
and permanent no-relaunch quarantine. This verifies observer prerequisites only.

Original artifact: `12991588693`, name
`windows-engine-83b0bd1c1d2d697973ef43272d42b34cc58baa7f`;
21 files,250290 bytes,SHA256
`daa5f7b6ab686de1340a73dd80d626e01fd8157487447da651c2cb7ed3c4e913`.
Independent source review of this exact SHA found no blocking source defect.
Independent original-ZIP audit remains pending; metadata/log verification is not
a substitute for that audit.

Earlier failures are retained, not overwritten: initial14/21
`41019391474`; diagnostics14/21 `41022244832` and `41022763085`;
bounded-wait27/28 `41023412188`; cleanup diagnostic27/28 `41023948573`;
the 28-control green `41024463623` and earlier29-control green
`41024553069` are distinct sources, never combined into this run.
The GUID-path runtime failure `41085547489` remains documented above.

Important boundaries: the deadline governs acceptance, not an upper bound on
synchronous I/O; cleanup retains its separate original10-second bound.
A busy refusal proves only that this call did not launch, not that another call
is terminal. An uncertain gate or inherited adapter latch remains UNCERTAIN.
Quarantine is process-lifetime and instance-scoped, not cross-process admission.
OBSERVED authenticates bytes and identities, not SDK logical validity, migration
COMMIT, independent reopen, durable recovery, final-provider F07 or full P0.
The caller must retain external admission on UNCERTAIN. No public SDK/ABI,
frozen adapter, original consumer assertion or common/staged branch changed.
