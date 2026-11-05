# Apple SDK 3.42 full host candidate launch

This documentation-only commit promotes prepared tree 81a67f7dc2c423306b10addf44b63e66dfb26316 to the explicit codex/apple-sdk342-full-handoff-20261029 validation branch. Every production, module, driver, original testcase and workflow blob is unchanged from that prepared source.

The Actions run must build both actual SDK3.42 installations from its own exact source and reuse only its own same-run/attempt artifacts for all Apple native gates. Its public-boundary modules remain exactly from e6b899284744b95dc832db92ed16324711ff5362. The separate 6be10b3de1e7f9e98bab72db586a66e571199034 driver-correction run remains in progress and is not rerun or substituted for this candidate.

The launch itself grants no acceptance. Native tests, strict failure/cancel/retry observations, original saved-byte checks and package/source/hash receipts must finish before any scoped result is accepted. Final six-platform delivery and catalog acceptance remain separate.
