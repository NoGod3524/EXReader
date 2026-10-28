# GTK ↔ Android organization relay

Base: `36fb8db3c088d665f87aac407f8e3739fa73e0f0`.
Only this package's workflow and test drivers are changed. No SDK or production API replacement.

Execution is GitHub Actions only. Local source editing is not validation.

1. Real GTK chooser imports a TXT original. Native collection dialogs create a
   parent shelf, child shelf, tag, series, and each book membership. Application
   account UI publishes original and revisions to authenticated HTTPS.
2. Android API 34 real Activity receives and visibly traverses that organization.
   UI renames the tag, removes its membership, deletes the series, and creates
   Android-authored shelf, child shelf, tag, series and memberships. Actual app
   sync publishes the edits. No preloaded database or synthetic sync revision.
3. GTK receives these records into a fresh profile, displays native rows,
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
