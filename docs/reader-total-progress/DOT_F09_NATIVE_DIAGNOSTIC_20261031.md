# F09 native UIA diagnostic continuation
Original failures 41152293447/69cd82d7 and 41155749004/bd334761 are retained.
The second reached baseline text length 432 twice and Ctrl+A event, then failed
with native AccessViolation during selection GetText. Candidate independently
reported ElementNotAvailable during initial DocumentRange, before Escape.
No full F09 acceptance or screen-reader pass is established.

The newly authorized batch permits at most two additional evidence-led rounds.
This is round 1 of that batch. Only the ready loop retries ElementNotAvailable
within the unchanged 120 seconds. No AccessViolation is caught or suppressed.
All original text, selection, focus and event assertions and budgets remain.

Actions creates two detached worktrees, baseline plus diagnostic overlay and
candidate plus the identical overlay; these are NOT original unmodified binary
receipts. The production provider file in Git is untouched. Only test builds set
EXR_F09_DIAGNOSTICS=1. The overlay logs GetText entry/return, reference counts,
endpoints and text length, PID/TID and HRESULT, never text or memory contents.
It uses no added mutex or inter-thread synchronization; diagnostic file IO can
still perturb timing, which is an explicit limitation.

The receipt records original/compiled provider hashes, overlay hash and macro.
Windows events are constrained to the launched probe/host PIDs and current
observation time window, exposing only module/app names, exception code and fault
offset. No full event Message, credential data or memory dump is collected.
Missing events are reported as missing, not evidence of no fault.
Both observations run independently; either failure keeps the workflow red.
Source/Git editing only through the designated Desktop Commander/InstaBox route.
All execution and validation remain Actions-only.

## New-batch round 1 result and final bounded diagnostic
Run 41156727928 A1 at 475a6e7875b250f8b96c531a4a70898a1e429fd1 remains FAILURE.
Both diagnostic hosts returned document text length 432 twice and received Ctrl+A.
After GetSelection returned one range, both managed probes crashed in selection
GetText. Provider logs contain two complete successful document GetText sequences
but no selection GetText entry; prior logging success narrows the boundary but
missing output alone cannot prove non-entry because logging IO can fail.
The candidate ready transient exception is now retried within the same 120s.
Windows fault events were unavailable; no fault address has been established.
Artifact 13026045081 retains 10572 bytes with SHA256
cf589512893bea0749c99e1e0351f31013ee211796a282b99f8381ed8e53a258.

Round 2 of the new two-round batch adds only test-overlay observation of real
range creation, QI request category, actual AddRef/Release return counts, and the
SAFEARRAY publication VT/dimension/bounds. Process-local pointer values identify
objects, not their memory contents. No extra self-QI or reference operations are
introduced; real final ownership and all return/error paths remain unchanged.
No product fix is inferred from this diagnostic. The existing exact original
and compiled hashes, identical dual overlay, text/selection/event assertions,
budgets, and failed overall verdict for either probe remain.
After this final authorized round there is no automatic additional execution.
