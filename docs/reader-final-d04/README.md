# D04 Apple default UI / AX audit

Target implementation: `0889f7d1e9a537c6c1b05456547e016b26e1cd85`.
Approved SDK identity: `edddc463c06ed5731195cdb8f06b2df6dff7699e`, 3.41.0 / ABI1 / core3.40.0.
Harness branch: `codex/reader-final-d04`. No product changes. All execution and artifact inspection are Actions-only.

## Reuse and difference from G16

- Reuses unchanged G16 AX recorder, geometry classifier and its positive/negative regression. No duplicated AX implementation.
- Reuses unchanged `tests/apple_host/accessibility/ui/ReaderAccessUITests.swift` for genuine fixture import/body semantics and compact reading regression, preserving its original assertions and waits.
- Reuses current original `tests/apple_host/make_xcodeproj.rb` through its explicit `/accessibility/` path, SDK3.41, page-theme OFF. This links current product modules and emits no review macros. G16's old generator lacks that current product linkage; its older UI suite retries taps and does not represent current default UI, so is not reused as a driver.
- New no-argument launch audits default shelf/account chooser, dismissal reachability, reading next page, search/TOC/notes dialogs, More → reading records, return, rotation/window drag, and Mac Tab/Escape. Fixture buttons are asserted absent on these launches. Previously seeded sample books come only from the separately named unchanged import case.
- True simulator content size is set/read at medium and accessibility-extra-extra-extra-large; recorder reports device text metrics. No SwiftUI text-size override. Mac window resize is not system large-font coverage.
- Every target builds the same protected fixed-base files; actual executable/plist hashes, installed-library hashes, model/runtime destination, generated configuration, entitlements output, XCUI trees, screenshots, traces and xcresults are retained. The embedded EXRSourceSHA is the fixed target SHA, not the harness SHA.

## Gates and limits

Three targets run with matrix max-parallel 2. Failure is retained; audit-completed is separate from UI/AX/Dynamic Type acceptance (initially false). Independent verifier downloads original artifact ZIP bytes only in Actions, recalculates byte length/SHA-256 against GitHub metadata, checks unique names, expiry and same run/source/attempt/job, and validates the internal file manifest. Mutated metadata negative cases must be rejected.

This is not VoiceOver, physical-device or final product acceptance. Focus owner/restoration order is unobservable via the reused public XCUI API. Mobile hardware/full keyboard access, macOS system large-font setting, system picker import, text-clipping visual review, search query/result navigation and complete settings remain pending. Default page-theme OFF has no theme action (`examples/apple/HostViews.swift:521–524`); no raw3/review build is substituted. Conservative geometry findings for offscreen controls are observations, not proof that native scrolling cannot recover them.

Retained historical failures: G16 runs 40085956514/40090892898 classifier gaps (see immutable existing report); Apple mobile candidate `72c6bbdd14ebf3be453fa7f0da81119d52675eb5`, run40203714083, failed as a whole. No prior iPhone/iPad/Mac success is joined to this run.

## Retained round 1 failure — 40215135700 / attempt 1

Harness `5a8a210cf524303dae9748c8130aa9def20176d3` did not audit the default program. Mac job121234532673 stopped before compilation: Bash3 empty-array expansion under nounset. iPhone121234532463 and iPad121234532680 built with **EXR_APPLE_HOST_REVIEW and EXR_APPLE_IMPORT_REVIEW**, because File.expand_path removed the terminal slash and `/accessibility/` did not match the staging path. The shell's `! grep` did not exit under `set -e`. The old report's hardcoded `review_macros: []` is incorrect; actual project and compiler logs take precedence. No default-UI observations or acceptance are transferred from this round.

Both mobile original regression cases failed at unchanged ReaderAccessUITests.swift:146 (`reader.state` unexpectedly exists). Sample.epub seeding therefore never ran; subsequent default reader journey and compact regression failed on missing Sample. Both default-launch shelf/account-dismissal cases executed at normal/large size, but in the wrong review-enabled binary and do not grant default product scope. Program hash e630b428b0529df8911046ff5431d366bca9c51fbba59e13fcee8c72e2d7a3eb is the **review-enabled** mobile executable, not a valid default program.

Round 2 changes only owned harness paths: stage under `/accessibility/ui`, explicit rejecting guard, derive review macros from actual generated project, verifier cross-check actual project and compiler flags with review-leak negatives; preserve original test assertions/time budgets. Mac supplies a nonempty macosx SDK option. PNG attachment signatures and original geometry-regression evidence are retained. No production fixes or assertions weakened.

## Retained round 2 findings / final harness correction

Round2 `4f342940fbe1c3bbd74022e33b2e6fdea6f572b6` / run40217426634 is a genuine no-review build. macOS original production semantics/import/edge-tap and compact reader tests pass. The new journey incorrectly read only StaticText.label: actual AX value changed 第1章·第1页→第1章·第2页 while label remained empty. Final harness uses the same label-or-value accessor as the unchanged original test; assertion and timeout unchanged.

iPhone original normal/large regressions pass. New normal journey reaches page turn and search/TOC/notes dismissal, then direct `reader.more.isHittable` is false. This is **not proof of a product-user reachability defect**: existing `tests/apple_host/reading/ui/ReadingUITests.swift:53–71` documents UIKit Menu AX wrapper/trigger limitations and a measured native-coordinate method. D04 retains its failing direct-XCUI path without coordinate fallback; records reachability remains pending. Large-font new audit aborts when the unchanged G16 recorder asks isHittable of offscreen reader.font.decrease and XCTest cannot derive an activation point. That is an instrumentation limitation; original compact regression still exercises actual toolbar scrolling.

Geometry/name output is raw conservative audit evidence: empty XCUI label alone does not prove lack of a spoken name (value/placeholder may carry it), offscreen frames alone do not prove unrecoverable clipping, and false Menu isHittable alone does not prove real taps fail. No such observation is promoted to VoiceOver or full AX acceptance.

Final verifier additionally compares uploaded executable/Info.plist bytes directly to reported hashes/source/version/page-theme and scans retained text logs/manifests for concrete credential patterns. This is a bounded scan, not proof of absence of all possible secrets.
