# F09 simulator environment-only observation
Base: 0f07b97837356ee225fda87e932496208d22b869.
Branch: audit/f09-simulator-environment-20261102.

One commit/push; one macos-15 job capped at five minutes; orchestration budget
240 seconds. Exactly three new files; old product, SDK, tests and evidence
collectors unchanged.

Only version/path commands once, relevant process-name observations before and
after, and one original simctl list devices available --json command capped at
60 seconds. Precondition failure stops before enumeration. No retries, warming
calls, simulator boot/erase, service restart, SDK download, project generation,
build, app installation or test.

Enumeration stdout/stderr are regular files, unlike the original stdout PIPE.
The report includes timing, child PID, poll at timeout, return code and partial
output hashes/tails. This observation-mode difference prevents a single success
from proving the original PIPE caused failure. Only the newly spawned command
process group may be killed at timeout; never a discovered system-service PID.
Process snapshots use comm, not argv/environment, and retain only relevant rows.

No service health, product correctness, VoiceOver, G16 acceptance, or original
failure root cause is inferred merely from enumeration success. Original two
60-second failures and successful iPhone run remain separate evidence.
acceptance_eligible=false. No ledger or ownership changes.
