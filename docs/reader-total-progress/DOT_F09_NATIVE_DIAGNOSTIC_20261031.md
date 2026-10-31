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
