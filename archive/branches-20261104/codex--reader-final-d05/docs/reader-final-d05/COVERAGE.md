# D05 coverage delta (fixed default target)

Target 0889f7d1e9a537c6c1b05456547e016b26e1cd85; SDK
edddc463c06ed5731195cdb8f06b2df6dff7699e (source-identical SDK subtree).
No candidate feature macro is enabled. APK remains owner-built, unmodified.

Existing `reader_a11y_android` provides 15 cases including semantic labels,
48dp targets, shelf filtering, organization, annotation, rotation, scale 2.0 and
480dpi. D05 compiles and runs that Java suite unchanged; it does not replace its
assertions or treat findings as successful accessibility acceptance.

Additional independent UI-only cases: cancel document picker; actual import;
three read-back system scales (1.0, 1.3, 2.0) with shelf and reader captures;
portrait/landscape, explicit Activity rebuild, book identity and visible reading
text continuity; touch page advance; keyboard DPAD focus and dialog Back recovery;
explicit default entry probes for search, contents, records, settings and account.
Every capture retains XML, PNG and AccessibilityNodeInfo states/bounds; each input
is journaled with PID and activity dumps. No direct business/JNI call.

Default reachability is a product finding, not candidate coverage: Gradle defaults
all six feature switches to false. MainActivity.java:279–307 conditionally constructs
panels and hides `reader_more`. Search, TOC, records/bookmarks and preferences are
therefore not reachable in the formal default APK, despite candidate tests under
`tests/reader_android_{search,navigation,reading,preferences}`. Sync/account is also
macro-gated. Existing reading annotation is separately exercised by the reused
suite. Candidate raw3 4a04a9cc evidence is not used as default UI evidence.

Bounds checks detect zero/out-of-window controls; the original suite also checks overlap. They
cannot prove text glyph clipping, contrast or spoken labels. Screenshots support
later visual review; no screenshot-resize substitute for system font scale.
Scroll reachability and persisted reading offsets/records require successful
end-to-end entry; a blocked prerequisite stays failed/unverified, never accepted.
Physical keyboard hardware, actual TalkBack speech/gestures, physical Android,
other APIs/locales and release-signing behavior remain pending. Debug owner APK is
the only runtime scope; it is not a release/product grant.

## Retained execution history

Round 1: harness `5a8dd7e66a00a5262f61bf118574c42e03a811d4`, run
40215041256 attempt 1, audit job 121234243011 failed at tool installation:
`sdkmanager: command not found` (17:09:02 UTC). Build/emulator never ran; no
artifact was produced because the output folder was empty. Raw log remains at
https://github.com/NoGod3524/EXReader/actions/runs/40215041256/job/121234243011 .
Classification: harness environment setup, not a product failure. Round 2 uses
the existing audit's absolute Android SDK tool path and retains setup logging.
Also fixed filename sanitization for a TOC label containing `/`; no case IDs,
semantic labels, product source or assertions changed.

Round 2: harness `a32a10c191e8a6d2e791f81686f8f8761515a7b5`, run
40215281412 attempt 1. Audit job 121234967050 completed both independent
instrumentations: 15 original cases (5 pass, 10 fail), 19 delta cases (2 pass,
17 fail). Artifact 12607826896 retained. Verify job 121238972852 failed on
cross-host artifact redirect HTTP401, before ZIP authentication. The next
verifier strips Authorization on cross-host redirect; GitHub API still receives
its required token, and the signed artifact URL supplies storage authorization.
No credentials are printed and no digest/expiry/source check is weakened.

The delta cancellation case left DocumentsUI active; its failure is retained.
The independent import case now force-stops/relaunches the host as explicit
case setup, not as a retry of cancellation. Shelf row selection is restricted
to `book_list` plus the fixture's embedded title, matching CatalogShelf.java:262,
not status text or the old filename-only selector. The original 15-case suite
is unchanged, including its legacy selector and all failures. Added independent
annotation creation and post-rebuild record checks through real controls.
Font tree checks remain distinct from full font-scale acceptance because glyph
clipping/visual review and some page surfaces are unverified.
