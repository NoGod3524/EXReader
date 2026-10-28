# Linux GTK sync/account focused acceptance

The focused Linux GTK sync/account scope passed on source
`6b2e3a2d44e085c40fa20e07bbceef93706e8ff0`, Actions
[40629444286, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40629444286).
The combined job built the installed GTK host and passed the 27 retained
checks plus two new checks. They cover real GNOME Secret Service save, reload,
forget and unavailable/session-only behavior, actual HTTPS WebDAV failure,
cancellation and explicit retry, and read-only status captures in running,
cancelled, failed and completed sessions. The AT-SPI check reads the actual
live GTK text control, confirms it is not editable and compares its text to
the captured status. A bounded test-only worker gate holds the borrowed session
before capture; the test observes the session reach CLOSED while still retained,
then releases the gate and requires safe destruction and reopening. The gate is
compiled only in the dedicated Actions build and is absent from normal builds.

The separate same-run authentication job downloaded the original artifact and
verified its API digest and size, source/run/attempt, packaged host SHA-256,
all 27 original check names, both added checks and the unchanged bounds. The
artifact is `12790797986`, 5,185,218 bytes, SHA-256
`aea21c97eaa96a5aad9656b6419196e7581d18b098a1100ca2f3ea04de43c6fc`;
its host SHA-256 is
`ab8c2b7497b72d1af1121ac2cece610420ffb5c84b543a8aecbf4e26ec5b56a8`.
The identity report is retained in the same run. The earlier failed runs
40627094024 and 40627689240, and their evidence, remain intact.

This is acceptance of the focused Linux host scope on the stated source, not
acceptance of a composed six-platform product or of D26 on this source. The fixed catalog uses an Actions-only adapter for this pinned report, preserving
the original string-valued checks. It independently verifies the original ZIP,
all 29 named checks and the same-run authentication artifact. The catalog
admission remains subject to the existing fixed-catalog audit.
