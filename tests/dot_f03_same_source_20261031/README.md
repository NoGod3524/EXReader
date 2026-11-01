# Authorized reader suite — F03 GTK → Android, first partial round

Canonical branch: dot/reader-suite-20261101, product baseline 94fb236a4a2da87dfbaf4f1dd2a47885d615a230.
SDK freeze: 8357eafa28423a7ab93ba08b823af80f01ad1505 / 3.42.0. Exactly 11 new files; no production or original tests change.
User approved 2026-11-01 00:20:51 UTC: one run, GTK60 + Android120 + audit20 = 200 runner-minutes, no automatic rerun.
F07 alone owns workflow/scope and dispatches only after independent whole-tree review. F03 owns the nine other files.
All source remains unexecuted until that authorized dispatch. Preparation commits use [skip ci].

## Proof target and limits
Original F03 goal is organization consistency across six hosts. This round proves only the real GTK author → real Android receiver path, preserving nested shelves, tag, series, group deletion/restoration, member removal/restoration and process restart.
It cannot grant full F03, a formal count increase, or Windows/macOS/iPhone/iPad/F04/F05 credit.
The old F03 branch is sealed at 0fa23868a585c6a7698e05ea25a835f279063c8a. Its Apple two-file production delta is retained there, NOT incorporated here.

## Actual producer path
- GTK build uses the existing native installed recipe, with an explicit SDK3.42 version adapter and same-target canonical OPDSHash dependency.
- The original GTK 27-case organization suite remains. Six phases author actual revisions via native UI and authenticated HTTPS; no manufactured receiver history or SQL projection writes.
- Android calls the original tools/build_android_host.py to emit its own build/APK/native evidence. An in-memory build-product extension installs unchanged webdav/sideload/sync/session modules into the same native prefix; Gradle receives the explicit SDK3.42 and native sync options. New UI instrumentation is included through an isolated Gradle init directory, not editing old tests.
- The complete original reader-organization-android device script and every post-device gate execute, retaining native owner17, kill2, functional112, gate87, owner altered-evidence19, organization8 native+8 UI and the existing organization evidence gate.
- Each receiver phase installs the same host APK, clears only its test app profiles after the original suite has preserved its artifacts, performs native account sync, checks organization UI and a real restart, and reads the stopped app DB/WAL without writing it.

## Candidate admission versus historical ownership
The original checker has a supported candidate mode. Its existing environment is ANDROID_CANDIDATE_SDK_BASE=94fb and ANDROID_OWNERSHIP_HEAD=94fb; its candidate_only report and empty review range are preserved, not relabeled as the old owner review.
Outer admission independently checks SDK five objects against8357 and every change against the exact11-file allowlist relative to94fb. Production and old tests remain unchanged.
Every new identity states candidate_admission=true and historical_owner_guard_reexecuted=false. The historical owner reference is fixed in scope; it is background, never spliced into current results.
Wrong SDK-as-product-baseline mapping, a changed production/old-test path, or wrong source/run/attempt/program must fail admission.

## Audit and negative cases
The partial audit fetches the current run/attempt API itself, requires successful exact gtk/android jobs, downloads the exact attempt-named original artifacts and checks API digest/size plus every extracted member byte. Supplied metadata is not trusted.
It checks original suite counts/outcomes, real installed program/APK identity, immutable authenticated wire lineage, exact received revision bodies, organization projections and retained actual Android DB snapshots for all six phases.
Separate negative copies alter source, SDK, APK, restart proof, original count/failure or host role and must reject for the precise expected reason, preserving original hashes. They never become accepted producer data.
Restart is an observation rather than a new author write: prior immutable wire is retained; no fabricated PUT is required.
Raw ZIPs, failures and historical evidence are retained. A failed gate is not converted to success by partial scope.

## CLI contract
build.py --host gtk --output build/f03-gtk-build.json
build.py --host android --output build/f03-android-build.json
build.py --host android --android-retained --output build/f03-android-retained-driver.json (API34 x86_64 emulator already running)
gtk.py --mode author --phase create|delete|restore|member-remove|member-restore|restart ... emits per-phase projection.json, expected-groups.json and wire/state.json.
android.py --mode receive ... --wire ... --expectations ... --projection-expectations ... --tls-fixture build/wave3/network-fixture
verify.py --partial --evidence build/f03-evidence --output build/f03-partial-result.json

Artifact roots: gtk/ and android/ preserve their original build/ relative paths. Fixture private keys, connection passwords and tokens must never be uploaded.
