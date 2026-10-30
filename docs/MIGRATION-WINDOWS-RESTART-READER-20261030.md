# Fresh-process restart evidence reader candidate

Base99ac7522ab5d2cdd512b494d5427b5c95c0a2b98. New isolated package; original
C01/engine/SDK/provider/tests remain unchanged. C01 installed provider is built
separately in Actions from ccd7fec67eb8aa463b09533ce320820f2da472d9.

This reader reacquires an EXCLUSIVE lease itself with a caller-supplied stable
identity and expected generation, requires persisted PENDING, then creates fresh
original wr_context qualification and opens retained read-only/share-read handles.
This fresh restrictive custody remains live solely for inspection; no rename or
publisher operation is attempted beneath it. It is not a cast from publisher
custody, nor an attempt to reuse the killed owner's handles.

Caller must provide independently trusted complete external session binding,
including mapping of the actual C01 admission domain to lease_identity. The
record codec's run32hex is not the product Actions/run/attempt/provider/gates tuple.
Reader checks the codec binding and phase FORMAT, not coordinator phase legality.
The test expected manifest is fixture input, NOT a production trusted-manifest
provider. It is deliberately outside the production reader's authority.

Classification: REFUSED, RESERVED (all4096 zero reservations), PREFIX (valid
records then reservations), COMPLETE_EVIDENCE (all canonical linked records), or
NAMESPACE_CONFLICT (source/destination both present or both absent).
Unknown/missing/partial/reordered/extra slot entries refuse. The reserved slot
namespace bridge-slot-*.rec is enumerated; unrelated sibling names are not adopted.
The reader verifies actual full49 target/root/parent identities, actual predecessor
record identity, canonical seal/SHA, payload digest and retained bytes.
Target digest stays1MiB; record4096; slots32. No old budget/assertion changes.

Even COMPLETE_EVIDENCE is NOT COMMIT, restart SDK admission, generation advancement,
or permission to clear PENDING. No lm_wl_exclusive_commit call exists. Closing
releases read handles and the exclusive lease, but leaves PENDING unchanged;
participating SHARED callers remain STALE. Errors retain the reader object/lease
when acquisition succeeded; callers inspect classification and remain closed.
All API calls serialized; no privilege boundary/thread-safe claim.

Actions creates writer processes using the installed bridge/publisher+C01, proves
a competing reader cannot acquire while they live, kills them, then launches a
different reader process. Four cut stages plus reader death/re-reacquire and the
negative/classification cases below are checked. Later SHARED calls must remain
STALE. Old record27, publisher28+2cuts, bridge26+4cuts, refusal8 are rerun unchanged.
Built/installed archives and map/fixture/source/run receipts are archived.

No physical-power-loss/directory-durability claim, no worker/host/SDK integration,
no C02 stage-policy validation, no clearing or retry of partial records, no fullP0.

## Containment added in this revision

The pinned C01 provider is frozen outside this package, so its two weaknesses are
contained in the adapter rather than patched in place. First, it opens the lease
file with OPEN_ALWAYS, which would silently re-create or re-initialise a lease
whose file was deleted or truncated. The reader now qualifies the lease namespace
itself before any lease handle exists: the lease directory and the exactly
80-byte lease file are pinned with deny-delete sharing, the 48-lowercase-hex
identity is validated, the 64-byte header must be bound to that identity, the
on-disk generation must equal the caller's expected generation, and PENDING must
already be set. A missing, empty, truncated, oversized, header-tampered or
counter-mismatched lease is refused with a distinct reason, and nothing is
written, re-created or re-initialised. Second, the provider caches
generation/pending at acquire time and its own check re-verifies only the
identity header. The reader re-reads the whole 80-byte region from disk on every
check under its own shared byte-range window over [0,80), which is disjoint from
the provider's 4096/4097 admission locks and therefore cannot collide with a live
C01 holder, and it refuses on any drift between disk, the value retained at open
and the provider cache. Third, a failed wr_prepare already holds ancestor pins;
the context is closed immediately on that path instead of being left for close,
and this is proven by the private root staying renameable while the retained
reader object is still alive.

Tested cases (24 total: 15 retained plus 9 new). Retained: four cut stages
(before/record/published/after classification), reader death and re-acquisition,
and the refusals for partial, missing slot, extra slot, tampered predecessor,
wrong payload, both targets present, and missing target. Caller-binding refusals:
stale admitted generation now refuses before any lease handle exists, while a
wrong root or wrong session binding still yields retained REFUSED evidence. New:
missing lease, empty lease, truncated lease, grown lease, tampered lease header,
on-disk generation mismatch, cleared PENDING, a write through a memory-mapped
view of the aged region while the reader is live, and the failed-wr_prepare pin
release above. Byte-range locks cannot prevent SetEndOfFile or mapped writes, so
those are detection cases, not durability claims; detection never clears PENDING
and never grants admission.

Initial status: source candidate, Actions pending. Maximum3 authorized rounds.

## Completed run

Source e74452f7f838e7d02a14e3e6ba89df923fce0466, run41099419879, attempt1,
job124213581187 completed success on windows-2022. All24 cases passed: the four
cut stages, reader death and re-acquisition, the seven retained content and
namespace refusals, the three caller-binding refusals, and the nine new cases.
The new cases include the missing, empty, truncated, grown, header-tampered,
generation-mismatched and PENDING-cleared leases (each refused with its own
reason and with the lease bytes left exactly as the negative control wrote them,
so nothing was re-created or re-initialised), the memory-mapped write that the
live reader must report as restart-lease-disk-drift even though byte-range locks
cannot prevent it, and the failed-wr_prepare case where the private root stays
renameable while the retained reader object is still alive. Artifact12998980254
retains restart/lease installed libraries, the consumer map, every per-case
inherited evidence file and the receipt; API size499274 bytes, SHA256
43c83be9d177a2a008cb282dd22f92009b659ce5b0e96851eec137ffabfbc75c. Old record27,
publisher28+2cuts, bridge26+4cuts and refusal8 were rerun unchanged in the same
job and passed.

Two earlier attempts on this branch are retained, not hidden: bcf26e1b failed on
the tampered-header negative control because that control spliced a single
replacement byte with the tail of the lease and produced a70-byte file, so the
size rule refused it first; 42dcb66f passed every other case and then failed on
the mapped-write case because lm_rr_check collapsed the specific drift reason
into restart-not-qualified. Both are test/adapter defects; neither changed any
lease, record or assertion budget, and neither is product evidence.

