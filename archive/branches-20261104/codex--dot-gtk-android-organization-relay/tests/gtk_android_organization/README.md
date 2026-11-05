# GTK ↔ Android organization relay

Base: `36fb8db3c088d665f87aac407f8e3739fa73e0f0`.
Only this package's workflow and test drivers are changed. No SDK or production API replacement.

Execution is GitHub Actions only. Local source editing is not validation.

1. Real GTK chooser imports a TXT original. Native collection dialogs create a
   parent shelf, child shelf, tag, series, and each book membership. Application
   account UI publishes original and revisions to authenticated HTTPS.
2. Android API 34 real Activity explicitly receives the original, verifies its public SDK source hash, and visibly traverses that organization.
   UI renames the tag, removes its membership, deletes the series, and creates
   Android-authored shelf, child shelf, tag, series and memberships. Actual app
   sync publishes the edits. No preloaded database or synthetic sync revision.
3. GTK resumes its authenticated same-round originating native profile, receives new records through HTTPS, displays native rows,
   restores the removed membership and series through its dialogs, displays
   Android collections and publishes restoration.
4. Android receives restored state, repeats sync and force-stops/restarts the
   actual app to verify persisted visible organization and exact read-only rows.

Each phase has a distinct localhost HTTPS server, authenticated credentials and
TLS certificate. Same-run, same-attempt, same-source hash-checked Actions state
artifacts transport only server-authored bytes between phases. This is staged
service continuity, **not simultaneous online hosts**. Credentials are generated
per stage, not logged, and not included in state. The Android network fixture CA
and disposable test key travel in the private intermediate runtime artifact to
match the test-only trusted CA; they are not user/account credentials.

APK bytes installed on Android are compared with same-run build bytes; GTK
executable identity is repeated on return. Screenshots and native UI observation
outputs accompany read-only catalog snapshots; DB reads never create app state.
Original GTK account/native tests and Android C11/navigation/reading/sync tests
remain unchanged. All failure runs/artifacts are retained; a green relay alone
is not permission to claim failed retained suites passed.

Scope: GTK X11 Actions host and Android API 34 emulator, organization only. No
physical Android, TalkBack, multi-user Internet deployment, release signing,
store distribution, concurrent conflict resolution or cross-version SDK claims.

## Deletion and exact dependency contract

The retained failure run 40663675283 expected fully projected status immediately
following series deletion. That expectation was incorrect for one retained active
membership pointing to the deliberately deleted series. At the unchanged base:

- `apps/reader/revisions/src/revisions.cpp:402-405` (`project`) requires an active
  book and collection for active membership projection.
- `apps/reader/revisions/src/organization_projection.cpp:53-68` (`page`) reports a
  still-safe rejected membership as `READER_ORGANIZATION_PENDING_DEPENDENCY`.
- `apps/reader/revisions/include/reader_projection.h:86-99` documents that dependency
  changes require a later fresh projection scan and that pending is not complete.

Only this deletion phase expects exactly ONE dependency: its exact safe membership
head and exact deleted-series revision are recorded with original body hashes.
Every retained entity must have one safe complete head, every other dependency
must exist, and the outbox must be empty. GTK must visibly report exactly zero
conflicts and one dependency. After native restore, **the original strict fully
projected-success assertion remains required**, as do real membership display,
duplicate synchronization and process restart.

The GTK originating profile is actual prior native-app state, not synthesized or
pre-filled data. Each file hash is recorded before/after the byte-identical copy.
Actions ZIP mode normalization is corrected by tightening directories to 0700 and
files to 0600; account ID/root and DB bytes are untouched. The staged HTTPS service
rebinds the original loopback root so the native exact-root guard remains intact.

## Diagnostic versus acceptance

Diagnostic branch `codex/dot-gtk-android-org-diagnostic`, test SHA
`4ce6c07495d85b76f6a014baf7032aed79145500`, run 40667377711 proved the
remaining driver sequence using authenticated producer 7408 binaries. Its Android
APK was re-signed with an ephemeral test key after every non-signature entry was
verified unchanged. That run is **not same-source acceptance**. This branch's full
workflow instead rebuilds the original hosts and all retained gates at its exact
HEAD; no re-signing or prior binaries enter that acceptance.

For integration, apply only this package's test directory and full workflow to the
coordinator's candidate, then run a new same-source round. Do not substitute any
prior run for that combined candidate's evidence. See `FAILURES.md` for preserved
runs; no old run is relabelled as passed.
