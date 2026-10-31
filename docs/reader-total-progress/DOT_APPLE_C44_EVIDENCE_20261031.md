# Apple c44 / independent F09 evidence-only inspection
Authorized 2026-10-31: one macOS Actions run, 20-minute job cap; three new files only. No builds, product or consumer execution, test reruns, acceptance promotion, changed budgets, or default/shared branch writes.
Base c44a9cf211fffa4ed6f2720ffa49a186c3b4d196. Apple producer run41161011007/A1: five jobs pass; iPhone original-five has 4/5 (annotation 4-minute failure), plus ps15-second observer timeout. This must not be spliced with b195's product5/5. Full19 remains blocked.
## Input pins (independent identities)
- Apple original: c44a9cf211fffa4ed6f2720ffa49a186c3b4d196/run41161011007/A1/job124419218830/artifact13028001843/181108941B/42b1ce664a7e2a37c1e66bd35876ce7e35c4ddfaf3a457a6b8f6ae55957289f9.
- Apple observation: same producer/job/artifact13027627711/14382B/ac30db434949c44a5b440915ed25b356be46f00a3aa0cccc1f2a2621883be240.
- F09 legacy: 9ab7076114a0213bd0513921b77152dd9014c9ce/run41162331946/A1/job124422399406/artifact13027487617/37960B/967c46e2e7f00286d7df8c1b26b76c400d7d81dcdc7daa2c565fca14c2b8009e.
Each API source/run/attempt/job/name/size/digest plus raw ZIP size/hash checked. Reject duplicate, traversal, symlink, encrypted, over-budget members. Extract evidence only; never execute producer binaries.
## Outputs
Apple original xcresult issues/annotation activity tree, full original log scoped segments, last real status/frame/teardown; observer redacted timeline and process sampling gaps. Producer ps exception lacks a timestamp: report that limitation, not a fabricated exact timeout moment. F09 JSON return codes printed raw/signed32/unsigned32/hex32 independently, with whitelisted native-stage tokens only, no inferred AV without exact code. No args/env/memory/unrelated system logs.
Separate receipts and preserved original errors. Failure still uploads diagnostic evidence; diagnostic success is not product success. Existing failed runs remain immutable. Formal ledger95/108 unchanged.

Review hardening: F09 raw JSON/log/text remain in memory only and are not uploaded. Persist only derived whitelisted receipts/stage tokens and API identity metadata. Small ZIP members capped at1000. Exit codes require exact integer (not bool) in signed/unsigned32 range; invalid/missing values fail rather than infer a crash.
