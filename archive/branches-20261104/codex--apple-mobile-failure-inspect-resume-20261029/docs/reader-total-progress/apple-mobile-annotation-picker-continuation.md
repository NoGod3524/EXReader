# Mobile annotation picker continuation — 2026-10-29

Candidate based on `622b9558f79eda07211e15c51bffcd728da6c553`.
The original run [40923468266](https://github.com/NoGod3524/EXReader/actions/runs/40923468266) remains failed.
Both mobile hosts passed the original 13 base, 13 reading/navigation, 4 search and 4 live-system-theme cases.
Only `testNativeAnnotationPreviewConfirmCancelAndDuplicate` timed out under the original 240-second allowance.

The retained iPhone trace in [40932555109](https://github.com/NoGod3524/EXReader/actions/runs/40932555109) shows:
- JSONL was exported through the native folder chooser.
- The fixture path names the chosen `File Provider Storage/EXReaderAnnotations` directory.
- The native import chooser remains at local storage root with a cell identified `EXReaderAnnotations, Folder`, label `EXReaderAnnotations, 3 items`, after tapping the nested static text.
- The former helper queried exact labels across an embedded chooser and a separate Files app, then continued a fixed list of navigation labels.

The candidate activates the actual folder cell, stops navigation once the requested file is visible, and matches file cells with or without displayed extensions. It continues to select real native files and retains all preview, invalid-input, revision, cancellation, confirmation, duplicate, export-content and reading-position assertions. Every test body is unchanged.

The general tap helper captures the target and viewport frames once per attempt and reuses the successful target. It retains enabled/hittable/viewport conditions, the 24-scroll limit and 90-second wait. No native test count or time allowance changes.

The workflow runs the original five feature cases and all 34 prior cases on macOS, iPhone simulator and iPad simulator, then the original same-run ZIP authentication. This note does not grant acceptance before the new results are independently read. No SDK or product source changes are included.
