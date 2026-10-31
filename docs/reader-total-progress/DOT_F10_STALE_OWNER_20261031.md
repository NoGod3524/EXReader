# F10 stale owner additive API — prepared, not yet executed

## Authority and ownership
User explicitly transferred only `extras/webdav-cleanup/include/exr_webdav_cleanup.h` and `extras/webdav-cleanup/src/cleanup_posix.c` to native dot F10. The independent branch `dot/f10-stale-owner-20261031` starts at sealed `b5e7fea87174f5e0baabfad97cf5cf7082f2d85e`. This is the old core/SDK727 background, not a claim that the common SDK8357 integration is done. The separate no-replace delta remains at `123e1852335ab16e3bc1863e050eb0a298b01cca`; no whole-branch merge occurred.

Original header blob: `47d2d4fa2ac066b21ad644479a84cf541b7f310e`.
Original source blob: `3cbc6f9a6135b64a19d4a8ee09b3fad3ddc4de16`.
Two-file prepared source: `19be8d8fddb8b0b916791f9d9725b2f76498d3e3`.

## Contract
Additive `exr_wc_abandon_stale` requires exclusive root ownership, no active transaction, unpoisoned receipt, exact slot/id/recorded inode/bytes/state identity. Only OWNED or SEALED may be abandoned; CLEANED of the same identity is idempotent. Historical device numbers are not compared across restarts; actual files must match the current root device. Unknown/replaced/non-private/symlink/extra-link/extra-entry objects are refused. Missing already-removed owned names may complete an interrupted cleanup. OWNED bytes are not sealed and are not constrained to receipt bytes=0; SEALED length is checked. Original recover still handles PUBLISHED only; receipt format and 64 lifetime slots are unchanged.

`exr_wc_borrow_sealed_fd` validates the existing component O_RDONLY hold descriptor and identity before lending it for pread within the transaction lifetime. Caller no-close/dup/fork obligations belong to the trusted cooperative-worker contract, not kernel enforcement. No pathname is exported and the pathname-only WebDAV publish API is unchanged. No sync integration or full F10 acceptance follows from this package.

## Approved experiment
Seven new files: five files under `tests/product/f10_stale_owner_20261031/`, this document, and the independent workflow. One Linux45 + audit15 minute run; no automatic retry. All compilation, syntax, testing and artifact processing occur only in Actions.

33 independent cases / 258 exact assertions. 29 use the installed unchanged-build-mode library; four real SIGKILL boundary cases use a separately labelled binary with existing production test-hook sites. These hooks choose exact crash timing, not fake cleanup outcomes. Eight independent semantic mutations verify source, consumer digest, actual death, EACCES, identity refusal, lifetime capacity, readonly access and ambiguous-state refusal. Original files/tests are not edited.

Coverage includes OWNED/SEALED actual process death, exclusive-lock conflict, real nonroot EACCES and retry, identity/permission/link/symlink/extra-entry refusal, unknown residue preservation, exact readonly borrowing and close lifetime, original PUBLISHED recovery, 64-slot capacity, interrupted cleanup convergence, and RESERVED/PUBLISH_INTENT refusal. Test secrets/data are synthetic; private fixture trees are not uploaded. A synthetic foreign-UID fixture uses Actions sudo chown on its own generated payload only.

## Status
Prepared only. No run/artifact identity exists yet. Full F10 remains false. Linux API evidence cannot grant other platforms, SDK/host UI integration, malicious same-UID resistance or hardware power-loss claims.
