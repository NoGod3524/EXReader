# F4 independent review and fixes

The original delivery `a85bbc5fb817ab28c28512665efc19e7c13f5ff9` should not be
merged unchanged. Its original 668 checks passed on all three platforms, but
additional actual fixtures exposed four defects. The corrected implementation
`67cee4696bcb37d072b8ffe8fdf2b926df792c8d` passed the original 668 checks plus
four new regressions on Windows, Linux and macOS, a Linux ThreadSanitizer run,
and the stricter artifact verifier. This corrected package is ready to merge.

The review branch is `codex/reader-batch-import-review`, starting from the original
documentation HEAD `e0d6f339e7c05b37014187406d2e92f2bc63814d`. The original
author's branch and delivery records remain unchanged.

## Confirmed findings

1. **Directory budget counted opened directories but ignored queued siblings.**
   Original `batch_import.c:818–819` checked `directories_seen` only while
   enqueueing; line 456 incremented it on open, and lines 491–497 opened pending
   entries without another budget check. With a root containing three leaf
   directories, `max_directories=2` produced three candidates and reported
   `complete=1, truncated=0` on all three platforms. Four directories had been
   visited under a budget of two. The fix checks the budget immediately before
   opening each pending directory; the same fixture now yields one candidate
   and `complete=0, truncated=1`.

2. **A link in a candidate's parent path bypassed leaf-only checks.**
   Original POSIX source open at line 989 used `O_NOFOLLOW` only on the final
   component. Windows lines 946–948 likewise used `FILE_FLAG_OPEN_REPARSE_POINT`
   only on the opened leaf. The fixture enumerated `root/parent/book.txt`, moved
   `parent` aside, then replaced it with a symlink/junction to an external
   directory containing another `book.txt`. All three original implementations
   committed the external replacement. POSIX now opens path components using
   anchored `openat` descriptors with `O_NOFOLLOW`, and enumeration metadata uses
   `fstatat` on the open directory. Windows verifies the opened handle's final
   path against its expected full/long path before reading, accounting for DOS
   short names and extended/UNC prefixes. The replacement is now rejected
   without committing on every platform.

3. **macOS dropped subsecond modification times during staging.**
   Original lines 1013 and 1093 set stamp nanoseconds to zero. A copy-progress
   callback overwrote a not-yet-copied 64 KiB range without changing file size,
   then changed mtime from 100 ms to 900 ms within the same fixed second. Linux
   and Windows rejected it; macOS committed the mixed copy. Enabling the Darwin
   declarations and preserving `st_mtimespec.tv_nsec` fixes that comparison.
   The exact fixture now returns an uncommitted failed item on all platforms.

4. **The temporary-name counter was shared without synchronization.**
   Original line 1109 declared a process-global static counter; line 1119 used
   `counter++`. Independent libraries each used on their own SDK owner still
   accessed this variable concurrently. Actual ThreadSanitizer execution with
   eight owners and 64 imports reported a data race in `rb_create_temp` and
   exited 66. Exclusive file creation protected against overwrite but did not
   remove that C data race. The fix uses C11 relaxed atomic increment on POSIX
   and `InterlockedIncrement` on Windows. The same instrumented installed
   adapter now finishes all 64 imports without a race report.

Line numbers above refer to the frozen original implementation. The public
header, statuses, SDK owner/callback contract, format ceilings and original 668
checks are unchanged. SDK success still sets `committed=1` before the outer loop
checks cancellation for later items; committed results are preserved.

## Reproduction before fixes

The first three review commits changed tests/workflow only; the implementation
remained byte-identical to the original:

| Source | Actions run | Observed result |
| --- | --- | --- |
| `87c0fd3cda5925fbf85670bbbaae5fe2d0a1573b` | [40067630022](https://github.com/NoGod3524/EXReader/actions/runs/40067630022) | Original 668 passed everywhere; Linux/macOS directory and parent-link defects, macOS timestamp defect, Linux TSan counter race; Windows new junction fixture setup failed |
| `3d4eaee03357adf6c12ac8660f0262d24dc9d012` | [40068018470](https://github.com/NoGod3524/EXReader/actions/runs/40068018470) | Original defects retained; Windows fixture still failed because cmd quoting misparsed the command |
| `559b8bf5b58112930313a758fead946461129429` | [40068301211](https://github.com/NoGod3524/EXReader/actions/runs/40068301211) | Windows fixture used the native PowerShell file provider; original directory/junction defects reproduced, alongside the Linux/macOS failures |

All runs are attempt 1 and remain available. The Windows fixture failures are
recorded as fixture failures, rather than product conclusions. The fixed fixture
requires a real junction and records a failure if setup is unavailable.

## Accepted source and evidence

[Run 40068645513, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40068645513)
used exact implementation source `67cee4696bcb37d072b8ffe8fdf2b926df792c8d`:

| Job | Result |
| --- | --- |
| macOS `120797111697` | Original 668 plus review 4 passed |
| Windows `120797111752` | Original 668 plus review 4 passed |
| Linux `120797111790` | Original 668 plus review 4 passed; actual installed-adapter TSan run passed |
| Artifact evidence `120797721602` | Three artifacts verified; six altered-report cases rejected |

The original gate accepted missing source/check details and truthy success
values. The reviewed gate now requires the exact source, boolean success and
every successful check, exactly 668 original checks and the four named review
cases, matching review run/attempt, and a clean Linux TSan record. Artifact ids,
sizes, expiry, declared SHA-256 and downloaded bytes are checked on Actions.

The new regressions are independent C++ consumers of installed public packages.
Each concurrent import opens, uses and closes its own real SDK library on the
same worker. TSan instruments the batch adapter and its consumer while linking
the unchanged installed SDK and sideload libraries. No SDK mocks or product SQL
implementations were introduced.

Artifacts contain the original SDK readbacks/databases, installed packages,
review consumers, raw regression output, TSan evidence and the strict record.
The full identities and SHA-256 values, including every failed run, are in
[the review validation record](validation/reader-batch-import-review.json).

No local compilation, tests, fixture execution or artifact download occurred.
The SDK protected trees, original author branch, default root build, Android
WebDAV delivery and separate Apple work were preserved.
