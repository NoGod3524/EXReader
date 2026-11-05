# C1 backend receipt (2026-10-29)

Verified from inside the session, not guessed:

- Model: `claude-sonnet-5-5` (session `configured_model`, `session_context.model` and
  `external_metadata.last_served_model` all report it). Effort: `medium`
  (`session_context.effort_level`).
- Session: `session_01YAwfwo2WUHPq4dKD1re5KQ`.
- The CLI launched the session checkout at `b61cd85fb19c9347b020d9b66b53a7d474c57f5d`
  (wrong baseline). Before any implementation I fetched
  `origin/claude/handoff-c1-android-sync-20261029` and switched to it.
- Local HEAD = `origin/claude/handoff-c1-android-sync-20261029` =
  `bd28d4946f17a184dd3cd47a584cf49fce34e973` (full SHA verified equal).
- Only remote write target: `claude/handoff-c1-android-sync-20261029`. No PR, no other
  branch, no tag/release. The auto-created session branch
  `claude/c1-android-installed-sync-npmu3n` is not written.
- All build/test/fixture work is Actions-only; none was run in the cloud workspace.
