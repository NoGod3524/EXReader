# WebDAV managed cross-process cleanup component (2026-10-31)

## Scope and authorization
Common base: 666d0d81730ac3cf7caea52b05ca1f01b1d183b1 (sealed bounded-retry result).
Core branch codex/dot-webdav-managed-cleanup-core-20261031, core commit dba079b550f9ec83054e6b7b0b7475f43bc1739f,
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

## 历史状态（原 producer run）
Initial run 41169665419/A1 (tests d262e079d9b377a077f73f7155dd8279e04ad7dc, core 6ba50a89a82f82212fcadaf8d825176cc9fbe856)
failed on both platforms at core compilation: one implicit declaration of renameat, no other diagnostic; no test ran.
The single targeted correction adds <stdio.h> to the core (8de75fa97fed32b25fa65eae4d7fa7b5f6b07693), repins the tests,
and adds two precautions to not-yet-compiled test code (an explicit uint32_t cast, every runner exception recorded).
Correction run 41169795520/A1 (tests 8c60ab9a0b1846c79dbac323d762e155f0acf816, core 8de75fa9): macOS 30/30; Linux 29/30,
case 10 failed (worker exit 1; detail only in the artifact). Cause, consistent with Linux-only failure: ext4 reused the
freed inode number for the recreated payload, so dev/ino identity accepted the replacement. The user then approved all
corrections in this conversation. Fix core dba079b550f9ec83054e6b7b0b7475f43bc1739f: a component-only O_RDONLY payload
handle stays open from begin until the slot is cleaned or tx_close, keeping the original inode allocated; the runner now
prints the last worker lines of a failed case.
Run 41170057297/A1 (tests 12da717cef38c90ae2097e52d33f7b3682aef043, core dba079b5): success, 30/30 on both platforms
with the complete fixed name set; file-set, archive-export/hook-absence, header identity and link-line audits passed.

| Platform | Job | Artifact ID | Name | Bytes | Digest |
|---|---|---|---|---|---|
| Linux x86_64, euid 1001 | 124445872128 | 13030965993 | webdav-managed-cleanup-Linux-41170057297-1 | 86807 | sha256:25b95345c6607c6fc0fadd54c95bdd62c515bcc460498664bddabdf88c88b442 |
| macOS arm64, euid 501 | 124445872050 | 13030352879 | webdav-managed-cleanup-macOS-41170057297-1 | 74101 | sha256:72ac0c1e56854a06669e01b7e9714605562c03275e482853d0088901f8d566fe |

Claims: transient_cleanup_passed=true (inherited); managed_cleanup_component_passed=true pending independent
certification of the artifacts above (not yet done); product_cleanup_passed=false; crash_recovery_validated=false
(SIGKILL process-death recovery only, no power-loss proof, no product wiring).
Not done: managed WebDAV entry point, first host root creation and UUID persistence, startup recovery, pending display,
unpublished staging abandon policy and root rotation. Old unreceipted residue is never adopted. Formal 95/108 unchanged.

## 2026-10-31 GPT 上游补证接管

用户在产品接入聊天明确要求“把这两个上游阻塞也接管解决，补齐原始证据并完成独立审计，然后继续产品接入和 CI 验证，直到完成”。
本次在原 tests 分支补齐原始观测，core 固定为 dba079b550f9ec83054e6b7b0b7475f43bc1739f；原 30 个用例、断言和每进程 30 秒界限保留。
results.json 新增 raw schema 1：真实子进程 PID/argv/returncode/kill_sent/signal_sent/timed_out；before-case、held、after-death、before/after-recovery、final 的 no-follow 文件元数据及原始字节；C 进程逐次恢复快照，以及 EACCES canary 和 cleanup 的实际返回值、errno、euid、mode。
快照在 fixture teardown 前保存；失败同样保留记录。后续独立验证器须自己解码 receipt/CRC 并重算目标身份、进程死亡与恢复幂等性，不能仅采信 PASS。
历史 run 41169665419、41169795520、41170057297 及各次失败原因继续保留；新 run 与审计终态见下节。
所有编译、语法检查、运行和 ZIP 处理仅发生于 GitHub Actions。

## 补证与独立审计终态

受测 tests SHA：711e1fc8a8c5b86f210bcddc934c479599387582；core SHA：dba079b550f9ec83054e6b7b0b7475f43bc1739f。
[Producer run 41174402876](https://github.com/NoGod3524/EXReader/actions/runs/41174402876) / attempt 1：Linux job 124458850309、macOS job 124458849971 均 completed/success，原 30 项各 30/30。

| 平台 | Artifact | Bytes | SHA-256 |
|---|---|---:|---|
| Linux | 13031778309 / webdav-managed-cleanup-Linux-41174402876-1 | 114285 | 4520aae748dff728019ce865116685930cd887a3783c827c2ac3bf4422554946 |
| macOS | 13031863107 / webdav-managed-cleanup-macOS-41174402876-1 | 101735 | 3c8533a40556485d8818821068fe6cceef67e83e94cd15d26d59ba431abfe2ec |

独立 verifier 受测 SHA：ea54eb95eafc62a2db8fec4547eab142856f9351；[Audit run 41174612650](https://github.com/NoGod3524/EXReader/actions/runs/41174612650) / attempt 1；job 124459479516 completed/success。
审计 artifact：13031974546，232564 bytes，SHA-256 88b3580ea082c941c6286dc6bb542683cc2bf75675944981b415b27462579efa。
实测 audit_completed=true、evidence_integrity_passed=true、critical_evidence_complete=true、audit_passed=true、errors=[]。
每平台重算 30 个 case、10 组实际进程死亡及 receipt/recovery 对；各 8 个原负控和 10 个 raw 负控全部按预期拒绝，共 36 个。原始 ZIP、源码字节和输出均保存在 Actions artifact。
独立性为独立检查实现与独立 Actions 执行；本次补证和 verifier 扩展均由接手 GPT 编写。历史批准记录未被补造，core 的已披露 valid-next 修订维持原字节。
此封存提交只更新文档，上述受测 SHA 不变。产品验证另见 [GTK 接入记录](https://github.com/NoGod3524/EXReader/blob/codex/gpt-webdav-product-integration-20261031/docs/reader-total-progress/GPT_WEBDAV_PRODUCT_INTEGRATION_20261031.md)，组件审计本身不授予产品验收。正式 95/108 保持。
