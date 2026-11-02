# F09 macOS production evidence, candidate only
Base ee627f12ef41e1c2a9c7d62fcb1cd583fcdc3126; branch audit/f09-g16-macos-evidence-20261102.
Five new files only. Existing iPhone/iPad files, product, SDK, old tests and
contract are unchanged. One commit/push; one macos-15 job <=45 minutes; one
default-size collector case once. No retry.

Pinned SDK artifact 13106576006, source e9, producer 41363868404 A1,
22424085 bytes, SHA256 4f8509453079401841106161d91d9105ce7f87801be70fceb4212c86e1aca74f.
Reuse production overlay and original product/link checker, mac signing YES.
The mac UI target alone receives a new collector; source-phase signatures are
checked before and after saving without old-reference real_path resolution.

At both exact-ID query states, the test process observes the unique running
org.exreader.host through NSRunningApplication, checks PID liveness, and reads
its actual bundle/executable URLs, launch date, executable/plist hashes/source.
The runner binds these observations to the generated test target path and
built identity, checks cross-state consistency, and independently hashes files
after the case. It does not claim the app remains alive after teardown.
Unsupported configuration/path, denied identity access, nonunique process,
missing state or mismatch stops the run. No fallback or private XCUI PID API.

Two current-app XCUI queries only: current empty-shelf text (label else value,
comparison stripped) and reader.state absent at anchored reading state.
No OS-wide AX, VoiceOver, formal legacy G16 or three-platform same-diagnostic-
SHA acceptance claim. acceptance_eligible=false; legacy failures and ledger
are preserved. Contract integration and production ownership are unchanged.
