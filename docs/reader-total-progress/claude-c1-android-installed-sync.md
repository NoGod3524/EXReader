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

## Run history (failures retained)
- Run 40948116790 / attempt 1, source `a065494878da3bf1130defe34172efbf9ca66461`: protocol passed; host build
  passed; emulator step FAILED before any test ran (`ModuleNotFoundError: run_roundtrip`: the relocated frozen
  driver resolved `sys.path` relative to its new location). The verifier then failed for missing `ui/result.json`.
  No installed-runtime claim is made from this run.
- Next source: absolute `sys.path` in the generated driver (recorded in provenance), and the verifier now checks the
  complete exact hash and Sync symbols on one single candidate that is byte-equal to the APK image or equal after
  the recorded `llvm-strip --strip-unneeded` transform; the selected candidate and mapping are recorded.
- Run 40949086554, source `96d6e3cb`: protocol FAILED (SyntaxError in `verify.py`, a literal newline in a string); the
  android job was skipped. Retained; fixed in the next source.
- Run 40949194972, source `4d200066`: protocol and host build passed; the frozen suite ran on the installed
  host and all four phases (16 checks) reported passed in the Actions log. The verifier FAILED
  `live_process_upload` and `live_process_listing` (hypothesis: native libraries are mapped from the APK,
  not from extracted `.so` files, so no `.so` path appeared). Retained, not counted as a pass.
  Process note: I downloaded this run's artifact to a local temp dir to inspect it and the read failed before
  any content was parsed; the directory was deleted. That was outside the Actions-only rule and is disclosed.
- Next source: the live-process gate accepts either an extracted-library mapping equal to the packaged hash or
  mappings of the installed `base.apk` (hash equal to the installed APK) whose file offsets fall inside the stored
  `libexreader_product.so` entry, and prints the evidence to the job log.
- Runs 40950434398 (`114e9700`) and 40951088843 (`edd56e1f`) used the intermediate APK-offset rule (any mapping).
  Their results are retained as superseded.
- Read-only Actions diagnosis of the original ZIP, run 40951208170 (source `8fffbfb5`): artifact id 12930612243
  (`claude-c1-android-installed-sync-40949194972-1`), 31129693 bytes, sha256
  `36d125d839ff77ad93240084bf2d16d900a79c3cf92e4def3293be74f03580bd` (equals the API digest), run head
  `4d20006637e3fb0e7c9a79437fa554e5d3810837`, 80 members; nothing from it was executed. Original failed gates:
  `live_process_upload`, `live_process_listing` only; all other gates (including UI16 and upload sha256) passed.
  The original snapshots hold `maps_libs: []`, `lib_sha256: {}`: the original capture only kept `.so` paths and did
  not retain raw maps, so the old failure is explained by the libraries being mapped out of `base.apk`, not
  extracted files (confirmed by the 114e run's logged maps: executable `r-xp` mappings of the host `base.apk`
  at offset 7929856 = the product entry data start; the entry is stored, page aligned). The ELF's executable
  PT_LOAD is p_offset 0, p_filesz 2947104; the logged mapping is 0x2d0000 = 2949120 bytes, i.e. the page-rounded size.
- Next source tightens the gate: an executable (`x`) mapping of the host APK (hash equal to the installed APK, not the
  test APK) must start at entry data start + page-aligned PT_LOAD offset and cover its page-rounded file size.
  The extracted-library hash chain is kept; both chains are recorded.

## Result
Run 40951458995 / attempt 1, source `7dce4bd6090cb8e1c1fa54b2329583bc55c3e138`: protocol job 123720363567 and android job
123720438740 both succeeded; `verify.py` reported `passed: true, failures: []` over all 14+ gates. Artifact 12931807958
`claude-c1-android-installed-sync-40951458995-1`, 32387963 bytes, sha256
`9f2b5786ec6e93bc37fdb7f5ca7a12dc31d55921c6d876f65b50a3c97cc98838`.

Evidence in that run: the installed `org.exreader.host` APK bytes equal the built APK; the frozen HostSync suite passed
16/16 on the real Activity at SDK 3.42.0; the seeded local original reached the TLS WebDAV fixture with object path ==
body SHA-256 == SHA-256 of the original (201, stored), after a UI-cancelled in-flight upload and a retry; no object with a
mismatched identity; the live process, while a real native upload and a real listing were blocked in flight, had an
executable (`r-xp`) mapping of the host `base.apk` at offset 7929856 (entry data start) of 0x2d0000 bytes covering the
executable PT_LOAD (p_offset 0, p_filesz 2947104). The extracted-`.so` chain was not applicable (libraries are mapped from
the APK; `chain_extracted_file=false`) and is retained as a gate alternative. The product image's complete exact hash and Sync
symbols were checked on a single candidate byte-bound to the packaged image.

Not covered: the tamper/hash-mismatch failure on a local original through the installed path (only interruption/cancel and
retry are exercised); physical device; F01/F07/F08/F12; full product; 108-item credit.
