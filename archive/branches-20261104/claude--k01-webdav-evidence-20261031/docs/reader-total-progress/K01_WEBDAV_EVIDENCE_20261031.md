# K01 — independently recomputable evidence for the WebDAV managed cleanup 30/30 (2026-10-31)

## Scope and authorization
Owner: Claude (same owner as the core and the 30-case tests). The user approved, in this conversation, every item of
the K01 package: branch `claude/k01-webdav-evidence-20261031`, commit and push from the local Git/gh route on this
device, the push-triggered workflow run, the Actions budget (Linux 30 min, macOS 30 min, verifier 10 min; one initial
run plus at most one targeted correction), and fetching this package's CI metadata and artifacts.
Base: sealed result d69bae312fd0791dac119509437fb29abc92a25c (tests 12da717cef38c90ae2097e52d33f7b3682aef043).
Core dba079b550f9ec83054e6b7b0b7475f43bc1739f is consumed read-only from a separate pinned checkout; none of its four
files is changed. The independent audit branch `codex/dot-webdav-managed-cleanup-audit-20261031` is not touched.
No build, test or artifact parsing ran locally. Formal ledger 95/108 unchanged.

Changed files (enforced by the workflow file-set guard against d69bae31):
`tests/webdav_managed_cleanup_20261031/run.py`, `tests/webdav_managed_cleanup_20261031/worker.c`,
new `tests/webdav_managed_cleanup_evidence_20261031/{SCHEMA.md,verify.py,negatives.py}`,
new `.github/workflows/claude-k01-webdav-evidence-20261031.yml`, this document.

## What changed and what did not
Observation only. The 30 case names, their count, every existing success/refusal assertion and the 30 s worker limit
are unchanged; no failure became a warning or skip. The installed consumer still links only the installed archive;
the hook worker still compiles the same pinned core source directly; the hook stays out of the archive and consumer
(same audits as the original workflow).
- run.py records every process (argv, pid, exit status, timeout, whether the runner itself sent SIGKILL, handshake
  lines, full stdout) and fixture snapshots (type, mode, dev, ino, nlink, size, sha256, raw `.receipt*` bytes) before
  recovery and after each of the two recovery passes, and writes each case record as soon as the case ends, including
  partial records on failure.
- The recovery reopen now uses `recover-step`: the same two passes in one new process, waiting for a stdin line after
  each pass so the runner can snapshot in between. The old `recover` command is kept unchanged.
- worker.c case 13 prints the canary's uid/euid/mode/return/errno and the cleanup status/native_error/pending/txdir
  mode as `EVID` lines; the CHECK conditions are the same.
- The schema, the offline verifier and its 12 negative controls are in `tests/webdav_managed_cleanup_evidence_20261031/`
  (see SCHEMA.md). The verifier runs in a separate job on downloaded artifacts and never reads producer verdicts.

## Contract alignment (no new contract)
The four v1 amendments are the ones recorded in `DOT_WEBDAV_MANAGED_CLEANUP_20261031.md` ("The user approved ... the
four contract amendments below", sealed at d69bae31) and in the header of `exr_webdav_cleanup.h` at dba079b5. Their
expected behaviour in the evidence:
1. Definite link failure returns the slot to SEALED with published=0 (cases 08, 09); only an unknown link outcome stays
   PUBLISH_INTENT (case 26/27 stay pending, never cleaned, target never deleted).
2. A residual `.receipt.next` is discarded only when `.receipt` is valid and the successor is the same root with
   generation exactly current + 1 — case 30 records those raw bytes and the verifier recomputes UUID, root inode,
   generation and CRC; any other residue is REFUSED (case 20: garbage and same-generation copy). This is the
   documented, approved behaviour, not an unexplained bug.
3. Inodes are compared across opens, device numbers only against the current root device.
4. Fixed little-endian layout with CRC-32; the CRC detects damage and is not authentication.
Limits restated: controlled namespace, cooperative processes and local filesystems only; the payload hold fd during an
active transaction prevents inode reuse in that window and does not make arbitrary replacement across restarts safe;
SIGKILL proves process-death recovery, not power-loss durability. The authorization chain for the amendments is the
user approval recorded in the sealed document; the overall acceptance owner should confirm it when consuming this.

## Status
Initial run 41173668011 / attempt 1 on tests b821ea48bea88d54fddd69ff1c58ad3effc10d19 (core dba079b5): success on
the first attempt; the targeted-correction allowance was not used. File-set, archive-export/hook-absence, header
identity and link-line audits passed on both platforms.

| Job | ID | Result | Artifact ID | Name | Bytes | Digest |
|---|---|---|---|---|---|---|
| Linux x86_64 (ubuntu-22.04), euid 1001 | 124456677607 | success | 13032546141 | k01-webdav-evidence-Linux-41173668011-1 | 121881 | sha256:57ee5985f9cecb5517f15c4b7a0223ad68062a1fb7859ea19ca3ae8dd1c28ac3 |
| macOS arm64 (macos-15), euid 501 | 124456677730 | success | 13032062590 | k01-webdav-evidence-macOS-41173668011-1 | 110595 | sha256:e63e37366b7fcf0d69c0527861331f5bc57a56fa889b0889b8421d285da1ac68 |
| Offline verifier + negatives | 124456783132 | success | 13032067656 | k01-webdav-evidence-verifier-41173668011-1 | 7841 | sha256:54dc4395693afa23c502c46ee08f513fef0c4780cdff62882408167a7679769c |

Three separate conclusions:
1. Original test result: passed — 30/30 on Linux and macOS with the fixed name set (producer summary).
2. Evidence completeness: passed — the offline verifier, reading only raw evidence, accepted both platforms
   (30/30 cases verified, 0 errors); the unmodified control was accepted and all 12 negative mutations were rejected
   for their named reason on both platforms.
3. Independent audit status: not done. This is the producer owner's verifier; acceptance by the overall acceptance
   owner's independent audit is still required before K02 may start.

Not claimed: product F10 cleanup, product wiring (K02), power-loss durability, root rotation. Formal 95/108 unchanged.

## For the next owner
Fixed inputs: tests b821ea48bea88d54fddd69ff1c58ad3effc10d19, core dba079b550f9ec83054e6b7b0b7475f43bc1739f, the three
artifacts above. Re-verify offline from a downloaded artifact (inside Actions or any isolated runner):
`python -I tests/webdav_managed_cleanup_evidence_20261031/verify.py <artifact>/wc-evidence/evidence --report v.json`
and `python -I tests/webdav_managed_cleanup_evidence_20261031/negatives.py <same dir> --report n.json`.
