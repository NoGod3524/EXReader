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
last book and font size. Each accepted frame commits its chapter-local text
anchor on the worker before another reading operation is allowed. A restart
reopens the saved book without the original source file.

New EPUB imports use the public source-unique API, source-backed publication,
and bounded chapter pager. They do not allocate a full-book input/text snapshot
or silently retry the document API after failure. Existing snapshot records
retain their explicit compatibility route. TXT, HTML/XHTML, FB2, RTF, DOCX and
MOBI imports retain the 8 MiB original-byte host cap and SDK document limits.
EPUB follows the public source/chapter SDK budgets. Fixed-page, audio, DRM and
OPDS UI are outside this reference host's product scope.
No format outside the seven listed routes is silently treated as plain text.
The page cache holds at most three pages / 8 MiB; a seek is capped at 20,000
pages, the chapter window preference is 16 KiB with the SDK's 64 MiB workspace
budget, and font controls stay between 12 and 48 px. Hitting a page/work limit
reports failure and retains the previously displayed page.

The page image is rendered by EXReader. A native selectable text panel exposes
the same page range, including Unicode. Select text there, enter a comment, and
choose Add note. The notes list opens the range's first page and selects its
visible portion; Delete removes the
selected note. This is a text-panel selection UI, not an image-overlay selector.

Toolbar actions also have F1–F11 keys: import, shelf, previous, next, larger,
smaller, text focus, add note, notes focus, delete note, comment focus.
Escape requests cancellation of a reading task; F12 retries a failed position
save. Saving cannot be cancelled, and a failed save blocks switching and close
until the accepted pending frame is saved.
GTK controls provide keyboard navigation and standard clipboard selection.
The fixed 520×640 content viewport is scrollable when the window is small;
window resize does not repaginate or alter the saved source location.

One serial worker owns all SDK handles and executes reading/import/rendering.
GTK receives owned current-page UTF-8 text and pixels. Generation and book/part
guards reject stale work; cancellation and failure retain the accepted frame.
Forward/back navigation crosses reading-order chapter boundaries. A saved exact
in-page position survives font changes and process reopen. Non-unique progress
quotes show an explicit validated-offset fallback and retain the original saved
record; note jumps require a unique FOUND match.
The application uses native GTK controls without a WebView. Page payloads and
SDK workspace accounting have separate budgets; these are not an overall RSS
guarantee.

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

## H11 bounded EPUB adoption: initial ce5 acceptance

The sole production host is now `examples/linux/reader.c`, backed by
`reading.c`/`reading.h`; the temporary asynchronous duplicate and the old
uncompiled synchronous host have been removed. Source
`f42cfa2e23b4f43bb3417ebd0ca9272b8be45201` passed run `39869717148`, attempt 1,
job `120140792044`, against frozen SDK
`ce5d664c9f76d0613df6d79b27568a7039c4a81e`.

All original twenty GTK cases passed without removing assertions. The driver
waits for each asynchronous operation and SAVE to finish before issuing the
next scripted user action. Native chooser input waits for file-location
resolution; the main reader no longer intercepts the modal chooser's Escape.
Four regression groups passed, including 26 real GTK/backend fault assertions
and the original font-restore mutant rejected at check 13 after its twelve
positive operations. Fault checks cover note-query failures, candidate discard,
save failure/retry, blocked switching, non-cancellable SAVE and the busy state
inside the actual GTK text-publication callback. A successful save retry also
clears the previous error indicator.

`tests/linux_host/check_bounded_ui.py` passed 37 checks through the normal
packaged application and real X11 input. These include separate chapter routes,
UTF-8 clipboard and chapter-local notes, 65 long-chapter page turns, window
eviction, exact-position font changes, cross-chapter note jumps, deleted-source
process reopen, repeated resource/spine recovery, missing-chapter preservation,
input during a large-source worker operation, Escape cancellation, stale-result
rejection and a subsequent book switch. It also checks package hashes and the
frozen SDK ancestor/eight protected trees. The installed backend independently
passed 82 assertions, including an in-page byte offset of 30 through font and
library reopen.

This run observed 1,279,999 projected chapter bytes, 789,460 index bytes,
2,296,896 peak parse-workspace bytes, zero explicit snapshot bytes and six
evicted windows after 65 page turns. F2 input was handled in 18.60 ms while the
worker remained busy; Escape returned `EXR_CANCELLED`. These are observations
on this cloud runner, not an end-to-end memory or latency ceiling.

The sealed artifact contains the runnable package/build manifest, original
20-case report and screenshot, fault/mutant evidence, H11 per-check JSON and
two screenshots, application logs and profile databases, and the backend log.
Identity, digest and preserved failed attempts are recorded in
`docs/validation/r5-linux-bounded.json`. H11 covers native GTK/X11 bounded EPUB
adoption; PDF/CBZ UI, physical/Wayland accessibility, per-format legacy fixture
coverage and overall RSS/performance gates remain separate work.

## H11 final SDK candidate revalidation

Final source `6cb58962866c4f2223dfba0d21b6d36675cbfff1` adopts SDK candidate
`9c69bc4c7efb0cff68ced27562709fe597189041`, including the oversized inline-unit
preparation fix and its corrected lazy-load budget regression. The H11 guard
requires that exact candidate as an ancestor and compares all eight protected
trees. No host implementation, fixture, assertion, window preference or
workspace budget was changed for this revalidation.

Run `39872057413`, attempt 2, job `120150277110` passed every step: original
20 cases, all four regression groups including 26 GTK/backend fault assertions,
37 H11 checks and 82 backend assertions. Long-chapter measurements remain
1,279,999 projection bytes, 789,460 index bytes, 2,296,896 peak parse-workspace
bytes, zero explicit snapshot bytes, 65 page turns and six window evictions.
Real input during worker activity was handled in 16.74 ms. Original process
5877 reopened as 6031, and cancellation returned `EXR_CANCELLED`.

Attempt 1 timed out mapping the first GTK window before any acceptance case.
The entire sole job was rerun at the same source. Its failure log and artifact
`12466573199` remain alongside successful attempt-2 artifact `12466748302`;
the accepted artifact is selected by the completed upload log's exact ID and
digest. Earlier ce5 and 2f source successes remain historical records, and no
checks were borrowed from them. Exact identities and hashes are in
`docs/validation/r5-linux-bounded.json`. SDK-wide freeze and the final common
source integration run remain the integration owner's gates.
