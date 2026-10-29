# Apple font and original-save evidence audit

Independent audit [40904394809](https://github.com/NoGod3524/EXReader/actions/runs/40904394809), source `1def6623e5d0aa2d7562940de96970b893c04909`, reread the original run jobs, pinned artifact ZIP digests and native XCTest result bundles. It did not rerun the product tests or change the original conclusions.

Font: macOS, iPhone Simulator and iPad Simulator each passed `testDistinctFontInvalidRollbackLeaseAndReopen()` on source `d23fc1de44d94a80ea8cfc5aa8d74fb24d63400a`, in [40627627614](https://github.com/NoGod3524/EXReader/actions/runs/40627627614). The audit verified the original program, bundle source identity and distinct fixture font. The overall original run failed because of other jobs; that failure remains.

Original save: macOS passed `testSystemFolderSave()` on source `e0926aee809ac94ccad46ee57bda6ca52a5f5656`, in [40647623322](https://github.com/NoGod3524/EXReader/actions/runs/40647623322). The original ZIP contains equal source and saved EPUB files of 7,724 bytes; SHA-256 `0c54c6c969cb720875557d8f877d0733cc65dd1e80d74d098fb18ba65bf42bdb`. The original run did not retain the program binary, so its reported executable hash cannot be independently checked from that artifact. iPhone and iPad jobs failed and remain open.

These are independent scoped host outcomes. They do not establish physical-device behavior, SDK 3.42 coverage, or a unified-source product release.
