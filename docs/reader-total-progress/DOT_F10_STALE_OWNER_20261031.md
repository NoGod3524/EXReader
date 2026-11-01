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
Prepared source is now verified by the single approved run below. Full F10 remains false. Linux API evidence cannot grant other platforms, SDK/host UI integration, malicious same-UID resistance or hardware power-loss claims.

## Fixed measured result and handoff

- Run [41254709863 attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/41254709863), measured source **1dd213236ccd77899cb58c7d7ec58d5d3bca4448**.
- Linux job **124695313603** and audit job **124695358391** both succeeded.
- Independent verdict: **api_accepted=true**, **errors=[]**, **33 cases / 258 assertions**, all **8 semantic negative controls rejected**. 29 installed-library cases and 4 labelled existing-hook real-kill boundary cases.
- Producer artifact **13061754329**, `f10-stale-linux-41254709863-1`, **101625 bytes**, SHA256 **bd79ea75b8475caea784b0f519f70d9d5073ddb67326b32df17e7c3d179da5e8**.
- Audit artifact **13062403971**, `f10-stale-audit-41254709863-1`, **711 bytes**, SHA256 **9ce612a724d9559498c28c7659c0c340481fc4bad239ce9c93697f4c34603862**.
- Both artifacts expire **2027-01-29T23:58:38Z**. Ordinary audit stdout supplies the verdict; no local artifact extraction was used.
- Approved budget: **1/1 run consumed**, zero reruns. This document seal is skip-ci and does not change the measured API.

The two additive interfaces are accepted within the stated Linux cooperative-owner contract. Existing recover semantics and 64-slot lifetime behavior are retained and exercised. This is **not** sync snapshot integration: the earlier high-level EACCES and SIGKILL residue observations remain unresolved until the product uses owned snapshots and exposes recovery status. The newly supported readonly descriptor does not silently extend pathname-only WebDAV upload.

Next phase must first specify a reviewed test design linking original F10 requirements to positive/negative scenarios, expected refusal causes and evidence boundaries. Keep at most one implementation line and one verification line for this module. Old no-replace and diagnosis branches remain sealed; no continuing CI or automatic extra team is authorized. Full F10 and the official total remain unchanged.

## Phase B — approved preparation, not yet measured

User approval 2026-11-01 00:20:51 UTC explicitly includes 13 paths, registry v2 persistence and rollback compatibility, and one Linux45 + audit15 run. Phase baseline is 659ef67bb6d408bb5653cedd03efe06e9d7dd6f9. Five production paths are WebDAV header/source, managed header/implementation and sync.cpp; six existing package files and two new test files complete the scope. The two accepted cleanup API files and original probe.c are frozen. No SDK or external host files change.

The exact cache no-replace helper/call delta from 123e1852335ab16e3bc1863e050eb0a298b01cca is explicitly authorized here. No whole-branch integration or common SDK8357 acceptance is implied.

### Frozen proof design (before execution)

Original F10 obligations: owned private snapshot identity, bounded transfer without pathname substitution, retained cleanup failure and restart ownership, no false immutable outbox acknowledgement, unchanged originals and bounded lifetime resources.

- Callback: actual TLS PUT of known bytes; exact monotonic bounded offset reads. Error, short read, oversize read, exception and cancellation refuse. Zero/over-ceiling length refuses before callback. Redirect not followed; 412 remains EXISTS requiring GET verification.
- Managed lifecycle: actual installed producer write/seal/read-only borrow/PUT/close, active-owner rejection and descriptor invalidation. Rename the original payload name and install replacement: held descriptor still sends original bytes; cleanup refuses replacement and preserves it.
- Permission/restart: real nonroot directory EACCES leaves registered pending work, restored permission permits retry. Real OWNED/SEALED SIGKILL and exclusive lock conflict; reopening reclaims only registered S identities. Existing old 33 cases retain all inode/permissions/unknown-entry/core refusal controls.
- Registry: v1 ordinary download/read-only reopen unchanged; first explicit S allocation atomically writes v2 and keeps D leaf/UUID exact. Actual old b5e7 WebDAV consumer refuses v2. Constructed bounded fixtures use public cleanup roots: 16 D roots refuse S despite free D slots; mixed 15D+1S stays total16 and S slot65 refuses. Legacy D OWNED remains pending. Bad CRC, unknown purpose and residual next preserve records. Separately labelled existing registry hook binary dies by SIGKILL before/after rename; old registry or registered unbound v2 remains, never silently adopted.
- Product sync: actual installed raw revisions + sync + managed WebDAV and TLS server. Original + revision bytes and outbox are checked across normal run, cleanup EACCES after committed PUT, process death, cancellation, response loss and restart. Pending cleanup keeps the original immutable outbox; retries use identical bytes and independent GET verification before ack.

Original 33 / 258 exact assertions / 8 semantic negative controls remain unchanged.
Phase B adds 29 scenarios / 187 fixed checks plus 10 exact-reason semantic mutations. Additional raw callback statuses and server-observed hash/conditional-write/GET facts are independently checked by audit. Callback, managed and sync results are separate. Missing evidence is a failed result, not skipped success.

### Persistent format and rollback boundary

One existing registry and exclusive lock retain the total 16 roots x 64 lifetime slots across D and S. No second pool, hidden capacity increase, slot reuse or D-to-S reassignment. v1 loads all existing roots as D and is not rewritten by ordinary reads/downloads. First S allocation opts into v2 with purpose per root using exclusive registry.next, fsync, rename and directory fsync. D recovery remains PUBLISHED-only; only registered S OWNED/SEALED can be abandoned. Unknown purpose/CRC/partial registration fails closed.

Old binaries refuse v2; this batch has no automatic downgrade. Restoring old registry would orphan new ownership and is not an approved rollback. Registry crash tests are process death, not hardware power loss.

### Evidence limits

Linux managed upload snapshots only, trusted cooperative owner. Not all host credentials/OSes, not defense against malicious same-UID writes to the held inode. Verification GET and other existing private_file paths remain outside this narrow snapshot cleanup change; any observed residual is retained as a gap, never treated as whole-F10 success. Full F10 remains false. Budget B is one new 60-minute run with zero automatic reruns; prior red and green runs remain sealed.

Preparation status: source/test design committed with skip-ci; stable SHA requires independent review before the sole activation.

## Phase B measured result — retained failure

- Run [41257244190 attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/41257244190), source **6230fc8d1dc531d9d7c4d574d79cc6d9c458bda0**.
- Linux job **124702921508** passed ownership/SDK guards, Actions syntax and all builds. Producer collected observations; its success does not equal acceptance.
- Audit job **124703554193** failed. Original API **33 / 258 / 8** remains accepted with errors=[].
- New snapshot verdict is **false**; callback/managed/sync aggregate verdicts are false. Four gated sync cases reported exceptions because the PUT boundary was not reached. Network-dependent PUT/GET assertions failed. No errors were reported for local registry purpose/CRC/capacity, process-death recovery, permission retry or old-client v2 refusal checks, but that does not make the whole package accepted.
- Producer artifact **13063907551**, **2452124 bytes**, SHA256 **a4f4c436d92f77825832b653c21f33ce525c3f5bde2bc2b07dff940691bf7842**.
- Audit artifact **13063184364**, **1422 bytes**, SHA256 **f40968cd788095272f09fc4659660009f6156383abfda399c4bacd673aa2cb32**.
- Expiry **2027-01-30T00:33:16Z**. Budget B **1/1 used**, no retry.
- New negative controls that rely on already-failed network/outbox guards are explicitly not accepted; no washing of failed baselines.

Static diagnosis found the fixture generates cert.pem and the existing trust helper copies the original filename to /usr/local/share/ca-certificates. Linux update-ca-certificates expects .crt, so this fixture does not correctly install its trust anchor. This is a confirmed setup mismatch from source, not yet a claim that original artifact raw status has been read: ordinary logs contain the audit differences but not those numerical producer values. Next proposed test-only repair must first print the original fixed artifact observations, use cert.crt without disabling TLS checks, expose per-case evidence to ordinary logs, retain all old/new assertions and rerun only with a separately approved budget. No production correction or automatic rerun has been performed.

F10 remains pending. This doc-only skip-ci seal preserves the measured failure and is not a stop/completion of the user's full goal.
