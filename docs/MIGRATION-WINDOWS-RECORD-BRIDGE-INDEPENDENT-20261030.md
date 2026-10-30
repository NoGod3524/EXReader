# Independent Windows record bridge audit

This separate branch contains only an independent audit script
(`tests/migration/windows_record_bridge_independent_20261030/audit.py`), its
Actions workflow and this evidence document. It never modifies producer code,
SDK, old tests or the shared composition. Its pinned producer is
af851ee7a7d3c04fd4905785a51e6fc9a1226327, run 41085869945 attempt 1,
job 124166761142, artifact 12991273158 (341928 bytes;
SHA256 5880b88ee98dfefe2c3a697054e475df06cfd176fb9089a4964b4acf15fa52fb).

The original ZIP is downloaded and independently rehashed only in Actions
(`GITHUB_ACTIONS` guard, read-only token). The auditor binds
source/run/attempt/job/artifact, rejects unsafe, duplicate or linked members and
oversized archives, then parses the retained inner evidence itself instead of
trusting the producer's summary: original bridge 26 aggregate checks and four
process-death cuts, unchanged original record 27, original publisher 28 plus both
death cuts, and the original eight refusal cases. It recomputes every record
seal, ordinal/phase order, predecessor link and full 48-hex identity, checks
publication layout and exact payload bytes, proves built==installed equality for
the bridge, publication and record libraries, and binds each consumer `.map` to
its library. Twenty-one negative controls must reject tampered identities, counts,
scope flags, missing evidence, mutated payloads, mutated reserved slots and
re-sealed records; the `sealed-*` controls rewrite the producer manifest so that
no outer archive hash or manifest comparison can be the rejection mechanism, and
only the semantic checks can fail. A new audit receipt retains the pinned outer
binding, every negative-control rule name and the retained limits.

This can accept only the bounded live-process serialized bridge. No migration
admission, COMMIT acknowledgement, host restart/reopen, SDK admission or physical
power-loss safety is granted. The original 26 checks are aggregate producer
output, not 26 independent re-executions, and the original NTFS record file ID
cannot be re-measured from a ZIP member, so `previous_id` is validated as syntax
and chain binding only. Process-death cuts establish retained bytes, not durable
recovery. The auditor never executes any binary it retrieves, and no result is
transferred to a combined, newer or product source.

Initial status before the run: audit not yet run; the producer's own failure
history remains in its own document.
