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
