# Independent OpenType contextual-miss acceptance

This is a test-only package. It does not modify `src/opentype.c`, SDK headers,
existing tests, or existing resource/time budgets. All generators, consumers,
comparators, evidence hashing and artifact authentication run in GitHub Actions.

## Pinned identities

- Candidate SDK: `5b7a34ee4f1ce38cf3bcd7cf0220575f4ecf7da9`.
- Fixed control SDK: `25c2ef86c5c1c4e72b2c9d9daf8c47873c49bcab`.
- Test source: the workflow's complete `GITHUB_SHA`, recorded separately.
- Workflow: `sdk-ot-cache-acceptance.yml`, branch `codex/dot-ot-cache-acceptance`.

The candidate and control are separate exact checkouts. Each is built and
installed using its unchanged `reading-library` preset. The same independent
consumer is compiled using only the installed public SDK, not private headers
or an instrumented engine. A source-admission check permits changes only to this
new test package, its workflow and its handoff documentation.

## Evidence and scope

The Windows, Linux and macOS jobs each generate dedicated deterministic fonts,
run handwritten expected substitutions and fieldwise control/candidate
comparisons, preserve raw requests and responses, and execute all unchanged
platform-applicable `tests/bounded_txt_scan` CTest checks against both installed SDKs (seven on Windows, six on Unix).
The unregistered Noto/3,000-page performance experiment is not rerun here.

All command logs and return codes, elapsed wall times, fixture hashes, installed
file hashes, source identities and results are uploaded even after failure.
A separate job authenticates all three operating systems against the same
source, run and attempt. No result is complete merely because one matrix job
passed. Compare the final authentication result and each platform's report.

This suite verifies observable public behavior, including cancellation callback
counts. It does not expose private cache hit counters or claim a speedup from
this correctness workload. Any product failure must be handed to the SDK
coordinator with the original failing fixture and raw evidence; it is not fixed
by changing product code in this package. Dedicated generated fonts are test
assets, not a replacement for real-font or real-reader performance validation.

## Integration

Cherry-pick only this package's test/workflow commits after reviewing the tested
SDK SHA. If the coordinator changes the candidate, update both explicit pins
in the workflow and `run.py`, retain the previous evidence, and rerun all three
platforms. Do not combine passing artifacts from different sources or attempts.
No main-branch merge, pull request, tag or release is performed by this package.

## Preserved initial failure and platform admission correction

Run [40622921759, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40622921759)
used test source `c6199ffc60f1737e7164ce92e3d3d02f4c00c058`. Dedicated
OpenType comparisons passed on all three platforms. The initial aggregate was
correctly rejected because the unmodified `bounded_txt_view` test hardcodes
`C:/Windows/Fonts/arial.ttf`; both control and candidate therefore returned
`font: 3 Cannot open file` on Linux and macOS. This is not a cache regression.
The existing source, assertions and budgets remain unchanged. The final scope
requires that test on Windows only; the other six portable original checks
remain mandatory on all platforms. Unix `bounded_txt_view` is not claimed passed
or fixed. No font-path substitution, symlink or D13 experiment is performed.

The first authentication also revealed Windows backslash evidence keys being
interpreted as literal names on Linux. The new evidence writer uses POSIX
relative keys. This changes artifact serialization, not product behavior.

Preserved initial artifacts:
- Windows `12788530856`, SHA256 `d9a2ae215148da0b4c0063eeed8dff59f9c9d57d550f231e5a891ce229af03d2`.
- Linux `12787843796`, SHA256 `9dadc22933aeec0e47c2a24a8db1e2608abf01a573ab8abf7b7ae4a4c5045b24`.
- macOS `12787684758`, SHA256 `e955d75d05f454ddbb399140073adf4bcc2cae5be68d052842ca318f6aae8e6b`.
- Rejected authentication `12788880217`, SHA256 `f397db10c64db3ee9099cc690c5f4c1abc2bd611f99dd1ac118f9dd4af129157`.
