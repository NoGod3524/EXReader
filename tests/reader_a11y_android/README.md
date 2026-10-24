# Android accessibility audit harness

Read-only audit of the installed EXReader Android host. It adds no production code:
the audited application is built by its own owner build (`tools/build_android_host.py`),
installed unchanged, and observed from a **separate** APK through the public
accessibility tree.

| Path | Purpose |
| --- | --- |
| `harness/` | Standalone Gradle root that produces `org.exreader.host.a11y` and its androidTest APK. It deliberately does not include `examples/android`. |
| `harness/a11y/src/androidTest/java/org/exreader/a11y/A11yAuditTest.java` | The 15 audit cases: shelf, import, organize, read, annotate, back navigation, rotation, 200% font scale, 480 dpi display scaling. |
| `check_reader_a11y_android.py` | Actions-only checker: re-derives every verdict from the retained evidence, keeps `audit_completed` apart from `accessibility_accepted`, and refuses eight deliberately corrupted copies. |
| `ci/emulator-audit.sh` | Emulator-side driver: install, fixture push, read back the installed APK identity, run the audit, pull the trees, screenshots and report. |

Each case records, per capture point:

* the raw UiAutomator window hierarchy (`trees/<name>.xml`),
* the parsed node tree with name, role, state, live region, actions, bounds in dp and extras (`trees/<name>.json`),
* a screenshot (`shots/<name>.png`).

A capture on an API34 emulator proves what the semantic tree contains. It does not
prove TalkBack speech, a physical device, another API level or RTL, and the report
keeps every one of those as `unverified`.

## Local rules

Builds, execution, parsing and artefact inspection happen on GitHub Actions only.
`tests/reader_a11y_android/**` is the only writable tree besides the workflow and the
two documents named in the handoff.

## Running

``.github/workflows/reader-a11y-android.yml`` runs on pushes to
`codex/reader-a11y-android`. A `workflow_dispatch` run with `diagnostics_run`
re-reads a preserved artefact of that exact run instead of executing a new audit.
