# Windows F3 focus/theme correction

## Base selection before host changes

Audited source `1adeabf2a672ddc0c200631e29897cfe76106afd` and precise failed source
`e330a415b733db18dea5aa6010d13cf3063587fd` diverge at
`f34a4f27161061d08ecc40f5cebfb6f5018aa77f`.
The audited source predates the accepted TXT forward-scan/font lifecycle changes
present in the failed current Windows composition. Select **e330a415** as the
minimal compatible base, preserving all its host and frozen SDK source.

Original failure: run 40638398225 attempt 1; original artifact 12795210910.
Authenticated diagnostic: run 40640905795 attempt 1, job 122658557186,
artifact 12795776314. Actual client 797x541; layout [214,4,368,533]; white page
corner, 692 ink samples and minimum RGB sum 0 passed. Only surround (210,1)
was black. Original failed evidence remains intact.

The first independent branch run changes no product source. It measures the
same original sample and real HWND focus/UI-cue changes; it does not edit the
old F3 judge, sample coordinates, checks or thresholds. Hypothesis: unconditional
DrawFocusRect ignores the Windows UI cue state; actual contrast is required
before selecting a host correction. This is not yet acceptance.

## Real Windows contrast and selected minimal fix

Run 40653667318/1, job 122699474014, source
`210a482f16c380afacd57ff43a13037eb2e072ec` rebuilt unchanged production.
Artifact 12800723856: 39,251,362 bytes, SHA-256
`9d37009872f302283b43930d1dc9db607f8ef3d851d88efb6f4ff1d1cc00b7a0`.
After the original light-settings interaction the native UI state was **0**,
not hidden; sample (210,1) was black and 397 top-edge pixels were dark.
Explicit UISF_HIDEFOCUS changed the native state to **1** but all 397 pixels
remained. Thus the original failure is a focus-overlay/sample collision, not
incorrect SDK theme ink, and ignoring native cue state is a separately proven
host defect. The initial WM_NEXTDLGCTL focus-away labels were ineffective on
the ordinary window; they do not prove focus transitions. The final independent
harness uses UI Automation with GetGUIThreadInfo verification and real Tab.

The isolated host fix respects WM_QUERYUISTATE, repaints after WM_UPDATEUISTATE,
and confines the visible document focus outline to its rendered canvas rather
than drawing over the unrelated letterbox gutter. Empty views retain their
whole-control focus outline. The outline is inset one pixel inside the clipped
canvas, outside text; new live comparisons check light/dark interior hashes,
visible keyboard cues and unchanged white gutter. The original 25 F3 checks,
coordinates and thresholds are unchanged. This is not a theme-renderer or layout
redesign. High-contrast settings/screen-reader acceptance remain separate unless
explicitly tested and reported.
