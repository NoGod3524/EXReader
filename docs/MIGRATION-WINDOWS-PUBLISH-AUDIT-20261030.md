# Independent Windows publication primitive audit

This separate branch contains only an independent audit script, Actions workflow
and this evidence document. It never modifies producer code, SDK, old tests or
the shared composition. Its pinned producer is c45d01c8fdec63851c5f4539813a8f66885eceb1,
run 41022476473 attempt 1, job 123952756428, artifact 12962371134 (198573 bytes;
SHA256 b23f790c642d04a57dbd22970974ed242541cf334a6ad9d0d903041b54b3415e).

The original ZIP is downloaded and independently rehashed only in Actions. The
auditor binds source/run/attempt/job/artifact, rejects unsafe or duplicate members,
validates original native28 plus both death cuts, unchanged record27 and refusal8,
checks original fixture bytes and manifests, installed record archive hash,
installed publication header and consumer map bindings. Nine negative controls
must reject tampered identities, counts, provider bytes, scope flags and missing
evidence. A new audit-result receipt retains source and member hashes.

This can accept only the bounded publication primitive. No migration admission,
COMMIT acknowledgement, host restart/reopen or physical power-loss safety is granted.
The original producer did not separately archive its built publication .lib;
installed bytes and map are audited, but independent built==installed equality
cannot be claimed. Process-death cuts establish retained bytes, not durable recovery.
Initial status before the run: audit not yet run; original producer failure remains in its own document.

## Completed independent audit

Audit source ef5d40c25c1ef6c88a2e865b1a3468c4e05393c8, run41024148733,
attempt1, job123958152950 completed success. Actions independently downloaded
and rehashed original artifact12962371134: 198573 bytes, SHA256
b23f790c642d04a57dbd22970974ed242541cf334a6ad9d0d903041b54b3415e.
All 28 native controls, before/after process-death evidence, original record27,
original refusal8, nine auditor rejection controls, original fixture manifests,
installed provider/hash/header and consumer map bindings passed this audit.

Audit artifact12962039116 retains original.zip plus run/job/artifact API metadata
and audit-result.json (full member manifest). Its API/upload size is193140 bytes,
SHA256 496de1a90f4b56a49a416a4777efbeff462be11f4cc4429014e3f383a281e18a.
The audit output archive itself has not been independently rehashed by a further
job; the original producer ZIP above has been independently rehashed.

Installed publication archive SHA256:
c6fff2c58e825dac4ac3d40085d792beb8fff1577983dc1a9c58e1968de12023.
Installed record provider SHA256:
2e0dac0e3dde32d6e1c1d4e4fa0fbd5dfad0e98893271bc32b35024038593308.
Acceptance is limited to the tested publication primitive at producer source c45d01c8.
Full P0, migration admission, real-host lifecycle and physical power-loss safety
remain unaccepted. No result is transferred to a combined or newer product source.
