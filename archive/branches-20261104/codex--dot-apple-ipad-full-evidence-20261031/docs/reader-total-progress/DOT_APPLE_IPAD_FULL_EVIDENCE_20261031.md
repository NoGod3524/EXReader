# Fixed iPad full failure text evidence
Prepared, not yet executed. Independent diagnostic only; Apple implementation remains with its owner.
Base/source 94fb236a4a2da87dfbaf4f1dd2a47885d615a230, producer run 41170540560 attempt 1.
Branch codex/dot-apple-ipad-full-evidence-20261031, only verifier/workflow/this document.
User grants Sentinel_29d403f1989481918499b46cbb643164 and Sentinel_77ce490d866c8191b2c61b846bee32fd.
Budget: ONE Ubuntu Actions run, 20 minutes; no correction rerun, build, UI launch or new product test.
Original tests, assertions, runner/checker, SDK and product source remain byte-unchanged.
Full producer 15 success / 4 failure remains; focused success is not substituted. Formal 95/108 unchanged.

## Immutable inputs
- Native iPad job124448285973 artifact13032504303, 464812115 bytes,
  SHA256 b0b85e0f441c0744bb7cd944f1e6c541cc9ac3ae495e645d93ca494bfb76661b.
- Organization iPad job124448286050 artifact13031193956, 134077340 bytes,
  SHA256 185ea31bb53fff8ee051fa827f6b8530b95f928a4e9571e482bddd19c511e987.
Both must match source/run/attempt/job/name/conclusion/API size/digest and downloaded bytes.
Original ZIPs are read only in Actions temporary storage, never executed or uploaded again.
Safe members only: no traversal/aliases/duplicates/links/encryption; 50000 members, 8GiB total,
1GiB individual binary, selected logs <=256MiB, line <=32768 bytes, <=1M lines.
Excess is an explicit failed diagnostic, never silent omission.

## Evidence and privacy
Use exported original wave3-native-ui.log and organization logs/whitelisted result JSON.
Retain exact member hash, original line number, original elapsed timestamp, test/launch boundaries,
first explicit error, bounded error context, native tap/scroll decision values and largest adjacent gaps.
No added accessibility queries. Adjacent gaps are not exclusive AX durations.
The last action before teardown is not automatically successful body completion.
Debug tree native type/geometry/identifier retained; display labels/values redacted.
No environment, command argv, credentials, full unrelated logs, screenshots or payloads uploaded.
Only derived redacted JSON and receipt are published; no raw ZIP/extracted tree.

Ubuntu cannot decode binary xcresult objects/attachments. Their presence is recorded, not parsed.
Missing first issue/activity metadata is an explicit gap, not invented from a 4-minute duration.
Existing c44 parser was macOS-dependent: reuse identity/safety/segmentation concepts only, not xcrun.
Do not infer a new product root cause before reading this run's original lines.

Privacy boundary: sensitive-key/header/Bearer-bearing text lines are wholly omitted; retained JSON strings use the same filter. This is scoped redaction, not a claim of universal secret detection.
Only selected log and JSON formats are parsed. XML presence is reported as an explicit unsupported-format gap, never silently treated as inspected.

## Sealed result: 2026-10-31 07:14Z

Diagnostic source 739a5ce6179fc91026e8ffe89117e804e208e818, run 41179353708 attempt 1, job 124473385813: SUCCESS. Budget 1/1 consumed; no product rerun.
https://github.com/NoGod3524/EXReader/actions/runs/41179353708
Derived artifact 13034347129: 46788 bytes; SHA256 2e287227af954b18598611489a56de6b0c83268e85fcc0588a660a7ec792a652.
Both input ZIPs authenticated against producer run 41170540560 A1 / source 94fb236a4a2da87dfbaf4f1dd2a47885d615a230; diagnostic_complete=true, errors=[].
Independent reviewer verified API and ordinary Actions log. This is diagnostic success, not product acceptance. Formal count stays 95/108.

### Native iPad annotation

wave3-native-ui.log: testNativeAnnotationPreviewConfirmCancelAndDuplicate starts line1833. Line2706 t237.93s drags toward features.preview.confirm; line2717 t238.77 waits for idle; line2718 first explicit 4-minute execution allowance failure.
Actual confirm tap only at t243.84 (line2738), reader.location t246.78, teardown t246.87 (2769), terminate t246.98 (2773). Failure therefore occurs within the original body, not teardown-only. Later actions do not erase the timeout.

93 EXR-DECISION records retained, NOT 93 taps/scrolls.
Call20 preview.discard: four queries, one controlled reversal after overshoot, ready after8.492s.
Call21 annotations.roundtrip: three queries, ready after5.560s.
Call22 preview.confirm: three queries/two scrolls, ready after6.159s, budget expires before tap.
Different controls are at separated positions; evidence does not establish an unbounded same-button loop.
Longest adjacent observed log gap20.99s: line2249 t106.48 features.cancel existence to2250 t127.47 features.status find. This is elapsed time, not exclusive AX time or a proven removable wait. Stable remediation needs margin, not merely four seconds saved.

### Organization iPad

apple-sdk342-supplemental/ipad/organization/original-organization-six.log: first five cases pass. testTagAndSeriesPersist starts2393; first assertion2851: OrganizationUITests.swift:42 Missing organization.kind.tag.
After launch/automation setup, t55.03 waits for library.organization. Debug tree collected t145.50 contains library.organization and library.list. Teardown146.83, terminate147.23, failed duration148.781s.
Filtered full actions are retained in derived evidence; console excerpts do not establish why entry failed to produce tag controls. Zero decision records does not mean no tap.

### Limits and owner handoff

Ubuntu does not decode xcresult object/attachment binaries; unavailable issue/activity fields remain gaps. No stitching with focused success/other attempts. Preserve original failures.
Owner should examine body scroll/query timing and organization entry separately using fixed producer source/run, original line numbers and derived artifact. No implementation or further test run is performed by this diagnostic package.
This is a continuity backup, not completion of the target.
