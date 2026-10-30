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
different reader process. Four cut stages plus reader death/re-reacquire and ten
negative/classification cases are checked. Later SHARED calls must remain STALE.
Old record27, publisher28+2cuts, bridge26+4cuts, refusal8 are rerun unchanged.
Built/installed archives and map/fixture/source/run receipts are archived.

No physical-power-loss/directory-durability claim, no worker/host/SDK integration,
no C02 stage-policy validation, no clearing or retry of partial records, no fullP0.
Initial status: source candidate, Actions pending. Maximum3 authorized rounds.
