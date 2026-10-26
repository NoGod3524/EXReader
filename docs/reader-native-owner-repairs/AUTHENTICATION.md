# Read-only sealed runtime authentication

This is one separately authorized lightweight inspection of runtime source
`4bdf59ade3389b9a3e454511f6a30de7d0ddc112`, producer run `40245803457`,
attempt `1`. No build, fixture generation, GUI or fourth complete round runs.
The original run remains failure, its authenticator remains failure, and
the historical `result.json` remains accepted:false.

The inspection branch is `codex/reader-native-owner-evidence-auth`. Its actual
source/run/attempt/job are recorded independently. It uses Python3.12 and
never changes `GITHUB_SHA`, run identifiers or workflow identity. It accepts
only the fixed original run/attempt/source inputs and authenticates the
original three job IDs, two successes and original strict failure. It also
authenticates the original failed authenticator ZIP/report without rewriting it.

The producer source guard is recomputed from immutable producer Git objects,
using the original path policy. Existing runtime, SDK, raw packages, tests and
business judges must match the original producer commit exactly. Only the
declared inspection entry, runtime interpreter setup and evidence docs may
differ in inspection source. No old runtime guard entry is executed as if the
current inspection were the original run.

The sealed native judges retain all business assertions. Two enumerated,
exactly reversible source-context substitutions replace current-checkout
source lookups with the explicitly inspected producer-commit proof. The
original Windows judge retains its full owner/kill/compact/bulk/Mac assertions;
only its enclosing run entry and added native-source proof use the declared
closed-producer context. Actual GitHub metadata remains unchanged. The output
distinguishes runtime authentication acceptance from original same-run success.

A successful inspection will export the exact eight-owner binary Git diff,
base/source SHA, file hashes and original ZIP identities alongside its limited
authentication result. Until that run succeeds, no additional scope is granted.
