# Windows migration host lifecycle controller — isolated slice

Base: be3f9f5610125d1ff969add1169028111b398a22.
This is an additive, default-OFF private controller, NOT an actual host integration
or filesystem recovery engine. No existing source or test changes in this slice.
No host imports windows_migration_host.cmake. No real provider is installed.
Missing or incomplete providers refuse controller creation.

The owner UI thread alone advances CLOSED / ADMITTED / RUNNING / DRAINING /
MIGRATING / REOPEN_READY / RECOVERY_REQUIRED. A request freezes command admission.
A monotonically increasing epoch rejects stale worker observations. A separate
worker is supervised through a private opaque provider; it never touches the
controller. Provider callbacks must be nonblocking and cannot reenter it.

The caller must stop all command/timer/receive paths, respect accepted-operation
commit barriers, join actual jobs and release every pending/discard/session/
candidate/module owner before reporting all host handles closed. The controller
cannot inspect those owners in this unwired slice. Product/profile ownership
must stay held throughout. A false drain report is a caller contract violation.

The provider must supply retained shared admission, exclusive conversion with no
unlocked gap, full native target/parent/root binding, actual worker containment,
and independent post-worker namespace/target/SDK validation. Cancellation or a
zero exit code is not clean abort. A COMMITTED_ACKNOWLEDGED observation also
requires independent admit_reopen before normal SDK open. Partial spawn failure
latches recovery-required and retains the lease until terminal containment.
Neither late cancellation nor observed bytes may infer commit or rollback.

The library never opens SDK/SQLite, parses a marker, deletes uncertain data,
changes ACLs, kills workers or drops a lease while the worker may be live.
No provider fixture is linked into the library.

Actions builds with MSVC /W4 /WX and runs 16 fake-provider contract groups
(assertions active in Release), including wrong-thread/reentrant calls, stale
epochs, partial acquisition/spawn, cancellation barriers, independent reopen
refusal and recovery retention. These are unit contract checks only. No claim
of actual host, installed provider, full P0, common-source or power-loss safety.

Actual host work remains gated on a real shared-lease/worker provider and explicit
seams in examples/reader.c plus windows_feature_integration.cmake. Original
startup ten cases, record 27 + refusal eight and recovery 270 retain their exact
source-specific acceptance; none is transferred here. All builds/tests run only
in Actions. No local test or syntax result is acceptance evidence.
