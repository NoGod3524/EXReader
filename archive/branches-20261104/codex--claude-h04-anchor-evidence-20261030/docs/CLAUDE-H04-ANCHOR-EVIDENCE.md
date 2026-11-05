# CLAUDE-H04: removed-book paging anchor evidence

Status: candidate evidence, no score change. The formal acceptance baseline stays
95/108 (87.96%). Nothing in this package was built, syntax-checked or run locally;
all execution happens in GitHub Actions only.

Base: `7f15fe49374cd9389e2106837351d4bbd5e56113`
(`codex/dot-f05-paging-evidence-20261030`). Branch:
`codex/claude-h04-anchor-evidence-20261030`.

## Question

Does `reader_catalog_removed_page(catalog, after_key, limit, ...)` treat
`after_key` as a key anchor (exclusive, order-based, independent of offsets) rather
than as a position? The base evidence only covers one 50 + 1 + 0 walk.

## Checks (`tests/claude_h04_anchor_evidence/anchor.cpp`)

Synthetic installed typed-command catalog: 51 tombstones, then two more between
sessions. Claim scope is the installed synthetic API only; not GTK, not SDK original.

1. Chained anchors (last key of each page) over limits 1, 7, 50, 100 reproduce the
   removed set exactly once: no gap, no duplicate, terminates on an empty page.
2. A present anchor is exclusive: the page is the keys strictly after it
   (anchors at index 0, 24, 49, 50).
3. Absent anchors: one sorting between two keys starts at the next greater key;
   one before all keys returns the first page; one after all keys returns empty.
4. Anchor is a key, not an offset: after tombstones are added both below the lowest
   key and above the highest (new session), the page after the old anchor
   is `[keys[50], new-greater]`, the first page holds both new keys, and an
   anchor at the new lowest key returns everything else.

Every call writes one receipt line to `calls.jsonl` (anchor, limit, return code,
rows). `manifest.json` binds file sizes and SHA-256.

## Assumption stated up front

Ordering is bytewise ascending `book_key`, as the base test's use of zero-padded
hex keys implies. Checks 3 and 4 depend on it. If the product orders otherwise,
those checks go red and the red result is kept, not adjusted.

## Not proven

- Behaviour with a very long or non-UTF-8 anchor, or `limit` values outside 1..100
  (the base package already covers the refusals).
- Restore interaction (a restored book leaving the removed set between pages).
- Any GTK or SDK-original behaviour.

## Delivery

Run ID, attempt, job, artifact ID, size and SHA256 are recorded in the delivery
message after the Actions run, not in this file. Re-check:
`git diff --stat 7f15fe49374cd9389e2106837351d4bbd5e56113..HEAD`.
