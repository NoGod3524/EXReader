# F09 crash-event collector correction

Authorized branch codex/dot-f09-av-stack-20261031; parent 068bf454388b2576883ef8b8f60f80be878faf58. Exactly three new files: run.py, workflow, this document. The earlier debugger (CDB) capture plan for this branch was stopped by a reply-generation safety classifier twice and is abandoned, not reworded. One initial Actions run and at most one correction limited to defects of this collector; the job keeps the 90min cap. All execution only GitHub Actions.

## Why

Read-only review of existing logs: every F09-EVENTS record in run41165411704 (7) and run41162331946 (5) reports available=false, error_type System.Exception, no events. The old collector kept no exception message and queried about 0.04s after process exit, so "no event written" and "query failed or too early" cannot be told apart. Faulting module, faulting offset and the event's exception code are therefore missing. Exit code 0xC0000005 and the managed stack (UiaCoreApi.RawTextRange_GetText under TextPatternRange.GetText) are the only crash facts.

## What changes

The new run.py loads the byte-frozen visible-range driver and replaces only three things: its guard (now pinned to this parent and three new paths, with nine consumer, driver, provider and product files hash-frozen), its output directory build/f09-av-stack, and its crash_events collector. The eight observations, both 26-check suites, all assertions, timeouts and same-source host builds with the identical test-only provider overlay are the frozen driver's own code.

For each nonzero exit the corrected collector polls the Application log up to 30s for event 1000 (Application Error) matching the probe or host PID, and for event 1001 APPCRASH whose app is one of the five known binaries. It keeps only app, module, module version, exception code, fault offset, time and provider, plus WerSvc status, poll count and each query exception type and message. No event Message text, no LocalDumps, no debugger, no memory, register or parameter reads, no book text.

## Interpretation limits

A module plus offset is a location, not a root cause or responsibility. No events after 30s will be recorded as "WER produced no record on this runner", not as proof of anything. Formal F09 acceptance and screen-reader verification remain false. All earlier failures are retained.

Initial status: source prepared, no run yet.
