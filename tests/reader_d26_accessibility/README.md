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

## Continued repair: separate current drivers (user requested completion)

The original historical files and failing runs above are still immutable.
D26 now carries explicit current copies and emits exact unified diffs + SHA256
manifests in Actions. Current acceptance is separate from historical outcomes:
`identity_current.py` requires every check of every current report to pass and
binds both GTK programs, all native regression reports and the separate raw3
account artifact to the exact source/run/attempt. `historical_accepted` is
reported independently and may remain false; it is never converted to true.

Mapping of corrected observations, without reducing behavior requirements:
- Current audit uses role-qualified, unique showing list/text lookup, preserving
  the exact original names and row/focus/content assertions.
- Status events use the real GI full event type AND event-source proxy identity;
  the same original status widget must emit its changed name.
- Tab must complete a genuine focus cycle with named controls inside the reader,
  including both original text/comment targets; 128 is a safety bound, not a
  smaller reachability requirement. Asynchronous focus/extents are waited for,
  never synthesized by extra activation or navigation.
- Current account labels are required and Receive books is additionally required.
- Export retains the entire old five-tool script and byte/directory assertions;
  its full target path is entered through the real focused Ctrl+L field,
  followed by Return, then Tab to the actual Export here button and Space if
  GTK navigates rather than accepts; no stale pointer coordinate is used. The output must still match the exact chosen directory and bytes.
  The attempted AT-SPI scroll_to route failed explicitly in run40457260445
  (native scroll refused: work) and is preserved, not silently swallowed.
- Original audit/tool outcomes run separately and retain their raw exit status,
  checks and error. The evidence collector validates source and report presence;
  it does not assert they passed. Strict current gates cannot pass on their behalf.

The earlier blocked assessment describes the frozen historical gates, not the
outcome of these new current-driver runs. Consult the exact final same-SHA run.

Current and retained jobs now share one hashed build handoff instead of rebuilding.
The previous 110-minute GTK job allowance is split into 30 current + 80 retained
minutes; account remains 90. Every delivered file and executable mode is verified
in Actions before the retained suite, and aggregate requires all three jobs.
Run40460915375 current G13 passed 32/32; its Export input exact-string check
timed out, and frozen navigation (active-scan sampling) / batch chooser (missing
EXReader cell) also failed. Those outcomes remain archived, not reclassified.

Run40464084185 confirmed the normalized location entry, but pointer responses
did not close SELECT_FOLDER. The next current driver uses the native keyboard
response and retains detailed visible-control diagnostics on failure.

Run40465292740 preserved tree, read only inside diagnostic Actions job122062168532,
shows Export here insensitive while the Location entry is focused and Recent
still displayed. Current driver now enters an explicit directory slash and waits
for native asynchronous validation to enable the response before activation.
No native control is programmatically enabled; exact final bytes/path stay strict.

GTK upstream gtkfilechooserwidget.c location_entry_changed_cb explicitly skips
selection-change timeout for SELECT_FOLDER, explaining disabled Recent response.
The current driver first uses documented Alt+Home to enter a real folder before
Ctrl+L. This is actual user navigation, not a programmatic chooser selection.
Source: https://raw.githubusercontent.com/GNOME/gtk/gtk-3-24/gtk/gtkfilechooserwidget.c

Split-job run40464084185 exposed artifact-upload symlink dereferencing, not a
product import change: original batch saw38 instead of37 and drop imported11
instead of10. Retained job now runs unchanged make_inputs.py in fresh independent
directories on Actions so actual symlink refusal cases remain symlinks. No existing
paths are replaced and no historical fixture generator or assertion is modified.
Its original G13 gate also rejected an unevaluated status check combined with
audit_completed (exit1 INVALID REPORT); this exact historical validator rejection
is recorded as historical_report_valid=false, not promoted to acceptance.

Alt+Home current five-tool passed all10 in run40467044912. Run40467454602
failed before its first behavior check: Session.launch could not find a mapped
PID-qualified host window. Workflow now requires actual Openbox readiness before
launch; failures also retain root window tree/process list/application log inline.
No host-launch timeout, original test expectation or total job budget was enlarged.

Historical collector now captures command output to a regular file rather than
a pipe: GUI clipboard helpers may inherit stdout and outlive the original driver,
so PIPE communicate waits for a descendant EOF after the driver has exited.
The original process exit and raw output remain unchanged; no test timeout/expectation
is relaxed and current acceptance is still independent.
