# Claude H01 — domain gate (candidate evidence, no score)

Input: `6db7c3dc1005c7fd22f91b02a150bfdd671f723c` on `codex/p0-win-restart-reader-20261030`.
Branch: `codex/claude-h01-domain-gate-20261030`. Additive only; no SDK, frozen C01,
production owner, older test or mainline change.

## What it gates

The restart reader requires the caller to supply an independently trusted mapping
from the C01 admission domain to `lease_identity`. This gate validates that
supplied binding before it is handed to `lm_rr_open`:

- exact key set `domain, lease_identity, expected_generation, run_id, run_attempt, provider_sha, gates`;
- `lease_identity` is 48 lowercase hex characters;
- `expected_generation` is an integer in `[0, 2^64-1]` (no bool, no string);
- `run_id`, `run_attempt` positive integers; `gates` a non-empty list of unique strings;
- `provider_sha` is exactly the frozen C01 `ccd7fec67eb8aa463b09533ce320820f2da472d9`;
- a separately supplied registry (`{"domains": {domain: lease_identity}}`) must be
  well-formed, have no two domains sharing one identity, contain the binding's
  domain, and map it to exactly the binding's `lease_identity`.

`BINDING_VALID` is never admission: output always carries `admission_granted:false`.
It does not open a lease, touch PENDING, or prove the on-disk lease header matches.

## Invocation (for H05)

```
python -I extras/migration/claude_h01_domain_gate/gate.py --binding B.json --registry R.json
```

stdout is exactly one line: `H01-GATE {sorted-key compact JSON}` with keys
`admission_granted, gate, reason, verdict`. Exit 0 = `BINDING_VALID`, 1 = `REFUSED`,
2 = unreadable input/usage (still `REFUSED`). Reasons: `ok`, `usage`, `input-unreadable`,
`registry-{schema,empty,domain,identity-format,identity-shared}`,
`binding-{schema,keys,domain,identity-format,generation,run-id,run-attempt,provider-format,provider-mismatch,gates}`,
`domain-unknown`, `domain-identity-mismatch`.

Workflow `claude-h01-domain-gate-20261030.yml` (job `gate`) runs the 31 self-test cases
(`tests/claude_h01_domain_gate/run.py`, lines `H01-CASE <name> PASS|FAIL`, final
`H01-SUMMARY cases=N failed=M gate_sha256=...`) and uploads `claude-h01-domain-gate-evidence`.
H05 should consume that artifact or call the CLI above.

## Status

Written locally, not yet run. No verification result is claimed until an Actions run
exists; run id, attempt, job, artifact id/bytes/SHA256 are added after it completes.
Unproven even when green: the real 80-byte lease header, any `lm_rr_open` integration,
the true Actions-tuple authenticity (the gate checks shape, not provenance).
