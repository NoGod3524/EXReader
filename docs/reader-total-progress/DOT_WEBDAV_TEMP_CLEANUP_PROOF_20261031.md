# WebDAV post-publication temporary cleanup proof

Base: a9a22319825d97b9d94b4d2f11e7ca0a5635a673.
Branch: codex/dot-webdav-temp-cleanup-proof-20261031.
Five new test/workflow/document paths only. Product source and public interface
remain byte-for-byte unchanged. Linux-only Actions job, 30 minutes; one initial
run and at most one targeted correction are authorized. No local execution.

## Contract and observation

extras/webdav/src/webdav.cpp:243-247 links the completed temporary to the selected
target without replacement, ignores the following unlinkat result, then clears
the temporary name. The destructor at 212 no longer retries once the name is
empty. The download path at 720 therefore returns OK and published=1.
The public header 51-58 preserves successful publication even after later
cancellation. Callers treat non-OK as unpublished failure, so this proof must not
invent IO/published=0 after a committed link.

The installed unmodified static library is linked into a test-only executable
with GNU linkat/unlinkat wrappers. A fault is armed only after real linkat succeeds
between the exact private directory identity and a validated random temporary
basename, to the exact book.epub leaf. Both device/inode identities are checked.
One case returns EIO once for that unlink only. Another really removes directory
write permission after linking; the non-root process calls real unlinkat and
observes EACCES. The directory stays non-writable through the library call and
temporary destructor; only the fixture then restores 0700. An unrelated unlink
must still work. Both target and leftover hardlink hashes and inode identity are
checked before explicit residue removal; the published target is never deleted.

Normal success and existing-target no-replace controls accompany the two faults.
The untouched 77-case native TLS suite runs separately, preserving cancellation,
short reads, full-payload hash verification and other original assertions.
No caller import/sync failure suite is claimed to have run merely by preserving
its source. No actual credentials or user data are used. TLS private keys are
ephemeral Actions fixture infrastructure and excluded from uploaded artifacts.

A green proof means proof_completed=true and cleanup_failure_reproduced=true;
product_cleanup_passed remains false. It does not mean product cleanup was fixed,
nor does it authorize publication semantics changes. No SDK/C01/Claude/C02 files
are changed. Status: pending first Actions observation.

## Initial Actions result: defect reproduced, product not fixed

Run https://github.com/NoGod3524/EXReader/actions/runs/41159220235,
attempt 1, source 73229da841bdb1fec7be830ab4af8deba6109e75, job 124412788541,
completed SUCCESS. The unchanged TLS suite reports 77 accepted checks.
Four new raw case receipts establish:
- Normal: OK/published=1, one real link and one unlink, no residue, target nlink=1.
- EIO once: OK/published=1, errno=5, one injected failure and only one target
  unlink attempt even after destructor; a temporary hardlink remains.
- Persistent permission failure: uid=1001, actual directory mode=0500,
  no synthetic EACCES injection, real unlink errno=13; OK/published=1 and
  one temporary hardlink remains after destructor.
- Existing target: EXISTS (11), published=0, bytes=0, no committed link or
  residual temporary, original target content unchanged.

Both fault cases have identical target/temporary device+inode and nlink=2.
All three newly published targets are 1048609 bytes, SHA256
8fe1c8c0f8b33638905f8cf884bbc5718f091345cbcf413c5406092cdb41c4f5.
The fixture restores directory mode 0700, verifies unrelated unlink succeeds,
records the defect, and only then removes the residual temporary name. This
explicit fixture cleanup is not product cleanup and never deletes the target.
The evidence reports proof_completed=true, cleanup_failure_reproduced=true,
publication_contract_preserved=true, product_cleanup_passed=false.

Source/installed binding:
- extras/webdav/src/webdav.cpp SHA256
  b38acf80184cea14e98acab908685aa3282b602a15e792193141f3d7c68bda5e.
- Public header SHA256
  efef0f4a1d04f6c3e790da339065f45c33e4aecbaf5e4d3c3ac4025f00e72971.
- Built and installed archive SHA256
  90045e216a0a11147f778b4ac138eb41ce618308e9da41903fc61da236ee2469.
Artifact 13025898592, 143785 bytes, SHA256
beffd770e8ba6a60c07447e6f6dba8e92bd2c53ce58e959184c02a4beb8449ee.
Only logs and artifact metadata were read outside Actions; no local ZIP parsing.

The initial round establishes the requested reproduction; no corrective rerun
is needed or consumed. This documentation-only receipt uses [skip ci].
Any product cleanup fix or recovery policy remains a separate owner decision
and must preserve successful publication semantics rather than returning a
misleading unpublished failure.
