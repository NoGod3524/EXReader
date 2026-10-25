# D01 — real-process SDK reading-record migration verification

## Scope and immutable inputs

This is an installable **verification probe**, not a replacement SDK, parser,
host, product schema, migration writer or sync backend. All execution, fixtures,
builds and artifact operations are restricted to GitHub Actions.

- Host start: `a826a65c9c66e43620eff61b49cb79f941a3c953`.
- Only permitted ordinary merge: `f680aeaddfb1ecc67ead353554f5b91a5703f72f`.
- Post-merge base: `d170d43038ebcc22a9e6e0bea9bf463a5ebec98e`, tree
  `4d535b85026c3ed08e9fbdae81a0de191f0c8fc4`. Both original parents retained.
- SDK 3.40.0: `9854061be331fe603a1822d9b2b36ee357154927`.
- SDK 3.41.0: `edddc463c06ed5731195cdb8f06b2df6dff7699e`.

The two SDKs are archived independently, built and installed into disjoint
prefixes. Unmodified product/revision/reading-state/G03/navigation modules are
installed against each version. Fresh C and C++ consumers use installed public
headers and targets only. The original G03 consumer and its complete assertions
also run unchanged against each installed SDK; their results are not substituted
for migration results.

## Contract and invocation

`migration-probe produce WORK ORIGINALS FONT REPORT role=sha256...` imports
Actions-generated TXT, global/bounded EPUB, PDF and CBZ through public SDK APIs.
G03 creates real progress, bookmarks, range highlights, note edits, deletes and
restores. A real public range capture also produces retained anchor-v1 wire.
Public revision APIs create concurrent heads and a retained final tombstone.
SDK notes and progress are seeded through public APIs. All handles close and the
process exits before any consuming process starts.

`migration-probe consume WORK ORIGINALS FONT REPORT role=sha256...` reopens those
same SDK/product database files; it neither imports substitute books nor writes
records. Every retained revision is read, decoded and resolved through the public
APIs. Reports retain exact wire bytes/hash, genuine producer and consumer parser
tags, match state, actual located text, offsets, quote context, part and page IDs.
Originals, library files, history/outbox files and retained wires are hashed before
and after; public snapshots independently compare book bytes, notes and progress.
SDK-local book IDs are local reopen references, never cross-version book identity.

The fixed `contract.py` names all **56 retained records**, all four process
directions (two same-version controls and both cross-version directions), and
mandatory negatives. Wrong original/content, missing spine, malformed Unicode or
wire, unknown anchor version, ambiguity, legacy selectors, conflict and tombstone
are never automatically navigated or rewritten. No percentage or title fallback.

Every call runs serially on the opening owner thread, without callback reentry.
SDK sources are transferred only to public owners, readers close before library
close, outputs use their documented free functions, and process boundaries ensure
old handles cannot survive. Failures remain in logs/artifacts; there is no recovery
write. Input sizes are bounded by the fixed generated fixtures and existing public
wire/graph limits. Existing G03 negatives retain wrong-owner, retry and failed
commit coverage; no host UI, device or in-flight crash recovery is newly claimed.

## What acceptance means

The public reading-state resolver does **not** itself check `parser_version`.
Consequently decode/FOUND can establish raw selector compatibility but cannot
grant host identity acceptance. The public navigation contract requires the
verified original format/hash **and parser tag**. A real navigation snapshot from
the retained source identity is resolved with the actual live SDK tag, without
spoofing either tag. Cross-version mismatch is recorded separately from raw anchor
resolution and produces no navigation target.

`verification_accepted` may become true when the matrix and its authentication
pass. `migration_accepted` remains **false** under this strict source-identity
contract. This does not establish cross-device synchronization or full-product
acceptance. A minimal future public-interface solution is an explicitly versioned,
root-owned compatibility policy for parser identity, backed by exact-original and
public recapture/route verification. It must not silently alter stored wire or
label a 3.41 process as 3.40. D01 does not implement that policy.

## Evidence

The same-run verifier requires completed/successful upstream jobs on this exact
source/run/attempt, unique artifact names and IDs, unexpired nonempty ZIPs with
API size/digest equal to recomputed bytes, unique members and JSON keys, exact
named cases, original G03 report binding, frozen module trees, and hashes of the
actual installed programs/libraries. Executable negative verifier cases reject
forged source/run/attempt, nonterminal/failed jobs, artifact mismatch, missing or
duplicate records, tampered binaries, and false migration acceptance.

Current execution status and retained failures are in
`docs/validation/reader-sdk-record-migration.json`. Final evidence is committed
separately with `[skip ci]`; that documentation-only HEAD is not the tested SHA.
