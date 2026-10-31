# F10 annotation export POSIX privacy candidate

Base: 5963488997a7169f2ae40a8d6d33abae15eb3f36. The existing public selector boundary is retained.
Branch: codex/dot-f10-annotation-private-20261031.

The single product edit creates annotation export temporaries with mode 0600 and
atomic O_CLOEXEC, rather than mode 0666 without close-on-exec. Publication continues
to replace the explicitly selected target as documented. Windows and SDK code are
unchanged. Published POSIX files remain private; callers wanting sharing must use
their explicit sharing flow rather than ambient umask.

One authorized Actions run contains Ubuntu 22.04 and macOS 15 jobs (30 minutes each).
Both build installed packages, run the untouched original annotation export suite,
then six additive cases: umask 022/000 crossed with success/cancellation/budget.
Success and cancellation inspect both actual staged files and use fork/exec plus
device/inode checks to prove descriptors do not survive exec. A real inheritable
control descriptor proves the observer can detect leakage. Successful files are
checked as 0600 and independently parsed; cancellation/budget preserve sentinel
targets and leave no matching temporary files. Tests use synthetic fixtures only.

This does not establish Windows ACL safety, mobile device behavior, malicious
same-user directory races, durable cleanup after process death, or full F10.
No credential handling, retry policy, C02, old assertion or global SDK change.
Status: not yet tested. Actual source/run/attempt receipts are Actions evidence,
not inferred from this document.

The exec observer enumerates descriptor numbers below 65536 and requires finding
the actual staged device/inode within that range. It does not certify arbitrary
high descriptor workloads. The unchanged suite remains the full content oracle;
new cases additionally check book identity, annotation count, and replacement of
the Markdown sentinel with a book-bound document.
