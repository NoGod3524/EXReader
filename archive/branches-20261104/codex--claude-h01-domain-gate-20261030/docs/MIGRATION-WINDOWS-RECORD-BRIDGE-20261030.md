# Live retained-record bridge candidate

Base: 826bfc527c6305d41b4a8a2c61be5dbc1315ddb6. New independent branch
codex/p0-win-record-bridge-20261030. No old wr_* provider, SDK, original assertion,
shared root build or coordinator/engine path is modified.

The bridge prepares up to 32 uniquely named bridge-slot-NN.rec files under original
qualified custody, charging 4096 bytes per slot through the original write/entry
budget. Existing leaves refuse without replacement. Reservations are invalid zero
bytes, not records. Partial preparation failures retain all evidence; close only
releases owned handles, never removes files.

Caller holds exclusive admission and a trusted target handle. The bridge owns slot
handles; target and publication custody are borrowed and must outlive operations.
Handles must not be inherited/duplicated to workers or mutated concurrently.
Prepare publisher custody while original pins are live, attach by full root/parent
identity, then explicitly close the original context. No cast or restrictive-pin
reopening is used. The publisher addition exposes only checked identity copies.

write_once validates session/source/run, root/parent/target full48hex identity,
target bytes and size, predecessor canonical bytes held by retained handle, native
previous file identity and chain SHA. It reserves the slot as attempted before any
mutation, writes/truncates/flushes, verifies canonical readback and custody again.
Any attempted write failure is uncertain, cannot be retried, and blocks advancing.
It never grants COMMIT/recovery/admission. Codec phase range checking is not a
coordinator phase-state-machine check; the coordinator owns phase legality.

Limits remain record4096 bytes, target/publisher digest1MiB, original write and
entry budgets. Directory custody admits child writes but retains deny-delete;
slot and target handles retain share-read-only protection. All calls are serialized
by the owning coordinator. No thread safety or privilege-boundary guarantee.

Actions builds installed libraries and a separate installed consumer with /W4 /WX,
runs 26 native controls, process deaths before first record, after first record,
after publication before the next record, and after the next record. Original
record27, publisher28+two death cuts and refusal8 are rerun unchanged. Archives,
maps, original record bytes and source/run/attempt receipts are retained.

These cuts do not inject a mid-write error or the native rename/postcheck gap.
No restart reader exists. Empty/partial/missing records after death require a
separately qualified exclusive recovery reader, never auto-cleanup or SDK admission.
Observed flush/readback is not physical-power-loss or directory-fsync equivalence.
No full P0 or common-source acceptance is claimed. Initial status: Actions pending.

## Retained first Actions failure

Source 0db2df43371ace854dd27aa2cc2648d9a84a5a8c, run41085127597 attempt1,
job124164152366: failure. Frozen/admitted source checks and installed library and
consumer /W4 /WX builds passed; original record27 and publisher28 plus its two
death cuts passed. New probe exited3221225725 (STATUS_STACK_OVERFLOW) before output:
two large wr_context automatic objects exceeded the default executable stack.
The corrective change uses static storage only in the serialized new probe.
No old assertions or budgets change. Original refusal8 was skipped after failure.

Retained artifact12990619994:314593 bytes; upload SHA256
41817de8f437bd000e8b90d982a99686622191527a49eed72a9451715114c33f.
This is an upload digest, not an independent original-ZIP rehash.

Integration note: codec run[33] is a 32hex transaction token, not C02's complete
run/attempt/gate identity tuple. A future adapter must preserve and validate that
external session binding; it cannot substitute the codec field for it.

## Completed second Actions round

Tested source af851ee7a7d3c04fd4905785a51e6fc9a1226327, run41085869945
attempt1, job124166761142 completed SUCCESS. Installed archive/consumer builds
passed /W4 /WX; bridge26 native controls and all four process-death cuts passed.
Original record27, publication28 plus its two death cuts, and refusal8 passed
unchanged. Source/frozen-path guards passed. Actions compared built and installed
bridge, publisher and record archive bytes, retaining their hashes in installed.json.

Original producer artifact12991273158 contains88 files,341928 bytes, upload SHA256
5880b88ee98dfefe2c3a697054e475df06cfd176fb9089a4964b4acf15fa52fb.
This is producer upload evidence, not an independent ZIP rehash/audit.
Records, source/run/attempt receipts, maps, built and installed archives are retained.
Two of the authorized maximum three Actions rounds were used.

Independent source review found no blocking defect within the serialized,
trusted-handle, borrowed-custody contract. This is not integration acceptance.
The live bridge is now producer-tested at the exact source above; restart reader,
mid-write injection, full C02 session/phase binding, SDK admission, physical
power-loss safety and full P0 remain unaccepted. No common-source result is inferred.
