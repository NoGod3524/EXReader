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
