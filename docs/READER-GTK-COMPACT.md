# Optional compact native GTK candidate

Status: **source candidate; no executed UI acceptance yet**.
Start: `25bc0c67971f81491f50e0a3caaaf7e509bb7e35`.
Reviewed production pin: `a7bcf0483fb52ecf9cd3cdf7dda07a4aa742f174`.

`EXR_READER_GTK_COMPACT` defaults **OFF** in `examples/linux/CMakeLists.txt`.
Only that file and `examples/linux/reader.c` change production. SDK3.41,
schema1, record/MAX2/wire formats, owners, existing dialogs and budgets remain
unchanged. Removing the new C conditionals must reproduce the exact old source
bytes, normalizing only CRLF/LF. The original CMake text must also match after
removing the four new option lines.

ON starts in the library with import, continue, search and the existing list.
Opening a book shows library/back, previous, next, contents and More. The old
selectable text, comment and note widgets are retained in an explicit panel.
All low-frequency actions are available in native GTK menus and use their
existing owner callbacks. Original function keys and Ctrl shortcuts remain.
Continue uses the existing open owner and last-book setting; closing the
library without opening Continue preserves that last book.

Layout changes visibility only when the desired state changes. Expanding text
and notes retains any larger window and restores at least the old 1040×820
default; hiding it does not shrink the window. Focus is handed to the reading
page when entering reading, and the original dialog lifetimes remain intact.

The independent workflow compiles and runs the ON UI **before** the expensive
original OFF GUI/old-owner regressions. It preserves all 31 original authored
OFF producer steps, fixtures, assertions, thresholds and judges. The one added
ON step increases the actual producer step count from 34 to 35. Original OFF
strict checks adapt only the exact new workflow identity and reviewed
production pin; the OFF report never grants ON behavior.

ON checks real pointer/keyboard/AT-SPI input, every More entry, TXT/EPUB/PDF/CBZ
pages, focus, dialog dismissal, notes, import cancellation/paste, library
search, two window sizes and close/reopen/continue. Native PNG screenshots,
AT-SPI trees, failures' visibility dictionaries, programs, maps and configuration
are retained. A final collector authenticates the real ZIPs and separate scopes
at the same source/run/attempt. Its 24 independent refusal controls and UI
cases are unexecuted until Actions runs them.

No local build, syntax test, fixture generation, UI execution or PNG/ZIP
processing is allowed. These functional checks grant no ON frame correctness,
performance, physical-device, screen-reader, six-platform or complete-product
acceptance.
