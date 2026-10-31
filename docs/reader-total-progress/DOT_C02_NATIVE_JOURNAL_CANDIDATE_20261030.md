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
