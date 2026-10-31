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
Status: first run failed in the new JSONL test parser; correction awaits its separately authorized validation. Actual source/run/attempt receipts are Actions evidence,
not inferred from this document.

The exec observer enumerates descriptor numbers below 65536 and requires finding
the actual staged device/inode within that range. It does not certify arbitrary
high descriptor workloads. The unchanged suite remains the full content oracle;
new cases additionally check book identity, annotation count, and replacement of
the Markdown sentinel with a book-bound document.

## First-run failure and narrowly authorized parser correction

Run 41152773143 attempt 1, source 2b6b94e03d41fd44e5738d9957b27bf620add865,
is retained as FAILURE on both platforms. Both original regression steps passed.
The new runner failed at line 33 with JSONDecodeError (unterminated string,
column 537): str.splitlines split legal U+2028/U+0085 inside fixture strings.
The first 022-normal probe returned success and its preceding mode/cleanup checks
completed; the remaining five cases did not run. This is not a six-case pass.

Only the new runner and this document change in the correction. The parser uses
LF bytes, requires the final LF, decodes strict UTF-8, and rejects invalid JSON
without discarding blank records. One Unicode separator positive control and four
negative controls (missing final LF, blank record, truncated JSON, invalid UTF-8)
run before the unchanged six operational cases. All content, permission, exec,
cancellation and cleanup assertions remain. The production one-line change,
Windows, SDK, original tests and workflow are unchanged.

A second explicit authorization permits one new push-triggered validation run
with the existing Ubuntu/macOS matrix and 30-minute limit per job. Its result is
pending; no local test or build is used. Full F10 promotion remains false.

## Second-run evidence and separately authorized archive diagnosis

Run 41155648866 attempt 1 at 036717d9796e40b69cb48352c797695b76e17ae7
is FAILURE overall: Linux job 124401750360 succeeds, macOS 124401750603 fails.
Both platforms' original suites pass and both raw PRIVATE-SUMMARY receipts show
all six operational cases plus parser controls passing. macOS fails afterwards
at the retained built==installed archive byte equality assertion. This does not
establish why archive bytes differ, nor permit calling the overall run green.
Linux artifact 13024203900; macOS artifact 13024099122.

A new authorization allows at most two additional diagnostic/correction runs.
The first only adds evidence to this workflow: original built and installed
archive SHA/size, raw archive headers and object payload hashes, exact tools and
version output, generated install script and verbose archive build command.
Both original archives are retained. No bytes are normalized and the existing
built==installed assertion remains the acceptance gate. No product, SDK,
old assertion, new operational case or runtime limit is changed.

CMake v4.4.4's cmInstallTargetGenerator.cxx generates post-install ranlib for
Apple static libraries. Apple cctools libtool.c documents deterministic -D and
ZERO_AR_DATE. These explain a candidate mechanism, not this run's actual
difference; diagnostics must establish the changed bytes and actual tools first.
Sources:
https://raw.githubusercontent.com/Kitware/CMake/v4.4.4/Source/cmInstallTargetGenerator.cxx
https://raw.githubusercontent.com/apple-oss-distributions/cctools/main/misc/libtool.c

Member records preserve order and offsets, including repeated names and symbol
index members. BSD inline names are decoded; GNU /NNN long-name references remain
raw name tokens, not resolved identities. No object equality is inferred from
names alone. Diagnostic tool failures/timeouts are recorded without bypassing
the final full-byte comparison.

## Observed archive difference and final bounded correction candidate

Diagnostic run 41156691844 attempt 1 at 22b73528929338b2828baf3a973828db8fcb9f16
remains FAILURE (Linux success, macOS failure). Both six-case receipts pass.
macOS built/installed archives are both 84904 bytes and differ at only offset 33:
the __.SYMDEF SORTED member header time changes 1793411154 to 1793411155.
The symbol-index payload SHA and annotation_export.cpp.o payload SHA are equal;
this fact does not turn the original full-byte comparison into a pass.
Verbose build and generated install script both show /usr/bin/ranlib calls.
The executed tool reports Apple cctools-1024.3.

The exact official cctools-1024.3 source supports ZERO_AR_DATE: libtool.c
1234-1241 reads the environment variable, 1421 avoids realtime toc_time,
4390 writes that value into the TOC archive date. This matches the observed
difference, and motivates a candidate, not a retroactive successful result.
https://github.com/apple-oss-distributions/cctools/blob/cctools-1024.3/misc/libtool.c

Only the annotation-export configure/build/install subprocesses now receive
ZERO_AR_DATE=1 via cmake -E env. Other dependencies, SDK, global environment,
production code, and all assertions remain unchanged. Diagnostic JSON retains
the ambient ZERO_AR_DATE value separately from the declared scoped subprocess
environment; an ambient null does not describe those three subprocesses.
The remaining second run in the new two-run authorization must still prove
the original entire built==installed equality; no normalization is performed.

## Final result (supersedes pending status above)

Run https://github.com/NoGod3524/EXReader/actions/runs/41157287749, attempt 1,
source 914e08622e84473206638409be9586b20766f817, completed SUCCESS.
Ubuntu job 124406764013 and macOS job 124406764273 both passed the unchanged
original regression and the new installed-consumer step. Raw logs contain each
platform's six operational cases and 1 positive / 4 negative parser controls.
Normal/cancel cases observed two staged files and two exec checks each; budget
cases observed zero staged files and are only cleanup/target-preservation checks.
Normal cases exported 23 annotations. F10_promoted remains false.

The original complete archive byte equality assertion passes on both platforms,
without normalization:
- Linux: 143562 bytes; built and installed SHA256
  ea0702fd7e8caac0bd6058dd88b11314e174b1f005e964ac52d8ce841d65d92f.
- macOS: 84904 bytes; built and installed SHA256
  d0024df02767b1a0945592386cfcb80e70dc04cb2675dc2d5dc1bc430004d9bf.
Both diagnostics report equal=true and zero differing bytes. macOS member dates
are zero; the TOC and object payload hashes match the diagnostic failure run.
The production source SHA256 on both platforms is
77638d408d301949c76b424090b23dd04f803f95f526b150301a2a4e6106b72b.

Artifact metadata (not locally extracted):
- Linux 13025547510, 775955 bytes, SHA256
  00d13ad637f39397f1727e9c39cc9a848dc5ff3f35a8774f08fecaacae40bb31.
- macOS 13025407717, 855604 bytes, SHA256
  882735d99200a2e05d46c861fd5579b09fce71a4836fbf595d6b51ab6a20beaf.

Historical runs 41152773143, 41155648866, and 41156691844 remain failures.
No old assertion was removed; no product or SDK changes followed the original
single POSIX creation-line fix. The extra authorized two-run batch is exhausted.
This result covers the bounded POSIX permissions/exec package, not full F10,
Windows/mobile behavior, crash durability, or arbitrary same-user path attacks.
This documentation-only receipt is committed with [skip ci]; it does not create
another validation run or replace the tested source SHA above.
