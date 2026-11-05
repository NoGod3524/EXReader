# F03 live collection selection / 2026-10-31

Base: cfdaf6a4531548be63b4dd0c2bccd6b050a93124.
Owned branch: codex/dot-f03-gtk-selection-20261031.
Exactly three additive files; no product, SDK, old test, shared branch or Claude path changes.

Actions-only Ubuntu 22.04, 80-minute job. One initial run plus at most one targeted correction authorized. No local execution.
The unchanged installed metadata suite (29 original checks) and original collections UI suite (27 checks) remain separate.
New evidence: 15 checks (five each for Shelves/Tags/Series), 153 setup API calls (51 live groups/type).
Setup uses the installed native command consumer with real revisions, not direct database writes.
The packaged actual GTK host performs selection, membership creation, rename, shelf ordinal change, cancellation and paging.
AT-SPI actual row names/selection, visible labels, editable entry text and screenshots supplement the product observation file;
read-only SQL binds names and stable keys and checks history/outbox effects.

Retained selection outside the current 50-row page is permitted. It is not called a defect merely because the current page has no selected row.
The check requires the right-pane identity and next edit to retain that exact object, and paging back to show the correct selection.
Shelf position changes from last to first; tag/series IDs retain their ordering. Cancellation must append no history.
This does not duplicate Removed pagination, original-file retry, or synchronization interoperability.
No numeric performance claims, no whole F03 promotion, formal 95/108 unchanged.
Failures retain state/tree/logs/screenshots; no assertion or timeout relaxation and no skipped negative outcomes.

## Observed first-run result
Exact tested source: 3de7d45dc21f034916d5e9aa6a89a3d3126ef806.
Run https://github.com/NoGod3524/EXReader/actions/runs/41160082299 attempt1, job124415495100 SUCCESS completed2026-10-31T02:32:08Z.
Actual Actions logs: unchanged metadata29 passed, unchanged collections UI27 passed; F03_SELECTION accepted=true/checks15/setup153/error=null. Every kind's dirty-before-cancel snapshot label is retained.
This confirms the existing live/off-page selection contract for the tested native GTK build; it did not discover a product defect.
Artifact13026418563,897668 bytes,SHA2563b2dc81542655d344ab83ffbe8deb31a10bd150591ecc0de5581bcc8bac89a78,source-bound and unexpired at read.
Independent static+terminal reviewer verified API/log/counts/metadata. Neither reviewer nor writer downloaded or parsed the original artifact ZIP outside Actions, and screenshots were not independently visually inspected in this review.
F03_accepted remains false, formal95/108 unchanged. 1of2 authorized runs consumed; targeted correction round unused. This doc-only receipt is not a new tested source or a new CI run.
