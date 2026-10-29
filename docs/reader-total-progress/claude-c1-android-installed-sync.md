# C1 Android installed Sync/WebDAV runtime loop

Branch `claude/local-c1-android-sync-20261029`, base `bd28d4946f17a184dd3cd47a584cf49fce34e973`.
Owner: local Claude Sonnet 5.5 (medium) background job. No 108-item count is changed here.

## Gap
Public-boundary run 40871185232 (`e6b89928`) reports `installed_android_sync_runtime=false`: its
Android runtime is a source-adapter probe, not the installed Sync/WebDAV digest path.

## What this packet runs
The workflow `claude-c1-android-installed-sync.yml` (Actions only):

1. Builds the explicit OPDS hash prefix (`extras/opds`, hash-only) and gives it to the unchanged
   `android-composition-candidate.yml` recipe, retargeted to SDK 3.42.0 exactly as
   `tests/android_sdk342_package/run.py` does. The result is the real `org.exreader.host` APK whose
   `libexreader_product.so` links `reader_sync` against the installed hash owner.
2. Builds the frozen `HostSyncTest` / `run_ui.py` unchanged except for class/runner names and one
   admission list that adds `3.42.0` (the identity assertion stays exact). Provenance hashes are in
   `build.json`.
3. On the API34 x86_64 emulator installs that APK, pulls it back and compares bytes, then runs the
   frozen suite against the TLS fixture server: seeded local original, UI-cancelled blocked upload and
   retry, receive, background close during a blocked listing, secure-credential restart, session-only
   credential. While each native request is blocked in flight a poller snapshots the live process
   (`/proc/<pid>/maps`, sha256 of every mapped `*exreader*.so`).
4. `verify.py` joins source SHA, installed APK bytes, shipped `.so` hashes, nm symbols of the product
   image (hash owner + Sync), live mapped libraries, and the recorded PUT requests (object path ==
   body SHA-256 == SHA-256 of the seeded local original; no mismatched object).

Nothing here substitutes a standalone adapter probe. Not claimed: F01/F07/F08/F12, physical device,
full product, accessibility, or any 108-item credit.
