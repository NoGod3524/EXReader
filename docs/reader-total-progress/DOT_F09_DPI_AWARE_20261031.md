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

## Result (1/2), 2026-10-31 07:25 UTC

Source cc65d1e2855a054851d132f863bc5f79c8c44c18; run41175736889 attempt1, job124462798287: success, 26 Windows native host checks passed, no new compiler warning from reader.c. Artifact13033480326, `f09-dpi-aware-41175736889-1`, 17141996 bytes, SHA256 872996eedf469fff6be3e70edc82ebe387b03fec8774ac9dcbd305cc104fde5e; EXReader.exe SHA256 6f1e561e5f12ed85c047063e46d019358cba5a3d4c563c7f74d609ffe29332cf. Downloaded with user confirmation into a new empty folder; all 31 files matched the manifest.

Local check on the same 125% display (AppliedDPI 120), same method as the Narrator package observation: EXReader opened at DPI-scaled size with scaled controls and font. With Narrator running, its focus box matched the real control rectangles for the whole window, the reading page, the annotation list, the annotation content box and the shelf search box (checked by moving focus with the mouse and keyboard and comparing screenshots). The 0.8x position/size offset and the box leaving the window no longer occurred. Narrator's Home window appeared at start and was minimized; Narrator was then stopped and EXReader closed.

Dialogs and compact layout: the packaged target (EXReaderProduct via tools/build_windows_host.py --static-reading) shows only the shelf, import row, reading page and annotation panes; the metadata, account, in-book search, directory and reading-record windows, the preferences menu and the compact layout are not part of it, so they could not be exercised here. Their DPI scaling changed only through the same MoveWindow/CreateWindowExW macros and SetWindowPos edits and stays unchecked; they belong to the Wave3 target, which needs its own package.

Not established: Narrator speech (still unheard; Live captions showed nothing earlier), every dialog and the compact layout at 125% (only the main window was exercised), 150% or higher scales, and moving the window between monitors of different DPI (system-aware only). The earlier defect candidate is considered fixed for the main window at 125%. Formal F09 and Narrator verification remain false.
