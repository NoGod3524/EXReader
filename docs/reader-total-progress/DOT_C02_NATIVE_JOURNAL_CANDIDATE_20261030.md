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
