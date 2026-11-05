# Windows account checks on the Wave3 host

[Actions 40642072411/1](https://github.com/NoGod3524/EXReader/actions/runs/40642072411)
tested `42445abd6dfeb312c8803d0a000a32f2a0459a15`. Its 32 account
checks passed and the account evidence was uploaded before downstream tests.
The complete workflow subsequently finished successfully; see the final result below.

The account test now waits for the truthful incomplete receive state when it
deliberately plants concurrent and missing-parent records. It requires one
conflict, one missing ancestor, one tombstone and no unresolved collection
dependency, then verifies the separate data and revision heads. A safe
tombstone is required to mark its book deleted while preserving its SDK
mapping and exact original bytes. This aligns with the separate native
organization suite's soft-delete, original readback and explicit-restore
contract, rather than calling a hidden book active. Prior failed runs,
including [40639588814/1](https://github.com/NoGod3524/EXReader/actions/runs/40639588814),
remain preserved.

[Actions 40643169696/1](https://github.com/NoGod3524/EXReader/actions/runs/40643169696)
independently authenticated the early artifact, exact run/source/attempt,
32 unique successful checks and the original report:

- Early artifact 12795934576, 4,115,157 bytes, SHA-256
  `bf48afd9828d90777b10e7efcc9411038aee7d5f689c445edfabc79cb2c09659`.
- Account report SHA-256
  `85efbc117e1622973f8b46641ae825d9661dd2e0111503ecd45af40721280670`.
- Host executable SHA-256 as recorded by the account report
  `ff06edc9f2b61c2222115a4a19d78690683b71eacc28694b51a6fd63bfc710e0`.
- Authentication artifact 12796456767, 463 bytes, SHA-256
  `bed831639efe1219bd90082b9cfac5d5f99d65beff952cf053406ac0ae59282f`.

## Same-run final result

The full workflow completed successfully on the same tested source and attempt.
The retained native organization and receive cancellation/retry step also
succeeded after the 32 account checks. Its logged checks include cancellation
of an active original read, retry without duplicate import, original hashes,
mapping recovery, and shelf, series, and tag synchronization between two
Windows hosts using a runner-local HTTPS service.

- Final artifact 12796877182, 7,671,168 bytes, SHA-256
  `9f6f2f2347b87670904b9a3ee6a3cbdffa9e89cd89fb0d86175ae4bef19b5a39`.
- [Final artifact](https://github.com/NoGod3524/EXReader/actions/runs/40642072411/artifacts/12796877182).
- The retained workflow ran against SDK 3.41. This does not establish
  acceptance of the separate SDK 3.42 composition or six-platform sync.
- The documentation-only commits are not the tested source.

