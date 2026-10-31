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
Not yet executed. No pass is claimed.
Successful bounded retry does not imply complete cleanup: persistent permissions/EIO and crash windows remain.
product_cleanup_passed stays false; crash recovery is not validated. No durable receipt was added.
A durable recovery design would require a separately authorized ownership/identity/active-transfer protocol
established before permissions become unavailable; a later receipt alone cannot guarantee deletion.
