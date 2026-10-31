# F09 Windows Narrator check package

Authorized branch codex/dot-f09-narrator-package-20261031; parent 6c5f68e62c0ea95d8e3b4818ad4fadf7424b9e5d. Exactly three new files: run.py, workflow, this document. One initial Actions run and at most one correction limited to defects of this package; the job keeps the 90min cap. Build, packaging and the 26-check self-test run only in GitHub Actions.

## Purpose

Produce a downloadable, clean Windows candidate package for a manual real-Narrator check on the user's Windows 11 desktop. The user granted an explicit exception to download and unpack this artifact locally; every download is still confirmed with its name, source and size first.

## Build

Product source is the current tree, whose examples/reader.c and apps/reader/desktop/windows_accessibility.inc are guarded byte-equal to the pushed a835 routing candidate a8352f3623078e4d64b222c5af4dc7a2f2bfa379. No test-only diagnostic overlay and no EXR_F09_DIAGNOSTICS macro. The existing tools/build_windows_host.py packages it with --static-reading, including its generated Sample.epub; its self-test must pass with at least 26 checks. package-manifest.json records SHA256 and size for every payload file.

## Limits

This package proves nothing about Narrator by itself. The manual check result is recorded separately and only as Windows-target evidence; it does not touch the other five F09 targets or formal F09 state.

Initial status: source prepared, no run yet.
