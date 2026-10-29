# Claude local C2: product performance / interaction budget (F08)

Receipt: official CLI `--bg` local job, model `claude-sonnet-5-5`, effort medium, logged-in claude.ai
subscription (no API key). Branch `claude/local-c2-product-performance-20261029`, base
`bd28d4946f17a184dd3cd47a584cf49fce34e973`. Not the earlier cloud C2; only this branch is written.

Fixed list stays 95/108; this work does not change `catalog.json` and does not score F08.

## Findings
* Existing drivers already measure the real Windows and GTK hosts (2202-original shelf, first screen,
  pagination, search, page turn, resume, import, working set / RSS) but are pinned to SDK 3.41.0.
* No numeric product budget has been ratified (`docs/READER-PRODUCT-PERFORMANCE.md`); Windows
  p95-based figures are proposals only. Therefore the gate applies no thresholds and `f08_accepted=false`.
* Not covered by any existing driver: scroll, locate/jump, font switch, frame time. Listed as not measured.
* Known earlier blocker kept: Windows original 16 MiB TXT import was `import_rejected`; not retried or hidden.

## Delivered
`tests/reader_product_performance_handoff/` and `.github/workflows/reader-product-performance-handoff.yml`
(Windows + Linux sampling at SDK 3.42.0, verified artifact identity, combined handoff report).

## Results
Pending Actions run; see the bottom section once recorded.
