# J03 GTK Removed books real UI paging — result: partial (base paging passed; select/restore blocked)

Baseline: GTK 7f15fe49374cd9389e2106837351d4bbd5e56113 (production files untouched; workflow guard enforces owned paths; C07 audit commit resolved to 2938e0af7632f8316808f238afe1d301d528015e). The unchanged packaged host was built in Actions and driven with real X11 input; the dialog was read through AT-SPI. This is UI evidence, distinct from C07's installed-API paging.

## Runs (budget: initial + 2 corrections = 3, all used)
- 41152615827 failed: workflow defect (env var exported only for later steps). 
- 41152725632 failed: driver defect (`accessible_text` returns a dict).
- 41155169283 (tooling commit 14bc36de) failed at scenario B; scenario A passed. Evidence artifact 13024218310 (sha256:b2999b4d...86d9), result in `result-run41155169283.json`, screenshots here.

## Passed in the real UI (scenario A, 51 seeded tombstones, ids `txt:…0001`–`…0033` hex, no restores)
- Open Removed books: 50 rows, ids equal the first 50 keys in order; Next enabled.
- Click Next page: exactly 1 row (key …0033); Next disabled; First enabled.
- Click First page: the same 50 ids in the same order.
- Tombstone set unchanged (51) after paging. Screenshots 01–03.
Setup: typed PUT+DELETE through the installed command API (no SQL mutation); not real imports, which is why scenario B existed.

## Not passed (scenario B: 2 really imported and really deleted books + 49 synthetic tombstones)
Passed: both imports deleted through the UI; 51 tombstones with the real books first and last by key; page 1 = 50 rows, page 2 = exactly the last real book id. Then, after Home+Return on the page-2 row, no `Book details` window appeared within 35 s; the final screenshot (`b-failure-desktop.png`) shows the host in the reading view of book B. So row activation did not reach the restore dialog as the driver assumed. Why is not established (a driver focus/activation mistake or product behaviour); I did not guess. Not run as a consequence: restore from page 2 and page 1 by id, reopening counts, synthetic-row refusal, selection-state observations after paging.

## Conclusion
Base 50→1→First by real UI with id verification: passed. Selection/tombstone/restore by id: **not established**. No product defect is claimed. Next step needs a new budget approval: diagnose row activation (dump AT-SPI tree and window list after Return; try double-click on the row instead of Home+Return).
