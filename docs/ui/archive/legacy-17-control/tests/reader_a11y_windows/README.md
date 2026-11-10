# Windows keyboard and accessibility audit (G12)

Automated UI Automation and real-keyboard audit of the fixed Win32 reference host
(`examples/reader.c`, built as the product `EXReaderProduct`) at the
handoff source. Tests only: no host, SDK or product file is modified.

    tests/reader_a11y_windows/
      run_audit.py       launches the packaged host, runs the seven flows, writes report.json
      flows.py           one named check per claim (shelf, import, organize, reading,
                         annotation, settings, keyboard)
      session.py         control identity, keyboard navigation, captures, UIA dumps
      uia_layer.py       IUIAutomationElement property/pattern reader
      keyboard.py        SendInput transport with a recorded posted-message fallback
      host.py            process control, IDC_* control identity, host.ini reader
      w32.py             ctypes Win32 bindings (enumeration, focus, capture)
      png.py             dependency-free PNG writer and pixel comparison
      evidence.py        key trace, named checks, source evidence
      verify_report.py   strict same-source validator for the produced evidence

## What the audit does

It starts the packaged host with a private `--data` directory and then drives it
**only** with the keyboard: Tab, Shift+Tab, arrows, Space, Enter, Escape and, when the
input queue is available, Ctrl chords. For each claimed behaviour it reads the UI
Automation tree of the real controls (by dialog control id and window class, which
is the identity `examples/reader.c` itself assigns), records the key trace, and
compares pixel rectangles for visible focus.

Flows: bookshelf and search, import, organize (details dialog), reading, annotation,
the existing inline size/zoom settings, and global keyboard traversal.

## What it produces

`report.json` with, for every check, the element locator, reproduction steps,
expected and actual result, severity, evidence reference and a minimal fix
suggestion; raw UIA trees (`uia/`), the key trace (`key-trace.jsonl`, one line per
input event with its transport), screenshots and focus crops, plus `verification.json`
from the strict validator.

`audit_completed` and `accessibility_accepted` are separate verdicts. A blocking
finding forces `accessibility_accepted: false` while the CI job can still succeed
because the evidence itself is valid.

## Limits

- Automated UIA plus injected input is **not** screen-reader acceptance. No NVDA or
  Narrator pass is performed, so `screen_reader_verified` stays `false`.
- The host paints page text itself and implements no accessibility provider; the audit
  records that as a measured finding (RD-02, KB-05) rather than judging speech output.
- If a runner session cannot deliver injected input, the audit records the
  `postmessage` transport and refuses to claim modifier-chord checks.
- Only the fixed Win32 host at the recorded source is in scope. iOS, Android, GTK,
  sync and network features are not audited here.
