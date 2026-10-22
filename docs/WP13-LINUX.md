# WP13 Linux native reference host

This independent SDK consumer uses GTK 3 controls and the installed EXReader
3.40.0 static core/library components. It changes no engine API, ABI1 or schema6.
Its source lives in `examples/linux`; it is deliberately outside the SDK's
existing top-level example inventory until integration.

## Product scope

Run `exreader-linux FONT STATE_DIRECTORY` to open a persistent bookshelf. The
directory holds `library.sqlite` and `reader.ini`; originals, progress anchors
and notes are stored through the public SQLite library API. Settings retain the
last book and font size. Closing or losing focus saves the current page's text
anchor, and a restart reopens the saved book without the original source file.

Import supports EPUB, TXT, HTML/XHTML, FB2, RTF, DOCX and MOBI snapshots, up to
8 MiB of original bytes. A fixed-cap read enforces that host limit; the engine's
existing decoded-document limits still apply. Fixed-page, audio, DRM, OPDS and
large windowed EPUB reading are outside this reference host's product scope.
No format outside the seven listed routes is silently treated as plain text.

The page image is rendered by EXReader. A native selectable text panel exposes
the same page range, including Unicode. Select text there, enter a comment, and
choose Add note. The notes list opens and selects that range; Delete removes the
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
shelf switching; oversized input rejection; invalid EPUB rejection; note deletion
and restart. Static source checks are not counted as successful interaction.

Artifacts contain the runnable package, dependency notices, source/file hashes,
application log, screenshot, database, settings and per-case `report.json`.
Failed attempts remain in GitHub Actions; an incomplete report cannot pass.

The cloud run ID and final status are recorded in
`docs/validation/wp13-linux.json`. No test, build, simulator, evidence download or
local evidence aggregation was run on the user's computer for this package.

## Integration handoff

The integration owner can add this host to the global host/support matrix and
decide how to publish its desktop launcher and Linux package. GTK 3, GLib,
Cairo/Pango, a graphical display server and the system's normal GTK runtime
dependencies are required. The tarball is a reference binary plus assets, not a
standalone distro package or an assertion of compatibility with every distro.
Physical desktop/Wayland accessibility and additional format fixtures remain
separate acceptance extensions. This package cannot inherit the unrelated
frozen WP16 long-test run's results.
