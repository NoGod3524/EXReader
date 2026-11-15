# Windows keyboard failure follow-up

The first full local run failed at `examples/windows/check_shell_selection.c:118`, immediately after Ctrl+C, on `clipboard_contains("Alpha")`. That failure remains in `ctest-first-failed.txt` / `.xml`.

The exact isolated test was run without source changes:

```text
ctest --test-dir build/audit-msvc -V -R '^windows-selection-keyboard$'
507: SHIFT inline 3/3; row 2/2; Ctrl+A/C/Esc 3/3
507: PASS
1/1 Test #507: windows-selection-keyboard ....... Passed 0.08 sec
100% tests passed out of 1
Total Test time (real) = 0.12 sec
exit=0
```

Full output: `keyboard-isolated.txt`.

`examples/windows/shell_selection_drive.inc:23`–`:27` saves the calling thread's keyboard state, explicitly sets generic Ctrl/Shift, calls the real page HWND synchronously via SendMessage, then restores the state. The immediately preceding Ctrl+A assertion checks a nonempty selection. This route does not need a foreground window or physical modifier input.

The remaining system dependency is the Windows clipboard. `examples/reader.c:4800` calls OpenClipboard once for the production copy; `examples/windows/shell_drive_test.inc:389` calls it once for the assertion's read. The read helper returns false on an open failure or missing/unmatched Unicode text. The original failure lacks clipboard error/owner/sequence diagnostics, so it cannot distinguish contention from replacement or another copy failure. `examples/windows/selection_tests.cmake:82` already makes the test RUN_SERIAL.

Clipboard contention is a hypothesis, not a confirmed cause. No production change, retry, assertion change or threshold change was made for this diagnosis. The original failing full run and the later passing isolated run are separate results.

## Subsequent diagnostic reproduction

After a second complete local run again failed this assertion, failure-only diagnostics were added under `EXR_READER_TEST_DRIVERS`. They record API error, clipboard sequence, owner/open HWND and PID, storage byte size and UTF-8 length. No clipboard contents are recorded. Forty diagnostic subprocess runs retained the original assertion; `keyboard-repeat-40.txt` records **38 pass / 2 fail** (attempts 3 and 18), with harness exit 0 meaning only that all diagnostic repetitions completed.

Both failing attempts recorded production write and assertion read failing OpenClipboard with error 5 while an external window held it. Example from attempt 3:

```text
CLIPBOARD write-open-failed error=5 sequence=198->198 owner=0000000000340876 owner_pid=29532 open_window=0000000000040234 open_pid=6392 storage_bytes=580 utf8_bytes=308
CLIPBOARD read-open-failed error=5 sequence=198->198 owner=0000000000340876 owner_pid=29532 open_window=0000000000040234 open_pid=6392 storage_bytes=0 utf8_bytes=0
Assertion failed: clipboard_contains("Alpha")
```

The complete original lines also retain owner HWNDs. Read-only process lookup `keyboard-lock-process.json` identifies PID 6392 as NetEase `GameViewer.exe`. Every before/after physical Ctrl/Shift/Alt snapshot was false. This reproduces external clipboard lock contention; it replaces the earlier hypothesis with measured evidence.

Some passing baseline attempts also recorded a failed copy acquisition: because every loop copied the same Alpha-containing fixture, the old assertion could read previous fixture content. The final keyboard test therefore asserts that writing a non-Alpha sentinel succeeds before each Ctrl+C, retains the exact Alpha assertion, and asserts that the clipboard sequence changes after copy.

The production fix shares one bounded acquisition helper between clipboard_set and the test read: on ERROR_ACCESS_DENIED it polls at 5 ms intervals against a 200 ms deadline; other errors and persistent denial still return failure. This retries resource acquisition, never the assertion or whole test. Normal product builds do not include the diagnostic logger. Final repeat/full-suite results are recorded separately after rebuilding.

After the full MSVC rebuild returned exit 0, the same 40-run diagnostic harness ran the strengthened sentinel/sequence test. `keyboard-repeat-fixed-40.txt` records **40 pass / 0 fail** and no CLIPBOARD failure diagnostic lines; every repetition retains the Alpha assertion. Actual final output:

```text
SHIFT inline 3/3; row 2/2; Ctrl+A/C/Esc 3/3
PASS
Diagnostic summary: {"runs": 40, "passed": 40, "failed": 0}
harness_exit=0
```

These diagnostic repetitions support the resource-acquisition fix; they do not replace the final complete local/Actions CTest runs recorded by the main report.
