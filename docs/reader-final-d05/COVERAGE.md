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
