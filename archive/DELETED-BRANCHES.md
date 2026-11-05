# Deleted branch register

This register covers all branch deletions recorded in the three completed pruning passes and the file-archive round. `deleted_at` uses UTC; earlier receipts retain only the confirmed date (2026-11-05), while this round records per-delete timestamps.

`recoverable=yes` means either the original commit is reachable from an advertised remote head/tag, or the owner-requested non-deleted file set has a published, verified file archive. File custody does not preserve commit history. `no` means neither remote reference coverage nor a certified per-branch file archive was found; local Git objects are not counted as durable remote custody.

The original SHA-only evidence deletions are rechecked against the references remaining after this round. They had 7 covered tips before this round; deleting the 297 source refs leaves 5. The other 29 are marked `no`. In addition, 57 file-level-superseded historical tips lack remaining remote coverage, for 86 total `no` rows.

The main-branch register and evidence-index update are prepared on `archive/branches-20261104`, pending owner PR #42. They have not been merged into main.
