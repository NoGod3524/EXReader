# C02 native journal candidate

This is C02's native storage stage. Full C02 still requires a persistent domain gate, actual owner/reader wiring and end-to-end verification. Formal acceptance remains 95/108.

## Custody and scope

Worktree /data/workspace/exreader-dot-c02-native-journal-20261030, branch codex/dot-c02-native-journal-20261030, baseline a8d0b162d8c21617e4c2c837e3eb2b2174bbf69b. Original partial files are preserved in commit e150f6f5.

Original header: 1694 bytes, SHA256 de93266dae6fbf3e62f4cba9822331884b9b376a26e3cd29482818ff70515f34.
Original source: 8400 bytes, SHA256 e273a27b33646b2776c89057b0c85413bd1d86cf883df005d0ee5418dc7114c5.

Only the original seven candidate paths change. ABI2, ABI3, C01, SDK, production owners, Apple, F12 and H02 are unchanged. The original conversation explicitly approved this package and one two-job Actions run. The current user additionally instructed full completion of C02. Writes use the same lap25002 Desktop Commander / saved official InstaBox CLI route.

## Transaction

Open validates the entire length-framed journal and canonical BEGIN/ACK chain. It rejects empty intent with nonempty journal, nonzero reserved bytes, missing/duplicate sequences, skipped/duplicated old counts, wrong ACK bindings and torn records. No implicit bootstrap or repair is performed.

Append borrows the domain; revalidates original input prefixes and file identities; rereads the actual full disk chain and exact expected tip; validates the prospective chain; writes and flushes BEGIN; appends and flushes the journal; independently reads it through a new identity-checked handle; writes/flushed ACK; and independently verifies the entire intent chain. OK returns the actual disk tip. MISMATCH before BEGIN leaves both files byte-identical. Every failure after attempting BEGIN is UNCERTAIN.

Directory pins use FILE_LIST_DIRECTORY plus attributes to participate in sharing checks, without write/delete sharing. Journal and intent use exclusive-writer sharing and WRITE_THROUGH. Revalidation checks original path prefixes, file IDs, volumes, non-reparse attributes and single-link counts.

## Planned checks, not results

The original 20-case/80-check proposal was expanded to 46 scenarios within the same test file. Actual counts and outcomes come from Actions.

Windows tests installed libraries with real NTFS files and child processes. Inherited event barriers select ten exact kill points: PRE_BEGIN, partial BEGIN, BEGIN_FLUSHED, partial length header, partial body, JOURNAL_WRITTEN, JOURNAL_FLUSHED, partial ACK, ACK_WRITTEN before flush confirmation, and ACK_FLUSHED before return. No sleep chooses the crash point.

A complete ACK may be visible after termination even without a delivered receipt. A fresh process must reject oldexpected without writes; only exact newtip may continue. Short-write controls write real prefixes; flush/readback controls inject API failure and are labeled separately.

Other scenarios cover both writer startup orders, case aliases, readonly sharing in both orders, initial/post-open hardlinks, actual ancestor rename and delete/write-capable opens with exact OS errors, an initial junction, and descendant replacement at an open barrier. Semantic attacks are resealed before reopening: reserved bytes, duplicated/skipped counts, false ACK binding, sequence gaps, empty-intent bootstrap, interior corruption and torn records.

Both jobs rerun unchanged ABI3 16 cases/64 checks and unchanged ABI2 81 checks. ABI2's six prior failures remain raw failures and keep the jobs/run red. Native and ABI3 outcomes are separate. Compilation, syntax checks, fixture creation, testing and artifact parsing occur only in Actions.

## Remaining C02 obligations

The domain callbacks are test controls, not a production domain gate. Poison appends a best-effort malformed suffix; if the device rejects all writes, this cannot promise persistent isolation. The actual domain must establish durable pending state before migration, retain it through errors and process death, and make every real reader consult the same gate. Closing native handles does not release that gate or mark CLEAN.

Process termination is not power-loss testing. Independent reads may still use OS cache. Administrative/raw-volume modification and pre-existing writable mappings require the real domain threat model.

Next phases: persistent domain isolation; coordinated Windows/GTK/Android/Apple owner and borrow-lifetime wiring; same-source end-to-end recovery/admission checks; independent original-ZIP audit binding source/run/attempt/job/artifact. This candidate does not grant SDK admission or full P0 acceptance.

## Run record

Pending the one authorized push-triggered validation. No build or test success is claimed yet.

### First run: preserved failure

Source 8bfe57395de52f221f4abeb50f3f80cc12d90198, run https://github.com/NoGod3524/EXReader/actions/runs/41151540486, attempt 1.

Windows job 124388962762: native archive and installed consumer compiled successfully. Native result: 46 scenarios, 299 checks, 3 failures (296 passing). All three failures are in unpinned-descendant-rebind-during-open: the move did not occur, replacement creation failed, and the unchanged trusted root opened. Ten deterministic crash scenarios, other identity controls, all fault controls and resealed semantic attacks passed in this source. This is a failing candidate, not native acceptance.

The successful-rebind fixture stopped after pinning the target parent, which already prevented the namespace change. The correction stops immediately after pinning the volume root; it first proves that the target can be renamed/restored, then requires the actual mid-open replacement to succeed and trusted root identity to reject it. No production code or assertion of identity rejection is removed.

Ubuntu job 124388962467 and Windows each retain ABI2 81 checks / 6 failures. Both ABI3 steps succeeded against unchanged 16-case/64-check assertions. Entire run conclusion: failure.

GitHub artifact metadata, not independently rehashed ZIPs:
- Windows ID 13023092516, 32864 bytes, SHA256 2169ef787169b502a8906bb2fcaa0845be7e8a74f063d1dc340fc42097ffd602.
- Ubuntu ID 13022813222, 1677 bytes, SHA256 ff2258f216bf01a1493e9db610e0564b4498b126aa0fc083e09710fb98cfa887.

The one originally authorized run is consumed. The corrected fixture is prepared for a separately authorized next run; no automatic retry has been started.

### Approved correction run: native storage passes

The user approved exactly one additional two-job round after the first failure. Source 867ca3cd9aaa58acb5b4a5ace35370b50383e2f8, run https://github.com/NoGod3524/EXReader/actions/runs/41151974177, attempt 1.

Windows job 124390323488: native installed consumer passed all 46 scenarios / 301 checks / 0 failures. The path-rebinding fixture recorded `OBS midopen root_move=1 error=0 reached=101`; trusted identity then refused the actual replacement. Only the fixture and this record changed from the first run; native library source is identical.

Windows and Ubuntu job 124390323249 both retained ABI3 16 cases / 64 checks / 0 failures and ABI2 81 checks / 6 failures. Each job's only failed step is the original ABI2 consumer. Overall conclusion remains failure.

Exact producer artifact metadata:
- Windows ID 13023637120, 33171 bytes, SHA256 0c4e066105bc80256c4025569de566edef47503346f74009561654f9c1b25b3d.
- Ubuntu ID 13023372361, 1673 bytes, SHA256 6a6af3956d5dfd3d897e7709df36b0ac617d7134990aaaa5de9da77ef23bd93d.

Both authorized native validation rounds have now been used.

### Prepared original-ZIP audit

The existing workflow now has a separate audit-only path, selected by the commit marker `[c02-audit-only]`. That path skips both native matrix jobs and runs one Ubuntu job, at most 15 minutes. No further validation starts until separately approved.

The audit binds the exact producer source, run, attempt, two job IDs and artifact IDs above. Inside Actions only, it downloads both original ZIPs, verifies their exact sizes and SHA256 values, checks every internal inventory entry, parses all raw native journal/intent pairs, and verifies the ten observed process barriers and successful path replacement. It rejects seven semantic mutations after recomputing the package's internal inventory: wrong source, wrong run, wrong attempt, false full-P0 claim, resealed reserved bytes, resealed duplicate/gap counts, and changed interior journal bytes. After parsing it rehashes and retains both untouched original ZIPs in the audit artifact.

This is a separately implemented artifact audit, not an independent human review. Its result is pending. It grants no production admission. Persistent gate and actual owner/reader lifetime wiring remain required for full C02.

### Production integration inventory prepared after native validation

Read-only inspection of the candidate tree found the following actual entry and ownership boundaries. These are implementation obligations, not completed wiring.

| Owner | Actual entry | Lifetime that must retain admission |
| --- | --- | --- |
| Windows product | `examples/reader.c`, WinMain SDK open at line 6437; presence gate in `apps/reader/desktop/windows_migration_gate.h` | Keep shared custody through worker shutdown and session/source/fixed-reader destruction, then SDK close at line 6316. Presence checks alone do not exclude a later migrator. |
| GTK product | `examples/linux/reading.c`, `linux_reader_open` / `linux_reader_close` | Acquire before SDK open at line 273; release after batch, navigation, search, account jobs, session and wave-3 owners close. The existing `.product.lock` is a separate catalog lock. |
| Apple product | `examples/apple/HostSDK.swift`, `HostLibrary.init/deinit`; independent opens in `HostModel.swift` | Every HostLibrary instance needs the same domain check. HostPublication already retains HostLibrary; HostSession/back-to-library also retains it. Source fingerprint/export operations release scoped sources. A return to the shelf is not final release. |
| Android product | `examples/android/app/src/main/cpp/exreader_host_jni.c`, NativeLibrary nativeOpen/nativeClose; Java `NativeLibrary.java` | Source currently has no parent borrow. BoundedEpub, NativeSearch and NativeNavigation keep native objects after their open calls; each needs a retained borrow through actual native close. Defer the library's gate release until all such objects finish, including exceptional construction paths. |
| Helper readers | `apps/reader/local-downloads/src/local_downloads.c:889` | The open is verification of a newly made private backup, not an additional open of the original library. Classify and protect its namespace while verifying; do not silently treat it as public-target admission. |
| Migration owner and observers | `extras/migration/src/lm_main.c`, `lm_recovery.c`, `lm_new_target.c`, worker executable | Owner admission must precede snapshot, stage, target SDK open and publication. Child observers need tracked live borrows; recovery must prove worker termination before any terminal release. Windows recovery currently returns platform-unqualified, so installing the journal alone cannot activate it. |

The frozen SDK's source retains its database owner after `exr_library_close` (`include/exr/library.h` and `src/library.c`). Fixed-source CBZ readers can also retain that source internally. Intercepting only source calls made directly by a host would therefore miss real borrows. Keep custody with each host owner and its derived reader objects, with tests that close the parent before releasing the final child.

Persistent gate contract for the next stage:
- Read an independently trusted domain-to-full49 mapping and exact object identities before taking custody. H01 validates the shape of supplied JSON; it supplies neither registry provenance nor SDK authority.
- Under exclusive custody, durably establish PENDING before the first migration write. A failed, short or unknown gate write grants no mutation capability. Native journal poison must never rely on a second write succeeding.
- Every ordinary reader acquires shared custody, verifies the full persisted state and expected generation while held, and retains custody until its final borrow. Missing, truncated, replaced or unresolved gate state refuses SDK open; it is never silently initialized.
- Recovery acquires fresh exclusive custody and matches the exact actual journal/intent tip, actual publication state and terminal worker evidence. A string identity, a green test receipt, closing a handle or returning to the shelf cannot clear PENDING.
- Establish CLEAN only after the terminal journal, publication/abort proof and all worker/borrow obligations agree. The known C01 generation-5/PENDING-0 drift must remain isolated after killing the holder.
- Bootstrap/enrollment is a separate explicit operation over a proved initial state. Its trusted registry and native object binding must be implemented before production use; no automatic empty-file repair is allowed.

Required integration evidence includes real source/publication/pager/search/navigation/export borrows surviving parent close; both reader/writer acquisition orders; killed-owner fresh-reader refusal; missing/replaced gate refusal; generation drift with PENDING cleared in C01; failed persistence with subsequent writes denied; and recovery using only the exact acknowledged tip. Existing 46 native scenarios, ABI3 16/64 and ABI2 81/6 remain preserved.

No production-owner file was changed during this inventory. Apple Features helpers/admission/workflows, F12's audit files, H01 and H02 account handlers remain outside this writer's changes.

### Original-ZIP audit completed

Audit source ff4bed4356db38835cbdae997e86d37f60e46af2, run https://github.com/NoGod3524/EXReader/actions/runs/41155803873, attempt 1, job 124402210551: success. The native matrix was skipped. Both exact producer ZIPs passed size/digest/inventory/semantic verification; all seven internally rehashed mutations were rejected. Both original ZIPs were rehashed again after parsing and retained intact.

Audit artifact ID 13024233704, 19998 bytes, GitHub ZIP SHA256 7e8dc0e71ae1025660f22b3dbac62b0850f28ad03a2222b8268e8fd5b9dc5bd5. Its producer remains 867ca3cd9aaa58acb5b4a5ace35370b50383e2f8 / 41151974177 / attempt 1, not the audit source. The original producer run remains failed solely on its preserved ABI2 checks.

### Persistent gate implementation and continuing authorization

After approving the audit, the user explicitly authorized continued C02 implementation, independent-branch pushes and necessary verification without per-round confirmation. Previous per-round CI limits therefore no longer block C02 work. Frozen C01/SDK and original test contracts remain preserved.

The native library now adds an independently stored append-only admission object. Explicit enrollment operates only on an already existing, trusted, empty object; ordinary opens never create or repair it. Every prefix is pinned, the exact root/file identities are revalidated, and shared/exclusive whole-file locks enforce actual cross-process custody.

BEGIN is flushed and reread before the gate issues a capability. A journal error poisons the live holder while the prior PENDING record remains sufficient to isolate a fresh process, without depending on another disk write succeeding. An open journal retains gate storage; a live journal or per-call borrow prevents premature close.

Reader grants contain both the exact generation and the complete last-record seal from an independently trusted registry. Readers never derive a newer grant from the gate file. CLEAN requires the complete actual terminal journal plus the owner's independent proof of actual publication/abort and terminated workers. A failed CLEAN write/flush/readback returns no new grant. A fresh exclusive recovery can reconcile a completely written terminal state only after checking the caller's exact tip and independently proving publication again.

The added installed consumer plans 28 scenarios, including four deterministic process-kill barriers, missing/truncated/aliased objects, both lock orders, failed gate and journal writes, retained journal references, exact-tip recovery and the frozen C01 generation-5/PENDING-0 drift. The C01 implementation is extracted from its exact frozen commit inside Actions and compiled unchanged. Existing 46-case native, 16/64 ABI3 and 81/6 ABI2 checks continue in their original jobs.

Gate test publication proof is deliberately a control. Actual trusted-registry, publisher, recovery worker and product-host integration remain in progress; no full C02 score is claimed by this library-stage test.

### First persistent-gate run: configuration failure retained

Source 83d85a7e21ccae5936f9f54fc8feb2774664acef. Native regression run https://github.com/NoGod3524/EXReader/actions/runs/41157097677 / attempt 1 built the extended native archive successfully; the native 46-case step and both ABI3 steps passed. Both original ABI2 steps retained their six failures.

The separate gate run https://github.com/NoGod3524/EXReader/actions/runs/41157097763 / attempt 1 stopped while configuring its installed consumer: the Windows C01 source path contained backslashes, and CMake rejected the resulting source-list escape. The gate executable was not compiled or run. The correction normalizes this input with CMake's TO_CMAKE_PATH before adding the unchanged frozen source. No assertion, case or provider code is removed.

### Persistent gate validation passed

Source 13e06ca5bc808cce5279d9101b88b64544fa1907, run https://github.com/NoGod3524/EXReader/actions/runs/41157310400 / attempt 1, Windows job 124406831183: 28 scenarios / 309 checks / 0 failures. The four process barriers (201, 202, 203, 204), both cross-process lock orders and the actual frozen C01 drift passed.

Artifact 13025791064: 39970 bytes, GitHub ZIP SHA256 5afec0359aeb2c5963008dcd558fe6005ca045d15964be077cd072dc4eef1551. This is a gate-component result; its publication callback remains a test control.

### Actual host borrow lifetimes

The Android source, search and navigation owners now retain explicit NativeLibrary borrows until native teardown completes. Parent close refuses new work and defers native library close until the last borrower releases. Failed construction releases its borrow after JNI cleanup; a failed close does not prematurely release it.

Each BoundedEpub native pager has its own borrow, including a candidate PageLoad that has not been committed. Closing the parent cannot release that candidate's admission. A late commit after reader close refuses and disposes the candidate. Apple HostFixed now strongly retains HostLibrary through exr_fixed_free, matching HostPublication's existing ownership.

A separate C02 workflow builds the actual Android and macOS products against the unchanged SDK 3.42 source. It reuses existing build recipes but records its own C02 provenance; it does not reuse the old package guard's restricted branch claim. Live admission wiring and native publication/recovery are still required before C02 completion.

### First actual-host build: setup failures retained

Source 6750ca5ce97abe8c02b625accab65285cb2a1e1e, run https://github.com/NoGod3524/EXReader/actions/runs/41158383462 / attempt 1. Android job 124410152477 stopped at the new C02 guard: it incorrectly compared the separately frozen C01 tree against this branch, where C01 has never been merged. The corrected guard checks this branch against its actual baseline and verifies the frozen source object separately. The existing gate consumer still extracts and compiles that exact C01 source.

macOS job 124410152702 built and installed the frozen SDK, then stopped before compiling the host because the independent OPDSHash prefix was absent. The C02 workflow now installs that existing dependency for each target and passes its canonical prefix. No SDK or existing build recipe changes. Both jobs now retain a C02 receipt even if an early configuration fails.

The first configuration-fix commit 17c66b38921792b7a13c958f81f75d0b9fb900f5 contains an interrupted workflow write. Its run is ineligible for build evidence regardless of conclusion: the truncated recipe has no complete host build. The completed workflow is verified byte-for-byte against the authored source before the corrective commit. Commit/push is now stopped whenever a source-transfer result is incomplete.

### Actual Android and macOS products built

Source 8f4f311fb16e7201e02340fd658c13617c0f2936, run https://github.com/NoGod3524/EXReader/actions/runs/41159005963 / attempt 1: Android job 124412117716 and macOS job 124412117932 both completed the actual product build. This validates compilation/linking of the owner changes against frozen SDK 3.42, not admission behavior on those platforms.

Artifacts: Android 13026571265, 65242 bytes, SHA256 ac3efcb2e35b87cfc7889f4f500dc63dd520313ace65ead32b5b9f87b3052664; macOS 13026154827, 21796 bytes, SHA256 4fa735a2e664fb3bc28ed1e43f4c9e043eefa3f9d906bc46728ae8809faf1632. Digests are GitHub original-ZIP metadata pending independent ZIP audit.

### Windows trusted registry and actual product entry

The new Windows registry adapter anchors registration in HKCU Software/EXReaderC02Admission, with explicit protected current-user/SYSTEM ACLs. It rejects registry links, weak ACLs and noncanonical bindings. The binding records the native root/admission/journal/intent/target identities and exact acknowledged gate generation plus seal. Ordinary open never creates a key, file or grant. Enrollment is separate, requires empty native objects and independent initial-state proof while held.

Shared open pins the target namespace and actual library FileID and holds the persistent gate. Owner begin persists PENDING before issuing a capability. Publication can release the owner's target pin only while that capability is live; successful terminal journal and independent published-target proof precede registry advancement. A fresh explicit recovery can reconcile an unacknowledged native CLEAN with the old trusted grant. Registry publication is the final authority publication after the native CLEAN receipt and actual proof; an ambiguous registry API result is not reported as success.

The actual Windows product now requires this installed admission provider and acquires shared registration before ordinary SDK open. Its cleanup releases registration only after workers, sources and session owners are torn down and the SDK library closes. The separate native consumer plans 14 registry/SDK cases and 6 actual-product checks. Its publication operation uses a real replacement SDK database and independent SDK source-byte verification; orchestration remains test code, not the production migration coordinator.

Still required: production enrollment and enrollment recovery; the actual migration coordinator/publisher and worker recovery; explicit recovery of partial native journal records; transaction journal rollover; Android/Apple/GTK persistent admission adapters and runtime borrower tests; final same-source acceptance and original-ZIP audit. Existing standalone self-test/private-backup namespaces must also be classified before full entry-point coverage is claimed. Formal acceptance remains 95/108.

### First registry/product validation: native publication still failing

Source 4608e35c49c66b06392fa058d042edf12cb55b64, registry run https://github.com/NoGod3524/EXReader/actions/runs/41159961403 / attempt 1, job 124415112620. Native registration, frozen SDK, installed consumer and actual Windows product all compiled. The registry consumer reported 14 cases / 110 checks / 9 failures. One failure is a test-driver misuse of the existing finish(handle, kill_boolean) helper, which already performs TerminateProcess; the correction invokes it once. The other eight failures originate in actual target rename/publication and its dependent proof/admission checks. The next run records exact native delete-open, parent-write-open and each rename result before choosing a repair. Assertions remain intact.

Artifact 13027001137, 51894 bytes, SHA256 a490f9a5429b8f7e1f9301a5a581e3a13d3500fc72d14cbe0e738138e364a708. Actual product runtime checks were skipped after the consumer failed. Separately, same-source persistent-gate run 41159961331 passed; native regression run 41159961328 passed its native and ABI3 steps and retained the original ABI2 failures.

### Publication sharing conflict isolated

Diagnostic source bf62627691a08e1e70933edb8fa57054cab02aae, run https://github.com/NoGod3524/EXReader/actions/runs/41160320401 / attempt 1, job 124416237619: 14 cases / 110 checks / 8 failures. The process-kill correction passed. Both publication cases reported target DELETE open success, parent FILE_ADD_FILE error 32, and absolute MoveFile error 32. Artifact 13026384213: 51935 bytes, SHA256 a635dccc3bc7a77f8c4b471469c79b345c49d39151c065301bcbb6a50343e507.

The publisher now uses native FileRenameInformation with a simple leaf and a null root, binding each rename to its opened source handle's actual parent. All original directory pins remain held with their original no-write/no-delete sharing. It verifies staged and original FileIDs, flushes both files, preserves the original at a fresh name, and reacquires the published target. Any attempted rename without a confirmed result poisons the live gate; admission remains pending for fresh recovery. Tests retain the absolute-rename refusal and add wrong-stage identity, path traversal, original-content retention and post-publication directory-custody checks. Native semantics: https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntifs/ns-ntifs-_file_rename_information .

### Actual publication and Windows product admission passed

Source 36dc472c18c757a62962ae1a2c250060831acc5d, run https://github.com/NoGod3524/EXReader/actions/runs/41160776520 / attempt 1, job 124417607161: installed registry consumer 14 cases / 122 checks / 0 failures; actual Windows product 6 cases / 0 failures. Both same-parent native publications succeeded while absolute MoveFile and directory write/delete opens stayed blocked. Artifact 13026947955: 90645 bytes, SHA256 44f48f27faa8d3c1db9b830418d9d264fb5bbd0d8a35fff790e275241398e53e.

Enrollment now records an independent protected-registry intent before writing its native initial record. The expected initial seal is computed from the canonical initial state, never learned from residual gate bytes. Explicit recovery verifies that intent and every recorded native identity, reacquires exclusive custody, repeats actual SDK proof and only then publishes Binding. Existing legacy policy objects refuse before SDK proof; torn, missing or changed objects remain retained and refused. Four real kill barriers cover durable intent, durable initial gate, completed proof and committed Binding. The expanded consumer keeps all original 14 cases and adds 14 enrollment cases. Production CLI/worker integration remains pending.

### Enrollment recovery passed; production command added

Source ce22056631d7384a869e4452fa996e0e37b28edd, run https://github.com/NoGod3524/EXReader/actions/runs/41161285547 / attempt 1, job 124419176985: 28 registry/SDK cases / 225 checks / 0 failures and 6 actual-product cases / 0 failures. Artifact 13026948951: 122650 bytes, SHA256 0068916e5892112eae594893ffa8be25c95cb4eeaa164b8705bfe29fc00e5069. All four enrollment kill barriers and all changed-object/policy refusals passed.

The installed exreader-c02-admission tool exposes explicit create, enroll, recover-enrollment and check operations. It reads every actual SDK original in bounded chunks and closes all sources before returning admission. Explicit creation pins both input ancestries before CREATE_NEW, retains newly created object handles across enrollment, and never fills an existing incomplete root. The added Actions driver exercises nine command cases. Original registry export is now retained with each run for subsequent ZIP audit. This command supplies production bootstrap; migration coordinator/worker/recovery integration is still required.

### Installed admission command passed; cross-root bootstrap race fixed

Source 239366009c98b53ebfe3735d2c5228e2bb8fa7a2, run https://github.com/NoGod3524/EXReader/actions/runs/41161870970 / attempt 1, job 124420969840: registry 28 cases / 225 checks / 0 failures, installed production command 9 cases / 0 failures, actual product 6 cases / 0 failures. Artifact 13027057864: 157063 bytes, SHA256 255da0b0d0590c1525ac441fec4d4b7f453e70909f192a13bc045d6a5c6ff0ff.

Source review then identified a bootstrap race: two explicit enrollments could hold different native roots for the same logical library while inspecting the same initially empty registry route. Enrollment and enrollment recovery now serialize that route with a Global mutex keyed by the actual user SID and normalized library path. Its owner and protected user/SYSTEM-only ACL are validated before acquisition. Abandonment only permits reinspection; it never supplies a grant. The new fifth kill barrier stops after reserving an empty key but before writing intent. A competing enrollment through another root must refuse before SDK proof; after the original process dies, recovery refuses the absent intent, while an explicit enrollment retry revalidates the complete empty native set. Existing 28 cases remain, with one added race/crash case.
