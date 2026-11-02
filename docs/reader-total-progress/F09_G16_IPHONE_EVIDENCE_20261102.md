# One iPhone production G16 evidence chain
Base 5511a29328c214d63bfaa96e5a8d7552699f77a3. Five new diagnostic files only.
One macOS job at most 45 minutes. One normal-size collector case, no retry,
no large-size repetitions. Existing tests, assertions, product and SDK unchanged.
Reuse the successful production generator, product overlay, retained SDK and
xcodebuild invocation. New overlay adds one source only to the temporary
EXReaderHostUITests-iOS target; scheme/application EXReaderHost-iOS unchanged.

Collector uses current-app exact identifier queries, not the legacy 240-node
filtered dump. Observe library.empty then reader.epub after explicit anchors
and busy-state completion. One import tap, no fallback second tap.
Zero reader.state matches means only absence in this app's XCUI-queryable scope
at that instant; it is not proof of absence in every OS accessibility node.
A unique current empty-shelf StaticText must have the expected label/value name.

Swift emits its own session and raw fields, not self-asserted binary hashes.
Runner binds both records to one completed selected case and full log digest,
actual build settings, source/run/attempt, built and pre/post installed program
hashes. Hashes bracket the invocation; they are not a measurement of process
memory during the query. Program source embedded by the existing generator
must equal this run's immutable source SHA. SDK remains separately pinned to e9.
Any missing record, ambiguous identity, failed query/case/build or mismatched
hash stops the run. Failures and raw outputs remain in its artifact/stdout.
No automatic synthetic replay, old gate rewriting, or six-blocker removal.
acceptance_eligible=false; single endpoint evidence, not complete F09.

The same artifact retains program-identity/EXReaderHost (at most 64 MiB) and
program-identity/Info.plist (at most 1 MiB), with byte counts and SHA256.
These are copies of the built host; separately recorded installed-container
pre/post hashes establish the bracketing comparison, not the copied files alone.
No local artifact-read permission is granted by this workflow.
