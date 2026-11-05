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

History: the first passing revision 074a06bd7099193a2c534db2ad31dfbf87e81413
(run41098408296, attempt1, job124210073306) already re-derived the same positive
counts and rejected twenty-one controls, but it never wrote the ZIP it had
verified, so its retention claim was false and it stands only as history.

Correction: the script now writes the exact bytes it verified to
audit-evidence/original.zip before running any control, and the receipt records
that path with its byte count and SHA256. Path normalisation for producer
inventories no longer merges keys silently: two manifest keys that collapse to one
member path are rejected as duplicate-manifest-key, which is exercised as its own
negative control. Deep byte controls replace the single existing key that
normalises to the member path and never add an alias, with a structural guard that
fails if the key set changes, so each control reaches the semantic rule it exists
to test instead of tripping the duplicate rule first.

Three failed attempts on this branch are retained, not hidden. 6714d847 failed
with HTTP 401 because the API token followed the artifact redirect into signed
blob storage. ccecb103 failed on `inventory` because the producer manifest records
Windows backslash separators for nested keys while archive members use forward
slashes. 924bcd63 failed with `accepted-negative:duplicate-manifest-key` because
the deep controls indexed the manifest with a forward-slash alias and, separately,
the duplicate control took whichever key came first, which could be a
separator-free top-level name that cannot be aliased at all. All three are auditor
defects, not producer defects; none of them accepted or rejected the producer, and
none is evidence about the producer.

## Completed audit with retained bytes re-hashed

Audit source 0cb31f6786208409e739c980a67838477f5e7dde, run41103549070, attempt1
(18:03:29Z to 18:05:03Z), two jobs: audit124226543442 and rehash124226669316,
both completed success. The audit job independently downloaded and rehashed
original artifact12991273158 (341928 bytes, SHA256
5880b88ee98dfefe2c3a697054e475df06cfd176fb9089a4964b4acf15fa52fb), re-derived
bridge26, four death cuts, unchanged original record27, original publisher28 plus
both death cuts, original refusal8 and the three installed built==installed pairs
from the retained members, rejected all twenty-two negative controls by their
intended rule, and wrote the verified bytes to audit-evidence/original.zip.

The rehash job then downloaded that artifact and re-measured the retained file,
printing `retained original ZIP re-hashed by a second job: 341928 bytes, SHA256
matches` after asserting the size, the producer digest, the receipt claim and the
outer binding. The retention claim therefore no longer rests on a field written by
the job that produced the file. Artifact12999342819 carries the result; its API
upload size is321391 bytes (compressed) and its digest is
sha256:5df51cbc3afcdeaec3c44d74f667f6e1caafd44452e7939715689ff3baab0c8b.

Acceptance is limited to the tested live-process serialized bridge at producer
source af851ee7. Full P0, migration admission, real-host lifecycle and physical
power-loss safety remain unaccepted. No result is transferred to a combined or
newer product source.


