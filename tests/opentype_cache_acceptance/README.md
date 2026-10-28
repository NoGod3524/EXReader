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
registered `tests/bounded_txt_scan` CTest checks against both installed SDKs.
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
