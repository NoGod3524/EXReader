# WebDAV bounded temporary cleanup retry (2026-10-31)

## Scope and authorization
Base: 5dffc953109d13b7537f27de6fbaa6125eb19993.
Branch: codex/dot-webdav-temp-cleanup-retry-20261031.
Exactly six paths: one product source, new CMake/probe/runner, workflow, this document.
User approved the product change and seven cases, initial one run plus at most one targeted correction.
Original proof run 41159220235/A1 at 73229da841bdb1fec7be830ab4af8deba6109e75 stays frozen:
publication succeeded while single EIO and actual non-root EACCES each left one same-inode hardlink.

## Candidate
Only non-Android POSIX publication changes: after successful linkat, failed unlinkat returns from void publish before name.clear.
The already-existing destructor closes the file and retries the retained temporary name using the held directory fd.
download_file still returns OK/published=1 and the complete byte count. No destination removal, retry loop, sleep,
new public API, cancellation recheck, Windows/Android change or persistent recovery state.
Callers cloud_import, sync, Apple HostAccount and Windows accounts distinguish published success from failure;
Android JNI uses a separate publication branch. An IO return after commit would misrepresent the existing contract.

## Actions-only validation design
Linux and macOS jobs, 90 minutes each. Unmodified cloud-import regression is built against the frozen exact
3.40.0 SDK source 9854061be331fe603a1822d9b2b36ee357154927 in an Actions-only detached tree, not current 3.42.0.
No SDK source is changed. Both platforms run the original 77-case TLS suite without wrappers.
Linux additionally links the installed candidate archive with test-only GNU linkat/unlinkat wrappers:
- normal: one unlink, no residue;
- EIO once / EINTR once: two attempts, no residue;
- persistent EIO / real non-root EACCES: two failures, one same-inode residual hardlink;
- existing target: no replace, existing bytes preserved;
- cancellation armed only after successful real link: OK/published=1 wins, no residue.
Faults bind held directory identity, exact private temporary basename, destination and flags. Real link must succeed
first. Observation follows API return and destructor. All committed cases verify target bytes/hash and publication.
Private permissions are restored in normal and timeout paths; synthetic keys are excluded from artifacts.
Old proof and all old tests remain byte-for-byte unchanged.

## Limits and result
At initial review no execution or pass was claimed; final evidence is recorded below.
Successful bounded retry does not imply complete cleanup: persistent permissions/EIO and crash windows remain.
product_cleanup_passed stays false; crash recovery is not validated. No durable receipt was added.
A durable recovery design would require a separately authorized ownership/identity/active-transfer protocol
established before permissions become unavailable; a later receipt alone cannot guarantee deletion.

## Initial run and targeted harness correction
Run 41160684498/A1 at 62b739439578d2d4f11f1fa0638fc5b89d5e55e6 failed on both platforms.
Frozen SDK, candidate WebDAV and cloud-import packages built and installed. Existing cloud-review-probe.c:19
uses a four-parent relative include from a three-level source directory, so the compiler could not locate
apps/reader/cloud-import/src/cloud_import.c. The old 77 and seven new runtime cases were skipped, not passed.
The only correction is a workflow-local compiler include anchor build/wi-include/a/b. Its four-parent
resolution is asserted equal to the current candidate repository cloud_import.c, not the frozen SDK tree.
The original consumer source, allocator-failure macros and all assertions are unchanged. No product change
beyond the reviewed one line. This consumed the sole targeted correction run; final result follows.

## Final targeted run evidence
Run [41161210906/A1](https://github.com/NoGod3524/EXReader/actions/runs/41161210906)
at ef83932406f8160547ebc3b73751f807a8486561 completed SUCCESS.
Linux job 124418948710 ended 02:44:52Z; macOS job 124418948596 ended 02:46:56Z.
Both raw job logs report accepted=true, checks=47 for unchanged cloud-import and checks=77 for unchanged TLS.
Both log include anchors resolve to the current candidate repository adapter, not wi-frozen.
This is SDK 3.40 compatibility regression, not SDK 3.42 or six-platform acceptance.

Linux real HTTPS seven-case receipt:
| Mode | Status / published | Target unlinks | Residual names after API return |
|---|---|---:|---:|
| normal | OK / 1 | 1 | 0 |
| EIO once | OK / 1 | 2 | 0 |
| EINTR once | OK / 1 | 2 | 0 |
| persistent EIO | OK / 1 | 2 | 1 |
| persistent real EACCES | OK / 1 | 2 | 1 |
| existing | EXISTS / 0 | 0 | 0 |
| late cancellation | OK / 1 | 1 | 0 |

Each committed target has 1048609 bytes, SHA256
8fe1c8c0f8b33638905f8cf884bbc5718f091345cbcf413c5406092cdb41c4f5.
Both persistent cases retain the same inode as the target, nlink=2. EACCES is a real syscall result
(errno13, uid1001, directory0500), not simulated errno. Permission restoration and unrelated unlink controls passed.
Single EIO errno5 and EINTR errno4 each injected once; destructor's real second unlink removes the name.
Existing target SHA fed6b4d3ee2fe8ae7156922d717c886b2f2cbd57ed8b8b9703420d47eda0d9bf remains unchanged.
Fixture residue removal occurs only after the recorded residual observation, not as product cleanup.

Receipt: validation_completed=true; transient_cleanup_passed=true; publication_contract_preserved=true;
product_cleanup_passed=false; persistent_cleanup_unresolved=true; crash_recovery_validated=false.
Thus the bounded transient mitigation passes, not total cleanup or durable crash recovery.

### Identity and artifacts
Product source SHA256: 36fd471a0bfbd9a1535fc7aacd5efeadec523a65cf4cb16978c03f826b7588e1.
Unchanged public header SHA256: efef0f4a1d04f6c3e790da339065f45c33e4aecbaf5e4d3c3ac4025f00e72971.
Built and installed module archive hashes agree within each platform:
- Linux: 6e6f3864b34b01a5058fcb95859aa642c1e7208f599abeb6c1bdc2fc3af9d14d.
- macOS: 1229ce7539bb2fc048b89e07c6078a25476f0bab29b68696e9de5867b2c6ee18.
Artifacts bound by API metadata to this run/source:
- Linux 13027740149, 12586665 bytes, SHA256 367d2ead206d5d5d4f006b7f57b55c47402177990d97694375d99e3c082cc4bd.
- macOS 13027720393, 10776106 bytes, SHA256 14dccf0a6aae333b551e66b0a8226424d9f2c0e1c8f60de7311e3adc5a7bc01f.
Evidence was read from original Actions logs and artifact metadata; no local artifact/ZIP parsing.
Initial failure 41160684498 and original defect proof 41159220235 remain unchanged.
Budget: initial one plus sole targeted correction consumed (2/2); no further run authorized.

### Git approval record
The first targeted-correction push was rejected before execution (no PID), citing missing exact branch authorization.
Work stopped. User then explicitly approved ef83932406f8160547ebc3b73751f807a8486561 to
codex/dot-webdav-temp-cleanup-retry-20261031 for the sole correction run; the identical original push was retried
once and completed (PID12384, exit0). No alternate route or bypass was used.

Independent reviewer diagnose_iphone_annotation_failure read original run metadata/logs and confirmed the same result (PID21272, exit0); no ZIP parsing or additional CI.
