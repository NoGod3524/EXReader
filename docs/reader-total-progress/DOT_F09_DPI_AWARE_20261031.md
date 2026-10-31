# F09 Windows DPI awareness

Branch codex/dot-f09-dpi-aware-20261031; parent 1e3a1bc66b9465e42a3afb3cd72c8294d0bfcf39 (Narrator package observation). Product change: ten files; plus run.py, workflow and this document.

## Defect

Local Narrator check on a 125% display (AppliedDPI 120): its focus box for EXReader controls was drawn at about 0.8 times the real position and size, partly outside the window. A DPI-unaware Microsoft RichEdit test window showed the same offset, a system-DPI-aware one drew it correctly, and EXReader had no DPI awareness anywhere (no manifest, no API). Accessibility rectangles, Narrator highlight, magnifier following and touch exploration all depend on this.

## Change

- Start-up declares system DPI awareness (SetProcessDpiAwarenessContext, resolved dynamically) and reads the system DPI.
- Layout constants stay written for 96 DPI. MoveWindow and CreateWindowExW are wrapped by macros that scale them; the two places that derive sizes from the client rectangle (main layout and compact layout) convert to 96-DPI units first; dialog placement, minimum track sizes and the persisted window size use the same helpers (the persisted size is stored in 96-DPI units, matching what a DPI-unaware process used to see).
- DEFAULT_GUI_FONT (fixed size) is replaced by a font from SystemParametersInfoForDpi at the system DPI.
- Not touched: accessibility provider, the a835 Escape routing, page rendering. At 96 DPI every helper is the identity, so CI geometry and the 26-check self-test are unchanged.

## Limits

System-aware, not per-monitor: a window moved to a monitor with a different DPI is bitmap-scaled by Windows and its accessibility rectangles are then virtualized for that monitor. No WM_DPICHANGED handling. Scaling and the highlight can only be checked on a display above 100%, so CI proves build and self-test only; the real check is manual. Formal F09 and Narrator speech verification remain false.

Initial status: source prepared, no run yet.
