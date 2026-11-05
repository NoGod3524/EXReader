# Apple installed OPDSHash continuation

The failed common public-module candidate remains source
`bd28d4946f17a184dd3cd47a584cf49fce34e973`, run `40937997549`.
Its installed SDK jobs reached the catalog configure step without an installed
OPDSHash prefix and failed the existing explicit dependency check.

`tools/build_apple_product.py` now builds the existing hash-only OPDS package
before the catalog, into the independent canonical prefix `<product>/opds-hash`.
All subsequent product configure steps, including the exact raw-family check,
receive that prefix through `READER_ORIGINAL_HASH_PREFIX`. The hash package uses
the same target/deployment settings as the product. The existing catalog/package
ownership checks and public module sources are unchanged.

Both legacy and raw installations retain their own hash package inside the
existing artifact roots. The existing complete installed-file inventories cover
those files, and the original SDK/core pin, checker, original tests, assertions,
and budgets remain unchanged. No new host feature or final-product gate is
claimed by this build wiring change.

Validation is the existing full same-source Apple workflow, on the isolated
`codex/apple-opdshash-resume-20261029` branch. Results must be taken from its exact
source and run; the historical failed run is preserved.
