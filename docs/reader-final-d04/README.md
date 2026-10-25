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
