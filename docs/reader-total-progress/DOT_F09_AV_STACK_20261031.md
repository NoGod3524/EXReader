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

## Initial validation result (1/2), 2026-10-31 04:56 UTC

Source 65a53165226ebfa0abd4b48434f87d5fc81a7186; run41170051294 attempt1, job124445853620: overall failure, as the frozen assertions require. Artifact13030448364, `f09-av-stack-41170051294-1`, 49289 bytes, SHA256 97716877fec7af31858689f0d6ff9757101204693f026ba3b53bbfb61aa90aa5. Guard passed, both preserved 26-check suites passed, all eight observations executed:

| Consumer | Baseline exit | Candidate exit |
|---|---|---|
| managed selection | 0xC0000005 | 0xC0000005 |
| typed native COM | 1 (original Escape clear failure) | 0, all original assertions pass |
| legacy selection | 0xC0000005 | 0xC0000005 |
| legacy visible array | 0xC0000005 | 0xC0000005 |

Same pattern as run41165411704. Within this run all four consumers per source share one host hash: baseline d17083681fe660c7232ccd5f351f76d0459867be593c385c2a0d0142ba698e05, candidate 7275d64c5ba22f62a2c833dce23e417fc22a58e49f6bb95c4a8d856abdde8b89. These differ from run41165411704's hashes, so host builds are not byte-reproducible across runs; cross-run comparison is by source, not binary.

Collector result for all seven nonzero exits: collector rc0, 30 polls each over the whole window from probe start to 30s after exit, every poll returning the OS message "No events were found that match the specified selection criteria." (210 of 210, no other query error). WerSvc status Stopped. application_error_1000 and wer_1001 empty everywhere.

Conclusion: the old empty result was not a query defect or timing artifact; this windows-2022 runner writes no Application Error 1000 or WER 1001 record for these crashes. Faulting module, faulting offset and event exception code remain missing and cannot be obtained from Windows event logs on this runner. No collector defect was found, so the one correction run is not used and stays unspent; it cannot be repurposed for a different diagnostic. No product, provider or consumer change. Formal F09 remains false; all prior failures remain retained.
