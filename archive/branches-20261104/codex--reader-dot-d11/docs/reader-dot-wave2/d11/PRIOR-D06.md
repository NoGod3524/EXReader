# Findings and owner queue

This is an audit queue, not permission to change platform shortcuts. Findings distinguish
source facts, native execution, and harness limitations. Final run identities/counts live
in `validation.json`; historical runs are not combined into a six-platform pass.

## Source-level consistency findings

1. **P1 / Windows host integration owner — Ctrl+O changes meaning by mode.**
   At default source 0889, page `WM_KEYDOWN` dispatches `IDC_OPEN_BUTTON`; compact
   translator catches Ctrl+O before native dispatch and invokes `compact_import`.
   Default open-selected and compact import-picker are different semantic actions.
   Compact import/cancel has real new execution; default Ctrl+O comparison is source
   tracing, not a newly replayed shortcut. Preserve both current mappings until owner
   chooses/document one policy.
2. **P1 / GTK host owner — Ctrl+F is shelf search, not in-book search.**
   `key()` reserves Ctrl+Shift+F for `inbook_open`, then Ctrl+F switches to shelf and
   focuses search. Windows Ctrl+F opens in-book search. This may remain intentional,
   but labels/help must make it predictable. GTK compact real menu/search navigation
   is replayed; this audit does not privately change keys.
3. **P1 hypothesis / Android preferences owner — explicit edit/modifier guard absent.**
   Hardware mode `MainActivity.dispatchKeyEvent` tests current page, operation,
   selection and repeat but not EditText focus or modifiers. A modal may intercept
   before Activity; therefore absence is not proof of typing loss. The new adb query
   focus test does not force hardware mode4 and is not a physical DPAD/keyboard pass.
4. **P1 hypothesis / Windows event-routing owner — modifier matching is broader than J08.**
   Ctrl+L accepts Shift/Alt; Ctrl+F and Ctrl+G reject Shift but not Alt. A focused input
   on an AltGr layout requires a native follow-up before input-loss verdict. J08's
   exact-modifier safety is not evidence that these real host routes use it.
5. **P2 / Apple host owner — no explicit host shortcut routing located.**
   Shared views/ReaderApp contain no custom keyDown, keyboardShortcut, UIKeyCommand
   or onKeyPress routing. Native text defaults still work independently; neither
   J08 Command mappings nor a simulator tap pass establishes macOS keyboard parity.

## Retained native harness failures (not product defects)

Round2 harness `9f5358bfa4ba8d4de06d254442baf4def4b0fbb3`, run40215565178/1:

- **macOS / job121235871626:** real unsigned app reached next page, focused search
  input and no-hit result. Immediate `XCTAssertFalse(search.query.exists)` after
  tapping close failed at ActionFocusTests.swift:23. The assertion did not wait for
  sheet dismissal animation. Hypothesis: premature observation, not proven broken
  Close. Small fix for the D06 harness owner: wait for actual query disappearance
  before asserting restoration; preserve the observable disappearance requirement.
- **iPhone / job121235871580 and iPad / job121235871611:** native test reached
  `reader.more` but generic `.isHittable` precondition timed out. Existing owner
  `tests/apple_host/reading/ui/ReadingUITests.swift:53–71` already documents the
  UIKit SwiftUI Menu AX wrapper: the native descendant button has measurable bounds
  but neither wrapper nor trigger supplies an XCTest hit point. The original owner
  taps the measured button center and then requires the real popup to appear.
  Small fix for the D06 harness owner: reuse that exact native trigger procedure,
  retaining bounds checks and actual records popup assertion. Do not substitute a
  private handler or call the Menu inaccessible solely from this generic predicate.
- These runs used HOST_REVIEW + IMPORT_REVIEW + PAGE_THEME due the generator's
  directory-based configuration. They are not production-semantic-tree grants.
  Final harness uses `accessibility/ui` staging and explicit rejecting macro guard.
- Signing was disabled; these original failures were real XCTest assertions, **not
  a signing/installation blocker**. The unsigned apps did launch and execute.

## Still not granted

Complete modal Tab loops and repeated-submit suppression across every dialog;
default GTK runtime parity; mobile physical keyboard/DPAD; all screen-reader speech;
production six-platform common-source acceptance; external account/network behavior;
performance or layout budget compliance. Missing dedicated Continue entries remain
missing rather than being represented by an internal API.

## Final-round Android cancellation observation

Run40217793667/1, job121242662311, target4a04a9cc74dde67f755c87e87b278d63a254a3ac:
unchanged native search15 and navigation18 pass; added query Left/Right/Space/A,
search Back page preservation, records entry/Back page preservation, shelf return,
and native picker entry pass (9 checks). One Back followed by the expectation that
`book_list` reappears timed out at `picker-cancel`. This is an unresolved harness
expectation, not a product cancel defect: DocumentsUI Back can navigate inside its
provider before exiting. Raw UI XML/screenshots are retained in the authenticated
artifact. D05 independently observed Download→storage-root navigation; that separate
run is a diagnostic lead, not D06 evidence or acceptance. Owner: D06 harness owner;
next authorized run should inspect the active package/tree and use the actual native
cancel/close route, then retain the same app-return and focus assertions.

Final-round macOS job121242662291 repeats the immediate query-disappearance failure
at ActionFocusTests.swift:36 after search-result. Unlike round2, its generated project
explicitly rejects review macros (`review_macros_present=false`, page theme enabled,
project SHA256 f0b2b93de5b8733b9f0bd1fe2734462be385f0bd587e57819b96d0581ac387f1).
The real unsigned app launched and the runtime reader.state absence guard passed.
Do not describe this as a signing failure or grant a complete search-close/focus path.
