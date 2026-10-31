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

### Alias-stable registry routing

Path spelling alone can name multiple registration domains for one physical target. Registry and bootstrap-mutex routing now hash WH3LOC01, the actual parent volume/FileID128, and the uppercase long leaf name. The route is recomputed after acquiring all input-prefix pins, so a parent rebind cannot silently select another route. Admission still checks the exact stored target identity and namespace. Alternate path spellings cannot enroll a separate gate for the same location.

The additional scenario creates a real DOS drive mapping, proves both paths resolve to the same full native identity, and requires alternate-root enrollment to refuse before SDK proof. It also attempts shared admission through the alias while the original owner holds exclusive custody, then removes only its exact fixture mapping. Available real short-name aliases receive the same check and an explicit availability observation. The original 29 scenarios remain.

Bootstrap serialization source bd648afa3398e1e8d1b388e6791d52ff69722e84 passed run https://github.com/NoGod3524/EXReader/actions/runs/41162420675 / attempt 1, job 124422675251: 29 cases / 237 checks / 0 failures, plus production command 9/0 and actual product 6/0. Artifact 13027767515: 160353 bytes, SHA256 a01180304591cb01bbe61196156f9620d7d5e4ea47b555db79b74df53f53bc2f. The fifth real kill barrier and cross-root competing enrollment both passed.

### Native route qualification and live publication identity

Source `5daffa96fea8a62c1dc523ec79ed6098735f6eef`: registry run [41162898960/A1](https://github.com/NoGod3524/EXReader/actions/runs/41162898960), job 124424133442, success: 30 cases / 252 checks / 0 failures; installed admission command 9 cases and actual Windows product 6 cases also passed. An actual DOS drive alias resolved to the same volume/FileID and could not enroll a second gate or bypass the original exclusive holder. This runner reported short_alias_available=0, so it provides no exercised short-name alias claim. Artifact 13027848321, 163550 bytes, API digest sha256:54d9058299aab8ff7e3c45a8444be6c441e90d4a9a1e7085233f0edbfec56dfc. Original ZIP semantic review remains pending for these newer component runs. Gate run 41162898962 succeeded. Native run 41162898911 retains the known ABI2 failure result.

The next candidate separates the currently pinned target identity from the independently registered previous target identity. A successful native publication changes the live pin; the trusted previous target remains unchanged until independent terminal proof and durable CLEAN/registry confirmation. The previous comparison would reject a real coordinator check after publication even though manually constructed terminal-journal tests passed. The original 30 registry cases remain; two additional cases execute the frozen wh3_run state machine with actual SDK snapshot/import/verification, native CAS journal and handle-bound publication, and check explicit recovery of an observed missing target. The single-book transformation remains fixture orchestration, not the installed production migration engine. Recovery refuses any newly appearing target instead of adopting it during check. No frozen SDK/ABI2/ABI3 source or assertions change.

### Actual coordinator publication qualification

Source `7f6fcb53f793cc749618e66cffb9a07252fa0a58`: registry run [41163412856/A1](https://github.com/NoGod3524/EXReader/actions/runs/41163412856), job 124425721730, success: 32 cases / 272 checks / 0 failures, admission CLI 9 cases and actual product 6 cases. The real frozen wh3_run reported WH_COMPLETED, 13 acknowledged native lines, five successful checks after native publication, one independent terminal SDK proof and confirmed release. Artifact 13027953977, 175283 bytes, API digest sha256:c9edd237823c28b1ebf4d6483dc6ba27351c6184327ad6699fa4848752c44d68. Gate run 41163412858 succeeded; native run 41163412845 retains known ABI2 failures. These component artifacts still require final original-ZIP audit on the eventual qualified source.

The next recovery check kills that real coordinator at an observed barrier inside successful native publication, before PUBLISH_OK. A new owner reads the complete original journal/intent pair, rejects a deliberately wrong expected tip without adopting the actual tip, then uses a fresh wh3_recover capability. The retained original identity, journal-recorded stage identity and independently read actual SDK content must agree before a recovered COMMIT and RELEASE_BEGIN can advance admission. The new wh3w_read API only observes a fully acknowledged pair under its storage lock; it does not mutate, repair or authorize a newer transaction tip. The fixture transformer remains explicitly separate from the production migration engine.

### Real coordinator restart qualification

Source `4d6655d3d9e45e86983037c4179989ad33b828d6`: registry run [41163872509/A1](https://github.com/NoGod3524/EXReader/actions/runs/41163872509), job 124427112483, success. The run succeeded with 33 cases / 293 checks / 0 failures, installed admission command 9 cases and actual product 6 cases. Observed real recovery: status WH_COMPLETED, 14 acknowledged native journal lines, one independent terminal proof and confirmed release. Artifact 13028500141, 182803 bytes, API digest sha256:c1f0a72b881b7c03f556eba591088905e72b92be0e50d5034eaeb07bad6fc916. Gate run 41163872431 succeeded; native run 41163872424 retains known ABI2 failures. No final original-ZIP audit is claimed for these newer artifacts.

### Candidate immutable transaction proofs and clean checkpoints

Protected registry values now retain immutable input and prepared-stage payloads by actual native domain identity. Envelopes bind canonical prior registration, phase, bounded payload length and full seal; a read validates the inner registration seal as well as the outer seal. The same domain can advance its trusted target once; a later migration uses newly created native objects and a different domain identity. Input records precede mutation capability; prepared-stage records require both an acknowledged input and live capability. Application providers must additionally validate payload semantics.

The explicit next-epoch command proves the current exact trusted CLEAN state, writes and confirms a protected Checkpoint intent, creates a fresh sibling root with three new native objects, independently computes its initial grant, and confirms the new Binding before retiring the intent into an immutable history value. Ordinary open/check refuses while that intent exists. Original roots, journal/intent bytes and old transaction records are retained. Retry before Binding switches preserves and abandons any incomplete new namespace; retry after the switch validates the exact new empty pair and repeats actual SDK proof before admitting readers. It never resets a PENDING domain or accepts an unregistered newer CLEAN grant. Five deterministic kill barriers cover intent, objects, prepared registration, committed Binding and retired intent. Additional controls exercise malformed intent, replaced new journal identity, internally rehashed metadata mutation, two complete real coordinator runs across epochs, and the installed command. Partial journal/gate repair and the production legacy transformer remain subsequent integration work.

Checkpoint candidate source `b88323a75d2018ff19bcfc55d3417e2b613e30ec`, run [41164998675/A1](https://github.com/NoGod3524/EXReader/actions/runs/41164998675), job 124430534684, failed during native compilation: MSVC C4456/C2220 rejected a shadowing local path-length variable in checkpoint record validation. New runtime cases did not execute. The next revision renames that variable and retains /W4 /WX, all 44 intended registry cases, 11 admission-command cases, original native cases and frozen ABI controls. Failure artifact 13029196389, 1418 bytes, API digest sha256:40fd764846a938a7e18bd11c44f632cdaf25d66c949d7b59472f462aad5eb00c. Companion gate run 41164998676 also failed at compilation; no runtime pass is claimed.

### Immutable proof and checkpoint qualification

Source `496fd00eaf9b12afefb4c8da5db838661080f357`, run [41165129647/A1](https://github.com/NoGod3524/EXReader/actions/runs/41165129647), job 124430927917, success: 44 registry/native/SDK cases, 423 checks, zero failures; 11 installed admission-command cases and 6 actual Windows product cases also passed. This includes two full real coordinators across different native epochs, five checkpoint process-kill barriers, independent input/stage envelopes, internally rehashed negative metadata controls, malformed checkpoint and changed new-journal refusal before SDK proof. Artifact 13028827494, 256610 bytes, API digest sha256:e642f2a23a61e4b36c45812e98161af52008b1cf911dea971d213bb3609bd2a7. Final original-ZIP audit remains outstanding.

### Candidate compound-member native publication

A new explicit member operation holds actual original/staged handles with write/delete sharing denied while an independent callback checks their bytes. It accepts only the exact original+stage+absent-retained state, the exact retained-original+stage+missing-target recovery state, or the exact retained-original+published-target state with staging absent. Originally absent auxiliary targets use a separately defined two-object state. It never overwrites an unexpected target or retained object, and any unknown result after attempting a rename poisons the holder. All directory pins remain unchanged; successful main-library publication reopens and checks the new live identity. Four deterministic native barriers cover successful proof, retained original with missing target, published target and final flush. New component tests exercise existing and new mirror members, false content proof, occupied retained paths, idempotent observation and process death at all four barriers. The low-level fixtures construct their journal prefix explicitly; the already-qualified real wh3_run/wh3_recover tests remain intact. This does not yet represent the production legacy transformer or partial native-log repair.

## Actual compound-member result and production importer candidate

Source 37ce9128672817bd699dbc8cea92c78a20eb505f, run 41165902815 attempt 1,
job 124433297895 succeeded: registry consumer 50 cases / 530 checks / zero failures,
installed admission CLI 11 cases, actual Windows host 6 cases.
Original artifact 13028424590 is 306611 bytes, SHA256
ff87fc79045210e46adcbced58f2dd2cdd30fdbac2bad0620b648c9876e128cf.
This result qualifies component member publication; it does not qualify the production importer.

The next candidate adds the synchronous actual migration command. Under the native PENDING
capability it streams the fixed, write-denied original into a previously reserved private
database object; SQLite WAL/SHM/journal companions are refused before and after the copy.
The unchanged SDK opens only the private image. The original book/annotation/policy loop
is extracted into process_pack_rows and reused; originals are independently hashed before
and after import, migration ledger bytes are committed in the private image, and an independent
SDK reopen verifies the pack, library and external mirror before immutable PREPARED is written.
Both actual publication handles are checked against INPUT/PREPARED before either member
is renamed. Every SDK owner/source closes synchronously before publication.

The installed production binary has no barrier-control code. A separately named test binary
contains deterministic named-event controls, while both producer binaries record their actual
SHA256 and original Actions source/run/attempt. Recovery retains original producer binding and
reacquires only for the exact acknowledged native prefix; it either confirms both prepared
members or proves unchanged originals and preserves identified private objects.

This candidate is not yet executed. Planned Actions preserve all old ABI2/ABI3/native assertions,
run the original legacy scenario runner for the shared-loop extraction, then exercise actual
migration, a second epoch, strict rollback, process kills and foreign prepared bytes/identities.
Torn-journal/gate explicit repair, other platform admission and final same-source original-ZIP
semantic audit remain outstanding. Formal acceptance remains 95/108.

## Actual owner bring-up and explicit raw repair (2026-10-31)

Source 1f618780d936627d9bd1ab48cece4781dbca7e11, Actions run 41169507968/A1,
retains the first fast actual-migration failure: all 25 scenarios exited in input
setup before any requested barrier. Native registry/product and original legacy
scenario steps passed; actual migration did not. Artifact 13030373853 is 1043819
bytes with API SHA256 73caa568fd826be71b15fbb25d21817c2a069a49697d95903b30d94212e674f9.
Source ef2478b5e0e9bb782e06e53c0d28fa3d727180a3 run 41168469106 remains the earlier
slow-wait attempt; its original record is retained separately. The path-pin loop
was restoring a directory character as a separator after temporarily terminating
the drive root; the new candidate preserves the original character.

The next candidate adds an independent read-only last-ACK/gate scanner, preserved
raw archives, a protected registry Repair plan and resumable application of only
its validated target bytes. Ordinary readers and new epochs refuse an active
Repair. Actual terminal proof and CLEAN Binding must precede Repair retirement.
Archive paths derive from the identified root's native volume-GUID path, including
roots already accepted near the original length limit.

The separate scanner consumer has 29 planned scenarios with every-byte prefixes
and resealed semantic contradictions. The actual-owner runner has 83 planned
scenarios: original migration cases, native append cut points, interrupted repair,
partial BEGIN/CLEAN gates, archive tampering and a long registered root.
An Applied Repair also fixes the minimum ACK prefix: same-FileID rollback to an
older complete history is refused by byte comparison against the protected archive.
It checks SQLite ledger/source/annotation content independently of the C verifier.
These additions have not yet passed Actions. POSIX host/owner integration and the
final same-source original-ZIP audit remain outstanding; formal acceptance is 95/108.

## Qualified Windows raw repair and POSIX component result (2026-10-31 05:40 UTC)

Source faae61879441085d800879332699d0b6fd5e2307, run
[41170465266/A1](https://github.com/NoGod3524/EXReader/actions/runs/41170465266),
job 124447124317 passed all 83 actual migration/recovery scenarios, the 29-case
scanner (91794 checks, 6603 observations), registry 50/530, installed enrollment
11 cases, actual Windows product 6 cases and the unchanged legacy scenario runner.
Original artifact 13031266152: 2859406 bytes, API SHA256
dbad1ea92cdaa8f256eeb67b61d9a95f42bbf99540c7447253bf4c1c6bedd6ed.
The raw repair and original-prefix floor additions above now have actual Actions
evidence. The earlier ef2478 run 41168469106 ended cancelled at its 35-minute
job timeout; it is retained as a failed bring-up attempt, not a runtime pass.

Source 10926201953185cd1ec2fcd0c2b3f4985bc9feef, run
[41171196433/A1](https://github.com/NoGod3524/EXReader/actions/runs/41171196433)
passed the strict native POSIX consumer on Ubuntu and macOS: each 28 cases /
207 checks / zero failures. These component receipts explicitly declare
actual_sdk=false, host_wiring=false and power_loss=false.
Ubuntu artifact 13030579171: 99149 bytes, API SHA256
d9efdab3688cce47c6c3696cb168391eab7fb7afb9b27a86254b25db0f1e4d8c.
macOS artifact 13030429676: 99452 bytes, API SHA256
7da3f86bea1aafc5935c4865683ced331153d58cbde6ead5f28eabaee0241316.
The first POSIX source b366191a run 41170770328 preserved its macOS Clang
uninitialized-observation compile failure; 109262 initialized that descriptor.
Its companion native run 41170770312 retains the original six ABI2 failures
on both platforms, including the absent/stale prefix mutation signatures.

The next integration candidate adds a fixed OS-container scope without weakening
the default POSIX path walk, plus seven scoped native cases; an explicit SDK
creation/enrollment adapter; actual GTK admission before product-lock/SDK access
and until its live page/search owners retire; and default C02 admission for all
Windows standalone readers and installed legacy read commands. Old Windows
mutation commands refuse before target/report/lock access. The unchanged legacy
runner uses an explicitly selected Actions-only, noninstallable historical build.

A new independent audit consumes the four pinned original faae ZIP artifacts.
It checks native protocols and SQLite content, and reruns nine resealed negative
controls. Its Windows component mode explicitly remains incomplete; original
ZIP hashes and failure output are retained. The new scope/host/audit candidates
have not yet been executed at this entry. Actual POSIX synchronous migration,
Android/Apple admission and final same-source complete qualification remain open.
Formal acceptance remains 95/108.

## First actual reader integration result

Source 2d0423c5ec7c1079dbc7de95f0e9db30f4c4f3d5 has passed:
- Windows run 41173415484/A1: all 83 actual migration scenarios, scanner
  29/91794/6603, registry 50/530, enrollment 11, actual product 6, and the new
  18 installed legacy-command refusal/admission cases. Standalone reader built.
  Artifact 13032157171, 2890705 bytes, SHA256
  6ecfac68e28444ca78591a29f3c8fd0ac95f2b64162a9d61ef644b8acbffdd3b.
- GTK run 41173415522/A1: 12 actual host cases, including a live page plus
  incomplete SDK search holding shared custody, final-owner release, explicit
  creation, actual shelf reopen and independent original SQLite bytes, cloned
  path/inode refusal, and durable PENDING before catalog access.
  Artifact 13032511149, 12965813 bytes, SHA256
  d99b933a70fa07df5f634943af576f5c9f126e7538ca2aca521e69d4c4054fe2.
- POSIX run 41173415556/A1 on both Ubuntu and macOS: original 28/207 and
  scoped 7/58, all zero failures.

The first independent audit run 41173415518/A1 failed on native fixture case001.
The audit incorrectly used the actual producer SHA as the fixed fixture binding;
the native fixture intentionally uses HX40 in its journal while its result and
Actions receipt bind the actual source. The fix independently reads the fixed
fixture manifest from the specified producer Git source and retains strict API,
receipt, original 46/301, invalid-case and negative-control checks. Failure
artifact 13032097070, 21422 bytes, SHA256
be81c4a1c504e37a3fac55c5642436e97a781b498a40b8f0c2506c318b6760ef.
The corrected audit, packaged GTK enrollment tool and standalone-reader runtime
checks are new candidates pending Actions. Full C02 remains open.

## Original ZIP semantic audit and platform integration (2026-10-31 06:26 UTC)

Audit source 422b40c238ac595272c706fd48e38ccf5564e475, run
[41175856635/A1](https://github.com/NoGod3524/EXReader/actions/runs/41175856635)
passed independent decoding of all four original faae6187 producer ZIPs,
including the 83 actual migration scenarios, native original 46/301, gate
28/309, registry 50/530, scanner 29/91794/6603 and unchanged legacy cases.
All nine resealed/repacked semantic negative controls were rejected.
Audit artifact 13032652174: 1733685 bytes, API SHA256
c9e8e30d6e3dc036a9130802005d15c733dff505c8a77344be5e044857406e99.
The audit explicitly reports full_c02_complete=false and missing platform
host roles. This is a completed Windows component audit, not final C02.

Retained audit failures: 41174018878 (CRLF gate observation parsing),
41174560431 and 41175352126 (CMake in-memory LF provider fingerprint versus
Windows text serialization), and 41175466342 (the exact pre-admission
abandonment record intentionally has no source/provider fields). Each fix
preserves original ZIP/API binding, complete native counts and invalid-case
classification. The early-abandonment exception is restricted to successful
recover at phase900 and independently checked empty journal/initial gate.
Source b396d639f audit run41176352115 also passed the same fixed experiment.

GTK source8c00e9b3 run41174560448 passed13 actual runtime cases and packaged
explicit enrollment create/check. It adds a second library under the same
valid authority. The preceding539ae run41174018899 failed packaged creation
because the helper tried to recreate an existing root; ordinary opens still
never create or enroll authority. New captures retain original native IDs,
UID/mode/link/size/SHA and bytes at clean/borrowed/released/pending stages.

POSIX source b396d639ff56016e1b7f806cce64385890486936,
run41176352105/A1 passed on both Ubuntu and macOS: original28/207,
OS-scope10/81 and new metadata/member/floor16/119, all zero failures.
Ubuntu artifact13033122111:267925 bytes, SHA256
a94661a7d57f14d351adcf3a71adfa04b6a9739a2ca9081c231bb171be9b97fc.
macOS artifact13032752777:268526 bytes, SHA256
a22b85587a70f84957873f62d5f7a4bce3e1bfcd0b2c597e02d901a0069f7768.
First run41175856697 retained Ubuntu GCC misleading-indentation errors;
macOS passed. The repair only separates statements and keeps Werror.
These are native components with actual_sdk=false and host_wiring=false.

Windows full Wave3 bring-up retained run41174560399 (noncanonical Windows
hash-prefix spelling) and41175352156 (feature-created Wave3 target missing
reader_c02 linkage). b396d639f links the installed native provider to that
actual target after the unchanged feature include. Its runtime is pending.
Android actual app-UID and Apple macOS/simulator admission first candidates
are committed, but their runtime scenarios have not yet been qualified.
The Android first failure exposed an unbounded no-device logcat collection;
its evidence step is being bounded so failure artifacts can upload.

Still required: actual synchronous POSIX SDK migration, archived explicit
repair of partial state/head tails, actual Android/macOS/iOS and full Windows
runtime results, independent POSIX/host byte audit, and one-source complete
qualification. Frozen SDK/C01 and formal acceptance95/108 remain unchanged.


## Full Windows host and GTK independent native snapshots

Source b396d639ff56016e1b7f806cce64385890486936, Windows run41176352067/A1
passed the actual full Wave3 build and6 runtime admission cases, standalone6,
product6, installed legacy guard18, enrollment11, registry50/530, scanner
29/91794/6603 and all83 real migration scenarios. Artifact13033081676:
7024746 bytes, API SHA256
587753f56af7abe734735b4cf564b05b1cfc892e7c72da5feb1048d73f6a4317.

Source36918c9c1ee18aa5345cd6ea4cf3072922e3c43b, GTK run41177046720/A1
passed13 actual host cases, packaged create/check and independent decoding
of four native snapshots. Eight fully resealed/rehashed POSIX corruptions
were rejected, including pending-prefix rollback, wrong native ID, wrong
grant, reserved/sequence changes, permissions and a torn state tail.
Artifact13033177186:57284131 bytes, API SHA256
5ee9fbc3aaae64507698a3b795d5b8b9015743d9a08485b3f7346cc3afd95846.
The raw original ZIP still requires inclusion in the final cross-platform
audit; the same Actions job's independent decoder is a component result.

POSIX run41177046644 retained the new17-case macOS Clang uninitialized
observation compile failure; Ubuntu passed original28+scope10+API17.
The correction zero-initializes only local observation structs and retains
all55 scenarios and Werror. The next Windows candidate packages the explicit
admission/migration commands and tests that packaged enrollment works.

## 2026-10-31 platform runtime and independent original-byte audit update

The formal 95/108 ledger remains unchanged. These are separate, source-bound
component qualifications; they do not combine different commits into a final
C02 result. The remaining complete-C02 gates are the real POSIX SDK migration
owner, explicit protected Repair of incomplete native records, and all required
roles qualified again at one final source.

### Ordinary Windows and GTK packages

- Source 0bf4bf4b99795e0f2301b372cd7eb60dd631361e, Windows run 41177757587/A1,
  succeeded with the ordinary full host package. The package includes the actual
  admission and migration executables and exercises packaged create/check.
  Original artifact 13033423402: 53135499 bytes,
  SHA256 1bc5839a19e91ea0e2037428c49881d3d366f18c89e0f3f603120552161c248b.
- GTK original-ZIP audit 41178152226/A1 used audit code 6613749f5011b25f2c7e58eea62cfe112347d842
  and the three original 36918c9c1ee18aa5345cd6ea4cf3072922e3c43b packages.
  It independently checked the actual GTK package, 13 cases, four native snapshots,
  SQLite original content, before-SDK refusals, final search/page custody,
  and all 17 controls (9 original Windows plus 8 resealed POSIX controls).
  Audit artifact 13033921020: 57397043 bytes,
  SHA256 d7cdf7c16f2446b7a706b5dcf73b131e14552548f23f200696785ad46ae52924.

### Actual Android application, sample, and ordinary package

Source 6613749f5011b25f2c7e58eea62cfe112347d842, run 41178126581/A1,
completed the actual application job 124469811855 (14 cases, 361 checks,
app UID 10141) and the original import-entry sample job 124469811718
(19 scenarios, 95 passed, 0 failed). App artifact 13033543534:
20057961 bytes, SHA256 15c2d07346c26ca21e6f3ea22d1e6e86701926e1dacd1a46709e7af74ea5a4a2.

The first Android original audit 41179393722 failed because the adapter applied
the runtime inventory to the later artifact envelope. The producer has two
inventories: run.py records the runtime, then the workflow adds source.txt,
logcat-final.txt and artifact-receipt.json and records artifact-file-hashes.json.
Commit a16aa72353ff73caaeae383f68daa56514c3aa5b verifies both inventories completely.
Audit 41179499606 then passed 14/361, all seven app-UID native snapshots,
independent SQLite original content, actual SDK-close/source-release/lease-close
order, exact B/C/Binding native identities, process-death PENDING, and 17 negative
controls. It explicitly retained android-installed-sdk-byte-binding as missing:
the old artifact did not preserve the pre-strip SDK bytes. Audit artifact
13034287464: 20207481 bytes,
SHA256 0ad6e89ec544cce3065461e6c7c3be83fac43467be2cb51ddaf72f774993dda8.

Source 07386b64e10fe45199fcd52af9b7c01ccece750c, run 41179597460/A1,
subsequently succeeded through the ordinary tools/build_android_host.py entry,
ordinary Debug and Release APKs, the 14/361 actual app-UID cases and original
19/95 sample scenarios. The shared SDK is built once and C02 admission archives
are installed into its prefix. Both normal and skip-SDK paths require the same
frozen source boundary. The independent installed OPDS hash and original-import
product dependency are now built by the ordinary product recipe.

App artifact 13034417579: 75549634 bytes,
SHA256 f7e1256557fab02f39cbbdd0a14ba7695f341fa7e99891df45205c9504597664.
It preserves the actual pre-strip SDK, APK-extracted SDK, official NDK strip
outputs, ordinary packages, and matching native host provider evidence.
Independent audit 41180555114/A1 at e2695dac6369fc162be2bac4e3d79031e5a5c164
passed original raw semantics plus 8 fully resealed native negatives. It parses
the actual APK ELF dynamic imports/exports and compares every SDK PT_LOAD byte
and program header, normalizing only ELF section-table metadata changed by
strip. installed_sdk_byte_binding and standard_package_byte_binding are both
true. Audit artifact 13034906411: 75465075 bytes,
SHA256 f1db75e769008cd8a626d62d88625b350f440048f956046caf5e14ba2eeaed1d.

A subsequent static review found a debug-only primary-close probe could ignore
non-Source Java borrows. Commit 2a8a073af rejects mixed borrows before changing
Java or native ownership. Its existing scenario now also proves rejected close
preserves the SDK and lease; the total remains 14 cases, expected 362 checks.
Commit 99999d629 additionally compiles that native probe closed in ordinary
products. Their Actions results must be recorded separately when available.

### Apple actual runtimes and original snapshots

Run 41177757574/A1 at 0bf4bf4b99795e0f2301b372cd7eb60dd631361e passed macOS
runtime but failed iOS baseline. Read-only original ZIP diagnostic 41178931382
retained and checked original iOS artifact 13033871756 before showing the actual
failure: the test occupied the main GCD queue while waiting for HostModel's
main-queue completion. This was a test scheduling failure, not an admission
failure. Commit 267bdbaddeb15f9420bd5c2e20f1cb031fd95613 runs the iOS test driver
on a worker while keeping HostModel actions and observations on the main queue.
It retains the same 30-second deadline and all 14 cases.

At that source, run 41179330166/A1 succeeded for both frozen SDK jobs, both
installed-product jobs and both actual runtime jobs:
- macOS job 124474161157, artifact 13034720573, 55008521 bytes,
  SHA256 8700b0786c51a1a988e3e422e85fe071d719603774566eb3b546e959ac6b132c.
- iOS simulator job 124474161201, artifact 13034398089, 55041336 bytes,
  SHA256 c6210ff3cb2d0838132b0a2b8cd33ba4ee525f2f84a1f00a0c8c79492285705c.

Original-ZIP audit 41180380294/A1 at af19d8e586c9c6c5120ff251be6e76a1370c4f8c
succeeded for both runtime artifacts: 14 cases per platform, five actual process
phases, enrollment and PENDING external kills, all nine positive/negative
authority routes, original SQLite contents, before-SDK rejection, real document/
publication/fixed final owners, actual stdout observations and 16 resealed native
controls. Audit artifact 13034344083: 109826075 bytes,
SHA256 8490db3d255033cfd37d0dcc799b804c0e9406cf9b40e065ab2370d124c91a22.
This first adapter bound native consumer binaries and installed C02 archives;
its bundled shared-SDK check still only established Mach-O structure. Review
therefore added the stricter SDK identity comparison in 99999d629. The producer
now also preserves authenticated pre-codesign SDK dylibs in installed-sdk/,
before any bundle copying/signing. Exact SDK/bundle code binding still requires
that strengthened audit result; the earlier component pass is not substituted.

### POSIX API raw bytes, fstat, and original ZIPs

Source 18490e949dbbd40be48d26b312bacd024cf38f5f, run 41179811151/A1,
passed on both Ubuntu and macOS: original 28/207, scope 10/81 and API 17/130,
55 cases and 418 checks per platform. The additional independent adapter
opens the real producer objects with NOFOLLOW and captures fstat, retaining the
original producer inventory and every raw regular file. It independently
classifies all 17 API cases as 7 positive and 10 exact expected refusals.
Its component floor profile is explicitly 272 bytes and journal_bound=false;
it cannot qualify the real production ACK/floor contract.

- macOS job 124474722889, artifact 13034038752, 718524 bytes,
  SHA256 a17d27931a7fd30fb5b2a93831de7525fdc03b0fef04377908d2d2ce53ce673f.
- Ubuntu job 124474723053, artifact 13033719660, 732993 bytes,
  SHA256 56c2536b7cb010de541f9d1464edf3acabc0e940b5cfde4b551f033530abf503.

Original-ZIP audit 41180443980/A1 at af19d8e586c9c6c5120ff251be6e76a1370c4f8c
independently re-decoded those two snapshots together with the same-source
original native Windows and Ubuntu ZIPs. The original ABI2 81/6 exact signatures,
ABI3 16/64/0, Windows native 46/301/0 and all 9 original negatives remain intact.
Audit artifact 13034094644: 826335 bytes,
SHA256 b92b3f45e76a50d3fc209100fa6c77992021797d8b1f5713f1c64ee85a64b3c5.
The old evidence truthfully retains independent_pre_confirm_snapshot=false:
it has the post-confirm head and C assertions, not an independently retained
464-byte pre-confirm original. A new producer patch is being prepared to retain
both actual source-fd identities and before/after raw heads; historical artifacts
will not be rewritten.

Selected host-only original audits require at least seven independent native
semantic negatives and always retain missing roles. Complete mode still
requires all twelve same-source roles, including both real POSIX migration
owners and the original Windows negative baseline. All build, runtime, fixture,
syntax, archive download and archive decoding operations remain Actions-only.

The strengthened Apple audit 41181231939/A1 at 99999d629 failed at the expected
original-versus-bundled SDK byte comparison for the old 267bdbad macOS artifact:
libexreader.1.dylib, original identity SHA256
e3c1c09e57569ce001d7663115a5a224ee61b6445b528b287dc978cc5f8be528 versus bundled
SHA256 bdab1d5ce896c58c6791bdfa7e3bb19b704e457955b2cbc3da4b7a3742b932d0
(8062896 bytes). The producer copies then ad-hoc signs bundle dylibs after its
SDK identity was recorded. Actual signature-region differences must be decoded
from the newly retained original SDK bytes; the audit does not waive this mismatch.

### First POSIX production build and latest Android original audit

Commit 73f445f61f06c41916677960076f241b640317a5 adds the synchronous desktop
POSIX actual SDK migration owner, immutable private pack custody, INPUT/PREPARED,
ACK296/FLOOR352 binding, native two-member publication and the 36-case driver.
Run 41182277983/A1 failed during the first owner build on both Ubuntu and macOS:
ABI3's installed exr_wh3.h includes exr_wh.h, but the owner target did not yet
carry the original ABI2 header include directory. SDK and native authority
installation passed; the original 65 and actual 36 cases were not run. Preserve
this failed run. The follow-up adds the explicit frozen ABI2 include; its
validation is a separate run.

Android producer 99999d62933cf38a40f69325c11df320df29d7fb passed run
41181228186/A1: actual app 14 cases / 362 checks at UID 10141, and unchanged
import-entry sample 19 / 95. App job 124478856217 retains artifact 13034658274,
75551660 bytes, SHA256
2e6d3d1c0253c04a77ec6821d2ed1554c5fc0e826db49725f655f1a53145dc86.
Independent original ZIP audit 41182350480/A1 at 73f445f61f06c41916677960076f241b640317a5
passed with installed_sdk_byte_binding=true, standard_package_byte_binding=true
and all 8 fully resealed native negative controls. Audit artifact 13035622460,
75483204 bytes, SHA256
b5f6acb3f00a68620de26557b2dffdbccc9ce5a010d3b198fa9eccc3e8948a07.
It remains selected Android evidence with the other eleven roles explicitly
missing. The source-qualified native pre/post-confirm capture at
20ef447e25504a2855acf44d1b5729dd81a4fe14 also passed both POSIX jobs in
41181680798/A1; its original ZIP audit remains part of final qualification.

The complete request template now lists all twelve current roles and exact
workflows. Actual POSIX Repair and its independent production adapter, Apple
signed SDK byte binding, and a final common-source all-role audit remain open.
Formal 95/108 and frozen SDK/C01 values remain unchanged.

### Qualified actual POSIX owner and SDK byte audits (08:25 UTC)

The ABI2 include correction at 692e52506c2508434d5792ba0e1ac775e1e1e2ba
passed Ubuntu job 124483253755 in 41182716610/A1: actual owner 36 cases and
unchanged historical 65 cases / 135 checks. macOS job 124483253727 failed at
getentropy's missing declaration. Commit 0ddfc8d09e2def04ed3df095c06e5a0207f8d758
adds Apple's sys/random.h declaration without weakening Werror. Run
41183156836/A1 then passed both complete platform jobs:
- Ubuntu job 124484542053, artifact 13035955228, 44748311 bytes,
  SHA256 a80fc58b910afa2f571374e8f8b9d740fbc6c332577cb652d7192b0ae95ff750.
- macOS job 124484542364, artifact 13036390157, 39326349 bytes,
  SHA256 4044518f0187533a9b5e7280daf99a7bf7dc3119948d681833fc5f96af546832.

Independent Actions diagnostic 41184422915/A1 at
734f4fa5d1a23515a754a51d0a09dea0e13f1c25 retained and audited the original
692e Ubuntu ZIP (artifact 13035563580, 44751227 bytes,
SHA256 4d549d71db64240e438c41fee79940e33f0b79f4c136f3c390bd1fdfe76f05cc).
Its independent production decoder passed all 36 actual and 65 historical
cases, 65 transactions, 70 phase snapshots, 2728 native fstat objects and
3784 runtime files. It verified actual SDK payloads, INPUT13844/PREPARED251,
ACK296/FLOOR352, native IDs and fresh process recovery. The result explicitly
retains partial_state_head_repair=false. This is diagnostic evidence from a
successful job in a partially failed workflow, not a complete qualification.
The diagnostic artifact is 13036950208, 42607586 bytes,
SHA256 0b087b5b1d080bd8a9d403969de3a1d9f2bbeade0f5f96ce84cd811ecc13663b.

Apple's original SDK and re-signed bundle binding now independently validates
all CodeDirectory SHA256 pages and the entire prefix before the signature.
Only the verified __LINKEDIT VM/file lengths and LC_CODE_SIGNATURE datasize
(20 bytes total) are normalized; original code, symbols and other LINKEDIT
bytes remain exact. The original and ad-hoc signature layouts, identities,
special slots, executable ranges and allocation bounds are checked separately.
Eight SDK byte-pair attacks per platform are repacked, rehashed, read back and
rejected, including changed code or LINKEDIT with recomputed page hashes.

Run 41184435643/A1 at 734f4fa5d independently audited both original 99999 Apple
runtime ZIPs. Its compact Actions result and separate saved-result receipt
confirm two originals, 32 semantic negatives and 22 role-substitution negatives.
Artifact 13036272253 is 254890304 bytes, SHA256
de24b7840f670dcfc442365bb8137ff03195f425df198f68171ec7576bea44f1;
audit-result.json SHA256 is
d074b61154435d7b76d6b4f1bb91eac89b549ddd7f8ba6e4300ba097054055ac.
The earlier d8cd9f549 run 41183677876 also succeeded; its giant stdout result
was not visible through gh logs. Full JSON remains retained in both artifacts;
734f4fa5d emits compact logs instead of printing the giant record first.

Review also closed two qualification gaps: each role is now fixed to its real
platform/workflow/job/artifact naming rule, and POSIX production roles call
their own decoder instead of falling through the Apple host adapter. Missing
pre-confirm snapshots and missing explicit Repair are unconditional capability
gaps. selected-components can never set full_c02_complete=true. GTK still has
a static-SDK binary-binding gap; preserving real link inputs and independent
relinking is in progress. Complete acceptance still requires all twelve roles
at one common source and every capability gap closed. Formal 95/108 is unchanged.

### Six-role original ZIP qualification and negative summary correction

At producer 734f4fa5d1a23515a754a51d0a09dea0e13f1c25, the two original native
baseline packages, two POSIX native packages (including actual pre-confirm
snapshots), and both actual migration packages passed independent original ZIP
audit 41185117231/A1. It retained all six originals, 9 semantic negatives and
66 role-substitution negatives. Artifact 13036468152, 79707845 bytes, SHA256
c3ea8d9d0912384810b2672d8c1cd438cc3bf9d7123c9585291ec138e9a03ea1.
Both actual owners still declare the missing explicit partial-state/head Repair.

The next audit 41185479465/A1 added eight owner-specific resealed attacks per
platform. All six decoders and all 25 semantic controls reached the saved result,
but the final compact log formatter raised KeyError('reason'): the new owner
control records use 'rejection'. The workflow correctly remained failed because
its audit process exit was nonzero. Preserve artifact 13036783195, 113110575 bytes,
SHA256 fbd35cbd42f25951d0b34903c810eb3654b37647ebb762f7caf021c15a673cd8.
The follow-up changes only compact-log field selection; all original checks,
patch ZIP readback, reconstructed semantic decoders and exact expected rejection
classes remain unchanged. Its full successful result must be recorded separately.

### Native owner negative controls and exact GTK binary closure

Audit 41185703560/A1, after the compact-log correction, successfully audited
the six original producer 734f4fa5d packages with 25 semantic negatives and
66 role-substitution negatives. Artifact 13036877890 is 113111385 bytes,
SHA256 3eef035cb3a7ebd96d63929ef3cc478c746261b121c57811c2d067204c13dfa1.
The two missing production capabilities remain explicit partial B/C/head Repair;
the six other roles are absent from this selected request, so it is not complete.

GTK producer 57c6407e992992459cd6aa742043c263c19926c7 passed runtime run
41184993985/A1, job 124490014750, with all 13 existing cases. Original artifact
13035922715 is 91436418 bytes, SHA256
a036bd51032359aee8374e19cdbb9d321e48e75ae397badb34214e51deeec763.
It retains every actual linker input and original build/executed/packaged ELF
for runtime-host, product-host and admission. The independent verifier checks
the compiler/linker digests, permits only the known plain argument grammar,
relinks with the retained actual objects/archives, and requires exact ELF bytes.
GNU map/symbol checks bind real SDK entry points and native admission entry
points to the specified common installed archives. No arbitrary strip/RPATH
normalization or shell/plugin argument is accepted.

Independent GTK audit 41186558815/A1 passed with one original ZIP, 16 semantic
negatives (8 native plus 8 binary/link controls), and 11 role substitutions.
Three self-consistent code changes fail exact independent static relinking;
plugin and shell argument attacks are rejected before execution. Each binary
negative retains its patch capsule, source/run/job/original-ZIP context, fresh
inventory/CRC, reconstructed inputs and exact rejection class. Audit artifact
13035929642 is 270109631 bytes, SHA256
73b0bb376e1904bbb427ca0c538a2b24e9d91208bf982d5566361fabddc6b85a.
GTK's installed_sdk_byte_binding gap is closed for this producer. Complete
qualification still needs all twelve roles at the final common producer.

The POSIX Repair scanner/store and isolated consumer are now separately
submitted to native Ubuntu/macOS Actions. Their 30 named component scenarios
cover every partial B/C byte boundary 1..367 and head boundary 1..271, strict
ACK296/FLOOR352 relationships, actual immutable publication, identity/permission/
ACL/link refusal and source retention. FIFO reads are nonblocking; the created
temporary FD stays pinned through final publication readback. The real FIFO
remains on the runner with native metadata retained, and is explicitly excluded
from ZIP upload to avoid blocking the artifact reader. This component workflow
does not qualify production Repair; the real owner integration and independent
raw repair-plan/archive decoder are still pending. Formal 95/108 remains unchanged.

The first helper run 41187608811/A1 compiled successfully on Ubuntu. Its native
consumer reached 30 cases / 3870 checks with one failure at line 201 in
complete-state-resealed-contradictions. The failing test changed a complete C
record's nonzero terminal to another nonzero value and re-sealed it. State-prefix
parsing has no ACK input; it must retain a complete C fact, with terminal proof
performed by the transaction/SDK layer. Treating that record as a prefix-internal
contradiction was an invalid test expectation. The correction preserves all nine
actual contradiction checks by testing C generation against the preceding B,
and adds two checks that another structurally valid complete C remains count 3
and cannot be truncated back to B. No production scanner/store code is changed.
Preserve failed Ubuntu job 124497608383 and artifact 13037466997, 238913 bytes,
SHA256 895495475b2c05b92d8d9db9f24b1056c621febad15440436149169065cc5176.
The corrected helper run is separate evidence and still pending.

The corrected helper run 41187908522/A1 passed Ubuntu job 124498481459:
30 cases / 3872 checks. Artifact 13037427589 is 238597 bytes, SHA256
3e1c479b083ea7eb2b06ec7d42d05648f7fa0e0b0e38b03b0477bccdfedbcd87.
macOS job 124498481297 exposed a real production ACL bug: three checks for
an actual extra ALLOW entry on a source file/directory were accepted. Preserve
artifact 13038106489, 239857 bytes, SHA256
7d5e8e674411b9db003109e4cab831a1661488b4a060e517df7b54c46f7f5527.
Darwin acl_get_entry returns 0 for an entry and -1/EINVAL at the end; the
old loop incorrectly expected 1 and skipped real entries. The repair store,
native admission and owner I/O now validate the ACL, enumerate successful
0 results, accept only the validated ACL's -1/EINVAL termination, and reject
other errors or acl_free failure. This follows Apple's acl_get_entry(3)
contract: https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man3/acl_get_entry.3.html
Existing real ACL negative checks remain unchanged. Production Repair guard
and SDK proof callbacks are submitted with this correction for native compile
and original regressions; actual new Repair cut/retry scenarios are not yet
qualified. All prior failures remain available.

At producer 730fe1ec94ad369145daa7c9f143e3000287c8b6, helper run
41188280561/A1 passed on both platforms: 30 cases / 3872 checks / 0 failures,
8 independently decoded wrappers, and all real ALLOW ACL refusals.
- macOS job 124499572401, UID 501, artifact 13037756864, 238598 bytes,
  SHA256 dd9732a83263deed3fe55173daf38af99bc55e75c83d3e9a06dc176c6885d586.
- Ubuntu job 124499572553, UID 1001, artifact 13037238786, 238595 bytes,
  SHA256 c181f33d7b21123547b78ad00e950d5aad50a9a093832bf0d085a758264dc566.
Native admission run 41188280516 also passed both unchanged 55/418 consumers.
Actual owner Ubuntu job 124499572095 in run 41188280556 passed the existing
36 cases plus the historical 65/135, with artifact 13037807922, 45015277 bytes,
SHA256 f2a47c5e53f3854fe00b98d5e14e8b3eea9cbb49fe6710d251f21c97b944071e.
These runs verify compilation and previous behavior after production Repair
integration; the new explicit Repair cut/retry scenarios remain a separate gate.
