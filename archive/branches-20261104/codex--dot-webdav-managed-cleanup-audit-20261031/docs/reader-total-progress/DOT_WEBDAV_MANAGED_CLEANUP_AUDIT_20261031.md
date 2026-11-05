# Managed cleanup：原始证据独立重算审计

状态：补证独立审计已通过；实际 run、artifact 及重算结论如下。当前用户明确接管上游补证和审计，并授权继续到产品 CI 完成。
本提交延续既有独立验证程序，不导入或执行 producer 代码，只读取固定 ZIP 和源码文本。原 prepared 程序及文档（本地 deec56424e494848a17c799a357525f0852fed62）已按原字节保存在父提交 a788f82b9c84ea6fab1f5e8e3f3e928b1b3be98e；没有追认它曾运行或接受。
新增原始字段检查由本次接手者编写，独立性指与 producer 分离的实现、执行和重新计算。

固定 producer：run 41174402876 / attempt 1；tests 711e1fc8a8c5b86f210bcddc934c479599387582；core dba079b550f9ec83054e6b7b0b7475f43bc1739f。
Linux 30/30，job 124458850309，artifact 13031778309，114285 bytes，SHA-256 4520aae748dff728019ce865116685930cd887a3783c827c2ac3bf4422554946。
macOS 30/30，job 124458849971，artifact 13031863107，101735 bytes，SHA-256 3c8533a40556485d8818821068fe6cceef67e83e94cd15d26d59ba431abfe2ec。
完整 source/header/archive/consumer/hookworker SHA-256 均固定在 verify.py 中，并与 API 源码和 ZIP 内字节重新比对。

每个平台保留原 8 项篡改负控，并新增 10 项原始数据负控：SIGKILL 返回码、canary errno、cleanup errno、目标 inode、nlink、内容、receipt CRC、UUID、状态以及第二次恢复变化。修改 JSON 后重新计算内部 seal，拒绝必须来自语义检查。
重新计算覆盖真实子进程生命周期、十组死亡观测、权限与 canary、receipt 4160 字节独立 CRC/布局解码、发布目标 inode/内容/大小/链接数、保留 pending 残留、两次恢复幂等性和 valid-next 修订边界。
原始 ZIP 仅在 Actions 下载、哈希、解析和保留；不在本机或 VM 解包。原始失败及旧缺口历史保留如下。


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

## 历史 prepared 记录（适用于旧 run，不作为当前结果）

# Independent managed cleanup artifact audit

Status: prepared; no audit result claimed. One authorized Ubuntu Actions job,
10 minutes, no correction round. No product/worker execution or rebuild.
Base d69bae312fd0791dac119509437fb29abc92a25c; three new paths only.
Branch codex/dot-webdav-managed-cleanup-audit-20261031.
User grant: Sentinel_6361505dfa0c8191a755cb2d15e67c37, relayed 2026-10-31 04:57Z.

## Immutable producer identities
Run 41170057297, attempt 1, tests 12da717cef38c90ae2097e52d33f7b3682aef043,
core dba079b550f9ec83054e6b7b0b7475f43bc1739f, original base
666d0d81730ac3cf7caea52b05ca1f01b1d183b1. Separate source SHAs, not a combined product.
- Linux job124445872128: artifact13030965993, 86807 bytes,
  sha256:25b95345c6607c6fc0fadd54c95bdd62c515bcc460498664bddabdf88c88b442.
- macOS job124445872050: artifact13030352879, 74101 bytes,
  sha256:72ac0c1e56854a06669e01b7e9714605562c03275e482853d0088901f8d566fe.
Producer source and installed-header hash:
5c683d07eb87c21d521bab95b0fc56738da12975ebbc022257ef338498edd979.
Source C hash: 2ebb5a27b62998b6fc185277a04d81b506871880f7edb3860923f775dfb70590.

Read-only API/log inspection confirmed both platforms reported all 30 fixed names,
file-set/export/header/link guards passed. This is not yet independent ZIP authentication.
History: 41169665419/A1@d262e079d9b377a077f73f7155dd8279e04ad7dc failed both
core builds, cases skipped; 41169795520/A1@8c60ab9a0b1846c79dbac323d762e155f0acf816
passed macOS, failed Linux case10; third run above passed both. Prior failures remain.

## Three distinct evidence levels
1. Authenticate producer execution: fixed outer ZIP identity, exact source bindings,
   actual installed header/archive/consumer/hookworker bytes, 30 unique individual case
   records, per-case PASS or HELD/OPEN/RECOVER/STATUS logs, same original source assertions.
2. Independently recompute retained raw evidence: recovery counters/states and handshake
   sequence can be recomputed. Several transient observations were never serialized.
3. Product correctness: absence of retained observations is NOT proof that a product
   assertion failed. The producer's source-bound assertions and reported 30/30 remain
   valid execution evidence at their stated level.

The audit returns a nonzero completeness gate if required raw evidence is missing;
it separately reports audit_completed, evidence_integrity_passed,
producer_case_execution_authenticated, critical_evidence_complete,
audit_passed and product_failure_proven. Never relabel missing evidence as a failed
product test, never turn known gaps into zero/true measurements.

## Known serialization gaps (no producer edits or new observations)
- Independent published-target preservation: case13 and published kill cases27-29
  check before/after dev/ino/hash/nlink in producer memory, but do not save those values.
- Independent actual permission refusal: case13 C CHECK verifies nonroot/canary
  unlink EACCES and cleanup EACCES under0500. Only PASS reaches the log, not numeric
  syscall/permission records. Source-bound execution can be authenticated, raw errno
  cannot be independently recalculated from the archive.
- Independent SIGKILL observation: cases22-30 retain HELD and RECOVER logs, but do not
  serialize spawned PID/returncode or disk snapshots. The runner's returncode==-9
  assertion is pinned, but the auditor cannot reproduce its discarded inputs.

## Disclosed contract amendment and approval provenance
The frozen handoff draft refused every residual .receipt.next. The producer document
at tests12da717c explicitly labels four "Approved amendments to the handoff API v1",
including valid same-root next generation=current+1 reconciliation, and states user
approval. Thus the author DID disclose this policy; this audit evaluates the pinned
actual source and revised documented contract, not the superseded draft as latest law.
The original user approval transcript for those amendments was not independently
available to this audit; repository self-description alone is not that transcript.

Actual core open_at lines474-490 validates current receipt/root inode/expected UUID,
then requires next receipt structural decode, same UUID/root inode, generation+1.
wc_decode128-161 checks full4160-byte CRC, version, reserved bytes, count<=64,
generation/root inode nonzero, all64slots (unused slots zero; state range; reserved
fields; RESERVED has no byte/inode values, other states require inode identities).
Receipt reads require O_NOFOLLOW, private regular file, nlink1, exact4160byte length.
The branch does not compare old/new slots for a single legal state transition or a
predecessor hash. It discards ONLY .receipt.next, fsyncs root and keeps the old receipt.
This matches the disclosed amendment under the cooperative-namespace model; absence
of a predecessor link is not alone declared a safety bug. Case20 rejects malformed
and same-generation residue; case30 explicitly tests a valid uncommitted successor.
Unknown staging entries are not reclaimed by this reconciliation. Owner/user approval
provenance remains a separate note, not invented product-failure evidence.

The inode-reuse correction holds a private read-only payload descriptor from begin
through cleanup success or tx_close. This protects active transaction lifetime only;
it does not establish protection against arbitrary replacement after process death,
tx_close or reboot. No hostile same-UID defense, legacy adoption, product wiring,
power-loss durability, formal acceptance promotion or 95/108 score change is claimed.

## Authentication and controls
Only the fixed two original ZIPs are downloaded in Actions and retained byte-for-byte,
checked against API ID/name/source/attempt/size/digest and hashed again after saving.
No archive members are extracted or executed. Path traversal, aliases, duplicate
casefold names, encryption, links/special files and member/total/count excess are refused.
Installed-package and hook-variant nm/link records are checked separately.
Fixed original source bytes are fetched as text and hashed, never imported/executed.

Each real authenticated package is a positive control. Eight negative variants per
platform mutate case membership/result/PASS marker/hook phase/recovery state/euid/core
binding/binary bytes. The auditor re-encodes JSON and recomputes its inner inventory
seal before semantic verification; rejection must have the exact expected semantic
reason rather than merely failing the unchanged outer ZIP digest. Synthetic variants
never overwrite the original ZIPs. Producer source and all existing tests remain frozen.

Only this package's verifier/workflow/document are new. Any evidence expansion,
component change or new product execution requires separate owner/user authorization.
