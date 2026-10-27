# H.android.font_library — current common candidate

Base: `1dfd2c3ba3184eb9a9df531d3858eafb95c2e80c`.

The product delta exposes the existing local-font panel from the reading More menu.
No new font owner, protocol, or SDK change is introduced. Font choice retains the
existing next-open application semantics.

The task workflow runs the original C11 device driver (all original walkthrough,
wave3, navigation and reading checks), followed by an independent font-reader
instrumentation runner on the same installed APK and API 34 emulator. A failing
retained suite remains failing even if the new checks pass.

The original C11 guard is immutable and scoped to historical seed d263ce5; applying
that branch's exclusive ownership list to the later common candidate rejects
already-accepted unrelated integrations. The independent task guard instead
freezes **every** path outside its four explicit task paths against the requested
common candidate; SDK, public ABI, old tests and budgets are unchanged. The
retained report executes all original acceptance checks, with only the explicit
provenance seed rebound to this task's guard. Historical evidence is not modified.

System document activity results in the new font runner are framework test stubs
returning private fixture URIs; DocumentsUI is not driven. Actual font import,
selection, SDK rendering and lease ownership run in the real application. The
book is set up through the existing C11 SDK-import fixture path, not an end-to-end
system book picker. This is emulator evidence, not physical-device or TalkBack
speech acceptance. It does not independently change the 108-item audit.

Pending Actions result; do not treat this plan as completion evidence.
