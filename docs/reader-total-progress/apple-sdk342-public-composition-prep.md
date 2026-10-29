# Apple 3.42 and public-boundary source composition

Source comparison: SDK3.42 base 80da967f5411e0c76d25e8bb21ec23c5f2b22385 versus public-boundary/Android-Hash candidate e6b899284744b95dc832db92ed16324711ff5362. The branches diverged at d81e0d6f8bc944baf5d7e1b5c47eb9acde3e980c (e6 side 36 ahead, 9 behind). This preparation uses e6 as its base; it does not overwrite public modules with the older stage modules.

The SDK content trees src/include/cmake/bindings and root CMakeLists.txt are byte-identical across both candidates and match frozen 8357eafa28423a7ab93ba08b823af80f01ad1505. The public candidate's modules introduce selector-bytes API v1, retained-raw encoder API v1, installed-boundary guards and Android's independent OPDSHash. Those package files are retained exactly from e6.

All ten Apple feature/source-test modifications staged in 4a68d80fbaa524fc28f899d209d795248627080b have exact base-parent blobs shared with e6. They are applied only after verifying those parent identities; no conflicting module file is copied. HostReadingRecords.swift separately retains the explicit SDK3.42 admission of recorded SDK3.40/3.41 from 80da. The e6 tools/build_apple_host.py already admits SDK3.42 page themes and remains unchanged.

The four changed production Apple files are HostAccount.swift, HostAccountViews.swift, HostPageThemeViews.swift and HostWave3Views.swift. Public selector/retained-raw module API signatures used behind the Apple C bridge preserve reader_annotation_import_raw3_run, reader_annotation_export_raw3_run and reading-command entry points. No new private module call is added by the Apple changes. Build/installed-prefix/consumer proof and native tests must still run on the composed source.

The original 39-case wrapper and actual 3.42 SDK build driver from 6be10b3de1e7f9e98bab72db586a66e571199034 are carried. The native helper blob from 55ec49020383ef5073f47502b300ab0b5d0a7cae is included as an unaccepted candidate pending its own source results. The prepared full workflow reuses one source/run/attempt's two SDK archives across all three 39-case suites plus each host's font, real original-save, original six organization cases with tag/series members, and actual TLS account failure/cancel/retry suites. Each existing runner and its assertion/budget contract remains separate; supplemental receipts authenticate exact 3.42 app metadata and binaries. The final summary is restricted to these Apple host gates and explicitly does not grant complete-product acceptance.

This is source preparation only. The prep branch does not match the workflow trigger. The new workflow is prepared for codex/apple-sdk342-full-handoff-20261029, which is not created here. No build, syntax check, fixture or artifact parser has run locally. No catalog update, F01/F07 acceptance, default merge, PR, tag or release is established.

| Path | 80da blob | e6 public-boundary blob |
| --- | --- | --- |
| apps/reader/annotation-export/CMakeLists.txt | 18d4ab724371d429db3a5e794ccaaed05f2387fb | 73d6e4ea112ce9e1f838e8622c30242834401c2d |
| apps/reader/annotation-export/EXReaderAnnotationExportConfig.cmake.in | 52ca720a5845b03c08bfd70c988166b62eb9966a | d47c689965e22a668d81d95f6be8d4e1f9593438 |
| apps/reader/annotation-export/src/annotation_export.cpp | 8d2935ad049d158c37316aa6c65cd676063075e9 | 3034f5530102ce24cee499ad2f0984cbf650691a |
| apps/reader/annotation-import/CMakeLists.txt | b8c672afeec4ee22577387a94c4b1d98a2181f6b | a5ecc51e3b4e751f81354981d342eeb8db97b135 |
| apps/reader/annotation-import/EXReaderAnnotationImportConfig.cmake.in | df7da51b331e6beb58ee9f3227678c8ef5820795 | d3346825c374c80d4c96c007f0141ecaff78c10d |
| apps/reader/annotation-import/src/annotation_import.cpp | 05b6324e5976fcc4272efec922a4d17ce6db3940 | c78c1cd8d6d5ec376b3b9d55132bd7a0865f4cf8 |
| apps/reader/original-import/original_import.cpp | ed4cc8cd14160c745fc7d9f00ee02c6aa48a8ed4 | a6bf7f68841500c86e525c12069d10f758ecf746 |
| apps/reader/reading-commands/CMakeLists.txt | 71c7a7e09301c810766d35aa2d9c33b6294533f2 | 7db84e2366bfbcf8107c9ada73e6a05edda53808 |
| apps/reader/reading-commands/EXReaderReadingCommandsConfig.cmake.in | 238a228025024c0b7ba562845ef026739f5bff14 | ec77ae2d3b8e8256f6b56b1c134e01ae78d52d6e |
| apps/reader/reading-commands/src/reading_commands.cpp | d87389d0c6cc9e999d309c6cf1fbe740575ed1b9 | eb290fbb9de452da4833b1c57c32580ab668ee61 |
| apps/reader/reading-state/CMakeLists.txt | 71d3f9d7fb026a77cd982503ecba24aa0616858c | e7e7787f5546cc1700df2c6cfda0e708bfdc0c9c |
| apps/reader/reading-state/EXReaderReadingStateConfig.cmake.in | 6e6ccf895787b57269689aad59127dec81854f64 | e52b3fede1c51ef35a5f0eecf2095080d61c9d32 |
| apps/reader/reading-state/src/reading_state.cpp | 25de29dd59828371d7c35dc8a6295b9d74bc738d | fcd920479f83e3926c88b5ef5e16aa1ed5fc2cf7 |
| apps/reader/revisions/CMakeLists.txt | 81ef3bd433df70f071a6cdab5c32b2f405ea0a33 | c5fcbfed8ca550360605946a99d36c55f0812219 |
| apps/reader/revisions/EXReaderRevisionsConfig.cmake.in | 8da2b75bc56494802408e4478fb7a700d5558bf3 | ba6a6b7f41f39a2bce60c45323c62a54041b6c79 |
| apps/reader/store/native/CMakeLists.txt | 6654c6ad6c3176b246edc01be055b4ed8bd18528 | 81b98dfacf26ea58a30400df5e9513fee83fa24f |
| apps/reader/store/native/EXReaderProductCatalogConfig.cmake.in | 32640d417b3e491cf11b6e7f1bb48cea63715e7e | 0294f7ef242aa5a9b246ff342457803a60feacb7 |
| apps/reader/sync/CMakeLists.txt | fd056b17d4384f3c57d8338574e23f5239da3b24 | 4ae72f37391aa8fd6956ff38258c533c2694f321 |
| apps/reader/sync/EXReaderSyncConfig.cmake.in | f2a7d8bdfd9f218cecbff9f5a59ff72830ebe715 | ef441c8ecf31d3d74c5f746724c61ab6e4eaae53 |
| apps/reader/sync/src/sync.cpp | 2a63ba85375556ca92ffb92cc1c2bc08a9b8ae30 | df2cf28e41146ef870ae7ed20dae3e75cf8e4e1e |
| examples/apple/HostReadingRecords.swift | 987885aba528260f79d7302d97e28fb1633e322e | e15a269c3ae5c5804f584889976216090555bd73 |
| extras/opds/CMakeLists.txt | 54ecd3c50d54633145e4079aebe7ecb433cb22d5 | 285344341ecd4ae1b4f53ca97354c40a9ddf989b |
| extras/opds/src/opds_core.c | 9ea74ba676fbbb5be4a5350a5c7bb8ab761a5e89 | f2aeb87298da5ac2614f795e2e925731f911e66e |
| tools/build_apple_host.py | 4f8758daf24d89f6aa6165d0643d9e50ade5397e | df023420681dfe66f8e9c80cd44e4953cff3e372 |
| apps/reader/reading-state/include/reader_reading_state_retained_raw_v1.h | (absent) | 59b4062f6aea60dad7520febed5772a8632818b2 |
| apps/reader/revisions/include/reader_selector_bytes_v1.h | (absent) | 13dad75cc0587466538f9b9cc27fe08cf1bdc3ad |
| apps/reader/revisions/src/selector_bytes_v1.cpp | (absent) | f95a7d76071ee968d70ee8da28238cf5f56178cb |
| extras/opds/EXReaderOPDSHashConfig.cmake.in | (absent) | 8c4535b02c108089413399da0c30f6d5a1db34f6 |
| extras/opds/include/opds_sha256_stream.h | (absent) | 4832555073765bdbe0f52255ebbb1050a0325112 |
| extras/opds/src/opds_sha256_stream.c | (absent) | 9f6aec678b36f1fe5f99d112351134d3d79dc0d5 |
