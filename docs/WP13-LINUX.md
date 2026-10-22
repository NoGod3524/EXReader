# WP13 Linux native reference host

This independent SDK consumer uses GTK 3 controls and the installed EXReader
3.40.0 static core/library components. It changes no engine API, ABI1 or schema6.
Its source lives in `examples/linux`; it is deliberately outside the SDK's
existing top-level example inventory until integration.

## Product scope

Run the packaged `bin/exreader-linux` to open a persistent bookshelf, using its
bundled font and the XDG user data directory's `exreader` folder. Optional
`exreader-linux FONT STATE_DIRECTORY` arguments choose an explicit profile. The
directory holds `library.sqlite` and `reader.ini`; originals, progress anchors
and notes are stored through the public SQLite library API. Settings retain the
last book and font size. Closing or losing focus saves the current page's text
anchor, and a restart reopens the saved book without the original source file.

Import supports EPUB, TXT, HTML/XHTML, FB2, RTF, DOCX and MOBI snapshots, up to
8 MiB of original bytes. A fixed-cap read enforces that host limit; the engine's
existing decoded-document limits still apply. Fixed-page, audio, DRM, OPDS and
large windowed EPUB reading are outside this reference host's product scope.
No format outside the seven listed routes is silently treated as plain text.
The page cache holds at most three pages / 8 MiB; a seek is capped at 20,000
pages, and font controls stay between 12 and 48 px. Hitting a page/work limit
reports failure and retains the previously displayed page.

The page image is rendered by EXReader. A native selectable text panel exposes
the same page range, including Unicode. Select text there, enter a comment, and
choose Add note. The notes list opens the range's first page and selects its
visible portion; Delete removes the
selected note. This is a text-panel selection UI, not an image-overlay selector.

Toolbar actions also have F1–F11 keys: import, shelf, previous, next, larger,
smaller, text focus, add note, notes focus, delete note, comment focus.
GTK controls provide keyboard navigation and standard clipboard selection.
The fixed 520×640 content viewport is scrollable when the window is small;
window resize does not repaginate or alter the saved source location.

Operations execute synchronously on the GTK event loop under the declared small
snapshot scope. This package does not claim cancellation, background import or
responsive large-book parsing. Host input buffers and page payloads are bounded
separately; these limits do not substitute for an overall RSS guarantee.

## Build and acceptance

All execution takes place on GitHub-hosted Ubuntu 22.04, through
`.github/workflows/wp13-linux.yml`. The workflow builds an installed SDK with
core/library enabled and optional PDF/audio/index/image codecs disabled, compiles
this separate CMake consumer with warnings as errors, packages it with font and
license notices, and runs the actual GTK app under Xvfb and Openbox.

`tools/check_linux_host.py` supplies real X11 input using xdotool and the standard
clipboard, drives the native file chooser and lists, and verifies each observed
transition. It also checks the saved SQLite annotation independently, captures
the visible reader, and checks ink in the rendered-page region. The observation
file is optional diagnostics; it cannot invoke actions or bypass the UI.

The 20 required cases are: empty launch; initial import cancellation; Unicode
EPUB path import; mapped window/rendered page; next; previous; first-page bound;
font increase; font decrease; native text selection; selected Unicode note
storage; note navigation; close/restart without original source; minimize/restore
and resize; cancellation while reading; exact import deduplication; two-book
shelf switching with independently checked UTF-8 selection offsets; oversized
input rejection; invalid EPUB rejection; note deletion
and restart. Static source checks are not counted as successful interaction.

Artifacts contain the runnable package, dependency notices, source/file hashes,
application log, screenshot, database, settings and per-case `report.json`.
Failed attempts remain in GitHub Actions; an incomplete report cannot pass.

The cloud run ID and final status are recorded in
`docs/validation/wp13-linux.json`. No test, build, simulator, evidence download or
local evidence aggregation was run on the user's computer for this package.

The accepted source is `44e546296862e3258ad885a3706652319c266a56`: GitHub run
`39707069576`, job `119589495393`, completed successfully. All 20 real UI cases,
SDK installation, independent consumer compilation, packaging and artifact
upload passed in that one run. Earlier incomplete runs remain listed in the
evidence JSON and are not added to the accepted run's count.

## Integration handoff

The integration owner can add this host to the global host/support matrix and
decide how to publish its desktop launcher and Linux package. GTK 3, GLib,
Cairo/Pango, a graphical display server and the system's normal GTK runtime
dependencies are required. The tarball is a reference binary plus assets, not a
standalone distro package or an assertion of compatibility with every distro.
Physical desktop/Wayland accessibility and additional format fixtures remain
separate acceptance extensions. This package cannot inherit the unrelated
frozen WP16 long-test run's results.

## Review repairs and negative acceptance

The follow-up review branch `codex/wp13-linux-review` preserves the original
delivery and its evidence above. Source `af0fef29c5c61caf3607012965173db1e540330a`
passed cloud run `39713302962`, job `119609451216`: the same twenty real X11
operations plus new negative regressions. No original case was removed.

Failed note queries now preserve the current list/count and remain visible as
errors after add/delete. Opening a candidate book prepares its notes before
replacing the active document, pager or pixels. A GTK consumer using the real
public SDK and SQLite injects only note-read failures and checks thirteen
conditions, including unchanged old book/frame, retained persisted notes,
correct deletion and recovery. The test-only query substitution does not enter
the packaged application.

The UI checker rejects nonzero exit codes even when a child exited before
`close()`. Separate real already-exited children check both rejected nonzero
and accepted zero exits. Restart acceptance now leaves 26px selected and checks
that exact nondefault value. A separate deliberately faulty host ignores stored
font settings; the real UI verifier passes its first twelve operations, then
rejects that host during restart when 24px appears instead of 26px. That expected
negative report remains in the artifact and is not counted as a successful
twenty-case application run.

The accepted artifact includes `linux-host-evidence/report.json` and
`linux-review-evidence/regressions.json`. IDs, archive/report hashes, earlier
incomplete attempts and remaining scope are recorded in
`docs/validation/wp13-linux-review.json`. The dedicated workflow permits manual
dispatch on the integration branch; automatic pushes are restricted to the
review branch. The original delivery JSON remains unchanged.
