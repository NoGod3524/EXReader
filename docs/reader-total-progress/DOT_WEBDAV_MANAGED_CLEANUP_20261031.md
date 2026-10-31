# WebDAV managed cross-process cleanup component (2026-10-31)

## Scope and authorization
Common base: 666d0d81730ac3cf7caea52b05ca1f01b1d183b1 (sealed bounded-retry result).
Core branch codex/dot-webdav-managed-cleanup-core-20261031, core commit 6ba50a89a82f82212fcadaf8d825176cc9fbe856,
exactly four new files under extras/webdav-cleanup/.
Tests branch codex/dot-webdav-managed-cleanup-tests-20261031, exactly five new files: tests/webdav_managed_cleanup_20261031/
CMakeLists.txt, worker.c, run.py, this workflow and this document.
The user approved the local Git/gh route, exclusive worktrees, Claude as sole writer, and the four contract amendments below.
Build, syntax, tests and artifact parsing run only in GitHub Actions. Budget: Linux 30 min, macOS 30 min, independent
certification 10 min; one initial run plus at most one targeted correction. Core and tests SHAs are recorded separately;
this is a component result, not a single-SHA product integration. Product wiring needs a separate approval.

## Component
Package EXReaderWebDAVCleanup 0.1.0, target EXReaderWebDAVCleanup::exr_webdav_cleanup, installed header
include/exr_webdav_cleanup.h and static library lib/libexr_webdav_cleanup.a. POSIX only, C11.
A dedicated root (0700, owned by geteuid) holds a permanent .lock under a non-blocking exclusive flock for the root's
lifetime, a 4160-byte .receipt replaced atomically through .receipt.next (file fsync, rename, directory fsync), and
transaction directories tx-<id> each with one fixed payload leaf. 64 lifetime slots, never reused; one active transaction.
States RESERVED -> OWNED -> SEALED -> PUBLISH_INTENT -> PUBLISHED -> CLEANED. RESERVED is durable before mkdir; INTENT is
durable before the no-replace link; a link success returns OK/published=1 and later persistence failures are reported
separately through receipt_uncertain/cleanup_pending and stop further mutation.

## Approved amendments to the handoff API v1
1. A definite link failure (EEXIST, EXDEV, ENOENT, EACCES, ...) rewrites the slot to SEALED and returns EXISTS/IO with
   published=0. An existing destination is detected before INTENT. Only an unknown link outcome stays in INTENT.
2. open_at discards .receipt.next only when .receipt is valid and .receipt.next is a valid receipt of the same root whose
   generation is exactly one higher (its rename never happened, so no later step ran). Any other residue is REFUSED.
3. Inodes are compared across opens; device numbers only against the root's current st_dev, never a stored value.
4. Fixed little-endian layout. Header: magic EXRWCRCT, version 1, count, generation, root inode, uuid[16], 12 reserved
   bytes, CRC-32. Slot: state, 4 reserved, bytes, directory inode, payload inode, id[16], 16 reserved. CRC-32 (IEEE)
   covers the whole image with its own field zeroed; it detects damage and is not a signature.

## Safety model and limits
Cooperative processes only: no handle sharing, forking, concurrent calls or other namespace writers. It is not robust
against a non-cooperative same-UID process with write access. fstatat followed by unlinkat is not an atomic
remove-by-inode; safety comes from the lock and the controlled namespace. Existing residue is never claimed by prefix,
mtime, PID, UID, hash or inode; published targets are never deleted, replaced or chmodded; success is never reported as IO.
RESERVED, OWNED, SEALED and INTENT slots are kept pending by recovery. RESERVED and INTENT are never reclaimable in v1,
so the finite slot lifetime needs a root rotation protocol in product wiring. A torn .receipt.next (crash during its
write) still fails closed. flock and link semantics assume a local filesystem. SIGKILL proves process-death recovery, not
power-loss durability (macOS uses F_FULLFSYNC where available).

## Test design
Hooks exist only when the core source is compiled with PRIVATE EXR_WC_TEST_HOOKS: synchronous notification, no value
injection. wc-consumer links only the installed package; wc-hookworker compiles the same pinned core source directly and
never links the installed archive. The workflow audits the exact file sets, the separate core checkout, the ten exported
symbols, hook absence from the archive and consumer, the header identity, and both link lines.
30 fixed cases, each in a fresh tempfile directory with a 30 s worker limit and HELD/hook marker handshakes:
01 normal publish and cleanup; 02/03 explicit abandon OWNED/SEALED; 04 unauthorized abandon refused; 05 same-process and
06 cross-process lock (holder SIGKILLed, then the lock is free); 07 active tx blocks root close and tx_close keeps the root
lock; 08 existing target not replaced; 09 root/registered txdir as destination refused; 10 payload inode replacement and
11 payload symlink refused and preserved; 12 unknown entry preserved until its owner removes it; 13 real non-root EACCES
(canary proves errno 13, txdir 0500, permissions restored, recovered by a new process); 14 bounded paging and idempotence;
15 65th lifetime slot LIMIT with out=NULL/fd=-1 (also after reopen); 16 wrong UUID; 17 legacy unreceipted directory;
18 root symlink; 19 CRC damage; 20 residual .receipt.next (garbage and same-generation copy) fails closed;
21 illegal leaves; 22-30 SIGKILL at directory_created, payload_created, owned, sealed, publish_intent, linked, published,
alias_unlinked and receipt_next_synced(RESERVED). Every kill case checks the disk residue, reopens in a new process,
recovers twice for idempotence and checks destination bytes, hash, dev and inode (nlink may drop by one only).

## Status
Pending the first Actions run. Claims: transient_cleanup_passed=true is inherited from the base;
managed_cleanup_component_passed, product_cleanup_passed and crash_recovery_validated stay false until certified.
Not done: managed WebDAV entry point, first host root creation and UUID persistence, startup recovery, pending display,
unpublished staging abandon policy and root rotation. Old unreceipted residue is never adopted. Formal 95/108 unchanged.
