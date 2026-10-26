# Apple feature integration

`include/reader_apple_features.h` is the optional Apple host C bridge to the installed annotation import/export, font library, original export, jump history, and sync status packages. `examples/apple/product/ReaderProduct.h` includes it only with `EXR_APPLE_WAVE3`; the raw selector capability must also be enabled. The existing product SQLite module remains the only SQLite provider.

`examples/apple/HostWave3.swift` owns native calls and copied UI snapshots. The host owner queue serializes SDK access; font package handles and their leases run on a dedicated OS thread, and a borrowed `HostFont` retains its lease until every renderer using it has gone away. Preview is read-only and confirmation revalidates the complete file fingerprint. A NULL selector remains preserved and cannot navigate; receipt graph counts appear only after receive. Jump cursor completion follows an accepted public FOUND renderer candidate. Sync capture never starts or retries network work.

`HostWave3Review.swift` is compiled only for the review application. It creates portable NULL/concurrent-head fixtures through public SQLite backup, raw reading-state encoding, revision receive, and annotation export into an independent private product snapshot. It also creates an idle native sync session without starting a sweep. These helpers are exercised only by GitHub Actions.
