# Windows worker ownership review

This supplement preserves the original Windows delivery and its evidence. It
changes only the Windows host and adds an independent cloud regression consumer.
Public SDK 3.40.0, core 3.39.0, ABI1/schema6 and engine resource limits remain intact.

The distributed reader uses a serialized worker for fixed annotation creation and
comment updates, with copied book/range/comment data and cooperative cancellation.
OPEN results own a candidate session until the UI accepts both its identity and
its completion state. Font changes own a candidate pager. Cancelled and superseded
page results cannot be published, including cancellation after rendering.

The visible frame now owns an independent SDK positioned layout containing only
the page's glyph/line hit data, or an owned fixed-text result and page geometry.
It continues using public SDK hit testing. Pager-cache eviction, failed distant
seeks and candidate-session cleanup cannot invalidate selection of the old frame.
The UI resets captured dragging at job start and refuses busy hit/selection work.

Offset searches propagate actual SDK failures and require the final page to
contain the requested offset. Import cancellation checks the actual SQL deletion
result; a failed cleanup reports the retained row and refreshes the real shelf.
Late import cancellation schedules serialized cleanup rather than deleting from
the UI thread. Fixed-page progress is updated in the shelf snapshot after saving.

Notes are replaced only after a successful query. A failed same-book refresh keeps
its existing list and reports the error; switching books clears an unrelated
list. Shelf/title refresh errors cannot become success messages. Progress writes
report failure and a close cannot silently discard an unsaved position. The UI
waits asynchronously for cancelled work during close, with the existing 20-second
failure guard. It never saves a candidate book through the old book's frame.

Comments exceeding 65535 UTF-8 bytes are explicitly rejected before any write;
valid Unicode at the byte boundary remains exact. This avoids truncating a scalar
or silently shortening a longer comment.

## Cloud verification

`.github/workflows/wp13-windows-worker.yml` supports push on the isolated review
branch and manual dispatch on integration refs. The normal consumer/package still
runs the unchanged original 26-check self-test and original UI phases/checker.
New results are separate in `wp13-worker-review-evidence/worker-review.json` inside
the `EXReader-WP13-Windows-WorkerReview` artifact.

An independent consumer compiles observation/fault gates only for cloud review.
The distributed executable does not include these gates. Real Win32 controls
drive eleven regression scenarios, with SQL state verified through an independent
SQLite connection. The rollback and progress failures use a real external writer
lock; query/page failures model public API failure returns without changing an
engine budget. Gates make the completion/cancellation interleavings deterministic.

The original `2d99fcd` reader is compiled with the same observation-only gates to
reverse-check the regressions. It must reject the same eleven contracts without
unexpected harness errors; the candidate must pass all eleven. No original case,
failure record, screenshot requirement, budget or tolerance is removed.

Current acceptance is pending the new cloud run. No local build/test, evidence
download or local evidence aggregation is used.
