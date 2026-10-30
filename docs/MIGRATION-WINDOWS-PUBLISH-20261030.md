# Windows private-root to public-parent publication primitive

Additive installed-library candidate, not a Windows recovery coordinator or full P0.
Base: 2743f32a4eccd5823657da19cb4f77f2411424af. Frozen SDK, original migration
executables, old assertions and the default-off record option are unchanged.

The standalone package consumes installed record/provider headers and archive.
Its only destination is the immediate public parent retained by a qualified
private-root context, on the same local NTFS volume. Source is a trusted adapter
retained GR/GW/DELETE, share-read-only handle. Full volume64/FileID128 identity,
SHA256, parent custody and source membership are checked before native no-replace
rename; the final destination is checked afterward. No copy fallback, overwrite,
permission broadening, recursive cleanup, recovery admission or COMMIT inference.

Caller retains all handles. A false return with published=true means native rename
succeeded but subsequent verification failed: preserve evidence and require explicit
recovery. Success is process-observed publication, not directory-fsync equivalence
or physical power-loss durability. The existing Windows startup refusal stays intact.

Actions independently builds the installed provider and primitive, builds a consumer
against installed archives only, runs positive/refusal/identity checks and process
death cuts before and after publication, then repeats original record27 and refusal8.
Original tests and admission guards are not relaxed. New workflow has its own narrow
additive path admission. Evidence must be tied to the exact source and original ZIP;
until a completed run and independent audit exist, this document claims no acceptance.

## Retained first Actions result

Source 62a71a2e238cb434feacd3e55a7074f6f84ade44, run 41019097661, job
123942062630 failed. Frozen/admitted paths, installed SDK/provider and both
publication archive and independent consumer built successfully with /W4 /WX.
Original record27 passed. Native publication consumer completed 24 controls with
19 passed and 5 failed: the first positive cross-directory rename returned
STATUS_SHARING_VIOLATION (0xC0000043), Win32 32. Later failures are publication
consequences. Process-death cuts and original refusal8 were not reached.

The retained original artifact is 12960368109, 174564 bytes, producer ZIP SHA256
d0c86b91eec9dd2477711031ea2cebe87907c2a58a57f13cd47429f73ea53850.
This hash is from Actions upload output, not an independent ZIP rehash.

Existing parent custody pins permit FILE_SHARE_READ only. A cross-directory
native rename's destination-directory write access is the suspected conflict;
no handle sharing was widened, no pin was dropped, and no copy fallback was
introduced. A separately reviewed directory-custody policy is required before
attempting admission. This source is not an accepted publication primitive.

## Separately named initial publication custody

The next source introduces opaque lm_wp_custody_prepare and
lm_wp_publish_prepared APIs. Original wr_* code and sharing modes remain
byte-for-byte unchanged. Preparation acquires independent directory handles with
FILE_SHARE_READ|FILE_SHARE_WRITE but never FILE_SHARE_DELETE while every original
qualification pin is still live. It validates each full identity, then the caller
explicitly closes its original context. This is a continuous deny-delete handoff,
not closing pins or widening handles during publication. Old lm_wp_publish retains
its original safe refusal under the original directory-sharing contract.

Tradeoff: directory child writes are now admitted. This does NOT mean the namespace
is globally immutable. The retained source handle still disallows write/delete
sharing; the destination leaf is published using kernel no-replace semantics and
checked independently. Ancestor/root/parent renames remain excluded by retained
deny-delete handles. New tests include parent/root/source rename attempts, source
and published-file write-open attempts, and an admitted sibling creation, alongside
existing file/directory/reparse collisions and full FileID/hash controls. The new
suite requires 28 native controls and both process-death cuts; original record27
and refusal8 remain unchanged. No real migration admission is supplied.
