# Windows private supervised observer engine, 2026-10-30

Status: source implementation; Actions acceptance pending. Default OFF.
This package implements an actual installed worker and supervisor, not a mock
or a replacement for frozen SDK/public ABI, POSIX recovery or legacy formats.

The supervisor pins the actual worker image with write/delete sharing denied,
hashes that held image, and opens a separate read-only/no-write/no-delete target
custody handle bound to the caller's complete volume64/FileID128 identity.
A bounded binary request binds configured source SHA, caller nonce, private
root/parent/full target IDs and worker image SHA. The worker inherits only the
request/output and reduced-read target handles, hashes the target twice and
returns the exact request plus observed bytes/hash. Parent rehashes the held
target and validates exact result size, identity and request equality.

The existing qualified adapter launches suspended, assigns a bounded kill-on-close
job before resume, and restricts inherited handles. Worker completion alone is
insufficient: active job descendants must be zero. Timeout/descendant failure
terminates the owned job and boundedly verifies quiescence; unconfirmed cleanup
is LM_WE_UNCERTAIN. Output is exclusive-created and retained on every outcome.
The caller must keep its wr_context alive throughout; no target path is accepted
from a worker response.

**LM_WE_OBSERVED is only a stable-byte observation.** It is not semantic database
validation, a COMMIT receipt, migration admission or permission to reopen.
The full migration importer/state machine, readonly SQLite logical snapshot,
crash recovery records, shared lifetime host-admission lease, cross-directory
publication integration and independent admit_reopen are still required.
No fake implementation of these gates is supplied and no lr_* stub is enabled.
Private Windows publisher and host-controller packages remain separate work.

Build via extras/migration with EXR_MIGRATION_WINDOWS_ENGINE_CANDIDATE=ON and
EXR_WINDOWS_ENGINE_SOURCE=<full current SHA>; the ordinary default is OFF.
Installed outputs: exreader-migration-windows-engine.lib,
exreader-migration-windows-observer.exe and private tool headers.
No changes to lm_main.c are necessary for this observation-only slice.

Actions builds the frozen SDK, installs the engine/worker, compiles a separate
installed consumer, checks actual image hash, full identities, exact output,
write-custody refusal, duplicate output, wrong worker hash, invalid nonce and
timeout bounds. Provider maps and raw bytes are retained, but full F07 provider
closure is not inferred from those files' mere existence. Full P0 stays false.
