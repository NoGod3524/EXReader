# F09 Windows Narrator check package

Authorized branch codex/dot-f09-narrator-package-20261031; parent 6c5f68e62c0ea95d8e3b4818ad4fadf7424b9e5d. Exactly three new files: run.py, workflow, this document. One initial Actions run and at most one correction limited to defects of this package; the job keeps the 90min cap. Build, packaging and the 26-check self-test run only in GitHub Actions.

## Purpose

Produce a downloadable, clean Windows candidate package for a manual real-Narrator check on the user's Windows 11 desktop. The user granted an explicit exception to download and unpack this artifact locally; every download is still confirmed with its name, source and size first.

## Build

Product source is the current tree, whose examples/reader.c and apps/reader/desktop/windows_accessibility.inc are guarded byte-equal to the pushed a835 routing candidate a8352f3623078e4d64b222c5af4dc7a2f2bfa379. No test-only diagnostic overlay and no EXR_F09_DIAGNOSTICS macro. The existing tools/build_windows_host.py packages it with --static-reading, including its generated Sample.epub; its self-test must pass with at least 26 checks. package-manifest.json records SHA256 and size for every payload file.

## Limits

This package proves nothing about Narrator by itself. The manual check result is recorded separately and only as Windows-target evidence; it does not touch the other five F09 targets or formal F09 state.

Initial status: source prepared, no run yet.

## Package result (1/2), 2026-10-31 06:56 UTC

Source 45ecf0feca221b672d74cbf9ed70294d2b116d97; run41174337334 attempt1, job124458651494: success. 26 Windows native host checks passed. Artifact13032094134, `f09-narrator-package-41174337334-1`, 17141311 bytes, SHA256 f79a86938cee096d5eb41a4a3bd376db9bc80cfc5bc0c352e823016e4b9bb4f6. 31 payload files; EXReader.exe SHA256 43ca4c9814cee46e275855345e8cc6604d16c77785fac6d8852433484434c289.

## Local Narrator observation, 2026-10-31 (user's Windows 11 desktop, explicit download exception)

Downloaded with user confirmation into a new empty folder; all 31 files matched the manifest hashes, no extra files. EXReader was started with a fresh profile and the packaged Sample.epub; it opened the sample book with the shelf, annotation panes and reading page visible. Narrator was turned on and off with its standard shortcut; Windows Live captions was started to transcribe speech.

Display: AppliedDPI 120 (125% scaling); primary screen 1536x960 logical. No DPI-awareness declaration or API (dpiAware, SetProcessDpiAwareness*, PerMonitor, GetDpiFor*) exists in apps/reader/desktop, examples/reader.c or the packager.

Observed:
- Narrator's visual focus highlight around the EXReader window, the reading page and a left-pane control was drawn at about 0.8 times the controls' on-screen position and size (125% inverse). Once it fell partly outside the EXReader window. This matches a DPI-unaware process whose accessibility rectangles are reported in unscaled coordinates under 125% scaling. It is a real Windows accessibility defect candidate for F09 (highlight, magnifier and touch exploration would point at the wrong place), not yet root-caused per control.
- Live captions displayed no transcript during the session, so Narrator's spoken output was not observed. Speech content is unverified.
- A Notepad control comparison was inconclusive (no Narrator highlight visible); it was stopped because Notepad held the user's own document. Nothing in Notepad was changed.

Not established: what Narrator speaks for the page, text navigation, selection and Escape; keyboard reachability of all features. These need a person listening to Narrator. Narrator verification remains false; formal F09 remains pending.
