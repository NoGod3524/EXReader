# D26 GTK accessibility work and acceptance limits

Base: `2f215f5793a7344d22db350276ba9f8a07abe86f`.
The existing G13 production fixes were inspected and reused, not recreated.
This branch changes only the account notice/progress accessibility adapter:
explicit changed-name events, stable semantic descriptions, and no redundant
name update for unchanged text. No account/session/SDK logic is changed.

## Preserved evidence

- Baseline product, current-source full G13: `9d75dc84c998b6588b8926c6565c7dbb1c5c5f58`,
  Actions `40447118700/1`. Complete audit: 24/32 pass, eight findings.
  Its initial artifact authentication had an artifact-name mismatch; this was
  corrected in the next workflow revision, not concealed.
- Account fix and independent event/keyboard checks:
  `99fc81dfa824ee26c02f41c0a5566c02f4a935d0`, Actions `40447648026/1`.
  The account event, semantic progress description, and Escape/focus checks pass.
  Original compact 45, G13 targeted 10, search/navigation/records/batch/drop,
  raw/legacy owner recovery and real GTK HTTPS account suites ran. The full
  G13 gate and five-tool export driver failed; aggregate acceptance is false.
- Container-name experiment `a0baaee0c47a253c585430eb185bee41e26e3dc0`,
  Actions `40450545191/1`, is intentionally reverted in this revision.
  It disambiguated scrolling-container names, fixing five full-G13 findings,
  but broke the historical drop driver that explicitly locates a scroll pane
  named Bookshelf. Do not integrate that experiment independently.
  This run also recorded missing search-entry extents and an empty focus after
  import Escape. Earlier rounds passed those observations; they are unresolved
  observations, not evidence that the product is necessarily correct.

## Conflicting/failing retained contracts (not waived)

1. `tests/reader_a11y_gtk/audit_gtk_a11y.py` resolves Bookshelf by name only
   (`wait_element`, shelf and shelf-row phases), then expects a list and its
   rows. `reader.c:scroll()` historically names both the outer scroll pane and
   the list Bookshelf. In contrast,
   `tests/reader_gtk_drop_import/check_ui.py:136` explicitly requires the
   *scroll pane* named Bookshelf. Renaming the pane makes the latter time out.
2. The full G13 status check requires `event['detail1']=='accessible-name'`.
   Real GI events recorded here have numeric-zero/empty detail1 and type
   `object:property-change:accessible-name`. The unchanged targeted G13 checker
   uses that type and source identity, and passed. Original full-G13 failure
   remains recorded; this is not an assertion replacement.
3. `tests/reader_a11y_gtk/expectations.py:55-56` requires Scan library,
   Cancel scan, Retry scan. The current native product has Sync library,
   Cancel, Retry. No legacy expected name is silently rebound.
4. Full G13's reader Tab phase records only 14 steps; its current sequence
   reaches Reading records before Annotation comment. It remains an advisory
   failure, not a claim that the comment is unreachable or a passed check.
5. `tests/reader_wave3_c10/check_ui.py:309,152,97` selects an offscreen
   SELECT_FOLDER cell during Export original. `xdotool mousemove` receives
   `-2147483313 -2147483638` and exits 1. No product change is made to cater
   to that invalid coordinate; the old driver and its failure are preserved.

The strict original acceptance gates remain enabled. Final acceptance is
blocked until the historical-driver/contract corrections are explicitly
authorized and validated while retaining original failures. No screen-reader
speech or physical-device acceptance is granted: Orca and human/device testing
remain unexecuted. AT-SPI event automation is not a substitute.

All execution and evidence generation/download/parsing occurs in GitHub
Actions. `g13_current.py` only binds the current source and frozen SDK version;
it does not change checks, event interpretation, names, thresholds or fixtures.
The retained raw3 account suite uses an old Apple wire packet as an explicitly
historical protocol fixture, not as same-source Apple host validation.

Integration: review/cherry-pick the isolated account product commit
`9a87235186062f0f34f4d819e38a114516a9bc46`, plus D26-only workflow/tests as
needed. Do not pick the reverted scrolling-name experiment. Account UI file
ownership was coordinated with D23; no import/file-picker/sync implementation
was changed. The final branch must not be called fully accepted while any
original required gate remains red.
