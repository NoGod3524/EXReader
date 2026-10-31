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
