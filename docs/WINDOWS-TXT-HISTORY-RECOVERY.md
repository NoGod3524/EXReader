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

[Run 40623920454](https://github.com/NoGod3524/EXReader/actions/runs/40623920454)
executes the unchanged host assertions on the candidate. Its result, including
the ambiguity refusal and history cursor behavior, must be reviewed separately.

## Passing original host scenario

[Run 40624221957, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40624221957)
completed successfully on source c5688c4adf0506d44e097b076be30e1985341012.
The actual Windows host found the deep unique target, returned to the original
page and advanced again. Its independently expected and restored source byte
offsets were both 970,000. It then displayed a repeated target near the end,
returned to the unique page, and rejected an ambiguous forward history entry
without moving the cursor. The original per-operation 300-second limit was
retained. The full host report, owner, compact and extracted UI checks passed.

The run artifact is [12788901967](https://github.com/NoGod3524/EXReader/actions/runs/40624221957/artifacts/12788901967),
612,796 bytes, SHA-256
f53cba3197f9ce31fbf1bd1454fcfa27e814bea08d6d34ea7d1d35ddde17897a.
The same-run report is preserved in that artifact. The earlier 92,015 ms
measurement above belongs to the failed source and is not a measurement from
this successful run.
