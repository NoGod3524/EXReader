# Windows native recovery prerequisites — 2026-10-29

## Current status

**Authored, not compiled or executed.** This is a seven-addition qualification package, not a Windows production recovery port. Neither source review nor the earlier POSIX results earn any of its 67 groups. Product admission, full P0, directory-fsync equivalence and physical power-loss qualification remain false.

The owner approved the exact seven-file implementation/publication/Actions package at 11:54:19 UTC, and explicitly approved the private-custody-boundary amendment at 12:11:33 UTC. Branch: `codex/migration-windows-native-qualification-20261029`. Predecessor: `acf892d4fe852dda4ed668589af53f7b3694f679`, tree `e3e2af970320f78a5c5990827b6189112f6ee40e`.

One Windows job: **24 new groups + 43 unchanged preflight groups = 67**. First run plus at most one independently reviewed repair; 30 minutes per job, 60 configured runner minutes total. All builds, tests, fixtures and artifact parsing are Actions-only. No current product target links this adapter. No SDK, predecessor source/test/assertion, old budget, main, PR, tag or release changes.

## Exact additions

1. `extras/migration/src/lm_recovery_win32_platform.h`
2. `extras/migration/src/lm_recovery_win32_platform.c`
3. `tests/migration/windows_recovery_native_20261029/CMakeLists.txt`
4. `tests/migration/windows_recovery_native_20261029/probe.c`
5. `tests/migration/windows_recovery_native_20261029/run.py`
6. `.github/workflows/migration-windows-native-qualification-20261029.yml`
7. `docs/MIGRATION-WINDOWS-NATIVE-QUALIFICATION-20261029.md`

The workflow requires exactly these seven additions against the tested predecessor and exact checkout/fetch identities. Every other predecessor byte remains frozen. The new consumer explicitly includes the unchanged preflight scanner/oracle implementation; it is not a hidden replacement SDK or second SQLite implementation. Both the frozen and new executable must match the installed single-static-provider dependency graph and exact MSVC public-symbol/archive/object definitions. Every native consumer invocation additionally checks installed SDK 3.42.0/ABI 1 and matching SQLite 3.54.0 header/runtime source ID. Schema6 fixtures come from actual pinned SDK 3.40 at `c2d23c29a3b2096c2236fdb414dcd1e66d3243b4`.

Python is explicitly 3.12 for both new and unchanged prerequisite scripts. This changes their selected interpreter, not their source or assertions. BUSY, syntax and read-only failures use actual numeric sqlite_errorcode, never message matching.

## Qualified namespace, if the native controls pass

Only a **new private custody directory on local fixed NTFS** is admitted. Target DBs, worker outputs, anchor, records and liveness slots reside within it. No UNC, device, ADS, ambiguous path, reparse/hardlink data alias, generic pre-existing target path or OS permission modification is authorized.

The root and adapter-created files have current TokenUser ownership and a protected DACL containing exactly current TokenUser and LocalSystem, each FILE_ALL_ACCESS (collapse duplicates when the user is System). Root directory ACEs inherit to children; adapter record ACEs are explicit/no-inheritance. Actual SDK-created DB/sidecar/clone files may inherit those **same two** principals, with exact allowed flags/mask and no third SID. This is not a claim that SDK files possess the adapter's explicit protected descriptor. Actual root SDDL and a bounded list of each outside ancestor’s full identity/type, requested access/share masks and observed SDDL are retained. Outside ACLs are observations, explicitly not classified as private or used as an expanded principal allowlist.

Outside system ancestors do not have to satisfy this private ACL. They are held as non-reparse, full-identity-bound namespace components, without write/delete sharing, for the operation. No administrators/Everyone/TrustedInstaller ACE is added to the private profile. This is the explicitly approved custody amendment, not a runtime waiver.

Creation-to-pinning uses the returned handle from relative `NtCreateFile(FILE_CREATE)` and requires `FILE_CREATED`; it does not infer that a later reopen is the object just created. The returned full FILE_ID_INFO volume+128-bit ID, private ACL and final pathname are checked while the handle is retained. The consumer reports the actual NTSTATUS and IO_STATUS_BLOCK information. The exact DIRECTORY/WRITE_THROUGH/SYNCHRONOUS_IO_NONALERT/OPEN_REPARSE_POINT combination is a required runtime capability with **no fallback**. Microsoft documents the constituent operations but the Win32 page's directory-compatible flag list does not expressly list OPEN_REPARSE_POINT; documentation alone is not claimed to prove this combination.

File IDs use 48 hexadecimal characters (64-bit volume plus 128-bit file ID), not truncated POSIX profile IDs. Adapter writes use CREATE_NEW, bounded full writes, same-handle FlushFileBuffers, exact reread and identity/path checks. Native publication uses held destination RootDirectory and no-replace FileRenameInfo; no copy/delete or cross-volume fallback. File flush, requested write-through and measured directory-handle flush remain separate observations. No privileged volume flush, backup/restore privilege, or directory-fsync/power-loss equivalence is inferred.

## Worker and SQLite ownership

A root anchor predeclares four exact slot inodes and four exact single-use record inodes before spawning. A use record transitions from empty to one canonical request under the outer lease, is flushed/reread, and binds kind, nonce, producer executable hash, root, slot, use inode and actual created output directory identity plus the parent-observed target FileID. The parent retains the exact created request inode/digest across wait, rather than adopting a reread digest as authority. Missing/replaced entries cannot vanish from accounting or regain capacity. Partial/foreign request bytes refuse.

Liveness uses a zero-sharing read/write file handle, not inherited LockFileEx semantics. Every child is created suspended with an explicit handle allowlist, assigned to the supervisor-owned Job Object, verified, then resumed. No breakaway fallback. Parent duplicates close without claiming the child exited. The independent Python supervisor retains the job while a killed coordinator's child or grandchild genuinely stays alive. Restart independently checks **all anchored slots before output availability**; whole-output disappearance cannot hide a busy slot. The control has two explicit phases: a real SDK-live orphan retains the output pin and must refuse rename; a separately paused, genuinely live pre-I/O/pre-pin child permits actual output disappearance and still excludes restart without opening the SDK. Cleanup terminates only exact retained process handles or the owned job, waits for exit, and latches unconfirmed cleanup to prohibit later launches. Closing a process handle is never used as termination evidence.

Children recheck the complete typed request/output/target envelope after GO and at the final exposed pre-I/O boundary. The actual output directory is then pinned without write/delete sharing through child I/O and process exit. A Unicode wmain wrapper performs bounded strict UTF-8 conversion, with no ANSI-codepage assumption. Child results bind actual waited PID, producer/request digest/nonce/root/type and literal SDK status. A free slot or a complete-looking result alone never grants restart success: the separate completion entry explicitly refuses without this invocation's actual wait proof. The descendant test intentionally retains a grandchild under the independent job; it is not mistaken for a successfully completed worker.

The native coordinator holds the real public SDK transaction from migration_open through snapshot comparison and the declared operation. Independent SQLite connections must observe numeric BUSY at the claimed fence boundaries and availability after owner release. The fresh scanner inherits no SQLite/SDK/outer-lease handle, reads a coherent full typed baseline and creates an isolated clone. Public SDK getters run on that clone; the Python oracle compares their ordered values to the independent **pre-owner original** projection before allowing continuation. Full typed state includes schema/index/rowid/type/content framing, not SELECT-star-only evidence. The frozen scanner's small-fixture backup_step(-1) is reused unchanged; no new arbitrary-library bounded-backup guarantee is claimed.

Fixture-only copy/mkdir/token modes deliberately permit controlled fault injection while the coordinator is paused; they are not product entrypoints or a production guard contract. The final positive handoff changes one declared book title through the public SDK, commits under the same owner, and retains baseline/anchor/prepare/ack evidence. Schema6 permits exactly the already-frozen empty schema7 additions and planned title change; all other data remains exact. Baseline, scanner baseline and result identities/bytes are rechecked before mutation/COMMIT and after completion. Later ordinary writers are preserved. No-op/ABA establishes current parity only, never historical rollback or COMMIT proof. This is **not the full production importer** and does not retire production pending evidence.

## Fixed new groups

| Group | Required actual evidence |
|---|---|
| 01 | Unicode/local NTFS/full ID, actual ACL and directory-flush measurement; numeric syntax calibration |
| 02 | Exact protected ACL; deliberately broader owned-file and private-root ACLs refuse (including owner pre-SDK gate) without changing content |
| 03 | CREATE_NEW occupied-name refusal preserves original ID/bytes |
| 04 | Full write/flush/reread plus independent reopened bytes |
| 05 | Actual process kill with incomplete JSON; restart refuses retained partial record |
| 06 | Actual read-only WriteFile/FlushFileBuffers access failures and native errors |
| 07 | Kill after flush but before acknowledgment; no invented completion |
| 08 | Complete-looking bytes plus real flush refusal remain untrusted |
| 09 | Reparse/symlink/junction/hardlink/ADS and post-precheck pinned-parent controls; outside canary exact |
| 10 | Equal-byte foreign baseline/request/output identities refuse at the relevant live gate |
| 11 | No-replace rename positive and occupied destination preservation |
| 12 | Actual no-delete-share source-open refusal before publication; retained source |
| 13 | Outer coordinator exclusion while the actual SDK writer remains BUSY |
| 14 | Inherited zero-sharing handle excludes after parent duplicate closes |
| 15 | Real parent death/live child with whole-output disappearance; anchored exclusion persists |
| 16 | GO EOF and actual pre-resume invalid-job failure; no late SDK open |
| 17 | Wrong kind/nonce/producer/output plus absent/partial result; dependent work refused |
| 18 | Actual wait + complete typed result; lock-free restart still cannot invent wait proof |
| 19 | Real descendant-held slot; exact bounded job cleanup and later availability |
| 20 | SDK schema6/7 × DELETE/WAL, numeric BUSY/available/read-only controls and complete original parity |
| 21 | Fresh full typed scanner + independently expected ordered public projections |
| 22 | Actual Windows journal-delete sharing refusal during public SDK finish, exact SQLite OS filename/phase/code, literal SDK return and observed retained journal |
| 23 | Later changed writer refusal/preservation; no-op/ABA current-parity-only controls |
| 24 | Complete bounded test-consumer handoff, real title update/COMMIT, fresh original-data oracle and later-writer preservation |

All required positives and refusals must pass. Missing symlink/job/NTFS/API capability is a named failed group, never a skipped pass. The 43 frozen preflight groups are a separate mandatory prerequisite; continue-on-error only permits collecting both suites, while the final aggregate requires exactly 67/67. Group22 does **not** demand a non-OK SDK return: prior evidence demonstrated internal rollback I/O can coexist with SDK OK. It records the actual return and internal error separately and does not assert data loss.

## Bounds and retained evidence

Each helper has an absolute 120-second supervisor lifetime (native cooperative deadline 115 seconds), followed only by bounded exact cleanup. The job enforces 512 MiB/process, 1 GiB/job and 60 CPU seconds/helper; unconfirmed cleanup stops new launches. Native stdout is limited to 2 MiB by the supervisor. The adapter reserves 1 MiB/record, cumulative 64 MiB per invocation and a current root inventory ceiling of 64 MiB/4096 entries before adapter writes; SDK/SQLite external writes are **not kernel-enforced disk quotas**. Only finite known fixtures are qualified.

The driver checks/reserves 1 GiB fixture plus 64 MiB report headroom against a 4 GiB planned workspace and limits reports to 64 MiB. Actual child, sidecar and log growth is observed/refused; it is not sold as arbitrary-file hard quota. The job timeout remains the ultimate native/blocking-call bound. Evidence copying has its own four-minute Actions step bound plus a 180-second cooperative stream deadline, 30,000-node/1 GiB total/64 MiB-file limits. It retains pinned no-write/no-delete-share ancestor/directory handles, opens regular files no-follow, and stores reparse metadata without following or extracting targets. The immutable INCOMPLETE receipt survives failures. The final manifest is incrementally bounded to 8 MiB, includes at most 28,000 source entries and 4096 UTF-8 bytes/32 components per relative path, and is published from fully flushed/reread staging with no replacement. A 16 MiB reserve includes manifest/receipts inside the 1 GiB output budget; the destination is re-inventoried with an overall 30,000-node cap. Actual helper controls cover manifest budget, overlong path and interrupted final write. Shared max+1 protocol reads have exact-limit/one-over/growth controls. Original failure logs/records remain; no local artifact parse occurs.

## Previous evidence and remaining product work

The previous POSIX new-target result remains `acf892d4` / Actions `40864739308/1`, 270/270. Its first 262/270 failure and earlier existing-target 198/198, original red historical migration gate, SDK error-observability limitation, old frozen-handoff failures, and physical-durability gaps are retained; this new package does not erase or re-earn them.

Even a future 67/67 would only qualify these native prerequisites. Windows real existing-target importer recovery, Windows new-target publication, every product entrypoint's guard/record profile, capacity and full common-source integration remain separately authorized work. Fixed108 F12 also requires final-version compatibility, licensing/dependencies and complete user installation/import/sync documentation across the common source. Formal verified count remains 83/108, with no new formal credit from this qualification.

## Primary API contracts

- [NtCreateFile](https://learn.microsoft.com/en-us/windows/win32/api/winternl/nf-winternl-ntcreatefile): relative handle-bound creation and returned creation status; exact flags still require native qualification.
- [CreateFileW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew): exclusive creation, sharing and reparse handling.
- [Handle inheritance](https://learn.microsoft.com/en-us/windows/win32/procthread/inheritance) and [process creation attributes](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute): explicit handle allowlists.
- [CloseHandle](https://learn.microsoft.com/en-us/windows/win32/api/handleapi/nf-handleapi-closehandle): closing a process handle is not terminating its process.
- [FILE_RENAME_INFO](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_rename_info) and [FlushFileBuffers](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-flushfilebuffers): native publication and file flush, not inferred directory/power-loss guarantees.
