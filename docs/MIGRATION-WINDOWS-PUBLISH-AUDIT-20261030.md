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
Status: audit not yet run; original producer failure remains in its own document.
