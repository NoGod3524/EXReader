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
