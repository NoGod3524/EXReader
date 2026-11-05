# Windows P0 additive fault acceptance — 2026-10-30

Status: source admission/readiness scaffolding only. No native provider is bound.
A green readiness job is NOT a product test pass. M01–M10 remain pending,
accepted=false, product_tests_executed=false, full_p0_acceptance=false.
No stub, fabricated report, or unsupported-platform refusal satisfies a positive case.

## Exclusive ownership
Only tests/migration/windows_p0_fault_acceptance_20261030/**,
tools/reader_composition/windows_p0_fault_independent_20261030.py,
.github/workflows/windows-p0-fault-20261030.yml and this document.
Base: 2743f32a4eccd5823657da19cb4f77f2411424af.
Common343 and staged9330 are not targets. All execution, fixtures and ZIP parsing
are Actions-only. VM operations are source/Git/document operations only.

## Frozen baseline
Windows67=43 preflight+24 native qualification. Migration270=Linux131+macOS131+
Windows8 refusal. Record27 is isolated codec/installed-consumer qualification.
Startup10 is cooperative startup refusal, not migration lifecycle.
Preserve original code, counts, assertions, budgets and failure history.
Windows native24 already contains real process-kill and same-directory rename
coverage; this package must not relabel it as previously absent.
The legacy/POSIX33 and new Windows49 identity protocols are distinct, not conversions.

## Required real cases
- M01: actual installed importer succeeds on supported native Unicode Windows paths;
  original hashes, independent schema/public projection, no duplicated import.
- M02: distinct retained source/destination directory handles, same supported volume,
  absent destination, no-replace publication, full48-hex identity preserved.
- M03: occupied target file/nonempty directory/reparse target refuses with both trees intact.
- M04: foreign/live existing lock refuses before SDK open; no implicit break-lock.
- M05: hard kill at observed partial copy: source intact, partial never admitted;
  restart retains uncertain evidence and refuses SDK admission until qualified.
- M06: separate pre-rename and post-rename/pre-record hard cuts; exact observed state,
  no inference of durable completion from filename or complete-looking JSON.
- M07: completed transaction/pre-host-ack interruption; qualified restart and repeated
  retry preserve exactly one logical import and immutable history.
- M08: source-entry/destination-parent replacement at handshake refuses, retains
  foreign state; no sharing widening or path fallback.
- M09: full49 identity survives publish/record/restart; matching prefix32 and
  mismatching tail16 must reject. Never truncate native FileID.
- M10: real host pause writers, migrate, reopen and repeat; actual handles/worker
  termination observed; reading state and original bytes survive.

Each case requires provider source/interface pins, actual installed library/binary
hashes, native phase/nonce/PID/wait status, typed before/after inventories
(identity/type/length/hash), target SDK-open count, exact refusal status and
independent logical projection. Kill requires observed boundary and process
termination, not a sleep. Missing boundaries remain pending, not skipped-pass.
No power-loss or directory-fsync-equivalence claim is granted.

## Provider binding
Publication belongs to scope_p0_migration_closure; engine identity/integration
belongs to audit_p0_sdk_identity_boundary. Do not execute arbitrary commands
provided through evidence. Binding must be a reviewed source change with pinned
interface and a real installed consumer. Current null bindings intentionally
prevent native test execution. F05 peer/tombstone work belongs to a separate lane.

## Evidence
admit.py checks exact HEAD/run identity, ancestor base, exclusive changed paths,
and frozen Git objects, then writes ten explicit pending cases.
The independent audit authenticates original ZIP size/hash/run/job/source,
rejects duplicate/unsafe entries and oversized members, independently recomputes
frozen objects/changed paths/contract hash, and verifies honest non-acceptance.
No mixed-source evidence may grant P0. Preserve failed/not-run/pending distinctions.
