# Windows large TXT search history recovery

[Run 40622141313, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40622141313)
on source 346bab9ad7b0c16086fbae70059c7b4590e1119e failed the native TXT
progress suite. The original failure remains recorded in that run.

The real host independently verified and displayed a repeated search hit near
the end of the large TXT. Its trace measured page location from tick 501781 to
593796, or 92,015 ms. The next history-back operation failed: the page remained
at the repeated result and the host reported an invalid or unresolved location.
The test timed out at the original 300-second back-navigation assertion.
Other retained owner, compact and native UI checks shown in the report passed.

Candidate source ab13b7606a08d1053f129749c8bdb39d32a7b99e preserves the
current selected point as the history origin when that selection belongs to the
displayed TXT page; otherwise it retains the page-start point. This can preserve
the distinctive point of a previous search without accepting ambiguous results.
The candidate adds controlled diagnostics for selector resolution state and
offsets, without logging book text. It has not yet been accepted.

[Run 40623920454, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40623920454)
failed at the same history-back assertion. Its trace established that after
back and forward the selection had been cleared, the old candidate used page
start 969,960, and the selector was ambiguous. The history cursor did not move.

[Run 40624221957, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40624221957)
on source c5688c4adf0506d44e097b076be30e1985341012 passed the complete
Windows host workflow. A later candidate keeps the previously resolved point
with the displayed frame, and the run asserted that the expected and actual
restored source offsets were both 970,000. The end-of-file search, history
back and ambiguity refusal all passed under the unchanged 300-second limits.
The same-run artifact is 12788901967, 612,796 bytes, SHA-256
f53cba3197f9ce31fbf1bd1454fcfa27e814bea08d6d34ea7d1d35ddde17897a.
