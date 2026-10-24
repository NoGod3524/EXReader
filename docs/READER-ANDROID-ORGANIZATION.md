# Android native organization candidate

Base `ae584ccfc4c241196bcf8e6513ae512b7ac0ca9e`, with read-only Removed paging dependency `ccd5f39f717467ca86f60093385667318c99aef5`. PR22 remains frozen. This candidate changes the Android host, its tests, workflow and source inventory; it does not change SDK, schema1 or revision wire.

The shelf's **More → Organize** entry opens a native Android list for shelves, tags and series. Long-pressing a shelf book offers **Organize book**. Shelves support children and a bounded parent picker; groups support create, edit, delete and explicit restore. Membership supports add, remove, explicit restore and order values for shelves/series. Smaller order values appear first. Removed lists all historical removed groups of the chosen kind across shelf levels, with bidirectional ID keysets. Restoring a child with a removed parent requires the user to restore its parent first.

Each main list retains one page of at most 50 rows. An open parent picker retains another bounded 50-row page. Shelf navigation retains at most eight breadcrumb records. All product work uses the existing host worker and installed native provider; JNI exposes narrow group/member/selection reads and the existing typed command producer. Production code adds no SQL connection, generic SQL path or wire encoder.

An edit loads an immutable metadata/selection snapshot between complete observed-head reads. Missing history can initialize through an explicit save; pending parents, concurrent heads and blocked restore state refuse editing. Submission retains the original full observed heads, and the native transaction refuses a stale write. UI generation tokens discard obsolete results without changing committed outcomes.

`IntentJournal` synchronously persists the complete desired command, stable revision/entity IDs and full observed heads before submission. A membership needing book history also persists its complete bootstrap command, verified original format/SHA/length and local SDK source reference. The bootstrap captures current product title, author, sort title and favorite fields. It re-verifies the public SDK retained original before submission and refuses changed legacy product fields. Native code alone generates new revision wire.

The journal retains refusal and uncertain-response state. **Saved intent → Retry exact intent** reuses the same fields, heads and IDs. A committed book bootstrap followed by refused membership is recorded separately and retained; retry never substitutes fresh heads. **Discard and review** explicitly abandons the local recovery intent while preserving committed history. Publication catches outcomes inside `HostTask.commit`, so late cancellation cannot label a committed change canceled. Closing or destroying the Activity drops its UI callback; the worker finishes publication and retains recovery state.

## Actions validation

Workflow `.github/workflows/reader-organization-android.yml` runs the unchanged owner17, two true kill/recovery probes, original112 functional cases, original87 strict gates and owner19 altered-evidence gates. It also verifies Release excludes the debug fixture, the sole installed product provider, native link/build identity and identical reinstalled application APK bytes.

Added instrumentation cases: complete Unicode intent before writes; stale refusal retaining exact request; bootstrap preserving current user fields; partial bootstrap with membership refusal; changed legacy fields refusing bootstrap; late cancellation after commit; bounded bidirectional Removed pages; explicit membership restore.

Added real UI cases: More/create/edit/nested shelves; adding two real SDK books; membership remove/restore; visible series order change; group delete/full Removed restore; forward/reverse active and Removed paging; book long-press entry; refusal followed by an actual process stop and exact saved-intent UI retry. Per-case screenshots, Gradle XML, raw instrumentation and source/run/attempt-bound phase witnesses are retained. The final recovery witness compares persisted entity/revision/payload/heads and verifies product user fields.

`tools/check_reader_organization_android.py` rejects incomplete, duplicate, skipped, failed or mismatched evidence and requires every original exit. The separate organization gate corrupts native/UI/source/process/retry/screenshot/XML/original-owner evidence and requires refusal, restoring each original before the final positive check.

Status: source implementation prepared; this document grants no acceptance before its Actions run completes.
