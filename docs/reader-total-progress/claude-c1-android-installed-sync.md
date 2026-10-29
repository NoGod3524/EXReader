# C1 Android installed Sync/WebDAV runtime loop

Baseline `bd28d4946f17a184dd3cd47a584cf49fce34e973`; reference boundary run 40871185232
(`e6b8992…`) had `installed_android_sync_runtime=false` (only a source-included hash adapter ran).

## What this packet does
One workflow (`android-installed-sync-handoff-20261029.yml`, Actions only) on a single source SHA:

1. builds the independent installed OPDS hash owner (`EXREADER_OPDS_HASH_ONLY`) into an explicit prefix;
2. replays the unchanged SDK 3.42 Android recipe steps (as `tests/android_sdk342_package`) with that prefix,
   so `reader_sync` links `EXReaderOPDSHash::opds_sha256_stream` and the real wave3 host APK embeds it;
3. generates `HostSync342Test` + driver from the unchanged `reader_host_session_android` Sync UI suite
   (only class/runner names and the supported-version allow-list gain `3.42.0`; provenance hashes recorded);
4. installs the host APK on an API34 emulator, pulls the *installed* APK, proves byte equality with the build,
   proves the installed `libexreader_product.so` contains the new Sync hash-adapter code, then runs the original
   real-TLS-WebDAV suite in the installed app process (local-original hash, immutable upload with blocked-PUT
   cancel + retry, receive hash verification, credential/session lifecycle);
5. checks server-side that the uploaded object body SHA-256 equals its content-addressed name, was stored once,
   re-downloaded for verification, and the revision record was uploaded.

No frozen assertion or time/memory budget is relaxed; the independent adapter probe is not used as evidence.

## Status
Source written; no Actions result is asserted here. Results are recorded below after the run.
Not claimed: F01/F07/F08/F12, physical device, full product, any 108-list item.
