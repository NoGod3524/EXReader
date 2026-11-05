# exr-wc-evidence/1

Raw evidence written by `tests/webdav_managed_cleanup_20261031/run.py` under `OUTPUT/evidence/`.
Only synthetic fixtures in fresh `tempfile` directories inside GitHub Actions are recorded; there are no user
directories, credentials, Authorization headers or server responses in this component.

## Files
- `identity.json`: `schema`, full `core_sha`/`tests_sha`, `system`, `release`, `machine`, `python`, `uid`, `euid`,
  `compiler` (path and first `--version` line), `worker_limit_seconds` (30), `payload_sha256` and `files`:
  label -> `{path, sha256}` for `consumer`, `hookworker`, `archive` (installed `libexr_webdav_cleanup.a`),
  `installed_header`, `core_source`, `worker_source`, `runner_source`. Written before the first case.
- `cases/<name>.json`: one record per case, written as soon as that case ends (pass or fail).
- `manifest.json`: `names` in execution order, the producer's `complete` claim, and the SHA-256 of every case file.
  Written last; a missing manifest means the run did not finish.

## Case record
| Field | Meaning |
|---|---|
| `name` | fixed case name |
| `phases` | steps actually executed, in order (`case`, `prep`, `hold`, `try-open-while-held`, `kill-holder`, `try-open-after-kill`, `kill-flow`, `kill-worker`, `recover`) |
| `processes[]` | every spawned process in order |
| `snapshots[]` | `{label, entries, walk_errors}` |
| `exception` | `null`, or the runner exception text; partial evidence is kept |
| `seconds` | wall time |

Process: `kind` (`run` = subprocess.run, `worker` = Popen with handshake), `argv` (binary basename, fixture paths),
`pid`, `returncode` (Python convention: `-9` means the wait status was death by signal 9), `timed_out`,
`signal_sent` (`9` only when the runner itself sent SIGKILL to a still-running PID it spawned, else `null`),
`handshake` (marker lines the runner waited for), `stdout` (complete merged stdout/stderr).

Worker lines with meaning: `UUID <32 hex>`, `HELD <phase> <slot> <state>` (hook), `HELD <status>` (holder),
`STATUS <status>`, `OPEN <status>`, `RECOVER {status,inspected,cleaned,pending,refused,next_slot,total_slots,
receipt_uncertain,native_error,states}` (one per pass, emitted by `recover-step`, which waits for a stdin line after
each pass so the runner snapshots between the two passes of the same process), `EVID canary uid= euid= mode= rc= errno=`
and `EVID cleanup txdir_mode= status= removed= pending= receipt_uncertain= native_error=` (case 13; modes octal).

Snapshot labels: `final` (in-process and cross-process cases), `before_recovery`, `after_recovery_1`,
`after_recovery_2` (cases 13 and 22-30), `at_exception`. `entries` maps the fixture-relative path of every entry
(symlinks not followed) to `{type: file|dir|symlink|other, mode (permission bits), dev, ino, nlink, size}` plus
`sha256` for readable files, `bytes_b64` for `.receipt*` files, `link` for symlinks and `read_errno` when unreadable.

Status values: 0 OK, 1 ARGUMENT, 2 IO, 3 BUSY, 4 REFUSED, 5 LIMIT, 6 EXISTS, 7 UNCERTAIN.
States: 1 RESERVED, 2 OWNED, 3 SEALED, 4 PUBLISH_INTENT, 5 PUBLISHED, 6 CLEANED.

## Receipt (decoded by verify.py from `bytes_b64`)
4160 bytes, little-endian. Header: 0 magic `EXRWCRCT`, 8 version 1, 12 count, 16 generation (u64), 24 root inode
(u64), 32 uuid[16], 48 reserved[12] = 0, 60 CRC-32. Slot i at 64 + 64*i: 0 state, 4 reserved = 0, 8 bytes,
16 directory inode, 24 payload inode, 32 transaction id[16] (directory `tx-<hex>`), 48 reserved[16] = 0; unused slots
all zero. CRC-32 (IEEE, as `zlib.crc32`) over the whole image with bytes 60-63 zeroed. The CRC detects accidental
damage only; it is not authentication.

## Verifier
`verify.py EVIDENCE_DIR [--report FILE]` never reads `passed`, `results.json` or the producer summary. It requires the
exact fixed 30 names with no duplicates and every required field, decodes every receipt, and recomputes per case:
- kill cases 22-30: the runner sent signal 9 and the wait status is -9; the hook handshake phase/state; disk residue
  before recovery; receipt UUID = handshake UUID, root inode = root directory inode, tx dirs and payload inodes =
  receipt slots; case 30's `.receipt.next` is the same root with generation current + 1; both passes in one new
  process report the expected pending/states with no refusal or uncertainty, the first pass cleans the expected count
  and the second cleans nothing; destination dev/ino/sha256/size/mode unchanged, nlink drops 2 -> 1 only when
  cleaned; pending residue keeps its inodes and bytes; `.receipt.next` is gone.
- case 13: non-root euid, canary mode 0500 with a real errno 13, cleanup IO/native_error 13/pending 1 at txdir mode
  0500, then a new process cleans once and the second pass is a no-op with the published target identity unchanged.
- case 06: phase order, holder `HELD 0`, try-open BUSY while held, SIGKILL, then OK.
- in-process cases: exit 0 and the PASS marker (the in-worker CHECKs remain the oracle for intermediate values), all
  receipts valid and consistent with the tx dirs, plus final-state checks for 01, 08, 10, 11, 12, 14, 15 and 17.
- a manifest that claims completeness while any process timed out is rejected.

`negatives.py EVIDENCE_DIR --report FILE` copies the evidence, checks the unmodified copy is accepted, and requires 12
mutations to be rejected for the named reason: missing required field, SIGKILL replaced by a normal exit, target hash
changed, target inode changed, illegal nlink, wrong UUID, wrong generation (valid CRC), bad CRC, missing case,
duplicate case, second recovery cleaning again, and complete-with-timeout. The source directory is never modified.
