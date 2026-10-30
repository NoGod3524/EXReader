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

Tested cases (26 total: 15 retained plus 11 new). Retained: four cut stages
(before/record/published/after classification), reader death and re-acquisition,
and the refusals for partial, missing slot, extra slot, tampered predecessor,
wrong payload, both targets present, and missing target. Caller-binding refusals:
stale admitted generation now refuses before any lease handle exists, while a
wrong root or wrong session binding still yields retained REFUSED evidence. New:
missing lease, empty lease, truncated lease, grown lease, tampered lease header,
on-disk generation mismatch, cleared PENDING, a write through a memory-mapped
view of the aged region while the reader is live, the failed-wr_prepare pin
release above, and the injected acquire-window case below. Byte-range locks cannot
prevent SetEndOfFile or mapped writes, so those are detection cases, not durability
claims; detection never clears PENDING and never grants admission.

## The acquire window, reproduced rather than argued

Pre-validation and the provider acquire are not one atomic step, and the pinned
provider must open the lease for write, so an in-place truncation inside that
window cannot be denied. Its OPEN_ALWAYS branch then re-initialises the zero-length
file, which clears PENDING and would have re-opened shared admission once this
adapter released the lease. Three mechanisms now cover that:

1. The whole 80-byte region is snapshotted before the acquire and settled again
   immediately after it, under the reader's own window.
2. A settled region that is a fresh initialisation (generation zero with PENDING
   cleared) cannot be a legitimate commit, because a commit from generation zero
   leaves generation one. In exactly that shape the pre-acquire bytes are written
   back so the domain's PENDING isolation survives, and the reader still refuses
   custody with restart-lease-window-restored. Any other movement refuses with
   restart-lease-window-race.
3. Both refusals retain the exclusive lease until the caller closes the object, so
   shared admission stays closed even when the bytes could not be proven repairable.
   Only a failure that never acquired a lease releases early.

The interleaving is injected, not assumed: `lm_rr_set_window_probe()` runs between
pre-validation and the acquire and receives the pinned lease path, and the probe
uses it to empty the file so the provider really does re-initialise it. Production
leaves the hook NULL and the sequence is unchanged. The repair writes through the
pinned handle, because a shared byte-range lock over [0,80) blocks every other
handle including a second one in the same process; if a platform still refuses that
write, the window is dropped, the write repeated, and the window retaken.

A second injected state covers recovery that must not be repaired. The lease ends
the window with an advanced generation and no PENDING, which is exactly what a
real concurrent commit looks like, so the reader refuses with
restart-lease-window-race and writes nothing back; the refused object keeps the
exclusive lease, and shared admission stays blocked while it lives. The case then
kills that process and records the residual: the drift survives, the next reader
refuses on the advanced generation, and the domain marker is gone. That is stated
as a recorded limit, not as durability across a crash.

Shared admission is measured, not asserted from a literal: every case asks the
provider for a shared lease afterwards and records the verdict, with explicit
policies for namespaces the provider refuses outright and for the two cases where
asking would either re-create a lease the reader must leave untouched or reproduce
the known hazard the control itself created.

## Completed run

Source 6db7c3dc, run41130069225, attempt1, completed success on windows-2022 with
all26 cases; the earlier 0d575448 run41105493390 passed the 25 cases without the
recovery-failure state. Newest artifact13011924675, API size507992 bytes. The injected window case
reported restart-lease-window-restored, lease_restored true, the lease back at
80 bytes, and shared admission still stale after the reader closed, which is the
isolation the earlier refusal path lost. Artifact13001202247 retains
restart/lease installed libraries, the consumer map, every per-case inherited
evidence file and the receipt; API size505718 bytes, SHA256
d9ccbd2bea0b1f9388fb66c792f2aad57b65bc62d269eecc5d3d10ff6e153d47. Old record27,
publisher28+2cuts, bridge26+4cuts and refusal8 were rerun unchanged in the same
job and passed. An earlier revision e74452f7 passed the 24 cases without the
window seam (run41099419879, job124213581187, artifact12998980254, 499274 bytes,
SHA256 43c83be9d177a2a008cb282dd22f92009b659ce5b0e96851eec137ffabfbc75c).

Five earlier attempts on this branch are retained, not hidden. bcf26e1b failed on
the tampered-header control because that control spliced a single replacement byte
with the tail of the lease and produced a70-byte file, so the size rule refused it
first. 42dcb66f passed every other case and failed on mapped-write because
lm_rr_check collapsed the specific drift reason into restart-not-qualified.
6454b95f and 774ae7dc failed on the injected window case with
restart-lease-restore because the repair could not write: a read-only pin cannot
write at all, and a second writable handle is blocked by the reader's own shared
window lock. Both are adapter defects; the repair now writes through the locking
handle. None of these attempts changed a lease, record or assertion budget, and
none is product evidence.

## Residual limits

The window can be detected, repaired when the bytes prove a re-initialisation, and
kept closed by custody when they do not; it cannot be prevented from outside the
provider, and a re-initialisation that leaves no distinguishable byte pattern, or
one that happens before this adapter first sees the file, is outside what this
adapter can repair. The provider's OPEN_ALWAYS branch remains the defect owner.
None of this is migration admission, COMMIT, SDK admission, real-host lifecycle or
physical power-loss evidence, and no full P0 claim is made.


